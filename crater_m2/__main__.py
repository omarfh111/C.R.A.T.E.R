"""Run calibrated M2 demo or replay calibrated M1 JSONL observations."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

from .bridge import TelemetryBridge
from .codec import encode_frame
from .radio import LinkConfig, RadioLink, ReliableTransport
from .source import Scenario, observation_to_frame, read_observations


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="virtual time, no WebSocket server")
    parser.add_argument("--input", type=Path, help="calibrated M1 observations JSONL; otherwise synthetic pixels")
    parser.add_argument("--duration", type=float, default=30, help="capture duration in seconds")
    parser.add_argument("--drain", type=float, default=60, help="maximum extra seconds to drain radio queue")
    parser.add_argument("--fps", type=float, default=1, help="generated observation frames per second")
    parser.add_argument("--bandwidth", type=float, default=256, help="shared DATA+ACK bytes per second")
    parser.add_argument("--latency", type=float, default=.1, help="one-way seconds")
    parser.add_argument("--jitter", type=float, default=.05, help="additional one-way jitter, seconds")
    parser.add_argument("--loss", type=float, default=.2, help="loss probability in each direction")
    parser.add_argument("--blackout", action="append", help="START:END seconds; repeatable (default 8:14)")
    parser.add_argument("--no-blackout", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--queue", type=int, default=64)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--start-sequence", type=int, default=0, help="must exceed M3's previous accepted sequence")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--report", type=Path, default=Path("artifacts/m2-report.json"))
    parser.add_argument("--received-jsonl", type=Path, default=Path("artifacts/received-frames.jsonl"))
    args = parser.parse_args(argv)
    for key in ("duration", "fps"):
        if not math.isfinite(getattr(args, key)) or getattr(args, key) <= 0:
            parser.error(f"{key} must be finite and positive")
    if args.fps > 50:
        parser.error("fps must be <= 50 (simulation tick is 20 ms)")
    if not math.isfinite(args.drain) or args.drain < 0:
        parser.error("drain must be finite and nonnegative")
    if not 0 <= args.start_sequence < 2**32:
        parser.error("start-sequence must fit uint32")
    if args.report.resolve() == args.received_jsonl.resolve():
        parser.error("report and received-jsonl must be different paths")
    if args.input and args.input.resolve() in (args.report.resolve(), args.received_jsonl.resolve()):
        parser.error("output paths must not overwrite input observations")
    if args.no_blackout and args.blackout:
        parser.error("use either --blackout or --no-blackout")
    try:
        intervals = tuple(tuple(map(float, interval.split(":"))) for interval in (args.blackout or ["8:14"]))
        args.link_config = LinkConfig(args.bandwidth, args.latency, args.jitter, args.loss,
                                     () if args.no_blackout else intervals, args.seed)
        ReliableTransport(RadioLink(args.link_config), max_queue=args.queue, max_attempts=args.attempts)
        TelemetryBridge(port=args.port)
    except ValueError as exc:
        parser.error(str(exc))
    return args


async def run_mission(args, bridge=None):
    transport = ReliableTransport(RadioLink(args.link_config), max_queue=args.queue, max_attempts=args.attempts)
    scenario = Scenario(datetime.now(timezone.utc), seed=args.seed) if args.input is None else None
    observations = iter(read_observations(args.input)) if args.input else None
    binary_sizes, json_sizes = [], []
    rejected, quantized_errors = [], []
    wall_start = time.perf_counter()
    elapsed = next_capture = 0.
    generated = 0
    source_done = False
    cancelled = False
    args.received_jsonl.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.received_jsonl.open("w", encoding="utf-8") as received:
            while elapsed <= args.duration + args.drain + 1e-9:
                if not args.benchmark:
                    await asyncio.sleep(max(0., wall_start + elapsed - time.perf_counter()))
                transport.advance(elapsed)
                for delivery in transport.take_deliveries():
                    received.write(json.dumps(delivery.frame, separators=(",", ":"), allow_nan=False) + "\n")
                    received.flush()
                    if scenario:
                        for hazard in delivery.frame["hazards"]:
                            truth = scenario.points[hazard["id"]][1]
                            position = tuple(hazard["position"][key] for key in ("xM", "yM", "zM"))
                            quantized_errors.append(math.dist(position, truth))
                    if bridge:
                        await bridge.publish(delivery.frame)
                if elapsed < args.duration - 1e-9 and elapsed + 1e-9 >= next_capture and not source_done:
                    link = dict(status=transport.link.status(elapsed), packetsSent=transport.link.data_sent,
                                packetsLost=transport.link.data_lost)
                    sequence = args.start_sequence + generated
                    if scenario:
                        result = scenario.capture(elapsed, sequence, link)
                    else:
                        try:
                            result = observation_to_frame(next(observations), sequence, link)
                        except StopIteration:
                            source_done = True
                            result = None
                    if result is not None:
                        rejected.extend(result.rejected)
                        binary_sizes.append(len(encode_frame(result.frame)))
                        json_sizes.append(len(json.dumps(result.frame, separators=(",", ":")).encode("utf-8")))
                        transport.enqueue(result.frame)
                        generated += 1
                        next_capture = generated / args.fps
                if (elapsed >= args.duration - 1e-9 or source_done) and not transport.pending:
                    break
                elapsed = round(elapsed + .02, 10)
    except asyncio.CancelledError:
        cancelled = True
    finally:
        if observations is not None:
            observations.close()
        report = dict(
            schemaVersion=1, mode="benchmark" if args.benchmark else "live",
            simulatedElapsedS=transport.clock, wallElapsedS=time.perf_counter()-wall_start,
            completed=transport.pending == 0 and (source_done or transport.clock >= args.duration - 1e-9),
            cancelled=cancelled,
            source=scenario.report() if scenario else dict(source="m1-calibrated-jsonl", rejectedDetections=len(rejected)),
            transport=transport.report(),
            meanBinaryFrameBytes=sum(binary_sizes)/len(binary_sizes) if binary_sizes else None,
            meanJsonFrameBytes=sum(json_sizes)/len(json_sizes) if json_sizes else None,
            totalRadioBytesPerOriginalJsonByte=transport.link.bytes_sent/sum(json_sizes) if sum(json_sizes) else None,
            maxDeliveredLocalizationErrorM=max(quantized_errors) if quantized_errors else None,
            rejectedDetections=rejected, slowWebSocketClients=bridge.slow_clients if bridge else 0,
            link=dict(bytesPerSecond=args.bandwidth, latencyS=args.latency, jitterS=args.jitter,
                      lossProbability=args.loss, blackouts=args.link_config.blackouts, seed=args.seed),
            byteAccounting="application packets including CRC, DATA retries and ACK; excludes TCP/WS/IP headers",
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if cancelled:
        raise asyncio.CancelledError
    return report


async def execute(args):
    if args.benchmark:
        return await run_mission(args)
    async with TelemetryBridge(port=args.port) as bridge:
        print(f"M2 station ready: {bridge.url}", flush=True)
        print("Source: calibrated synthetic pixels" if not args.input else f"Source: {args.input}", flush=True)
        return await run_mission(args, bridge)


def main(argv=None):
    args = arguments(argv)
    try:
        report = asyncio.run(execute(args))
    except KeyboardInterrupt:
        print("Mission stopped; partial report saved.")
        return 130
    except (ValueError, OSError) as exc:
        raise SystemExit(f"M2 error: {exc}") from exc
    print(json.dumps(report, indent=2))
    return 0 if report["completed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
