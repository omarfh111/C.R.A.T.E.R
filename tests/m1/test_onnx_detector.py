import pytest
from crater_m1.onnx_detector import convert_boxes
from crater_m1.windows_gpu import preferred_adapter


def test_gpu_selection_prefers_dedicated_nvidia_on_hybrid_laptop():
    intel={"device_id":0,"vendor_id":0x8086,"dedicated_video_mb":128}
    nvidia={"device_id":1,"vendor_id":0x10de,"dedicated_video_mb":6144}
    assert preferred_adapter([intel,nvidia])==nvidia
    with pytest.raises(RuntimeError): preferred_adapter([])


def test_onnx_boxes_clipped_deduplicated_and_terrain_rejected():
    boxes,rejected=convert_boxes([[-1,10,30,40],[0,10,30,40],[0,0,100,100]],[.8,.7,.9],100,100,.25)
    assert len(boxes)==1 and boxes[0].bbox==(0,10,30,40) and rejected==1
    assert convert_boxes([[0,0,100,100]],[.9],100,100,.25,max_area=1)[1]==0
    with pytest.raises(RuntimeError): convert_boxes([[0,0,20,20]],[float("nan")],100,100,.25)


def test_fp16_promotion_preserves_stored_weights_and_valid_graph():
    onnx=pytest.importorskip("onnx")
    import numpy as np
    from onnx import helper,numpy_helper,TensorProto
    from crater_m1.onnx_prepare import promote_fp16_graph
    source=np.array([.1,.2],dtype=np.float16)
    graph=helper.make_graph([
        helper.make_node("Cast",["x"],["half"],to=TensorProto.FLOAT16),
        helper.make_node("Mul",["half","weight"],["product"]),
        helper.make_node("Cast",["product"],["y"],to=TensorProto.FLOAT)],"small",
        [helper.make_tensor_value_info("x",TensorProto.FLOAT,[2])],
        [helper.make_tensor_value_info("y",TensorProto.FLOAT,[2])],
        [numpy_helper.from_array(source,name="weight")])
    model=promote_fp16_graph(helper.make_model(graph,opset_imports=[helper.make_opsetid("",17)]))
    assert model.graph.initializer[0].data_type==TensorProto.FLOAT
    np.testing.assert_array_equal(numpy_helper.to_array(model.graph.initializer[0]),source.astype(np.float32))
    assert model.graph.node[0].attribute[0].i==TensorProto.FLOAT
    onnx.checker.check_model(model)


def test_real_local_onnx_gpu_runs_without_network(monkeypatch):
    import os
    if os.environ.get("CRATER_ONNX_SMOKE")!="1": pytest.skip("requires prepared ONNX model and local GPU")
    import socket,cv2
    from crater_m1.onnx_detector import OnnxGroundingDino
    def blocked(*args,**kwargs): raise AssertionError("network forbidden during local inference")
    monkeypatch.setattr(socket.socket,"connect",blocked)
    monkeypatch.setattr(socket,"create_connection",blocked)
    detector=OnnxGroundingDino(device="directml")
    result=detector.detect(cv2.imread("outputs/inspection/left-10.jpg"))
    assert len(result)>=1 and detector.resources()["gpu_adapter"]["vendor_id"]==0x10de
    assert detector.resources()["execution"]=="local-onnx"
