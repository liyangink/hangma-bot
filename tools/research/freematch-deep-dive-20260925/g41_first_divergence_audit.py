#!/usr/bin/env python3
"""G41：复跑已开发根，只定位两臂首个可见动作分歧与其规则事实。"""

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

import argparse
import hashlib
import json
from pathlib import Path

import g14_accounted_paired_panel as panel
from hangma_bot.application.audit_codec import rule_analysis_to_json
from hangma_bot.kernel.serialization import observation_to_json


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _RecordingPolicy:
    """只读记录焦点策略的动作前输入和选择，不改变受测策略语义。"""

    def __init__(self, inner, records: list, table_ids: tuple[str, ...]):
        self.inner = inner
        self.records = records
        self.table_ids = table_ids
        self.policy_id = inner.policy_id

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def choose(self, request, budget):
        plan = await self.inner.choose(request, budget)
        table_id = next((item for item in self.table_ids if item in request.decision_id), None)
        if table_id is None:
            raise ValueError("焦点决策不能匹配冻结桌 ID")
        self.records.append((table_id, request, plan))
        return plan


def _run(*, mix: str, root: int, seat: int, arm: str, manifest: dict):
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=manifest["panel_seed"])
    table_ids = tuple(plan.table_id for plan in plans)
    records = []
    original_factory = panel.paired.policy_factory(arm)

    def factory(monotonic):
        return _RecordingPolicy(original_factory(monotonic), records, table_ids)

    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    unit = mix, root, seat, arm, manifest["panel_seed"]
    panel.verify_unit({"mix": mix, "root_index": root, "focal_seat": seat,
                       "arm": arm, "stage": stage},
                      unit=unit, tables_per_stage=manifest["tables_per_stage"])
    old_path = panel.paired.unit_path(FROZEN, unit)
    old = json.loads(old_path.read_text(encoding="utf-8"))["stage"]
    for fresh_table, old_table in zip(stage["tables"], old["tables"]):
        if (fresh_table["table_id"] != old_table["table_id"] or
                fresh_table["scores_by_seat"] != old_table["scores_by_seat"] or
                fresh_table["hand_records"] != old_table["hand_records"]):
            raise ValueError("诊断复跑与冻结 G32 结算不一致")
    by_table = {table_id: [] for table_id in table_ids}
    for table_id, request, plan in records:
        by_table[table_id].append((request, plan))
    return stage, by_table, {table_id: _sha(panel.paired.unit_path(FROZEN, unit))
                             for table_id in table_ids}


def _decision(row):
    request, plan = row
    return {
        "decision_id": request.decision_id,
        "window": {"round_no": request.window_key.round_no,
                   "trigger_seq": request.window_key.trigger_seq,
                   "phase": request.window_key.phase.value,
                   "seat": request.window_key.seat},
        "observation": observation_to_json(request.observation),
        "rules": rule_analysis_to_json(request.rules),
        "ranked": [{"action_key": item.action_key, "rank": item.rank,
                    "total_score": item.total_score,
                    "score_parts": [{"name": part.name, "value": part.value}
                                    for part in item.score_parts],
                    "score_trace": item.score_trace}
                   for item in plan.candidates],
    }


def _identity(row):
    request, plan = row
    return (request.window_key.round_no, request.window_key.trigger_seq,
            request.window_key.phase.value, plan.candidates[0].action_key)


def main() -> None:
    """原样复跑 G32 根，保存首个分歧；旧根只作诊断，不作确认。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mix", choices=("H", "M"), required=True)
    parser.add_argument("--root", type=int, required=True)
    parser.add_argument("--seats", default="2,3")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("拒绝覆盖已冻结诊断：" + str(args.out))
    manifest = json.loads((_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")).read_text(encoding="utf-8"))
    if (manifest["panel_seed"] != 2026122703 or manifest["roots_per_mix"] != 12 or
            manifest["candidate_sources"][manifest["arms"][1]] !=
            "bdfaf823e5b52718f3eefef5ac9972ee455dc9742dfda560c1b53f4e238ae7b2"):
        raise ValueError("G32 冻结身份漂移")
    seats = tuple(int(item) for item in args.seats.split(","))
    if not seats or any(seat not in range(4) for seat in seats):
        raise ValueError("座位必须是 0..3")
    result = {"schema": "g41-first-divergence-audit/1", "mix": args.mix,
              "root": args.root, "seats": list(seats),
              "g32_manifest_sha256": _sha(_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")),
              "script_sha256": _sha(Path(__file__)), "tables": [],
              "boundary": "旧 G32 开发根仅作首处分歧诊断；重跑逐桌结算对账，不用于收益确认。"}
    for seat in seats:
        baseline, b_rows, _ = _run(mix=args.mix, root=args.root, seat=seat,
                                   arm=manifest["arms"][0], manifest=manifest)
        candidate, c_rows, _ = _run(mix=args.mix, root=args.root, seat=seat,
                                    arm=manifest["arms"][1], manifest=manifest)
        for b_table, c_table in zip(baseline["tables"], candidate["tables"]):
            table_id = b_table["table_id"]
            if table_id != c_table["table_id"]:
                raise ValueError("两臂桌 ID 不一致")
            before, after = b_rows[table_id], c_rows[table_id]
            first = next((index for index in range(min(len(before), len(after)))
                          if _identity(before[index]) != _identity(after[index])), None)
            if first is None and len(before) != len(after):
                first = min(len(before), len(after))
            result["tables"].append({
                "table_id": table_id,
                "focal_seat": b_table["hand_account"]["focal_seat"],
                "baseline_score": b_table["hand_account"]["focal_table_delta"],
                "candidate_score": c_table["hand_account"]["focal_table_delta"],
                "baseline_decisions": len(before), "candidate_decisions": len(after),
                "first_divergence_index": first,
                "baseline_first": None if first is None or first >= len(before)
                else _decision(before[first]),
                "candidate_first": None if first is None or first >= len(after)
                else _decision(after[first]),
            })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"out": str(args.out), "tables": [
        {key: row[key] for key in ("table_id", "focal_seat", "baseline_score",
                                    "candidate_score", "first_divergence_index")}
        for row in result["tables"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
