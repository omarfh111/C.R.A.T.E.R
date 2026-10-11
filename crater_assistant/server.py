"""Loopback-only, serialized, bounded HTTP sidecar for a future M3 panel."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# Every origin the local M3 dev server or its preview can present, as exact literals.
ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173",
                   "http://localhost:4173", "http://127.0.0.1:4173", "http://[::1]:4173")


def allowed_origin(origin):
    """True only for an exact local dev-server origin.

    Compared as whole strings rather than parsed and inspected: urlsplit() removes ASCII tabs
    and newlines before parsing, so a folded Origin header carrying CR, LF or TAB inside the
    port satisfied every parsed check and was then echoed verbatim into
    Access-Control-Allow-Origin, putting attacker-controlled CRLF in the response headers.
    """
    return origin in ALLOWED_ORIGINS


def echoable_origin(origin):
    """The matching literal from ALLOWED_ORIGINS, or None.

    Returns a value from this module, never the request's own bytes, so no header the client
    sent can reach a response header even if the comparison above is later loosened.
    """
    return next((allowed for allowed in ALLOWED_ORIGINS if allowed == origin), None)


def parse_question(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or not set(data) <= {"question", "topK"}:
        raise ValueError("Expected only question and optional topK")
    question, top_k = data.get("question"), data.get("topK", 4)
    if (not isinstance(question, str) or not question.strip() or len(question) > 2000
            or type(top_k) is not int or not 1 <= top_k <= 8):
        raise ValueError("question: 1..2000 characters; topK: 1..8")
    return question, top_k


def make_server(assistant, port=8766, report=None):
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
            origin = echoable_origin(self.headers.get("Origin"))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send(200 if self._trusted() and self.path == "/ask" else 403, {})

        def do_GET(self):
            if not self._trusted():
                self._send(403, {"error": "Untrusted Host or Origin"})
            elif self.path == "/health":
                self._send(200, {"status": "ready", "indexedChunks": len(assistant.index.chunks),
                                 "llm": assistant.backend.chat_model,
                                 "embedding": assistant.backend.embedding_model})
            else:
                self._send(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if not self._trusted():
                self._send(403, {"error": "Untrusted Host or Origin"})
                return
            if self.path != "/ask":
                self._send(404, {"error": "Unknown endpoint"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 16384 or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Request body must be 1..16384 bytes with Content-Length")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected application/json")
                question, top_k = parse_question(self.rfile.read(length))
            except (ValueError, UnicodeError, TimeoutError) as exc:
                self._send(400, {"error": str(exc)})
                return
            try:
                self._send(200, assistant.ask(question, top_k, report))
            except (OSError, ValueError, KeyError, TypeError):
                self._send(503, {"error": "Assistant unavailable: check local models, source files and index"})

    server = HTTPServer(("127.0.0.1", port), Handler)
    port = server.server_port
    return server


def serve(assistant, port=8766, report=None):
    if not 1 <= port <= 65535:
        raise ValueError("port must be 1..65535")
    with make_server(assistant, port, report) as server:
        print(f"Assistant: http://127.0.0.1:{port} (read-only, separate from telemetry)", flush=True)
        server.serve_forever()
