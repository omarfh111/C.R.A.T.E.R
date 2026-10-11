"""Journal regression tests adapted to current contracts, not legacy assistant APIs."""
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from crater_assistant.experience import Journal, now
from crater_m2.source import Scenario


def event(session, **updates):
    return dict(eventId=str(uuid.uuid4()), sessionId=session["sessionId"], kind="telemetry_stale",
                eventAt=now(), receivedAt=None, summary="No recent accepted receipt; cause unknown",
                triggerKey="stale", **updates)


@pytest.fixture
def journal(tmp_path):
    return Journal(tmp_path / "journal.sqlite3")


def test_persistent_incident_without_model_and_no_invented_decision(journal):
    session = journal.begin("rover", "historical_replay")
    raw = event(session)
    saved = journal.record(raw)
    reopened = Journal(journal.path)
    assert reopened.get(raw["eventId"]) == saved
    assert saved["provenance"]["observation"] == "historical_replay"
    assert not saved["provenance"]["certifiedMeasurement"]
    assert "decision" not in saved
    assert reopened.list()[0]["job"]["state"] == "waiting_capture"
    assert reopened.record(raw) == saved
    raw["summary"] = "different"
    with pytest.raises(ValueError, match="conflict"):
        reopened.record(raw)


def test_dedup_atomic_and_cooldown(journal):
    session = journal.begin("rover", "synthetic")
    with ThreadPoolExecutor(4) as pool:
        values = list(pool.map(lambda _: journal.record(event(session), clock=100), range(4)))
    assert len({v["eventId"] for v in values}) == 1
    journal.record(event(session), clock=131)
    assert len(journal.list()) == 2


def test_queue_saturation_preserves_incident_and_bounded_retry(tmp_path):
    journal = Journal(tmp_path / "j.db", capacity=1)
    session = journal.begin("rover", "synthetic")
    a, b = event(session), event(session)
    b["kind"], b["triggerKey"] = "websocket_changed", "disconnected"
    journal.record(a); journal.record(b)
    assert journal.list()[0]["job"]["state"] == "saturated"
    with pytest.raises(ValueError, match="saturated"):
        journal.retry(b["eventId"])
    journal.cancel(a["eventId"])
    journal.retry(b["eventId"])
    assert journal.list()[0]["job"]["state"] == "waiting_capture"
    journal.finish(session["sessionId"])
    assert journal.list()[0]["job"]["state"] == "queued"
    journal.update_job(b["eventId"], "failed", attempt=3)
    with pytest.raises(ValueError, match="attempt limit"):
        journal.retry(b["eventId"])


def test_producer_warning_authority_and_separate_review(journal):
    session = journal.begin("rover", "live_inference")
    raw = event(session); raw["kind"] = "producer_warning"
    with pytest.raises(ValueError, match="authority"):
        journal.record(raw)
    saved = journal.record(raw, producer=True)
    review = journal.review(saved["eventId"], "inconclusive", "Cause not established")
    snap = journal.snapshot()
    assert snap["reviews"] == [review]
    assert snap["incidents"][0] == saved
    assert "verified" not in snap["incidents"][0]


@pytest.mark.parametrize("update", [{"question":"invent coordinates"}, {"provenance":"measured"},
    {"eventAt":"yesterday"}, {"sessionId":str(uuid.uuid4())}, {"decision":""}])
def test_reject_invalid_contract(journal, update):
    session = journal.begin("rover", "synthetic")
    raw = event(session); raw.update(update)
    with pytest.raises((ValueError, TypeError)):
        journal.record(raw)


def test_image_reference_hash_root_and_no_vision(tmp_path):
    from PIL import Image
    media = tmp_path / "media"; media.mkdir()
    path = media / "frame.png"; Image.new("RGB", (2,2)).save(path)
    journal = Journal(tmp_path / "j.db", media_root=media)
    session = journal.begin("rover", "synthetic")
    raw = event(session)
    ref = dict(relativePath="frame.png", sha256=hashlib.sha256(path.read_bytes()).hexdigest(), provenance="synthetic")
    raw["images"] = [ref]
    assert journal.record(raw)["images"][0]["imageAnalysis"] == "not_performed"
    for relative in ("../frame.png", "C:/frame.png", "..\\frame.png", "/frame.png"):
        raw = event(session); raw["images"] = [dict(ref, relativePath=relative)]
        with pytest.raises((ValueError, OSError)):
            journal.record(raw)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        journal.record(raw | {"images": [ref]})


def test_storage_bounds_are_explicit(tmp_path):
    journal = Journal(tmp_path / "j.db", max_events=1)
    session = journal.begin("rover", "synthetic")
    journal.record(event(session), clock=100)
    with pytest.raises(ValueError, match="capacity"):
        journal.record(event(session), clock=131)
    with pytest.raises(ValueError, match="capacity"):
        journal.begin("rover", "synthetic")
