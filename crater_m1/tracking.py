"""Global-motion-compensated IoU association, with bounded occlusion memory."""
from dataclasses import dataclass
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from .schema import Detection


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0., x2-x1) * max(0., y2-y1)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0.


def suppress_duplicates(detections, threshold=.5):
    kept = []
    for d in sorted(detections, key=lambda item: item.confidence, reverse=True):
        if not any(d.type == k.type and iou(d.bbox, k.bbox) > threshold for k in kept):
            kept.append(d)
    return kept


@dataclass
class Track:
    id: str
    detection: Detection
    missed: int = 0
    hits: int = 1


class Tracker:
    def __init__(self, min_iou=.15, max_missed=3, motion_compensation=True):
        if not 0 < min_iou <= 1 or max_missed < 0:
            raise ValueError("invalid tracker settings")
        self.min_iou, self.max_missed = min_iou, max_missed
        self.motion_compensation = motion_compensation
        self.tracks = []
        self.next_id = 1
        self.previous_gray = None
        self.last_motion_inliers = 0

    def _motion(self, image):
        self.last_motion_inliers = 0
        if image is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        old, self.previous_gray = self.previous_gray, gray
        if not self.motion_compensation or old is None or old.shape != gray.shape:
            return None
        orb = cv2.ORB_create(nfeatures=1500)
        kp1, d1 = orb.detectAndCompute(old, None)
        kp2, d2 = orb.detectAndCompute(gray, None)
        if d1 is None or d2 is None or len(d1) < 8 or len(d2) < 8:
            return None
        matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d2, k=2)
        good = [m[0] for m in matches if len(m) == 2 and m[0].distance < .7*m[1].distance]
        if len(good) < 8:
            return None
        src = np.float32([kp1[m.queryIdx].pt for m in good])
        dst = np.float32([kp2[m.trainIdx].pt for m in good])
        matrix, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
        if matrix is None or mask is None or mask.sum() < 8:
            return None
        scale = np.hypot(matrix[0,0], matrix[1,0])
        if not .7 < scale < 1.4 or np.linalg.norm(matrix[:,2]) > max(gray.shape)*.35:
            return None
        self.last_motion_inliers = int(mask.sum())
        return matrix

    def update(self, detections, image=None):
        detections = suppress_duplicates(detections)
        motion = self._motion(image)
        if motion is not None:
            for track in self.tracks:
                x1,y1,x2,y2 = track.detection.bbox
                corners=np.array([[x1,y1,1],[x2,y1,1],[x1,y2,1],[x2,y2,1]]) @ motion.T
                lo,hi=np.maximum(corners.min(axis=0),0),corners.max(axis=0)
                if hi[0]>lo[0] and hi[1]>lo[1]:
                    track.detection=Detection((*lo,*hi),track.detection.confidence,track.detection.type)
        scores=np.zeros((len(self.tracks),len(detections)))
        for i,t in enumerate(self.tracks):
            for j,d in enumerate(detections):
                if t.detection.type==d.type: scores[i,j]=iou(t.detection.bbox,d.bbox)
        # Dummy columns let every track remain unmatched; subthreshold matches
        # cannot steal a detection from a valid association.
        matched={}
        if self.tracks and detections:
            cost=np.ones((len(self.tracks),len(detections)+len(self.tracks)))
            cost[:,:len(detections)]=np.where(scores>=self.min_iou,1-scores,2)
            rows,cols=linear_sum_assignment(cost)
            matched={int(i):int(j) for i,j in zip(rows,cols) if j<len(detections) and scores[i,j]>=self.min_iou}
        observed=[]
        for i,t in enumerate(self.tracks):
            if i in matched:
                t.detection=detections[matched[i]]; t.missed=0; t.hits+=1; observed.append(t)
            else: t.missed+=1
        self.tracks=[t for t in self.tracks if t.missed<=self.max_missed]
        for j,d in enumerate(detections):
            if j not in matched.values():
                t=Track(f"hazard-{self.next_id:06d}",d); self.next_id+=1
                self.tracks.append(t); observed.append(t)
        return observed
