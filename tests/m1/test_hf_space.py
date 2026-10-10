import json
from pathlib import Path
import numpy as np
import pytest
from crater_m1.hf_config import HFConfig
from crater_m1.hf_space import SpaceGrounding,parse_space_boxes,SPACE_ID

TOKEN="hf_test_placeholder_only"


class FakeJob:
    def __init__(self,result): self.value=result; self.cancelled=False
    def result(self,timeout):
        if isinstance(self.value,Exception): raise self.value
        return self.value
    def cancel(self): self.cancelled=True


class FakeClient:
    def __init__(self,result): self.value=result; self.calls=[]; self.jobs=[]
    def submit(self,image,*args,**kwargs):
        assert Path(image["path"]).exists()
        self.calls.append((image,args,kwargs))
        job=FakeJob(self.value); self.jobs.append(job); return job


def test_pixels_rescale_deduplicate_and_filter_terrain():
    text="rock 0.8 10, 20, 50, 60\nrock 0.7 10, 20, 50, 60\nrock 0.9 0, 0, 640, 480"
    boxes,rejected=parse_space_boxes(text,640,480,1280,960,.25)
    assert len(boxes)==1 and boxes[0].bbox==(20,40,100,120) and rejected==1
    assert parse_space_boxes("No detections.",640,480,1280,960,.25)==([],0)


@pytest.mark.parametrize("text",["", "rock NaN 0, 0, 10, 10", "rock 0.9 0, 0, 641, 480", "sky 0.9 0, 0, 10, 10", "rock 0.9 10, 0, 0, 10", "rock 1.1 0, 0, 10, 10"])
def test_malformed_response_is_rejected(text):
    with pytest.raises(ValueError): parse_space_boxes(text,640,480,1280,960,.25)


def test_authenticated_request_budget_cleanup_and_safe_metrics():
    client=FakeClient(({},"rock 0.8 10, 20, 50, 60")); options={}
    def factory(space,**kwargs):
        assert space==SPACE_ID; options.update(kwargs); return client
    detector=SpaceGrounding(HFConfig(TOKEN,max_side=640,max_requests=1),client_factory=factory)
    assert detector.detect(np.zeros((960,1280,3),dtype=np.uint8))[0].bbox==(20,40,100,120)
    assert options["hf_token"]==TOKEN and options["download_files"] is False
    image,args,kwargs=client.calls[0]
    assert not Path(image["path"]).exists() and kwargs["api_name"]=="/run_grounding"
    assert args==( "rock. stone. boulder.",.25,.2)
    with pytest.raises(RuntimeError,match="HF_MAX_REQUESTS"): detector.detect(np.zeros((100,100,3),dtype=np.uint8))
    assert len(client.calls)==1 and TOKEN not in json.dumps(detector.resources())


@pytest.mark.parametrize("value",[TimeoutError(TOKEN),RuntimeError("GPU quota exceeded "+TOKEN),({},"not a detection"),({},)])
def test_remote_errors_fail_closed_and_never_expose_token(value):
    client=FakeClient(value)
    detector=SpaceGrounding(HFConfig(TOKEN),client_factory=lambda *a,**k:client)
    with pytest.raises(RuntimeError) as error: detector.detect(np.zeros((100,100,3),dtype=np.uint8))
    assert TOKEN not in str(error.value) and len(client.calls)==1 and client.jobs[0].cancelled
