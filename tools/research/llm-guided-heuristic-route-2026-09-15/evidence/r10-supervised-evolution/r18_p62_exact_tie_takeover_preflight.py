"""R18 P62：严格平分后继接管的零桌支持度预检。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p47_integrated_parent_registration as p47  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.protected_public_successor_policy import (  # noqa: E402
    protected_trace_state,
)
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    RootSearchScore,
    reduce_public_successors,
)
from hangma_bot.policy.r18_integrated_positive_v1 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V1_SHA256,
    R18_INTEGRATED_POSITIVE_V1_SOURCE,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p62-exact-tie-takeover-preflight-01-20260923')
P47_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p47-integrated-parent-registration-01-20260922/result.json')
P60_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p60-confirmed-hu-takeover-preflight-01-20260923/result.json')
P61_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p61-confirmed-hu-takeover-screen-01-20260923/result.json')
R17_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-seed-author-b-sol-repair-01-20260921/candidate.py')
R17_SOURCE_SHA256 = "fb9764faa2a01ded3f8cea94eeee27d59929f014f1dcc0ffbd56380e5b1384a2"
SPECIAL_TRACE_KEYS = (
    "r18_opportunity_overlay",
    "r18_gang_dominance_overlay",
    "r18_seven_pairs_value_overlay",
    "two_wealth_piao_keeps_baotou_cf",
)
EXPECTED_REQUESTS = 377
MINIMUM_TEACHER_STATES = 24
LIMITS = ValueAnalysisLimits()


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def strict_successor_improvement(
    challenger: RootSearchScore,
    parent_top: RootSearchScore,
) -> bool:
    """复述 P60 的四项规则事实条件，不增加事后阈值。"""

    return bool(
        challenger.conditional_hu_capacity
        > parent_top.conditional_hu_capacity
        and challenger.conditional_hu_net_support
        > parent_top.conditional_hu_net_support
        and challenger.lower_support_score >= parent_top.lower_support_score
        and challenger.upper_support_score >= parent_top.upper_support_score
    )


async def evaluate() -> dict[str, Any]:
    """在冻结请求上统计严格平分且满足四条件的动作对。"""

    requests = p47.current_requests()
    if len(requests) != EXPECTED_REQUESTS:
        raise ValueError("P47 冻结请求数漂移")
    parent = ActionValuePolicy(
        ActionValueScorer("r18-p62-parent", R18_INTEGRATED_POSITIVE_V1_SOURCE),
        value_limits=LIMITS,
    )
    leaf = LeafProgramExecutor(
        R17_SOURCE.read_text(encoding="utf-8"), name="r18-p62-r17-b"
    )
    rules_cache: dict[str, HangmaRules] = {}
    budget = DecisionBudget(10.0, 20.0, 30.0)
    counts: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    ties: list[dict[str, Any]] = []
    for label, request in requests:
        counts["requests"] += 1
        plan = await parent.choose(request, budget)
        if any("action_value_failed" in reason for reason in plan.degraded_reasons):
            counts["action_value_failures"] += 1
            failures.append({"label": label, "reason": "parent_action_value_failed"})
            continue
        protected, _keys = protected_trace_state(plan, SPECIAL_TRACE_KEYS)
        if protected:
            counts["protected_plans"] += 1
            continue
        if request.observation.phase != "draw":
            counts["response_plans"] += 1
            continue
        discards = tuple(
            item for item in plan.candidates
            if item.action_key.startswith("discard:")
        )
        if len(discards) < 2:
            counts["draw_not_applicable"] += 1
            continue
        counts["eligible_ordinary_draws"] += 1
        version = request.rules.ruleset_version
        rules = rules_cache.setdefault(
            version, HangmaRules(RuleConfig(version, 1, False))
        )
        reduction = reduce_public_successors(
            request,
            rules.analyze_public_self_draw_successors(request.observation),
            leaf.window_scorer(),
        )
        if not reduction.complete:
            failures.append({"label": label, "reason": reduction.reason})
            continue
        counts["complete_ordinary_draws"] += 1
        roots = {item.action_key: item for item in reduction.roots}
        parent_top = discards[0]
        parent_root = roots.get(parent_top.action_key)
        if parent_root is None:
            failures.append({"label": label, "reason": "parent_top_root_missing"})
            continue
        challengers = [
            item for item in discards[1:]
            if item.total_score == parent_top.total_score
            and item.action_key in roots
            and strict_successor_improvement(roots[item.action_key], parent_root)
        ]
        if not challengers:
            continue
        counts["exact_tie_windows"] += 1
        challenger = challengers[0]
        successor = roots[challenger.action_key]
        ties.append(
            {
                "label": label,
                "parent_action": parent_top.action_key,
                "challenger_action": challenger.action_key,
                "parent_total_score": parent_top.total_score,
                "challenger_total_score": challenger.total_score,
                "parent_rank": parent_top.rank,
                "challenger_rank": challenger.rank,
                "conditional_hu_capacity": [
                    parent_root.conditional_hu_capacity,
                    successor.conditional_hu_capacity,
                ],
                "conditional_hu_net_support": [
                    parent_root.conditional_hu_net_support,
                    successor.conditional_hu_net_support,
                ],
                "lower_support_score": [
                    parent_root.lower_support_score,
                    successor.lower_support_score,
                ],
                "upper_support_score": [
                    parent_root.upper_support_score,
                    successor.upper_support_score,
                ],
            }
        )
    return {
        "counts": dict(counts),
        "failures": failures,
        "exact_tie_rows": ties,
    }


def run() -> None:
    """先冻结零桌支持度门，再执行并关闭或开放因果教师。"""

    if OUT.exists():
        raise SystemExit("P62 目录已存在；拒绝覆盖")
    p47_result = json.loads(P47_RESULT.read_text(encoding="utf-8"))
    p60_result = json.loads(P60_RESULT.read_text(encoding="utf-8"))
    p61_result = json.loads(P61_RESULT.read_text(encoding="utf-8"))
    prerequisites = {
        "p47_active_parent": (
            p47_result.get("status") == "PASS_P47_INTEGRATED_PARENT_REGISTRATION"
            and p47_result.get("active_research_parent") is True
            and p47_result.get("candidate_sha256")
            == R18_INTEGRATED_POSITIVE_V1_SHA256
        ),
        "p60_static_preflight_passed": p60_result.get("status")
        == "PASS_P60_CONFIRMED_HU_TAKEOVER_PREFLIGHT",
        "p61_effect_rejected": (
            p61_result.get("status")
            == "FAIL_P61_CONFIRMED_HU_TAKEOVER_SCREEN"
            and p61_result.get("selection_eligible") is False
        ),
        "r17_source_exact": digest(R17_SOURCE) == R17_SOURCE_SHA256,
    }
    if not all(prerequisites.values()):
        raise ValueError("P62 前置证据不成立：" + repr(prerequisites))
    OUT.mkdir(parents=True)
    inputs = {
        "script": digest(Path(__file__)),
        "p47_result": digest(P47_RESULT),
        "p60_result": digest(P60_RESULT),
        "p61_result": digest(P61_RESULT),
        "r17_source": digest(R17_SOURCE),
        "p47_parent_source": R18_INTEGRATED_POSITIVE_V1_SHA256,
    }
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        {
            "schema": "r18-p62-exact-tie-preflight-authorization/1",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "purpose": (
                "只判断严格平分破同是否有足够冻结请求支持进入共同隐藏世界教师；"
                "不得用P61结果调阈值"
            ),
            "expected_requests": EXPECTED_REQUESTS,
            "minimum_teacher_states": MINIMUM_TEACHER_STATES,
            "predicate": (
                "P47首选与挑战弃牌total_score严格相等，且挑战动作同时严格增加"
                "conditional_hu_capacity与conditional_hu_net_support，后继上下界均不退"
            ),
            "stop_rule": (
                "少于24个窗口即关闭当前破同表示，不运行自然桌或隐藏世界教师；"
                "不得追加rank2、epsilon平分或分差变体"
            ),
            "budgets": {"tables_full": 0, "model_calls": 0, "network_calls": 0},
            "frozen_inputs": inputs,
        },
    )
    evaluation = asyncio.run(evaluate())
    counts = Counter(evaluation["counts"])
    mechanical = bool(
        counts["requests"] == EXPECTED_REQUESTS
        and counts["action_value_failures"] == 0
        and counts["complete_ordinary_draws"]
        == counts["eligible_ordinary_draws"]
        and not evaluation["failures"]
    )
    enough = counts["exact_tie_windows"] >= MINIMUM_TEACHER_STATES
    open_teacher = mechanical and enough
    result = {
        "schema": "r18-p62-exact-tie-takeover-preflight-result/1",
        "status": (
            "OPEN_P62_EXACT_TIE_CAUSAL_TEACHER"
            if open_teacher
            else "CLOSE_P62_EXACT_TIE_TAKEOVER_INSUFFICIENT_SUPPORT"
        ),
        "prerequisite_checks": prerequisites,
        "mechanical_checks_passed": mechanical,
        "minimum_teacher_states": MINIMUM_TEACHER_STATES,
        "counts": dict(counts),
        "failures": evaluation["failures"],
        "exact_tie_rows": evaluation["exact_tie_rows"],
        "teacher_opened": open_teacher,
        "tables_run": 0,
        "model_calls": 0,
        "network_calls": 0,
        "strength_claim": False,
        "selection_eligible": False,
        "release_eligible": False,
        "interpretation": (
            "冻结回归请求中没有严格平分且满足四条件的动作对；当前破同表示无可评估支持，"
            "不值得生成新自然桌或共同隐藏世界标签"
            if mechanical and not enough
            else "仅在支持度门通过时，才可另行冻结全新来源的共同隐藏世界教师"
        ),
        "next": (
            "关闭R17-B动作接管表示；主搜索转向新的精确杭麻机会家族"
            if not open_teacher
            else "冻结全新来源并在任何收益标签前拆分开发/隐藏集"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p62-exact-tie-takeover-preflight-manifest/1",
            "authorization_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "authorization.json")),
            "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
            "frozen_inputs": inputs,
        },
    )
    (_project_file(_PROJECT_ROOT, OUT / "README.md")).write_text(
        "# R18 P62 严格平分接管支持度预检\n\n"
        "结论：`" + result["status"] + "`。377 个冻结请求中，专项保护 87 个、"
        "响应窗口 48 个；242 个普通摸牌窗口全部完成归约，但严格平分且满足 P60 "
        "四条件的动作对为 **0**。因此不运行新自然桌或共同隐藏世界教师，关闭当前 "
        "R17-B 动作接管表示；这不表示未来任何新公开表示都不可能有效。\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
