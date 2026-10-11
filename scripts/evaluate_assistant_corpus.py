"""Opt-in real local embedding evaluation; does not call the LLM or any source URL."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from crater_assistant.core import Index
from crater_assistant.ollama import Ollama


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="artifacts/assistant-research-index.json")
    parser.add_argument("--output", default="artifacts/assistant-corpus-retrieval.json")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("Choose a new output path; existing evidence is not overwritten")
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/knowledge/corpus.json").read_text(encoding="utf-8"))
    backend = Ollama()
    index = Index.load(args.index, backend)
    selected = {str((root / path).resolve()) for path in manifest["files"]}
    if {chunk["path"] for chunk in index.chunks} != selected:
        parser.error("Index sources do not match the reviewed manifest; rebuild it")
    results = []
    for case in manifest["retrievalCases"]:
        start = perf_counter()
        hits = index.search(case["question"], backend, top_k=4)
        returned = [{"file": Path(hit["path"]).relative_to(root).as_posix(),
                     "score": hit["score"], "digest": hit["digest"],
                     "sourceUrl": hit.get("sourceUrl"), "verifiedOn": hit.get("verifiedOn")}
                    for hit in hits]
        rank = next((i for i, hit in enumerate(returned, 1) if hit["file"] == case["expectedFile"]), None)
        results.append(dict(case, rankInTop4=rank, seconds=round(perf_counter() - start, 3), hits=returned))
    report = {"validatedAt": datetime.now(timezone.utc).isoformat(),
              "embeddingModel": index.model, "embeddingIdentity": index.identity,
              "indexedChunks": len(index.chunks), "selectedDocuments": len(selected),
              "cases": len(results), "hitsAt4": sum(r["rankInTop4"] is not None for r in results),
              "top1": sum(r["rankInTop4"] == 1 for r in results), "results": results,
              "limitations": "Prepared corpus probes, not unseen-query accuracy or LLM factual validation. CPU, local Ollama; no source URL fetched."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("cases", "hitsAt4", "top1", "indexedChunks")}))
    return 0 if report["hitsAt4"] == report["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
