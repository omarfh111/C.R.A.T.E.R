import json

from crater_assistant.__main__ import main
from test_experience import event


def test_cli_records_reviews_and_exports_without_any_model(tmp_path):
    source = tmp_path / "event.json"
    source.write_text(json.dumps(event()), encoding="utf-8")
    journal = str(tmp_path / "experience.sqlite")
    assert main(["record-event", str(source), "--journal", journal]) == 0
    evidence = tmp_path / "test.json"
    evidence.write_text('{"result":"passed"}', encoding="utf-8")
    assert main(["review-event", event()["eventId"], "--journal", journal, "--reviewer", "Test operator",
                 "--outcome", "confirmed", "--statement", "Test simulé vérifié.", "--evidence", str(evidence)]) == 0
    export = tmp_path / "reviewed.md"
    assert main(["export-experiences", "--journal", journal, "--output", str(export)]) == 0
    assert "Test simulé vérifié" in export.read_text(encoding="utf-8")
    assert main(["export-experiences", "--journal", journal, "--output", str(export)]) == 2
    full = tmp_path / "all.jsonl"
    assert main(["export-journal", "--journal", journal, "--output", str(full)]) == 0
    assert [json.loads(line)["recordType"] for line in full.read_text(encoding="utf-8").splitlines()] == ["event", "review"]
