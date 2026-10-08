#!/usr/bin/env python3
"""G50：复跑 G49 已开发根，追踪首改选及后两次本人出牌窗口。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import g13_accounted_panel as accounted
import g14_accounted_paired_panel as panel
import g41_first_divergence_audit as first
import g46_paired_first_response_audit as response
import g47_next_own_draw_shape_audit as shape
import g49_natural_route_policy as candidate


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-novel-ordinary-route-expansion-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g50-g49-route-forensic-20260927/result.json')
SOURCE_SHA = "faa6c335f60367553c8976971db5dc1050cbeb37fa1912bfc4b883d2cb89d18f"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _targets(manifest: dict) -> tuple[dict[tuple[str, int, int], set[str]], int]:
    """仅从候选已冻结的实际改选指标选阶段，不用桌分挑样本。"""

    targets: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    count = 0
    for mix in panel.MIXES:
        for root in range(1, 13):
            for seat_group in panel.SEATS:
                unit = mix, root, seat_group, manifest["arms"][1], manifest["panel_seed"]
                stage = json.loads(panel.paired.unit_path(FROZEN, unit).read_text(encoding="utf-8"))["stage"]
                table_ids = tuple(table["table_id"] for table in stage["tables"])
                for metric in stage["g49_metrics"]:
                    if metric["status"] != "adopted":
                        continue
                    table_id = next((item for item in table_ids
                                     if "sitin-stage:" + item + ":" in metric["decision_id"]), None)
                    if table_id is None:
                        raise ValueError("G49 改选指标不能定位冻结桌")
                    targets[mix, root, seat_group].add(table_id)
                    count += 1
    if count != 34:
        raise ValueError("G49 扩样实际改选数漂移")
    return dict(targets), count


def _replay(mix: str, root: int, seat_group: int, arm: str, manifest: dict):
    """旁路记录焦点决策和全座位动作，逐桌结算必须与冻结扩样一致。"""

    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat_group, panel_seed=manifest["panel_seed"])
    table_ids = tuple(plan.table_id for plan in plans)
    own = []
    outcomes = {}
    metrics = []
    factory = (panel.paired.policy_factory("r18_v2") if arm == manifest["arms"][0]
               else candidate.policy_factory(metrics))

    def wrapped(monotonic):
        return first._RecordingPolicy(factory(monotonic), own, table_ids)

    original = accounted.drive_match

    async def capture(**kwargs):
        outcome = await original(**kwargs)
        outcomes[kwargs["spec"].match_id] = outcome
        return outcome

    accounted.drive_match = capture
    try:
        stage = accounted.run_accounted_stage(
            plans=plans, candidate_policy_factory=wrapped,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            versions_block=panel.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=panel.paired.LIMITS)
    finally:
        accounted.drive_match = original
    unit = mix, root, seat_group, arm, manifest["panel_seed"]
    panel.verify_unit({"mix": mix, "root_index": root, "focal_seat": seat_group,
                       "arm": arm, "stage": stage},
                      unit=unit, tables_per_stage=manifest["tables_per_stage"])
    path = panel.paired.unit_path(FROZEN, unit)
    frozen_stage = json.loads(path.read_text(encoding="utf-8"))["stage"]
    for fresh, old in zip(stage["tables"], frozen_stage["tables"]):
        if (fresh["table_id"] != old["table_id"] or
                fresh["scores_by_seat"] != old["scores_by_seat"] or
                fresh["hand_records"] != old["hand_records"]):
            raise ValueError("G50 复跑逐桌结算与冻结 G49 扩样不同")
    if arm == manifest["arms"][1]:
        old_metrics = [(row["decision_id"], row["action"], row["status"])
                       for row in frozen_stage["g49_metrics"]]
        new_metrics = [(row["decision_id"], row["action"], row["status"])
                       for row in metrics]
        if old_metrics != new_metrics:
            raise ValueError("G50 复跑候选改选与冻结 G49 不同")
    by_table = {table_id: [] for table_id in table_ids}
    for table_id, request, plan in own:
        by_table[table_id].append((request, plan))
    if set(outcomes) != {"sitin-stage:" + table_id for table_id in table_ids}:
        raise ValueError("G50 全座位动作缺桌")
    return stage, by_table, outcomes, sha(path)


def _two_draw_phases(own: list, first_index: int, round_no: int) -> list[dict]:
    """同局后两个 draw 阶段窗口；鸣牌后出牌时 drawn_tile 可为空。"""

    result = []
    for row in own[first_index + 1:]:
        request, _plan = row
        if request.window_key.round_no != round_no:
            break
        if request.window_key.phase.value == "draw":
            result.append(shape.next_shape(row))
            if len(result) == 2:
                break
    return result


def _actual_intervening(outcome, first_id: str, next_id: str | None,
                        round_no: int) -> list[tuple[int, str, str]]:
    """首弃至本人下个出牌窗口之间的全部已执行动作，供跨臂同路径核验。"""

    return shape.intervening(outcome, first_id, next_id, round_no)


def main() -> None:
    """已看开发根只作路线归因；不把未来摸牌或桌分当在线标签。"""

    if OUT.exists():
        raise SystemExit("G50 诊断已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")).read_text(encoding="utf-8"))
    if (manifest["panel_seed"] != 2026122706 or manifest["roots_per_mix"] != 12
            or manifest["arms"] != ["r18_v2", "g49_novel_ordinary_route_v1"]
            or sha(_project_file(_PROJECT_ROOT, HERE / "g49_natural_route_policy.py")) != SOURCE_SHA):
        raise ValueError("G50 冻结面板或候选源码身份漂移")
    targets, adoption_count = _targets(manifest)
    rows = []
    for (mix, root, seat_group), table_ids in sorted(targets.items()):
        baseline, b_own, b_outcomes, b_sha = _replay(
            mix, root, seat_group, manifest["arms"][0], manifest)
        other, c_own, c_outcomes, c_sha = _replay(
            mix, root, seat_group, manifest["arms"][1], manifest)
        b_tables = {table["table_id"]: table for table in baseline["tables"]}
        c_tables = {table["table_id"]: table for table in other["tables"]}
        for table_id in sorted(table_ids):
            before, after = b_own[table_id], c_own[table_id]
            first_index = next((index for index in range(min(len(before), len(after)))
                                if first._identity(before[index]) != first._identity(after[index])), None)
            if first_index is None or first_index >= len(before) or first_index >= len(after):
                raise ValueError("G49 已改选桌没有可比较首处分歧")
            b_request, b_plan = before[first_index]
            c_request, c_plan = after[first_index]
            if (b_request.window_key != c_request.window_key or
                    first._decision(before[first_index])["observation"] !=
                    first._decision(after[first_index])["observation"]):
                raise ValueError("G49 首处分歧不是相同动作前观察")
            if not c_plan.candidates[0].action_key.startswith("discard:"):
                raise ValueError("G49 首处分歧不是候选弃牌")
            selected, select_evidence = candidate.select(c_request, b_plan)
            if selected != c_plan.candidates[0].action_key:
                raise ValueError("G49 首处分歧与重算候选入口不同")
            round_no = b_request.window_key.round_no
            b_next = _two_draw_phases(before, first_index, round_no)
            c_next = _two_draw_phases(after, first_index, round_no)
            b_next_id = next((row[0].decision_id for row in before[first_index + 1:]
                              if row[0].window_key.round_no == round_no
                              and row[0].window_key.phase.value == "draw"), None)
            c_next_id = next((row[0].decision_id for row in after[first_index + 1:]
                              if row[0].window_key.round_no == round_no
                              and row[0].window_key.phase.value == "draw"), None)
            b_outcome = b_outcomes["sitin-stage:" + table_id]
            c_outcome = c_outcomes["sitin-stage:" + table_id]
            b_actions = _actual_intervening(b_outcome, b_request.decision_id, b_next_id, round_no)
            c_actions = _actual_intervening(c_outcome, c_request.decision_id, c_next_id, round_no)
            b_response = response.immediate_response(b_outcome, b_request.decision_id, round_no)
            c_response = response.immediate_response(c_outcome, c_request.decision_id, round_no)
            b_table, c_table = b_tables[table_id], c_tables[table_id]
            delta = (c_table["hand_account"]["focal_table_delta"] -
                     b_table["hand_account"]["focal_table_delta"])
            rows.append({"table_id": table_id, "mix": mix, "root": root,
                         "seat_group": seat_group, "actual_focal_seat": b_request.window_key.seat,
                         "round_no": round_no,
                         "trigger_seq": b_request.window_key.trigger_seq,
                         "first_baseline": shape.next_shape(before[first_index]),
                         "first_candidate": shape.next_shape(after[first_index]),
                         "first_selector": select_evidence,
                         "baseline_immediate": {"kind": b_response[0], "seat": b_response[1]},
                         "candidate_immediate": {"kind": c_response[0], "seat": c_response[1]},
                         "same_intervening_actions": b_actions == c_actions,
                         "baseline_next_two": b_next, "candidate_next_two": c_next,
                         "baseline_hand_result": b_table["hand_records"][round_no - 1],
                         "candidate_hand_result": c_table["hand_records"][round_no - 1],
                         "baseline_score": b_table["hand_account"]["focal_table_delta"],
                         "candidate_score": c_table["hand_account"]["focal_table_delta"],
                         "table_delta": delta,
                         "frozen_stage_sha256": {"baseline": b_sha, "candidate": c_sha}})
        print(json.dumps({"mix": mix, "root": root, "seat_group": seat_group,
                          "target_tables": len(table_ids)}), flush=True)
    counts = Counter()
    by_mix = defaultdict(Counter)
    for row in rows:
        mix = row["mix"]
        direction = "positive" if row["table_delta"] > 0 else "negative" if row["table_delta"] < 0 else "zero"
        for values in (counts, by_mix[mix]):
            values["tables"] += 1
            values["score|" + direction] += 1
            values["immediate|" + row["baseline_immediate"]["kind"] + "→" +
                   row["candidate_immediate"]["kind"]] += 1
            values["same_intervening_actions|" + str(row["same_intervening_actions"])] += 1
            values["both_reach_next_draw_phase"] += int(bool(row["baseline_next_two"] and row["candidate_next_two"]))
    output = {"schema": "g50-g49-route-forensic/1", "adoption_count": adoption_count,
              "target_stages": len(targets), "target_tables": len(rows),
              "g49_manifest_sha256": sha(_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")),
              "g49_result_sha256": sha(_project_file(_PROJECT_ROOT, FROZEN / "result.json")),
              "script_sha256": sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "by_mix": {mix: dict(sorted(values.items())) for mix, values in sorted(by_mix.items())},
              "rows": rows,
              "boundary": "旧 G49 开发根的赛后轨迹诊断；draw 阶段可能没有新摸牌，未来摸牌、他家动作和净分不得进入在线观察或作独立确认。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"adoption_count": adoption_count, "target_stages": len(targets),
                      "target_tables": len(rows), "counts": output["counts"],
                      "by_mix": output["by_mix"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
