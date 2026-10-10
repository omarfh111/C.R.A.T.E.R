"""Prepare a pinned local FP32 graph from the smaller FP16 distribution."""
from pathlib import Path
import hashlib
import json

SOURCE_SHA256="04c18d2db35569f11c47732f2e05ed3a71559a8903823fc581e90b0e3168c9ff"


def promote_fp16_graph(model):
    import onnx
    import numpy as np
    from onnx import numpy_helper,TensorProto,AttributeProto
    def tensor(value):
        if value.data_type==TensorProto.FLOAT16:
            value.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(value).astype(np.float32),name=value.name))
    def graph(value):
        for initializer in value.initializer: tensor(initializer)
        for info in list(value.input)+list(value.output)+list(value.value_info):
            if info.type.tensor_type.elem_type==TensorProto.FLOAT16: info.type.tensor_type.elem_type=TensorProto.FLOAT
        for node in value.node:
            for attribute in node.attribute:
                if node.op_type=="Cast" and attribute.name=="to" and attribute.i==TensorProto.FLOAT16:
                    attribute.i=TensorProto.FLOAT
                if attribute.type==AttributeProto.TENSOR: tensor(attribute.t)
                elif attribute.type==AttributeProto.TENSORS:
                    for item in attribute.tensors: tensor(item)
                elif attribute.type==AttributeProto.GRAPH: graph(attribute.g)
                elif attribute.type==AttributeProto.GRAPHS:
                    for item in attribute.graphs: graph(item)
    graph(model.graph)
    onnx.checker.check_model(model)
    return model


def prepare(cache_dir=".cache/huggingface",download=False):
    from huggingface_hub import snapshot_download
    from .onnx_detector import MODEL_ID,MODEL_REVISION,MODEL_FILE
    import onnx
    folder=Path(snapshot_download(MODEL_ID,revision=MODEL_REVISION,cache_dir=cache_dir,
        local_files_only=not download,token=False,allow_patterns=["*.json","*.txt",MODEL_FILE],max_workers=2))
    source=folder/MODEL_FILE
    if not source.is_file(): raise RuntimeError("ONNX source missing; run download-onnx-model")
    destination=Path(cache_dir)/"prepared-onnx"/MODEL_REVISION/"model_fp32.onnx"
    metadata=destination.with_suffix(".json")
    if destination.exists() and metadata.exists():
        saved=json.loads(metadata.read_text())
        if saved.get("source_sha256")==SOURCE_SHA256: return folder,destination
    with source.open("rb") as stream: digest=hashlib.file_digest(stream,"sha256").hexdigest()
    if digest!=SOURCE_SHA256: raise RuntimeError("ONNX source checksum mismatch")
    destination.parent.mkdir(parents=True,exist_ok=True)
    model=promote_fp16_graph(onnx.load(str(source)))
    temporary=destination.with_suffix(".tmp")
    onnx.save(model,str(temporary));temporary.replace(destination)
    metadata.write_text(json.dumps({"model_id":MODEL_ID,"revision":MODEL_REVISION,
        "source_sha256":digest,"transformation":"FP16 values promoted to FP32; rounding loss not reversed"},indent=2))
    return folder,destination
