#!/usr/bin/env python3
"""Install bundled skills from this checkout without making network requests."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent


def _load_installer():
    """Reuse the bundled official installer's validation and copy routines."""
    scripts = REPO_ROOT / "skills" / "skill-installer" / "scripts"
    spec = importlib.util.spec_from_file_location(
        "_collection_upstream_installer", scripts / "install-skill-from-github.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the bundled official skill installer.")
    module = importlib.util.module_from_spec(spec)
    # dataclasses needs its module registered; github_utils is a sibling import.
    sys.modules[spec.name] = module
    sys.path.insert(0, str(scripts))
    previous_bytecode_setting = sys.dont_write_bytecode
    # 导入帮助函数也不生成缓存，避免改动来源文件集合而破坏 SHA256 预检。
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting
        sys.path.pop(0)
    return module


def _select_skills(entries, requested, error_type):
    by_id = {entry["id"]: entry for entry in entries}
    selected = []
    visited = set()
    visiting = set()

    def visit(identifier):
        entry = by_id.get(identifier)
        if entry is None:
            matches = [entry for entry in entries if entry["name"] == identifier]
            if len(matches) != 1:
                raise error_type(f"Unknown or ambiguous skill: {identifier}")
            entry = matches[0]
        identifier = entry["id"]
        if entry["distribution"] != "bundled":
            source = entry.get("source", {})
            official = source.get("url") or (
                "the official Codex plugin/skill entry for "
                + source.get("plugin", identifier)
            )
            raise error_type(
                f"{identifier} requires official installation and is not bundled. "
                f"Use {official}."
            )
        if identifier in visiting:
            raise error_type(f"Dependency cycle detected: {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        # 别名技能依赖共享正文；递归补齐并去重，避免只安装入口后无法使用。
        for dependency in entry.get("dependencies", []):
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
        selected.append(entry)

    identifiers = requested if requested is not None else [
        entry["id"] for entry in entries if entry["distribution"] == "bundled"
    ]
    for identifier in identifiers:
        visit(identifier)
    return selected


def _preflight(selected, destination, installer):
    source_root = (REPO_ROOT / "skills").resolve()
    destination = destination.expanduser().resolve()
    if destination == source_root or source_root in destination.parents:
        raise installer.InstallError("Destination must be outside this checkout's skills directory.")
    if destination.exists() and not destination.is_dir():
        raise installer.InstallError(f"Destination is not a directory: {destination}")

    planned = []
    targets = set()
    # 所有来源、清单和目标统一预检后才复制；已存在任一目标就整批停止，不覆盖。
    # 预检覆盖可预知失败，不能代替文件系统事务或阻止其他进程随后修改目标。
    for entry in selected:
        name = entry["name"]
        installer._validate_skill_name(name)
        relative = entry["path"]
        installer._validate_relative_path(relative)
        source = REPO_ROOT / relative
        resolved = source.resolve()
        if source_root not in resolved.parents:
            raise installer.InstallError(f"Source must be inside skills/: {relative}")
        installer._validate_skill(str(source), str(REPO_ROOT))

        expected = entry.get("files_sha256")
        if not isinstance(expected, dict) or not expected:
            raise installer.InstallError(f"Missing files_sha256 manifest for {entry['id']}.")
        actual = {
            path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source.rglob("*") if path.is_file()
        }
        if actual != expected:
            raise installer.InstallError(f"File inventory or SHA256 mismatch for {entry['id']}.")

        target = destination / name
        if target in targets or os.path.lexists(target):
            raise installer.InstallError(f"Destination already exists or is duplicated: {target}")
        targets.add(target)
        planned.append((source, target))
    return planned


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Install all bundled skills only")
    selection.add_argument("--skills", nargs="+", metavar="NAME", help="Install named skills and dependencies")
    parser.add_argument(
        "--dest", type=Path,
        default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills",
        help="Destination skills directory (default: $CODEX_HOME/skills or ~/.codex/skills)",
    )
    args = parser.parse_args(argv)
    installer = _load_installer()
    try:
        catalog = json.loads((REPO_ROOT / "catalog.json").read_text(encoding="utf-8-sig"))
        selected = _select_skills(catalog["skills"], args.skills, installer.InstallError)
        planned = _preflight(selected, args.dest, installer)
        for source, target in planned:
            installer._copy_skill(str(source), str(target))
            print(f"Installed {target.name} to {target}")
        print(f"Installed {len(planned)} bundled skills. Restart Codex to load them.")
        return 0
    except (installer.InstallError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
