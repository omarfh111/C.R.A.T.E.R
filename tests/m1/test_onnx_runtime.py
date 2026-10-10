"""Numerical offline runtime checks using a tiny graph, without rover weights."""
import os
import socket
import numpy as np
import pytest


def test_promoted_graph_executes_numerically_without_network(monkeypatch):
    onnx=pytest.importorskip('onnx')
    ort=pytest.importorskip('onnxruntime')
    from onnx import helper,numpy_helper,TensorProto
    from crater_m1.onnx_prepare import promote_fp16_graph
    stored=np.array([.1,.2],dtype=np.float16)
    graph=helper.make_graph([
        helper.make_node('Cast',['x'],['half'],to=TensorProto.FLOAT16),
        helper.make_node('Mul',['half','weight'],['product']),
        helper.make_node('Cast',['product'],['y'],to=TensorProto.FLOAT)],'runtime-fixture',
        [helper.make_tensor_value_info('x',TensorProto.FLOAT,[2])],
        [helper.make_tensor_value_info('y',TensorProto.FLOAT,[2])],
        [numpy_helper.from_array(stored,name='weight')])
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',17)])
    model.ir_version=10
    promoted=promote_fp16_graph(model)
    def blocked(*args,**kwargs): raise AssertionError('runtime inference must remain offline')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setattr(socket,'create_connection',blocked)
    ort.disable_telemetry_events()
    session=ort.InferenceSession(promoted.SerializeToString(),providers=['CPUExecutionProvider'])
    inputs=np.array([2.,-3.],dtype=np.float32)
    actual=session.run(None,{'x':inputs})[0]
    np.testing.assert_allclose(actual,inputs*stored.astype(np.float32),rtol=1e-7,atol=0)


def test_directml_distribution_registers_provider_when_required():
    if os.environ.get('CRATER_REQUIRE_DIRECTML')!='1':
        pytest.skip('DirectML package registration is checked by Windows CI')
    ort=pytest.importorskip('onnxruntime')
    assert 'DmlExecutionProvider' in ort.get_available_providers()
