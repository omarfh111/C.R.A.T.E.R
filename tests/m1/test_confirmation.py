import json
import pytest
from crater_m1.schema import Detection
from crater_m1.tracking import Tracker
from crater_m1.pipeline import run
from crater_m1.simulation import generate

BOX=Detection((10,10,30,30),.8)


def test_tentative_obstacle_is_immediate_but_confirmation_requires_streak():
    tracker=Tracker(min_hits=2)
    first=tracker.update([BOX])[0]
    assert not first.confirmed
    assert tracker.update([])==[]
    again=tracker.update([BOX])[0]
    assert again.id==first.id and again.hits==2 and not again.confirmed
    assert tracker.update([BOX])[0].confirmed
    assert tracker.update([])==[]
    assert tracker.update([BOX])[0].confirmed


def test_confirmed_only_filters_flash_and_expired_id():
    tracker=Tracker(min_hits=2,max_missed=1,confirmed_only=True)
    assert tracker.update([BOX])==[]
    confirmed=tracker.update([BOX])[0].id
    assert tracker.update([])==tracker.update([])==[]
    assert tracker.update([BOX])==[]
    assert tracker.update([BOX])[0].id!=confirmed


def test_single_hit_mode_and_invalid_settings():
    assert Tracker(min_hits=1).update([BOX])[0].confirmed
    with pytest.raises(ValueError): Tracker(min_hits=0)


def test_pipeline_exports_only_fresh_confirmed_observations(tmp_path):
    generate(tmp_path/'scene',count=4)
    class Detector:
        def __init__(self): self.sequence=iter([[BOX],[BOX],[],[BOX]])
        def detect(self,image): return next(self.sequence)
        def resources(self): return {'device':'cpu'}
        def synchronize(self): pass
    report=run(tmp_path/'scene/scene.mp4',tmp_path/'run',Detector(),preview=False,
               tracker=Tracker(confirmed_only=True))
    rows=[json.loads(s) for s in (tmp_path/'run/observations.jsonl').read_text().splitlines()]
    assert [len(r['detections']) for r in rows]==[0,1,0,1]
    first,last=rows[1]['detections'][0],rows[3]['detections'][0]
    assert first['id']==last['id'] and first['tracking']['status']=='confirmed'
    assert last['tracking']['consecutiveHits']==1
    assert last['observedAt']==rows[3]['capturedAt']
    assert report['tracking_settings']['confirmed_only']
