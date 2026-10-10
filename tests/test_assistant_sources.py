import json

import pytest

from crater_assistant.core import Index, chunks_from_files


class Backend:
    embedding_model = "test"
    def embed(self, texts, **kwargs): return [[1, 0] for _ in texts]


def test_official_source_metadata_survives_chunking_index_and_retrieval(tmp_path):
    doc = tmp_path / "nasa.md"
    url = "https://science.nasa.gov/resource/how-perseverance-drives-on-mars/"
    doc.write_text(f"Source URL: {url}\nVerified on: 2026-10-10\n\n" + "terrain " * 300, encoding="utf-8")
    index = Index.build([doc], Backend())
    assert len(index.chunks) > 1
    output = tmp_path / "index.json"
    index.save(output)
    result = Index.load(output, Backend()).search("terrain", Backend())
    assert all(chunk["sourceUrl"] == url and chunk["verifiedOn"] == "2026-10-10" for chunk in result)


@pytest.mark.parametrize("url", ["http://science.nasa.gov/x", "https://nasa.gov.evil.com/x",
    "https://evil.com/nasa.gov", "https://user:pass@science.nasa.gov/x", "javascript:alert(1)"])
def test_invalid_official_source_links_rejected(tmp_path, url):
    doc = tmp_path / "nasa.md"
    doc.write_text(f"Source URL: {url}\nVerified on: 2026-10-10\nText", encoding="utf-8")
    with pytest.raises(ValueError, match="source"):
        chunks_from_files([doc])


def test_tampered_index_source_metadata_rejected(tmp_path):
    doc = tmp_path / "nasa.md"
    doc.write_text("Text", encoding="utf-8")
    index = Index.build([doc], Backend())
    out = tmp_path / "index.json"
    index.save(out)
    data = json.loads(out.read_text())
    data["chunks"][0]["sourceUrl"] = "https://evil.com"
    out.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="source"):
        Index.load(out, Backend())
