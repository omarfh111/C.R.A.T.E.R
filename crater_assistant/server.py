"""Bounded, loopback-only read-only HTTP service, separate from telemetry."""

from contextlib import nullcontext
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import math
import socket
import sqlite3
from socketserver import ThreadingMixIn
import threading
from urllib.parse import urlsplit

import psutil

from .ollama import AssistantInvalidResponse, AssistantTimeout, AssistantUnavailable

DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173")


def live_capture_active():
    """Conservative process guard; operational sequencing remains required."""
    try:
        for process in psutil.process_iter(["name", "cmdline"], ad_value=None):
            info = process.info
            name = (info.get("name") or "").lower()
            arguments = info.get("cmdline")
            if arguments is None:
                if name.startswith("python") or name in {"crater-m1", "crater-m1.exe"}:
                    return True  # Cannot establish that an inaccessible Python process is safe.
                continue
            normalized = [str(argument).lower().replace("\\", "/") for argument in arguments]
            m2_live = any(value in {"crater_m2", "crater_m2.__main__", "crater-m2", "crater-m2.exe"}
                          or value.rsplit("/", 1)[-1] in {"crater-m2", "crater-m2.exe", "crater-m2-script.py"}
                          for value in normalized)
            if m2_live and any(value == "--perception-video" or value.startswith("--perception-video=") for value in normalized):
                return True  # M1 normally executes inside the M2 live-perception producer.
            for index, argument in enumerate(arguments):
                value = str(argument).lower().replace("\\", "/")
                basename = value.rsplit("/", 1)[-1]
                if (basename in {"crater-m1", "crater-m1.exe", "crater-m1-script.py", "start-live.ps1"}
                        or (index and arguments[index - 1] == "-m" and value in {"crater_m1", "crater_m1.cli"})
                        or value.endswith("/crater_m1/__main__.py")):
                    return True
        return False
    except (psutil.Error, OSError):
        return True  # Fail closed when process inspection is unavailable.


def validate_origin(origin):
    """An explicit exact HTTP loopback origin; never a wildcard or URL path."""
    try:
        url = urlsplit(origin)
        return (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
                and url.username is None and url.password is None and not url.path and not url.query
                and not url.fragment and url.port is not None and 1 <= url.port <= 65535
                and origin == f"http://{'[' + url.hostname + ']' if ':' in url.hostname else url.hostname}:{url.port}")
    except (TypeError, ValueError):
        return False


def allowed_origin(origin, origins=DEFAULT_ORIGINS):
    return validate_origin(origin) and origin in origins


def parse_question(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or not set(data) <= {"question", "topK"}:
        raise ValueError("Expected only question and optional topK")
    question, top_k = data.get("question"), data.get("topK", 4)
    if (not isinstance(question, str) or not question.strip() or len(question) > 2000
            or type(top_k) is not int or not 1 <= top_k <= 8):
        raise ValueError("question: 1..2000 characters; topK: 1..8")
    return question, top_k


class _BoundedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, address, handler, max_connections):
        self._connections = threading.BoundedSemaphore(max_connections)
        self.inference_lock = threading.Lock()
        self.timeout_quarantine = False
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            # Load shed without creating an additional request thread or queue.
            body = b'{"code":"busy","error":"HTTP connection capacity reached"}'
            try:
                request.settimeout(0.05)
                try:
                    request.recv(16384)  # Drain a bounded initial request; avoid Windows reset discarding the reply.
                except OSError:
                    pass
                request.settimeout(0.25)
                request.sendall(b"HTTP/1.0 429 Too Many Requests\r\nContent-Type: application/json\r\n"
                                b"Cache-Control: no-store\r\nConnection: close\r\nContent-Length: "
                                + str(len(body)).encode() + b"\r\n\r\n" + body)
                request.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


