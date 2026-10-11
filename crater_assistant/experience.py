"""Durable incident journal. No model dependency and no canonical telemetry writes.

Selective redesign of the journal at pinned M2 57b2943; current safety contracts win.
SQLite transactions serialize deduplication/admission across collector and producer.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import uuid

from crater_m2.contract import timestamp, utc_iso, validate_frame

KINDS = {"telemetry_stale", "websocket_changed", "radio_changed", "producer_warning", "operator_note"}
QUESTIONS = {
    "telemetry_stale": "Explain evidence limitations when observations are delayed. Do not infer the cause or estimate mission measurements.",
    "websocket_changed": "Explain why a dashboard connection change does not establish the rover radio state or a perception failure.",
    "radio_changed": "Explain the limits of interpreting a declared communication state, using scientific references where relevant.",
    "producer_warning": "Explain the limitations of camera localization and tracking evidence. Do not diagnose a cause beyond the producer warning.",
    "operator_note": "Explain the scientific context of this operator note without inventing mission measurements or decisions.",
}
ACTIVE = ("waiting_capture", "queued", "waiting_service", "running")


def now():
    return utc_iso(datetime.now(timezone.utc))


def identifier(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("canonical UUID required")
    return value


def text(value, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("bounded nonempty text required")
    return value


def dump(value):
    result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(result.encode()) > 65536:
        raise ValueError("incident exceeds bounded payload")
    return result


class Journal:
    def __init__(self, database, *, media_root=None, capacity=16, max_events=10000):
        if type(capacity) is not int or not 1 <= capacity <= 64 or not 1 <= max_events <= 100000:
            raise ValueError("invalid journal bounds")
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.media_root = Path(media_root).resolve(strict=True) if media_root else None
        self.capacity, self.max_events = capacity, max_events
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, session TEXT NOT NULL,
                    kind TEXT NOT NULL, trigger_key TEXT NOT NULL, recorded REAL NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS incident_dedup ON incidents(session,kind,trigger_key,recorded);
                CREATE TABLE IF NOT EXISTS jobs (event_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
                    result TEXT, error TEXT, updated TEXT NOT NULL, expires REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, event_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, event_id TEXT NOT NULL, payload TEXT NOT NULL);
            """)
            if "expires" not in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}:
                db.execute("ALTER TABLE jobs ADD COLUMN expires REAL NOT NULL DEFAULT 0")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=.2)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def begin(self, rover_id, provenance):
        text(rover_id, 128)
        if provenance not in {"synthetic", "historical_replay", "live_inference"}:
            raise ValueError("explicit producer provenance required")
        session = dict(sessionId=str(uuid.uuid4()), roverId=rover_id, startedAt=now(), endedAt=None,
                       phase="capturing", provenance=provenance, radioProvenance="simulated", authority="m2-producer")
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= self.max_events:
                raise ValueError("session storage capacity reached; export/archive explicitly")
            db.execute("INSERT INTO sessions VALUES (?,?)", (session["sessionId"], dump(session)))
        return session

    def finish(self, session_id, *, interrupted=False):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (identifier(session_id),)).fetchone()
            if not row:
                raise ValueError("unknown session")
            session = json.loads(row[0])
            if session["phase"] != "capturing":
                return session
            session.update(phase="interrupted" if interrupted else "completed", endedAt=now())
            db.execute("UPDATE sessions SET payload=? WHERE id=?", (dump(session), session_id))
            db.execute("UPDATE jobs SET state='queued',updated=? WHERE state='waiting_capture' AND event_id IN "
                       "(SELECT id FROM incidents WHERE session=?)", (now(), session_id))
        return session

    def session(self, session_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (identifier(session_id),)).fetchone()
            if not row:
                raise ValueError("unknown session")
            return json.loads(row[0])

    def sessions(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions ORDER BY rowid DESC LIMIT 20")]

    def _images(self, images):
        if not isinstance(images, list) or len(images) > 4:
            raise ValueError("at most four image references")
        output = []
        for ref in images:
            if not isinstance(ref, dict) or set(ref) != {"relativePath", "sha256", "provenance"} or not self.media_root:
                raise ValueError("configured media root and explicit image provenance required")
            relative = PurePosixPath(text(ref["relativePath"], 300))
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative) or "\\" in str(relative):
                raise ValueError("unsafe media path")
            path = (self.media_root / str(relative)).resolve(strict=True)
            if not path.is_relative_to(self.media_root) or path.suffix.lower() not in {".png", ".jpg", ".jpeg"} or path.stat().st_size > 5*1024*1024:
                raise ValueError("unsafe media file")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if ref["sha256"] != digest or ref["provenance"] not in {"synthetic", "historical_replay", "live_capture", "operator_supplied"}:
                raise ValueError("image hash/provenance mismatch")
            from PIL import Image
            with Image.open(path) as image:
                if image.width * image.height > 20000000:
                    raise ValueError("image dimensions exceed limit")
                image.verify()
            output.append(dict(ref, imageAnalysis="not_performed"))
        return output

    def record(self, event, *, producer=False, clock=None):
        import time
        if not isinstance(event, dict) or not set(event) <= {"eventId", "sessionId", "kind", "eventAt", "receivedAt", "summary", "triggerKey", "frame", "decision", "images"}:
            raise ValueError("unexpected incident fields")
        raw_input = dump(event)
        if len(raw_input.encode()) > 16384:
            raise ValueError("incident request exceeds limit")
        event = json.loads(raw_input)
        event_id, session_id = identifier(event.get("eventId")), identifier(event.get("sessionId"))
        kind = event.get("kind")
        if kind not in KINDS or (kind == "producer_warning" and not producer):
            raise ValueError("producer warnings require native producer authority")
        timestamp(event.get("eventAt")); text(event.get("summary")); text(event.get("triggerKey"), 128)
        if "receivedAt" in event and event["receivedAt"] is not None:
            timestamp(event["receivedAt"])
        if "decision" in event:
            text(event["decision"], 1000)  # Present only when explicitly supplied; never generated.
        if event.get("frame") is not None:
            validate_frame(event["frame"])
            if len(dump(event["frame"]).encode()) > 12000:
                raise ValueError("observation too large")
        images = self._images(event.get("images", []))
        at = time.time() if clock is None else clock
        raw = dump(event)
        with self.connect() as db:
            existing = db.execute("SELECT payload FROM incidents WHERE id=?", (event_id,)).fetchone()
            if existing:
                saved = json.loads(existing[0])
                if saved["submitted"] != event:
                    raise ValueError("UUID payload conflict")
                return saved
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise ValueError("unknown producer session; no inferred end-of-capture")
            session = json.loads(row[0])
            if event.get("frame") and event["frame"]["roverId"] != session["roverId"]:
                raise ValueError("observation rover differs from session")
            # Rate limit each incident kind/key durably, independent of browser reloads.
            duplicate = db.execute("SELECT payload FROM incidents WHERE session=? AND kind=? AND trigger_key=? AND recorded>? ORDER BY recorded DESC LIMIT 1",
                (session_id, kind, event["triggerKey"], at-30)).fetchone()
            if duplicate:
                return json.loads(duplicate[0])
            if db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] >= self.max_events:
                raise ValueError("incident storage capacity reached; export/archive explicitly")
            saved = dict(event, roverId=session["roverId"], question=QUESTIONS[kind], recordedAt=now(),
                         provenance=dict(observation=session["provenance"], radio=session["radioProvenance"],
                                         reporter="m2-producer" if producer else "dashboard-client-reported-v1",
                                         certifiedMeasurement=False), images=images, submitted=event)
            db.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?)", (event_id, session_id, kind, event["triggerKey"], at, dump(saved)))
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE state IN (?,?,?,?)", ACTIVE).fetchone()[0]
            state = "saturated" if count >= self.capacity else ("waiting_capture" if session["phase"] == "capturing" else "queued")
            db.execute("INSERT INTO jobs(event_id,state,updated,expires) VALUES (?,?,?,?)", (event_id, state, now(), at+3600))
        return saved

    def get(self, event_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM incidents WHERE id=?", (identifier(event_id),)).fetchone()
            if not row:
                raise ValueError("unknown incident")
            return json.loads(row[0])

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT i.payload,j.state,j.attempt,j.result,j.error,j.updated FROM incidents i JOIN jobs j ON i.id=j.event_id ORDER BY i.rowid DESC LIMIT 50")
            return [dict(json.loads(r[0]), job=dict(state=r[1], attempt=r[2], result=json.loads(r[3]) if r[3] else None, error=r[4], updatedAt=r[5])) for r in rows]

    def update_job(self, event_id, state, *, result=None, error=None, attempt=None, next_at=0):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?,result=?,error=?,updated=?,next_at=?,attempt=COALESCE(?,attempt) WHERE event_id=?",
                       (state, dump(result) if result else None, error, now(), next_at, attempt, event_id))

    def retry(self, event_id):
        import time
        event = self.get(event_id)
        with self.connect() as db:
            row = db.execute("SELECT state,attempt FROM jobs WHERE event_id=?", (event_id,)).fetchone()
            if row[0] not in {"failed", "cancelled", "interrupted", "saturated", "unavailable"} or row[1] >= 3:
                raise ValueError("job active or attempt limit reached")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE state IN (?,?,?,?)", ACTIVE).fetchone()[0] >= self.capacity:
                raise ValueError("analysis queue saturated")
            session = json.loads(db.execute("SELECT payload FROM sessions WHERE id=?", (event["sessionId"],)).fetchone()[0])
            db.execute("UPDATE jobs SET state=?,error=NULL,updated=?,next_at=0,expires=? WHERE event_id=?",
                       ("waiting_capture" if session["phase"] == "capturing" else "queued", now(), time.time()+3600, event_id))

    def cancel(self, event_id):
        self.get(event_id)
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='cancelled',error=?,updated=? WHERE event_id=? AND state IN (?,?,?,?)",
                       ("Operator cancelled; backend inference may continue until deadline", now(), event_id, *ACTIVE))

    def review(self, event_id, verdict, note):
        self.get(event_id)
        if verdict not in {"confirmed", "rejected", "inconclusive"}:
            raise ValueError("invalid review verdict")
        review = dict(reviewId=str(uuid.uuid4()), eventId=event_id, verdict=verdict, note=text(note), reviewedAt=now(), authority="operator-reported")
        with self.connect() as db:
            if db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] >= self.max_events:
                raise ValueError("review capacity reached")
            db.execute("INSERT INTO reviews VALUES (?,?,?)", (review["reviewId"], event_id, dump(review)))
        return review

    def snapshot(self):
        with self.connect() as db:
            return dict(schemaVersion=1, sessions=[json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions")],
                        incidents=[json.loads(r[0]) for r in db.execute("SELECT payload FROM incidents")],
                        jobs=[dict(zip(("eventId", "state", "attempt", "nextAt", "result", "error", "updatedAt", "expiresAt"), r)) for r in db.execute("SELECT * FROM jobs")],
                        attempts=[json.loads(r[0]) for r in db.execute("SELECT payload FROM attempts")],
                        reviews=[json.loads(r[0]) for r in db.execute("SELECT payload FROM reviews")],
                        limitations="No automatic promotion into RAG or trusted telemetry; image interpretation not performed")
