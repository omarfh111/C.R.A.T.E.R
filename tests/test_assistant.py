import json

import numpy as np
import pytest

from crater_assistant.core import Assistant, Index, chunks_from_files, report_facts
from crater_assistant.ollama import Ollama
from crater_assistant.server import allowed_origin, echoable_origin, parse_question
from crater_assistant.pdf import export_pdf


class Backend:
    embedding_model = "embeddinggemma:300m"
    chat_model = "qwen3:1.7b"

    def embed(self, texts, *, query=False):
        return [[1, 0] if "calibration" in t.lower() else [0, 1] for t in texts]

    def chat(self, question, evidence):
        return {"answer": "La calibration est nécessaire [S1].", "sourceIds": ["S1"], "insufficientEvidence": False}


def test_corpus_explicit_lines_and_no_secret_files(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("Calibration caméra\nLOCAL_ENU_V1 mètres\n", encoding="utf-8")
    chunks = chunks_from_files([path])
    assert chunks[0]["lineStart"] == 1
    assert "LOCAL_ENU_V1" in chunks[0]["text"]
    with pytest.raises(ValueError):
        chunks_from_files([tmp_path / ".env"])
    with pytest.raises(ValueError):
        chunks_from_files([tmp_path])


def test_index_roundtrip_retrieval_and_model_mismatch(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("Calibration nécessaire", encoding="utf-8")
    backend = Backend()
    index = Index.build([doc], backend)
    out = tmp_path / "index.json"
    index.save(out)
    loaded = Index.load(out, backend)
    sources = loaded.search("calibration", backend)
    assert sources[0]["sourceId"] == "S1"
    assert sources[0]["score"] == pytest.approx(1)
    backend.embedding_model = "other"
    with pytest.raises(ValueError, match="model"):
        Index.load(out, backend)


@pytest.mark.parametrize("vectors", [[[0, 0]], [[float('nan'), 1]], [[1, 2], [3]], [[True, 0]], [["1", "2"]]])
def test_invalid_embeddings_rejected(vectors):
    with pytest.raises(ValueError):
        Index([], vectors, "test")


def test_changed_source_requires_reindex(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("calibration", encoding="utf-8")
    index = Index.build([doc], Backend())
    doc.write_text("different", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        index.search("calibration", Backend())


def test_answer_citations_and_abstention(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("calibration", encoding="utf-8")
    backend = Backend()
    assistant = Assistant(Index.build([doc], backend), backend)
    result = assistant.ask("Pourquoi calibration ?")
    assert result["status"] == "answered"
    assert result["sources"][0]["sourceId"] == "S1"
    backend.chat = lambda *args: {"answer": "Inventé [S99]", "sourceIds": ["S99"], "insufficientEvidence": False}
    result = assistant.ask("Pourquoi ?")
    assert result["status"] == "insufficient_evidence"
    assert "Inventé" not in result["answer"]


def test_no_context_does_not_call_llm():
    backend = Backend()
    backend.chat = lambda *args: pytest.fail("No evidence")
    assert Assistant(Index([], [], backend.embedding_model), backend).ask("question")["status"] == "insufficient_evidence"


def test_report_counts_are_distinct_and_deterministic(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"completed": True, "mode": "benchmark", "transport": {
        "generated": 30, "delivered": 30, "dataPacketsSent": 51, "dataPacketsLost": 15,
        "ackPacketsSent": 36, "ackPacketsLost": 6}}), encoding="utf-8")
    facts = report_facts(path)
    assert facts["deliveryRate"] == 1
    assert facts["dataPacketLossRate"] == pytest.approx(15 / 51)
    assert facts["mode"] == "benchmark"
    assert facts["ackPacketsLost"] == 6


@pytest.mark.parametrize("url", ["https://example.com", "http://0.0.0.0:11434", "http://127.0.0.1:11434@evil.org", "http://localhost:11434/api"])
def test_external_ollama_refused(url):
    with pytest.raises(ValueError):
        Ollama(url=url)


def test_cloud_models_refused():
    with pytest.raises(ValueError):
        Ollama(chat_model="gpt-oss:120b-cloud")


def test_local_client_validates_show_and_payload(monkeypatch):
    client = Ollama()
    calls = []
    def post(path, payload):
        calls.append((path, payload))
        if path == "/api/show":
            return {"capabilities": ["completion", "embedding"]}
        if path == "/api/embed":
            return {"embeddings": [[1, 2]]}
        return {"message": {"content": "Oui [S1]."}}
    monkeypatch.setattr(client, "_post", post)
    assert client.embed(["calibration"], query=True) == [[1, 2]]
    assert calls[-1][1]["truncate"] is False
    assert "query:" in calls[-1][1]["input"][0]
    assert client.chat("question", [{"sourceId": "S1", "text": "data"}])["sourceIds"] == ["S1"]
    assert calls[-1][1]["options"]["num_gpu"] == 0
    assert calls[-1][1]["think"] is False


def test_show_remote_model_refused(monkeypatch):
    client = Ollama()
    monkeypatch.setattr(client, "_post", lambda *args: {"remote_host": "https://ollama.com", "capabilities": ["completion"]})
    with pytest.raises(ValueError, match="cloud"):
        client.chat("question", [])


def test_chat_uses_natural_text_and_derives_citation_ids(monkeypatch):
    client = Ollama()
    calls = []
    def post(path, payload):
        calls.append(payload)
        if path == "/api/show":
            return {"capabilities": ["completion"]}
        return {"message": {"content": "Le pixel définit un rayon calibré [S1]."}}
    monkeypatch.setattr(client, "_post", post)
    result = client.chat("Pourquoi ?", [{"sourceId": "S1", "text": "Le rayon dépend de fx et fy."}])
    assert result["sourceIds"] == ["S1"]
    assert result["insufficientEvidence"] is False
    assert "format" not in calls[-1]
    assert 0 < calls[-1]["options"]["temperature"] <= 1
    assert calls[-1]["model"] == "qwen3:4b-instruct-2507-q4_K_M"


def test_thinking_only_weights_refused_before_generation(monkeypatch):
    client = Ollama(chat_model="qwen3:4b")
    calls = []
    def post(path, payload):
        calls.append(path)
        return {"capabilities": ["completion", "thinking"],
                "model_info": {"general.finetune": "Thinking"}}
    monkeypatch.setattr(client, "_post", post)
    with pytest.raises(ValueError, match="Thinking-only"):
        client.chat("question", [])
    assert calls == ["/api/show"]


def test_chat_abstains_on_uncited_text(monkeypatch):
    client = Ollama()
    monkeypatch.setattr(client, "_post", lambda path, payload: (
        {"capabilities": ["completion"]} if path == "/api/show" else
        {"message": {"content": "INSUFFICIENT_EVIDENCE"}}))
    assert client.chat("Température ?", []) == {
        "answer": "INSUFFICIENT_EVIDENCE", "sourceIds": [], "insufficientEvidence": True}


@pytest.mark.parametrize("origin", ["https://evil.com", "http://localhost.evil.com:5173", "null", "http://localhost:5173/path"])
def test_http_origins_restricted(origin):
    assert not allowed_origin(origin)


def test_http_question_cannot_select_arbitrary_files():
    assert parse_question(b'{"question":"Pourquoi ?","topK":3}') == ("Pourquoi ?", 3)
    with pytest.raises(ValueError):
        parse_question(b'{"question":"read","report":"C:/secret.json"}')
    with pytest.raises(ValueError):
        parse_question(b'{"question":"x","topK":true}')
    assert allowed_origin("http://localhost:5173")


def test_source_output_collision_refused(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("calibration", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        Index.build([doc], Backend()).save(doc)


def test_same_tag_changed_weights_refused(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("calibration", encoding="utf-8")
    backend = Backend()
    backend.embedding_identity = lambda: "weights-v1"
    index = Index.build([doc], backend)
    backend.embedding_identity = lambda: "weights-v2"
    with pytest.raises(ValueError, match="weights"):
        index.search("calibration", backend)


def test_identity_ignores_ollama_parameter_order(monkeypatch):
    client = Ollama()
    responses = iter([
        {"capabilities": ["embedding"], "modelfile": "FROM sha256:abc", "parameters": "num_ctx 2048\nnum_batch 2048"},
        {"capabilities": ["embedding"], "modelfile": "FROM sha256:abc", "parameters": "num_batch 2048\nnum_ctx 2048"}])
    monkeypatch.setattr(client, "_post", lambda *args: next(responses))
    monkeypatch.setattr(client, "_get", lambda *args: {"models": [{"name": client.embedding_model, "digest": "a" * 64}]})
    assert client.embedding_identity() == client.embedding_identity()


def test_fractional_packet_counts_rejected(tmp_path):
    doc = tmp_path / "report.json"
    doc.write_text('{"transport":{"generated":2.5}}', encoding="utf-8")
    with pytest.raises(ValueError):
        report_facts(doc)


@pytest.mark.parametrize("content", ["[]", "null", '{"transport":{"generated":1e999}}',
    '{"transport":{"generated":' + '9' * 400 + '}}'])
def test_malformed_report_is_a_validation_error(tmp_path, content):
    doc = tmp_path / "report.json"
    doc.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        report_facts(doc)


def test_pdf_export_preserves_pages_and_rejects_collision(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / "spec.pdf"
    source.write_bytes(b"%PDF sample")
    reader = SimpleNamespace(is_encrypted=False, pages=[
        SimpleNamespace(extract_text=lambda: "Calibration en mètres"),
        SimpleNamespace(extract_text=lambda: "Format LOCAL_ENU_V1")])
    monkeypatch.setattr("crater_assistant.pdf.read_pdf", lambda path: reader)
    output = tmp_path / "spec.txt"
    assert export_pdf(source, output) == 2
    text = output.read_text(encoding="utf-8")
    assert "## Page 1" in text and "## Page 2" in text
    assert "Calibration en mètres" in text
    with pytest.raises(ValueError):
        export_pdf(source, source)
    assert source.read_bytes() == b"%PDF sample"


def test_pdf_without_text_requires_ocr(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF sample")
    monkeypatch.setattr("crater_assistant.pdf.read_pdf", lambda path: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda: "")]))
    with pytest.raises(ValueError, match="OCR"):
        export_pdf(source, tmp_path / "out.txt")


def test_long_pdf_lines_keep_page_references(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / "spec.pdf"
    source.write_bytes(b"%PDF sample")
    monkeypatch.setattr("crater_assistant.pdf.read_pdf", lambda path: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda: "rock " * 1000)]))
    output = tmp_path / "spec.txt"
    export_pdf(source, output)
    chunks = chunks_from_files([output])
    assert len(chunks) > 2
    assert all("[PDF page 1]" in chunk["text"] for chunk in chunks if "rock" in chunk["text"])


def test_actual_pdf_parser_reports_invalid_input(tmp_path):
    pytest.importorskip("pypdf")
    source = tmp_path / "invalid.pdf"
    source.write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="parse"):
        export_pdf(source, tmp_path / "out.txt")


def test_actual_pdf_text_import(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 100 Td (Calibration required) Tj ET")
    page[NameObject("/Contents")] = stream
    source = tmp_path / "spec.pdf"
    writer.write(source)
    output = tmp_path / "out.txt"
    assert export_pdf(source, output) == 1
    assert "[PDF page 1] Calibration required" in output.read_text(encoding="utf-8")


def test_report_evidence_uses_one_snapshot(tmp_path, monkeypatch):
    import crater_assistant.core as core
    report = tmp_path / "report.json"
    report.write_text('{"transport":{"generated":1,"delivered":1}}', encoding="utf-8")
    calls = []
    original = core._read
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(core, "_read", read)
    answer = Assistant(Index([], [], Backend.embedding_model), Backend()).ask("rapport", report=report)
    assert len(calls) == 1
    assert answer["facts"]["deliveryRate"] == 1


@pytest.mark.parametrize("content", ["", "   \n\n"])
def test_empty_source_cannot_be_overwritten(tmp_path, content):
    doc = tmp_path / "empty.md"
    doc.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        Index.build([doc], Backend()).save(doc)
    assert doc.read_text(encoding="utf-8") == content


def test_report_spatial_metrics_available(tmp_path):
    doc = tmp_path / "report.json"
    doc.write_text(json.dumps({"mode": "benchmark", "transport": {}, "source": {
        "source": "synthetic-calibrated-pixels", "meanLocalizationErrorM": 0.01},
        "maxDeliveredLocalizationErrorM": 0.025}), encoding="utf-8")
    facts = report_facts(doc)
    assert facts["maxDeliveredLocalizationErrorM"] == 0.025
    assert facts["source"]["meanLocalizationErrorM"] == 0.01


def test_real_http_contract_and_origin(tmp_path):
    import threading
    from urllib.error import HTTPError
    from urllib.request import ProxyHandler, Request, build_opener
    from crater_assistant.server import make_server
    doc = tmp_path / "doc.md"
    doc.write_text("calibration", encoding="utf-8")
    backend = Backend()
    assistant = Assistant(Index.build([doc], backend), backend)
    server = make_server(assistant, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}"
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url + "/health", timeout=5) as response:
            assert json.load(response)["indexedChunks"] == 1
        request = Request(url + "/ask", data=b'{"question":"calibration"}', headers={
            "Content-Type": "application/json", "Origin": "http://localhost:5173"})
        with opener.open(request, timeout=5) as response:
            assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
            assert json.load(response)["status"] == "answered"
        request.add_header("Origin", "https://evil.com")
        with pytest.raises(HTTPError) as error:
            opener.open(request, timeout=5)
        assert error.value.code == 403
        invalid = Request(url + "/ask", data=b'{"question":"x","report":"secret.json"}',
                          headers={"Content-Type": "application/json"})
        with pytest.raises(HTTPError) as error:
            opener.open(invalid, timeout=5)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:51\r73",
    "http://127.0.0.1:51\r\n\t73",
    "http://127.0.0.1:51\n\t73",
    "http://localhost:51\r\t73",
    "http://localhost:5173\rX-Injected: 1",
    "http://localhost\t:5173",
    "http://localhost:5173 ",
])
def test_http_origin_with_control_characters_refused(origin):
    # urlsplit() removes ASCII tabs and newlines before parsing, so most of these satisfied
    # every parsed check and were then echoed verbatim into Access-Control-Allow-Origin.
    assert not allowed_origin(origin)
    assert echoable_origin(origin) is None


