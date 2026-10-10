"""Free community Space experiments; no local model weights or paid router calls."""
import math
from pathlib import Path
import re
import tempfile
import time
import cv2
from .schema import Detection
from .tracking import suppress_duplicates

SPACE_ID = "developer0hye/Grounding_DINO_Base_demo"
MODEL_ID = "IDEA-Research/grounding-dino-base"
DEFAULT_PROMPT = "rock. stone. boulder."


def parse_space_boxes(text, sent_width, sent_height, width, height, threshold, max_area=.5):
    """Parse this Space's pixel-box text, fail closed, and restore original pixels."""
    if not isinstance(text, str) or len(text)>65536:
        raise ValueError("invalid Space detection response")
    if text.strip()=="No detections.": return [], 0
    lines=text.strip().splitlines()
    if not lines or len(lines)>128: raise ValueError("invalid Space detection list")
    found=[]; rejected=0
    for line in lines:
        match=re.fullmatch(r"(.+) ([0-9.]+) (\d+), (\d+), (\d+), (\d+)", line.strip())
        if not match: raise ValueError("unexpected Space box format")
        words=match[1].lower().split()
        if not words or any(word not in {"a","rock","stone","boulder"} for word in words) or not any(word in {"rock","stone","boulder"} for word in words):
            raise ValueError("unexpected Space label")
        score=float(match[2]); x1,y1,x2,y2=(int(match[i]) for i in range(3,7))
        if not math.isfinite(score) or not 0<=score<=1 or not 0<=x1<x2<=sent_width or not 0<=y1<y2<=sent_height:
            raise ValueError("invalid Space coordinates or score")
        if score<threshold: continue
        if (x2-x1)*(y2-y1)/(sent_width*sent_height)>max_area:
            rejected+=1; continue
        box=(min(x1*width/sent_width,width-1.),min(y1*height/sent_height,height-1.),
             min(x2*width/sent_width,width-1.),min(y2*height/sent_height,height-1.))
        if box[2]-box[0]>=4 and box[3]-box[1]>=4: found.append(Detection(box,score,"rock"))
    return suppress_duplicates(found), rejected


class SpaceGrounding:
    def __init__(self,config,*,threshold=.25,text_threshold=.2,max_area=.5,client_factory=None):
        if not 0<threshold<1 or not 0<text_threshold<1 or not 0<max_area<=1:
            raise ValueError("invalid Space thresholds")
        self.config=config; self.threshold=threshold; self.text_threshold=text_threshold; self.max_area=max_area
        self.client_factory=client_factory; self.client=None
        self.calls=0; self.uploaded_bytes=0; self.latencies=[]; self.rejected_large_boxes=0

    def detect(self,image):
        if self.calls>=self.config.max_requests: raise RuntimeError("HF_MAX_REQUESTS reached; no further Space calls sent")
        h,w=image.shape[:2]; scale=min(1.,self.config.max_side/max(w,h))
        sent=cv2.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))),interpolation=cv2.INTER_AREA) if scale<1 else image
        ok,jpeg=cv2.imencode(".jpg",sent,[cv2.IMWRITE_JPEG_QUALITY,90])
        if not ok: raise ValueError("cannot encode Space input")
        started=time.perf_counter(); job=None
        try:
            from gradio_client import Client,handle_file
            if self.client is None:
                factory=self.client_factory or Client
                self.client=factory(SPACE_ID,hf_token=self.config.token,verbose=False,
                    download_files=False,analytics_enabled=False,max_workers=2,
                    httpx_kwargs={"timeout":self.config.timeout_s})
            with tempfile.TemporaryDirectory(prefix="crater-m1-") as folder:
                path=Path(folder)/"frame.jpg"; path.write_bytes(jpeg.tobytes())
                self.calls+=1; self.uploaded_bytes+=len(jpeg)
                job=self.client.submit(handle_file(str(path)),DEFAULT_PROMPT,self.threshold,self.text_threshold,api_name="/run_grounding")
                result=job.result(timeout=self.config.timeout_s)
            if not isinstance(result,(tuple,list)) or len(result)!=2: raise ValueError("invalid Space output")
            detections,rejected=parse_space_boxes(result[1],sent.shape[1],sent.shape[0],w,h,self.threshold,self.max_area)
            self.rejected_large_boxes+=rejected
            return detections
        except Exception as exc:
            if job is not None:
                try: job.cancel()
                except Exception: pass
            # Never echo library exceptions: they may contain credentials or request headers.
            message=str(exc).lower()
            if "quota" in message or "limit" in message:
                detail="Free Space quota/rate limit reached; wait for quota reset"
            elif "401" in message or "403" in message or "unauthorized" in message:
                detail="Space authentication rejected; check HF_TOKEN access"
            elif isinstance(exc,ValueError):
                detail="Space API or box response invalid; frame not accepted"
            elif isinstance(exc,ImportError):
                detail="Install the spaces dependency extra before running"
            else:
                detail="Space request failed or timed out; check availability or retry later"
            raise RuntimeError(detail+". No automatic retry or fallback was performed.") from None
        finally:
            self.latencies.append((time.perf_counter()-started)*1000)

    def synchronize(self): pass

    def resources(self):
        return {"device":"remote","execution":"hf-space-zerogpu","model_id":MODEL_ID,"space_id":SPACE_ID,
            "remote_weights_revision":"community-managed; not pinned","challenge_local_perception_compliant":False,
            "confidence_semantics":"Grounding DINO detector score; not calibrated probability",
            "prompt":DEFAULT_PROMPT,"threshold":self.threshold,"text_threshold":self.text_threshold,
            "max_image_side":self.config.max_side,"max_rock_box_area_fraction":self.max_area,
            "rejected_large_boxes":self.rejected_large_boxes,"api_requests":self.calls,
            "uploaded_jpeg_bytes":self.uploaded_bytes,
            "api_latency_ms_mean":sum(self.latencies)/len(self.latencies) if self.latencies else None}
