#!/usr/bin/env python3
"""Inspect Claude model-picker metadata or run a minimal routed request."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def normalize_model(value):
    return re.sub(r"\[1m\]$", "", value, flags=re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-binary", required=True, type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--mode", choices=["picker", "smoke"], default="picker")
    parser.add_argument("--model", help="Alias or provider ID to probe in smoke mode")
    parser.add_argument("--expect-model", help="Expected provider ID, without [1m]")
    parser.add_argument("--effort", help="Optional effort supported by this provider")
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    if args.mode == "smoke" and not args.model:
        parser.error("smoke mode requires --model")
    binary = args.claude_binary.expanduser().resolve()
    if not binary.is_file() or binary.suffix.lower() in {".cmd", ".bat"}:
        parser.error("Select the real native executable; trace shell shims separately")

    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    settings_path = args.settings.expanduser().resolve() if args.settings else config_dir / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        if not isinstance(settings, dict):
            raise ValueError("Settings root must be an object")
    except (OSError, ValueError):
        # 解析异常可能包含文件内容，统一输出类型说明，避免把凭据写入日志。
        emit({"ok": False, "error": "Cannot read valid Claude JSON settings"})
        return 2

    config_env = settings.get("env", {})
    if not isinstance(config_env, dict):
        emit({"ok": False, "error": "Settings env must be an object"})
        return 2
    secrets = [str(v) for k, v in {**os.environ, **config_env}.items()
               if re.search(r"key|token|secret|password|authorization", k, re.I)
               and v and len(str(v)) >= 6]

    def redact(value):
        value = str(value)
        for secret in sorted(set(secrets), key=len, reverse=True):
            value = value.replace(secret, "<redacted>")
        return re.sub(r"sk-[A-Za-z0-9_-]+", "<redacted>", value)

    def report(value):
        # 连成功结果和显示说明也脱敏；自定义标签中可能误填过凭据。
        def scrub(item):
            if isinstance(item, str):
                return redact(item)
            if isinstance(item, list):
                return [scrub(child) for child in item]
            if isinstance(item, dict):
                return {redact(key): scrub(child) for key, child in item.items()}
            return item
        emit(scrub(value))

    env = os.environ.copy()
    env.update({"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "API_TIMEOUT_MS": str(args.timeout * 1000), "API_MAX_RETRIES": "0"})
    command = [str(binary), "-p", "--tools", "", "--no-session-persistence"]
    if args.settings:
        command.extend(["--settings", str(settings_path)])
    if args.mode == "picker":
        command.extend(["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"])
        request = {"type": "control_request", "request_id": "skill-model-picker-check",
                   "request": {"subtype": "initialize"}}
        stdin = json.dumps(request) + "\n"
    else:
        command.extend(["--model", args.model, "--system-prompt",
                        "You are an API connectivity check. Reply with exactly OK.",
                        "--output-format", "json", "--max-turns", "1"])
        if args.effort:
            command.extend(["--effort", args.effort])
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "64"
        if args.disable_thinking:
            env["MAX_THINKING_TOKENS"] = "0"
        stdin = "Reply with exactly OK.\n"

    # 空目录阻止测试顺带装载项目代码；凭据仅由目标 CLI 读取，脚本不写配置。
    try:
        with tempfile.TemporaryDirectory(prefix="claude-api-verify-") as cwd:
            result = subprocess.run(command, input=stdin, cwd=cwd, env=env,
                                    capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=args.timeout)
    except subprocess.TimeoutExpired:
        report({"ok": False, "error": "timeout", "timeout_seconds": args.timeout})
        return 1
    except OSError as error:
        report({"ok": False, "error": "launch_failed", "detail": str(error)})
        return 1

    if result.returncode:
        report({"ok": False, "error": "cli_failed", "exit_code": result.returncode,
                "detail": (result.stderr or result.stdout)[-1200:]})
        return 1

    if args.mode == "picker":
        for line in result.stdout.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if not isinstance(item, dict) or item.get("type") != "control_response":
                continue
            response = item.get("response", {})
            if not isinstance(response, dict):
                continue
            body = response.get("response", {})
            models = body.get("models") if isinstance(body, dict) else None
            if response.get("subtype") == "success" and isinstance(models, list) and models:
                report({"ok": True, "evidence": "client_picker_metadata", "models": models})
                return 0
        report({"ok": False, "error": "no_picker_metadata", "detail": "Check CLI version and SDK initialization protocol"})
        return 1

    try:
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("Unexpected result shape")
        usage = payload.get("modelUsage", {})
        ids = list(usage) if isinstance(usage, dict) else []
        answer = str(payload.get("result", "")).strip()
        ok = payload.get("subtype") == "success" and payload.get("is_error") is False and answer == "OK" and bool(ids)
        if args.expect_model:
            # 用客户端请求记录核对别名；不能将这里的 ID 宣称为服务端模型证明。
            ok = ok and {normalize_model(x) for x in ids} == {normalize_model(args.expect_model)}
        report({"ok": ok, "evidence": "client_request_and_connectivity", "selected_model": args.model,
                "requested_model_ids": ids, "expected_model": args.expect_model,
                "result": answer[:300], "server_model_verified": False})
        return 0 if ok else 1
    except (ValueError, TypeError):
        report({"ok": False, "error": "invalid_result", "detail": result.stdout[-1200:]})
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
