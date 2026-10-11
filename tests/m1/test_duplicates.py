from crater_m1.schema import Detection
from crater_m1.tracking import Tracker, suppress_duplicates


def test_nested_alternate_boxes_keep_best_score_and_one_id():
    best = Detection((20,20,40,40), .9)
    larger = Detection((15,15,45,45), .7)
    assert suppress_duplicates([larger,best]) == [best]
    assert len(Tracker().update([larger,best])) == 1


def test_large_ground_box_does_not_swallow_small_rock():
    boxes = [Detection((0,0,100,100), .9), Detection((40,40,60,60), .8)]
    assert len(suppress_duplicates(boxes)) == 2


def test_adjacent_rocks_and_different_classes_remain_separate():
    boxes = [Detection((10,10,30,30), .9), Detection((25,10,45,30), .8),
             Detection((10,10,30,30), .7, 'crater')]
    assert len(suppress_duplicates(boxes)) == 3
