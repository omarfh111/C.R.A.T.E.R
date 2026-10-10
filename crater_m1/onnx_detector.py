"""Offline Grounding DINO Tiny ONNX; GPU via DirectML or explicit CPU."""
from types import SimpleNamespace
import cv2
import numpy as np
from .schema import Detection
from .tracking import suppress_duplicates
from .terrain import reject_terrain_box

MODEL_ID="onnx-community/grounding-dino-tiny-ONNX"
MODEL_REVISION="ff690b0a8050566c290287545bd059350f3e9096"
MODEL_FILE="onnx/model_fp16.onnx"


def convert_boxes(boxes,scores,width,height,threshold,max_area=.5,terrain_policy="edges"):
    found=[];rejected=0
    for box,score in zip(boxes,scores):
        x1,y1,x2,y2=(float(v) for v in box);score=float(score)
        if not np.isfinite([x1,y1,x2,y2,score]).all() or not 0<=score<=1:
            raise RuntimeError("ONNX produced invalid boxes or scores")
        x1,x2=max(0.,min(x1,width-1.)),max(0.,min(x2,width-1.))
        y1,y2=max(0.,min(y1,height-1.)),max(0.,min(y2,height-1.))
        if score<threshold or x2-x1<4 or y2-y1<4: continue
        if reject_terrain_box((x1,y1,x2,y2),width,height,max_area,terrain_policy):
            rejected+=1;continue
        found.append(Detection((x1,y1,x2,y2),score,"rock"))
    return suppress_duplicates(found),rejected


class OnnxGroundingDino:
    def __init__(self,*,device="auto",cache_dir=".cache/huggingface",image_size=800,
                 threshold=.25,text_threshold=.2,max_area=.5,profile=False,terrain_policy="edges"):
        import onnxruntime as ort
        import torch
        from transformers import AutoProcessor
        if device not in {"auto","cpu","directml"}: raise ValueError("ONNX device must be auto, cpu or directml")
        if not 0<threshold<1 or not 0<text_threshold<1 or not 0<max_area<=1 or image_size!=800 or terrain_policy not in {"edges","area","off"}:
            raise ValueError("invalid ONNX settings")
        # Local cache lookup only. Preparation is a separate explicit command.
        from .onnx_prepare import prepare
        folder,model_path=prepare(cache_dir,download=False)
        self.torch=torch;torch.set_num_threads(4)
        self.processor=AutoProcessor.from_pretrained(str(folder),local_files_only=True)
        self.processor.image_processor.size={"height":800,"width":800}
        self.image_size=image_size;self.threshold=threshold;self.text_threshold=text_threshold;self.max_area=max_area;self.terrain_policy=terrain_policy
        self.prompt="rock. stone. boulder.";self.rejected_large_boxes=0;self.adapter=None
        ort.disable_telemetry_events()
        providers=ort.get_available_providers()
        self.device="directml" if device=="auto" and "DmlExecutionProvider" in providers else "cpu" if device=="auto" else device
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.enable_profiling=profile
        options.log_severity_level=3
        if profile:
            from pathlib import Path
            Path("outputs/profiles").mkdir(parents=True,exist_ok=True)
            options.profile_file_prefix="outputs/profiles/local-onnx"
        options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        if self.device=="directml":
            if "DmlExecutionProvider" not in providers: raise RuntimeError("DirectML unavailable; install onnxruntime-directml or select cpu")
            from .windows_gpu import adapters,preferred_adapter
            self.adapter=preferred_adapter(adapters())
            options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
            selected=[("DmlExecutionProvider",{"device_id":str(self.adapter["device_id"])}),"CPUExecutionProvider"]
        else: selected=["CPUExecutionProvider"]
        self.session=ort.InferenceSession(str(model_path),sess_options=options,providers=selected)
        self.session.disable_fallback()
        if self.device=="directml" and "DmlExecutionProvider" not in self.session.get_providers():
            raise RuntimeError("GPU session initialization failed; CPU fallback was refused")
        self.ort_version=ort.__version__;self.profile=profile

    def detect(self,image):
        from PIL import Image
        rgb=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
        encoded=self.processor(images=rgb,text=self.prompt,return_tensors="np")
        dtype={"tensor(float)":np.float32,"tensor(float16)":np.float16,"tensor(int64)":np.int64,"tensor(bool)":np.bool_}
        inputs={}
        for item in self.session.get_inputs():
            if item.name not in encoded or item.type not in dtype: raise RuntimeError(f"unsupported ONNX input {item.name} ({item.type})")
            inputs[item.name]=np.asarray(encoded[item.name],dtype=dtype[item.type])
        outputs=dict(zip([item.name for item in self.session.get_outputs()],self.session.run(None,inputs)))
        if not {"logits","pred_boxes"}<=outputs.keys(): raise RuntimeError("unexpected ONNX model outputs")
        result=SimpleNamespace(logits=self.torch.from_numpy(outputs["logits"].astype(np.float32)),
            pred_boxes=self.torch.from_numpy(outputs["pred_boxes"].astype(np.float32)))
        grounded=self.processor.post_process_grounded_object_detection(result,self.torch.from_numpy(encoded["input_ids"]),
            threshold=self.threshold,text_threshold=self.text_threshold,target_sizes=[image.shape[:2]])[0]
        detections,rejected=convert_boxes(grounded["boxes"].tolist(),grounded["scores"].tolist(),image.shape[1],image.shape[0],self.threshold,self.max_area,self.terrain_policy)
        self.rejected_large_boxes+=rejected
        return detections

    def synchronize(self): pass  # session.run returns completed CPU-readable outputs

    def resources(self):
        return {"device":self.device,"execution":"local-onnx","model_id":MODEL_ID,"model_revision":MODEL_REVISION,
            "source_model_file":MODEL_FILE,"prepared_model_file":"model_fp32.onnx","precision":"FP32 promoted from FP16 source","onnxruntime_version":self.ort_version,
            "providers":self.session.get_providers(),"gpu_adapter":self.adapter,"image_size":self.image_size,
            "prompt":self.prompt,"threshold":self.threshold,"text_threshold":self.text_threshold,
            "max_rock_box_area_fraction":self.max_area,"terrain_filter_policy":self.terrain_policy,"rejected_large_boxes":self.rejected_large_boxes,
            "confidence_semantics":"Grounding DINO detector score; not calibrated probability",
            "challenge_local_perception_compliant":True,
            "provider_note":"DirectML accelerates supported operators; unsupported/shape operators may execute on CPU."}
