"""One local model worker, persistent bounded jobs and explicit retry/recovery."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from uuid import uuid4

from crater_m2.contract import utc_iso
from .experience import QUESTIONS, _id, _json


class QueueFull(ValueError):
    pass


class ExperienceService:
    def __init__(self, assistant, journal, capacity=16):
        if type(capacity) is not int or not 1 <= capacity <= 16:
            raise ValueError("Analysis capacity must be 1..16")
        self.assistant, self.journal, self.capacity = assistant, journal, capacity
        self.model_lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self._lease = open(str(journal.path) + ".worker.lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self._lease.seek(0, 2)
                if self._lease.tell() == 0:
                    self._lease.write(b"0")
                    self._lease.flush()
                self._lease.seek(0)
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lease.close()
            raise ValueError("An analysis worker already owns this journal") from None
        # Holding the OS lease proves that no other worker can still be running.
        with journal.connection() as db:
            for job_id, payload in db.execute("SELECT id,payload FROM jobs WHERE state='running'").fetchall():
                job = json.loads(payload)
                job.update(state="failed", result=None, error="Interrupted analysis; explicit retry required")
                db.execute("UPDATE jobs SET state='failed',payload=? WHERE id=?", (_json(job), job_id))
                db.execute("INSERT OR IGNORE INTO attempts VALUES (?,?,?)", (job_id, job["attempt"], _json(job)))
        self.thread = threading.Thread(target=self._run, daemon=True, name="crater-experience")
        self.thread.start()

    def __enter__(self): return self

    def __exit__(self, *_): self.close()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=2)
        # A running model call retains the lease until the worker actually exits.

    def analyze(self, event_id, retry=False):
        if self.stop.is_set() or not self.thread.is_alive():
            raise ValueError("Analysis service is stopped")
        if type(retry) is not bool:
            raise ValueError("retry must be boolean")
        event = self.journal.get_event(event_id)
        with self.journal.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM jobs WHERE event_id=?", (event_id,)).fetchone()
            prior = json.loads(row[0]) if row else None
            if prior and (prior["state"] != "failed" or not retry):
                return prior
            if prior and prior["attempt"] >= 5:
                raise ValueError("Analysis retry limit reached (5 attempts); record a new event after correcting the cause")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= self.capacity:
                raise QueueFull("Analysis queue full; event remains recorded")
            job = dict(analysisId=prior["analysisId"] if prior else str(uuid4()), eventId=event_id,
                       state="queued", question=event.get("question", QUESTIONS[event["kind"]]),
                       submittedAt=utc_iso(datetime.now(timezone.utc)), result=None, error=None,
                       attempt=prior["attempt"] + 1 if prior else 1)
            if prior:
                db.execute("UPDATE jobs SET state='queued',payload=? WHERE id=?", (_json(job), job["analysisId"]))
            else:
                db.execute("INSERT INTO jobs VALUES (?,?,?,?)", (job["analysisId"], event_id, "queued", _json(job)))
        self.wake.set()
        return job

    def job(self, analysis_id):
        _id(analysis_id)
        with self.journal.connection() as db:
            row = db.execute("SELECT payload FROM jobs WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown analysis")
        return json.loads(row[0])

    def _save(self, job):
        with self.journal.connection() as db:
            db.execute("UPDATE jobs SET state=?,payload=? WHERE id=?", (job["state"], _json(job), job["analysisId"]))
            if job["state"] in {"completed", "failed"}:
                db.execute("INSERT OR IGNORE INTO attempts VALUES (?,?,?)", (job["analysisId"], job["attempt"], _json(job)))

    def _context(self, event):
        summary = {k: v for k, v in event.items() if k not in {"frame", "question"}}
        summary["summary"] = event["summary"][:500]
        summary["summaryExcerptCharacters"] = 500
        if "decision" in summary:
            summary["decision"] = {k: v[:250] for k, v in event["decision"].items()}
            summary["decisionExcerptCharacters"] = 250
        if "frame" in event:
            frame = event["frame"]
            summary["frame"] = dict(frame, hazards=frame["hazards"][:8])
            summary["totalHazards"] = len(frame["hazards"])
            summary["hazardExcerptLimit"] = 8
        prefix = "Événement enregistré ; provenance déclarée, pas certifiée. Les images ne sont pas analysées.\n"
        while len((prefix + _json(summary)).encode()) > 16384 and summary.get("frame", {}).get("hazards"):
            summary["frame"]["hazards"].pop()
        text = prefix + _json(summary)
        return {"label": "experience:" + event["eventId"], "text": text}

    def _run(self):
        try:
            while not self.stop.is_set():
                with self.journal.connection() as db:
                    row = db.execute("SELECT payload FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
                if row is None:
                    self.wake.wait(.5)
                    self.wake.clear()
                    continue
                job = json.loads(row[0])
                job.update(state="running", startedAt=utc_iso(datetime.now(timezone.utc)))
                self._save(job)
                try:
                    with self.model_lock:
                        event = self.journal.get_event(job["eventId"])
                        job["result"] = self.assistant.ask(job["question"], context=self._context(event))
                    job.update(state="completed", finishedAt=utc_iso(datetime.now(timezone.utc)))
                except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                    job.update(state="failed", error="Local analysis unavailable; check model and index, then retry explicitly",
                               finishedAt=utc_iso(datetime.now(timezone.utc)))
                self._save(job)
        except sqlite3.Error:
            self.stop.set()  # Fail closed; durable queued jobs are retained for restart.
        finally:
            self._lease.close()
