"""Curated corpus stays explicit, sourceable and consistent with retrieval probes."""
import json
from pathlib import Path

from crater_assistant.core import chunks_from_files


def test_reviewed_corpus_and_probes_are_consistent():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/knowledge/corpus.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    assert len(files) == len(set(files))
    assert all(path.startswith("docs/") and ".." not in Path(path).parts for path in files)
    assert "docs/knowledge/README.md" not in files
    external = {path for path in files if path.startswith("docs/knowledge/")}
    assert {case["expectedFile"] for case in manifest["retrievalCases"]} == external
    assert all(case["question"].strip() for case in manifest["retrievalCases"])
    for path in external:
        chunks = chunks_from_files([root / path])
        assert len(chunks) == 1, f"Keep facts and limitations together: {path}"
        assert chunks[0]["verifiedOn"] == manifest["reviewedOn"]
        assert chunks[0]["sourceUrl"].startswith("https://")
    chunks_from_files([root / path for path in files])
