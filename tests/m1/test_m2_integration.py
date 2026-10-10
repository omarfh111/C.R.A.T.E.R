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
