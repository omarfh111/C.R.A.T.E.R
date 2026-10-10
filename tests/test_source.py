from datetime import datetime, timezone

import pytest

from crater_m2.contract import validate_frame
from crater_m2.source import Scenario, observation_to_frame, read_observations


@pytest.fixture
def observation():
    return {"roverId": "rover-1", "capturedAt": "2026-10-10T12:00:00.000Z",
            "roverPosition": {"frameId": "LOCAL_ENU_V1", "xM": 0, "yM": 0, "zM": 0},
            "positionUncertaintyRadiusM": .1,
            "camera": {"width": 640, "height": 480, "fx": 400, "fy": 400, "cx": 320, "cy": 240,
                       "centerEnuM": [0, 0, 2], "rotationCameraToEnu": [[1, 0, 0], [0, -1, 0], [0, 0, -1]]},
            "detections": [{"id": "rock-1", "type": "rock", "bboxPx": [300, 200, 340, 240], "confidence": .9}]}


def test_bbox_bottom_contact_and_stable_id(observation):
    result = observation_to_frame(observation, 1, dict(status="connected", packetsSent=0, packetsLost=0))
    assert result.rejected == []
    hazard = result.frame["hazards"][0]
    assert hazard["id"] == "rock-1"
    assert hazard["position"]["xM"] == pytest.approx(0)
    assert hazard["position"]["yM"] == pytest.approx(0)
    assert hazard["observedAt"] == observation["capturedAt"]
    validate_frame(result.frame)


def test_invalid_detection_is_reported_not_invented(observation):
    observation["detections"].append(dict(id="bad", type="rock", contactPixel=[-1, 0], confidence=.9))
    result = observation_to_frame(observation, 1, dict(status="degraded", packetsSent=1, packetsLost=1))
    assert len(result.frame["hazards"]) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0]["id"] == "bad"


def test_missing_calibration_fails(observation):
    del observation["camera"]
    with pytest.raises(ValueError, match="camera"):
        observation_to_frame(observation, 1, dict(status="connected", packetsSent=0, packetsLost=0))


def test_scenario_reconstructs_known_positions_and_moving_pose():
    scenario = Scenario(datetime(2026, 10, 10, tzinfo=timezone.utc), pixel_noise_px=0)
    first = scenario.capture(0, 0, dict(status="connected", packetsSent=0, packetsLost=0))
    later = scenario.capture(5, 1, dict(status="connected", packetsSent=1, packetsLost=0))
    assert first.frame["roverPosition"] != later.frame["roverPosition"]
    assert len(first.frame["hazards"]) >= 2
    assert set(h["id"] for h in first.frame["hazards"]) == set(h["id"] for h in later.frame["hazards"])
    assert scenario.report()["maxLocalizationErrorM"] < 1e-10
    assert scenario.report()["evaluatedObservations"] >= 4


def test_jsonl_line_errors_are_actionable(tmp_path):
    file = tmp_path / "observations.jsonl"
    file.write_text('{}\nnot-json\n', encoding="utf-8")
    stream = read_observations(file)
    assert next(stream) == {}
    with pytest.raises(ValueError, match="line 2"):
        next(stream)
