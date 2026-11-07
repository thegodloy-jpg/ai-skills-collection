#!/usr/bin/env python3
"""Resolve and allocate durable records in the DAY0 model workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import yaml


DEFAULT_WORKSPACE = Path(r"F:\DAY0")
MODEL_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
MODELS_DIRNAME = "模型"

KIND_TO_DIR = {
    "baseline": "基线",
    "experiment": "实验",
    "incident": "故障",
    "report": "报告",
}
KIND_TO_PREFIX = {
    "baseline": "b",
    "experiment": "e",
    "incident": "inc",
    "report": "r",
}
RECORD_SUBDIRS = (
    "命令",
    "环境",
    "服务日志",
    "基准数据",
    "性能剖析",
    "分析",
    "参考资料",
)


class Day0Error(RuntimeError):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def iso_now() -> str:
    return now_shanghai().isoformat(timespec="seconds")


def normalize_key(value: str) -> str:
    normalized = value.strip().strip('"').strip("'").replace("\\", "/")
    return normalized.rstrip("/").casefold()


def query_keys(value: str) -> set[str]:
    key = normalize_key(value)
    keys = {key}
    if "/" in key:
        keys.add(key.rsplit("/", 1)[-1])
    return keys


def validate_slug(value: str, label: str) -> None:
    if not SLUG_RE.fullmatch(value):
        raise Day0Error(
            f"{label} must use lowercase ASCII letters, digits, dots, and hyphens: {value}",
            2,
        )


def resolve_workspace(raw: str | None) -> Path:
    chosen = raw or os.environ.get("DAY0_WORKSPACE_ROOT") or str(DEFAULT_WORKSPACE)
    root = Path(chosen).expanduser().resolve()
    if not (root / "workspace.yaml").is_file():
        raise Day0Error(f"DAY0 workspace.yaml not found: {root}", 2)
    if not (root / "catalog.yaml").is_file():
        raise Day0Error(f"DAY0 catalog.yaml not found: {root}", 2)
    return root


def ensure_within(root: Path, candidate: Path, label: str) -> Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise Day0Error(f"{label} escapes DAY0 workspace: {resolved}", 2) from exc
    return resolved


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Day0Error(f"Required file not found: {path}", 2) from exc
    except yaml.YAMLError as exc:
        raise Day0Error(f"Invalid YAML in {path}: {exc}", 2) from exc
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise Day0Error(f"Expected a YAML mapping in {path}", 2)
    return value


def atomic_write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@contextmanager
def workspace_lock(root: Path) -> Iterator[None]:
    lock_path = root / ".day0.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        details = ""
        try:
            details = lock_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        suffix = f" ({details})" if details else ""
        raise Day0Error(f"DAY0 workspace is locked: {lock_path}{suffix}", 4) from exc
    try:
        payload = f"pid={os.getpid()} created_at={iso_now()}\n".encode("utf-8")
        os.write(descriptor, payload)
        os.close(descriptor)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_catalog(root: Path) -> dict[str, Any]:
    catalog = read_yaml(root / "catalog.yaml")
    models = catalog.get("models")
    if not isinstance(models, list):
        raise Day0Error("catalog.yaml must contain a models list", 2)
    return catalog


def model_keys(entry: dict[str, Any]) -> set[str]:
    values: list[str] = []
    for field in ("id", "display_name", "path"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            values.append(value)
    aliases = entry.get("aliases", [])
    if isinstance(aliases, list):
        values.extend(value for value in aliases if isinstance(value, str) and value.strip())
    result = {normalize_key(value) for value in values}
    for value in values:
        normalized = normalize_key(value)
        if "/" in normalized:
            result.add(normalized.rsplit("/", 1)[-1])
    return result


def base_model_keys(entry: dict[str, Any]) -> set[str]:
    values: list[str] = []
    base_model_id = entry.get("base_model_id")
    if isinstance(base_model_id, str) and base_model_id.strip():
        values.append(base_model_id)
    aliases = entry.get("base_aliases", [])
    if isinstance(aliases, list):
        values.extend(value for value in aliases if isinstance(value, str) and value.strip())
    result = {normalize_key(value) for value in values}
    for value in values:
        normalized = normalize_key(value)
        if "/" in normalized:
            result.add(normalized.rsplit("/", 1)[-1])
    return result


def find_models(catalog: dict[str, Any], query: str) -> list[dict[str, Any]]:
    wanted = query_keys(query)
    return [
        entry
        for entry in catalog["models"]
        if isinstance(entry, dict) and wanted.intersection(model_keys(entry))
    ]


def find_base_models(catalog: dict[str, Any], query: str) -> list[dict[str, Any]]:
    wanted = query_keys(query)
    return [
        entry
        for entry in catalog["models"]
        if isinstance(entry, dict) and wanted.intersection(base_model_keys(entry))
    ]


def resolve_model(root: Path, query: str) -> dict[str, Any]:
    catalog = load_catalog(root)
    matches = find_models(catalog, query)
    if not matches:
        base_matches = find_base_models(catalog, query)
        if base_matches:
            choices = ", ".join(
                f"{item.get('id')} [{item.get('scenario_label') or item.get('scenario_id')}]"
                for item in base_matches
            )
            raise Day0Error(
                f"Model scenario required for '{query}'. Candidates: {choices}", 3
            )
        raise Day0Error(f"No registered DAY0 model matches: {query}", 2)
    if len(matches) > 1:
        choices = ", ".join(str(item.get("id")) for item in matches)
        raise Day0Error(f"Ambiguous DAY0 model '{query}': {choices}", 3)
    entry = matches[0]
    relative = entry.get("path")
    if not isinstance(relative, str) or not relative:
        raise Day0Error(f"Model entry has no path: {entry.get('id')}", 2)
    model_root = ensure_within(root, root / relative, "Model path")
    if not model_root.is_dir():
        raise Day0Error(f"Registered model directory does not exist: {model_root}", 2)
    return {**entry, "resolved_path": str(model_root)}


def print_model(entry: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return
    print("STATE=RESOLVED")
    print(f"MODEL_ID={entry['id']}")
    print(f"BASE_MODEL_ID={entry['base_model_id']}")
    print(f"SCENARIO_ID={entry['scenario_id']}")
    print(f"SCENARIO_LABEL={entry['scenario_label']}")
    print(f"DISPLAY_NAME={entry['display_name']}")
    print(f"MODEL_ROOT={entry['resolved_path']}")


def command_status(args: argparse.Namespace) -> int:
    root = resolve_workspace(args.workspace_root)
    catalog = load_catalog(root)
    result = []
    for item in catalog["models"]:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": item.get("id"),
                "base_model_id": item.get("base_model_id"),
                "scenario_id": item.get("scenario_id"),
                "scenario_label": item.get("scenario_label"),
                "display_name": item.get("display_name"),
                "status": item.get("status"),
                "path": str(root / str(item.get("path", ""))),
            }
        )
    if args.json:
        print(json.dumps({"workspace": str(root), "models": result}, ensure_ascii=False, indent=2))
    else:
        print(f"WORKSPACE_ROOT={root}")
        print(f"MODEL_COUNT={len(result)}")
        for item in result:
            print(
                f"MODEL={item['id']} SCENARIO={item['scenario_id']} "
                f"STATUS={item['status']} "
                f"PATH={item['path']}"
            )
    return 0


def command_resolve(args: argparse.Namespace) -> int:
    root = resolve_workspace(args.workspace_root)
    print_model(resolve_model(root, args.model), args.json)
    return 0


def unique_aliases(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        key = normalize_key(cleaned)
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def command_register_model(args: argparse.Namespace) -> int:
    root = resolve_workspace(args.workspace_root)
    validate_slug(args.id, "Model ID")
    validate_slug(args.base_model_id, "Base model ID")
    validate_slug(args.scenario_id, "Scenario ID")
    if not args.id.startswith(f"{args.base_model_id}-"):
        raise Day0Error(
            "Model ID must begin with '<base-model-id>-' and include the scenario", 2
        )
    scenario_token = args.scenario_id.removeprefix("ascend-")
    if scenario_token not in args.id:
        raise Day0Error(
            f"Model ID must include hardware scenario token '{scenario_token}'", 2
        )
    aliases = unique_aliases(args.alias or [])
    base_aliases = unique_aliases(args.base_alias or [])
    proposed = {
        "id": args.id,
        "base_model_id": args.base_model_id,
        "scenario_id": args.scenario_id,
        "scenario_label": args.scenario_label,
        "display_name": args.display_name,
        "path": f"{MODELS_DIRNAME}/{args.id}",
        "status": "active",
        "aliases": aliases,
        "base_aliases": base_aliases,
    }
    catalog = load_catalog(root)
    proposed_keys = model_keys(proposed)
    conflicts = [
        str(entry.get("id"))
        for entry in catalog["models"]
        if isinstance(entry, dict) and proposed_keys.intersection(model_keys(entry))
    ]
    if conflicts:
        raise Day0Error(f"Model identity conflicts with: {', '.join(conflicts)}", 3)
    model_root = ensure_within(root, root / proposed["path"], "Model path")
    if model_root.exists():
        raise Day0Error(f"Model directory already exists: {model_root}", 3)
    if args.dry_run:
        print("STATE=DRY_RUN")
        print(f"MODEL_ID={args.id}")
        print(f"BASE_MODEL_ID={args.base_model_id}")
        print(f"SCENARIO_ID={args.scenario_id}")
        print(f"MODEL_ROOT={model_root}")
        return 0

    with workspace_lock(root):
        catalog = load_catalog(root)
        conflicts = [
            str(entry.get("id"))
            for entry in catalog["models"]
            if isinstance(entry, dict) and proposed_keys.intersection(model_keys(entry))
        ]
        if conflicts:
            raise Day0Error(f"Model identity conflicts with: {', '.join(conflicts)}", 3)
        if model_root.exists():
            raise Day0Error(f"Model directory already exists: {model_root}", 3)

        staging = root / MODELS_DIRNAME / f".tmp-{args.id}-{uuid.uuid4().hex[:8]}"
        registered = False
        try:
            staging.mkdir(parents=True)
            for directory in KIND_TO_DIR.values():
                (staging / directory).mkdir()
            model_manifest = {
                "schema_version": 1,
                "model_id": args.id,
                "base_model_id": args.base_model_id,
                "scenario_id": args.scenario_id,
                "scenario_label": args.scenario_label,
                "display_name": args.display_name,
                "status": "active",
                "engine_family": args.engine_family,
                "accelerator_family": args.accelerator_family,
                "aliases": aliases,
                "base_aliases": base_aliases,
                "legacy_sources": [],
                "notes": [
                    "Register a baseline or experiment only after its evidence boundary is recorded."
                ],
            }
            state = {
                "schema_version": 1,
                "model_id": args.id,
                "accepted_baseline_id": None,
                "best_known_experiment_id": None,
                "open_incident_ids": [],
                "last_validated_at": None,
            }
            atomic_write_yaml(staging / "model.yaml", model_manifest)
            atomic_write_yaml(staging / "state.yaml", state)
            staging.replace(model_root)
            catalog["models"].append(proposed)
            atomic_write_yaml(root / "catalog.yaml", catalog)
            registered = True
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            if model_root.exists() and not registered:
                shutil.rmtree(model_root)
            raise

    print("STATE=REGISTERED")
    print(f"MODEL_ID={args.id}")
    print(f"MODEL_ROOT={model_root}")
    return 0


def next_record_path(model_root: Path, kind: str, slug: str, timestamp: str) -> tuple[str, Path]:
    prefix = KIND_TO_PREFIX[kind]
    base = f"{prefix}-{timestamp}-{slug}"
    category = model_root / KIND_TO_DIR[kind]
    candidate = category / base
    counter = 2
    while candidate.exists():
        candidate = category / f"{base}-{counter:02d}"
        counter += 1
    return candidate.name, candidate


def command_create_record(args: argparse.Namespace) -> int:
    root = resolve_workspace(args.workspace_root)
    validate_slug(args.slug, "Record slug")
    entry = resolve_model(root, args.model)
    model_root = Path(entry["resolved_path"])
    timestamp = now_shanghai().strftime("%Y%m%d-%H%M%S")
    record_id, target = next_record_path(model_root, args.kind, args.slug, timestamp)
    target = ensure_within(root, target, "Record path")
    if args.dry_run:
        print("STATE=DRY_RUN")
        print(f"MODEL_ID={entry['id']}")
        print(f"RECORD_ID={record_id}")
        print(f"RECORD_DIR={target}")
        return 0

    with workspace_lock(root):
        entry = resolve_model(root, args.model)
        model_root = Path(entry["resolved_path"])
        record_id, target = next_record_path(model_root, args.kind, args.slug, timestamp)
        target = ensure_within(root, target, "Record path")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".tmp-{record_id}-{uuid.uuid4().hex[:8]}"
        try:
            staging.mkdir()
            for directory in RECORD_SUBDIRS:
                (staging / directory).mkdir()
            manifest = {
                "schema_version": 1,
                "record_id": record_id,
                "kind": args.kind,
                "title": args.title,
                "model_id": entry["id"],
                "created_at": iso_now(),
                "status": "collecting",
                "evidence_state": "incomplete",
                "parent_baseline_id": args.parent_baseline,
                "changed_variables": args.changed_variable or [],
                "source_context": args.source_context,
            }
            evidence = {
                "schema_version": 1,
                "record_id": record_id,
                "policy": "reference-canonical-artifacts",
                "artifacts": [],
            }
            atomic_write_yaml(staging / "manifest.yaml", manifest)
            atomic_write_yaml(staging / "evidence-index.yaml", evidence)
            staging.replace(target)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    print("STATE=CREATED")
    print(f"MODEL_ID={entry['id']}")
    print(f"RECORD_ID={record_id}")
    print(f"RECORD_DIR={target}")
    return 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_attach(args: argparse.Namespace) -> int:
    root = resolve_workspace(args.workspace_root)
    record_dir = ensure_within(root, Path(args.record_dir), "Record directory")
    manifest_path = record_dir / "manifest.yaml"
    evidence_path = record_dir / "evidence-index.yaml"
    if not manifest_path.is_file():
        raise Day0Error(f"Record manifest not found: {manifest_path}", 2)
    artifact_text = args.artifact.strip()
    if not artifact_text:
        raise Day0Error("Artifact reference must not be empty", 2)

    metadata: dict[str, Any] = {
        "role": args.role,
        "source": artifact_text,
        "registered_at": iso_now(),
        "note": args.note,
    }
    local_candidate = Path(artifact_text)
    if local_candidate.exists() and local_candidate.is_file():
        local_resolved = local_candidate.resolve()
        metadata["exists_at_registration"] = True
        metadata["size_bytes"] = local_resolved.stat().st_size
        metadata["sha256"] = args.sha256 or (sha256_file(local_resolved) if args.hash else None)
    else:
        metadata["exists_at_registration"] = False
        metadata["size_bytes"] = None
        metadata["sha256"] = args.sha256

    if args.dry_run:
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        print("STATE=DRY_RUN")
        return 0

    with workspace_lock(root):
        evidence = read_yaml(evidence_path)
        artifacts = evidence.setdefault("artifacts", [])
        if not isinstance(artifacts, list):
            raise Day0Error(f"artifacts must be a list: {evidence_path}", 2)
        for existing in artifacts:
            if (
                isinstance(existing, dict)
                and existing.get("role") == args.role
                and existing.get("source") == artifact_text
            ):
                print("STATE=ALREADY_REGISTERED")
                print(f"EVIDENCE_INDEX={evidence_path}")
                return 0
        artifacts.append(metadata)
        atomic_write_yaml(evidence_path, evidence)

    print("STATE=ATTACHED")
    print(f"EVIDENCE_INDEX={evidence_path}")
    return 0


def validate_workspace(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        catalog = load_catalog(root)
    except Day0Error as exc:
        return [str(exc)], warnings

    identity_owner: dict[str, str] = {}
    seen_ids: set[str] = set()
    registered_model_roots: set[Path] = set()
    for position, entry in enumerate(catalog["models"]):
        if not isinstance(entry, dict):
            errors.append(f"catalog models[{position}] is not a mapping")
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not MODEL_ID_RE.fullmatch(model_id):
            errors.append(f"invalid model id at catalog models[{position}]: {model_id}")
            continue
        if model_id in seen_ids:
            errors.append(f"duplicate model id: {model_id}")
        seen_ids.add(model_id)
        base_model_id = entry.get("base_model_id")
        scenario_id = entry.get("scenario_id")
        scenario_label = entry.get("scenario_label")
        if not isinstance(base_model_id, str) or not MODEL_ID_RE.fullmatch(base_model_id):
            errors.append(f"invalid base model id for {model_id}: {base_model_id}")
        elif not model_id.startswith(f"{base_model_id}-"):
            errors.append(f"model ID does not start with base model ID: {model_id}")
        if not isinstance(scenario_id, str) or not MODEL_ID_RE.fullmatch(scenario_id):
            errors.append(f"invalid scenario id for {model_id}: {scenario_id}")
        elif scenario_id.removeprefix("ascend-") not in model_id:
            errors.append(f"model ID does not include scenario: {model_id}")
        if not isinstance(scenario_label, str) or not scenario_label.strip():
            errors.append(f"scenario label missing for {model_id}")
        for key in model_keys(entry):
            owner = identity_owner.get(key)
            if owner and owner != model_id:
                errors.append(f"ambiguous identity key '{key}': {owner}, {model_id}")
            else:
                identity_owner[key] = model_id

        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            errors.append(f"model {model_id} has no path")
            continue
        if Path(relative).name != model_id:
            errors.append(f"model directory name must equal model ID: {relative}")
        try:
            model_root = ensure_within(root, root / relative, f"model {model_id} path")
        except Day0Error as exc:
            errors.append(str(exc))
            continue
        if not model_root.is_dir():
            errors.append(f"model directory missing: {model_root}")
            continue
        registered_model_roots.add(model_root)
        model_manifest_path = model_root / "model.yaml"
        state_path = model_root / "state.yaml"
        if not model_manifest_path.is_file():
            errors.append(f"model manifest missing: {model_manifest_path}")
        else:
            try:
                manifest = read_yaml(model_manifest_path)
                if manifest.get("model_id") != model_id:
                    errors.append(f"model ID mismatch in {model_manifest_path}")
                if manifest.get("base_model_id") != base_model_id:
                    errors.append(f"base model ID mismatch in {model_manifest_path}")
                if manifest.get("scenario_id") != scenario_id:
                    errors.append(f"scenario ID mismatch in {model_manifest_path}")
                if manifest.get("scenario_label") != scenario_label:
                    errors.append(f"scenario label mismatch in {model_manifest_path}")
                catalog_aliases = {
                    normalize_key(value)
                    for value in entry.get("aliases", [])
                    if isinstance(value, str)
                }
                manifest_aliases = {
                    normalize_key(value)
                    for value in manifest.get("aliases", [])
                    if isinstance(value, str)
                }
                if catalog_aliases != manifest_aliases:
                    errors.append(f"model alias mismatch in {model_manifest_path}")
                catalog_base_aliases = {
                    normalize_key(value)
                    for value in entry.get("base_aliases", [])
                    if isinstance(value, str)
                }
                manifest_base_aliases = {
                    normalize_key(value)
                    for value in manifest.get("base_aliases", [])
                    if isinstance(value, str)
                }
                if catalog_base_aliases != manifest_base_aliases:
                    errors.append(f"base model alias mismatch in {model_manifest_path}")
            except Day0Error as exc:
                errors.append(str(exc))
        if not state_path.is_file():
            errors.append(f"model state missing: {state_path}")
        else:
            try:
                state = read_yaml(state_path)
                if state.get("model_id") != model_id:
                    errors.append(f"model state ID mismatch in {state_path}")
            except Day0Error as exc:
                errors.append(str(exc))

        for kind, directory in KIND_TO_DIR.items():
            category = model_root / directory
            if not category.is_dir():
                errors.append(f"record category missing: {category}")
                continue
            for record in sorted(path for path in category.iterdir() if path.is_dir()):
                manifest_path = record / "manifest.yaml"
                if not manifest_path.is_file():
                    errors.append(f"record manifest missing: {manifest_path}")
                    continue
                try:
                    record_manifest = read_yaml(manifest_path)
                except Day0Error as exc:
                    errors.append(str(exc))
                    continue
                if record_manifest.get("record_id") != record.name:
                    errors.append(f"record ID mismatch: {manifest_path}")
                if record_manifest.get("model_id") != model_id:
                    errors.append(f"record model mismatch: {manifest_path}")
                if record_manifest.get("kind") != kind:
                    errors.append(f"record kind mismatch: {manifest_path}")
                for required in RECORD_SUBDIRS:
                    if not (record / required).is_dir():
                        errors.append(f"record directory missing: {record / required}")

    models_root = root / MODELS_DIRNAME
    if models_root.is_dir():
        for candidate in sorted(path for path in models_root.iterdir() if path.is_dir()):
            if candidate.name.startswith(".tmp-"):
                warnings.append(f"temporary model directory remains: {candidate}")
            elif candidate.resolve() not in registered_model_roots:
                warnings.append(f"unregistered model directory: {candidate}")

    legacy_path = root / "legacy-sources.yaml"
    if legacy_path.is_file():
        try:
            legacy = read_yaml(legacy_path)
            for source in legacy.get("sources", []):
                if not isinstance(source, dict):
                    continue
                relative = source.get("path")
                if isinstance(relative, str) and not (root / relative).exists():
                    warnings.append(f"legacy source missing: {root / relative}")
                if source.get("classification") == "pending":
                    warnings.append(f"legacy source pending classification: {relative}")
        except Day0Error as exc:
            errors.append(str(exc))
    else:
        warnings.append(f"legacy inventory missing: {legacy_path}")
    return errors, warnings


def command_validate(args: argparse.Namespace) -> int:
    root = resolve_workspace(args.workspace_root)
    errors, warnings = validate_workspace(root)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"ERROR_COUNT={len(errors)}")
    print(f"WARNING_COUNT={len(warnings)}")
    print("STATE=VALID" if not errors else "STATE=INVALID")
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", help="Override the DAY0 workspace root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="List registered models")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    resolve = subparsers.add_parser("resolve", help="Resolve an exact model identity")
    resolve.add_argument("--model", required=True)
    resolve.add_argument("--json", action="store_true")
    resolve.set_defaults(func=command_resolve)

    register = subparsers.add_parser("register-model", help="Register a new canonical model")
    register.add_argument("--id", required=True)
    register.add_argument("--base-model-id", required=True)
    register.add_argument("--scenario-id", required=True)
    register.add_argument("--scenario-label", required=True)
    register.add_argument("--display-name", required=True)
    register.add_argument("--alias", action="append")
    register.add_argument("--base-alias", action="append")
    register.add_argument("--engine-family")
    register.add_argument("--accelerator-family")
    register.add_argument("--dry-run", action="store_true")
    register.set_defaults(func=command_register_model)

    create = subparsers.add_parser("create-record", help="Allocate a durable record directory")
    create.add_argument("--model", required=True)
    create.add_argument("--kind", required=True, choices=sorted(KIND_TO_DIR))
    create.add_argument("--slug", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--parent-baseline")
    create.add_argument("--changed-variable", action="append")
    create.add_argument("--source-context")
    create.add_argument("--dry-run", action="store_true")
    create.set_defaults(func=command_create_record)

    attach = subparsers.add_parser("attach", help="Register an evidence reference without copying")
    attach.add_argument("--record-dir", required=True)
    attach.add_argument("--artifact", required=True)
    attach.add_argument(
        "--role",
        required=True,
        choices=(
            "service-log",
            "benchmark",
            "profile",
            "command",
            "environment",
            "analysis",
            "image",
            "model",
            "other",
        ),
    )
    attach.add_argument("--note")
    attach.add_argument("--sha256")
    attach.add_argument("--hash", action="store_true", help="Hash an existing local file")
    attach.add_argument("--dry-run", action="store_true")
    attach.set_defaults(func=command_attach)

    validate = subparsers.add_parser("validate", help="Validate registry and record structure")
    validate.set_defaults(func=command_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Day0Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
