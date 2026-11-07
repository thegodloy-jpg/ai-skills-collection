#!/usr/bin/env python3
"""Isolated behavioral smoke test for day0ctl.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


SCRIPT = Path(__file__).with_name("day0ctl.py")


def run(root: Path, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--workspace-root",
        str(root),
        *arguments,
    ]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=env, check=False
    )
    if result.returncode != expected:
        raise AssertionError(
            f"unexpected exit {result.returncode}, expected {expected}\n"
            f"command={command}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="day0-workspace-smoke-") as temporary:
        root = Path(temporary)
        (root / "workspace.yaml").write_text(
            "schema_version: 3\nworkspace_name: smoke\n", encoding="utf-8"
        )
        (root / "catalog.yaml").write_text(
            "schema_version: 3\nmodels: []\n", encoding="utf-8"
        )
        (root / "模型").mkdir()

        run(
            root,
            "register-model",
            "--id",
            "model-a-w8a8-910c-dual-node",
            "--base-model-id",
            "model-a-w8a8",
            "--scenario-id",
            "ascend-910c-dual-node",
            "--scenario-label",
            "Ascend 910C dual-node",
            "--display-name",
            "Model A W8A8 / Ascend 910C dual-node",
            "--alias",
            "served-a-910c-dual",
            "--base-alias",
            "served-a",
        )
        resolved = run(root, "resolve", "--model", "served-a-910c-dual", "--json")
        payload = json.loads(resolved.stdout)
        assert payload["id"] == "model-a-w8a8-910c-dual-node"
        assert payload["scenario_id"] == "ascend-910c-dual-node"

        scenario_required = run(root, "resolve", "--model", "served-a", expected=3)
        assert "scenario required" in scenario_required.stderr.casefold()

        run(
            root,
            "register-model",
            "--id",
            "model-b-w8a8-910b",
            "--base-model-id",
            "model-b-w8a8",
            "--scenario-id",
            "ascend-910b",
            "--scenario-label",
            "Ascend 910B",
            "--display-name",
            "Model B W8A8 / Ascend 910B",
            "--alias",
            "served-a-910c-dual",
            expected=3,
        )

        created = run(
            root,
            "create-record",
            "--model",
            "model-a-w8a8-910c-dual-node",
            "--kind",
            "experiment",
            "--slug",
            "feature-on",
            "--title",
            "Feature on",
            "--changed-variable",
            "feature=true",
        )
        record_line = next(
            line for line in created.stdout.splitlines() if line.startswith("RECORD_DIR=")
        )
        record_dir = Path(record_line.split("=", 1)[1])
        assert (record_dir / "manifest.yaml").is_file()
        assert all((record_dir / name).is_dir() for name in (
            "命令",
            "环境",
            "服务日志",
            "基准数据",
            "性能剖析",
            "分析",
            "参考资料",
        ))

        attached = run(
            root,
            "attach",
            "--record-dir",
            str(record_dir),
            "--artifact",
            "host-a:/var/log/engine.log",
            "--role",
            "service-log",
        )
        assert "STATE=ATTACHED" in attached.stdout
        duplicate = run(
            root,
            "attach",
            "--record-dir",
            str(record_dir),
            "--artifact",
            "host-a:/var/log/engine.log",
            "--role",
            "service-log",
        )
        assert "STATE=ALREADY_REGISTERED" in duplicate.stdout

        evidence = yaml.safe_load((record_dir / "evidence-index.yaml").read_text(encoding="utf-8"))
        assert len(evidence["artifacts"]) == 1
        validated = run(root, "validate")
        assert "STATE=VALID" in validated.stdout
        assert not (root / ".day0.lock").exists()

    print("DAY0CTL_SELF_TEST=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
