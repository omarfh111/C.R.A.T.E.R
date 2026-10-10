import pytest
from crater_m1.video import crop_rect

def test_stereo_crop_has_correct_pixel_origin():
    assert crop_rect(2560,960,"left")== (0,0,1280,960)
    assert crop_rect(2560,960,"right")== (1280,0,1280,960)
    with pytest.raises(ValueError): crop_rect(100,100,crop=(0,0,101,10))
