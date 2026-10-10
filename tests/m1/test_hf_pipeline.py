import json
import sys
from types import SimpleNamespace
import pytest
from crater_m1.hf_config import HFConfig
from crater_m1.hf_detector import HostedGrounding
from crater_m1.pipeline import run
from crater_m1.simulation import generate
from crater_m1.cli import main

class FakeHosted:
    def post(self,*args,**kwargs):
        return SimpleNamespace(status_code=200,json=lambda:{"choices":[{"finish_reason":"stop","message":{"content":'{"objects":[{"label":"rock","bbox":[100,200,300,400],"confidence":0.8}]}'}}]})

def test_hosted_predictions_flow_through_tracking_and_report_provenance(tmp_path):
    generate(tmp_path/"scene",count=3)
    detector=HostedGrounding(HFConfig("hf_fake_test_only"),session=FakeHosted())
    output=tmp_path/"run"
    report=run(tmp_path/"scene/scene.mp4",output,detector)
    observations=[json.loads(line) for line in (output/"observations.jsonl").read_text().splitlines()]
    assert len(observations)==3 and len({f["detections"][0]["id"] for f in observations})==1
    assert all(f["perception"]["execution"]=="remote" for f in observations)
    assert all(f["perception"]["challenge_local_perception_compliant"] is False for f in observations)
    assert report["model_resources"]["api_requests"]==3
    assert (output/"preview.mp4").exists()

def test_cli_requires_token_before_creating_output(tmp_path,monkeypatch,capsys):
    monkeypatch.delenv("HF_TOKEN",raising=False)
    monkeypatch.setattr(sys,"argv",["crater-m1","run","missing.mp4","--backend","hf-hosted","--env-file",str(tmp_path/"absent.env"),"--output",str(tmp_path/"out")])
    with pytest.raises(SystemExit) as error: main()
    assert error.value.code==1 and "HF_TOKEN" in capsys.readouterr().err
    assert not (tmp_path/"out").exists()
