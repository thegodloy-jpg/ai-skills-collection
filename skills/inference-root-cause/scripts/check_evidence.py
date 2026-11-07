#!/usr/bin/env python3
"""Validate a root-cause case/report for completeness and accidental secrets.

This intentionally uses only the Python standard library. It performs structural
and hygiene checks; it cannot establish that the diagnosis is correct.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path


CASE_KEYS = (
    "case_id",
    "status",
    "report_level",
    "problem",
    "environment",
    "tested_revision",
    "current_upstream_revision",
    "baseline",
    "variant",
    "controlled_variable",
    "reproduction",
    "root_cause",
    "resolution",
    "evidence",
    "upstream",
)

REPORT_HEADINGS = (
    "Conclusion Summary",
    "Scope and Evidence Boundary",
    "Verified Facts",
    "System Mechanism",
    "Expected Execution Path",
    "Actual Failure Chain",
    "Trigger and Non-trigger Conditions",
    "Competing Hypotheses",
    "Discriminating Experiments",
    "Root Cause Assessment",
    "Fix Principle",
    "Regression Validation",
    "Risks and Open Questions",
    "Evidence Index",
)

PLACEHOLDER_RE = re.compile(r"\$\{[^}]+\}|\b(?:TODO|TBD|CHANGEME)\b", re.I)
SECRET_PATTERNS = (
    ("GitHub token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    (
        "password assignment",
        re.compile(r"(?im)^\s*(?:password|passwd|pwd)\s*[:=]\s*[^\s#]{4,}\s*$"),
    ),
)
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_secrets(label: str, text: str, public: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            errors.append(f"{label}:{line_number(text, match.start())}: possible {name}")

    if public:
        for match in IPV4_RE.finditer(text):
            raw = match.group(0)
            try:
                address = ipaddress.ip_address(raw)
            except ValueError:
                continue
            if address.is_private or address.is_loopback or address.is_link_local:
                warnings.append(
                    f"{label}:{line_number(text, match.start())}: review non-public IPv4 address {raw}"
                )
    return errors, warnings


def validate_case(path: Path, text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for key in CASE_KEYS:
        if not re.search(rf"(?m)^{re.escape(key)}\s*:", text):
            errors.append(f"{path}: missing top-level key '{key}'")

    placeholders = list(PLACEHOLDER_RE.finditer(text))
    for match in placeholders:
        errors.append(f"{path}:{line_number(text, match.start())}: unresolved placeholder {match.group(0)!r}")

    confidence = re.search(
        r"(?ms)^root_cause\s*:\s*.*?^\s+confidence\s*:\s*[\"']?([a-z_]+)", text
    )
    allowed = {"observed", "associated", "mechanism_supported", "confirmed"}
    if not confidence:
        errors.append(f"{path}: root_cause.confidence is missing")
    elif confidence.group(1) not in allowed:
        errors.append(
            f"{path}: unsupported root_cause confidence {confidence.group(1)!r}; expected one of {sorted(allowed)}"
        )

    if re.search(r"(?m)^\s*request_failures\s*:\s*(?:null|~)\s*$", text):
        warnings.append(f"{path}: request_failures is unknown")
    if re.search(r"(?m)^\s*attempts\s*:\s*0\s*$", text):
        warnings.append(f"{path}: reproduction attempts are zero")
    return errors, warnings


def validate_report(path: Path, text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for heading in REPORT_HEADINGS:
        if not re.search(rf"(?im)^#+\s+.*{re.escape(heading)}\s*$", text):
            errors.append(f"{path}: missing report heading containing '{heading}'")

    for match in PLACEHOLDER_RE.finditer(text):
        errors.append(f"{path}:{line_number(text, match.start())}: unresolved placeholder {match.group(0)!r}")

    confidence = re.search(
        r"(?im)^\s*-\s*Root-cause confidence\s*:\s*`?([a-z_]+)`?\s*$", text
    )
    allowed = {"observed", "associated", "mechanism_supported", "confirmed"}
    if not confidence:
        errors.append(f"{path}: conclusion summary has no root-cause confidence field")
    elif confidence.group(1) not in allowed:
        errors.append(
            f"{path}: unsupported report confidence {confidence.group(1)!r}; expected one of {sorted(allowed)}"
        )
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check an inference root-cause case and report before archival or public use."
    )
    parser.add_argument("--case", type=Path, required=True, help="Filled case YAML path")
    parser.add_argument("--report", type=Path, help="Filled RCA Markdown report path")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Warn about private, loopback, or link-local IPv4 addresses",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return failure when warnings are present",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    for path in (args.case, args.report):
        if path is not None and not path.is_file():
            errors.append(f"missing file: {path}")

    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        return 1

    case_text = read_text(args.case)
    current_errors, current_warnings = validate_case(args.case, case_text)
    errors.extend(current_errors)
    warnings.extend(current_warnings)
    current_errors, current_warnings = scan_secrets(str(args.case), case_text, args.public)
    errors.extend(current_errors)
    warnings.extend(current_warnings)

    if args.report is not None:
        report_text = read_text(args.report)
        current_errors, current_warnings = validate_report(args.report, report_text)
        errors.extend(current_errors)
        warnings.extend(current_warnings)
        current_errors, current_warnings = scan_secrets(str(args.report), report_text, args.public)
        errors.extend(current_errors)
        warnings.extend(current_warnings)

    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARNING: {item}")

    if errors or (args.strict and warnings):
        return 1
    print(f"PASS: {args.case}" + (f" and {args.report}" if args.report else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
