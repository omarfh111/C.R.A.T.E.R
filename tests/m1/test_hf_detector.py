import json
from types import SimpleNamespace
import numpy as np
import pytest
import requests
from crater_m1.hf_config import HFConfig
from crater_m1.hf_detector import HostedGrounding,parse_grounding,ROUTER_URL

TOKEN="hf_test_placeholder_only"

def response(text,status=200,reason="stop"):
    return SimpleNamespace(status_code=status,json=lambda:{"choices":[{"finish_reason":reason,"message":{"content":text}}],"usage":{"prompt_tokens":100,"completion_tokens":30}})

class FakeSession:
    def __init__(self,result): self.result=result; self.calls=[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if isinstance(self.result,Exception): raise self.result
        return self.result

def valid(): return json.dumps({"objects":[{"label":"rock","bbox":[100,200,400,600],"confidence":.9}]})

def test_normalized_boxes_map_to_original_pixels_and_deduplicate():
    d=parse_grounding(valid(),1280,960,.25)[0]
    assert d.bbox==pytest.approx((128,192,512,576))
    assert parse_grounding('{"objects":[]}',1280,960,.25)==[]
    assert parse_grounding('```json\n'+valid()+'\n```',1280,960,.25)[0]==d

@pytest.mark.parametrize("text",['not json','[]','{"objects":null}',json.dumps({"objects":[{"label":"rock","bbox":[0,0,1001,900],"confidence":.8}]}),json.dumps({"objects":[{"label":"rock","bbox":[0,0,900,900],"confidence":True}]})])
def test_invalid_model_response_rejected(text):
    with pytest.raises(ValueError): parse_grounding(text,640,480,.25)

def test_actual_request_encoding_and_safe_resource_metrics():
    session=FakeSession(response(valid()))
    detector=HostedGrounding(HFConfig(TOKEN,max_side=640),session=session)
    found=detector.detect(np.zeros((960,1280,3),dtype=np.uint8))
    url,request=session.calls[0]
    assert url==ROUTER_URL and request["allow_redirects"] is False
    assert request["json"]["model"].endswith(":deepinfra")
    assert request["headers"]["Authorization"]=="Bearer "+TOKEN
    assert request["json"]["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert found[0].bbox[2]==512  # no accidental coordinates in resized image
    metrics=detector.resources()
    assert metrics["api_requests"]==1 and metrics["prompt_tokens_reported"]==100
    assert metrics["challenge_local_perception_compliant"] is False
    assert TOKEN not in json.dumps(metrics)

@pytest.mark.parametrize("status",[401,402,403,404,429,503])
def test_provider_errors_do_not_become_empty_detections_or_expose_token(status):
    session=FakeSession(response(TOKEN,status=status)); detector=HostedGrounding(HFConfig(TOKEN),session=session)
    with pytest.raises(RuntimeError) as error: detector.detect(np.zeros((100,100,3),dtype=np.uint8))
    assert TOKEN not in str(error.value) and len(session.calls)==1

def test_timeout_request_budget_and_truncation():
    image=np.zeros((100,100,3),dtype=np.uint8)
    session=FakeSession(requests.Timeout(TOKEN)); detector=HostedGrounding(HFConfig(TOKEN),session=session)
    with pytest.raises(RuntimeError,match="timed out"): detector.detect(image)
    session=FakeSession(response(valid())); detector=HostedGrounding(HFConfig(TOKEN,max_requests=1),session=session)
    detector.detect(image)
    with pytest.raises(RuntimeError,match="HF_MAX_REQUESTS"): detector.detect(image)
    assert len(session.calls)==1
    detector=HostedGrounding(HFConfig(TOKEN),session=FakeSession(response(valid(),reason="length")))
    with pytest.raises(RuntimeError,match="incomplete"): detector.detect(image)
