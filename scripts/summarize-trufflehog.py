"""Classify TruffleHog JSON findings, report them, and decide what blocks the build.

    trufflehog git file:///repo --no-update --results=verified,unknown,unverified --json > findings.jsonl
    python scripts/summarize-trufflehog.py findings.jsonl --summary "$GITHUB_STEP_SUMMARY"

Classification follows TruffleHog's own result semantics:

  verified    the detector asked the provider and the credential is live. Always blocking.
  unknown     verification was attempted and could not complete, usually because the runner
              cannot reach the provider. Treated as a live credential and blocking, except for
              the detectors named in `UNKNOWN_ADVISORY_DETECTORS`.
  unverified  a pattern matched but the provider rejected it. Reported, never blocking: git
              history cannot be rewritten from CI, so a pattern hit in an old commit has to be
              reviewed by a person.

Only metadata is printed: detector name, classification, path, line and commit. The matched
text, redacted or otherwise, is never written to a log, an annotation or the job summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Generic detectors whose `unknown` results are advisory rather than blocking.
#
# `URI` matches any `scheme://userinfo@host` shape, so it fires on the hostile URLs the test
# suites feed in on purpose to assert they are refused, and it can never identify a
# provider-specific credential. That is what makes it the one detector whose unverifiable hits
# are not treated as live. Every other detector still blocks on `unknown`, and `URI` hits are
# still listed below, so nothing is hidden. The shapes themselves are not reproduced here,
# which would only add another match for this scanner to report.
UNKNOWN_ADVISORY_DETECTORS = frozenset({"URI"})


def classify(finding: dict) -> str:
    if finding.get("Verified"):
        return "verified"
    return "unknown" if finding.get("VerificationError") else "unverified"


def read_findings(path: Path) -> list[dict]:
    findings = []
    # TruffleHog writes one JSON object per line; a PowerShell redirect may add a BOM.
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            findings.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise SystemExit(f"{path}:{number} is not valid TruffleHog JSON: {error}") from error
    return findings


def describe(finding: dict) -> dict:
    git = (finding.get("SourceMetadata") or {}).get("Data", {}).get("Git", {})
    filesystem = (finding.get("SourceMetadata") or {}).get("Data", {}).get("Filesystem", {})
    return {
        "detector": finding.get("DetectorName") or "unknown-detector",
        "classification": classify(finding),
        "file": git.get("file") or filesystem.get("file") or "n/a",
        "line": git.get("line") or filesystem.get("line") or 1,
        "commit": (git.get("commit") or "")[:7] or "n/a",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("findings", type=Path, help="TruffleHog JSON lines")
    parser.add_argument("--summary", type=Path, help="append a Markdown report here")
    parser.add_argument(
        "--label",
        default="git history",
        help="what was scanned, for the report heading",
    )
    args = parser.parse_args(argv)

    rows = [describe(finding) for finding in read_findings(args.findings)]
    blocking = [
        row
        for row in rows
        if row["classification"] == "verified"
        or (row["classification"] == "unknown" and row["detector"] not in UNKNOWN_ADVISORY_DETECTORS)
    ]
    counts = {
        name: sum(1 for row in rows if row["classification"] == name)
        for name in ("verified", "unknown", "unverified")
    }

    for row in rows:
        level = "error" if row in blocking else "warning"
        print(
            f"::{level} file={row['file']},line={row['line']},"
            f"title=TruffleHog {row['detector']} ({row['classification']})"
            f"::{row['detector']} {row['classification']} match at commit {row['commit']}."
            " Review it; the matched text is deliberately not printed.",
        )

    report = [
        f"### Secret scan of {args.label}: {len(rows)} match(es), {len(blocking)} blocking",
        "",
        f"- verified (live credential): **{counts['verified']}**",
        f"- unknown (verification could not complete): **{counts['unknown']}**",
        f"- unverified (provider rejected the pattern): **{counts['unverified']}**",
        "",
    ]
    if rows:
        report += [
            "| Blocking | Detector | Classification | File | Line | Commit |",
            "|---|---|---|---|---|---|",
        ]
        report += [
            f"| {'yes' if row in blocking else 'no'} | {row['detector']} | {row['classification']} "
            f"| {row['file']} | {row['line']} | {row['commit']} |"
            for row in rows
        ]
        report += ["", "Matched values are never printed. Review each match in the repository."]
    else:
        report.append("No matches of any classification.")

    text = "\n".join(report) + "\n"
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(text)

    if blocking:
        print(
            f"Secret scan failed: {len(blocking)} live or unverifiable credential match(es).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
