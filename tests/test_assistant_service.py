"""Real loopback HTTP tests: admission, origin policy and failure isolation."""

from contextlib import contextmanager
import json
import socket
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from crater_assistant.ollama import AssistantInvalidResponse, AssistantTimeout, AssistantUnavailable
from crater_assistant.server import make_server, validate_origin


class StubAssistant:
    def __init__(self, ask=None):
        self.backend = SimpleNamespace(chat_model="local-chat", embedding_model="local-embedding",
                                       timeout=2, model_status="unchecked")
        self.index = SimpleNamespace(chunks=[{}])
        self.calls = 0
        self.action = ask

    def ask(self, question, top_k, report):
        self.calls += 1
        if self.action:
            return self.action()
        return {"status": "insufficient_evidence", "answer": "No evidence"}


@contextmanager
def running(assistant, **kwargs):
    server = make_server(assistant, 0, **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def call(url, path="/health", body=None, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    request = Request(url + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            return response.status, json.load(response), response.headers
    except HTTPError as response:
        return response.status, json.load(response), response.headers


def test_health_remains_responsive_and_second_question_is_busy():
    entered, release = threading.Event(), threading.Event()
    def slow():
        entered.set()
        assert release.wait(3)
        return {"status": "insufficient_evidence"}
    assistant = StubAssistant(slow)
    with running(assistant) as (_, url):
        worker = threading.Thread(target=call, args=(url, "/ask", {"question": "science"}))
        worker.start()
        assert entered.wait(1)
        started = time.monotonic()
        status, health, _ = call(url)
        assert time.monotonic() - started < 0.75
        assert status == 200 and health["httpReady"] is True and health["busy"] is True
        assert health["modelStatus"] == "unchecked" and health["inferenceState"] == "running"
        status, error, _ = call(url, "/ask", {"question": "second"})
        assert status == 429 and error["code"] == "busy" and assistant.calls == 1
        release.set()
        worker.join(2)
        assert not worker.is_alive()


def test_dynamic_origin_is_exact_and_preflight_restricted():
    with running(StubAssistant(), allowed_origins=["http://127.0.0.1:55991"]) as (_, url):
        status, _, headers = call(url, origin="http://127.0.0.1:55991")
        assert status == 200 and headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:55991"
        for origin in ["http://127.0.0.1:55992", "http://localhost:55991", "http://127.0.0.1:5173", "https://evil.test"]:
            status, error, headers = call(url, origin=origin)
            assert status == 403 and error["code"] == "forbidden"
            assert "Access-Control-Allow-Origin" not in headers
        request = Request(url + "/ask", method="OPTIONS", headers={
            "Origin": "http://127.0.0.1:55991", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"})
        with build_opener(ProxyHandler({})).open(request) as response:
            assert response.status == 200


@pytest.mark.parametrize("origin", ["*", "http://localhost:0", "http://localhost:70000", "http://localhost:5173/",
    "http://LOCALHOST:5173", "http://localhost:5173?x", "http://localhost:5173#x", "http://localhost:05173",
    "http://user@localhost:5173", "http://localhost.evil:5173", "https://localhost:5173"])
def test_invalid_explicit_origin_rejected(origin):
    assert not validate_origin(origin)
    with pytest.raises(ValueError):
        make_server(StubAssistant(), 0, allowed_origins=[origin])


@pytest.mark.parametrize(("exc", "status", "code"), [
    (AssistantUnavailable("model missing"), 503, "unavailable"),
    (AssistantInvalidResponse("bad output"), 502, "invalid_response"),
    (AssistantTimeout("slow model"), 504, "timeout"),
])
def test_machine_readable_failure_and_timeout_quarantine(exc, status, code):
    def fail():
        raise exc
    assistant = StubAssistant(fail)
    with running(assistant) as (_, url):
        actual, error, _ = call(url, "/ask", {"question": "science"})
        assert actual == status and error["code"] == code
        _, health, _ = call(url)
        assert health["httpReady"] is True
        if code == "timeout":
            assert health["busy"] and health["inferenceState"] == "timeout_requires_restart"
            actual, error, _ = call(url, "/ask", {"question": "second"})
            assert actual == 429 and error["code"] == "busy" and assistant.calls == 1
        elif code == "unavailable":
            assert health["modelStatus"] == "unavailable"


def test_cancelled_client_does_not_release_inference_admission():
    entered, release = threading.Event(), threading.Event()
    def slow():
        entered.set()
        assert release.wait(3)
        return {"status": "insufficient_evidence"}
    with running(StubAssistant(slow)) as (server, url):
        client = socket.create_connection(("127.0.0.1", server.server_port))
        body = b'{"question":"science"}'
        client.sendall(f"POST /ask HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
        assert entered.wait(1)
        client.close()
        status, error, _ = call(url, "/ask", {"question": "second"})
        assert status == 429 and error["code"] == "busy"
        release.set()


def test_host_rebinding_and_duplicate_host_are_refused():
    with running(StubAssistant()) as (server, _):
        for hosts in ["Host: evil.test", f"Host: 127.0.0.1:{server.server_port}\r\nHost: evil.test"]:
            with socket.create_connection(("127.0.0.1", server.server_port)) as client:
                client.sendall(f"GET /health HTTP/1.0\r\n{hosts}\r\n\r\n".encode())
                assert b"403" in client.recv(1024).split(b"\r\n")[0]


def test_request_connections_are_bounded_without_worker_queue():
    with running(StubAssistant(), max_connections=2) as (server, url):
        sockets = [socket.create_connection(("127.0.0.1", server.server_port)) for _ in range(2)]
        try:
            for client in sockets:
                client.sendall(b"GET /health HTTP/1.0\r\n")  # deliberately incomplete headers
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and server._connections._value:
                time.sleep(0.01)
            status, error, _ = call(url)
            assert status == 429 and error["code"] == "busy"
        finally:
            for client in sockets:
                client.close()


def test_browser_cannot_choose_report_or_files():
    with running(StubAssistant()) as (_, url):
        for body in [{"question": "science", "report": "secret.json"}, {"question": "science", "topK": True}, {"question": ""}]:
            status, error, _ = call(url, "/ask", body)
            assert status == 400 and error["code"] == "invalid_request"

def test_invalid_citation_response_is_distinct_from_insufficient_evidence():
    assistant = StubAssistant(lambda: {"status": "insufficient_evidence", "reason": "invalid_model_response"})
    with running(assistant) as (_, url):
        status, error, _ = call(url, "/ask", {"question": "science"})
        assert status == 502 and error["code"] == "invalid_response"


def test_cli_check_does_not_require_index_or_load_models(monkeypatch, capsys):
    from crater_assistant.__main__ import main
    from crater_assistant.ollama import Ollama
    monkeypatch.setattr(Ollama, "preflight", lambda self: {"modelStatus": "available", "gpuRequested": self.gpu})
    assert main(["--gpu", "check"]) == 0
    assert json.loads(capsys.readouterr().out) == {"modelStatus": "available", "gpuRequested": True}

def test_forbidden_post_replies_survive_repeated_windows_connections():
    with running(StubAssistant()) as (_, url):
        for _ in range(30):
            status, error, headers = call(url, "/ask", {"question": "forbidden"}, "https://evil.test")
            assert status == 403 and error["code"] == "forbidden"
            assert "Access-Control-Allow-Origin" not in headers

def test_live_capture_guard_tracks_changes_without_blocking_telemetry_replay():
    active = [True]
    assistant = StubAssistant()
    with running(assistant, capture_guard=lambda: active[0]) as (_, url):
        status, health, _ = call(url)
        assert status == 200 and health["inferenceState"] == "capture_blocked" and health["busy"]
        status, error, _ = call(url, "/ask", {"question": "science"})
        assert status == 429 and error["code"] == "busy" and assistant.calls == 0
        active[0] = False
        status, _, _ = call(url, "/ask", {"question": "science"})
        assert status == 200 and assistant.calls == 1


@pytest.mark.parametrize(("arguments", "blocked"), [
    (["python.exe", "-m", "crater_m1", "--video", "scene.mp4"], True),
    (["python.exe", "-m", "crater_m2", "--perception-video", "scene.mp4", "--device", "directml"], True),
    (["python.exe", "-m", "crater_m2", "--perception-video=scene.mp4"], True),
    (["crater-m2.exe", "--perception-video", "scene.mp4"], True),
    (["powershell.exe", "-File", "D:/repo/scripts/start-live.ps1"], True),
    (["python.exe", "-m", "crater_m2", "--input", "historical.jsonl"], False),
    (["python.exe", "-m", "crater_assistant", "serve"], False),
    (["python.exe", "-m", "pytest"], False),
])
def test_live_process_detection_distinguishes_m2_capture_and_replay(monkeypatch, arguments, blocked):
    from crater_assistant.server import live_capture_active
    process = SimpleNamespace(info={"name": arguments[0], "cmdline": arguments})
    monkeypatch.setattr("crater_assistant.server.psutil.process_iter", lambda *args, **kwargs: iter([process]))
    assert live_capture_active() is blocked


def test_process_guard_fails_closed_for_unreadable_python_process(monkeypatch):
    from crater_assistant.server import live_capture_active
    process = SimpleNamespace(info={"name": "python.exe", "cmdline": None})
    monkeypatch.setattr("crater_assistant.server.psutil.process_iter", lambda *args, **kwargs: iter([process]))
    assert live_capture_active()


def test_unexpected_backend_failure_has_predictable_error_state():
    def fail():
        raise RuntimeError("private source text must not reach the client")
    with running(StubAssistant(fail)) as (_, url):
        status, error, _ = call(url, "/ask", {"question": "science"})
        assert status == 500 and error["code"] == "failed"
        assert "private source" not in error["error"]
