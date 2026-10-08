#!/usr/bin/env python3
"""G166：冻结新根窗口的两臂同世界单局续打，记录行动前事实与终局分量。"""

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
from collections import Counter
import json
import os
from pathlib import Path
from statistics import mean

import g100_g96_visible_trajectory as trajectory
import g166_fresh_root_learnability_source as source
from hangma_bot.application.audit_codec import (
    candidate_facts_to_json,
    candidate_value_facts_to_json,
)
from hangma_bot.kernel.serialization import observation_to_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g166-fresh-root-two-arm-teacher-20260928')
WORLD_KEYS = ("historical",) + tuple(
    f"g166-{index:03d}" for index in range(1, 17))
COMPONENTS = (
    "ordinary_one_fan_self_win", "seven_pairs_self_win",
    "ordinary_highfan_self_win", "opponent_win_payment", "draw_or_other",
)


class FullFactsTracePolicy(trajectory.TracePolicy):
    """只在本人头两个决策窗追加生产合法候选事实，不触碰策略排序。"""

    async def choose(self, request, budget):
        """保存动作前合法动作全集及可见观察摘要，后续窗口保留轻量轨迹。"""
        plan = await super().choose(request, budget)
        if len(self.records) <= 2:
            record = self.records[-1]
            record["observation_sha256"] = source.g160.source.g108.canonical_sha(
                observation_to_json(request.observation))
            record["all_legal_candidates"] = [
                {
                    "action_key": candidate.action_key,
                    "facts": (candidate_facts_to_json(candidate.facts)
                              if candidate.facts is not None else None),
                    "value_facts": (candidate_value_facts_to_json(candidate.value_facts)
                                    if candidate.value_facts is not None else None),
                }
                for candidate in request.rules.legal_candidates
            ]
        return plan


def branch(**kwargs) -> dict:
    """复用 G100 完整驱动和恒等核查，仅替换透明记录器。"""
    original = trajectory.TracePolicy
    trajectory.TracePolicy = FullFactsTracePolicy
    try:
        return trajectory.run_branch(**kwargs)
    finally:
        trajectory.TracePolicy = original


def component(settlement: dict, seat: int) -> dict[str, float]:
    """按实际官方结算互斥分账；所有分量之和必须等于本座单局积分。"""
    delta = float(settlement["score_delta"][seat])
    result = {name: 0.0 for name in COMPONENTS}
    winner = settlement["winner_seat"]
    if settlement["is_draw"] or winner is None:
        result["draw_or_other"] = delta
    elif winner != seat:
        result["opponent_win_payment"] = delta
    else:
        details = settlement["details"]
        seven = any(detail == "七对" or detail.startswith("豪华七对×")
                    for detail in details)
        if seven:
            result["seven_pairs_self_win"] = delta
        elif "平胡" in details and settlement["fan"] == 1:
            result["ordinary_one_fan_self_win"] = delta
        elif "平胡" in details and settlement["fan"] >= 2:
            result["ordinary_highfan_self_win"] = delta
        else:
            raise ValueError("G166 未知本人胡牌结算明细")
    if sum(result.values()) != delta:
        raise ValueError("G166 结算分量不守恒")
    return result


def selected() -> list[dict]:
    """只能载入 512 桌完成且四个层各十六独立根的结果盲选样。"""
    out = source.OUT
    data = json.loads((out / "selection.json").read_text(encoding="utf-8"))
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    if (data["schema"] != "g166-fresh-root-learnability-source-selection/1"
            or data["rows_sha256"] != source.g160.sha(out / "rows.jsonl")
            or data["manifest_sha256"] != source.g160.sha(out / "manifest.json")
            or not data["result_blind"] or not result["coverage_sufficient"]
            or len(data["selected"]) != 64):
        raise ValueError("G166 来源未完成或四层固定覆盖不足")
    return data["selected"]


