"""Calibrated synthetic pixel source and JSONL adapter for M1 observations."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import random

import numpy as np

from .contract import coordinates, utc_iso, validate_frame
from .geometry import Camera, locate_ground, project_point
from .metrics import RunningStats


@dataclass
class SourceResult:
    frame: dict
    rejected: list[dict]


def observation_to_frame(observation: dict, sequence: int, link: dict) -> SourceResult:
    try:
        spec = observation["camera"]
        camera = Camera(spec["width"], spec["height"], spec["fx"], spec["fy"], spec["cx"], spec["cy"],
                        spec["centerEnuM"], spec["rotationCameraToEnu"])
        frame = dict(schemaVersion=1, roverId=observation["roverId"], sequence=sequence,
                     capturedAt=observation["capturedAt"], roverPosition=observation["roverPosition"],
                     positionUncertaintyRadiusM=observation["positionUncertaintyRadiusM"], link=link, hazards=[])
        frame = validate_frame(frame)
        detections = observation["detections"]
        if not isinstance(detections, list):
            raise ValueError("detections must be a list")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid observation/camera calibration: {exc}") from exc
    rejected = []
    for detection in detections:
        identifier = detection.get("id", "<missing>") if isinstance(detection, dict) else "<invalid>"
        try:
            if "contactPixel" in detection:
                pixel = detection["contactPixel"]
            else:
                box = detection["bboxPx"]
                if len(box) != 4 or not all(math.isfinite(v) for v in box):
                    raise ValueError("bboxPx must contain four finite numbers")
                x1, y1, x2, y2 = box
                if not (0 <= x1 < x2 <= camera.width and 0 <= y1 < y2 < camera.height):
                    raise ValueError("bbox outside image or without visible ground contact")
                pixel = ((x1 + x2) / 2, y2)
            estimate = locate_ground(camera, pixel, ground_z_m=observation.get("groundZM", 0),
                                     pixel_error_px=detection.get("pixelErrorPx", 2),
                                     pose_error_m=frame["positionUncertaintyRadiusM"],
                                     max_range_m=observation.get("maxRangeM", 1000))
            hazard = dict(id=detection["id"], type=detection["type"], position=coordinates(*estimate.position_m),
                          confidence=detection["confidence"], uncertaintyRadiusM=estimate.uncertainty_radius_m,
                          observedAt=detection.get("observedAt", frame["capturedAt"]))
            candidate = dict(frame, hazards=[hazard])
            validate_frame(candidate)
            frame["hazards"].append(hazard)
        except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
            rejected.append(dict(id=identifier, reason=str(exc)))
    return SourceResult(validate_frame(frame), rejected)


def read_observations(path):
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                result = json.loads(line)
                if not isinstance(result, dict):
                    raise ValueError("expected an object")
                yield result
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path}: line {line_number}: {exc}") from exc


class Scenario:
    """Synthetic detections, not an AI model or calibrated NASA footage.

Known points -> camera pixels (+ noise) -> M2 localization. Ground truth is
used to assess errors only, never substituted for the reconstructed output.
"""

    def __init__(self, start_time: datetime, *, pixel_noise_px=.4, seed=7):
        utc_iso(start_time)
        if not math.isfinite(pixel_noise_px) or pixel_noise_px < 0:
            raise ValueError("nonnegative pixel noise required")
        self.start_time = start_time
        self.pixel_noise_px = pixel_noise_px
        self.random = random.Random(seed)
        self.points = {"rock-1": ("rock", (1., 4., 0.)),
                       "rock-2": ("rock", (-1.2, 6., 0.)),
                       "crater-edge-1": ("crater", (2., 9., 0.))}
        self._error_stats = RunningStats()
        self.rejected_count = 0

    def observation(self, elapsed_s):
        if not math.isfinite(elapsed_s) or elapsed_s < 0:
            raise ValueError("elapsed time must be nonnegative")
        # Bounded rover motion permits the same three markers to remain visible.
        rover = (.4 * math.sin(elapsed_s/4), .5 * (1-math.cos(elapsed_s/8)), 0.)
        theta = math.radians(25)
        rotation = np.array([[1., 0, 0], [0, -math.sin(theta), math.cos(theta)],
                             [0, -math.cos(theta), -math.sin(theta)]])
        camera = Camera(1280, 720, 800, 800, 640, 360, (rover[0], rover[1], 1.5), rotation)
        captured = utc_iso(self.start_time + timedelta(seconds=elapsed_s))
        detections = []
        for identifier, (kind, point) in self.points.items():
            try:
                u, v = project_point(camera, point)
            except ValueError:
                continue
            pixel = [u + self.random.uniform(-self.pixel_noise_px, self.pixel_noise_px),
                     v + self.random.uniform(-self.pixel_noise_px, self.pixel_noise_px)]
            detections.append(dict(id=identifier, type=kind, contactPixel=pixel,
                                   confidence=.9, pixelErrorPx=max(2., self.pixel_noise_px), observedAt=captured))
        return dict(roverId="rover-1", capturedAt=captured, roverPosition=coordinates(*rover),
                    positionUncertaintyRadiusM=.05, groundZM=0,
                    camera=dict(width=camera.width, height=camera.height, fx=camera.fx, fy=camera.fy,
                                cx=camera.cx, cy=camera.cy, centerEnuM=list(camera.center_enu_m),
                                rotationCameraToEnu=camera.rotation_camera_to_enu.tolist()), detections=detections)

    def capture(self, elapsed_s, sequence, link) -> SourceResult:
        result = observation_to_frame(self.observation(elapsed_s), sequence, link)
        self.rejected_count += len(result.rejected)
        for hazard in result.frame["hazards"]:
            point = np.array([hazard["position"][key] for key in ("xM", "yM", "zM")])
            self._error_stats.add(float(np.linalg.norm(point - self.points[hazard["id"]][1])))
        return result

    def report(self):
        return dict(source="synthetic-calibrated-pixels", evaluatedObservations=self._error_stats.count,
                    rejectedDetections=self.rejected_count,
                    meanLocalizationErrorM=self._error_stats.mean,
                    maxLocalizationErrorM=self._error_stats.maximum)
