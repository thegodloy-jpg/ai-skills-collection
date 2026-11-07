#!/usr/bin/env python3
"""Create an inference RCA case directory without overwriting existing work."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
from pathlib import Path


DEFAULT_WORKSPACE = Path(r"F:\DAY0")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_slug(kind: str, value: str) -> None:
    if not SLUG_RE.fullmatch(value):
        fail(
            f"invalid {kind} {value!r}; use lowercase ASCII letters, digits, dots, and hyphens"
        )


def ensure_below(root: Path, candidate: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError:
        fail(f"target escapes workspace root: {candidate}")


def render(template: str, replacements: dict[str, str]) -> str:
    for key, value in replacements.items():
        template = template.replace("${" + key + "}", value)
    return template


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize an immutable inference root-cause case under a DAY0 workspace."
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help=f"Workspace root (default: {DEFAULT_WORKSPACE})",
    )
    parser.add_argument("--model-slug", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--report-level", choices=("compact", "detailed"), default="detailed"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the resolved target without writing"
    )
    args = parser.parse_args()

    validate_slug("model slug", args.model_slug)
    validate_slug("case ID", args.case_id)

    root = args.workspace_root.resolve()
    if not root.is_dir():
        fail(f"workspace root does not exist: {root}")
    if not (root / "workspace.yaml").is_file():
        fail(f"workspace is not initialized: {root / 'workspace.yaml'}")

    model_root = (root / "模型" / args.model_slug).resolve()
    if not (model_root / "model.yaml").is_file():
        fail(f"model is not registered: {model_root / 'model.yaml'}")

    incidents_root = (model_root / "故障").resolve()
    target = (incidents_root / args.case_id).resolve()
    ensure_below(root, model_root)
    ensure_below(root, incidents_root)
    ensure_below(root, target)

    print(f"WORKSPACE_ROOT={root}")
    print(f"MODEL_ROOT={model_root}")
    print(f"CASE_DIR={target}")
    if args.dry_run:
        print("STATE=DRY_RUN")
        return 0

    if target.exists():
        fail(f"case already exists; refusing to overwrite: {target}")

    skill_root = Path(__file__).resolve().parent.parent
    case_template = skill_root / "assets" / "case-template.yaml"
    report_template = skill_root / "assets" / "root-cause-report-template.md"
    if not case_template.is_file() or not report_template.is_file():
        fail("skill templates are missing")

    incidents_root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    staging = incidents_root / f".{args.case_id}.tmp-{stamp}-{os.getpid()}"
    ensure_below(root, staging.resolve())
    if staging.exists():
        fail(f"staging directory already exists: {staging}")

    replacements = {
        "CASE_ID": args.case_id,
        "TITLE": args.title,
        "WORKSPACE_ROOT": str(root),
        "MODEL_SLUG": args.model_slug,
        "OUTPUT_DIR": str(target),
        "STATUS": "observed",
        "ROOT_CAUSE_CONFIDENCE": "observed",
        "TESTED_REVISION": "unverified",
        "CURRENT_UPSTREAM_REVISION": "unverified",
        "CURRENT_CONCLUSION": "Evidence collection and mechanism analysis are pending.",
        "NEXT_STEP": "Fill case.yaml, index evidence, and design the smallest discriminating experiment.",
    }

    try:
        for relative in (
            "证据/摘录",
            "证据/脱敏",
            "实验",
            "结论",
            "上游/评论",
        ):
            (staging / relative).mkdir(parents=True, exist_ok=True)

        case_text = render(case_template.read_text(encoding="utf-8"), replacements)
        case_text = case_text.replace(
            'report_level: "detailed"', f'report_level: "{args.report_level}"', 1
        )
        report_text = render(report_template.read_text(encoding="utf-8"), replacements)
        evidence_text = (
            "schema_version: 1\n"
            f'case_id: "{args.case_id}"\n'
            "policy: reference-canonical-artifacts\n"
            "evidence: []\n"
        )

        (staging / "case.yaml").write_text(case_text, encoding="utf-8", newline="\n")
        (staging / "root-cause-report.md").write_text(
            report_text, encoding="utf-8", newline="\n"
        )
        (staging / "evidence-index.yaml").write_text(
            evidence_text, encoding="utf-8", newline="\n"
        )
        staging.replace(target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    print("STATE=CREATED")
    print(
        "NEXT=fill placeholders, add evidence references, run check_evidence.py, "
        "then register the validated case in model.yaml"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
