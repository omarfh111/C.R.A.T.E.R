import os
import socket
import pytest

@pytest.mark.skipif(os.environ.get("CRATER_AI_SMOKE")!="1",reason="requires downloaded model weights and NASA video")
def test_real_model_inference_cannot_connect_to_network(monkeypatch):
    from crater_m1.detectors import GroundingDino
    from crater_m1.video import frames
    def blocked(*args,**kwargs): raise AssertionError("external network forbidden during inference")
    monkeypatch.setattr(socket.socket,"connect",blocked)
    monkeypatch.setattr(socket,"create_connection",blocked)
    detector=GroundingDino(device="cpu",cache_dir=".cache/huggingface",image_size=640)
    _,_,image,_=next(frames(os.environ.get("CRATER_NASA_VIDEO","../vid3.mp4"),view="left",max_frames=1))
    detected=detector.detect(image)
    assert detected, "no rocks detected in the real NASA frame"
    assert all(0<=d.confidence<=1 and d.type=="rock" for d in detected)
    assert detector.resources()["model_revision"]!="main"