def make_server(assistant, port=8766, report=None, *, allowed_origins=DEFAULT_ORIGINS,
                request_timeout=None, max_connections=8, capture_guard=None, journal=None, worker=None):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port must be 0..65535")
    origins = frozenset(allowed_origins)
    if any(not validate_origin(origin) for origin in origins):
        raise ValueError("Every allowed origin must be an exact HTTP loopback origin with a port")
    budget = request_timeout if request_timeout is not None else getattr(getattr(assistant, "backend", None), "timeout", 180)
    if type(budget) not in (int, float) or not 0 < budget <= 600 or not math.isfinite(budget):
        raise ValueError("request_timeout must be >0..600 seconds")
    if type(max_connections) is not int or not 2 <= max_connections <= 32:
        raise ValueError("max_connections must be 2..32")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
            self._body_consumed = False

        def log_message(self, *args):
            pass  # Never log questions, source text or operator document paths.

        def _trusted(self):
            hosts = self.headers.get_all("Host", [])
            origin_headers = self.headers.get_all("Origin", [])
            host = hosts[0] if len(hosts) == 1 else ""
            origin = origin_headers[0] if len(origin_headers) == 1 else None
            return (len(origin_headers) <= 1 and host in {f"127.0.0.1:{port}", f"localhost:{port}"}
                    and (origin is None or allowed_origin(origin, origins)))

        def _send(self, status, data):
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                origin = self.headers.get("Origin")
                if origin and allowed_origin(origin, origins):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type")
                if status == 429:
                    self.send_header("Retry-After", "2")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass  # Client cancellation does not release the model admission lock early.

        def _error(self, status, code, message):
            if self.command == "POST" and not self._body_consumed:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) == 1 and len(lengths[0]) <= 5 and lengths[0].isdigit() and 0 < int(lengths[0]) <= 16384:
                    try:
                        self.connection.settimeout(0.2)
                        self.rfile.read(int(lengths[0]))
                    except OSError:
                        pass
                    finally:
                        self.connection.settimeout(5)
            self._send(status, {"code": code, "error": message})

        def do_OPTIONS(self):
            requested_method = self.headers.get("Access-Control-Request-Method", "POST")
            requested_headers = self.headers.get("Access-Control-Request-Headers", "content-type")
            if (self._trusted() and self.path in {"/ask", "/health", "/incidents", "/sessions", "/jobs/retry", "/jobs/cancel", "/reviews", "/analyze-incident"} and requested_method in {"GET", "POST"}
                    and all(h.strip().lower() == "content-type" for h in requested_headers.split(","))):
                self._send(200, {})
            else:
                self._error(403, "forbidden", "Untrusted preflight")

        def do_GET(self):
            if not self._trusted():
                self._error(403, "forbidden", "Untrusted Host or Origin")
            elif journal is not None and self.path in {"/incidents", "/sessions"}:
                try:
                    self._send(200, {"incidents": journal.list()} if self.path == "/incidents" else {"sessions": journal.sessions()})
                except (OSError, sqlite3.Error):
                    self._error(503, "unavailable", "Journal unavailable")
            elif self.path == "/health" and assistant is None:
                self._send(200, {"httpReady": True, "collectorReady": True, "workerError": getattr(worker, "error", None),
                                 "limitations": "Collection does not require Ollama. Analysis requires explicit producer capture completion."})
            elif self.path == "/health":
                capture_blocked = capture_guard is not None and capture_guard()
                self._send(200, {"status": "ready", "httpReady": True,
                    "modelStatus": getattr(assistant.backend, "model_status", "unchecked"),
                    "busy": self.server.inference_lock.locked() or self.server.timeout_quarantine or capture_blocked,
                    "inferenceState": "timeout_requires_restart" if self.server.timeout_quarantine else
                        ("running" if self.server.inference_lock.locked() else ("capture_blocked" if capture_blocked else "idle")),
                    "indexedChunks": len(assistant.index.chunks),
                    "llm": assistant.backend.chat_model, "embedding": assistant.backend.embedding_model})
            else:
                self._error(404, "not_found", "Unknown endpoint")

        def do_POST(self):
            if not self._trusted():
                self._error(403, "forbidden", "Untrusted Host or Origin")
                return
            if self.path not in {"/ask", "/incidents", "/jobs/retry", "/jobs/cancel", "/reviews", "/analyze-incident"}:
                self._error(404, "not_found", "Unknown endpoint")
                return
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or len(lengths[0]) > 5 or not lengths[0].isdigit() or self.headers.get("Transfer-Encoding"):
                    raise ValueError("One valid Content-Length is required; chunked bodies are refused")
                length = int(lengths[0])
                if not 1 <= length <= 16384:
                    raise ValueError("Request body must be 1..16384 bytes")
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise ValueError("Expected application/json")
                body = self.rfile.read(length)
                self._body_consumed = True
                if len(body) != length:
                    raise ValueError("Incomplete request body")
                incident = None
                if self.path == "/ask":
                    question, top_k = parse_question(body)
                else:
                    data = json.loads(body)
                    if journal is None or not isinstance(data, dict):
                        raise ValueError("Journal not configured")
                    if self.path == "/incidents":
                        self._send(200, journal.record(data)); return
                    if self.path in {"/jobs/retry", "/jobs/cancel", "/analyze-incident"}:
                        if set(data) != {"eventId"}:
                            raise ValueError("Only eventId allowed")
                        incident = journal.get(data["eventId"])
                        if self.path != "/analyze-incident":
                            (journal.retry if self.path == "/jobs/retry" else journal.cancel)(data["eventId"])
                            self._send(200, {"ok": True}); return
                        session = journal.session(incident["sessionId"])
                        if session is None or session["phase"] == "capturing":
                            self._error(429, "busy", "Explicit producer capture completion required"); return
                        question, top_k = incident["question"], 3
                    elif self.path == "/reviews":
                        if set(data) != {"eventId", "verdict", "note"}:
                            raise ValueError("Expected review fields")
                        self._send(200, journal.review(**dict(event_id=data["eventId"], verdict=data["verdict"], note=data["note"]))); return
            except sqlite3.Error:
                self._error(503, "unavailable", "Journal busy or unavailable"); return
            except (ValueError, UnicodeError, OSError, KeyError, TypeError):
                self._error(400, "invalid_request", "Expected bounded JSON question and optional topK")
                return
            if assistant is None:
                self._error(503, "unavailable", "Collector has no model engine"); return
            if capture_guard is not None and capture_guard():
                self._error(429, "busy", "Live M1 capture is active or cannot be excluded; ask after capture finishes")
                return
            if self.server.timeout_quarantine:
                self._error(429, "busy", "Previous inference timed out; verify/unload Ollama and restart the sidecar")
                return
            if not self.server.inference_lock.acquire(blocking=False):
                self._error(429, "busy", "An assistant request is already running; retry after it completes")
                return
            try:
                request_budget = getattr(assistant.backend, "request_budget", None)
                with request_budget(budget) if request_budget else nullcontext():
                    if incident is None:
                        result = assistant.ask(question, top_k, report)
                    else:
                        context = {key: incident[key] for key in ("kind", "summary", "provenance")}
                        result = assistant.ask(question, top_k, context=context)
                if result.get("reason") == "invalid_model_response":
                    raise AssistantInvalidResponse("Generated answer failed citation or response validation")
                self._send(200, result)
            except (AssistantTimeout, TimeoutError):
                self.server.timeout_quarantine = True
                self._error(504, "timeout", "Assistant deadline exceeded; model termination is not guaranteed")
            except (AssistantUnavailable, OSError):
                if hasattr(assistant.backend, "model_status"):
                    assistant.backend.model_status = "unavailable"
                self._error(503, "unavailable", "Local assistant unavailable; check Ollama and installed models")
            except (AssistantInvalidResponse, ValueError, KeyError, TypeError):
                self._error(502, "invalid_response", "Assistant output or evidence failed validation; rebuild/check the local index")
            except Exception:
                self._error(500, "failed", "Assistant request failed; inspect the local service without exposing document contents")
            finally:
                self.server.inference_lock.release()

    server = _BoundedHTTPServer(("127.0.0.1", port), Handler, max_connections)
    port = server.server_port
    return server


def serve(assistant, port=8766, report=None, *, allowed_origins=DEFAULT_ORIGINS, request_timeout=None, capture_guard=None, journal=None):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be 1..65535")
    with make_server(assistant, port, report, allowed_origins=allowed_origins, request_timeout=request_timeout, capture_guard=capture_guard, journal=journal) as server:
        print(f"Assistant: http://127.0.0.1:{port} (read-only, separate from telemetry)", flush=True)
        print("Only operator-triggered inference; client cancellation does not guarantee model termination.", flush=True)
        server.serve_forever()
