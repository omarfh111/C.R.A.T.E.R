"""Report a `pip-audit --format json` result and apply an explicit blocking policy.

    pip-audit --format json ... > audit.json
    python scripts/summarize-pip-audit.py audit.json --label "core runtime" --gate fixable \
        --summary "$GITHUB_STEP_SUMMARY"

Policies:

  fixable   block on advisories that have a fixed release available, because those are the ones
            a maintainer can act on today. An advisory with no fix is still reported.
  advisory  never block. Used for the opt-in extras: the full live-AI path (PyTorch,
            Transformers) and the local ONNX group are not installed by the model-free demo or
            by the default CI, and this project does not upgrade them speculatively.

`pip-audit` emits one entry per package and repeats an advisory once per matching alias, so
identical (package, version, advisory) triples are collapsed before counting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def rows_from(payload: object) -> list[dict]:
    packages = payload["dependencies"] if isinstance(payload, dict) else payload
    seen: set[tuple[str, str, str]] = set()
    rows: list[dict] = []
    for package in packages:
        name = package.get("name", "?")
        version = package.get("version", "?")
        for vulnerability in package.get("vulns", []) or []:
            identifier = vulnerability.get("id", "?")
            key = (name, version, identifier)
            if key in seen:
                continue
            seen.add(key)
            fixes = [fix for fix in (vulnerability.get("fix_versions") or []) if fix]
            rows.append(
                {
                    "name": name,
                    "version": version,
                    "id": identifier,
                    "aliases": ", ".join(vulnerability.get("aliases") or []),
                    "fixes": ", ".join(fixes),
                    "fixable": bool(fixes),
                },
            )
    return sorted(rows, key=lambda row: (row["name"], row["id"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path, help="pip-audit JSON output")
    parser.add_argument("--label", required=True, help="which dependency set this is")
    parser.add_argument("--gate", choices=("fixable", "advisory"), default="advisory")
    parser.add_argument("--summary", type=Path, help="append a Markdown report here")
    args = parser.parse_args(argv)

    payload = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = rows_from(payload)
    blocking = [row for row in rows if args.gate == "fixable" and row["fixable"]]

    for row in rows:
        level = "error" if row in blocking else "warning"
        fix = f" Fixed in {row['fixes']}." if row["fixes"] else " No fixed release yet."
        print(
            f"::{level} title=pip-audit {args.label} {row['id']}::"
            f"{row['name']} {row['version']} is affected by {row['id']}.{fix}",
        )

    report = [
        f"### Python dependency audit, {args.label}: {len(rows)} advisory/advisories, "
        f"{len(blocking)} blocking (policy: {args.gate})",
        "",
    ]
    if rows:
        report += [
            "| Blocking | Package | Version | Advisory | Aliases | Fixed in |",
            "|---|---|---|---|---|---|",
        ]
        report += [
            f"| {'yes' if row in blocking else 'no'} | {row['name']} | {row['version']} "
            f"| {row['id']} | {row['aliases'] or '-'} | {row['fixes'] or 'no fix released'} |"
            for row in rows
        ]
    else:
        report.append("No known vulnerabilities.")

    text = "\n".join(report) + "\n"
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(text)

    if blocking:
        print(
            f"{args.label}: {len(blocking)} advisory/advisories with a fixed release available.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
