"""Local experience records. Observations, generated analyses and reviews stay separate."""
import hashlib
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image

from crater_m2.contract import timestamp, utc_iso, validate_frame
from .core import CHUNK_CHARS, _read

KINDS = {"telemetry_stale", "link_changed", "tracking_warning", "calibration_missing", "operator_note"}
QUESTIONS = {
    "telemetry_stale": "Que montrent les observations sur le retard de télémétrie ? Quelles causes restent à vérifier ?",
    "link_changed": "Que montre ce changement de liaison et quelles vérifications sont utiles ?",
    "tracking_warning": "Que sait-on sur ce problème de suivi et quelles vérifications sont nécessaires ?",
    "calibration_missing": "Pourquoi les données de calibration manquantes limitent-elles la localisation ?",
    "operator_note": "Explique cet événement à partir des observations disponibles, en distinguant faits et hypothèses.",
}


def _text(value, name, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Invalid {name}: nonempty text <= {maximum} characters")
    return value


def _id(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Expected canonical UUID identifier") from None
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Journal:
    def __init__(self, path, media_root=None):
        self.path = Path(path).resolve()
        self.media_root = Path(media_root).resolve() if media_root else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (job_id TEXT NOT NULL, attempt INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(job_id,attempt))")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _images(self, refs):
        if not isinstance(refs, list) or len(refs) > 4:
            raise ValueError("Expected <=4 image references")
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"relativePath", "mediaType", "sha256"} or not self.media_root:
                raise ValueError("Image references require configured media root and exact metadata")
            relative = Path(_text(ref["relativePath"], "relativePath", 200))
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative) or "\\" in ref["relativePath"]:
                raise ValueError("Image path must be relative, using forward slashes")
            target = (self.media_root / relative).resolve()
            if (not target.is_relative_to(self.media_root) or not target.is_file()
                    or target.suffix.lower() not in {".png", ".jpg", ".jpeg"} or target.stat().st_size > 5 * 1024 * 1024):
                raise ValueError("Expected local image <=5 MiB within media root")
            raw = target.read_bytes()
            if len(raw) > 5 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise ValueError("Image digest mismatch or oversized file")
            with Image.open(io.BytesIO(raw)) as image:
                if ref["mediaType"] != {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image.format):
                    raise ValueError("Image media type mismatch")
                if image.width * image.height > 20_000_000:
                    raise ValueError("Image pixel limit exceeded")
                image.verify()

    def add_event(self, value):
        required = {"eventId", "roverId", "capturedAt", "kind", "provenance", "summary"}
        if not isinstance(value, dict) or not required <= set(value) or not set(value) <= required | {"frame", "images", "decision", "question"}:
            raise ValueError("Invalid experience event fields")
        _id(value["eventId"])
        _text(value["roverId"], "roverId", 100)
        timestamp(_text(value["capturedAt"], "capturedAt", 64))
        if not isinstance(value["kind"], str) or value["kind"] not in KINDS:
            raise ValueError("Unknown event kind")
        if value["provenance"] not in ("measured", "simulated", "operator"):
            raise ValueError("Invalid declared provenance")
        _text(value["summary"], "summary")
        if "question" in value:
            _text(value["question"], "question")
        if "decision" in value:
            decision = value["decision"]
            if not isinstance(decision, dict) or set(decision) != {"action", "reason"}:
                raise ValueError("Decision requires recorded action and reason")
            for key in decision:
                _text(decision[key], key, 1000)
        if "frame" in value:
            frame = validate_frame(value["frame"])
            _text(frame["capturedAt"], "frame capturedAt", 64)
            if frame["roverId"] != value["roverId"] or timestamp(frame["capturedAt"]) != timestamp(value["capturedAt"]):
                raise ValueError("Frame rover/capture must match event")
        self._images(value.get("images", []))
        serialized = _json(value)
        if len(serialized.encode()) > 32768:
            raise ValueError("Event exceeds 32 KiB")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload FROM events WHERE id=?", (value["eventId"],)).fetchone()
            if existing:
                stored = json.loads(existing[0])
                if set(stored) - {"recordedAt", "imageAnalysis"} != set(value):
                    raise ValueError("Event identifier conflict")
                original = {key: stored[key] for key in value}
                if _json(original) != serialized:
                    raise ValueError("Event identifier conflict")
                return stored
            if db.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 10000:
                raise ValueError("Journal event limit reached; archive and start a new journal")
            saved = dict(value, recordedAt=utc_iso(datetime.now(timezone.utc)), imageAnalysis="not_performed")
            db.execute("INSERT INTO events VALUES (?, ?)", (value["eventId"], _json(saved)))
        return saved

    def get_event(self, event_id):
        _id(event_id)
        with self.connection() as db:
            row = db.execute("SELECT payload FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown event")
        return json.loads(row[0])

    def events(self, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Event list limit must be 1..100")
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM events ORDER BY rowid DESC LIMIT ?", (limit,))]

    def review(self, event_id, reviewer, outcome, statement, evidence_paths):
        event = self.get_event(event_id)
        _text(reviewer, "reviewer", 100)
        if not isinstance(outcome, str) or outcome not in {"confirmed", "rejected", "inconclusive"}:
            raise ValueError("Invalid review outcome")
        _text(statement, "review statement")
        if not isinstance(evidence_paths, list) or len(evidence_paths) > 4 or (outcome == "confirmed" and not evidence_paths):
            raise ValueError("Confirmed review needs explicit test evidence (<=4 files)")
        evidence = []
        for path in evidence_paths:
            _, digest = _read(path)
            evidence.append({"file": Path(path).name, "sha256": digest})
        saved = dict(reviewId=str(uuid4()), eventId=event_id, reviewer=reviewer, outcome=outcome,
                     statement=statement, evidence=evidence, provenance=event["provenance"],
                     reviewedAt=utc_iso(datetime.now(timezone.utc)))
        with self.connection() as db:
            if db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] >= 10000:
                raise ValueError("Journal review limit reached")
            db.execute("INSERT INTO reviews VALUES (?, ?)", (saved["reviewId"], _json(saved)))
        return saved

    def export_reviewed(self):
        with self.connection() as db:
            rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM reviews ORDER BY rowid")]
        # Only the latest human review of each event controls export.
        latest = {}
        for row in reversed(rows):
            latest.setdefault(row["eventId"], row)
        lines = []
        for row in list(latest.values())[:100]:
            if row["outcome"] != "confirmed":
                continue
            reviewer = " ".join(row["reviewer"].splitlines())
            prefix = (f"Expérience {row['eventId']} ; relecture {row['reviewId']} par {reviewer}, "
                      f"{row['reviewedAt']} ; provenance déclarée : {row['provenance']} ; "
                      f"preuves SHA256 : {','.join(item['sha256'] for item in row['evidence'])} ; "
                      "Limite : résultat de cet essai, pas garantie générale. ; Fait retenu : ")
            # Each line is one indivisible retrieval unit, including provenance and limits.
            statement = " ".join(row["statement"].splitlines())
            budget = CHUNK_CHARS - len(prefix) - 1
            lines.extend(prefix + statement[offset:offset + budget]
                         for offset in range(0, len(statement), budget))
        return "\n".join(lines)

    def records(self):
        """Snapshot export includes raw events, current jobs, terminal attempts and human reviews."""
        with self.connection() as db:
            db.execute("BEGIN")
            for table, kind in (("events", "event"), ("jobs", "analysis"),
                                ("attempts", "analysis_attempt"), ("reviews", "review")):
                for (payload,) in db.execute(f"SELECT payload FROM {table} ORDER BY rowid"):
                    yield {"recordType": kind, "record": json.loads(payload)}
