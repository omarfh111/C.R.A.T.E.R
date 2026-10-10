import pytest
from crater_m1.hf_config import HFConfig

def test_missing_token_reports_action_without_value(tmp_path,monkeypatch):
    monkeypatch.delenv("HF_TOKEN",raising=False)
    with pytest.raises(ValueError,match="HF_TOKEN"): HFConfig.load(tmp_path/"missing.env")

def test_dotenv_and_environment_priority_never_disclose_token(tmp_path,monkeypatch):
    path=tmp_path/".env"; path.write_text('HF_TOKEN=hf_test_file_value\nHF_MAX_SIDE=640\n')
    monkeypatch.setenv("HF_TOKEN","hf_test_environment_value")
    config=HFConfig.load(path)
    assert config.token=="hf_test_environment_value" and config.max_side==640
    assert config.token not in repr(config)

@pytest.mark.parametrize("kwargs",[{"max_requests":0},{"timeout_s":float("nan")},{"max_side":50},{"model":"Qwen/model:provider"}])
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError): HFConfig("hf_test_placeholder",**kwargs)
