import json
import math
import os
import sys
from pathlib import Path
import pytest
from crater_m1.simulation import generate
from crater_m1.pipeline import run
from crater_m1.detectors import SyntheticContrastDetector
from crater_m1.tracking import iou

@pytest.mark.skipif(not os.environ.get("CRATER_M2_SOURCE"),reason="set CRATER_M2_SOURCE to a checkout of M2")
def test_actual_m2_localizes_detected_pixels_and_rejects_uncalibrated_video(tmp_path):
    sys.path.insert(0,os.environ["CRATER_M2_SOURCE"])
    from crater_m2.source import observation_to_frame
    from crater_m2.contract import validate_frame
    generate(tmp_path/"scene",count=12)
    run(tmp_path/"scene/scene.mp4",tmp_path/"run",SyntheticContrastDetector(),calibration=tmp_path/"scene/calibration.json",preview=False)
    truth=json.loads((tmp_path/"scene/annotations.json").read_text())["frames"]
    errors=[]
    for index,line in enumerate((tmp_path/"run/observations.jsonl").read_text().splitlines()):
        observation=json.loads(line)
        result=observation_to_frame(observation,index,{"status":"connected","packetsSent":0,"packetsLost":0})
        assert not result.rejected
        assert len(result.frame["hazards"])==3
        validate_frame(result.frame)
        for detected,hazard in zip(observation["detections"],result.frame["hazards"]):
            expected=max(truth[index]["detections"],key=lambda item:iou(item["bboxPx"],detected["bboxPx"]))
            pos=[hazard["position"][axis] for axis in ("xM","yM","zM")]
            errors.append(math.dist(pos,expected["position_enu_m"]))
        observation["camera"]=None
        with pytest.raises(ValueError,match="calibration"): observation_to_frame(observation,index,{"status":"connected","packetsSent":0,"packetsLost":0})
    assert max(errors)<.1  # Integer contact pixels introduce quantization.


@pytest.mark.skipif(not os.environ.get("CRATER_M2_SOURCE"),reason="M2 checkout required")
def test_m1_pixels_reach_actual_local_websocket_after_radio_losses(tmp_path):
    import asyncio
    sys.path.insert(0,os.environ["CRATER_M2_SOURCE"])
    from crater_m2.__main__ import arguments, run_mission
    from crater_m2.bridge import TelemetryBridge
    from crater_m2.contract import validate_frame
    from websockets.asyncio.client import connect
    generate(tmp_path/"scene",count=6)
    run(tmp_path/"scene/scene.mp4",tmp_path/"run",SyntheticContrastDetector(),calibration=tmp_path/"scene/calibration.json",preview=False)
    args=arguments(["--input",str(tmp_path/"run/observations.jsonl"),"--fps","10","--duration",".6", "--drain","10",
        "--bandwidth","4096","--latency",".005","--jitter","0","--loss",".2","--blackout",".2:.4","--port","0",
        "--report",str(tmp_path/"report.json"),"--received-jsonl",str(tmp_path/"received.jsonl")])
    async def mission():
        async with TelemetryBridge(port=0) as bridge:
            async with connect(bridge.url) as client:
                task=asyncio.create_task(run_mission(args,bridge))
                frames=[validate_frame(json.loads(await asyncio.wait_for(client.recv(),10))) for _ in range(6)]
                report=await task
                assert [f["sequence"] for f in frames]==list(range(6))
                assert all(len(f["hazards"])==3 for f in frames)
                assert report["completed"] and report["transport"]["delivered"]==6
                assert report["transport"]["dataPacketsLost"]>0
    asyncio.run(mission())
