"""Bounded motion prediction, global camera compensation and gated association."""
from dataclasses import dataclass, field
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


def nested_duplicate(a, b):
    """Merge similar concentric boxes, without swallowing small nearby rocks."""
    areas = [(r[2]-r[0])*(r[3]-r[1]) for r in (a, b)]
    intersection = max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))
    centers = [np.array([(r[0]+r[2])/2, (r[1]+r[3])/2]) for r in (a, b)]
    diagonal = max(np.hypot(r[2]-r[0], r[3]-r[1]) for r in (a, b))
    return (max(areas)/min(areas) <= 2.5 and intersection/min(areas) >= .85
            and np.linalg.norm(centers[0]-centers[1]) <= .15*diagonal)


def suppress_duplicates(detections, threshold=.5):
    kept = []
    for d in sorted(detections, key=lambda item: item.confidence, reverse=True):
        if not any(d.type == k.type and (iou(d.bbox, k.bbox) > threshold or nested_duplicate(d.bbox, k.bbox)) for k in kept):
            kept.append(d)
    return kept


@dataclass
class Track:
    id: str
    detection: Detection
    missed: int = 0
    hits: int = 1
    consecutive_hits: int = 1
    confirmed: bool = False
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    appearance: np.ndarray | None = None


class Tracker:
    def __init__(self, min_iou=.15, max_missed=3, motion_compensation=True, min_hits=2, confirmed_only=False, predict_motion=True, appearance_matching=True):
        if not 0 < min_iou <= 1 or max_missed < 0 or min_hits < 1 or int(min_hits) != min_hits:
            raise ValueError("invalid tracker settings")
        self.min_iou, self.max_missed = min_iou, max_missed
        self.min_hits, self.confirmed_only = min_hits, confirmed_only
        self.predict_motion, self.appearance_matching = predict_motion, appearance_matching
        self.motion_compensation = motion_compensation
        self.tracks = []
        self.next_id = 1
        self.previous_gray = None
        self.last_motion_inliers = 0

    def resources(self):
        return {"min_consecutive_hits": self.min_hits, "max_missed_frames": self.max_missed,
                "confirmed_only": self.confirmed_only, "motion_compensation": self.motion_compensation,
                "predict_motion": self.predict_motion, "appearance_matching": self.appearance_matching,
                "gap_units": "processed frames, not seconds or original capture cadence"}

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

    @staticmethod
    def _center(box):
        return np.array([(box[0]+box[2])/2, (box[1]+box[3])/2])

    def _appearance(self, detection, image):
        if not self.appearance_matching or image is None:
            return None
        h,w=image.shape[:2]
        x1,y1,x2,y2=detection.bbox
        patch=image[max(0,int(y1)):min(h,int(np.ceil(y2))),max(0,int(x1)):min(w,int(np.ceil(x2)))]
        if not patch.size:
            return None
        gray=cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY)
        vector=cv2.resize(gray,(16,16),interpolation=cv2.INTER_AREA).astype(float).ravel()
        vector-=vector.mean()
        if np.std(vector)<5:
            return None  # Uniform patches provide no identity evidence.
        return vector/np.linalg.norm(vector)

    def _appearance_score(self, track, detection, descriptor):
        if track.appearance is None or descriptor is None:
            return 0.
        a,b=track.detection.bbox,detection.bbox
        ratio=((b[2]-b[0])*(b[3]-b[1]))/((a[2]-a[0])*(a[3]-a[1]))
        diagonal=max(np.hypot(r[2]-r[0],r[3]-r[1]) for r in (a,b))
        if not .5<=ratio<=2 or np.linalg.norm(self._center(a)-self._center(b))>.75*diagonal:
            return 0.
        similarity=float(np.dot(track.appearance,descriptor))
        return self.min_iou if similarity>=.95 else 0.

    def update(self, detections, image=None):
        detections = suppress_duplicates(detections)
        descriptors=[self._appearance(d,image) for d in detections]
        motion = self._motion(image)
        if motion is not None:
            for track in self.tracks:
                x1,y1,x2,y2 = track.detection.bbox
                corners=np.array([[x1,y1,1],[x2,y1,1],[x1,y2,1],[x2,y2,1]]) @ motion.T
                lo,hi=np.maximum(corners.min(axis=0),0),corners.max(axis=0)
                if hi[0]>lo[0] and hi[1]>lo[1]:
                    track.detection=Detection((*lo,*hi),track.detection.confidence,track.detection.type)
                    track.velocity=motion[:,:2] @ track.velocity
        if self.predict_motion:
            for track in self.tracks:
                x1,y1,x2,y2=track.detection.bbox
                vx,vy=track.velocity
                # Prediction is internal only; keep its origin valid at image edges.
                vx,vy=max(vx,-x1),max(vy,-y1)
                track.detection=Detection((x1+vx,y1+vy,x2+vx,y2+vy),track.detection.confidence,track.detection.type)
        scores=np.zeros((len(self.tracks),len(detections)))
        for i,t in enumerate(self.tracks):
            for j,d in enumerate(detections):
                if t.detection.type==d.type:
                    scores[i,j]=max(iou(t.detection.bbox,d.bbox),self._appearance_score(t,d,descriptors[j]))
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
                detected=detections[matched[i]]
                if self.predict_motion:
                    innovation=(self._center(detected.bbox)-self._center(t.detection.bbox))/(t.missed+1)
                    velocity=t.velocity+.6*innovation
                    limit=.75*np.hypot(detected.bbox[2]-detected.bbox[0],detected.bbox[3]-detected.bbox[1])
                    norm=np.linalg.norm(velocity)
                    t.velocity=velocity*min(1.,limit/norm) if norm else velocity
                t.appearance=descriptors[matched[i]]
                t.detection=detected; t.missed=0; t.hits+=1
                t.consecutive_hits+=1
                t.confirmed=t.confirmed or t.consecutive_hits>=self.min_hits
                observed.append(t)
            else: t.missed+=1; t.consecutive_hits=0
        self.tracks=[t for t in self.tracks if t.missed<=self.max_missed]
        for j,d in enumerate(detections):
            if j not in matched.values():
                t=Track(f"hazard-{self.next_id:06d}",d,confirmed=self.min_hits==1,appearance=descriptors[j]); self.next_id+=1
                self.tracks.append(t); observed.append(t)
        return [t for t in observed if t.confirmed or not self.confirmed_only]
