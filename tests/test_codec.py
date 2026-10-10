from copy import deepcopy
import json
import struct
import zlib

import pytest

from crater_m2.codec import encode_frame, decode_frame, encode_ack, decode_ack


def test_roundtrip_canonical_frame(frame):
    packet = encode_frame(frame)
    result = decode_frame(packet)
    assert result["sequence"] == frame["sequence"]
    assert result["link"] == frame["link"]
    assert result["capturedAt"] == frame["capturedAt"]
    assert result["hazards"][0]["confidence"] == pytest.approx(.87, abs=1/65535)
    assert result["hazards"][0]["position"] == frame["hazards"][0]["position"]
    assert len(packet) < len(json.dumps(frame, separators=(",", ":")).encode())


def test_unicode_ids_empty_hazards_and_offsets(frame):
    frame["roverId"] = "rover-é"
    frame["capturedAt"] = "2026-10-10T13:00:00.000+01:00"
    frame["hazards"] = []
    result = decode_frame(encode_frame(frame))
    assert result["roverId"] == "rover-é"
    assert result["capturedAt"] == "2026-10-10T12:00:00.000Z"
    assert result["hazards"] == []


def test_quantization_preserves_uncertainty_bounds(frame):
    frame["hazards"][0]["position"]["xM"] = -1.23456
    frame["hazards"][0]["uncertaintyRadiusM"] = .10001
    result = decode_frame(encode_frame(frame))["hazards"][0]
    assert abs(result["position"]["xM"] + 1.23456) <= .0005
    assert .10001 <= result["uncertaintyRadiusM"] < .10102


@pytest.mark.parametrize("change", ["sequence", "position", "huge_position", "uncertainty", "huge_uncertainty", "id", "timestamp"])
def test_refuse_unrepresentable_values(frame, change):
    if change == "sequence":
        frame["sequence"] = 2**32
    elif change == "position":
        frame["roverPosition"]["xM"] = 3e6
    elif change == "huge_position":
        frame["roverPosition"]["xM"] = 1e308
    elif change == "uncertainty":
        frame["positionUncertaintyRadiusM"] = 5e6
    elif change == "huge_uncertainty":
        frame["positionUncertaintyRadiusM"] = 1e308
    elif change == "id":
        frame["roverId"] = "é" * 128
    else:
        frame["capturedAt"] = "1960-01-01T00:00:00Z"
        frame["hazards"] = []
    with pytest.raises(ValueError):
        encode_frame(frame)


def test_corruption_and_every_truncation_rejected(frame):
    packet = encode_frame(frame)
    for size in range(len(packet)):
        with pytest.raises(ValueError):
            decode_frame(packet[:size])
    broken = bytearray(packet)
    broken[10] ^= 1
    with pytest.raises(ValueError):
        decode_frame(bytes(broken))


def test_extra_bytes_with_valid_crc_rejected(frame):
    payload = encode_frame(frame)[:-4] + b"extra"
    with pytest.raises(ValueError):
        decode_frame(payload + struct.pack(">I", zlib.crc32(payload)))


def test_unknown_binary_version_rejected(frame):
    payload = bytearray(encode_frame(frame)[:-4])
    payload[2] = 2
    with pytest.raises(ValueError):
        decode_frame(bytes(payload) + struct.pack(">I", zlib.crc32(payload)))


def test_packet_size_cap(frame):
    frame["hazards"] = [deepcopy(frame["hazards"][0]) for _ in range(3000)]
    with pytest.raises(ValueError):
        encode_frame(frame)


def test_ack_roundtrip_corruption_and_type():
    packet = encode_ack(42)
    assert decode_ack(packet) == 42
    with pytest.raises(ValueError):
        decode_ack(packet + b"x")
    with pytest.raises(ValueError):
        encode_ack(True)
    broken = bytearray(packet)
    broken[-1] ^= 1
    with pytest.raises(ValueError):
        decode_ack(bytes(broken))
