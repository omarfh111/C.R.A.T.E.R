"""Capture the real M2 WebSocket and validate it with M3's actual v1 parser.

No implicit synthetic source and no model downloads. Use JSONL first, then
explicit ONNX/DirectML arguments with the prepared model and calibrated video.
"""
import argparse
import asyncio
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from websockets.asyncio.client import connect

from .__main__ import arguments
from .contract import validate_frame


async def capture_pipeline(m2_args, output, *, shutdown_timeout=180):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("validation output already exists; choose a new directory")
    if not math.isfinite(shutdown_timeout) or shutdown_timeout <= 0:
        raise ValueError("positive finite shutdown timeout required")
    command_args = [*m2_args, "--port", "0", "--wait-for-client", "30", "--report", str(output / "m2-report.json"),
                    "--received-jsonl", str(output / "decoded.jsonl"),
                    "--perception-output", str(output / "perception")]
    args = arguments(command_args)
    if args.benchmark or not (args.input or args.perception_video):
        raise ValueError("validation requires explicit calibrated JSONL or perception video, with real WebSocket")
    for source in (args.input, args.calibration, args.perception_video):
        if source is not None and source.resolve().is_relative_to(output):
            raise ValueError("validation output must be separate from source files")
    output.mkdir(parents=True)
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       HF_HUB_DISABLE_TELEMETRY="1", PYTHONUNBUFFERED="1")
    process = None
    logger = None
    count = 0
    with (output / "stderr.log").open("wb") as errors, (output / "stdout.log").open("wb") as logs:
        try:
            process = await asyncio.create_subprocess_exec(sys.executable, "-m", "crater_m2", *command_args,
                stdout=asyncio.subprocess.PIPE, stderr=errors, env=environment)
            ready = await asyncio.wait_for(process.stdout.readline(), 30)
            logs.write(ready)
            line = ready.decode("utf-8").strip()
            if not line.startswith("M2 station ready: "):
                raise ValueError("M2 did not start; inspect stderr.log")
            async def log_stdout():
                while block := await process.stdout.read(65536):
                    logs.write(block)
            logger = asyncio.create_task(log_stdout())
            started = time.perf_counter()
            async def collect():
                nonlocal count
                async with connect(line.split("ready: ", 1)[1]) as client:
                    with (output / "websocket.jsonl").open("w", encoding="utf-8") as frames, \
                         (output / "arrivals.jsonl").open("w", encoding="utf-8") as arrivals:
                        async for message in client:
                            frame = validate_frame(json.loads(message))
                            frames.write(json.dumps(frame, allow_nan=False) + "\n")
                            arrivals.write(json.dumps({"sequence": frame["sequence"],
                                "receiverElapsedS": time.perf_counter()-started}) + "\n")
                            count += 1
            await asyncio.wait_for(collect(), args.duration + args.drain + shutdown_timeout)
            await asyncio.wait_for(process.wait(), shutdown_timeout)
            await logger
            if process.returncode != 0:
                raise ValueError(f"M2 exit {process.returncode}; inspect m2-report.json and stderr.log")
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if logger is not None:
                await asyncio.gather(logger, return_exceptions=True)
    report = json.loads((output / "m2-report.json").read_text(encoding="utf-8"))
    matches = True
    with (output / "websocket.jsonl").open(encoding="utf-8") as socket_frames, \
         (output / "decoded.jsonl").open(encoding="utf-8") as decoded:
        for actual, expected in itertools.zip_longest(socket_frames, decoded):
            if actual is None or expected is None or json.loads(actual) != json.loads(expected):
                matches = False
                break
    result = dict(webSocketFrames=count, socketMatchesDecodedFrames=matches, m2Report=report,
                  offlineEnvironment=True, canonicalM3Validated=False,
                  timing="Receiver arrival times are relative to station ready, not original video sensor cadence.")
    (output / "validation.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if not matches or count == 0 or count != report["transport"]["delivered"]:
        raise ValueError("WebSocket capture differs from decoded deliveries; see validation.json")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--m3-contract", type=Path, required=True, help="actual M3 src/telemetry/contract.ts")
    parser.add_argument("--node", default="node", help="Node >=22.18 executable")
    parser.add_argument("--shutdown-timeout", type=float, default=180)
    parser.add_argument("m2_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if not args.m3_contract.is_file() or not (shutil.which(args.node) or Path(args.node).is_file()):
        parser.error("M3 contract and Node executable must exist locally before validation")
    m2_args = args.m2_args[1:] if args.m2_args[:1] == ["--"] else args.m2_args
    try:
        result = asyncio.run(capture_pipeline(m2_args, args.output, shutdown_timeout=args.shutdown_timeout))
        validator = Path(__file__).resolve().parent.parent / "scripts/validate-m3-contract.mjs"
        check = subprocess.run([args.node, str(validator), str(args.m3_contract.resolve()),
                                str(args.output.resolve() / "websocket.jsonl")],
                               capture_output=True, text=True, timeout=60)
        if check.returncode:
            raise ValueError("M3 canonical validation failed: " + check.stderr[:2000])
        result.update(canonicalM3Validated=True, m3Contract=str(args.m3_contract.resolve()),
                      m3Validation=check.stdout.strip())
        (args.output / "validation.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(check.stdout.strip())
        print(f"Metrics: {(args.output / 'validation.json').resolve()}")
        return 0
    except (ValueError, OSError, asyncio.TimeoutError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, f"Pipeline validation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
