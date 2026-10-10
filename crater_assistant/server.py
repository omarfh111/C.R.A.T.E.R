"""Loopback-only, serialized, bounded HTTP sidecar for a future M3 panel."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import sqlite3
from urllib.parse import urlsplit


def allowed_origin(origin):
    try:
        url = urlsplit(origin)
        return (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
                and not url.username and not url.password and not url.path and not url.query
                and not url.fragment and url.port in {5173, 4173})
    except ValueError:
        return False


def parse_question(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or not set(data) <= {"question", "topK"}:
        raise ValueError("Expected only question and optional topK")
    question, top_k = data.get("question"), data.get("topK", 4)
    if (not isinstance(question, str) or not question.strip() or len(question) > 2000
            or type(top_k) is not int or not 1 <= top_k <= 8):
        raise ValueError("question: 1..2000 characters; topK: 1..8")
    return question, top_k


def make_server(assistant, port=8766, report=None, *, experiences=None):
    if not 0 <= port <= 65535:
        raise ValueError("port must be 0..65535")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # Do not log user questions or document contents.

        def _trusted(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return host in {f"127.0.0.1:{port}", f"localhost:{port}"} and (origin is None or allowed_origin(origin))

        def _send(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            origin = self.headers.get("Origin")
            if origin and allowed_origin(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            paths = {"/ask", "/experience/events", "/experience/analyses"} if experiences else {"/ask"}
            self._send(200 if self._trusted() and self.path in paths else 403, {})

        def do_GET(self):
            if not self._trusted():
                self._send(403, {"error": "Untrusted Host or Origin"})
            elif self.path == "/health":
                data = {"status": "ready", "indexedChunks": len(assistant.index.chunks),
                                 "llm": assistant.backend.chat_model,
                                 "embedding": assistant.backend.embedding_model}
                if experiences:
                    data["experience"] = {"enabled": True, "workerAlive": experiences.thread.is_alive(),
                                          "imageInference": False, "capacity": experiences.capacity}
                self._send(200, data)
            elif experiences and self.path.startswith("/experience/"):
                try:
                    if self.path == "/experience/events":
                        self._send(200, {"events": experiences.journal.events()})
                    elif self.path.startswith("/experience/events/"):
                        self._send(200, experiences.journal.get_event(self.path.split("/")[-1]))
                    elif self.path.startswith("/experience/analyses/"):
                        self._send(200, experiences.job(self.path.split("/")[-1]))
                    else:
                        self._send(404, {"error": "Unknown endpoint"})
                except ValueError:
                    self._send(404, {"error": "Unknown experience identifier"})
                except (OSError, sqlite3.Error):
                    self._send(503, {"error": "Journal unavailable"})
            else:
                self._send(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if not self._trusted():
                self._send(403, {"error": "Untrusted Host or Origin"})
                return
            if self.path != "/ask" and not (experiences and self.path in {"/experience/events", "/experience/analyses"}):
                self._send(404, {"error": "Unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 65536 if self.path.startswith("/experience/") else 16384
                if not 1 <= length <= maximum or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Request body must be 1..16384 bytes with Content-Length")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected application/json")
                raw = self.rfile.read(length)
                if self.path != "/ask":
                    self._experience_post(json.loads(raw))
                    return
                question, top_k = parse_question(raw)
            except (ValueError, UnicodeError, TimeoutError) as exc:
                self._send(400, {"error": str(exc)})
                return
            try:
                if experiences and not experiences.model_lock.acquire(blocking=False):
                    self._send(429, {"error": "Local model busy; use asynchronous experience analyses"})
                    return
                try:
                    self._send(200, assistant.ask(question, top_k, report))
                finally:
                    if experiences:
                        experiences.model_lock.release()
            except (OSError, ValueError, KeyError, TypeError):
                self._send(503, {"error": "Assistant unavailable: check local models, source files and index"})

        def _experience_post(self, data):
            from .experience_analysis import QueueFull
            try:
                if self.path == "/experience/events":
                    if (not isinstance(data, dict) or not {"event"} <= set(data) <= {"event", "analyze"}
                            or type(data.get("analyze", False)) is not bool):
                        raise ValueError("Expected event and optional boolean analyze")
                    saved = experiences.journal.add_event(data["event"])
                    analysis = experiences.analyze(saved["eventId"]) if data.get("analyze") else None
                    self._send(201, {"event": saved, "analysis": analysis})
                else:
                    if (not isinstance(data, dict) or not {"eventId"} <= set(data) <= {"eventId", "retry"}
                            or type(data.get("retry", False)) is not bool):
                        raise ValueError("Expected eventId and optional boolean retry")
                    job = experiences.analyze(data["eventId"], data.get("retry", False))
                    self._send(202 if job["state"] in {"queued", "running"} else 200, job)
            except QueueFull:
                self._send(429, {"error": "Analysis queue full; any submitted event remains recorded"})
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
            except (OSError, sqlite3.Error, TypeError, KeyError):
                self._send(503, {"error": "Experience service unavailable"})

    server = (ThreadingHTTPServer if experiences else HTTPServer)(("127.0.0.1", port), Handler)
    port = server.server_port
    return server


def serve(assistant, port=8766, report=None, *, experiences=None):
    if not 1 <= port <= 65535:
        raise ValueError("port must be 1..65535")
    with make_server(assistant, port, report, experiences=experiences) as server:
        print(f"Assistant: http://127.0.0.1:{port} (read-only, separate from telemetry)", flush=True)
        server.serve_forever()
