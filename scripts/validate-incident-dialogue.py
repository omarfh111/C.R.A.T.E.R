"""Opt-in target-PC guard test: real DirectML capture must shut down optional AI.

No model installs or downloads. Run with the owned start-assistant.ps1 launcher
already idle. That launcher is expected to stop its own sidecar/GPU runners when
capture appears; shared Ollama is untouched. Output must be new inside checkout.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crater_assistant.server import live_capture_active, validate_origin


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--m1-python", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--assistant-url", default="http://127.0.0.1:8766")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT) or output == ROOT or not validate_origin(args.assistant_url):
        parser.error("new checkout child output and exact loopback assistant origin required")
    if live_capture_active():
        parser.error("another capture is active or cannot be excluded")
    prepared = args.cache / "prepared-onnx/ff690b0a8050566c290287545bd059350f3e9096/model_fp32.onnx"
    if not prepared.is_file() or not args.m1_python.is_file():
        parser.error("existing validated M1 environment and prepared ONNX cache required")
    before = (prepared.stat().st_size, prepared.stat().st_mtime_ns)
    output.mkdir(parents=True)
    command = [str(args.m1_python), "-B", "-m", "crater_m2.validation", "--output", str(output / "pipeline"),
        "--m3-contract", str(ROOT / "src/telemetry/contract.ts"), "--", "--perception-video",
        str(ROOT / "examples/m1-onnx-calibrated/scene.mp4"), "--calibration", str(ROOT / "examples/m1-onnx-calibrated/calibration.json"),
        "--device", "directml", "--cache-dir", str(args.cache), "--max-frames", "6", "--no-preview", "--duration", "60",
        "--drain", "30", "--fps", "50", "--bandwidth", "4096", "--latency", ".005", "--jitter", "0", "--loss", ".25",
        "--blackout", ".5:5", "--queue", "128", "--attempts", "20", "--seed", "7", "--incident-journal", str(output / "incidents.sqlite3")]
    env = dict(os.environ, PYTHONPATH=str(ROOT), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    opener = build_opener(ProxyHandler({}))
    started = time.perf_counter()
    checks, attempted = [], False
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        try:
            while process.poll() is None:
                if time.perf_counter()-started > 150:
                    raise TimeoutError("capture validation deadline exceeded")
                active = live_capture_active()
                if active and not attempted:
                    attempted = True
                    request = Request(args.assistant_url + "/ask", data=json.dumps({"question":"How does NASA DTN buffer data?", "topK":3}).encode(), headers={"Content-Type":"application/json"})
                    try:
                        with opener.open(request, timeout=2) as response:
                            checks.append({"elapsedS":time.perf_counter()-started,"captureGuard":True,"httpStatus":response.status})
                    except HTTPError as exc:
                        checks.append({"elapsedS":time.perf_counter()-started,"captureGuard":True,"httpStatus":exc.code})
                    except (OSError, URLError) as exc:
                        checks.append({"elapsedS":time.perf_counter()-started,"captureGuard":True,"serviceUnavailable":True,"errorType":type(exc).__name__})
                time.sleep(.1)
            if process.returncode:
                raise ValueError("real M1/M2 pipeline failed; inspect logs")
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
    result = dict(checks=checks, blocked=attempted and all(c.get("httpStatus") == 429 or c.get("serviceUnavailable") for c in checks),
                  preparedCacheUnchanged=before == (prepared.stat().st_size, prepared.stat().st_mtime_ns),
                  pipeline=json.loads((output / "pipeline/validation.json").read_text(encoding="utf-8")),
                  limitations="Short synthetic calibrated video; real DirectML pixel inference; simulated radio. Guard sequencing, not a concurrent throughput benchmark.")
    (output / "guard.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result["blocked"] or not result["preparedCacheUnchanged"]:
        raise ValueError("capture guard or read-only cache invariant failed")
    print(json.dumps({"blocked":True,"canonicalM3Validated":result["pipeline"]["canonicalM3Validated"],"frames":result["pipeline"]["webSocketFrames"]}))


if __name__ == "__main__":
    main()
