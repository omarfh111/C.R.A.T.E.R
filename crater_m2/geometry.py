"""Pinhole ray/ground-plane intersection in the agreed ENU frame.

Input pixels must already be rectified; this module doesn't infer calibration.
"""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class Camera:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    center_enu_m: tuple
    rotation_camera_to_enu: np.ndarray

    def __post_init__(self):
        if type(self.width) is not int or type(self.height) is not int or min(self.width, self.height) <= 0:
            raise ValueError("resolution must contain positive integers")
        if not all(math.isfinite(v) for v in (self.fx, self.fy, self.cx, self.cy)) or min(self.fx, self.fy) <= 0:
            raise ValueError("invalid camera intrinsics")
        center = np.array(self.center_enu_m, dtype=float, copy=True)
        rotation = np.array(self.rotation_camera_to_enu, dtype=float, copy=True)
        if center.shape != (3,) or not np.isfinite(center).all():
            raise ValueError("invalid camera center")
        if (rotation.shape != (3, 3) or not np.isfinite(rotation).all()
                or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-7, rtol=0)
                or not np.isclose(np.linalg.det(rotation), 1, atol=1e-7, rtol=0)):
            raise ValueError("rotation must be right-handed and orthonormal")
        rotation.setflags(write=False)
        object.__setattr__(self, "center_enu_m", tuple(center))
        object.__setattr__(self, "rotation_camera_to_enu", rotation)


@dataclass(frozen=True)
class GroundEstimate:
    position_m: tuple[float, float, float]
    uncertainty_radius_m: float


def project_point(camera: Camera, point_enu_m) -> tuple[float, float]:
    point = np.asarray(point_enu_m, dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError("invalid ENU point")
    local = camera.rotation_camera_to_enu.T @ (point - camera.center_enu_m)
    if local[2] <= 1e-9:
        raise ValueError("point is behind the camera")
    pixel = (camera.fx * local[0] / local[2] + camera.cx,
             camera.fy * local[1] / local[2] + camera.cy)
    _pixel(camera, pixel)
    return tuple(float(v) for v in pixel)


def _pixel(camera, pixel):
    if len(pixel) != 2 or not all(math.isfinite(v) for v in pixel):
        raise ValueError("invalid pixel")
    if not (0 <= pixel[0] < camera.width and 0 <= pixel[1] < camera.height):
        raise ValueError("pixel outside image")


def _intersect(camera, pixel, ground_z_m, max_range_m):
    ray = camera.rotation_camera_to_enu @ np.array([
        (pixel[0] - camera.cx) / camera.fx, (pixel[1] - camera.cy) / camera.fy, 1.])
    if abs(ray[2]) < 1e-9:
        raise ValueError("ray parallel to ground")
    distance = (ground_z_m - camera.center_enu_m[2]) / ray[2]
    if distance <= 0:
        raise ValueError("ground is behind camera")
    displacement = distance * ray
    if np.linalg.norm(displacement) > max_range_m:
        raise ValueError("ground intersection exceeds range")
    point = np.asarray(camera.center_enu_m) + displacement
    point[2] = ground_z_m
    return point


def locate_ground(camera: Camera, pixel, *, ground_z_m=0., pixel_error_px=2.,
                  pose_error_m=.1, max_range_m=1000.) -> GroundEstimate:
    _pixel(camera, pixel)
    values = (ground_z_m, pixel_error_px, pose_error_m, max_range_m)
    if not all(math.isfinite(v) for v in values) or min(pixel_error_px, pose_error_m) < 0 or max_range_m <= 0:
        raise ValueError("invalid geometry or uncertainty settings")
    point = _intersect(camera, pixel, ground_z_m, max_range_m)
    # Conservative sampled pixel-box perturbation, plus configured pose budget.
    # This is not a certified bound for unknown terrain/orientation errors.
    radius = 0.
    for dx in (-pixel_error_px, pixel_error_px):
        for dy in (-pixel_error_px, pixel_error_px):
            perturbed = _intersect(camera, (pixel[0] + dx, pixel[1] + dy), ground_z_m, max_range_m)
            radius = max(radius, float(np.linalg.norm(perturbed - point)))
    return GroundEstimate(tuple(float(v) for v in point), radius + pose_error_m)
