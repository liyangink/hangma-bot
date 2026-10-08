#!/usr/bin/env python3
"""G236：仅在受限内建集合下执行已审过的作者函数，核真实类型合同。"""

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
import builtins
from hashlib import sha256
import json
from pathlib import Path

import g210_post_claim_guarded_familiar_policy as g210
import g233_inversion_same_world_branch as g233
import g87_post_claim_score_trace as g87
from hangma_bot.hangma.engine import _build_context
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.interface import DecisionBudget


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g236-glm-route-controller-author-20260929')
ANSWER = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g236-glm-route-controller-author-20260929/answer-attempt2.txt')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g236-glm-route-controller-author-20260929/contract-audit.json')


def digest(path: Path) -> str:
    """证明审查针对保存的原始答卷，而非手工修正副本。"""
    return sha256(path.read_bytes()).hexdigest()


def restricted_selector(source: str):
    """只准单个纯函数和有限内建调用；模型代码不获完整 Python 内建。"""
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("作者代码不是单个函数")
    if tree.body[0].name != "select":
        raise ValueError("作者函数名称漂移")
    forbidden = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global,
                 ast.Nonlocal, ast.With, ast.AsyncWith)
    blocked_names = {"eval", "exec", "open", "__import__", "setattr",
                     "delattr", "globals", "locals", "vars", "compile"}
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise ValueError("作者代码存在未授权语法")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("作者代码引用 dunder 属性")
        if isinstance(node, ast.Name) and node.id in blocked_names:
            raise ValueError("作者代码引用危险内建")
    safe = {name: getattr(builtins, name) for name in
            ("list", "getattr", "str", "isinstance", "int", "float", "bool",
             "len", "tuple", "set", "max", "Exception")}
    namespace = {"__builtins__": safe, "_build_context": _build_context}
    exec(compile(tree, "<g236-author-answer>", "exec"), namespace, namespace)
    return namespace["select"]


async def main() -> None:
    """用 G233 三个已归档的可见请求检查返回动作与真实字段访问。"""
    if RESULT.exists():
        raise FileExistsError("G236 审查结果已存在，拒绝覆盖")
    answer = json.loads(ANSWER.read_text(encoding="utf-8"))
    select = restricted_selector(answer["selector_code"])
    cases = []
    for target in g233.selected():
        if (target["mix"], target["root_index"]) not in {
                ("H", 3), ("H", 6), ("M", 1)}:
            continue
        _, root = g233.archived_root(target)
        observation = observation_from_json(root["observation"])
        request = g87.request_for(observation)
        baseline = g210.parent_factory(lambda: 0)
        plan = await baseline.choose(request, DecisionBudget(1000, 1001, 1002))
        if plan.candidates[0].action_key != target["parent_action"]:
            raise ValueError("G236 压力窗父代动作漂移")
        action, audit, memory = select(request, plan, {})
        legal = request.rules.legal_candidates[0]
        tile = _build_context(observation).full_hand()[0]
        cases.append({
            "mix": target["mix"], "root_index": target["root_index"],
            "parent_action": target["parent_action"],
            "alternate_action": target["representative_inversion"]["action"],
            "author_action": action, "author_audit_stage": audit.get("stage"),
            "author_memory": memory,
            "real_contract": {
                "RuleCandidate_has_direct_standard_shanten_after": hasattr(
                    legal, "standard_shanten_after"),
                "RuleCandidate_has_facts": hasattr(legal, "facts"),
                "Tile_has_code": hasattr(tile, "code"),
                "Tile_has_name_or_key": hasattr(tile, "name") or hasattr(tile, "key"),
                "observation_has_remaining_tile_count": hasattr(
                    observation, "remaining_tile_count"),
                "observation_has_author_wall_aliases": any(
                    hasattr(observation, name) for name in (
                        "wall_remainder", "wall_remaining", "wall_left",
                        "tiles_remaining", "wall_count")),
                "action_key_has_author_underscore_delimiter": "_" in
                target["representative_inversion"]["action"],
            },
        })
    if len(cases) != 3:
        raise ValueError("G236 三个压力窗缺失")
    payload = {
        "schema": "g236-author-contract-audit/1",
        "answer_sha256": digest(ANSWER),
        "script_sha256": digest(Path(__file__)),
        "cases": sorted(cases, key=lambda row: (row["mix"], row["root_index"])),
        "claim_boundary": "只核作者原函数和生产对象合同；不估计改弃收益。",
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False,
                                 sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": [(row["mix"], row["root_index"],
                                row["author_action"], row["author_audit_stage"])
                               for row in payload["cases"]]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
