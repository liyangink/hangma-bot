"""严格核验新自然面板留存的完整MatchResult；不等同于逐动作重算或发布许可。"""
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
import json
from pathlib import Path

from verify_natural_evidence import natural, stage, verify_panel, _same, _require, _digest
import sitin_execution_audit as execution_audit
import sitin_execution_profile as execution_profiles
from hangma_bot.offline.evaluation_results import (
    SIMULATION_SOURCE_NAMESPACE, check_complete_consistency, match_result_from_json,
)


def verify_full_table(table, plan, contract, expected_rules_hash, *, require_execution_audit=False):
    """对照独立赛程和规则摘要校验完整桌赛；拒绝历史摘要、缺局、错座及积分不符。"""
    raw = table.get("result")
    _require(isinstance(raw, dict) and bool(raw), "桌赛缺少完整MatchResult")
    result = match_result_from_json(raw)
    # 公开解析器允许扩展字段；已知字段不得通过类型强转或默认值被悄悄修正。
    for key, value in result.to_json().items():
        _same(raw.get(key), value, "结果字段 " + key)
    _same(result.source_kind, "simulation", "结果来源")
    _same(result.status, "complete", "完整桌赛状态")
    _require(not check_complete_consistency(result), "完整结果内部不一致")
    rounds = contract["versions"]["rounds_per_game"]
    _same(result.expected_hands, rounds, "冻结计划单局数")
    _same(result.completed_hands, rounds, "实际完成单局数")
    _same(result.result_id, "r-" + plan.match_id, "结果身份")
    _same(result.scenario_id, plan.scenario_id, "情景身份")
    _same(result.pair_id, plan.pair_id, "配对身份")
    _same(raw["game_key"], {"source_namespace": SIMULATION_SOURCE_NAMESPACE,
          "tournament_id": plan.scenario_id, "game_id": plan.match_id}, "场次身份")
    _same(list(result.policy_ids_by_seat), list(plan.seats()), "物理座位参赛者")
    _same(list(result.seat_permutation), list(plan.permutation), "换座映射")
    _same(list(result.scores_before or ()), [0, 0, 0, 0], "初始积分")
    _same(list(result.scores_after or ()), table["scores_by_seat"], "摘要与结果积分")
    _same(raw["official_ranks"], None, "模拟不产生官方排名")
    _require(result.config is not None, "缺少比赛配置")
    _same(result.config.max_games, 1, "单桌执行器并发配置")
    _same(raw["config"]["timing"], dict(stage.DEFAULT_TIMING), "冻结动作窗口配置")
    _same(result.config.rounds_per_game, rounds, "结果配置单局数")
    versions = stage.contract_versions_block(contract)
    for key in ("ruleset_version", "base_score", "you_cai_bi_kao"):
        _same(getattr(result.config.rules, key), versions[key], "规则配置 " + key)
    _require(isinstance(expected_rules_hash, str) and bool(expected_rules_hash), "必须提供冻结规则摘要")
    _same(raw["versions"].get("rules_hash"), expected_rules_hash, "规则代码摘要")
    _same(raw["versions"].get("clock_mode"), versions["clock_mode"], "时钟模式")
    _require(result.runtime_counts is not None, "缺少实际运行计数")
    for value in raw["runtime_counts"].values():
        _require(type(value) is int and value >= 0, "运行计数必须为已知非负整数")
    audit = execution_audit.verify_table(table, required=require_execution_audit)
    return {"result_digest": _digest(raw), "runtime_counts": raw["runtime_counts"],
            "policy_execution": audit}


def verify_full_panel(panel, contract, *, expected_identity, expected_root_indices, expected_rules_hash):
    """先复算完整摘要清单，再逐桌核验结果；所有输入只读，不扩充来源样本数。"""
    summary = verify_panel(panel, contract, expected_identity=expected_identity,
                           expected_root_indices=expected_root_indices)
    counts, digests, tables = {}, [], []
    audit_schema = expected_identity.get("policy_execution_schema")
    profile = expected_identity.get("candidate_execution_profile")
    if profile is not None:
        execution_profiles.resolve(profile)
    if audit_schema is not None:
        _same(audit_schema, execution_audit.SCHEMA, "冻结评分审计版本")
    for sample in panel["samples"]:
        plans = natural.build_seat_stage_plans(contract=contract, opponent=sample["opponent_mix"],
            root_index=sample["root_index"], focal_seat=sample["focal_anchor_seat"],
            panel_seed=panel["identity"]["panel_seed"])
        for arm in ("baseline", "candidate"):
            for table, plan in zip(sample["raw_arms"][arm]["tables"], plans):
                result = verify_full_table(table, plan, contract, expected_rules_hash,
                                          require_execution_audit=audit_schema is not None)
                if profile is not None:
                    execution_profiles.verify_table(table, profile=profile,
                        candidate_seat=(list(plan.seats()).index(natural.FOCAL_PARTICIPANT)
                                        if arm == "candidate" else None))
                tables.append(table)
                digests.append(result["result_digest"])
                for key, value in result["runtime_counts"].items():
                    counts[key] = counts.get(key, 0) + value
    execution_review = execution_audit.review_tables(tables, required=audit_schema is not None)
    if audit_schema is not None:
        _same(panel.get("execution_review"), execution_review, "面板评分执行汇总")
        for sample in panel["samples"]:
            for arm in ("baseline", "candidate"):
                raw_arm = sample["raw_arms"][arm]
                _same(raw_arm.get("execution_review"), execution_audit.review_tables(raw_arm["tables"]),
                      "阶段评分执行汇总")
    return {"status": "CONSISTENT_COMPLETE_MATCH_RESULTS", "summary_reconciliation": summary,
        "full_results_verified": len(digests), "results_digest": _digest(digests), "runtime_counts": counts,
        "execution_review": execution_review,
        "selection_eligible": False, "release_eligible": False,
        "limitations": ["完整MatchResult是终端结果，不是逐动作或逐笔结算日志",
                        "没有独立复演规则/牌墙，不能证明所有结算数学正确",
                        "持久来源/显著性消费账本和赛事可靠性门禁另行验收",
                        "不独立证明候选源码实际装配或供应商身份；依赖冻结执行器与运行证据"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, action="append", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--rules-hash", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("不覆盖既有核验")
    contract = json.loads(args.contract.read_text())
    results = []
    for path in args.panel:
        panel = json.loads(path.read_text())
        results.append(verify_full_panel(panel, contract, expected_identity=panel["identity"],
            expected_root_indices=sorted({s["root_index"] for s in panel["samples"]}),
            expected_rules_hash=args.rules_hash))
    with args.out.open("x") as handle:
        json.dump({"purpose": "posthoc_internal_reconciliation_not_preregistration", "results": results},
                  handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"full_results_verified": sum(r["full_results_verified"] for r in results),
                      "release_eligible": False}))
