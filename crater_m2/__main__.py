"""Run calibrated M2 demo or replay calibrated M1 JSONL observations."""

import argparse
import ctypes
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

from .bridge import TelemetryBridge
from .codec import encode_frame
from .contract import timestamp
from .metrics import RunningStats
from .radio import LinkConfig, RadioLink, ReliableTransport
from .source import Scenario, observation_to_frame, read_observations


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="virtual time, no WebSocket server")
    parser.add_argument("--input", type=Path, help="calibrated M1 observations JSONL; otherwise synthetic pixels")
    parser.add_argument("--input-ground-z", type=float, help="explicit known ground-plane height for raw M1 JSONL, in ENU meters")
    parser.add_argument("--perception-video", type=Path, help="local M1 video -> callback -> M2, in real time")
    parser.add_argument("--calibration", type=Path, help="M1 calibrated per-frame camera poses for the video")
    parser.add_argument("--perception-backend", choices=("onnx-grounding-dino", "grounding-dino", "synthetic-contrast"), default="onnx-grounding-dino")
    parser.add_argument("--perception-output", type=Path, default=Path("outputs/m1-live"))
    parser.add_argument("--perception-buffer", type=int, default=4, help="bounded callback handoff; full buffer slows M1")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "directml"), default="auto")
    parser.add_argument("--threshold", type=float, default=.25)
    parser.add_argument("--text-threshold", type=float, default=.2)
    parser.add_argument("--terrain-filter", choices=("edges", "area", "off"), default="edges")
    parser.add_argument("--max-rock-area", type=float, default=.5)
    parser.add_argument("--tiles", choices=("off", "2x2"), default="off")
    parser.add_argument("--track-min-hits", type=int, default=2)
    parser.add_argument("--track-max-missed", type=int, default=3)
    parser.add_argument("--confirmed-only", action="store_true")
    parser.add_argument("--cache-dir", default=".cache/huggingface")
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--duration", type=float, default=30, help="mission capture window in seconds; includes M1 model startup")
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
    parser.add_argument("--link-history", type=int, default=4096, help="maximum retained DATA snapshots; older captures fail explicitly")
    parser.add_argument("--rejection-samples", type=int, default=100, help="maximum rejected detection details in report; totals remain complete")
    parser.add_argument("--start-sequence", type=int, default=0, help="must exceed M3's previous accepted sequence")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--wait-for-client", type=float, default=0, help="wait up to this many seconds for a WebSocket receiver before capture")
    parser.add_argument("--report", type=Path, default=Path("artifacts/m2-report.json"))
    parser.add_argument("--received-jsonl", type=Path, default=Path("artifacts/received-frames.jsonl"))
    args = parser.parse_args(argv)
    if args.input_ground_z is not None and (args.input is None or not math.isfinite(args.input_ground_z)):
        parser.error("input-ground-z requires --input and finite ENU meters")
    if not math.isfinite(args.wait_for_client) or args.wait_for_client < 0:
        parser.error("wait-for-client must be finite and nonnegative")
    if args.link_history < 1 or args.rejection_samples < 0:
        parser.error("link-history must be positive and rejection-samples nonnegative")
    if args.perception_video:
        if args.device == "cuda" and args.perception_backend != "grounding-dino":
            parser.error("cuda requires the PyTorch grounding-dino backend")
        if args.device == "directml" and args.perception_backend != "onnx-grounding-dino":
            parser.error("directml requires onnx-grounding-dino")
        if args.tiles != "off" and args.perception_backend != "onnx-grounding-dino":
            parser.error("tiles require onnx-grounding-dino")
        if not (0 < args.threshold < 1 and 0 < args.text_threshold < 1 and 0 < args.max_rock_area <= 1):
            parser.error("invalid perception thresholds")
        if args.track_min_hits < 1 or args.track_max_missed < 0:
            parser.error("invalid track confirmation/retention limits")
        if args.input or args.benchmark:
            parser.error("--perception-video uses a live callback; choose JSONL --input for --benchmark")
        if args.calibration is None:
            parser.error("--perception-video requires --calibration; metric coordinates cannot be inferred")
        if args.perception_buffer < 1 or args.stride < 1 or (args.max_frames is not None and args.max_frames < 1):
            parser.error("perception-buffer, stride and max-frames must be positive")
        if not args.perception_video.is_file() or not args.calibration.is_file():
            parser.error("perception video and calibration files must exist")
        if (args.perception_output / "observations.jsonl").exists():
            parser.error("perception-output already contains a run; choose a new directory")
        m1_output = args.perception_output.resolve()
        for source in (args.perception_video.resolve(), args.calibration.resolve()):
            if source in (args.report.resolve(), args.received_jsonl.resolve()) or source.is_relative_to(m1_output):
                parser.error("output paths must not overwrite video/calibration; use a separate M1 output directory")
        if any(path.resolve().is_relative_to(m1_output) for path in (args.report, args.received_jsonl)):
            parser.error("M2 report/received-jsonl must be outside the M1 perception-output directory")
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


