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
    assert "max_workers" not in options  # preserve Gradio prediction, receiver and wait workers
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


def test_space_pipeline_preserves_tracks_cloud_provenance_and_original_pixels(tmp_path):
    from crater_m1.simulation import generate
    from crater_m1.pipeline import run
    generate(tmp_path/"scene",count=3)
    client=FakeClient(({},"rock 0.8 10, 20, 50, 60"))
    detector=SpaceGrounding(HFConfig(TOKEN,max_side=320,max_requests=3),client_factory=lambda *a,**k:client)
    report=run(tmp_path/"scene/scene.mp4",tmp_path/"run",detector,preview=True)
    frames=[json.loads(line) for line in (tmp_path/"run/observations.jsonl").read_text().splitlines()]
    assert report["processed_frames"]==3 and report["unique_track_ids"]==1
    assert all(f["perception"]["execution"]=="remote" and f["camera"] is None for f in frames)
    assert frames[0]["detections"][0]["bboxPx"]==[20,40,100,120]
    assert (tmp_path/"run/preview.mp4").stat().st_size>0


def test_cli_space_default_budget_and_explicit_configuration(tmp_path,monkeypatch,capsys):
    import sys
    from crater_m1.cli import main
    from crater_m1.simulation import generate
    from crater_m1 import hf_space
    generate(tmp_path/"scene",count=5)
    env=tmp_path/"token.env";env.write_text("HF_TOKEN="+TOKEN)
    client=FakeClient(({},"No detections."));real=hf_space.SpaceGrounding
    monkeypatch.setattr(hf_space,"SpaceGrounding",lambda config,**kwargs:real(config,client_factory=lambda *a,**k:client,**kwargs))
    monkeypatch.setattr(sys,"argv",["crater-m1","run",str(tmp_path/"scene/scene.mp4"),"--backend","hf-space","--env-file",str(env),"--output",str(tmp_path/"run"),"--no-preview"])
    main()
    report=json.loads((tmp_path/"run/metrics.json").read_text())
    assert report["processed_frames"]==3 and report["backend"]=="hf-space"
    assert len(client.calls)==3 and TOKEN not in capsys.readouterr().out


def test_quota_error_is_actionable_without_retries():
    client=FakeClient(RuntimeError("You have exceeded your GPU quota"))
    detector=SpaceGrounding(HFConfig(TOKEN),client_factory=lambda *a,**k:client)
    with pytest.raises(RuntimeError,match="wait for quota reset"):
        detector.detect(np.zeros((100,100,3),dtype=np.uint8))
    assert len(client.calls)==1 and client.jobs[0].cancelled
