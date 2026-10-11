import cv2
import numpy as np
import pytest
from crater_m1.schema import Detection
from crater_m1.tiling import TiledDetector,tile_rects,seam_truncated


class PixelDetector:
    def detect(self,image):
        mask=cv2.inRange(image[:,:,0],200,255)
        n,_,stats,_=cv2.connectedComponentsWithStats(mask)
        return [Detection((float(x),float(y),float(x+w-1),float(y+h-1)),.9) for x,y,w,h,area in stats[1:] if w>2 and h>2]
    def resources(self): return {"device":"cpu"}
    def synchronize(self): pass


def test_overlap_maps_real_pixels_and_removes_duplicate_crop_observations():
    image=np.zeros((100,100,3),dtype=np.uint8);image[55:70,55:70]=255
    d=TiledDetector(PixelDetector());boxes=d.detect(image)
    assert len(boxes)==1 and boxes[0].bbox==(55,55,69,69)
    assert d.resources()["tiling"]["inference_calls"]==5
    assert d.rejected_seam_boxes>0


def test_seam_filter_preserves_original_image_boundaries():
    assert seam_truncated((0,20,10,30),(40,0,60,60),100,100)
    assert not seam_truncated((0,20,10,30),(0,0,60,60),100,100)
    rects=tile_rects(101,81)
    assert len(rects)==4 and all(x+w<=101 and y+h<=81 for x,y,w,h in rects)


def test_partial_crop_failure_does_not_emit_incomplete_frame():
    class Broken(PixelDetector):
        def detect(self,image):
            if image.shape[0]<100: raise RuntimeError("crop failed")
            return super().detect(image)
    detector=TiledDetector(Broken())
    with pytest.raises(RuntimeError,match="crop failed"): detector.detect(np.zeros((100,100,3),dtype=np.uint8))
    assert detector.frames==0
