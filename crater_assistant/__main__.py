import argparse
import json
import sys

from .core import Assistant, Index, report_facts
from .ollama import Ollama
from .pdf import export_pdf
from .server import serve


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local document and M2-report assistant; no rover commands")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="embeddinggemma:300m")
    parser.add_argument("--llm", default="qwen3:4b")
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
                serve(assistant, args.port, args.report)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Assistant error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
