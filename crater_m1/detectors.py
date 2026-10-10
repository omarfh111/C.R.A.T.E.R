"""Local detection only. Download weights explicitly before offline runs."""
import cv2
from .schema import Detection
from .tracking import suppress_duplicates

MODEL_ID = "IDEA-Research/grounding-dino-tiny"
# Fixed upstream revision for reproducibility.
MODEL_REVISION = "a2bb814dd30d776dcf7e30523b00659f4f141c71"


class GroundingDino:
    def __init__(self, *, device="auto", threshold=.25, text_threshold=.2,
                 prompt="a rock.", cache_dir=None, local_files_only=True, image_size=640):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        self.torch=torch
        self.device=("cuda" if torch.cuda.is_available() else "cpu") if device=="auto" else device
        if self.device=="cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but unavailable")
        self.prompt, self.threshold, self.text_threshold = prompt, threshold, text_threshold
        self.processor=AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
            cache_dir=cache_dir,local_files_only=local_files_only)
        self.processor.image_processor.size={"shortest_edge":image_size,"longest_edge":int(image_size*1.67)}
        self.model=AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_ID,
            revision=MODEL_REVISION,cache_dir=cache_dir,local_files_only=local_files_only,
            use_safetensors=True).to(self.device).eval()
        if self.device=="cuda": torch.cuda.reset_peak_memory_stats()

    def detect(self, image):
        from PIL import Image
        rgb=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
        inputs=self.processor(images=rgb,text=self.prompt,return_tensors="pt").to(self.device)
        with self.torch.inference_mode(): outputs=self.model(**inputs)
        results=self.processor.post_process_grounded_object_detection(outputs,inputs.input_ids,
            threshold=self.threshold,text_threshold=self.text_threshold,
            target_sizes=[image.shape[:2]])[0]
        detections=[]; h,w=image.shape[:2]
        labels=results.get("text_labels",results.get("labels",[]))
        for box,score,label in zip(results["boxes"].cpu().tolist(),results["scores"].cpu().tolist(),labels):
            text=str(label).lower()
            kind="rock" if "rock" in text or "boulder" in text else "crater" if "crater" in text else "slope" if "slope" in text else "unknown"
            x1,y1,x2,y2=box
            box=(max(0.,min(x1,w-1.)),max(0.,min(y1,h-1.)),max(0.,min(x2,w-1.)),max(0.,min(y2,h-1.)))
            if box[2]-box[0]>=4 and box[3]-box[1]>=4:
                detections.append(Detection(box,float(score),kind))
        return suppress_duplicates(detections)

    def synchronize(self):
        if self.device=="cuda": self.torch.cuda.synchronize()

    def resources(self):
        return {"device":self.device,"gpu_peak_allocated_mb":self.torch.cuda.max_memory_allocated()/1048576 if self.device=="cuda" else None}


class SyntheticContrastDetector:
    """Actual image processing for the controlled toy scene, NOT a NASA model.

    Confidence is a fixed heuristic score, explicitly not a learned probability.
    Ground truth positions/boxes are never consumed by this detector.
    """
    device="cpu"
    def detect(self,image):
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        mask=cv2.inRange(gray,0,85)
        n,_,stats,_=cv2.connectedComponentsWithStats(mask)
        result=[]; h,w=gray.shape
        for x,y,bw,bh,area in stats[1:]:
            if area>=80 and bw>=8 and bh>=8 and area/(bw*bh)>=.3 and bw<w*.3 and bh<h*.3:
                result.append(Detection((float(x),float(y),float(min(x+bw-1,w-1)),float(min(y+bh-1,h-1))),.7))
        return result
    def synchronize(self): pass
    def resources(self): return {"device":"cpu","confidence_semantics":"fixed heuristic score"}
