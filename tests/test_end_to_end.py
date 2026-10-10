import asyncio
import json
import sys
import time

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from crater_m2.contract import validate_frame


def test_live_cli_delivers_through_blackout_to_real_websocket(tmp_path):
    async def check():
        report_path = tmp_path / "report.json"
        received_path = tmp_path / "received.jsonl"
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "crater_m2", "--duration", "3", "--drain", "5",
            "--port", "0", "--fps", "1", "--bandwidth", "1000", "--loss", "0",
            "--latency", ".01", "--jitter", "0", "--blackout", ".5:1.5",
            "--report", str(report_path), "--received-jsonl", str(received_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        frames, arrival_times = [], []
        try:
            ready = (await asyncio.wait_for(process.stdout.readline(), 5)).decode().strip()
            assert "station ready:" in ready
            url = ready.split("ready: ", 1)[1]
            async with connect(url) as client:
                while True:
                    try:
                        text = await asyncio.wait_for(client.recv(), 8)
                    except ConnectionClosed:
                        break
                    frames.append(validate_frame(json.loads(text)))
                    arrival_times.append(time.monotonic())
            _, stderr = await asyncio.wait_for(process.communicate(), 5)
            assert process.returncode == 0, stderr.decode()
            assert [frame["sequence"] for frame in frames] == [0, 1, 2]
            assert arrival_times[1] - arrival_times[0] >= 1
            report = json.loads(report_path.read_text())
            assert report["transport"]["deliveryRate"] == 1
            assert report["transport"]["ackPacketsSent"] == 3
            assert report["completed"]
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    asyncio.run(check())
