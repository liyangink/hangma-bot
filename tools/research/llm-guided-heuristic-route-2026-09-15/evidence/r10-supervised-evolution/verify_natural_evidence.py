"""复算已有自然面板的桌赛摘要、阶段账与目标值；只读，不执行模拟。

现有 raw_arms 没有保存完整 MatchResult。本工具验证摘要的内部一致性，不能
证明实际单局完成数、真实策略装配或未留存的动作轨迹；输出不能作为发布许可。
后续确认执行器可复用 verify_panel，但必须独立核验完整结果和运行前冻结身份。
"""
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
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(TOOLS))
import sitin_archive as archive
import sitin_natural_panel as natural
import sitin_stage as stage


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _same(actual: Any, expected: Any, label: str) -> None:
    # 严格 JSON 避免 bool == int、int == float 隐藏声明类型漂移。
    if _canonical(actual) != _canonical(expected):
        raise ValueError(label + " 与重建值不符")


def _require(ok: bool, label: str) -> None:
    if not ok:
        raise ValueError(label)


def _integer(value: Any, label: str) -> int:
    _require(type(value) is int, label + " 必须是整数，布尔或浮点不算整数")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _verify_arm(raw: Mapping[str, Any], slim: Mapping[str, Any], *,
                label: str, identity: str, plans: Sequence[Any], rounds: int) -> dict:
    """按冻结赛程重新映射物理座位，复算阶段账与唯一目标函数；失败即报错。"""
    _same(raw.get("arm"), label, "臂名称")
    _same(slim.get("candidate_id"), identity, "臂策略身份")
    _same(slim.get("policy_id"), natural.BASELINE_FOCAL_POLICY if label == "baseline" else "action_value",
          "臂策略类型")
    for record in (raw, slim):
        _require(record.get("status") == "complete" and record.get("usable") is True
                 and record.get("error") is None, "臂执行未完成")
    tables = raw.get("tables")
    _require(isinstance(tables, list) and len(tables) == len(plans), "臂桌赛清单缺失或多余")
    totals, points = {}, {}
    for index, (table, plan) in enumerate(zip(tables, plans)):
        _same(table.get("table_id"), plan.table_id, "桌赛身份或顺序")
        _same(table.get("seed"), plan.seed, "桌赛随机种子")
        _same(table.get("match_status"), "complete", "桌赛完成状态")
        scores = table.get("scores_by_seat")
        _require(isinstance(scores, list) and len(scores) == 4, "桌赛积分须为四座位向量")
        for score in scores:
            _integer(score, "桌赛积分")
        _require(sum(scores) == 0, "零初始积分桌赛的积分不守恒")
        situation = natural.build_stage_situation(plan=plan, table_no=index + 1,
            tables_completed=index, totals=totals, place_totals=points, rounds_per_game=rounds)
        _same(table.get("stage_situation"), situation.to_json(), "桌赛开始前阶段账")
        table_points = stage.place_points_for_table(scores)
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + scores[seat]
            points[participant] = points.get(participant, 0) + table_points[seat]
    rows = [stage.LedgerRow(participant_id=pid, total_score=totals[pid], place_points=points[pid])
            for pid in sorted(totals)]
    utility = stage.group_advance_utility(rows, focal_id=natural.FOCAL_PARTICIPANT)
    expected = {"stage_totals_by_participant": totals,
                "focal_stage_score": totals[natural.FOCAL_PARTICIPANT],
                "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
                "u": float(utility["u_low"]) if utility["u_low"] == utility["u_high"] else None,
                "unresolved": utility["unresolved"]}
    for key, value in expected.items():
        _same(raw.get(key), value, "原始臂 " + key)
        _same(slim.get(key), value, "统计臂 " + key)
    _same(raw.get("stage_place_points_by_participant"), points, "阶段名次分")
    _same(raw.get("u_interval"), {"a": utility["a"], "b": utility["b"],
          "tie_block": utility["tie_block"]}, "晋级识别区间")
    return expected