def manifest(items: list[dict]) -> dict:
    """绑定结果盲来源、世界键、轨迹与结算执行器版本。"""
    paths = {
        "prereg": source.PREREG,
        "script": Path(__file__),
        "selection": source.OUT / "selection.json",
        "source_rows": source.OUT / "rows.jsonl",
        "source_script": Path(source.__file__),
        "capture_script": Path(source.g160.source.__file__),
        "trajectory_script": Path(trajectory.__file__),
        "contract": source.g160.source.g95.g93.paired.CONTRACT,
        "simulation_engine": _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/simulation/engine.py"),
    }
    return {
        "schema": "g166-fresh-root-two-arm-teacher-manifest/1",
        "windows_planned": len(items),
        "world_keys": list(WORLD_KEYS),
        "parent_scorer_sha256": source.g160.source.g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "input_sha256": {name: source.g160.sha(path) for name, path in paths.items()},
        "boundary": "同世界双臂单局教师，非完整桌策略收益；终局分型不能作为线上特征。",
    }


def index() -> dict[tuple, tuple[dict, dict]]:
    """按池、根、座位、官方单局定位不可变父代观察。"""
    rows = [json.loads(line) for line in
            (source.OUT / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows) != 512:
        raise ValueError("G166 父代表尚不完整")
    found = {}
    for row in rows:
        for target in row["target_windows"]:
            key = (row["mix"], row["root_index"], row["focal_seat"],
                   target["round_no"])
            if key in found:
                raise ValueError("G166 目标窗口身份重复")
            found[key] = (row, target)
    return found


def compact_arm(full: dict, seat: int) -> dict:
    """保留前两次本人行动的可见事实、终局积分及可靠性核验。"""
    trace = full["focal_trajectory"]
    if not trace or trace[0]["action_key"] != full["first_decision_action"]:
        raise ValueError("G166 焦点首行动轨迹与分支不一致")
    first_two = trace[:2]
    if any("all_legal_candidates" not in item for item in first_two):
        raise ValueError("G166 前两次行动缺合法候选全集")
    settlement = full["settlement"]
    return {
        "settlement": settlement,
        "focal_score_delta": settlement["score_delta"][seat],
        "score_components": component(settlement, seat),
        "decision_count": full["decision_count"],
        "first_decision_action": full["first_decision_action"],
        "forced_once": full["forced_once"],
        "runtime_counts": full["runtime_counts"],
        "focal_action_count": len(trace),
        "terminal_before_next_focal_action": len(trace) < 2,
        "first_two_focal_actions": first_two,
    }


def one_window(item: dict, table: dict, target: dict, plan,
               contract: dict, versions: dict, scorer) -> dict:
    """重建历史父代表并在十七个同观察世界运行父代与备选两臂。"""
    capture = source.g160.source
    g95 = capture.g95
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, table["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(target["round_no"])
    if record is None or capture.scored_target(record, scorer) != target:
        raise ValueError("G166 父代观察或评分与固定来源不一致")
    if any(item[name] != target[name] for name in (
            "observation_sha256", "parent_action", "alternate_action")):
        raise ValueError("G166 固定选样身份漂移")
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    worlds = [("historical", record.world)]
    for sample_key in WORLD_KEYS[1:]:
        sampled = runtime["engine"].resample_public_consistent_hidden_world(
            record.world, focal_seat=item["focal_seat"], sample_key=sample_key)
        if runtime["engine"].frame(sampled).decisions[0].observation != reference:
            raise ValueError("G166 重采样改变依法可见观察")
        worlds.append((sample_key, sampled))
    pairs = []
    for sample_key, world in worlds:
        parent = compact_arm(branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=table["mix"], forced_key=None),
            item["focal_seat"])
        alternate = compact_arm(branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=table["mix"],
            forced_key=record.alternate_key), item["focal_seat"])
        if (parent["forced_once"] != 0 or alternate["forced_once"] != 1
                or parent["first_decision_action"] != record.parent_key
                or alternate["first_decision_action"] != record.alternate_key
                or parent["settlement"]["scores_before"] !=
                   alternate["settlement"]["scores_before"]):
            raise ValueError("G166 首弃或双臂起点不同")
        if any(parent["runtime_counts"].values()) or any(
                alternate["runtime_counts"].values()):
            raise ValueError("G166 分支出现保底、超时或非法动作")
        if sample_key == "historical":
            historical = hands[target["round_no"] - 1]
            for field in ("round_no", "scores_before", "scores_after",
                          "score_delta", "winner_seat", "is_draw", "fan", "details"):
                if parent["settlement"][field] != historical[field]:
                    raise ValueError("G166 历史父代单局恒等失败：" + field)
        difference = alternate["focal_score_delta"] - parent["focal_score_delta"]
        components = {name: alternate["score_components"][name]
                      - parent["score_components"][name]
                      for name in COMPONENTS}
        if sum(components.values()) != difference:
            raise ValueError("G166 双臂积分分量差不守恒")
        pairs.append({"sample_key": sample_key,
                      "focal_delta_alt_minus_parent": difference,
                      "component_alt_minus_parent": components,
                      "parent": parent, "alternate": alternate})
    return {"mix": item["mix"], "root_index": item["root_index"],
            "focal_seat": item["focal_seat"], "round_no": item["round_no"],
            "white_before": item["white_before"],
            "observation_sha256": item["observation_sha256"],
            "parent_action": item["parent_action"],
            "alternate_action": item["alternate_action"],
            "score_facts": target["score_facts"], "world_pairs": pairs}