async def run_mission(args, bridge=None, *, stream=None):
    transport = ReliableTransport(RadioLink(args.link_config, history_capacity=args.link_history), max_queue=args.queue, max_attempts=args.attempts)
    scenario = Scenario(datetime.now(timezone.utc), seed=args.seed) if args.input is None and stream is None else None
    observations = iter(read_observations(args.input)) if args.input else None
    binary_bytes = json_bytes = rejected_count = 0
    rejected = []
    quantized_errors = RunningStats()
    wall_start = time.perf_counter()
    mission_utc_start = datetime.now(timezone.utc)
    elapsed = next_capture = 0.
    generated = 0
    source_done = False
    cancelled = False
    failure = None
    args.received_jsonl.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.received_jsonl.open("w", encoding="utf-8") as received:
            while elapsed <= args.duration + args.drain + 1e-9:
                if not args.benchmark:
                    await asyncio.sleep(max(0., wall_start + elapsed - time.perf_counter()))
                    elapsed = time.perf_counter() - wall_start
                transport.advance(elapsed)
                for delivery in transport.take_deliveries():
                    received.write(json.dumps(delivery.frame, separators=(",", ":"), allow_nan=False) + "\n")
                    received.flush()
                    if scenario:
                        for hazard in delivery.frame["hazards"]:
                            truth = scenario.points[hazard["id"]][1]
                            position = tuple(hazard["position"][key] for key in ("xM", "yM", "zM"))
                            quantized_errors.add(math.dist(position, truth))
                    if bridge:
                        await bridge.publish(delivery.frame)
                if elapsed < args.duration - 1e-9 and elapsed + 1e-9 >= next_capture and not source_done:
                    link = dict(status=transport.link.status(elapsed), packetsSent=transport.link.data_sent,
                                packetsLost=transport.link.data_lost)
                    sequence = args.start_sequence + generated
                    if scenario:
                        result = scenario.capture(elapsed, sequence, link)
                    elif stream is not None:
                        observation = stream.poll()
                        source_done = observation is None and stream.done
                        if observation is not None:
                            captured_s = max(0., (timestamp(observation["capturedAt"]) - mission_utc_start).total_seconds())
                            link = transport.link.snapshot(captured_s)
                            result = observation_to_frame(observation, sequence, link)
                        else:
                            result = None
                    else:
                        try:
                            observation = next(observations)
                            if args.input_ground_z is not None:
                                observation = dict(observation, groundZM=args.input_ground_z)
                            result = observation_to_frame(observation, sequence, link)
                        except StopIteration:
                            source_done = True
                            result = None
                    if result is not None:
                        packet_size = len(encode_frame(result.frame))
                        json_size = len(json.dumps(result.frame, separators=(",", ":")).encode("utf-8"))
                        transport.enqueue(result.frame)
                        rejected_count += len(result.rejected)
                        rejected.extend(result.rejected[:max(0, args.rejection_samples - len(rejected))])
                        binary_bytes += packet_size
                        json_bytes += json_size
                        generated += 1
                        next_capture = elapsed + 1/args.fps if stream is not None else generated / args.fps
                if (elapsed >= args.duration - 1e-9 or source_done) and not transport.pending:
                    break
                if elapsed >= args.duration + args.drain:
                    break
                elapsed = min(round(elapsed + .02, 10), args.duration + args.drain)
    except asyncio.CancelledError:
        cancelled = True
    except (ValueError, OSError) as exc:
        failure = str(exc)
        raise
    finally:
        if observations is not None:
            observations.close()
        report = dict(
            schemaVersion=1, mode="benchmark" if args.benchmark else "live",
            simulatedElapsedS=transport.clock, wallElapsedS=time.perf_counter()-wall_start,
            completed=generated > 0 and failure is None and not cancelled and transport.pending == 0
                and (source_done or transport.clock >= args.duration - 1e-9),
            cancelled=cancelled,
            source=scenario.report() if scenario else dict(
                source="m1-live-callback" if stream is not None else "m1-calibrated-jsonl",
                rejectedDetections=rejected_count),
            transport=transport.report(),
            meanBinaryFrameBytes=binary_bytes/generated if generated else None,
            meanJsonFrameBytes=json_bytes/generated if generated else None,
            totalRadioBytesPerOriginalJsonByte=transport.link.bytes_sent/json_bytes if json_bytes else None,
            maxDeliveredLocalizationErrorM=quantized_errors.maximum,
            rejectedDetections=rejected, slowWebSocketClients=bridge.slow_clients if bridge else 0,
            rejectedDetectionsOmitted=rejected_count-len(rejected),
            diagnosticLimits=dict(rejectionSamples=args.rejection_samples, radioHistorySnapshots=args.link_history),
            link=dict(bytesPerSecond=args.bandwidth, latencyS=args.latency, jitterS=args.jitter,
                      lossProbability=args.loss, blackouts=args.link_config.blackouts, seed=args.seed),
            byteAccounting="application packets including CRC, DATA retries and ACK; excludes TCP/WS/IP headers",
        )
        if failure is not None:
            report["source"]["error"] = failure
        save_report(args, report)
    if cancelled:
        raise asyncio.CancelledError
    return report


