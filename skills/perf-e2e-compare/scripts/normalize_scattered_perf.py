#!/usr/bin/env python3
"""Normalize scattered benchmark CSV/XLSX sources into baseline/tuning CSVs."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from openpyxl import load_workbook
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("openpyxl is required to read XLSX inputs") from exc


CANONICAL_FIELDS = [
    "scenario_name",
    "input_length",
    "output_length",
    "max_concurrency",
    "request_throughput",
    "output_token_throughput",
    "total_token_throughput",
    "mean_ttft",
    "p90_ttft",
    "mean_tpot",
    "p90_tpot",
]

NUMERIC_FIELDS = [field for field in CANONICAL_FIELDS if field != "scenario_name"]
OPTIONAL_FIELDS = ["per_request_e2e_throughput"]

SCENARIO_ORDER = {
    "对话": 0,
    "通用复杂任务": 1,
    "合同分析": 2,
    "Agent应用": 3,
    "AI Coding": 4,
    "特长下行文": 5,
    "特长上下文": 6,
}

HEADER_ALIASES = {
    "scenario_name": ["scenario_name", "scenario", "场景", "场景名称", "业务场景"],
    "input_length": ["input_length", "input len", "input tokens", "输入长度", "输入token数"],
    "output_length": ["output_length", "output len", "output tokens", "输出长度", "输出token数"],
    "max_concurrency": ["max_concurrency", "concurrency", "并发", "最大并发", "并发数"],
    "request_throughput": ["request_throughput", "request throughput", "qps", "请求吞吐"],
    "output_token_throughput": [
        "output_token_throughput",
        "output token throughput",
        "总输出吞吐",
        "总输出吞吐 (tps)",
        "总输出吞吐(tps)",
    ],
    "total_token_throughput": [
        "total_token_throughput",
        "total token throughput",
        "总 e2e 吞吐",
        "总 e2e 吞吐 (tps)",
        "总e2e吞吐",
        "总e2e吞吐(tps)",
    ],
    "mean_ttft": ["mean_ttft", "mean ttft", "mean ttft (s)", "mean ttft (ms)", "ttft均值"],
    "p90_ttft": ["p90_ttft", "ttft p90", "ttft p90 (s)", "ttft p90 (ms)", "ttft p90值"],
    "mean_tpot": ["mean_tpot", "mean tpot", "mean tpot (ms)", "tpot均值"],
    "p90_tpot": ["p90_tpot", "tpot p90", "tpot p90 (ms)", "tpot p90值"],
    "per_request_e2e_throughput": [
        "per_request_e2e_throughput",
        "per request e2e throughput",
        "单路 e2e 吞吐",
        "单路 e2e 吞吐 (tps)",
        "单路e2e吞吐",
    ],
}


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip())


def header_key(value: Any) -> str:
    text = normalize_space(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s_&/\-]+", "", text)


ALIAS_INDEX: dict[str, str] = {}
for canonical, aliases in HEADER_ALIASES.items():
    for alias in aliases:
        ALIAS_INDEX[header_key(alias)] = canonical


def parse_number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{label} is blank or boolean")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        if not text:
            raise ValueError(f"{label} is blank")
        number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite")
    return number


def canonicalize_scenario(value: Any, user_map: dict[str, str]) -> str | None:
    if value is None:
        return None
    scenario = normalize_space(value)
    if not scenario:
        return None
    scenario = user_map.get(scenario, scenario)
    compact = re.sub(r"\s+", "", scenario)

    direct = {
        "对话": "对话",
        "中短对话": "对话",
        "通用复杂任务": "通用复杂任务",
        "复杂任务": "通用复杂任务",
        "合同分析": "合同分析",
        "Agent应用": "Agent应用",
        "AI Coding": "AI Coding",
        "特长下行文": "特长下行文",
        "特长上下文": "特长上下文",
    }
    if scenario in direct:
        return direct[scenario]
    if compact.startswith("对话(2K/2K)"):
        return "对话"
    if compact.startswith("通用复杂任务(8K/1K)"):
        return "通用复杂任务"
    if compact.startswith("合同分析(16K/4K)"):
        return "合同分析"
    if "64K/1K" in compact and compact.lower().startswith("aicoding/agent"):
        return "Agent应用"
    if "128K/1K" in compact and compact.lower().startswith("aicoding/agent"):
        return "AI Coding"
    if compact.startswith("特长下行文"):
        return "特长下行文"
    if compact.startswith("特长上下文"):
        return "特长上下文"
    return None


def infer_role(path: Path, sheet: str | None, explicit: str | None) -> tuple[str | None, str | None]:
    if explicit:
        role = explicit.strip().lower()
        if role in {"baseline", "base"}:
            return "baseline", None
        if role in {"tuning", "tuned", "optimized"}:
            return "tuning", None
        return None, f"invalid explicit role: {explicit}"

    label = f"{path} {sheet or ''}"
    lower = label.lower()
    baseline = "基线" in label or bool(re.search(r"(^|[^a-z])(baseline|base)([^a-z]|$)", lower))
    tuning = ("调优" in label or "优化" in label or bool(
        re.search(r"(^|[^a-z])(tuning|tuned|optimized)([^a-z]|$)", lower)
    ))
    if baseline and tuning:
        return None, "both baseline and tuning markers were found"
    if baseline:
        return "baseline", None
    if tuning:
        return "tuning", None
    return None, "role could not be inferred"


def detect_csv_encoding(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "cp936"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"unsupported CSV encoding: {last_error}")


def read_csv_rows(path: Path) -> tuple[list[list[Any]], dict[str, Any]]:
    text, encoding = detect_csv_encoding(path)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "\t" if "\t" in text.splitlines()[0] else ";" if ";" in text.splitlines()[0] else ","
    rows = [list(row) for row in csv.reader(text.splitlines(), delimiter=delimiter)]
    return rows, {"encoding": encoding, "delimiter": "TAB" if delimiter == "\t" else delimiter}


def read_xlsx_tables(path: Path, sheet_filter: str | None) -> Iterable[tuple[str, list[list[Any]], dict[str, Any]]]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        found = False
        for sheet in workbook.worksheets:
            if sheet_filter is not None and sheet.title != sheet_filter:
                continue
            found = True
            if sheet.sheet_state != "visible":
                continue
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            yield sheet.title, rows, {"sheet_state": sheet.sheet_state}
        if sheet_filter is not None and not found:
            raise ValueError(f"worksheet not found: {sheet_filter}")
    finally:
        workbook.close()


def map_headers(header_row: list[Any], column_overrides: dict[str, str]) -> tuple[dict[str, int], dict[str, str]]:
    mapped: dict[str, int] = {}
    raw_headers: dict[str, str] = {}
    normalized_cells = [header_key(value) if value is not None else "" for value in header_row]

    for index, value in enumerate(header_row):
        if value is None:
            continue
        canonical = ALIAS_INDEX.get(header_key(value))
        if canonical and canonical not in mapped:
            mapped[canonical] = index
            raw_headers[canonical] = str(value)

    for canonical, source_header in column_overrides.items():
        if canonical not in CANONICAL_FIELDS and canonical not in OPTIONAL_FIELDS:
            raise ValueError(f"unknown canonical column in manifest: {canonical}")
        wanted = header_key(source_header)
        matches = [index for index, value in enumerate(normalized_cells) if value == wanted]
        if len(matches) != 1:
            raise ValueError(f"column override for {canonical} matched {len(matches)} headers: {source_header}")
        mapped[canonical] = matches[0]
        raw_headers[canonical] = str(header_row[matches[0]])
    return mapped, raw_headers


def detect_header(
    rows: list[list[Any]], column_overrides: dict[str, str], fixed_scenario: str | None
) -> tuple[int | None, dict[str, int], dict[str, str], list[str], int]:
    best_index: int | None = None
    best_map: dict[str, int] = {}
    best_raw: dict[str, str] = {}
    best_score = -1
    for index, row in enumerate(rows[:20]):
        mapped, raw = map_headers(row, column_overrides)
        score = len([field for field in CANONICAL_FIELDS if field in mapped])
        if score > best_score:
            best_index, best_map, best_raw, best_score = index, mapped, raw, score
    required = [field for field in CANONICAL_FIELDS if field != "scenario_name" or fixed_scenario is None]
    missing = [field for field in required if field not in best_map]
    if best_index is None or best_score <= 0:
        return None, {}, {}, required, max(best_score, 0)
    return best_index, best_map, best_raw, missing, best_score


def infer_ttft_multiplier(raw_header: str, explicit_unit: str | None) -> float:
    if explicit_unit:
        unit = explicit_unit.strip().lower()
        if unit == "ms":
            return 1.0
        if unit == "s":
            return 1000.0
        raise ValueError(f"ttft_unit must be 'ms' or 's', found: {explicit_unit}")
    normalized = normalize_space(raw_header).lower().replace("（", "(").replace("）", ")")
    if "ms" in normalized or "毫秒" in normalized:
        return 1.0
    if re.search(r"\(\s*s\s*\)", normalized) or "秒" in normalized:
        return 1000.0
    return 1.0


def records_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["scenario_name"] != right["scenario_name"]:
        return False
    for field in NUMERIC_FIELDS:
        if not math.isclose(float(left[field]), float(right[field]), rel_tol=1e-9, abs_tol=1e-9):
            return False
    return True


def format_number(value: float, integer_preferred: bool = False) -> str:
    if integer_preferred and math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-9):
        return str(int(round(value)))
    return format(value, ".15g")


def resolve_manifest_path(pattern: str, manifest_dir: Path, input_root: Path) -> list[Path]:
    raw = Path(pattern)
    candidates: list[str] = []
    if raw.is_absolute():
        candidates.append(str(raw))
    else:
        candidates.append(str(manifest_dir / raw))
        if input_root.is_dir():
            candidates.append(str(input_root / raw))
    resolved: list[Path] = []
    for candidate in candidates:
        for match in glob.glob(candidate, recursive=True):
            path = Path(match).resolve()
            if path.is_file() and path not in resolved:
                resolved.append(path)
    return resolved


def discover_sources(input_path: Path, manifest: dict[str, Any] | None, manifest_path: Path | None) -> list[dict[str, Any]]:
    if manifest is not None:
        sources = manifest.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("manifest.sources must be a non-empty list")
        specs: list[dict[str, Any]] = []
        for entry in sources:
            if not isinstance(entry, dict) or not entry.get("path"):
                raise ValueError("each manifest source must be an object with path")
            matches = resolve_manifest_path(str(entry["path"]), manifest_path.parent, input_path)
            if not matches:
                raise ValueError(f"manifest source did not match a file: {entry['path']}")
            for path in matches:
                spec = dict(entry)
                spec["resolved_path"] = path
                specs.append(spec)
        return specs

    if input_path.is_file():
        paths = [input_path.resolve()]
    elif input_path.is_dir():
        paths = sorted(
            path.resolve()
            for path in input_path.rglob("*")
            if path.is_file() and path.suffix.lower() in {".csv", ".xlsx"} and not path.name.startswith("~$")
        )
    else:
        raise ValueError(f"input path does not exist: {input_path}")
    if not paths:
        raise ValueError("no CSV or XLSX inputs were found")
    return [{"resolved_path": path} for path in paths]


def process_table(
    *,
    path: Path,
    sheet: str | None,
    rows: list[list[Any]],
    metadata: dict[str, Any],
    spec: dict[str, Any],
    user_scenario_map: dict[str, str],
    auto_xlsx_sheet: bool,
    records: dict[str, dict[tuple[str, float], dict[str, Any]]],
    report: dict[str, Any],
) -> None:
    source_label = f"{path}::{sheet}" if sheet else str(path)
    columns = spec.get("columns") or {}
    if not isinstance(columns, dict):
        report["unresolved"].append({"source": source_label, "reason": "columns must be an object"})
        return
    fixed_scenario_raw = spec.get("scenario")
    fixed_scenario = canonicalize_scenario(fixed_scenario_raw, user_scenario_map) if fixed_scenario_raw else None
    if fixed_scenario_raw and fixed_scenario is None:
        report["unresolved"].append({"source": source_label, "reason": f"unsupported fixed scenario: {fixed_scenario_raw}"})
        return

    try:
        header_index, mapped, raw_headers, missing, score = detect_header(rows, columns, fixed_scenario)
    except Exception as exc:
        report["unresolved"].append({"source": source_label, "reason": str(exc)})
        return

    explicit_sheet = spec.get("sheet") is not None
    if header_index is None or score < 3:
        if auto_xlsx_sheet and not explicit_sheet:
            report["ignored"].append({"source": source_label, "reason": "no recognizable performance header"})
        else:
            report["unresolved"].append({"source": source_label, "reason": "no recognizable performance header"})
        return
    if missing:
        report["unresolved"].append({"source": source_label, "reason": "missing fields", "fields": missing})
        return

    role, role_error = infer_role(path, sheet, spec.get("role"))
    if role is None:
        report["unresolved"].append({"source": source_label, "reason": role_error})
        return

    try:
        mean_ttft_multiplier = infer_ttft_multiplier(raw_headers["mean_ttft"], spec.get("ttft_unit"))
        p90_ttft_multiplier = infer_ttft_multiplier(raw_headers["p90_ttft"], spec.get("ttft_unit"))
    except ValueError as exc:
        report["unresolved"].append({"source": source_label, "reason": str(exc)})
        return

    current_scenario = fixed_scenario
    parsed_rows = 0
    source_errors: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(value not in (None, "") for value in row):
            continue
        concurrency_index = mapped["max_concurrency"]
        concurrency_raw = row[concurrency_index] if concurrency_index < len(row) else None
        if concurrency_raw in (None, ""):
            continue
        try:
            if "scenario_name" in mapped:
                scenario_index = mapped["scenario_name"]
                scenario_raw = row[scenario_index] if scenario_index < len(row) else None
                if scenario_raw not in (None, ""):
                    current_scenario = canonicalize_scenario(scenario_raw, user_scenario_map)
                    if current_scenario is None:
                        raise ValueError(f"unsupported scenario: {scenario_raw}")
            if current_scenario is None:
                raise ValueError("scenario is blank and no prior/fixed scenario exists")

            normalized: dict[str, Any] = {"scenario_name": current_scenario}
            for field in NUMERIC_FIELDS:
                column_index = mapped[field]
                raw_value = row[column_index] if column_index < len(row) else None
                normalized[field] = parse_number(raw_value, field)
            normalized["mean_ttft"] *= mean_ttft_multiplier
            normalized["p90_ttft"] *= p90_ttft_multiplier
            if normalized["max_concurrency"] <= 0:
                raise ValueError("max_concurrency must be positive")

            if "per_request_e2e_throughput" in mapped:
                optional_index = mapped["per_request_e2e_throughput"]
                optional_raw = row[optional_index] if optional_index < len(row) else None
                per_request = parse_number(optional_raw, "per_request_e2e_throughput")
                expected_total = per_request * normalized["max_concurrency"]
                if not math.isclose(
                    normalized["total_token_throughput"], expected_total, rel_tol=1e-8, abs_tol=1e-6
                ):
                    raise ValueError(
                        "total_token_throughput is inconsistent with per-request E2E times concurrency"
                    )

            provenance = {"source": str(path), "sheet": sheet, "row": row_number}
            key = (current_scenario, normalized["max_concurrency"])
            existing = records[role].get(key)
            if existing is None:
                normalized["_provenance"] = [provenance]
                records[role][key] = normalized
            elif records_equal(existing, normalized):
                existing["_provenance"].append(provenance)
                report["deduplicated"] += 1
            else:
                report["conflicts"].append(
                    {
                        "role": role,
                        "scenario_name": current_scenario,
                        "max_concurrency": normalized["max_concurrency"],
                        "existing": existing["_provenance"],
                        "incoming": provenance,
                    }
                )
            parsed_rows += 1
        except (ValueError, TypeError, IndexError) as exc:
            source_errors.append({"row": row_number, "reason": str(exc)})

    if source_errors:
        report["unresolved"].append({"source": source_label, "reason": "row errors", "errors": source_errors})
    if parsed_rows == 0 and not source_errors:
        report["unresolved"].append({"source": source_label, "reason": "no data rows"})
    if parsed_rows > 0:
        report["accepted"].append(
            {
                "source": source_label,
                "role": role,
                "rows_seen": parsed_rows,
                "header_row": header_index + 1,
                "metadata": metadata,
            }
        )


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS)
        writer.writeheader()
        for record in records:
            row: dict[str, str] = {"scenario_name": record["scenario_name"]}
            for field in NUMERIC_FIELDS:
                row[field] = format_number(
                    float(record[field]), field in {"input_length", "output_length", "max_concurrency"}
                )
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, dest="input_path")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "normalization-report.json"

    report: dict[str, Any] = {
        "status": "collecting",
        "input": str(input_path),
        "manifest": None,
        "discovered": [],
        "accepted": [],
        "ignored": [],
        "unresolved": [],
        "conflicts": [],
        "deduplicated": 0,
        "counts": {"baseline": 0, "tuning": 0},
    }

    try:
        manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else None
        manifest: dict[str, Any] | None = None
        if manifest_path is not None:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            if not isinstance(manifest, dict):
                raise ValueError("manifest root must be an object")
            report["manifest"] = str(manifest_path)
        scenario_map_raw = (manifest or {}).get("scenario_map") or {}
        if not isinstance(scenario_map_raw, dict):
            raise ValueError("manifest.scenario_map must be an object")
        user_scenario_map = {normalize_space(key): normalize_space(value) for key, value in scenario_map_raw.items()}

        specs = discover_sources(input_path, manifest, manifest_path)
        excluded_paths = {Path(value).expanduser().resolve() for value in args.exclude}
        records: dict[str, dict[tuple[str, float], dict[str, Any]]] = {"baseline": {}, "tuning": {}}

        for spec in specs:
            path = Path(spec["resolved_path"])
            if path.resolve() in excluded_paths:
                report["ignored"].append({"source": str(path), "reason": "explicitly excluded"})
                continue
            if path.name.startswith("~$"):
                report["ignored"].append({"source": str(path), "reason": "Excel lock file"})
                continue
            report["discovered"].append(str(path))
            suffix = path.suffix.lower()
            try:
                if suffix == ".csv":
                    rows, metadata = read_csv_rows(path)
                    process_table(
                        path=path,
                        sheet=None,
                        rows=rows,
                        metadata=metadata,
                        spec=spec,
                        user_scenario_map=user_scenario_map,
                        auto_xlsx_sheet=False,
                        records=records,
                        report=report,
                    )
                elif suffix == ".xlsx":
                    sheet_filter = spec.get("sheet")
                    for sheet, rows, metadata in read_xlsx_tables(path, sheet_filter):
                        process_table(
                            path=path,
                            sheet=sheet,
                            rows=rows,
                            metadata=metadata,
                            spec=spec,
                            user_scenario_map=user_scenario_map,
                            auto_xlsx_sheet=True,
                            records=records,
                            report=report,
                        )
                else:
                    report["ignored"].append({"source": str(path), "reason": "unsupported extension"})
            except Exception as exc:
                report["unresolved"].append({"source": str(path), "reason": str(exc)})

        baseline_records = sorted(
            records["baseline"].values(),
            key=lambda row: (SCENARIO_ORDER[row["scenario_name"]], row["max_concurrency"]),
        )
        tuning_records = sorted(
            records["tuning"].values(),
            key=lambda row: (SCENARIO_ORDER[row["scenario_name"]], row["max_concurrency"]),
        )
        report["counts"] = {"baseline": len(baseline_records), "tuning": len(tuning_records)}

        if not baseline_records:
            report["unresolved"].append({"source": "aggregate", "reason": "no baseline rows"})
        if not tuning_records:
            report["unresolved"].append({"source": "aggregate", "reason": "no tuning rows"})

        if report["unresolved"] or report["conflicts"]:
            report["status"] = "failed"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"REPORT={report_path}")
            print(
                f"NORMALIZATION=FAILED unresolved={len(report['unresolved'])} conflicts={len(report['conflicts'])}",
                file=sys.stderr,
            )
            return 2

        baseline_csv = output_dir / "baseline.csv"
        tuning_csv = output_dir / "tuning.csv"
        write_csv(baseline_csv, baseline_records)
        write_csv(tuning_csv, tuning_records)
        report["status"] = "valid"
        report["outputs"] = {"baseline_csv": str(baseline_csv), "tuning_csv": str(tuning_csv)}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"BASE_CSV={baseline_csv}")
        print(f"TUNING_CSV={tuning_csv}")
        print(f"REPORT={report_path}")
        print(f"BASE_ROWS={len(baseline_records)}")
        print(f"TUNING_ROWS={len(tuning_records)}")
        print(f"DEDUPLICATED={report['deduplicated']}")
        print("NORMALIZATION=PASS")
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["unresolved"].append({"source": "normalizer", "reason": str(exc)})
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"REPORT={report_path}")
        print(f"NORMALIZATION=FAILED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