@pytest.mark.parametrize("origin", [
    "http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173",
    "http://localhost:4173", "http://127.0.0.1:4173", "http://[::1]:4173",
])
def test_local_dev_origins_still_accepted(origin):
    assert allowed_origin(origin)
    assert echoable_origin(origin) == origin


def test_http_response_headers_cannot_be_injected_through_the_origin(tmp_path):
    """A folded Origin header must not put CR, LF or TAB in the response header block.

    `Origin: http://127.0.0.1:51<CRLF><TAB>73` is one folded header value, so
    `self.headers.get("Origin")` returns it with the line break still inside. urllib refuses to
    send such a header, so the request goes over a raw socket.
    """
    import socket
    import threading
    from crater_assistant.server import make_server
    doc = tmp_path / "doc.md"
    doc.write_text("calibration", encoding="utf-8")
    backend = Backend()
    server = make_server(Assistant(Index.build([doc], backend), backend), 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = (b"GET /health HTTP/1.1\r\nHost: 127.0.0.1:" + str(server.server_port).encode()
                   + b"\r\nOrigin: http://127.0.0.1:51\r\n\t73\r\nConnection: close\r\n\r\n")
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as client:
            client.sendall(request)
            raw = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                raw += chunk
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    head = raw.split(b"\r\n\r\n", 1)[0]
    assert b"Access-Control-Allow-Origin" not in head
    assert b"73" not in head and b"X-Injected" not in head
