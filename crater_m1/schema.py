"""Validated M1 observations, distinct from M2/M3 spatial telemetry."""
from dataclasses import dataclass
from datetime import datetime
import math

HAZARDS = ("rock", "crater", "slope", "unknown")

@dataclass(frozen=True)
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    type: str = "rock"

    def __post_init__(self):
        if len(self.bbox) != 4 or not all(math.isfinite(v) for v in self.bbox):
            raise ValueError("bbox requires four finite pixel coordinates")
        x1, y1, x2, y2 = self.bbox
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must have positive area and nonnegative origin")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0,1]")
        if self.type not in HAZARDS:
            raise ValueError("unsupported hazard type")

    @property
    def contact_pixel(self):
        # Approximate ground contact; not a depth measurement.
        return [(self.bbox[0] + self.bbox[2]) / 2, self.bbox[3]]


def observation(track_id, detection, observed_at, width, height):
    if not isinstance(track_id, str) or not track_id:
        raise ValueError("nonempty track ID required")
    parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observation timestamp must have timezone")
    if detection.bbox[2] >= width or detection.bbox[3] >= height:
        raise ValueError("bbox/contact must be inside the processed image")
    return {"id": track_id, "type": detection.type, "bbox_px": list(detection.bbox),
            "contact_pixel_px": detection.contact_pixel, "confidence": detection.confidence,
            "observedAt": observed_at}
