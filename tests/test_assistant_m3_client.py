"""Actual HTTP + TypeScript adapter; deterministic backend, not an LLM benchmark."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

from crater_assistant.core import Assistant, Index
from crater_assistant.server import make_server


def test_typescript_adapter_uses_actual_assistant_http(tmp_path):
    node = os.environ.get("CRATER_NODE") or shutil.which("node")
    if not node:
        pytest.skip("Node >=22.18 required for TypeScript adapter")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    if tuple(map(int, version.split(".")[:2])) < (22, 18):
        pytest.skip("Node >=22.18 required for TypeScript adapter")
    class Backend:
        embedding_model = "unit-embedding"
        chat_model = "unit-llm"
        def embed(self, texts, **kwargs): return [[1, 0] for _ in texts]
        def chat(self, question, evidence):
            if "inconnue" in question:
                return dict(answer="INSUFFICIENT_EVIDENCE", sourceIds=[], insufficientEvidence=True)
            return dict(answer="Images espacees en distance [S1].", sourceIds=["S1"], insufficientEvidence=False)
    doc = tmp_path / "nasa.md"
    doc.write_text("Source URL: https://science.nasa.gov/resource/example/\nVerified on: 2026-10-10\nImages espacees.", encoding="utf-8")
    assistant = Assistant(Index.build([doc], Backend()), Backend())
    server = make_server(assistant, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    module = (Path(__file__).resolve().parent.parent / "integrations/m3-assistant-client.ts").as_uri()
    code = """
import { createAssistantClient } from MODULE;
import assert from 'node:assert/strict';
const client = createAssistantClient({baseUrl: process.argv[1]});
assert.equal((await client.health()).indexedChunks, 1);
const result = await client.ask('Cadence ?', 1);
assert.equal(result.status, 'answered');
assert.deepEqual(result.citedSourceIds, ['S1']);
assert.equal(result.sources[0].sourceUrl, 'https://science.nasa.gov/resource/example/');
assert.equal((await client.ask('Temperature inconnue')).status, 'insufficient_evidence');
""".replace("MODULE", json.dumps(module))
    try:
        subprocess.run([node, "--input-type=module", "-e", code,
                        f"http://127.0.0.1:{server.server_port}"], check=True, timeout=20)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
