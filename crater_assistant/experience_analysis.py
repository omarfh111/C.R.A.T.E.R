"""One durable, bounded post-capture worker; uses the current guarded HTTP engine."""
import json
import os
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.parse import urlsplit

from .experience import dump, now
from .server import live_capture_active, validate_origin


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class RemoteAssistant:
    def __init__(self, url, timeout=50):
        if not validate_origin(url) or not 1 <= timeout <= 600:
            raise ValueError("exact loopback assistant origin and bounded timeout required")
        self.url, self.timeout = url, timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, body=None):
        request = Request(self.url + path, data=None if body is None else dump(body).encode(),
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200 or response.geturl() != self.url + path:
                    raise ValueError("unexpected response or redirect")
                data = response.read(512001)
                if len(data) > 512000:
                    raise ValueError("response exceeds limit")
                value = json.loads(data)
                if not isinstance(value, dict):
                    raise ValueError("invalid response")
                return value
        except HTTPError as exc:
            code = {429: "busy", 503: "unavailable", 504: "timeout", 502: "invalid_response"}.get(exc.code, "failed")
            raise RuntimeError(code) from None

    def available(self):
        health = self.request("/health")
        return health.get("httpReady") is True and health.get("modelStatus") != "unavailable" and health.get("busy") is False

    def analyze(self, event_id):
        result = self.request("/analyze-incident", {"eventId": event_id})
        if (result.get("status") not in {"answered", "insufficient_evidence"} or result.get("facts") is not None
                or not isinstance(result.get("answer"), str) or not isinstance(result.get("sources"), list)
                or result.get("verification") not in {"unverified_generated", "not_generated"}):
            raise ValueError("invalid incident answer")
        known = {s["sourceId"] for s in result["sources"] if isinstance(s, dict) and "sourceId" in s}
        if any(i not in known for i in result.get("citedSourceIds", [])):
            raise ValueError("invalid citations")
        return result


class ExperienceWorker:
    def __init__(self, journal, assistant, *, capture_guard=live_capture_active, interval=1, start=True):
        self.journal, self.assistant, self.capture_guard, self.interval = journal, assistant, capture_guard, interval
        self.stop = threading.Event()
        self.error = None
        self.lease = open(str(journal.path) + ".worker.lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.lease.seek(0, 2)
                if not self.lease.tell():
                    self.lease.write(b"0"); self.lease.flush()
                self.lease.seek(0)
                msvcrt.locking(self.lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lease.close()
            raise ValueError("another worker owns this journal") from None
        with journal.connect() as db:
            db.execute("UPDATE jobs SET state='interrupted',error=?,updated=? WHERE state='running'",
                       ("Worker interrupted; backend termination unknown; explicit retry required", now()))
        self.thread = threading.Thread(target=self.run, daemon=True, name="crater-post-capture")
        if start:
            self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        else:
            self.lease.close()
        # A still-running thread retains its lease until its bounded HTTP request ends.

    def run(self):
        try:
            while not self.stop.is_set():
                try:
                    self.tick()
                except (OSError, ValueError, sqlite3.Error) as exc:
                    self.error = type(exc).__name__  # Fail closed; no private paths/text in health.
                    break
                self.stop.wait(self.interval)
        finally:
            self.lease.close()

    def tick(self, clock=None):
        at = time.time() if clock is None else clock
        if self.capture_guard():
            return  # No health/model request, preloading or inference while capture is active.
        with self.journal.connect() as db:
            row = db.execute("SELECT event_id,state,attempt,expires FROM jobs WHERE state IN ('queued','waiting_service') AND next_at<=? ORDER BY rowid LIMIT 1", (at,)).fetchone()
        if not row:
            return
        event_id, _, attempt, expires = row
        event = self.journal.get(event_id)
        session = self.journal.session(event["sessionId"])
        if session is None or session["phase"] == "capturing":
            return  # Explicit producer completion required; silence never closes a session.
        from crater_m2.contract import timestamp
        if at > expires:
            self.journal.update_job(event_id, "unavailable", error="Automatic analysis window expired; explicit retry required")
            return
        try:
            if not self.assistant.available():
                raise RuntimeError("busy_or_unavailable")
        except (OSError, RuntimeError, ValueError):
            self.journal.update_job(event_id, "waiting_service", error="Guarded assistant unavailable or busy; no model attempt admitted", next_at=at+10)
            return
        # Recheck after health. Sidecar independently checks capture and serializes manual/automatic requests.
        if self.capture_guard() or self.stop.is_set():
            return
        with self.journal.connect() as db:
            current = db.execute("SELECT state FROM jobs WHERE event_id=?", (event_id,)).fetchone()[0]
            if current not in {"queued", "waiting_service"}:
                return
            attempt += 1
            if attempt > 3:
                db.execute("UPDATE jobs SET state='failed',error='Attempt limit reached' WHERE event_id=?", (event_id,))
                return
            db.execute("UPDATE jobs SET state='running',attempt=?,updated=? WHERE event_id=?", (attempt, now(), event_id))
        started = time.perf_counter()
        result, error = None, None
        try:
            result = self.assistant.analyze(event_id)
            # Bounded storage independently validates serialization before committing.
            dump(result)
            state = "completed"
        except (OSError, RuntimeError, ValueError) as exc:
            error = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            state = "waiting_service" if error in {"busy", "unavailable"} and attempt < 3 else "failed"
        with self.journal.connect() as db:
            record = dict(eventId=event_id, attempt=attempt, state=state, error=error,
                          elapsedS=time.perf_counter()-started, finishedAt=now(), result=result)
            db.execute("INSERT INTO attempts(event_id,attempt,payload) VALUES (?,?,?)", (event_id, attempt, dump(record)))
            current = db.execute("SELECT state FROM jobs WHERE event_id=?", (event_id,)).fetchone()[0]
            if current != "cancelled":
                db.execute("UPDATE jobs SET state=?,result=?,error=?,updated=?,next_at=? WHERE event_id=?",
                           (state, dump(result) if result else None, error, now(), at+10, event_id))
