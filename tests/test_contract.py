import pytest

from crater_m2.contract import timestamp, validate_frame


def test_canonical_frame_is_valid_and_copied(frame):
    result = validate_frame(frame)
    assert result == frame
    result["link"]["packetsSent"] = 100
    assert frame["link"]["packetsSent"] == 42


@pytest.mark.parametrize("field,value", [
    ("schemaVersion", 2), ("schemaVersion", True), ("sequence", -1),
    ("sequence", 1.5), ("sequence", True), ("roverId", ""),
    ("capturedAt", "2026-10-10T12:00:00"),
    ("capturedAt", "2026-02-30T12:00:00Z"),
    ("capturedAt", "2026-10-10T12:00:00+00:99"),
    ("capturedAt", "2026-10-10T12:00:00-24:00"),
    ("positionUncertaintyRadiusM", float("nan")),
])
def test_reject_invalid_frame_fields(frame, field, value):
    frame[field] = value
    with pytest.raises(ValueError):
        validate_frame(frame)


@pytest.mark.parametrize("target", ["root", "position", "link", "hazard"])
def test_reject_unknown_fields(frame, target):
    obj = {"root": frame, "position": frame["roverPosition"],
           "link": frame["link"], "hazard": frame["hazards"][0]}[target]
    obj["extra"] = 1
    with pytest.raises(ValueError):
        validate_frame(frame)


@pytest.mark.parametrize("change", ["confidence", "future", "loss", "frame", "infinite"])
def test_reject_bad_semantics(frame, change):
    if change == "confidence":
        frame["hazards"][0]["confidence"] = 90
    elif change == "future":
        frame["hazards"][0]["observedAt"] = "2026-10-10T12:00:01Z"
    elif change == "loss":
        frame["link"]["packetsLost"] = 43
    elif change == "frame":
        frame["roverPosition"]["frameId"] = "GPS"
    else:
        frame["roverPosition"]["xM"] = float("inf")
    with pytest.raises(ValueError):
        validate_frame(frame)


def test_timezone_offsets_and_empty_hazards(frame):
    frame["capturedAt"] = "2026-10-10T13:00:00+01:00"
    assert validate_frame(frame) == frame
    frame["hazards"] = []
    assert validate_frame(frame)["hazards"] == []


def test_invalid_offset_is_not_normalized():
    with pytest.raises(ValueError):
        timestamp("2026-10-10T12:00:00+00:99")
