"""Explicit local corpus, cosine retrieval and source-checked explanations."""

import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

MAX_FILE_BYTES = 1_000_000
MAX_CHUNKS = 1000
CHUNK_CHARS = 1000


def _validate_source_metadata(url, verified):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or not (host == "nasa.gov" or host.endswith(".nasa.gov"))
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or any(c.isspace() for c in url) or date.fromisoformat(verified).isoformat() != verified):
            raise ValueError("invalid metadata")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid official source URL or verification date") from exc


def _source_metadata(text):
    urls = re.findall(r"^Source URL: (.+)$", text, flags=re.MULTILINE)
    dates = re.findall(r"^Verified on: (.+)$", text, flags=re.MULTILINE)
    if not urls and not dates:
        return {}
    if len(urls) != 1 or len(dates) != 1:
        raise ValueError("Expected one official source URL and verification date")
    url, verified = urls[0].strip(), dates[0].strip()
    _validate_source_metadata(url, verified)
    return dict(sourceUrl=url, verifiedOn=verified)


def _nonnegative_number(value):
    # Bound integers before float conversion; JSON giant integers must fail
    # validation, rather than crash the CLI/server with OverflowError.
    return (type(value) in (int, float) and 0 <= value <= 1e100 and math.isfinite(value))


def _read(path):
    path = Path(path).resolve()
    if (not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}
            or path.name.startswith(".") or path.stat().st_size > MAX_FILE_BYTES):
        raise ValueError(f"Expected explicit Markdown/TXT/JSON file <=1 MB: {path.name}")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Source file exceeds size limit")
    return raw.decode("utf-8-sig"), hashlib.sha256(raw).hexdigest()


def chunks_from_files(paths):
    chunks = []
    for path in dict.fromkeys(str(Path(p).resolve()) for p in paths):
        text, digest = _read(path)
        metadata = _source_metadata(text)
        first_chunk = len(chunks)
        if not text.strip():
            raise ValueError(f"Source is empty: {path}")
        buffer = ""
        start = 1
        end = 1
        # Split oversized individual lines; preserve their original line number.
        for line_number, line in enumerate(text.splitlines(), 1):
            for offset in range(0, max(1, len(line)), CHUNK_CHARS):
                piece = line[offset:offset + CHUNK_CHARS] + "\n"
                if buffer and len(buffer) + len(piece) > CHUNK_CHARS:
                    chunks.append({"path": path, "lineStart": start, "lineEnd": end,
                                   "digest": digest, "text": buffer.strip()})
                    if len(chunks) > MAX_CHUNKS:
                        raise ValueError("Corpus exceeds 1000 chunks; select fewer documents")
                    buffer = ""
                if not buffer:
                    start = line_number
                buffer += piece
                end = line_number
        if buffer.strip():
            chunks.append({"path": path, "lineStart": start, "lineEnd": end,
                           "digest": digest, "text": buffer.strip()})
        for chunk in chunks[first_chunk:]:
            chunk.update(metadata)
        if len(chunks) > MAX_CHUNKS:
            raise ValueError("Corpus exceeds 1000 chunks; select fewer documents")
    return chunks


def _normalize(vectors, expected=None):
    try:
        if any(type(x) not in (int, float) for row in vectors for x in row):
            raise ValueError("Non-numeric embedding")
        array = np.asarray(vectors, dtype=np.float64)
        if array.ndim != 2 or not 1 <= array.shape[1] <= 16384 or not np.isfinite(array).all():
            raise ValueError("Invalid embeddings")
        if expected is not None and array.shape[0] != expected:
            raise ValueError("Embedding count mismatch")
        # Stable normalization avoids norm overflow with otherwise finite values.
        scales = np.max(np.abs(array), axis=1, keepdims=True)
        if (scales == 0).any():
            raise ValueError("Zero embedding")
        array = array / scales
        return array / np.linalg.norm(array, axis=1, keepdims=True)
    except (TypeError, OverflowError) as exc:
        raise ValueError("Invalid embeddings") from exc


