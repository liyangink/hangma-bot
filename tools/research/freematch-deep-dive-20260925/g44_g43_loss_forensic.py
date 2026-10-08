#!/usr/bin/env python3
"""G44：G43 的两张负向开发桌首处分歧和随后公开行动复跑。"""

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

import g13_accounted_panel as accounted
import g14_accounted_paired_panel as panel
import g41_first_divergence_audit as g41
import g43b_audit_identity_policy as candidate


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g43b-audit-identity-pilot-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g44-g43-loss-forensic-20260927/result.json')
TARGETS = ((1, 2, "np-M-2026122704-r01-s2-t2"),
           (2, 3, "np-M-2026122704-r02-s3-t1"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(root: int, seat: int, arm: str):
    """原样复跑一阶段；仅旁路保留决策观察及全部座位动作。"""
    manifest = json.loads((_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")).read_text(encoding="utf-8"))
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent="M", root_index=root,
        focal_seat=seat, panel_seed=manifest["panel_seed"])
    table_ids = tuple(plan.table_id for plan in plans)
    records = []
    outcomes = {}
    metrics = []
    base_factory = (panel.paired.policy_factory("r18_v2") if arm == "r18_v2"
                    else candidate.policy_factory(metrics))

    def factory(monotonic):
        return g41._RecordingPolicy(base_factory(monotonic), records, table_ids)

    original = accounted.drive_match

    async def capture(**kwargs):
        outcome = await original(**kwargs)
        outcomes[kwargs["spec"].match_id] = outcome
        return outcome

    accounted.drive_match = capture
    try:
        stage = accounted.run_accounted_stage(
            plans=plans, candidate_policy_factory=factory,
            opponent_policies=contract["panel"]["opponent_scenarios"]["M"]["opponent_policies"],
            versions_block=panel.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=panel.paired.LIMITS)
    finally:
        accounted.drive_match = original
    unit = "M", root, seat, arm, manifest["panel_seed"]
    panel.verify_unit({"mix": "M", "root_index": root, "focal_seat": seat,
                       "arm": arm, "stage": stage},
                      unit=unit, tables_per_stage=manifest["tables_per_stage"])
    old_path = panel.paired.unit_path(FROZEN, unit)
    old = json.loads(old_path.read_text(encoding="utf-8"))["stage"]
    if ([(t["table_id"], t["scores_by_seat"], t["hand_records"])
         for t in stage["tables"]] !=
            [(t["table_id"], t["scores_by_seat"], t["hand_records"])
             for t in old["tables"]]):
        raise ValueError("G44 复跑结算与冻结 G43b 不一致")
    by_table = {table_id: [] for table_id in table_ids}
    for table_id, request, plan in records:
        by_table[table_id].append((request, plan))
    return stage, by_table, outcomes, metrics, sha(old_path)


def _future(outcome, decision_id: str, round_no: int) -> list[dict]:
    """只保留首处分歧后同局的前 24 个真实座位动作。"""
    all_records = list(outcome.decisions)
    index = next((i for i, row in enumerate(all_records) if row.decision_id == decision_id), None)
    if index is None:
        raise ValueError("首处分歧未进入实际模拟驱动")
    result = []
    for row in all_records[index:index + 25]:
        if row.window_key.get("round_no") != round_no:
            break
        result.append(row.to_json())
    return result


def main() -> None:
    """只读旧开发根，结果只用于归因，不用于独立收益确认。"""
    if OUT.exists():
        raise FileExistsError("拒绝覆盖 G44 旧根诊断")
    rows = []
    for root, seat, target in TARGETS:
        b_stage, b_own, b_outcomes, _, b_sha = replay(root, seat, "r18_v2")
        c_stage, c_own, c_outcomes, metrics, c_sha = replay(
            root, seat, "g43_edge_three_draw_filter_v1")
        before = b_own[target]
        after = c_own[target]
        index = next((i for i in range(min(len(before), len(after)))
                      if g41._identity(before[i]) != g41._identity(after[i])), None)
        if index is None or index >= len(before) or index >= len(after):
            raise ValueError("目标负向桌未找到首个焦点动作分歧")
        b_decision = g41._decision(before[index])
        c_decision = g41._decision(after[index])
        if (b_decision["window"] != c_decision["window"] or
                b_decision["observation"] != c_decision["observation"]):
            raise ValueError("首处分歧并非相同动作前玩家观察")
        b_table = next(item for item in b_stage["tables"] if item["table_id"] == target)
        c_table = next(item for item in c_stage["tables"] if item["table_id"] == target)
        game_key = "sitin-stage:" + target
        round_no = b_decision["window"]["round_no"]
        rows.append({
            "table_id": target, "mix": "M", "root": root, "seat_group": seat,
            "first_divergence_index": index,
            "baseline_score": b_table["hand_account"]["focal_table_delta"],
            "candidate_score": c_table["hand_account"]["focal_table_delta"],
            "baseline_first": b_decision, "candidate_first": c_decision,
            "baseline_following_actions": _future(
                b_outcomes[game_key], b_decision["decision_id"], round_no),
            "candidate_following_actions": _future(
                c_outcomes[game_key], c_decision["decision_id"], round_no),
            "baseline_hand_result": b_table["hand_records"][round_no - 1],
            "candidate_hand_result": c_table["hand_records"][round_no - 1],
            "g43_metrics_in_table": [item for item in metrics if target in item.get("decision_id", "")],
            "frozen_stage_sha256": {"baseline": b_sha, "candidate": c_sha},
        })
    result = {"schema": "g44-g43-loss-forensic/1", "rows": rows,
              "g43b_manifest_sha256": sha(_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")),
              "g43b_result_sha256": sha(_project_file(_PROJECT_ROOT, FROZEN / "result.json")),
              "script_sha256": sha(Path(__file__)),
              "boundary": "已看成绩的 G43 开发根，复跑仅作分歧与真实响应诊断；不可当候选净收益标签或独立确认。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"rows": [
        {"table_id": row["table_id"], "round_no": row["baseline_first"]["window"]["round_no"],
         "trigger_seq": row["baseline_first"]["window"]["trigger_seq"],
         "baseline_action": row["baseline_first"]["ranked"][0]["action_key"],
         "candidate_action": row["candidate_first"]["ranked"][0]["action_key"],
         "baseline_score": row["baseline_score"], "candidate_score": row["candidate_score"]}
        for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
