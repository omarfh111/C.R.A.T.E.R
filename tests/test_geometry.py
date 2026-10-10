import numpy as np
import pytest

from crater_m2.geometry import Camera, locate_ground, project_point


def downward_camera():
    return Camera(640, 480, 400, 400, 320, 240,
                  (2, 3, 2), np.diag([1., -1., -1.]))


@pytest.mark.parametrize("point", [(2, 3, 0), (2.5, 3.4, 0), (1, 2.5, 0)])
def test_known_enu_points_reconstructed(point):
    camera = downward_camera()
    pixel = project_point(camera, point)
    result = locate_ground(camera, pixel, pixel_error_px=1, pose_error_m=0.2)
    assert result.position_m == pytest.approx(point, abs=1e-10)
    assert result.uncertainty_radius_m >= 0.2


def test_nonzero_ground_and_translated_pose():
    camera = downward_camera()
    point = (2.1, 3.2, 0.5)
    assert locate_ground(camera, project_point(camera, point), ground_z_m=.5).position_m == pytest.approx(point)


def test_horizon_and_backwards_rays_are_rejected():
    camera = Camera(640, 480, 400, 400, 320, 240, (0, 0, 2), np.eye(3))
    with pytest.raises(ValueError):
        locate_ground(camera, (320, 240))
    horizontal = Camera(640, 480, 400, 400, 320, 240, (0, 0, 2),
                        np.array([[1., 0, 0], [0, 0, 1], [0, -1, 0]]))
    with pytest.raises(ValueError):
        locate_ground(horizontal, (320, 240))


@pytest.mark.parametrize("pixel", [(-1, 240), (640, 240), (320, 480), (float("nan"), 0)])
def test_bad_pixels_rejected(pixel):
    with pytest.raises(ValueError):
        locate_ground(downward_camera(), pixel)


def test_range_and_invalid_calibration():
    with pytest.raises(ValueError):
        locate_ground(downward_camera(), (320, 240), max_range_m=1)
    with pytest.raises(ValueError):
        Camera(640, 480, 0, 400, 320, 240, (0, 0, 2), np.eye(3))
    with pytest.raises(ValueError):
        Camera(640, 480, 400, 400, 320, 240, (0, 0, 2), np.ones((3, 3)))


def test_uncertainty_grows_with_pixel_error():
    camera = downward_camera()
    a = locate_ground(camera, (320, 240), pixel_error_px=1)
    b = locate_ground(camera, (320, 240), pixel_error_px=4)
    assert b.uncertainty_radius_m > a.uncertainty_radius_m
