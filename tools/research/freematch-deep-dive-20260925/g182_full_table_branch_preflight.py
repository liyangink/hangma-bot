#!/usr/bin/env python3
"""G182：同一结果盲父代观察下，核单次强制弃牌的完整桌续打。"""

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

import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import g126_all_draw_natural_width_exposure as capture
import g160_multi_action_value_source as source
import g181_two_draw_settlement_value as g181
import g95_wider_discard_same_hand_preflight as g95
from g13_hand_accounting import summarize_hands


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G182-FULL-TABLE-BRANCH-PREFLIGHT-PREREG-2026-09-28.md')
ERRATUM = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G182-SETTLEMENT-ONLY-ENGINE-ERRATUM-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g182-full-table-branch-preflight-20260928/result.json')
SAMPLES = ("historical", "g182-01", "g182-02")
SETTLEMENT_FIELDS = ("round_no", "scores_before", "scores_after", "score_delta",
                     "winner_seat", "is_draw", "fan", "details")


class SettlementOnlyTableEngine:
    """反事实全桌只读各单局结算，不要求历史一致世界的 full_world 牌谱。"""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.hands: list[dict] = []

    def frame(self, world):
        """保持生产模拟器的行动帧不变。"""

        return self.inner.frame(world)

    def advance(self, world, revision, choices):
        """每次推进后仅经公开结算出口采集已完成单局。"""

        before = self.inner.frame(world).completed_hands
        after_world = self.inner.advance(world, revision, choices)
        after = self.inner.frame(after_world).completed_hands
        if after < before or after > before + 1:
            raise ValueError("G182 单次推进完成单局数不在 0..1")
        if after > before:
            record = self.inner.export_hand_settlement(after_world, after)
            if record.get("coverage") != "settlement_only":
                raise ValueError("G182 非历史一致世界结算出口口径漂移")
            # 研究记录只要局内唯一标识以供积分校验；不宣称能导出正式牌谱。
            self.hands.append({"hand_id": "g182-settlement-only:" + str(after),
                               "result_confirmed": True,
                               **{name: record[name] for name in SETTLEMENT_FIELDS}})
        return after_world


