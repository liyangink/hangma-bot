#!/usr/bin/env python3
"""G58 作者答卷的只读 JSON/AST 初筛；绝不执行模型程序。"""

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

import ast
import hashlib
import json
from pathlib import Path

import g58_executable_search_wave as wave


OUT = wave.OUT / "static_screen.json"
CALLS = {"len", "sum", "min", "max", "any", "all", "sorted", "abs", "range"}
BLOCKED = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef,
           ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Raise, ast.Delete,
           ast.Global, ast.Nonlocal, ast.Lambda, ast.Yield, ast.YieldFrom,
           ast.Await, ast.Attribute, ast.NamedExpr)
CTX = {"white_count", "own_melds", "wall_remaining", "dealer", "table_rank",
       "opponent_melds", "drawn_tile"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def program_screen(program: str) -> dict:
    """只解析和编译语法，列出高置信静态错误；绝不执行。"""

    flags: list[str] = []
    try:
        tree = ast.parse(program, mode="exec")
        compile(tree, "<untrusted-author-program>", "exec")
    except (SyntaxError, ValueError, TypeError) as error:
        return {"syntax_ok": False, "flags": ["syntax_or_compile_error:" + type(error).__name__]}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(tree.body) != 1 or len(functions) != 1 or functions[0].name != "choose":
        flags.append("not_single_choose_function")
    elif [item.arg for item in functions[0].args.args] != ["ctx", "options"]:
        flags.append("wrong_choose_signature")
    integer_ctx_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, BLOCKED):
            flags.append("blocked_ast:" + type(node).__name__)
        if isinstance(node, ast.FunctionDef) and (not functions or node is not functions[0]):
            flags.append("nested_function")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in CALLS:
                flags.append("unapproved_call")
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == "ctx" and isinstance(node.slice, ast.Constant)
                and node.slice.value not in CTX):
            flags.append("unknown_ctx_key:" + str(node.slice.value))
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Subscript)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "ctx"
                and isinstance(node.value.slice, ast.Constant)
                and node.value.slice.value == "own_melds"):
            integer_ctx_aliases.add(node.targets[0].id)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "len" and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in integer_ctx_aliases):
            flags.append("len_on_integer_ctx_own_melds")
    if not any(isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
               and node.value.value is None for node in ast.walk(tree)):
        flags.append("no_explicit_return_none")
    return {"syntax_ok": True, "ast_nodes": sum(1 for _ in ast.walk(tree)),
            "flags": sorted(set(flags))}


def main() -> None:
    """完整四卡存在后做一次静态屏；原答和失效调用均保留。"""

    if OUT.exists():
        raise SystemExit("G58 初筛结果已存在，拒绝覆盖")
    rows = []
    for card in wave.CARDS:
        answer_path = wave.OUT / f"{card}.answer.txt"
        call_path = wave.OUT / f"{card}.call.json"
        if not answer_path.exists() or not call_path.exists():
            raise ValueError("G58 作者卡尚未全部完成")
        call = json.loads(call_path.read_text(encoding="utf-8"))
        raw = answer_path.read_text(encoding="utf-8")
        strict, strict_error = wave.parse_answer(raw) if call["exit_code"] == 0 else (False, "call_failure")
        payload = None
        trailing = 0
        if call["exit_code"] == 0:
            try:
                payload, end = json.JSONDecoder().raw_decode(raw.lstrip())
                trailing = len(raw.lstrip()[end:].strip())
            except json.JSONDecodeError:
                pass
        program = (payload.get("program") if isinstance(payload, dict)
                   and isinstance(payload.get("program"), str) else "")
        rows.append({
            "card": card, "call_exit_code": call["exit_code"],
            "answer_sha256": sha(answer_path), "strict_json_contract": strict,
            "strict_error": strict_error, "json_prefix": isinstance(payload, dict),
            "nonwhitespace_trailing_chars": trailing,
            "status_from_prefix": payload.get("status") if isinstance(payload, dict) else None,
            "program_chars": len(program),
            "program_screen": program_screen(program) if program else None,
        })
    result = {"schema": "g58-author-answer-static-screen/1", "outcome_blind": True,
              "author_script_sha256": sha(Path(wave.__file__)),
              "script_sha256": sha(Path(__file__)), "rows": rows,
              "boundary": "不执行任何模型程序；JSON 前缀只供诊断，不当严格合同通过。AST 通过不代表数学、规则、行为或净分通过。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