def verify_panel(panel: Mapping[str, Any], contract: Mapping[str, Any], *,
                 expected_identity: Mapping[str, Any], expected_root_indices: Sequence[int]) -> dict:
    """验证完整四换座自然面板摘要并重算统计，零副作用。

    expected_identity 与 expected_root_indices 应由运行前冻结计划独立传入；
    历史核算可从旧产物读取，但那只能证明内部一致，不能证明预登记或独立确认。
    contract 是完整冻结工程合同。本版仅支持现有 group-dev-v1 目标与生成器。
    """
    _same(panel.get("schema"), natural.NATURAL_PANEL_SCHEMA, "自然面板版本")
    _same(panel.get("generator"), natural.NATURAL_PANEL_GENERATOR, "生成器版本")
    identity = panel.get("identity", {})
    _same(identity, expected_identity, "运行前冻结身份")
    _same(identity.get("contract_sha256"), _digest(contract), "完整合同摘要")
    _same(identity.get("contract_id"), contract.get("contract_id"), "合同名称")
    _require(contract.get("mode") == "group_only" and
             contract.get("objective", {}).get("target_id") == "group_advance_v1" and
             contract["objective"].get("advance_count") == 2, "仅支持完整四人前二目标")
    _same(contract["group"].get("group_size"), 4, "四人组")
    _same(contract["group"].get("group_advance"), 2, "组内晋级数")
    _same(contract["ranking"].get("place_points_values"), list(stage.PLACE_POINTS), "名次分取值")
    _same(contract["objective"].get("ranking_keys_offline"), ["total_score", "place_points"],
          "离线排名键")
    _same(contract["objective"].get("missing_key_policy"), "recognition_interval", "未知排名键处理")
    _same(identity.get("stage_projection"), natural.STAGE_ACCOUNT_MODE, "阶段账投影版本")
    mix = identity.get("opponent_mix")
    _require(mix in ("H", "M"), "对手情景未知")
    _same(identity.get("panel_epoch"), natural.NATURAL_PANEL_GENERATOR + "@" + mix, "面板情景版本")
    panel_seed = _integer(identity.get("panel_seed"), "面板种子")
    indices = list(expected_root_indices)
    _require(bool(indices) and all(type(i) is int and 1 <= i <= natural.MAX_ROOT_INDEX for i in indices)
             and len(set(indices)) == len(indices), "冻结根序号无效或重复")
    config = panel.get("config", {})
    _same(config.get("roots"), len(indices), "根数")
    _same(config.get("seats_per_root"), 4, "完整四换座")
    _same(config.get("focal_policy"), {"baseline": natural.BASELINE_FOCAL_POLICY,
          "candidate": "ActionValuePolicy(av-candidate)"}, "焦点策略声明")
    tables_per_arm = _integer(contract["group"].get("tables_per_group"), "每臂桌数")
    _require(tables_per_arm > 0, "每臂桌数必须为正")
    _same(config.get("tables_per_group"), tables_per_arm, "每臂桌数")
    rounds = _integer(contract["versions"].get("rounds_per_game"), "每桌单局数")
    _require(rounds > 0, "每桌单局数必须为正")
    _same(config.get("opponent_policies"), contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
          "对手池")
    candidate = identity.get("candidate_id")
    baseline = identity.get("baseline_id")
    _require(isinstance(candidate, str) and bool(candidate) and isinstance(baseline, str)
             and bool(baseline) and candidate != baseline, "候选或基线身份缺失或相同")
    samples = panel.get("samples")
    _require(isinstance(samples, list), "样本清单缺失")
    expected_cells = {(index, seat) for index in indices for seat in range(4)}
    seen = set()
    reconstructed = {}
    for sample in samples:
        index = _integer(sample.get("root_index"), "根序号")
        seat = _integer(sample.get("focal_anchor_seat"), "焦点座位")
        cell = (index, seat)
        _require(cell in expected_cells and cell not in seen, "未登记根/座位或重复样本")
        seen.add(cell)
        _same(sample.get("candidate_id"), candidate, "样本候选身份")
        _same(sample.get("opponent_mix"), mix, "样本对手情景")
        _same(sample.get("scenario"), "normal", "自然开局场景")
        _require(sample.get("completeness") == "complete" and not sample.get("invalid_reasons")
                 and sample.get("invalid", False) is False
                 and sample.get("self_comparison", False) is False, "样本失效或错误自比较声明")
        root_id = natural.natural_root_id(mix, panel_seed, index)
        root_seed = natural.natural_root_seed(panel_seed, mix, index)
        _same(sample.get("source_root_id"), root_id, "来源根身份")
        _same(sample.get("root_seed"), root_seed, "来源根种子")
        _same(sample.get("root_expected"), {"seats": 4, "arms": ["baseline", "candidate"],
                                           "tables_per_arm": tables_per_arm}, "根期望清单")
        plans = natural.build_seat_stage_plans(contract=contract, opponent=mix,
                    root_index=index, focal_seat=seat, panel_seed=panel_seed)
        ids = [p.table_id for p in plans]
        seeds = [p.seed for p in plans]
        _same(sample.get("table_ids"), ids, "样本桌赛身份清单")
        _same(sample.get("table_seeds"), seeds, "样本桌赛种子清单")
        _same(sample.get("seat_participants_by_table"), [list(p.seats()) for p in plans], "换座赛程")
        reconstructed[cell] = {"table_ids": ids, "table_seeds": seeds}
        raw_arms, arms = sample.get("raw_arms", {}), sample.get("arms", {})
        _same(sorted(raw_arms), ["baseline", "candidate"], "原始双臂清单")
        _same(sorted(arms), ["baseline", "candidate"], "统计双臂清单")
        for label, policy_id in (("baseline", baseline), ("candidate", candidate)):
            _verify_arm(raw_arms[label], arms[label], label=label, identity=policy_id,
                        plans=plans, rounds=rounds)
    _same(sorted(seen), sorted(expected_cells), "完整冻结样本清单")
    for index in indices:
        # 与生成器 v2 公开产物的字段序列一致；仅复算身份，不复制牌局规则。
        root_digest = _digest({"generator": natural.NATURAL_PANEL_GENERATOR,
            "stage_projection": natural.STAGE_ACCOUNT_MODE, "panel_seed": panel_seed,
            "opponent": mix, "root_index": index,
            "root_seed": natural.natural_root_seed(panel_seed, mix, index),
            "tables_per_arm": tables_per_arm, "baseline_focal_policy": natural.BASELINE_FOCAL_POLICY,
            "seats": {str(seat): reconstructed[(index, seat)] for seat in range(4)}})
        for sample in samples:
            if sample["root_index"] == index:
                _same(sample.get("root_content_digest"), root_digest, "来源根内容摘要")
    min_roots = _integer(config.get("min_roots"), "最小统计根数")
    _require(min_roots > 0, "最小统计根数必须为正")
    statistics = archive.paired_stage_statistics(samples, min_roots=min_roots)
    _same(panel.get("statistics"), statistics, "存档根级统计")
    return {"schema": "natural-evidence-reconciliation/1", "status": "CONSISTENT_TABLE_SUMMARIES",
            "panel_digest": _digest(panel), "identity": identity, "n_roots": len(indices),
            "n_seat_pairs": len(samples), "n_table_summaries": len(samples) * 2 * tables_per_arm,
            "statistics": statistics, "selection_eligible": False, "release_eligible": False,
            "limitations": ["未保存完整 MatchResult，无法独立核验完成单局数",
                            "未重新运行策略或规则，不证明单桌原始积分计算正确",
                            "未验证来源消费与预登记时序，不作为独立确认"]}


def main() -> None:
    """历史核算入口：从旧产物读取身份作内部对账；输出新文件，拒绝覆盖。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", action="append", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    _require(not args.out.exists(), "输出已存在，禁止覆盖")
    contract = json.loads(args.contract.read_text())
    results = []
    for path in args.panel:
        panel = json.loads(path.read_text())
        result = verify_panel(panel, contract, expected_identity=panel["identity"],
                              expected_root_indices=sorted({s["root_index"] for s in panel["samples"]}))
        results.append({"path": str(path.resolve()), **result})
    with args.out.open("x") as handle:
        json.dump({"purpose": "historical_internal_reconciliation_only", "results": results},
                  handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"panels_verified": len(results), "table_summaries": sum(r["n_table_summaries"] for r in results),
                      "new_tables_executed": 0, "release_eligible": False}))


if __name__ == "__main__":
    main()
