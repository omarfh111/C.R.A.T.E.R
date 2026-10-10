"""Self-contained binary telemetry v1 and ACKs (big endian, CRC32).

Millimetre coordinates, millisecond UTC timestamps, uint16 confidence.
No external ID dictionary, no cloud service and no image payloads required.
"""

from datetime import datetime, timedelta, timezone
import math
import struct
import zlib

from .contract import (HAZARD_TYPES, LINK_STATUSES, coordinates, timestamp,
                       utc_iso, validate_frame)

HEADER = struct.Struct(">2sBIQiiiIBIIH")
HAZARD = struct.Struct(">BiiiIHQ")
ACK = struct.Struct(">2sBI")
MAX_PACKET_BYTES = 65507
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _uint(value, bits):
    if type(value) not in (int, float) or not math.isfinite(value) or int(value) != value or not 0 <= value < 2**bits:
        raise ValueError(f"value does not fit uint{bits}")
    return int(value)


def _mm(value):
    if not -(2**31) / 1000 <= value < 2**31 / 1000:
        raise ValueError("position exceeds int32 millimetre range")
    mm = round(value * 1000)
    if not -(2**31) <= mm < 2**31:
        raise ValueError("position exceeds int32 millimetre range")
    return mm


def _radius(value):
    if not 0 <= value <= (2**32 - 1) / 1000:
        raise ValueError("uncertainty exceeds uint32 millimetre range")
    return _uint(math.ceil(value * 1000), 32)


def _position(value):
    return tuple(_mm(value[key]) for key in ("xM", "yM", "zM"))


def _time(value):
    delta = timestamp(value) - _EPOCH
    return _uint(delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000, 64)


def _iso(milliseconds):
    try:
        return utc_iso(_EPOCH + timedelta(milliseconds=milliseconds))
    except (OverflowError, ValueError) as exc:
        raise ValueError("timestamp outside supported datetime range") from exc


def _string(value):
    try:
        data = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("identifier is not valid UTF-8") from exc
    if not 1 <= len(data) <= 255:
        raise ValueError("identifier must contain 1..255 UTF-8 bytes")
    return bytes([len(data)]) + data


def _checksum(payload):
    return payload + struct.pack(">I", zlib.crc32(payload))


def _checked(packet):
    if not isinstance(packet, bytes) or not 4 <= len(packet) <= MAX_PACKET_BYTES:
        raise ValueError("invalid packet type or length")
    payload, crc = packet[:-4], packet[-4:]
    if struct.unpack(">I", crc)[0] != zlib.crc32(payload):
        raise ValueError("CRC mismatch")
    return payload


def encode_frame(frame: dict) -> bytes:
    frame = validate_frame(frame)
    link = frame["link"]
    payload = HEADER.pack(b"CR", 1, _uint(frame["sequence"], 32), _time(frame["capturedAt"]),
                          *_position(frame["roverPosition"]), _radius(frame["positionUncertaintyRadiusM"]),
                          LINK_STATUSES.index(link["status"]), _uint(link["packetsSent"], 32),
                          _uint(link["packetsLost"], 32), _uint(len(frame["hazards"]), 16))
    payload += _string(frame["roverId"])
    chunks = [payload]
    length = len(payload) + 4
    for hazard in frame["hazards"]:
        chunk = _string(hazard["id"]) + HAZARD.pack(
            HAZARD_TYPES.index(hazard["type"]), *_position(hazard["position"]),
            _radius(hazard["uncertaintyRadiusM"]), round(hazard["confidence"] * 65535),
            _time(hazard["observedAt"]))
        length += len(chunk)
        if length > MAX_PACKET_BYTES:
            raise ValueError("packet exceeds size limit")
        chunks.append(chunk)
    return _checksum(b"".join(chunks))


class _Reader:
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0

    def take(self, size):
        end = self.offset + size
        if end > len(self.payload):
            raise ValueError("truncated packet")
        result = self.payload[self.offset:end]
        self.offset = end
        return result

    def unpack(self, layout):
        return layout.unpack(self.take(layout.size))

    def string(self):
        size = self.take(1)[0]
        if not size:
            raise ValueError("empty identifier")
        try:
            return self.take(size).decode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid UTF-8 identifier") from exc


def decode_frame(packet: bytes) -> dict:
    reader = _Reader(_checked(packet))
    magic, version, sequence, capture, x, y, z, radius, status, sent, lost, count = reader.unpack(HEADER)
    if magic != b"CR" or version != 1 or status >= len(LINK_STATUSES):
        raise ValueError("invalid telemetry header")
    result = dict(schemaVersion=1, roverId=reader.string(), sequence=sequence,
                  capturedAt=_iso(capture), roverPosition=coordinates(x/1000, y/1000, z/1000),
                  positionUncertaintyRadiusM=radius/1000,
                  link=dict(status=LINK_STATUSES[status], packetsSent=sent, packetsLost=lost), hazards=[])
    for _ in range(count):
        identifier = reader.string()
        kind, x, y, z, radius, confidence, observed = reader.unpack(HAZARD)
        if kind >= len(HAZARD_TYPES):
            raise ValueError("unknown hazard enum")
        result["hazards"].append(dict(id=identifier, type=HAZARD_TYPES[kind],
                                      position=coordinates(x/1000, y/1000, z/1000),
                                      confidence=confidence/65535, uncertaintyRadiusM=radius/1000,
                                      observedAt=_iso(observed)))
    if reader.offset != len(reader.payload):
        raise ValueError("trailing bytes")
    return validate_frame(result)


def encode_ack(sequence: int) -> bytes:
    return _checksum(ACK.pack(b"CA", 1, _uint(sequence, 32)))


def decode_ack(packet: bytes) -> int:
    payload = _checked(packet)
    if len(payload) != ACK.size:
        raise ValueError("invalid ACK size")
    magic, version, sequence = ACK.unpack(payload)
    if magic != b"CA" or version != 1:
        raise ValueError("invalid ACK header")
    return sequence
