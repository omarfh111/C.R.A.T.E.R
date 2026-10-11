import asyncio
import json
import os
from pathlib import Path

from crater_assistant.experience import Journal
from crater_m2.__main__ import arguments, execute
from crater_m2.contract import validate_frame


def test_optional_journal_preserves_lossy_blackout_frames(tmp_path):
    common = ["--benchmark", "--duration","2", "--fps","5", "--blackout",".2:.7", "--loss",".3", "--bandwidth","4096", "--input",str(Path(__file__).resolve().parents[1]/"examples/m1-onnx-calibrated/observations.jsonl"), "--input-ground-z","0"]
    def run(label, journal=False):
        args = arguments(common+["--report",str(tmp_path/f"{label}.json"), "--received-jsonl",str(tmp_path/f"{label}.jsonl")]
                         + (["--incident-journal",str(tmp_path/"j.db")] if journal else []))
        report = asyncio.run(execute(args))
        frames = [json.loads(line) for line in args.received_jsonl.read_text().splitlines()]
        for frame in frames: validate_frame(frame)
        return report, frames
    normal, a = run("off")
    optional, b = run("on", True)
    assert a == b and len(a) == 10
    assert normal["transport"] == optional["transport"]
    session = Journal(tmp_path/"j.db").sessions()[0]
    assert session["phase"] == "completed" and session["provenance"] == "historical_replay"
    assert optional["incidentJournal"]["failed"] == 0


def test_real_producer_failure_is_recorded_and_session_closed(tmp_path, monkeypatch):
    import crater_m2.__main__ as cli
    args = arguments(["--benchmark", "--incident-journal", str(tmp_path/"j.db"), "--report",str(tmp_path/"r.json"), "--received-jsonl",str(tmp_path/"r.jsonl")])
    async def failure(_): raise ValueError("calibration missing for actual frame")
    monkeypatch.setattr(cli, "_execute", failure)
    import pytest
    with pytest.raises(ValueError, match="calibration"): asyncio.run(execute(args))
    journal = Journal(tmp_path/"j.db")
    assert journal.sessions()[0]["phase"] == "interrupted"
    incident = journal.list()[0]
    assert incident["kind"] == "producer_warning" and incident["provenance"]["reporter"] == "m2-producer"
    assert "calibration missing" in incident["summary"]
    assert incident["job"]["state"] == "queued"


def test_journal_failure_cannot_break_rover(tmp_path):
    # A directory cannot be opened as SQLite; optional journal must fail independently.
    args = arguments(["--benchmark","--duration",".1", "--incident-journal",str(tmp_path), "--report",str(tmp_path/"r.json"), "--received-jsonl",str(tmp_path/"r.jsonl")])
    assert asyncio.run(execute(args))["completed"]
