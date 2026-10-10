#!/usr/bin/env python3
"""Validate the structure of a generated learning-guide Markdown file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote


LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
MERMAID_STARTS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "stateDiagram",
    "classDiagram",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "timeline",
    "mindmap",
)
PLACEHOLDER_RE = re.compile(
    r"(?:\bTODO\b|\{\{[^}\n]+\}\}"
    r"|\[待(?:补充|填写|确认)\])",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="Markdown document to validate")
    return parser.parse_args()


def read_utf8(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="strict")


def local_link_errors(text: str, base: Path) -> list[str]:
    errors: list[str] = []
    for raw_target in LINK_RE.findall(text):
        target = raw_target.strip().strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        path_part = unquote(target.split("#", 1)[0])
        if not path_part:
            continue
        resolved = (base / path_part).resolve()
        if not resolved.exists():
            errors.append(f"missing local link target: {target}")
    return errors


def mermaid_errors(lines: list[str]) -> tuple[list[str], int]:
    errors: list[str] = []
    blocks = 0
    inside = False
    start_line = 0
    body: list[str] = []

    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not inside and stripped == "```mermaid":
            inside = True
            start_line = number
            body = []
            continue
        if inside and stripped == "```":
            blocks += 1
            significant = [item.strip() for item in body if item.strip()]
            if not significant:
                errors.append(f"empty Mermaid block starting at line {start_line}")
            elif not significant[0].startswith(MERMAID_STARTS):
                errors.append(
                    f"unrecognized Mermaid declaration at line {start_line + 1}: "
                    f"{significant[0]}"
                )
            inside = False
            body = []
            continue
        if inside:
            body.append(line)

    if inside:
        errors.append(f"unclosed Mermaid block starting at line {start_line}")
    return errors, blocks


def validate(path: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    if not path.is_file():
        return [f"document does not exist: {path}"], {}

    try:
        text = read_utf8(path)
    except UnicodeDecodeError as exc:
        return [f"invalid UTF-8: {exc}"], {}

    lines = text.splitlines()
    fence_count = sum(1 for line in lines if line.startswith("```"))
    if fence_count % 2:
        errors.append(f"unbalanced fenced code blocks: {fence_count} markers")

    for number, line in enumerate(lines, start=1):
        if line.rstrip(" \t") != line:
            errors.append(f"trailing whitespace at line {number}")

    mermaid_problems, mermaid_count = mermaid_errors(lines)
    errors.extend(mermaid_problems)
    errors.extend(local_link_errors(text, path.parent))

    placeholder_matches = list(PLACEHOLDER_RE.finditer(text))
    for match in placeholder_matches[:10]:
        line_number = text.count("\n", 0, match.start()) + 1
        errors.append(f"placeholder at line {line_number}: {match.group(0)}")
    if len(placeholder_matches) > 10:
        errors.append(f"additional placeholders omitted: {len(placeholder_matches) - 10}")

    h1_count = sum(1 for line in lines if line.startswith("# "))
    if h1_count != 1:
        errors.append(f"expected exactly one H1 heading, found {h1_count}")

    stats = {
        "lines": len(lines),
        "fences": fence_count,
        "mermaid_blocks": mermaid_count,
        "local_links": sum(
            1
            for target in LINK_RE.findall(text)
            if not target.strip().strip("<>").startswith(
                ("http://", "https://", "mailto:", "#", "data:")
            )
        ),
    }
    return errors, stats


def main() -> int:
    args = parse_args()
    path = args.document.resolve()
    errors, stats = validate(path)
    if errors:
        print(f"STRUCTURE FAIL: {path}")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"STRUCTURE PASS: {path}")
    print(
        " ".join(
            f"{key}={value}"
            for key, value in stats.items()
        )
    )
    print(
        "SEMANTIC CHECKS NOT RUN: review layer ownership, handoff fields, "
        "quantitative accounting, source support, and scope boundaries."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
