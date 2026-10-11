import hashlib
import json
from pathlib import Path

import pytest

from crater_assistant.experience import Journal


def event(**extra):
    return {"eventId": "12345678-1234-4234-8234-123456789abc", "roverId": "rover-test",
            "capturedAt": "2026-10-11T00:00:00Z", "kind": "telemetry_stale",
            "provenance": "simulated", "summary": "Réception tardive observée pendant un essai.", **extra}


def test_event_is_durable_idempotent_and_conflicts_are_rejected(tmp_path):
    path = tmp_path / "journal.sqlite"
    journal = Journal(path)
    stored = journal.add_event(event(decision={"action": "wait", "reason": "recorded policy"}))
    assert journal.add_event(event(decision={"action": "wait", "reason": "recorded policy"})) == stored
    assert Journal(path).get_event(stored["eventId"]) == stored
    with pytest.raises(ValueError, match="conflict"):
        journal.add_event(event(summary="different"))
    with pytest.raises(ValueError, match="conflict"):
        journal.add_event(event(question="new field"))


@pytest.mark.parametrize("changes", [{"kind": "drive_motor"}, {"provenance": "real-ish"},
    {"capturedAt": "no date"}, {"eventId": "../file"}, {"unknown": True},
    {"summary": "x" * 2001}, {"decision": {"action": "go", "reason": 42}}])
def test_invalid_events_are_not_persisted(tmp_path, changes):
    journal = Journal(tmp_path / "j.sqlite")
    with pytest.raises(ValueError):
        journal.add_event(event(**changes))
    assert journal.events() == []


def test_images_are_verified_references_not_inference(tmp_path):
    from PIL import Image
    media = tmp_path / "media"
    media.mkdir()
    image = media / "frame.png"
    Image.new("RGB", (8, 8)).save(image)
    ref = {"relativePath": "frame.png", "mediaType": "image/png",
           "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    journal = Journal(tmp_path / "j.sqlite", media_root=media)
    saved = journal.add_event(event(images=[ref]))
    assert saved["images"] == [ref]
    assert saved["imageAnalysis"] == "not_performed"
    for bad in [dict(ref, relativePath="../frame.png"), dict(ref, sha256="a" * 64),
                dict(ref, relativePath=str(image)), dict(ref, mediaType="image/jpeg")]:
        with pytest.raises(ValueError):
            journal.add_event(event(images=[bad]))


def test_canonical_frame_must_match_event_rover_and_capture(tmp_path):
    from crater_m2.source import Scenario, observation_to_frame
    from datetime import datetime, timezone
    frame = observation_to_frame(Scenario(datetime(2026, 10, 11, tzinfo=timezone.utc)).observation(0), 0,
                                 {"status": "connected", "packetsSent": 1, "packetsLost": 0}).frame
    journal = Journal(tmp_path / "j.sqlite")
    good = event(roverId=frame["roverId"], capturedAt=frame["capturedAt"], frame=frame)
    assert journal.add_event(good)["frame"] == frame
    with pytest.raises(ValueError):
        journal.add_event(event(frame=frame))


def test_only_reviewed_facts_export_not_model_answers(tmp_path):
    journal = Journal(tmp_path / "j.sqlite")
    saved = journal.add_event(event())
    evidence = tmp_path / "test-result.json"
    evidence.write_text('{"delivered": 4, "pending": 0}', encoding="utf-8")
    assert journal.export_reviewed() == ""
    journal.review(saved["eventId"], "Omar", "confirmed", "Quatre trames livrées dans cet essai.", [evidence])
    text = journal.export_reviewed()
    assert "Quatre trames" in text and "simulated" in text
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() in text
    assert str(tmp_path) not in text
    with pytest.raises(ValueError):
        journal.review(saved["eventId"], "Omar", "confirmed", "Unverified", [])
    journal.review(saved["eventId"], "Omar", "rejected", "Test invalidé après relecture.", [])
    assert journal.export_reviewed() == ""



def test_long_review_keeps_provenance_with_every_retrievable_fact(tmp_path):
    from crater_assistant.core import chunks_from_files
    journal = Journal(tmp_path / "j.sqlite")
    saved = journal.add_event(event())
    evidence = tmp_path / "proof.json"
    evidence.write_text('{"simulated":true}', encoding="utf-8")
    journal.review(saved["eventId"], "Test operator", "confirmed", "Fait observé " * 140, [evidence])
    exported = tmp_path / "facts.md"
    exported.write_text(journal.export_reviewed(), encoding="utf-8")
    chunks = chunks_from_files([exported])
    assert len(chunks) > 1
    for chunk in chunks:
        assert "Fait retenu" in chunk["text"]
        assert "simulated" in chunk["text"]
        assert saved["eventId"] in chunk["text"]
        assert "Limite" in chunk["text"]
