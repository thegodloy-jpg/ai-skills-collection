#!/usr/bin/env python3
"""Plan, run, and validate Mode A fixed-scenario inference benchmarks.

The runner intentionally owns cache reset and invokes benchmark_new_v1.5.sh
with --no-reset-prefix-cache. It uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
from typing import Any, Iterable
from urllib import error, request


OWNED_EXTRA_ARGS = {
    "-M",
    "--mode",
    "-c",
    "--combinations",
    "-r",
    "--result-dir",
    "--no-reset-prefix-cache",
}
VALID_CACHE_POLICIES = {"cold", "shared-prefix-cold-start", "warm-reuse"}
SUMMARY_FIELDS = [
    "experiment_id",
    "arm_id",
    "parent_arm",
    "intended_delta",
    "scenario_id",
    "repetition",
    "verdict",
    "reason",
    "cache_policy",
    "cache_reset_success",
    "input_length",
    "output_length",
    "num_prompts",
    "max_concurrency",
    "prefix_ratio",
    "failed_requests",
    "request_throughput",
    "output_token_throughput",
    "total_token_throughput",
    "mean_ttft",
    "p95_ttft",
    "p99_ttft",
    "mean_tpot",
    "p95_tpot",
    "p99_tpot",
    "mean_e2el",
    "p95_e2el",
    "p99_e2el",
    "metrics_file",
    "unit_dir",
]


class ConfigError(ValueError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read JSON config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError("top-level config must be a JSON object")
    return value


def resolve_config_paths(config: dict[str, Any], config_path: Path) -> None:
    """Resolve the benchmark script without requiring a discovery login."""
    bench = config.get("benchmark")
    if not isinstance(bench, dict):
        return
    raw = bench.get("script_path")
    if not isinstance(raw, str) or not raw:
        return
    if raw == "@bundled":
        bench["script_path"] = str(Path(__file__).resolve().with_name("benchmark_new_v1.5.sh"))
        return
    candidate = Path(raw)
    if not candidate.is_absolute():
        bench["script_path"] = str((config_path.resolve().parent / candidate).resolve())


def require(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise ConfigError(f"missing {context}.{key}")
    return mapping[key]


def positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{label} must be a positive integer")
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{label} must be a positive integer") from exc
    if converted <= 0 or str(value).strip() not in {str(converted), f"{converted}.0"}:
        raise ConfigError(f"{label} must be a positive integer")
    return converted


def validate_config(config: dict[str, Any], *, for_run: bool = False) -> None:
    if config.get("schema_version") != 1:
        raise ConfigError("schema_version must be 1")
    require(config, "experiment_id", "config")
    arm = require(config, "arm", "config")
    bench = require(config, "benchmark", "config")
    cache = require(config, "cache", "config")
    scenarios = require(config, "scenarios", "config")
    if not isinstance(arm, dict) or not isinstance(bench, dict) or not isinstance(cache, dict):
        raise ConfigError("arm, benchmark, and cache must be JSON objects")
    if not isinstance(scenarios, list) or not scenarios:
        raise ConfigError("scenarios must be a non-empty array")
    require(arm, "id", "arm")
    require(arm, "intended_delta", "arm")
    for key in (
        "script_path",
        "model_path",
        "model_name",
        "base_url",
        "accelerator_type",
        "result_root",
    ):
        require(bench, key, "benchmark")
    if not str(bench["base_url"]).startswith(("http://", "https://")):
        raise ConfigError("benchmark.base_url must start with http:// or https://")
    repetitions = positive_int(config.get("repetitions", 1), "repetitions")
    config["repetitions"] = repetitions
    policy = cache.get("policy")
    if policy not in VALID_CACHE_POLICIES:
        raise ConfigError(f"cache.policy must be one of {sorted(VALID_CACHE_POLICIES)}")
    if cache.get("strict", True) is not True and policy != "warm-reuse":
        raise ConfigError("cache.strict must be true for cold-start Mode A data")
    seen: set[str] = set()
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            raise ConfigError(f"scenarios[{index}] must be an object")
        scenario_id = str(require(scenario, "id", f"scenarios[{index}]"))
        if scenario_id in seen:
            raise ConfigError(f"duplicate scenario id: {scenario_id}")
        seen.add(scenario_id)
        for key in ("input_tokens", "output_tokens", "num_prompts", "max_concurrency"):
            scenario[key] = positive_int(require(scenario, key, f"scenarios[{index}]"), f"{scenario_id}.{key}")
        if scenario["num_prompts"] < scenario["max_concurrency"]:
            raise ConfigError(f"{scenario_id}: num_prompts cannot be smaller than max_concurrency")
        try:
            prefix_rate = float(scenario.get("prefix_rate", 0.0))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{scenario_id}.prefix_rate must be numeric") from exc
        if not 0.0 <= prefix_rate <= 1.0:
            raise ConfigError(f"{scenario_id}.prefix_rate must be between 0 and 1")
        if policy == "shared-prefix-cold-start" and prefix_rate <= 0.0:
            raise ConfigError(f"{scenario_id}: shared-prefix-cold-start requires prefix_rate > 0")
        scenario["prefix_rate"] = prefix_rate
    extra_args = bench.get("extra_args", [])
    if not isinstance(extra_args, list) or not all(isinstance(item, str) for item in extra_args):
        raise ConfigError("benchmark.extra_args must be an array of strings")
    for item in extra_args:
        option = item.split("=", 1)[0]
        if option in OWNED_EXTRA_ARGS:
            raise ConfigError(f"benchmark.extra_args cannot override runner-owned option {option}")
    expected_hash = bench.get("script_sha256")
    if expected_hash and not re.fullmatch(r"[0-9a-fA-F]{64}", str(expected_hash)):
        raise ConfigError("benchmark.script_sha256 must be a 64-character hexadecimal digest")
    if for_run and config.get("require_identity_evidence", True):
        digest = str(arm.get("image_digest", ""))
        command_hash = str(arm.get("service_command_sha256", ""))
        if not digest or digest in {"verify-before-run", "unknown"}:
            raise ConfigError("run requires arm.image_digest evidence")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", command_hash):
            raise ConfigError("run requires a 64-character arm.service_command_sha256")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact_prefix(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def combo(scenario: dict[str, Any]) -> str:
    return " ".join(
        [
            str(scenario["input_tokens"]),
            str(scenario["output_tokens"]),
            str(scenario["num_prompts"]),
            str(scenario["max_concurrency"]),
            compact_prefix(float(scenario["prefix_rate"])),
        ]
    )


def build_command(
    config: dict[str, Any], scenario: dict[str, Any], script_path: str, result_dir: str
) -> list[str]:
    bench = config["benchmark"]
    command = [
        "bash",
        script_path,
        "--model-path",
        str(bench["model_path"]),
        "--model-name",
        str(bench["model_name"]),
        "--base-url",
        str(bench["base_url"]),
        "--accelerator-type",
        str(bench["accelerator_type"]),
        "--temperature",
        str(bench.get("temperature", 0)),
        "-c",
        combo(scenario),
        "-r",
        result_dir,
        "--no-reset-prefix-cache",
    ]
    command.extend(config["benchmark"].get("extra_args", []))
    return command


def plan(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    units = []
    for repetition in range(1, config["repetitions"] + 1):
        for scenario in config["scenarios"]:
            placeholder = f"<RUN_ROOT>/{scenario['id']}/rep-{repetition:02d}"
            command = build_command(config, scenario, "<SANITIZED_V1.5>", placeholder)
            units.append(
                {
                    "scenario_id": scenario["id"],
                    "repetition": repetition,
                    "combo": combo(scenario),
                    "cache_action": (
                        "none-intentional"
                        if config["cache"]["policy"] == "warm-reuse"
                        else "POST /reset_prefix_cache and require success"
                    ),
                    "command": shlex.join(command),
                }
            )
    return {
        "mode": "plan",
        "experiment_id": config["experiment_id"],
        "arm": config["arm"],
        "script_source": config["benchmark"]["script_path"],
        "result_root": config["benchmark"]["result_root"],
        "units": units,
    }


def api_headers(config: dict[str, Any]) -> dict[str, str]:
    env_name = config["benchmark"].get("api_key_env")
    if not env_name:
        return {}
    value = os.environ.get(str(env_name))
    if not value:
        raise ConfigError(f"API key environment variable is not set: {env_name}")
    return {"Authorization": f"Bearer {value}"}


def http_json(url: str, *, method: str, headers: dict[str, str], timeout: float) -> Any:
    req = request.Request(url, data=b"" if method == "POST" else None, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not 200 <= response.status < 300:
                raise RuntimeError(f"HTTP {response.status}: {raw[:500]}")
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"request failed for {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {url}: {raw[:500]}") from exc


def models_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/models"


def reset_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/") + "/reset_prefix_cache"


def sanitize_script(source: Path, destination: Path) -> tuple[str, str, bool]:
    raw = source.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    if had_bom:
        raw = raw[3:]
    destination.parent.mkdir(parents=True, exist_ok=False)
    destination.write_bytes(raw)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return source_hash, hashlib.sha256(raw).hexdigest(), had_bom


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_stream(command: list[str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        return process.wait()


def as_int(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def row_matches(row: dict[str, str], scenario: dict[str, Any]) -> bool:
    input_value = row.get("input_length", row.get("total_input_len"))
    output_value = row.get("output_length", row.get("output_start"))
    checks = [
        as_int(input_value) == scenario["input_tokens"],
        as_int(output_value) == scenario["output_tokens"],
        as_int(row.get("num_prompts")) == scenario["num_prompts"],
        as_int(row.get("max_concurrency")) == scenario["max_concurrency"],
    ]
    prefix = as_float(row.get("prefix_ratio", row.get("prefix_rate", 0)))
    checks.append(prefix is not None and abs(prefix - float(scenario["prefix_rate"])) <= 1e-6)
    return all(checks)


def find_matching_metric(unit_dir: Path, scenario: dict[str, Any]) -> tuple[Path | None, dict[str, str] | None]:
    for metrics_path in sorted(unit_dir.rglob("core_metrics.csv"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            with metrics_path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row_matches(row, scenario):
                        return metrics_path, row
        except OSError:
            continue
    return None, None


def summary_row(
    config: dict[str, Any],
    scenario: dict[str, Any],
    repetition: int,
    unit_dir: Path,
    reset_success: bool | None,
    exit_code: int | None,
) -> dict[str, Any]:
    metrics_path, row = find_matching_metric(unit_dir, scenario)
    if exit_code is None:
        verdict, reason = "INCOMPLETE", "missing benchmark exit code"
    elif exit_code != 0:
        verdict, reason = "INVALID", f"benchmark exited with code {exit_code}"
    elif config["cache"]["policy"] != "warm-reuse" and reset_success is not True:
        verdict, reason = "INVALID", "required prefix-cache reset did not succeed"
    elif row is None:
        verdict, reason = "INCOMPLETE", "no matching row in core_metrics.csv"
    elif (as_int(row.get("failed_requests")) or 0) != 0:
        verdict, reason = "INVALID", f"failed_requests={row.get('failed_requests')}"
    else:
        verdict, reason = "VALID", ""
    result: dict[str, Any] = {
        "experiment_id": config["experiment_id"],
        "arm_id": config["arm"]["id"],
        "parent_arm": config["arm"].get("parent"),
        "intended_delta": config["arm"]["intended_delta"],
        "scenario_id": scenario["id"],
        "repetition": repetition,
        "verdict": verdict,
        "reason": reason,
        "cache_policy": config["cache"]["policy"],
        "cache_reset_success": reset_success,
        "input_length": scenario["input_tokens"],
        "output_length": scenario["output_tokens"],
        "num_prompts": scenario["num_prompts"],
        "max_concurrency": scenario["max_concurrency"],
        "prefix_ratio": scenario["prefix_rate"],
        "metrics_file": str(metrics_path.resolve()) if metrics_path else "",
        "unit_dir": str(unit_dir.resolve()),
    }
    if row:
        for field in SUMMARY_FIELDS:
            if field in row:
                result[field] = row[field]
    return result


def write_summary(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def execute(config: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    validate_config(config, for_run=True)
    bench = config["benchmark"]
    source = Path(bench["script_path"])
    if not source.is_file():
        raise ConfigError(f"benchmark script does not exist: {source}")
    actual_source_hash = sha256_file(source)
    expected_hash = bench.get("script_sha256")
    if expected_hash and actual_source_hash.lower() != str(expected_hash).lower():
        raise ConfigError(
            f"benchmark script SHA256 mismatch: expected {expected_hash}, got {actual_source_hash}"
        )
    headers = api_headers(config)
    timeout = float(bench.get("http_timeout_seconds", 30))
    models = http_json(models_url(str(bench["base_url"])), method="GET", headers=headers, timeout=timeout)
    if not isinstance(models, dict) or not isinstance(models.get("data"), list) or not models["data"]:
        raise RuntimeError("/v1/models did not return a non-empty data array")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = (
        Path(bench["result_root"])
        / str(config["experiment_id"])
        / str(config["arm"]["id"])
        / stamp
    )
    root.mkdir(parents=True, exist_ok=False)
    runnable = root / "inputs" / source.name
    source_hash, runnable_hash, had_bom = sanitize_script(source, runnable)
    manifest = {
        "schema_version": 1,
        "created_utc": stamp,
        "config": config,
        "script_source_sha256": source_hash,
        "script_runnable_sha256": runnable_hash,
        "source_had_utf8_bom": had_bom,
        "models_response": models,
        "status": "RUNNING",
    }
    write_json(root / "manifest.json", manifest)
    rows: list[dict[str, Any]] = []
    try:
        for repetition in range(1, config["repetitions"] + 1):
            for scenario in config["scenarios"]:
                unit_dir = root / str(scenario["id"]) / f"rep-{repetition:02d}"
                unit_dir.mkdir(parents=True, exist_ok=False)
                reset_success: bool | None = None
                reset_response: Any = None
                if config["cache"]["policy"] != "warm-reuse":
                    reset_response = http_json(
                        reset_url(str(bench["base_url"])),
                        method="POST",
                        headers=headers,
                        timeout=timeout,
                    )
                    reset_success = isinstance(reset_response, dict) and reset_response.get("success") is True
                    write_json(unit_dir / "cache-reset.json", reset_response)
                    if not reset_success:
                        row = summary_row(config, scenario, repetition, unit_dir, False, None)
                        row["verdict"] = "INVALID"
                        row["reason"] = "reset endpoint did not return success=true"
                        rows.append(row)
                        raise RuntimeError(row["reason"])
                command = build_command(config, scenario, str(runnable), str(unit_dir))
                (unit_dir / "command.sh").write_text(shlex.join(command) + "\n", encoding="utf-8")
                unit_manifest = {
                    "scenario": scenario,
                    "repetition": repetition,
                    "cache_policy": config["cache"]["policy"],
                    "cache_reset_success": reset_success,
                    "cache_reset_response": reset_response,
                    "command": command,
                    "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
                write_json(unit_dir / "unit-manifest.json", unit_manifest)
                exit_code = run_stream(command, unit_dir / "runner.log")
                unit_manifest["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
                unit_manifest["exit_code"] = exit_code
                row = summary_row(config, scenario, repetition, unit_dir, reset_success, exit_code)
                unit_manifest["verdict"] = row["verdict"]
                unit_manifest["reason"] = row["reason"]
                write_json(unit_dir / "unit-manifest.json", unit_manifest)
                rows.append(row)
                write_summary(root / "mode_a_summary.csv", rows)
                if row["verdict"] != "VALID":
                    raise RuntimeError(
                        f"unit {scenario['id']} repetition {repetition} is {row['verdict']}: {row['reason']}"
                    )
        manifest["status"] = "VALID"
    except Exception as exc:
        manifest["status"] = "INVALID"
        manifest["failure"] = str(exc)
        raise
    finally:
        manifest["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(root / "manifest.json", manifest)
        write_summary(root / "mode_a_summary.csv", rows)
    return root, rows


def validate_existing(config: dict[str, Any], result_dir: Path) -> list[dict[str, Any]]:
    validate_config(config)
    if not result_dir.is_dir():
        raise ConfigError(f"result directory does not exist: {result_dir}")
    rows: list[dict[str, Any]] = []
    for repetition in range(1, config["repetitions"] + 1):
        for scenario in config["scenarios"]:
            unit_dir = result_dir / str(scenario["id"]) / f"rep-{repetition:02d}"
            unit_manifest_path = unit_dir / "unit-manifest.json"
            reset_success: bool | None = None
            exit_code: int | None = None
            if unit_manifest_path.is_file():
                unit_manifest = read_json(unit_manifest_path)
                reset_success = unit_manifest.get("cache_reset_success")
                exit_code = as_int(unit_manifest.get("exit_code"))
            rows.append(summary_row(config, scenario, repetition, unit_dir, reset_success, exit_code))
    write_summary(result_dir / "mode_a_summary.csv", rows)
    return rows


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    subcommands = top.add_subparsers(dest="action", required=True)
    for name in ("plan", "dry-run"):
        command = subcommands.add_parser(name, help="render the resolved plan without writes or requests")
        command.add_argument("--config", required=True, type=Path)
    run = subcommands.add_parser("run", help="execute the fixed-scenario matrix on this host")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument(
        "--allow-execute",
        action="store_true",
        help="required acknowledgement that benchmark requests may be sent",
    )
    validate = subcommands.add_parser("validate", help="validate an existing run without network requests")
    validate.add_argument("--config", required=True, type=Path)
    validate.add_argument("--result-dir", required=True, type=Path)
    return top


def main() -> int:
    args = parser().parse_args()
    try:
        config = read_json(args.config)
        resolve_config_paths(config, args.config)
        if args.action in {"plan", "dry-run"}:
            print(json.dumps(plan(config), ensure_ascii=False, indent=2))
            return 0
        if args.action == "run":
            if not args.allow_execute:
                print("refusing to execute without --allow-execute", file=sys.stderr)
                return 2
            root, rows = execute(config)
            print(json.dumps({"result_dir": str(root), "results": rows}, ensure_ascii=False, indent=2))
            return 0
        rows = validate_existing(config, args.result_dir)
        print(json.dumps({"result_dir": str(args.result_dir), "results": rows}, ensure_ascii=False, indent=2))
        return 0 if all(row["verdict"] == "VALID" for row in rows) else 3
    except (ConfigError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
