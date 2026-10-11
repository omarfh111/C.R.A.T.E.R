import threading
import time

import pytest

from crater_assistant.core import Assistant, Index
from crater_assistant.experience import Journal
from crater_assistant.experience_analysis import ExperienceService, QueueFull
from test_experience import event


class Backend:
    embedding_model = "test-embedding"
    chat_model = "test-llm"
    def chat(self, question, sources):
        return {"answer": "L'événement est simulé [S1].", "sourceIds": ["S1"], "insufficientEvidence": False}


def assistant(backend=None):
    backend = backend or Backend()
    return Assistant(Index([], [], backend.embedding_model), backend)


def done(service, job_id):
    for _ in range(200):
        job = service.job(job_id)
        if job["state"] in {"completed", "failed"}:
            return job
        time.sleep(.01)
    raise AssertionError("worker did not finish")


def test_event_context_is_cited_but_images_not_interpreted(tmp_path):
    j = Journal(tmp_path / "j.sqlite")
    saved = j.add_event(event())
    with ExperienceService(assistant(), j) as service:
        result = done(service, service.analyze(saved["eventId"])["analysisId"])
    assert result["state"] == "completed"
    assert result["result"]["sources"][0]["path"] == "experience:" + saved["eventId"]
    assert "simulated" in result["result"]["sources"][0]["text"]
    assert "not_performed" in result["result"]["sources"][0]["text"]
    assert Journal(j.path).get_event(saved["eventId"]) == saved


def test_slow_llm_does_not_block_journal_or_job_poll_and_capacity_is_bounded(tmp_path):
    started, release = threading.Event(), threading.Event()
    class Slow(Backend):
        def chat(self, *args):
            started.set()
            assert release.wait(3)
            return super().chat(*args)
    j = Journal(tmp_path / "j.sqlite")
    first = j.add_event(event())
    with ExperienceService(assistant(Slow()), j, capacity=1) as service:
        job = service.analyze(first["eventId"])
        assert started.wait(1)
        second = j.add_event(event(eventId="12345678-1234-4234-8234-123456789abd"))
        assert service.job(job["analysisId"])["state"] == "running"
        assert service.analyze(first["eventId"])["analysisId"] == job["analysisId"]
        with pytest.raises(QueueFull):
            service.analyze(second["eventId"])
        release.set()
        assert done(service, job["analysisId"])["state"] == "completed"


def test_model_failure_is_persisted_and_retry_is_explicit(tmp_path):
    class Failed(Backend):
        def chat(self, *args): raise OSError("secret path must not escape")
    j = Journal(tmp_path / "j.sqlite")
    saved = j.add_event(event())
    with ExperienceService(assistant(Failed()), j) as service:
        job = done(service, service.analyze(saved["eventId"])["analysisId"])
        assert job["state"] == "failed" and "secret" not in job["error"]
        assert service.analyze(saved["eventId"])["state"] == "failed"
    with ExperienceService(assistant(), j) as service:
        assert done(service, service.analyze(saved["eventId"], retry=True)["analysisId"])["state"] == "completed"
    attempts = [r["record"] for r in j.records() if r["recordType"] == "analysis_attempt"]
    assert [r["state"] for r in attempts] == ["failed", "completed"]


def test_only_one_worker_can_use_a_journal(tmp_path):
    j = Journal(tmp_path / "j.sqlite")
    with ExperienceService(assistant(), j):
        with pytest.raises(ValueError, match="worker"):
            ExperienceService(assistant(), j)


def test_large_unicode_event_still_has_a_bounded_analyzable_context(tmp_path):
    j = Journal(tmp_path / "j.sqlite")
    saved = j.add_event(event(summary="字" * 2000, question="字" * 2000,
                             decision={"action": "字" * 1000, "reason": "字" * 1000}))
    with ExperienceService(assistant(), j) as service:
        job = done(service, service.analyze(saved["eventId"])["analysisId"])
    assert job["state"] == "completed"
    assert len(job["result"]["sources"][0]["text"].encode()) <= 16384
    assert j.get_event(saved["eventId"])["summary"] == "字" * 2000


def test_restart_recovers_running_job_as_failed_and_preserves_completed_result(tmp_path):
    import json
    j = Journal(tmp_path / "j.sqlite")
    saved = j.add_event(event())
    with ExperienceService(assistant(), j) as service:
        job = done(service, service.analyze(saved["eventId"])["analysisId"])
    job["state"] = "running"
    with j.connection() as db:
        db.execute("UPDATE jobs SET state='running',payload=?", (json.dumps(job),))
    with ExperienceService(assistant(), j) as service:
        assert service.job(job["analysisId"])["state"] == "failed"
        retried = done(service, service.analyze(saved["eventId"], retry=True)["analysisId"])
        assert retried["attempt"] == 2 and retried["state"] == "completed"


def test_dead_worker_rejects_new_jobs(tmp_path):
    j = Journal(tmp_path / "j.sqlite")
    saved = j.add_event(event())
    service = ExperienceService(assistant(), j)
    service.close()
    with pytest.raises(ValueError, match="stopped"):
        service.analyze(saved["eventId"])


def test_sqlite_failure_stops_worker_and_restart_exposes_interrupted_job(tmp_path):
    import sqlite3
    j = Journal(tmp_path / "j.sqlite")
    saved = j.add_event(event())
    service = ExperienceService(assistant(), j)
    original = service._save
    def fail_on_completion(job):
        if job["state"] == "completed":
            raise sqlite3.OperationalError("simulated write failure")
        original(job)
    service._save = fail_on_completion
    job = service.analyze(saved["eventId"])
    service.thread.join(timeout=2)
    assert not service.thread.is_alive()
    with pytest.raises(ValueError, match="stopped"):
        service.analyze(saved["eventId"])
    service.close()
    with ExperienceService(assistant(), j) as recovered:
        assert recovered.job(job["analysisId"])["state"] == "failed"
