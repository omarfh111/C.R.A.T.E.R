"""Optional overlapping crops with original-pixel mapping and seam rejection."""
import math
from .schema import Detection
from .tracking import suppress_duplicates


def tile_rects(width,height):
    if width<8 or height<8: raise ValueError("image too small for tiling")
    tw,th=math.ceil(width*.6),math.ceil(height*.6)
    return [(x,y,tw,th) for y in (0,height-th) for x in (0,width-tw)]


def seam_truncated(box,rect,width,height,margin=2):
    x,y,w,h=rect;x1,y1,x2,y2=box
    return ((x>0 and x1<=margin) or (y>0 and y1<=margin) or
        (x+w<width and x2>=w-1-margin) or (y+h<height and y2>=h-1-margin))


class TiledDetector:
    def __init__(self,detector):
        self.detector=detector;self.calls=0;self.frames=0;self.rejected_seam_boxes=0

    def detect(self,image):
        h,w=image.shape[:2];rects=tile_rects(w,h)
        found=list(self.detector.detect(image));self.calls+=1
        for rect in rects:
            x,y,tw,th=rect
            current=self.detector.detect(image[y:y+th,x:x+tw].copy());self.calls+=1
            for d in current:
                if seam_truncated(d.bbox,rect,w,h): self.rejected_seam_boxes+=1;continue
                x1,y1,x2,y2=d.bbox
                mapped=(x+x1,y+y1,min(x+x2,w-1.),min(y+y2,h-1.))
                found.append(Detection(mapped,d.confidence,d.type))
        self.frames+=1
        return suppress_duplicates(found)

    def synchronize(self): self.detector.synchronize()

    def resources(self):
        return {**self.detector.resources(),"tiling":{"mode":"2x2-overlap-plus-full","inference_calls_per_frame":5,
            "completed_frames":self.frames,"inference_calls":self.calls,"rejected_seam_boxes":self.rejected_seam_boxes,
            "note":"Internal crop-edge boxes excluded; overlapping views merged by NMS."}}
