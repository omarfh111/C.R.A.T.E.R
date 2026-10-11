"""Static supply-chain policy checks for this repository's GitHub Actions workflows.

Run locally or in CI:

    python scripts/check-workflow-supply-chain.py

Checks, in order of how much damage the mistake does:

1. No workflow runs pull-request code with a privileged token. `pull_request_target` and
   `workflow_run` receive the base repository's secrets and a write-capable token, so checking
   out and executing a fork's code under them hands that token to the fork.
2. Every workflow declares an explicit top-level `permissions` block. Without one the job
   inherits the repository default, which can be read/write for every scope.
3. `security-events: write` appears only where a SARIF upload needs it, and `contents: write`
   / `packages: write` / `id-token: write` appear nowhere.
4. No `run:` script interpolates attacker-controlled event data. `${{ github.event.* }}`,
   `github.head_ref` and the like are substituted into the shell verbatim, so a branch or
   title containing shell metacharacters executes as code.
5. Third-party actions are either from an allow-listed first-party owner or pinned to a full
   commit SHA. A floating tag on someone else's action is a mutable dependency.
6. No workflow triggered by `pull_request` reads a repository secret.

Exit status is 0 when the policy holds and 1 when it does not. Findings name the workflow, the
job and what to change; nothing is printed that could leak a secret value.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

# Owners whose actions this repository accepts on a floating major tag. Both are maintained by
# GitHub itself and are already trusted to run the workflow at all.
TRUSTED_ACTION_OWNERS = frozenset({"actions", "github"})

# Scopes no workflow in this repository should ever request.
FORBIDDEN_PERMISSIONS = frozenset({"contents: write", "packages: write", "id-token: write"})

# Workflows allowed to request `security-events: write`, which uploads to Code Scanning.
SECURITY_EVENTS_ALLOWED = frozenset({"codeql.yml"})

# Triggers that give pull-request code the base repository's secrets and token.
PRIVILEGED_PR_TRIGGERS = ("pull_request_target", "workflow_run")

# Expression contexts an outside contributor can set the value of.
UNTRUSTED_EXPRESSIONS = re.compile(
    r"\$\{\{\s*(github\.event\b|github\.head_ref\b|github\.ref_name\b|inputs\.)",
)

SHA_PINNED = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def jobs_of(workflow: dict) -> dict:
    jobs = workflow.get("jobs")
    return jobs if isinstance(jobs, dict) else {}


def steps_of(job: dict) -> list:
    steps = job.get("steps")
    return steps if isinstance(steps, list) else []


def permission_lines(permissions) -> list[str]:
    if isinstance(permissions, dict):
        return [f"{scope}: {value}" for scope, value in permissions.items()]
    if isinstance(permissions, str):
        return [permissions]
    return []


def check_workflow(path: Path, raw: str, workflow: dict) -> list[str]:
    findings: list[str] = []
    name = path.name

    # `on:` is parsed by PyYAML 1.1 rules as the boolean True, so accept either key.
    triggers = workflow.get("on", workflow.get(True)) or {}
    trigger_names = set(triggers) if isinstance(triggers, (dict, list)) else {triggers}

    # 1. Privileged pull-request triggers.
    for trigger in PRIVILEGED_PR_TRIGGERS:
        if trigger in trigger_names:
            findings.append(
                f"{name}: uses `{trigger}`, which runs with the base repository's secrets and a "
                "write-capable token. Use `pull_request` instead, or justify and isolate it.",
            )

    # 2. Explicit top-level permissions.
    if "permissions" not in workflow:
        findings.append(
            f"{name}: declares no top-level `permissions`. Add `permissions: contents: read` and "
            "widen it per job only where needed.",
        )

    # 3. Permission scopes.
    scopes = permission_lines(workflow.get("permissions"))
    for job_id, job in jobs_of(workflow).items():
        scopes += [f"{job_id} -> {line}" for line in permission_lines(job.get("permissions"))]
    for line in scopes:
        bare = line.split(" -> ")[-1]
        if bare in FORBIDDEN_PERMISSIONS:
            findings.append(f"{name}: requests `{line}`, which no workflow here needs.")
        if bare == "security-events: write" and name not in SECURITY_EVENTS_ALLOWED:
            findings.append(
                f"{name}: requests `security-events: write`. Only "
                f"{', '.join(sorted(SECURITY_EVENTS_ALLOWED))} uploads SARIF.",
            )

    for job_id, job in jobs_of(workflow).items():
        for index, step in enumerate(steps_of(job)):
            if not isinstance(step, dict):
                continue
            where = f"{name} -> {job_id} -> step {index + 1}"

            # 4. Script injection through untrusted expressions.
            script = step.get("run")
            if isinstance(script, str):
                match = UNTRUSTED_EXPRESSIONS.search(script)
                if match:
                    findings.append(
                        f"{where}: interpolates `{match.group(1).strip()}` into a `run:` script. "
                        "Pass it through `env:` and reference the environment variable instead.",
                    )

            # 5. Third-party action pinning.
            uses = step.get("uses")
            if isinstance(uses, str) and not uses.startswith(("./", "docker://")):
                owner = uses.split("/", 1)[0]
                if owner not in TRUSTED_ACTION_OWNERS and not SHA_PINNED.match(uses):
                    findings.append(
                        f"{where}: uses third-party action `{uses}` on a mutable reference. "
                        "Pin it to a full 40-character commit SHA.",
                    )

    # 6. Secrets in pull-request-triggered workflows.
    if "pull_request" in trigger_names and re.search(r"\$\{\{\s*secrets\.", raw):
        findings.append(
            f"{name}: reads a repository secret in a workflow triggered by `pull_request`. "
            "Fork pull requests must not be able to reach a secret.",
        )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflows",
        type=Path,
        default=Path(".github/workflows"),
        help="directory holding the workflow definitions",
    )
    args = parser.parse_args(argv)

    paths = sorted(list(args.workflows.glob("*.yml")) + list(args.workflows.glob("*.yaml")))
    if not paths:
        print(f"No workflows found under {args.workflows}", file=sys.stderr)
        return 1

    findings: list[str] = []
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        try:
            workflow = yaml.safe_load(raw)
        except yaml.YAMLError as error:
            findings.append(f"{path.name}: is not valid YAML ({error.__class__.__name__}).")
            continue
        if not isinstance(workflow, dict):
            findings.append(f"{path.name}: does not parse to a workflow mapping.")
            continue
        findings += check_workflow(path, raw, workflow)

    print(f"Reviewed {len(paths)} workflow(s): {', '.join(path.name for path in paths)}")
    if not findings:
        print("Supply-chain policy holds: no findings.")
        return 0
    print(f"\n{len(findings)} finding(s):")
    for finding in findings:
        print(f"  - {finding}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
