"""Video decoding and explicit pixel transforms."""
from pathlib import Path
import cv2
import hashlib


def inspect_video(path):
    cap=cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened(): raise ValueError(f"cannot open video: {path}")
        fps=cap.get(cv2.CAP_PROP_FPS)
        if fps<=0: raise ValueError("video has no valid playback FPS")
        return {"file":Path(path).name,"fps":fps,"frames":int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
                "sha256":_sha256(path),"width":int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),"height":int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    finally: cap.release()


def crop_rect(width,height,view="full",crop=None):
    if crop is not None: rect=tuple(crop)
    elif view=="left": rect=(0,0,width//2,height)
    elif view=="right": rect=(width//2,0,width-width//2,height)
    else: rect=(0,0,width,height)
    x,y,w,h=rect
    if min(x,y)<0 or min(w,h)<=0 or x+w>width or y+h>height:
        raise ValueError("crop is outside source frame")
    return rect


def frames(path,*,view="full",crop=None,stride=1,max_frames=None):
    if stride<1 or max_frames is not None and max_frames<1: raise ValueError("invalid frame limit/stride")
    info=inspect_video(path); rect=crop_rect(info["width"],info["height"],view,crop)
    cap=cv2.VideoCapture(str(path)); index=0; count=0
    try:
        while True:
            ok,frame=cap.read()
            if not ok: break
            if index%stride==0:
                x,y,w,h=rect
                yield index,index/info["fps"],frame[y:y+h,x:x+w].copy(),rect
                count+=1
                if max_frames is not None and count>=max_frames: break
            index+=1
    finally: cap.release()


def _sha256(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()