class Index:
    def __init__(self, chunks, vectors, model, identity=None):
        self.chunks = chunks
        self.model = model
        self.identity = identity
        self.vectors = (_normalize(vectors, len(chunks)) if chunks or vectors
                        else np.empty((0, 0), dtype=np.float64))
        if len(chunks) > MAX_CHUNKS:
            raise ValueError("Too many chunks")
        for chunk in chunks:
            if (not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str)
                    or len(chunk["text"]) > CHUNK_CHARS + 1
                    or not isinstance(chunk.get("path"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", chunk.get("digest", ""))
                    or type(chunk.get("lineStart")) is not int or type(chunk.get("lineEnd")) is not int
                    or not 1 <= chunk["lineStart"] <= chunk["lineEnd"]):
                raise ValueError("Invalid index chunk")
            if "sourceUrl" in chunk or "verifiedOn" in chunk:
                _validate_source_metadata(chunk.get("sourceUrl"), chunk.get("verifiedOn"))

    @classmethod
    def build(cls, paths, backend):
        chunks = chunks_from_files(paths)
        vectors = []
        for offset in range(0, len(chunks), 16):
            vectors.extend(backend.embed([c["text"] for c in chunks[offset:offset + 16]]))
        identity = backend.embedding_identity() if hasattr(backend, "embedding_identity") else None
        return cls(chunks, vectors, backend.embedding_model, identity)

    def save(self, path):
        path = Path(path)
        if path.resolve() in {Path(c["path"]).resolve() for c in self.chunks}:
            raise ValueError("Index cannot overwrite a source")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": 1, "embeddingModel": self.model, "embeddingIdentity": self.identity,
                                    "chunks": self.chunks, "vectors": self.vectors.tolist()}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path, backend):
        path = Path(path)
        if path.stat().st_size > 64_000_000:
            raise ValueError("Index exceeds size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schemaVersion") != 1 or data.get("embeddingModel") != backend.embedding_model:
            raise ValueError("Index version/model mismatch; rebuild index")
        return cls(data["chunks"], data["vectors"], data["embeddingModel"], data.get("embeddingIdentity"))

    def search(self, question, backend, top_k=4):
        if not 1 <= top_k <= 8:
            raise ValueError("top_k must be 1..8")
        if self.model != backend.embedding_model:
            raise ValueError("Embedding model mismatch; rebuild index")
        if not self.chunks:
            return []
        if self.identity is not None and (not hasattr(backend, "embedding_identity")
                or self.identity != backend.embedding_identity()):
            raise ValueError("Embedding weights changed; rebuild index")
        for path, digest in {(c["path"], c["digest"]) for c in self.chunks}:
            if _read(path)[1] != digest:
                raise ValueError("Source changed; rebuild index")
        query = _normalize(backend.embed([question], query=True), 1)
        if query.shape[1] != self.vectors.shape[1]:
            raise ValueError("Embedding dimension changed; rebuild index")
        scores = self.vectors @ query[0]
        order = np.argsort(-scores, kind="stable")[:top_k]
        return [dict(self.chunks[int(i)], sourceId=f"S{n}", score=float(scores[i]))
                for n, i in enumerate(order, 1)]


def report_facts(path):
    text, _ = _read(path)
    return _report_facts_from_text(text)


def _report_facts_from_text(text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a M2 report object")
    transport = data.get("transport")
    if not isinstance(transport, dict):
        raise ValueError("Expected a M2 report with transport metrics")
    result = {"mode": data.get("mode"), "completed": data.get("completed")}
    source = data.get("source", {})
    if not isinstance(source, dict):
        raise ValueError("Invalid report source")
    result["source"] = {"source": source.get("source")}
    for key in ("meanLocalizationErrorM", "maxLocalizationErrorM"):
        value = source.get(key)
        if value is not None:
            if not _nonnegative_number(value):
                raise ValueError(f"Invalid spatial metric: {key}")
            result["source"][key] = value
    value = data.get("maxDeliveredLocalizationErrorM")
    if value is not None:
        if not _nonnegative_number(value):
            raise ValueError("Invalid delivered localization error")
        result["maxDeliveredLocalizationErrorM"] = value
    for key in ("generated", "delivered", "acknowledged", "pending", "queueDropped", "abandoned",
                "dataPacketsSent", "dataPacketsLost", "ackPacketsSent", "ackPacketsLost", "retransmissions",
                "totalBytesSent", "meanDeliveryLatencyS", "maxDeliveryLatencyS"):
        value = transport.get(key)
        if value is not None:
            if not _nonnegative_number(value):
                raise ValueError(f"Invalid report metric: {key}")
            if not key.endswith("LatencyS") and type(value) is not int:
                raise ValueError(f"Expected integer count: {key}")
            result[key] = value
    for numerator, denominator, name in (("delivered", "generated", "deliveryRate"),
            ("dataPacketsLost", "dataPacketsSent", "dataPacketLossRate"),
            ("ackPacketsLost", "ackPacketsSent", "ackPacketLossRate")):
        n, d = result.get(numerator), result.get(denominator)
        if n is not None and d is not None:
            if n > d:
                raise ValueError(f"Inconsistent report counts: {numerator}")
            result[name] = n / d if d else None
    return result


class Assistant:
    def __init__(self, index, backend):
        self.index = index
        self.backend = backend

    def ask(self, question, top_k=4, report=None):
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("Question must contain 1..2000 characters")
        sources = self.index.search(question, self.backend, top_k)
        facts = None
        if report:
            text, digest = _read(report)
            facts = _report_facts_from_text(text)
            sources.append({"sourceId": f"S{len(sources) + 1}", "path": str(Path(report).resolve()),
                            "lineStart": 1, "lineEnd": len(text.splitlines()),
                            "digest": digest, "score": None, "text": json.dumps(facts, ensure_ascii=False)})
        result = {"status": "insufficient_evidence", "answer": "Les sources disponibles ne permettent pas de répondre.",
                  "sources": sources, "citedSourceIds": [], "facts": facts,
                  "models": {"embedding": self.backend.embedding_model, "llm": self.backend.chat_model},
                  "roles": ["retriever", "report_analyst", "explainer", "citation_verifier"],
                  "limitations": "Les citations sont vérifiées, pas la vérité de chaque phrase. Aucun contrôle du rover."}
        if not sources:
            return result
        answer = self.backend.chat(question, sources)
        known = {s["sourceId"] for s in sources}
        if (not isinstance(answer, dict) or type(answer.get("insufficientEvidence")) is not bool
                or answer["insufficientEvidence"] or not isinstance(answer.get("answer"), str)
                or not answer["answer"].strip() or len(answer["answer"]) > 8000
                or not isinstance(answer.get("sourceIds"), list) or not answer["sourceIds"]
                or any(not isinstance(s, str) or s not in known for s in answer["sourceIds"])):
            return result
        mentions = set(re.findall(r"\[(S\d+)\]", answer["answer"]))
        if not mentions or mentions != set(answer["sourceIds"]):
            return result
        result.update(status="answered", answer=answer["answer"], citedSourceIds=answer["sourceIds"])
        return result
