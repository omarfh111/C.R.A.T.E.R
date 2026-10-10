import numpy as np
from crater_m1.schema import Detection
from crater_m1.tracking import Tracker


def box(x): return Detection((x,20,x+20,40),.9)


def test_motion_prediction_bridges_short_gap_without_stale_export():
    tracker=Tracker(motion_compensation=False,max_missed=2)
    identity=tracker.update([box(10)])[0].id
    assert tracker.update([box(22)])[0].id==identity
    assert tracker.update([])==[]
    track=tracker.update([box(46)])[0]
    assert track.id==identity and track.detection.bbox==box(46).bbox


def image(x,texture):
    pixels=np.zeros((80,160,3),dtype=np.uint8)
    pixels[20:40,x:x+20]=texture
    return pixels


def test_appearance_recovers_nearby_low_iou_box():
    texture=np.random.default_rng(21).integers(0,256,(20,20,3),dtype=np.uint8)
    tracker=Tracker(motion_compensation=False)
    identity=tracker.update([box(10)],image(10,texture))[0].id
    assert tracker.update([box(25)],image(25,texture))[0].id==identity


def test_distant_lookalike_and_different_texture_do_not_reuse_id():
    texture=np.random.default_rng(21).integers(0,256,(20,20,3),dtype=np.uint8)
    for x,new in [(100,texture),(25,255-texture)]:
        tracker=Tracker(motion_compensation=False)
        identity=tracker.update([box(10)],image(10,texture))[0].id
        assert tracker.update([box(x)],image(x,new))[0].id!=identity


def test_flat_patches_are_not_identity_evidence():
    texture=np.full((20,20,3),100,dtype=np.uint8)
    tracker=Tracker(motion_compensation=False)
    identity=tracker.update([box(10)],image(10,texture))[0].id
    assert tracker.update([box(25)],image(25,texture))[0].id!=identity


def test_expired_moving_track_does_not_reappear_with_old_id():
    tracker=Tracker(max_missed=1,motion_compensation=False)
    identity=tracker.update([box(10)])[0].id
    tracker.update([box(22)])
    assert tracker.update([])==tracker.update([])==[]
    assert tracker.update([box(58)])[0].id!=identity


def test_prediction_at_left_edge_expires_without_invalid_boxes():
    tracker=Tracker(max_missed=3,motion_compensation=False)
    tracker.update([box(20)])
    tracker.update([box(10)])
    for _ in range(4):
        assert tracker.update([])==[]
    assert not tracker.tracks
