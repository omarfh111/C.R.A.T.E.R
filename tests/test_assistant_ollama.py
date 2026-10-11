"""Offline tests of local Ollama HTTP policy, aggregate deadlines and options."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time

import pytest

from crater_assistant.ollama import AssistantInvalidResponse, AssistantTimeout, Ollama


@contextmanager
def runtime(action):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            action(self, None)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            action(self, body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def reply(handler, data):
    body = json.dumps(data).encode()
    handler.send_response(200)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        pass


def test_redirects_refused_before_following_other_host():
    paths = []
    def action(handler, _):
        paths.append(handler.path)
        handler.send_response(302)
        handler.send_header("Location", "http://localhost:1/private")
        handler.end_headers()
    with runtime(action) as url:
        with pytest.raises(AssistantInvalidResponse, match="redirect"):
            Ollama(url)._get("/api/tags")
    assert paths == ["/api/tags"]


def test_http_calls_share_one_aggregate_deadline():
    calls = []
    def action(handler, _):
        calls.append(handler.path)
        time.sleep(0.16)
        reply(handler, {"capabilities": ["embedding", "completion"]})
    with runtime(action) as url:
        backend = Ollama(url)
        started = time.monotonic()
        with pytest.raises(AssistantTimeout):
            with backend.request_budget(0.25):
                backend._check(backend.embedding_model, "embedding")
                backend._check(backend.chat_model, "completion")
        assert time.monotonic() - started < 0.55
    assert len(calls) == 2


def test_slow_drip_cannot_extend_aggregate_deadline():
    def action(handler, _):
        handler.send_response(200)
        handler.send_header("Content-Length", "200")
        handler.end_headers()
        try:
            for _ in range(200):
                handler.wfile.write(b" ")
                handler.wfile.flush()
                time.sleep(0.04)
        except (BrokenPipeError, ConnectionResetError):
            pass
    with runtime(action) as url:
        backend = Ollama(url)
        started = time.monotonic()
        with pytest.raises(AssistantTimeout):
            with backend.request_budget(0.2):
                backend._get("/api/tags")
        assert time.monotonic() - started < 0.5


def test_preflight_only_checks_installed_metadata(monkeypatch):
    backend = Ollama(gpu=True, keep_alive=120, num_ctx=4096, num_predict=256, num_thread=4)
    calls = []
    def post(path, data):
        calls.append(path)
        return {"capabilities": ["embedding", "completion"]}
    monkeypatch.setattr(backend, "_post", post)
    monkeypatch.setattr(backend, "_get", lambda _: {"models": [
        {"name": backend.embedding_model, "digest": "a" * 64},
        {"name": backend.chat_model, "digest": "b" * 64}]})
    result = backend.preflight()
    assert calls == ["/api/show", "/api/show"]
    assert result["modelStatus"] == "available" and backend.model_status == "available"
    assert result["models"][backend.chat_model] == "b" * 64


def test_gpu_warm_options_metrics_and_short_answer_budget(monkeypatch):
    backend = Ollama(gpu=True, keep_alive=120, num_ctx=4096, num_predict=256, num_thread=4)
    calls = []
    def post(path, data):
        calls.append((path, data))
        if path == "/api/show":
            return {"capabilities": ["embedding", "completion"]}
        if path == "/api/embed":
            return {"embeddings": [[1, 2]], "load_duration": 200}
        return {"message": {"content": "Research context [S1]."}, "load_duration": 100,
                "eval_count": 12, "eval_duration": 12000000}
    monkeypatch.setattr(backend, "_post", post)
    backend.embed(["context"])
    assert calls[-1][1]["keep_alive"] == 120 and calls[-1][1]["options"]["num_gpu"] == -1
    result = backend.chat("What did NASA test?", [{"sourceId": "S1", "text": "A research trial."}])
    assert set(result) == {"answer", "sourceIds", "insufficientEvidence"}
    assert calls[-1][1]["options"]["num_ctx"] == 4096
    assert calls[-1][1]["options"]["num_predict"] == 256
    assert calls[-1][1]["options"]["num_thread"] == 4
    assert calls[-1][1]["options"]["temperature"] == 0.1
    assert backend.last_metrics["eval_count"] == 12
    assert backend.last_metrics["kind"] == "chat"
    assert backend.model_status == "available"


@pytest.mark.parametrize("result", [{}, {"message": None}, {"message": {"content": 1}},
    {"message": {"content": "x" * 8001}}, {"message": {"content": "unfinished [S1]"}, "done_reason": "length"}])
def test_malformed_or_truncated_chat_is_not_an_answer(monkeypatch, result):
    backend = Ollama()
    monkeypatch.setattr(backend, "_post", lambda path, _: {"capabilities": ["completion"]} if path == "/api/show" else result)
    with pytest.raises(AssistantInvalidResponse):
        backend.chat("science", [{"sourceId": "S1", "text": "data"}])


@pytest.mark.parametrize("kwargs", [{"keep_alive": -1}, {"keep_alive": True}, {"num_ctx": 100},
    {"num_predict": 2048}, {"num_thread": 0}, {"timeout": float("nan")}, {"url": "http://localhost:65536"}])
def test_invalid_runtime_configuration_refused(kwargs):
    with pytest.raises(ValueError):
        Ollama(**kwargs)


def test_budget_restored_after_nested_failure():
    backend = Ollama()
    with backend.request_budget(2):
        outer = backend._local.deadline
        with pytest.raises(AssistantTimeout):
            with backend.request_budget(-1):
                backend._remaining()
        assert backend._local.deadline == outer
    assert backend._local.deadline is None
