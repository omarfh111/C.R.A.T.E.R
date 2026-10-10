"""Transparent geometry heuristic, not a traversability or safety classifier."""
import math


def reject_terrain_box(box,width,height,max_area=.5,policy="edges"):
    if policy not in {"edges","area","off"} or not math.isfinite(max_area) or not 0<max_area<=1:
        raise ValueError("invalid terrain filter")
    x1,y1,x2,y2=box
    area=(x2-x1)*(y2-y1)/(width*height)
    if policy=="off" or area<=max_area: return False
    if policy=="area": return True
    # Observed ground boxes cover both image edges; a localized close rock can
    # be large while remaining inside the image. Full-width rocks stay ambiguous.
    return x1<=width*.04 and x2>=width*.96
