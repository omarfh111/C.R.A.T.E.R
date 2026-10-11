import pytest
from crater_m1.terrain import reject_terrain_box
from crater_m1.onnx_detector import convert_boxes


def test_large_close_rock_is_preserved_while_full_width_ground_is_filtered():
    localized=(10,10,90,95)
    assert not reject_terrain_box(localized,100,100)
    assert reject_terrain_box((0,15,99,99),100,100)
    detections,rejected=convert_boxes([localized,(0,15,99,99)],[.8,.6],100,100,.25)
    assert len(detections)==1 and detections[0].bbox==localized and rejected==1


def test_ambiguous_full_width_rock_can_use_explicit_filter_override():
    box=(0,10,99,99)
    assert reject_terrain_box(box,100,100)
    assert not reject_terrain_box(box,100,100,policy="off")
    assert not reject_terrain_box(box,100,100,max_area=1)
    assert reject_terrain_box((10,10,90,95),100,100,policy="area")
    with pytest.raises(ValueError): reject_terrain_box(box,100,100,policy="magic")