def save_report(args, report):
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


async def execute(args):
    if args.benchmark:
        return await run_mission(args)
    async with TelemetryBridge(port=args.port) as bridge:
        print(f"M2 station ready: {bridge.url}", flush=True)
        if args.wait_for_client:
            deadline = asyncio.get_running_loop().time() + args.wait_for_client
            while bridge.client_count == 0:
                if asyncio.get_running_loop().time() >= deadline:
                    raise ValueError("no WebSocket receiver connected before capture timeout")
                await asyncio.sleep(.01)
        if args.perception_video:
            from .perception import PerceptionStream, local_producer

            print(f"Source: local M1 callback ({args.perception_backend}); calibrated video {args.perception_video}", flush=True)
            report = None
            try:
                async with PerceptionStream(local_producer(args), capacity=args.perception_buffer) as stream:
                    report = await run_mission(args, bridge, stream=stream)
            except ValueError as exc:
                if report is not None:
                    report["completed"] = False
                    report["source"]["error"] = str(exc)
                    save_report(args, report)
                raise
            report["source"].update(
                producerCompleted=stream.result is not None, interrupted=stream.interrupted,
                offeredObservations=stream.produced, consumedObservations=stream.consumed,
                maxSampledBufferedObservations=stream.max_buffered,
                callbackHandoffWaitS=stream.handoff_wait_s,
                maxCallbackHandoffWaitS=stream.max_handoff_wait_s,
                perceptionMetrics=stream.result,
                discardedAtStop=stream.buffered + int(stream.interrupted),
                timing="mission window includes local model startup; capturedAt remains M1 capture time")
            save_report(args, report)
            return report
        print("Source: calibrated synthetic pixels" if not args.input else f"Source: {args.input}", flush=True)
        return await run_mission(args, bridge)


def _terminate_windows_process(code):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    kernel.TerminateProcess.restype = ctypes.c_int
    if not kernel.TerminateProcess(kernel.GetCurrentProcess(), code):
        raise OSError(ctypes.get_last_error(), "unable to terminate completed DirectML process")


def _finish_process(args, code, *, platform=sys.platform):
    # The threaded DirectML runtime on Windows can hang in CRT DLL teardown.
    # The producer, sockets and reports have closed; flush before process exit.
    if platform == "win32" and args.perception_video and args.device == "directml":
        sys.stdout.flush()
        sys.stderr.flush()
        _terminate_windows_process(code)
    return code


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
    return _finish_process(args, 0 if report["completed"] else 2)


if __name__ == "__main__":
    raise SystemExit(main())
