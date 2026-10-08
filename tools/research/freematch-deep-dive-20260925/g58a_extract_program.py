#!/usr/bin/env python3
"""把 G58 A 卡的 JSON 前缀程序显式派生为可审计研究源码。"""

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
from pathlib import Path

import g58_answer_screen as screen
import g58_executable_search_wave as wave


HERE = Path(__file__).resolve().parent
ANSWER = wave.OUT / "a_contextual_width.answer.txt"
OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/g58a_author_program.py')
EXPECTED_ANSWER_SHA256 = "c2573bf6b503997d2203280e0404fbf904b8c421306d95d134169e1bd7bfc86d"


def main() -> None:
    """保留原答合同失败事实；仅把其语法可验纯函数另存为派生种子。"""

    answer = ANSWER.read_text(encoding="utf-8")
    if hashlib.sha256(answer.encode()).hexdigest() != EXPECTED_ANSWER_SHA256:
        raise ValueError("G58 A 原答摘要漂移")
    valid, problem = wave.parse_answer(answer)
    if valid or problem != "invalid_json":
        raise ValueError("G58 A 的原答合同状态与评审不符")
    payload, end = json.JSONDecoder().raw_decode(answer.lstrip())
    if payload.get("status") != "proposed" or not answer.lstrip()[end:].strip():
        raise ValueError("G58 A 不再是带尾文的 JSON 前缀")
    program = payload.get("program")
    if not isinstance(program, str) or screen.program_screen(program) != {
            "syntax_ok": True, "ast_nodes": 1132, "flags": []}:
        raise ValueError("G58 A 作者函数 AST 漂移")
    source = ('"""G58 A 原答 JSON 前缀中抽出的纯函数；原答严格合同失败，仅供离线研究。"""\n\n'
              + program.rstrip() + "\n")
    if OUTPUT.exists():
        if OUTPUT.read_text(encoding="utf-8") != source:
            raise ValueError("G58 A 派生程序已存在但内容不同")
    else:
        OUTPUT.write_text(source, encoding="utf-8")
    print(json.dumps({"answer_sha256": EXPECTED_ANSWER_SHA256,
                      "program_sha256": hashlib.sha256(program.encode()).hexdigest(),
                      "derived_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                      "trailing_chars": len(answer.lstrip()[end:].strip())},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