def summary(rows: list[dict], planned: int) -> dict:
    """世界先在同窗求均值；每池×根至多一窗，不能把十七世界当独立桌。"""
    groups = {}
    for mix in ("H", "M"):
        for white in (0, 1):
            subset = [row for row in rows if row["mix"] == mix
                      and row["white_before"] == white]
            all_means = [mean(pair["focal_delta_alt_minus_parent"]
                              for pair in row["world_pairs"]) for row in subset]
            historical = [row["world_pairs"][0]["focal_delta_alt_minus_parent"]
                          for row in subset]
            resampled = [mean(pair["focal_delta_alt_minus_parent"]
                              for pair in row["world_pairs"][1:]) for row in subset]
            component_means = {
                name: mean(mean(pair["component_alt_minus_parent"][name]
                                for pair in row["world_pairs"]) for row in subset)
                if subset else None for name in COMPONENTS
            }
            groups[f"{mix}/{white}"] = {
                "windows": len(subset),
                "roots": len({row["root_index"] for row in subset}),
                "related_world_pairs": sum(len(row["world_pairs"]) for row in subset),
                "paired_score_mean": mean(all_means) if all_means else None,
                "historical_world_mean": mean(historical) if historical else None,
                "resampled_world_mean": mean(resampled) if resampled else None,
                "component_means": component_means,
                "positive_window_means": sum(value > 0 for value in all_means),
                "negative_window_means": sum(value < 0 for value in all_means),
                "zero_window_means": sum(value == 0 for value in all_means),
            }
    return {"schema": "g166-fresh-root-two-arm-teacher-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "windows_completed": len(rows), "windows_planned": planned,
            "groups": groups,
            "boundary": "同世界单局配对诊断，不是独立完整桌候选净分。"}


def main() -> None:
    """准确前缀逐窗持久化；结果只在来源覆盖充足时运行。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    items = selected()
    expected = manifest(items)
    targets = index()
    g95 = source.g160.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = source.g160.source.g87.c31.load_parent()
    plans = {(mix, root, seat): plan
             for mix, root, seat, plan in source.plans(contract)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G166 两臂清单或代码改变，不能混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(items):
        raise ValueError("G166 已有双臂行超过固定选样")
    for old, item in zip(rows, items):
        if any(old[name] != item[name] for name in (
                "mix", "root_index", "focal_seat", "round_no",
                "observation_sha256", "parent_action", "alternate_action")):
            raise ValueError("G166 既有双臂行不是固定选样准确前缀")
    with rows_path.open("a", encoding="utf-8") as stream:
        for item in items[len(rows):]:
            key = (item["mix"], item["root_index"], item["focal_seat"],
                   item["round_no"])
            table, target = targets[key]
            row = one_window(item, table, target, plans[key[:3]],
                             contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            print(json.dumps({"windows_completed": len(rows),
                              "world_pairs": len(row["world_pairs"]),
                              "mix": item["mix"], "root": item["root_index"]},
                             ensure_ascii=False), flush=True)
            if args.max_new > 0 and len(rows) >= args.max_new:
                break
    result = summary(rows, len(items))
    result["manifest_sha256"] = source.g160.sha(manifest_path)
    result["rows_sha256"] = source.g160.sha(rows_path)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                          sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "windows_completed": result["windows_completed"],
                      "groups": result["groups"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
