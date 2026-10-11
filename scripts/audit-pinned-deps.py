"""Audit a fully pinned requirements file against OSV, without resolving or installing it.

    python scripts/pin-python-deps.py --group onnx-local --platform win32 --output pins.txt
    python scripts/audit-pinned-deps.py --requirement pins.txt --output audit.json
    python scripts/summarize-pip-audit.py audit.json --label "..." --gate advisory

`pip-audit` is the tool used for every dependency set this project can install. It cannot be
used for the local ONNX group from a Linux runner: even with `--no-deps` it resolves the
requirements through `pip install --dry-run` inside a throwaway virtual environment, and
`onnxruntime-directml` publishes Windows wheels only, so resolution fails with "No matching
distribution found" and no report is produced. Installing the group instead would pull PyTorch
and the DirectML provider onto the runner, which this project does not do.

Querying OSV by package name and version needs neither a resolver nor a compatible wheel, so
the Windows-only GPU provider and the portable CPU runtime are both audited at their declared
pins from one Linux job. The output deliberately uses pip-audit's JSON shape so the same
reporting and gating script consumes it unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

OSV_QUERY = "https://api.osv.dev/v1/query"
PYPI_ECOSYSTEMS = {"pypi"}


def pinned_requirements(path: Path) -> list[tuple[str, str]]:
    """`name==version` pairs from a pins file, ignoring comments and blank lines."""
    pins: list[tuple[str, str]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            raise SystemExit(f"{path}:{number} is not an exact pin: {line!r}")
        name, _, version = line.partition("==")
        pins.append((name.strip(), version.strip()))
    if not pins:
        raise SystemExit(f"{path} contains no pinned requirements")
    return pins


def normalize(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def query_osv(name: str, version: str, timeout: float) -> list[dict]:
    payload = json.dumps({"package": {"name": name, "ecosystem": "PyPI"}, "version": version}).encode()
    request = urllib.request.Request(OSV_QUERY, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
            body = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as error:
        raise SystemExit(f"OSV query for {name}=={version} failed: {error}") from error
    return body.get("vulns") or []


def fixed_versions(vulnerability: dict, name: str) -> list[str]:
    wanted = normalize(name)
    fixes: list[str] = []
    for affected in vulnerability.get("affected", []):
        package = affected.get("package", {})
        if (package.get("ecosystem", "").lower() not in PYPI_ECOSYSTEMS
                or normalize(package.get("name", "")) != wanted):
            continue
        for value_range in affected.get("ranges", []):
            for event in value_range.get("events", []):
                if event.get("fixed"):
                    fixes.append(event["fixed"])
    # Stable order, no duplicates.
    return sorted(dict.fromkeys(fixes))


def collapse_aliases(entries: list[dict]) -> list[dict]:
    """One row per advisory.

    OSV returns the GHSA, CVE and PYSEC records for the same advisory as separate entries that
    list each other as aliases. Reporting all of them would triple-count a single problem, so
    alias-linked entries are merged, the identifier a reader is most likely to recognise is kept
    as the primary, and the fixed versions are unioned.
    """
    preference = {"GHSA": 0, "CVE": 1, "PYSEC": 2}
    groups: list[dict] = []
    for entry in sorted(entries, key=lambda item: item["id"]):
        names = {entry["id"], *entry["aliases"]}
        match = next((group for group in groups if group["names"] & names), None)
        if match is None:
            groups.append({"names": names, "ids": [entry["id"]], "fixes": list(entry["fix_versions"])})
        else:
            match["names"] |= names
            match["ids"].append(entry["id"])
            match["fixes"] += entry["fix_versions"]
    merged = []
    for group in groups:
        primary = min(group["ids"], key=lambda value: (preference.get(value.split("-", 1)[0], 9), value))
        merged.append(
            {
                "id": primary,
                "aliases": sorted(group["names"] - {primary}),
                "fix_versions": sorted(dict.fromkeys(group["fixes"])),
            },
        )
    return sorted(merged, key=lambda item: item["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement", type=Path, required=True, help="fully pinned requirements file")
    parser.add_argument("--output", type=Path, required=True, help="write pip-audit-shaped JSON here")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)

    dependencies = []
    for name, version in pinned_requirements(args.requirement):
        vulnerabilities = []
        for vulnerability in query_osv(name, version, args.timeout):
            if vulnerability.get("withdrawn"):
                continue
            vulnerabilities.append(
                {
                    "id": vulnerability.get("id", "?"),
                    "aliases": sorted(vulnerability.get("aliases") or []),
                    "fix_versions": fixed_versions(vulnerability, name),
                },
            )
        collapsed = collapse_aliases(vulnerabilities)
        dependencies.append({"name": name, "version": version, "vulns": collapsed})
        print(
            f"{name}=={version}: {len(collapsed)} advisory/advisories "
            f"({len(vulnerabilities)} OSV records)",
            file=sys.stderr,
        )

    args.output.write_text(json.dumps({"dependencies": dependencies}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} for {len(dependencies)} pinned package(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