def sha(path: Path) -> str:
    """结果绑定结果盲选样、续打入口及本程序。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected() -> list[dict]:
    """固定 H 零白与 M 一白各一开发窗；不看结算或牌墙。"""

    items = g181._selected()
    chosen = []
    for mix, white in (("H", 0), ("M", 1)):
        matching = [item for item in items if item["split"] == "development"
                    and item["mix"] == mix and item["white_before"] == white]
        if not matching:
            raise ValueError("G182 事前开发层缺少指定池与白板格")
        chosen.append(min(matching, key=lambda item: (
            item["root_index"], item["focal_seat"], item["round_no"])))
    return chosen


def _decisions(outcome, start_window) -> list[tuple[dict, str]]:
    """比较原始父代表与续打分支从目标窗口起的行动键序列。"""

    records = outcome.decisions
    start = next((index for index, item in enumerate(records)
                  if (item.window_key["game_id"] == start_window.game_id
                      and item.window_key["round_no"] == start_window.round_no
                      and item.window_key["trigger_seq"] == start_window.trigger_seq
                      and item.seat == start_window.seat)), None)
    if start is None:
        raise ValueError("G182 原父代表缺目标决策")
    return [(dict(item.window_key), item.action_key) for item in records[start:]]


def run_branch(*, world, record, plan, contract, versions, runtime,
               rules, situation, mix, forced_key, prefix_hands):
    """仅合法第一弃牌可改，其后四座冻结 R18 与 H/M 策略续到完整桌。"""

    g93 = g95.g93
    accounting = SettlementOnlyTableEngine(runtime["engine"])
    clock = g93.ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(g95.policies_for(plan, contract, clock, mix))
    target = record.request.window_key
    force = None
    if forced_key is not None:
        force = g93.ForceOncePolicy(policies[target.seat], target, forced_key)
        policies[target.seat] = force
    initial_frame = runtime["engine"].frame(world)
    if not initial_frame.decisions or initial_frame.decisions[0].observation != record.request.observation:
        raise ValueError("G182 同世界焦点行动前观察不一致")
    snapshot = {
        "observation_summary": g93.frame_observation_summary(initial_frame),
        "match_spec": {"match_id": plan.match_id},
    }
    config = g93.MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=g93.BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    started = time.perf_counter()
    outcome = asyncio.run(g93.resume_match(
        engine=accounting, world=world, policies_by_seat=tuple(policies),
        rules=rules, choice_factory=runtime["choice_factory"],
        config=config, now_monotonic=clock.now, wall_clock=None,
        stage_snapshot=snapshot,
        remaining_schedule={"declared_endpoint": "complete_table"},
        value_limits=g93.paired.LIMITS, stage_situation=situation))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if outcome.status != "complete" or outcome.completed_hands != int(versions["rounds_per_game"]):
        raise ValueError("G182 分支未完成原赛制规定单局")
    if force is not None and force.used != 1:
        raise ValueError("G182 备选未恰好强制一次")
    runtime_counts = asdict(outcome.runtime_counts)
    if any(runtime_counts.get(name, 0) for name in ("fallbacks", "illegal_choices", "timeouts")):
        raise ValueError("G182 分支发生规则回退、非法或超时")
    expected = record.parent_key if forced_key is None else forced_key
    if not outcome.decisions or outcome.decisions[0].action_key != expected:
        raise ValueError("G182 首个动作未按预定执行")
    hands = list(prefix_hands) + accounting.hands
    if len(hands) != int(versions["rounds_per_game"]):
        raise ValueError("G182 历史单局前缀与续打单局数量不守恒")
    final = list(outcome.final_scores or ())
    if len(final) != 4:
        raise ValueError("G182 完整桌终分缺失")
    account = summarize_hands(
        hands, focal_seat=target.seat,
        initial_scores=hands[0]["scores_before"],
        final_scores=final, expected_hands=int(versions["rounds_per_game"]))
    return {"final_scores": final, "hands": hands,
            "account": account,
            "first_action": outcome.decisions[0].action_key,
            "decisions": [(dict(item.window_key), item.action_key)
                          for item in outcome.decisions],
            "decision_count": len(outcome.decisions),
            "forced_once": 0 if force is None else force.used,
            "runtime_counts": runtime_counts,
            "elapsed_ms": round(elapsed_ms, 3)}


def main() -> None:
    """两池、三同世界、双臂预检；失败保留异常而不产出假训练集。"""

    if OUT.exists():
        raise FileExistsError("G182 预检结果已存在，拒绝覆盖")
    items = selected()
    index = g181._table_targets(items)
    g93 = g95.g93
    contract = json.loads(g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in source.plans(contract)}
    scorer = capture.g87.c31.load_parent()
    output = []
    for item in items:
        table_key = (item["mix"], item["root_index"], item["focal_seat"])
        plan = plans[table_key]
        original = g95.CaptureWiderPolicy
        g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
        try:
            captured, runtime, rules, situation, full_hands, full_outcome = g95.run_full(
                plan, contract, versions, item["mix"])
        finally:
            g95.CaptureWiderPolicy = original
        target = index[table_key + (item["round_no"],)]
        record = captured.records.get(item["round_no"])
        if (record is None or capture.scored_target(record, scorer) != target
                or item["observation_sha256"] != target["observation_sha256"]
                or record.parent_key != item["parent_action"]
                or record.alternate_key != item["alternate_action"]):
            raise ValueError("G182 冻结父代观察或合法动作身份漂移")
        before = full_hands[:item["round_no"] - 1]
        initial = runtime["engine"].frame(record.world).decisions[0].observation
        pairs = []
        for sample in SAMPLES:
            world = (record.world if sample == "historical" else
                     runtime["engine"].resample_public_consistent_hidden_world(
                         record.world, focal_seat=item["focal_seat"], sample_key=sample))
            if runtime["engine"].frame(world).decisions[0].observation != initial:
                raise ValueError("G182 重采样改变本人依法可见观察")
            arms = {}
            for name, forced in (("parent", None), ("alternate", record.alternate_key)):
                arms[name] = run_branch(
                    world=world, record=record, plan=plan, contract=contract,
                    versions=versions, runtime=runtime, rules=rules,
                    situation=situation, mix=item["mix"], forced_key=forced,
                    prefix_hands=before)
            if arms["parent"]["hands"][0]["scores_before"] != arms["alternate"]["hands"][0]["scores_before"]:
                raise ValueError("G182 双臂不是同一积分起点")
            if sample == "historical":
                if (len(arms["parent"]["hands"]) != len(full_hands)
                        or any({name: old[name] for name in SETTLEMENT_FIELDS}
                               != {name: new[name] for name in SETTLEMENT_FIELDS}
                               for old, new in zip(full_hands, arms["parent"]["hands"], strict=True))
                        or arms["parent"]["final_scores"] != list(full_outcome.final_scores or ())):
                    raise ValueError("G182 历史父代完整桌逐局或终分不恒等")
                if arms["parent"]["decisions"] != _decisions(full_outcome, record.request.window_key):
                    raise ValueError("G182 历史父代续打逐动作不恒等")
            pairs.append({"sample_key": sample,
                          "focal_table_delta_alt_minus_parent":
                              arms["alternate"]["final_scores"][item["focal_seat"]]
                              - arms["parent"]["final_scores"][item["focal_seat"]],
                          "parent": {key: value for key, value in arms["parent"].items()
                                     if key != "decisions"},
                          "alternate": {key: value for key, value in arms["alternate"].items()
                                        if key != "decisions"},
                          "decision_sequence_equal":
                              arms["parent"]["decisions"] == arms["alternate"]["decisions"]})
            print(json.dumps({"mix": item["mix"], "white": item["white_before"],
                              "sample": sample, "delta":
                                  pairs[-1]["focal_table_delta_alt_minus_parent"]},
                             ensure_ascii=False), flush=True)
        output.append({"mix": item["mix"], "root_index": item["root_index"],
                       "focal_seat": item["focal_seat"], "round_no": item["round_no"],
                       "white_before": item["white_before"],
                       "observation_sha256": item["observation_sha256"],
                       "parent_action": item["parent_action"],
                       "alternate_action": item["alternate_action"],
                       "pairs": pairs})
    payload = {"schema": "g182-full-table-branch-preflight/1",
               "selected_windows": len(output),
               "paired_worlds": sum(len(row["pairs"]) for row in output),
               "source_sha256": {name: sha(path) for name, path in {
                   "plan": PLAN, "script": Path(__file__),
                   "settlement_only_erratum": ERRATUM,
                   "g160_selection": source.OUT / "selection.json",
                   "g160_rows": source.OUT / "rows.jsonl",
                   "g95_runtime": Path(g95.__file__),
                   "resume_match": _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/offline/evaluate.py"),
                   "accounting": _project_file(_PROJECT_ROOT, HERE / "g13_hand_accounting.py"),
               }.items()},
               "rows": output,
               "boundary": "两个开发窗口各三世界的机械整桌续打预检；非策略收益、非训练集，不读取锁定结算。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"selected_windows": len(output),
                      "paired_worlds": payload["paired_worlds"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
