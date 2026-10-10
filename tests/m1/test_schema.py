import pytest
from crater_m1.schema import Detection, observation

def test_contact_and_serializable_observation():
    d = Detection((10., 20., 30., 40.), .8)
    obj = observation("rock-1", d, "2026-10-10T18:00:00Z", 100, 80)
    assert obj["contactPixel"] == [20., 40.]
    assert obj["id"] == "rock-1"

@pytest.mark.parametrize("bbox,score", [((0,0,0,3),.5), ((-1,0,2,3),.5), ((0,0,2,3),float("nan")), ((0,0,2,3),1.1)])
def test_invalid_detection_rejected(bbox,score):
    with pytest.raises(ValueError): Detection(bbox,score)

def test_invalid_timestamp_and_out_of_frame_rejected():
    d = Detection((1,2,10,20),.5)
    with pytest.raises(ValueError): observation("1",d,"2026-10-10T00:00:00",40,40)
    with pytest.raises(ValueError): observation("1",d,"2026-10-10T00:00:00Z",10,40)
