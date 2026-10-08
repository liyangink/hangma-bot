#!/usr/bin/env python3
"""G37 原任务卡一次技术重试；仅记安全错误类别，不保存原始诊断。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import g37_glm_single_author as original


OUT = original.OUT
ANSWER = OUT / "retry-1.answer.txt"
CALL = OUT / "retry-1.call.json"
PROMPT = OUT / "prompt.txt"
FIRST = OUT / "call.json"


def signals(diagnostic: str) -> dict[str, bool]:
    """只输出固定错误类别，不反射包含 Token 或推理内容的原文。"""

    lower = diagnostic.lower()
    return {
        "http_400": bool(re.search(r"\b400\b", lower)),
        "http_401": bool(re.search(r"\b401\b", lower)),
        "http_403": bool(re.search(r"\b403\b", lower)),
        "http_429": bool(re.search(r"\b429\b", lower)),
        "http_5xx": bool(re.search(r"\b5\d\d\b", lower)),
        "rate_limit": "rate limit" in lower or "rate_limit" in lower,
        "context_or_output_limit": any(item in lower for item in
                                       ("context length", "max tokens", "max_tokens",
                                        "output limit", "token limit")),
        "timeout": "timeout" in lower or "timed out" in lower,
        "connection": any(item in lower for item in
                          ("econn", "network error", "connection error", "eai_again")),
        "no_adapter": "no_adapter" in lower,
    }


def main() -> None:
    """首次确为进程失败才重试；已有重试证据即拒绝再发。"""

    if ANSWER.exists() or CALL.exists():
        raise SystemExit("G37 技术重试已存在，拒绝再次发送")
    first = json.loads(FIRST.read_text(encoding="utf-8"))
    if first["exit_code"] == 0 or first["valid_json_contract"]:
        raise ValueError("G37 首次并非调用失败，不符合技术重试条件")
    prompt = PROMPT.read_text(encoding="utf-8")
    if hashlib.sha256(prompt.encode()).hexdigest() != first["prompt_sha256"]:
        raise ValueError("G37 冻结 prompt 摘要漂移")
    argv = ["dsh", "--profile", "headless", "--patch",
            str(original.CHANNEL / "credentials.patch.yml"), "--patch",
            str(original.CHANNEL / "no-tools-eval.patch.yml"), "--patch",
            str(original.ROUTE), prompt]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g37-retry-") as state_dir:
        try:
            result = subprocess.run(argv, cwd=original.ROOT,
                                    env=dict(os.environ, DSH_HOME=state_dir),
                                    capture_output=True, text=True, timeout=1200, check=False)
            code, answer, diagnostic = result.returncode, result.stdout, result.stderr
            failure = None if code == 0 else "nonzero_exit"
        except subprocess.TimeoutExpired as error:
            code = None
            answer = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else error.stdout or ""
            diagnostic = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else error.stderr or ""
            failure = "timeout_or_uncertain_transport"
    ANSWER.write_text(answer, encoding="utf-8")
    valid, parse_error = original.parse_answer(answer) if code == 0 else (False, "call_failure")
    record = {"schema": "g37-glm-retry/1", "first_call_sha256": original.sha(FIRST),
              "prompt_sha256": original.sha(PROMPT), "route_patch_sha256": original.sha(original.ROUTE),
              "script_sha256": original.sha(Path(__file__)),
              "model_requested": "zai-coding-cn/glm-5.3 max",
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "exit_code": code, "failure_kind": failure,
              "answer_chars": len(answer), "answer_sha256": original.sha(ANSWER),
              "diagnostic_bytes": len(diagnostic.encode()),
              "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
              "diagnostic_signals": signals(diagnostic),
              "valid_json_contract": valid, "parse_error": parse_error,
              "scope": "exact-prompt technical retry; offline author only"}
    CALL.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
