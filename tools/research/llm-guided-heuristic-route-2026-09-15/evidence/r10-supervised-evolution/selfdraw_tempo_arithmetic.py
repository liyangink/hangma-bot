"""自摸竞速的独立公式手算及缺分支保留证据反例；不复制评分循环。"""

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
from dataclasses import replace
import math

import selfdraw_tempo_checks as checks
from hangma_bot.policy.action_value import CompetitionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer

b = checks.b


def branch(code, shanten, support):
    """合成已生产弃牌分支；支持单位是未见枚数，不是概率。"""
    return {"followup_key": "peng:4b#" + code, "followup_discard": code,
            "combined_shanten": shanten, "support_remaining": support}


def route(code, support=2, delta=12):
    """条件自摸结算按物理座位0—3；合成数值只验证消费算术。"""
    return {"followup_discard": code, "shanten": 0,
            "useful_tiles": ({"code": "1t", "remaining_estimate": support},),
            "conditional_settlement": {"self_delta": delta,
                "score_delta": (delta, -delta / 3, -delta / 3, -delta / 3)},
            "conditions": {"draw_kind": "normal"}}


def cases():
    """期望显式代入作者原公式，覆盖独立事实不依赖缺失分支的合同。"""
    action, view = checks.action, checks.view
    wait = action("", 10, 1, "pass")
    direct = replace(action("4b", 12, 1, "peng"), best_followup_discard="9b")
    route_only = replace(action("4b", kind="peng"), routes=(route("9b"),))
    rows = []
    def add(name, actions, expected, competition=None):
        sample = view(tuple(actions), familiar=())
        sample = replace(sample, competition=competition or CompetitionView())
        rows.append((name, sample, expected))
    add("live_ready_over_one_away", [action("4b", 1, 0), action("8t", 20, 1)],
        {"discard:4b": 736, "discard:8t": 400 + 3600 / 28})
    add("dead_ready_below_live_one_away", [action("4b", 0, 0), action("8t", 4, 1)],
        {"discard:4b": 150, "discard:8t": 460})
    add("stages_two_and_three", [action("4b", 12, 2), action("8t", 16, 3)],
        {"discard:4b": 270, "discard:8t": 130})
    add("call_best_branch_not_sum", [replace(direct, shanten_after=0,
        useful_tiles=action("4b", 2, 0).useful_tiles,
        followup_branches=(branch("9b", 0, 2), branch("8b", 1, 8))), wait],
        {"peng:4b": 760, "pass": 500})
    add("call_direct_when_branches_missing", [direct, wait],
        {"peng:4b": 508, "pass": 500})
    add("call_direct_when_branch_unknown", [replace(direct,
        followup_branches=(branch("9b", None, None),)), wait],
        {"peng:4b": 508, "pass": 500})
    add("call_direct_when_branch_boolean", [replace(direct,
        followup_branches=(branch("9b", True, True),)), wait],
        {"peng:4b": 508, "pass": 500})
    add("call_route_when_branches_missing", [route_only, wait],
        {"peng:4b": 760 + 480 / 52, "pass": 500})
    add("call_route_not_in_partial_branch_list", [replace(direct,
        routes=(route("8b"),), followup_branches=(branch("9b", 1, 12),)), wait],
        {"peng:4b": 760 + 480 / 52, "pass": 500})
    add("mutually_exclusive_routes_max", [replace(route_only,
        routes=(route("9b"), route("8b", 4, 12))), wait],
        {"peng:4b": 790 + 480 / 52, "pass": 500})
    a = replace(action("4b"), routes=(route(None, 2, 30),))
    account = CompetitionView(stage_scores=(-5, 5, 15, -15),
        table_scores=(5, 5, 5, -15), current_stage_scores=(0, 10, 20, -30),
        freshness_masks=("stage_account:complete", "table_account:live"))
    add("full_stage_recomputed_line", [a, wait],
        {"discard:4b": 760 + 1200 / 70 + 600 / 70, "pass": 500}, account)
    add("no_stage_no_invented_line", [a, wait],
        {"discard:4b": 760 + 1200 / 70, "pass": 500})
    return rows


def run(first=False):
    """首答允许失败并保留全部反例；修复复用同组期望，不看效果改判据。"""
    source = checks.source_path()
    scorer = ActionValueScorer("tempo-arithmetic", source.read_text())
    output = checks.batch.OUT / checks.batch.NAME / ("first-answer-arithmetic.json" if first else "independent-arithmetic.json")
    if output.exists(): raise ValueError("不覆盖已完成算术证据")
    rows = []
    for name, sample, expected in cases():
        result = scorer.score(sample)
        got = {entry.action_key: entry.score for entry in result.entries}
        errors = [key for key, value in expected.items()
                  if key not in got or not math.isclose(got[key], value, abs_tol=1e-9, rel_tol=0)]
        if result.status != "SCORED": errors.append("status")
        rows.append({"name": name, "expected": expected, "actual": got, "errors": errors,
            "input_sha256": b.behavior.digest(sample.candidate_view()),
            "trace": {entry.action_key:dict(entry.trace) for entry in result.entries},
            "operations": scorer.last_operation_count})
    report = {"status": "FAIL" if any(r["errors"] for r in rows) else "PASS", "rows": rows,
        "source_sha256": b.digest(source.read_bytes()), "runner_sha256": b.digest(b.Path(__file__).read_bytes()),
        "scope": "12项合成合同算术；条件数值不冒充真实规则可达牌谱；无效果样本",
        "release_eligible": False}
    b.write(output, report)
    print(report["status"], [(r["name"],r["errors"]) for r in rows if r["errors"]], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", action="store_true")
    run(parser.parse_args().first)
