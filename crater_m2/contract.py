"""Canonical JSON v1, matching M3's strict Zod parser."""

from copy import deepcopy
from datetime import datetime, timezone
import math
import re

FRAME_ID = "LOCAL_ENU_V1"
HAZARD_TYPES = ("crater", "rock", "slope", "unknown")
LINK_STATUSES = ("connected", "degraded", "disconnected")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not _ISO.fullmatch(value):
        raise ValueError("timestamp must be ISO 8601 with timezone")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timezone required")
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"expected exactly fields: {', '.join(expected)}")


def _number(value, minimum=None, maximum=None, integer=False):
    if type(value) not in (int, float):
        raise ValueError("expected a number")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or (integer and int(value) != value):
        raise ValueError("expected a finite number (integer where required)")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError("number outside permitted range")


def _id(value):
    if not isinstance(value, str) or not value:
        raise ValueError("identifier must be a nonempty string")


def coordinates(x, y, z):
    result = dict(frameId=FRAME_ID, xM=float(x), yM=float(y), zM=float(z))
    _position(result)
    return result


def _position(value):
    _fields(value, ("frameId", "xM", "yM", "zM"))
    if value["frameId"] != FRAME_ID:
        raise ValueError("position must use LOCAL_ENU_V1")
    for key in ("xM", "yM", "zM"):
        _number(value[key])


def validate_frame(frame: dict) -> dict:
    _fields(frame, ("schemaVersion", "roverId", "sequence", "capturedAt", "roverPosition",
                    "positionUncertaintyRadiusM", "link", "hazards"))
    _number(frame["schemaVersion"], 1, 1, integer=True)
    _id(frame["roverId"])
    _number(frame["sequence"], 0, 2**53 - 1, integer=True)
    capture = timestamp(frame["capturedAt"])
    _position(frame["roverPosition"])
    _number(frame["positionUncertaintyRadiusM"], 0)
    link = frame["link"]
    _fields(link, ("status", "packetsSent", "packetsLost"))
    if link["status"] not in LINK_STATUSES:
        raise ValueError("invalid link status")
    _number(link["packetsSent"], 0, 2**53 - 1, integer=True)
    _number(link["packetsLost"], 0, link["packetsSent"], integer=True)
    if not isinstance(frame["hazards"], list):
        raise ValueError("hazards must be a list")
    for hazard in frame["hazards"]:
        _fields(hazard, ("id", "type", "position", "confidence", "uncertaintyRadiusM", "observedAt"))
        _id(hazard["id"])
        if hazard["type"] not in HAZARD_TYPES:
            raise ValueError("invalid hazard type")
        _position(hazard["position"])
        _number(hazard["confidence"], 0, 1)
        _number(hazard["uncertaintyRadiusM"], 0)
        if timestamp(hazard["observedAt"]) > capture:
            raise ValueError("observation cannot postdate capture")
    return deepcopy(frame)
