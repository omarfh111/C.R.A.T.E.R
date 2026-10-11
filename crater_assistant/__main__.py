import argparse
import json
import sys

from .core import Assistant, Index, report_facts
from .ollama import Ollama
from .pdf import export_pdf
from .server import DEFAULT_ORIGINS, live_capture_active, serve, validate_origin


def main(argv=None):
    parser = argparse.ArgumentParser(description="Optional local science assistant; no rover commands")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="embeddinggemma:300m")
    parser.add_argument("--llm", default="qwen3:4b-instruct-2507-q4_K_M")
    parser.add_argument("--gpu", action="store_true", help="Operator-selected GPU offload; validate coexistence before use during capture")
    parser.add_argument("--timeout", type=int, default=180, help="Aggregate question deadline in seconds")
    parser.add_argument("--keep-alive", type=int, default=0, help="Keep model loaded 0..600 seconds; 0 unloads after each call")
    parser.add_argument("--num-ctx", type=int, default=8192, help="Context budget 1024..16384 tokens")
    parser.add_argument("--num-predict", type=int, default=600, help="Output budget 64..1024 tokens")
    parser.add_argument("--num-thread", type=int, help="Optional CPU thread limit 1..64")
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
    http.add_argument("--journal", help="Fixed incident database; event IDs only over HTTP")
    http.add_argument("--report", help="Fixed report selected by server operator, never HTTP clients")
    http.add_argument("--allow-origin", action="append", help="Exact HTTP loopback dashboard origin; repeat for additional origins. Replaces fixed development defaults.")
    http.add_argument("--block-live-m1", action="store_true", help="Refuse questions while a live M1 Python process is detected; still sequence inference after capture")
    sub.add_parser("check", help="Check installed model metadata without loading, generating or downloading")
    sub.add_parser("warm", help="Explicitly preload the selected model; use a nonzero --keep-alive")
    sub.add_parser("unload", help="Explicitly unload the selected local models")
    facts = sub.add_parser("facts", help="Deterministic report analysis without any model")
    facts.add_argument("report")
    pdf = sub.add_parser("import-pdf", help="Extract PDF text with page references; optional assistant extra")
    pdf.add_argument("source")
    pdf.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "import-pdf":
            pages = export_pdf(args.source, args.output)
            print(json.dumps({"pages": pages, "output": args.output}))
            return 0
        if args.command == "facts":
            print(json.dumps(report_facts(args.report), ensure_ascii=False, indent=2))
            return 0
        backend = Ollama(args.ollama_url, args.embedding_model, args.llm, args.timeout, args.gpu,
                         args.keep_alive, args.num_ctx, args.num_predict, args.num_thread)
        if args.command == "check":
            print(json.dumps(backend.preflight(), ensure_ascii=False, indent=2))
        elif args.command == "warm":
            if not args.keep_alive:
                raise ValueError("warm requires --keep-alive greater than zero")
            backend.preflight()
            backend.warm()
            print(json.dumps({"status": "loaded", "llm": backend.chat_model, "keepAliveS": backend.keep_alive}))
        elif args.command == "unload":
            backend.unload()
            print(json.dumps({"status": "unloaded"}))
        elif args.command == "index":
            index = Index.build(args.files, backend)
            index.save(args.output)
            print(json.dumps({"index": args.output, "chunks": len(index.chunks), "model": index.model}))
        else:
            assistant = Assistant(Index.load(args.index, backend), backend)
            if args.command == "ask":
                with backend.request_budget():
                    result = assistant.ask(args.question, args.top_k, args.report)
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                origins = args.allow_origin if args.allow_origin is not None else DEFAULT_ORIGINS
                if any(not validate_origin(origin) for origin in origins):
                    raise ValueError("--allow-origin requires an exact loopback HTTP origin with a port")
                if args.report:
                    report_facts(args.report)
                try:
                    backend.preflight()
                except (OSError, ValueError):
                    print("Local model prerequisites unavailable; HTTP service will still start.", file=sys.stderr)
                from .experience import Journal
                journal = Journal(args.journal) if args.journal else None
                serve(assistant, args.port, args.report, allowed_origins=origins, request_timeout=args.timeout,
                      capture_guard=live_capture_active if args.block_live_m1 or journal else None, journal=journal)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Assistant error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
