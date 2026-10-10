from crater_m1.schema import Detection
from crater_m1.tracking import Tracker, suppress_duplicates

def box(x,kind="rock",score=.8): return Detection((x,10,x+20,30),score,kind)

def test_stable_ids_and_occlusion_without_stale_observations():
    tracker=Tracker(max_missed=2)
    first=tracker.update([box(10),box(80)])
    ids=[t.id for t in first]
    assert [t.id for t in tracker.update([box(12),box(82)])]==ids
    assert tracker.update([])==[]
    assert [t.id for t in tracker.update([box(14),box(84)])]==ids

def test_expired_tracks_get_new_id_and_classes_do_not_mix():
    tracker=Tracker(max_missed=0)
    initial=tracker.update([box(10)])[0].id
    tracker.update([])
    assert tracker.update([box(10)])[0].id != initial
    assert tracker.update([box(10,"crater")])[0].id != initial

def test_duplicates_do_not_create_extra_tracks():
    tracker=Tracker()
    assert len(tracker.update([box(10,score=.9),box(11,score=.7)]))==1

def test_large_motion_is_not_silently_same_identity():
    tracker=Tracker()
    initial=tracker.update([box(10)])[0].id
    assert tracker.update([box(100)])[0].id != initial


def test_camera_translation_compensation_preserves_identity():
    import cv2
    import numpy as np
    random=np.random.default_rng(17)
    gray=random.integers(0,256,(400,600),dtype=np.uint8)
    first=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    shifted=cv2.warpAffine(first,np.float32([[1,0,70],[0,1,10]]),(600,400))
    tracker=Tracker(motion_compensation=True)
    initial=tracker.update([Detection((200,180,250,220),.9)],first)[0].id
    current=tracker.update([Detection((270,190,320,230),.9)],shifted)
    assert tracker.last_motion_inliers>=8
    assert current[0].id==initial
