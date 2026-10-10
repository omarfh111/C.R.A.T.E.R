import argparse
import json
import sys
import sqlite3

from .core import Assistant, Index, report_facts
from .ollama import Ollama
from .pdf import export_pdf
from .server import serve


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local document and M2-report assistant; no rover commands")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="embeddinggemma:300m")
    parser.add_argument("--llm", default="qwen3:4b-instruct-2507-q4_K_M")
    parser.add_argument("--gpu", action="store_true", help="Allow GPU use; CPU by default to leave VRAM for M1")
    parser.add_argument("--timeout", type=int, default=180)
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index", help="Embed explicitly selected Markdown/TXT/JSON files")
    index.add_argument("files", nargs="+")
    index.add_argument("--output", default="artifacts/assistant-index.json")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--index", default="artifacts/assistant-index.json")
    ask.add_argument("--top-k", type=int, default=4)
    ask.add_argument("--report", help="Optional M2 report; numeric facts computed before LLM")
    http = sub.add_parser("serve")
    http.add_argument("--index", default="artifacts/assistant-index.json")
    http.add_argument("--port", type=int, default=8766)
    http.add_argument("--report", help="Fixed report selected by server operator, not HTTP clients")
    http.add_argument("--journal", help="Enable local experience endpoints and background worker (SQLite)")
    http.add_argument("--media-root", help="Operator-selected directory containing referenced images")
    add = sub.add_parser("record-event", help="Record an explicit event JSON without running a model")
    add.add_argument("event")
    add.add_argument("--journal", required=True)
    add.add_argument("--media-root")
    review = sub.add_parser("review-event", help="Append a human review; never approve an LLM answer automatically")
    review.add_argument("event_id")
    review.add_argument("--journal", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--outcome", choices=("confirmed", "rejected", "inconclusive"), required=True)
    review.add_argument("--statement", required=True)
    review.add_argument("--evidence", nargs="+", default=[])
    export = sub.add_parser("export-experiences", help="Export latest confirmed human facts for explicit corpus selection")
    export.add_argument("--journal", required=True)
    export.add_argument("--output", required=True)
    dump = sub.add_parser("export-journal", help="Export observations, questions, analyses, attempts and reviews as JSONL")
    dump.add_argument("--journal", required=True)
    dump.add_argument("--output", required=True)
    facts = sub.add_parser("facts", help="Deterministic report analysis without any model")
    facts.add_argument("report")
    pdf = sub.add_parser("import-pdf", help="Extract PDF text with page references; optional assistant extra")
    pdf.add_argument("source")
    pdf.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"record-event", "review-event", "export-experiences", "export-journal"}:
            from pathlib import Path
            from .experience import Journal
            from .core import _read
            journal = Journal(args.journal, getattr(args, "media_root", None))
            if args.command == "record-event":
                print(json.dumps(journal.add_event(json.loads(_read(args.event)[0])), ensure_ascii=True))
            elif args.command == "review-event":
                print(json.dumps(journal.review(args.event_id, args.reviewer, args.outcome, args.statement, args.evidence), ensure_ascii=True))
            elif args.command == "export-journal":
                output = Path(args.output)
                if output.exists() or output.suffix.lower() != ".jsonl":
                    raise ValueError("Choose a new JSONL output")
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("x", encoding="utf-8") as target:
                    for record in journal.records():
                        target.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                print(json.dumps({"output": str(output), "rawUnverifiedAnalysesIncluded": True}))
            else:
                output = Path(args.output)
                text = journal.export_reviewed()
                if output.exists() or output.suffix.lower() != ".md" or not text or len(text.encode()) > 1_000_000:
                    raise ValueError("Choose a new Markdown output; confirmed evidence required, <=1 MB")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(text + "\n", encoding="utf-8")
                print(json.dumps({"output": str(output), "automaticIndexing": False}))
            return 0
        if args.command == "import-pdf":
            pages = export_pdf(args.source, args.output)
            print(json.dumps({"pages": pages, "output": args.output}))
            return 0
        if args.command == "facts":
            print(json.dumps(report_facts(args.report), ensure_ascii=False, indent=2))
            return 0
        backend = Ollama(args.ollama_url, args.embedding_model, args.llm, args.timeout, args.gpu)
        if args.command == "index":
            index = Index.build(args.files, backend)
            index.save(args.output)
            print(json.dumps({"index": args.output, "chunks": len(index.chunks), "model": index.model}))
        else:
            assistant = Assistant(Index.load(args.index, backend), backend)
            if args.command == "ask":
                print(json.dumps(assistant.ask(args.question, args.top_k, args.report), ensure_ascii=False, indent=2))
            else:
                if args.report:
                    report_facts(args.report)
                if args.media_root and not args.journal:
                    raise ValueError("media-root requires journal")
                if args.journal:
                    from .experience import Journal
                    from .experience_analysis import ExperienceService
                    with ExperienceService(assistant, Journal(args.journal, args.media_root)) as experiences:
                        serve(assistant, args.port, args.report, experiences=experiences)
                else:
                    serve(assistant, args.port, args.report)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(f"Assistant error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
