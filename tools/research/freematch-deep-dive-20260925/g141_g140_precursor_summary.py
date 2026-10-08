#!/usr/bin/env python3
"""G141：汇总冻结 G140 面板，并用已观察的首次机会转移核验量具。"""

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

from collections import Counter
import json
from pathlib import Path

import g61_strong_draw_batch as g61
import g69_route_chain_analysis as g69
import g138_official_plain_baotou_opportunity as g138
import g140_plain_baotou_precursor_probe as g140
import g140_plain_baotou_precursor_select as selection_module
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = g140.OUT / "result.json"


def selected_panel() -> tuple[dict, list[dict], dict]:
    """只读预冻结名单和已落盘逐窗结果，拒绝身份不一致的阶段文件。"""
    selection = json.loads(selection_module.OUT.read_text(encoding="utf-8"))
    records = selection["selected"]
    if selection["selected_count"] != 63 or len(records) != 63:
        raise ValueError("G141 冻结面板不是 63 窗")
    stage_sha = {}
    stages = []
    for index, record in enumerate(records):
        path = g140.OUT / "stages" / f"window-{index:03d}.json"
        stage = json.loads(path.read_text(encoding="utf-8"))
        expected = {key: record[key] for key in (
            "peer", "room", "game_id", "round_no", "draw_seq", "white_before",
            "standard_shanten_after", "selection_sha256")}
        if stage["identity"] != expected:
            raise ValueError(f"G141 第 {index} 窗身份漂移")
        if (stage["arms"]["strong"]["action"] != record["actual_action"]
                or stage["arms"]["parent"]["action"] != record["parent_action"]):
            raise ValueError(f"G141 第 {index} 窗动作漂移")
        stage_sha[path.name] = g140.sha(path)
        stages.append(stage)
    return selection, stages, stage_sha


def compare(stages: list[dict]) -> dict:
    """对两种抓打包络逐窗配对，不把公开容量当作真实牌墙概率。"""
    result = {}
    for mode in ("restricted", "unrestricted"):
        counts = Counter()
        strong_rooms = set()
        protected_rooms = set()
        examples = []
        for stage in stages:
            strong, parent = stage["arms"]["strong"], stage["arms"]["parent"]
            a = strong["precursor"][mode].get("first_draw_codes", 0)
            b = parent["precursor"][mode].get("first_draw_codes", 0)
            counts["windows"] += 1
            counts["strong_has_support"] += a > 0
            counts["parent_has_support"] += b > 0
            direction = "strong_greater" if a > b else "parent_greater" if b > a else "equal"
            counts[direction] += 1
            if a <= b:
                continue
            room = stage["identity"]["room"]
            strong_rooms.add(room)
            # 普通胡、一摸有效牌和七对均不可被新代理的正向建议牺牲。
            protections = {
                "immediate_plain_capacity": strong["immediate_plain_capacity"] >=
                                            parent["immediate_plain_capacity"],
                "standard_useful_codes": strong["standard_useful_codes"] >=
                                         parent["standard_useful_codes"],
                "standard_useful_public_capacity":
                    strong["standard_useful_public_capacity"] >=
                    parent["standard_useful_public_capacity"],
                "seven_pairs_shanten": (parent["seven_pairs_shanten"] is None
                    or (strong["seven_pairs_shanten"] is not None
                        and strong["seven_pairs_shanten"] <= parent["seven_pairs_shanten"])),
            }
            for key, preserved in protections.items():
                counts["preserves/" + key] += preserved
            protected = all(protections.values())
            counts["preserves_all"] += protected
            if protected:
                protected_rooms.add(room)
            width_already_improves = (
                strong["standard_useful_codes"] > parent["standard_useful_codes"]
                or strong["standard_useful_public_capacity"] >
                parent["standard_useful_public_capacity"])
            counts["old_width_already_improves"] += width_already_improves
            counts["preserves_all_and_old_width_not_improved"] += (
                protected and not width_already_improves)
            examples.append({"peer": stage["identity"]["peer"], "room": room,
                             "game_id": stage["identity"]["game_id"],
                             "round_no": stage["identity"]["round_no"],
                             "draw_seq": stage["identity"]["draw_seq"],
                             "strong_action": strong["action"],
                             "parent_action": parent["action"],
                             "strong_first_draw_codes": a, "parent_first_draw_codes": b,
                             "protections": protections,
                             "old_width_already_improves": width_already_improves})
        result[mode] = {**dict(sorted(counts.items())),
                        "strong_greater_distinct_rooms": len(strong_rooms),
                        "all_protections_distinct_rooms": len(protected_rooms),
                        "strong_greater_examples": examples}
    return result


def observed_transition_check() -> dict:
    """用结果选中的真实相邻摸牌轨迹检验支持集能识别已发生的入口。"""
    source = json.loads(g138.OUT.read_text(encoding="utf-8"))
    if source["normal_draw_discard_windows"] != 36080:
        raise ValueError("G141 历史来源覆盖漂移")
    target_by_unit = {}
    for record in source["first_plain_baotou_rows"]:
        previous = record["previous_normal_draw"]
        if (previous is None or previous["white_before"] != record["first_white_before"]
                or previous["meld_count"] != record["first_meld_count"]):
            continue
        unit = (record["peer"], record["room"], record["actor"])
        target_by_unit.setdefault(unit, []).append(record)
    counts = Counter()
    misses = []
    source_sha = {}
    for (peer, room, actor), records in sorted(target_by_unit.items()):
        path = (g61.room_dir((peer, room)) / "windows.json" if actor == "peer"
                else g69.G69 / "rooms" / room / "windows.json.gz")
        windows, observed_sha = g69.load_windows(path)
        source_sha[f"{peer}/{room}/{actor}"] = observed_sha
        index = {(row["game_id"], row["round_no"], row["draw_seq"]): row
                 for row in windows}
        if len(index) != len(windows):
            raise ValueError("G141 历史窗口身份重复")
        for record in records:
            key = (record["game_id"], record["round_no"])
            prior = index[key + (record["previous_normal_draw"]["draw_seq"],)]
            current = index[key + (record["first_draw_seq"],)]
            if (prior["room_id"] != room or current["room_id"] != room
                    or prior["seat"] != current["seat"]):
                raise ValueError("G141 历史转移身份不一致")
            observation = observation_from_json(prior["observation"])
            precursor = g140.precursor(observation, prior["actual_action"])
            drawn_code = current["drawn_tile"]
            actual_catch = current["observation"]["rule_state"]["catch_play"]
            captured = drawn_code in precursor["unrestricted"]["first_draw_code_list"]
            restricted = drawn_code in precursor["restricted"]["first_draw_code_list"]
            counts["transitions"] += 1
            counts[f"{peer}/{actor}/transitions"] += 1
            counts["unrestricted_captured"] += captured
            counts["restricted_captured"] += restricted
            counts["current_catch_play_true"] += bool(actual_catch)
            if not captured:
                misses.append({"peer": peer, "room": room, "actor": actor,
                               "game_id": key[0], "round_no": key[1],
                               "prior_seq": prior["draw_seq"],
                               "current_seq": current["draw_seq"],
                               "actual_drawn_tile": drawn_code})
    return {"counts": dict(sorted(counts.items())), "misses": misses,
            "source_sha256_by_unit": source_sha,
            "boundary": "以已知最终首次入口倒选历史轨迹，只核量具覆盖，不测候选增益。"}


def main() -> None:
    """一次性产出规则核对与预登记停机结论；已有结果拒绝覆盖。"""
    if OUT.exists():
        raise FileExistsError("G141 已有结果，拒绝覆盖")
    selection, stages, stage_sha = selected_panel()
    comparisons = compare(stages)
    history = observed_transition_check()
    if (history["counts"]["transitions"] != 113
            or history["counts"]["unrestricted_captured"] != 113
            or history["misses"]):
        raise ValueError("G141 历史路径核验未达到已知 113 条覆盖")
    if (comparisons["restricted"].get("strong_greater", 0) != 0
            or comparisons["unrestricted"].get("preserves_all", 0) >= 20
            or comparisons["unrestricted"]["all_protections_distinct_rooms"] >= 10):
        raise ValueError("G141 与预冻结停机判断不一致，需人工复核")
    result = {"schema": "g141-g140-precursor-summary/1",
              "inputs_sha256": {"selection": g140.sha(selection_module.OUT),
                                "g138": g140.sha(g138.OUT),
                                "g140_probe_script": g140.sha(Path(g140.__file__)),
                                "g141_script": g140.sha(Path(__file__)),
                                "stage_by_file": stage_sha},
              "selected_count": selection["selected_count"],
              "comparisons": comparisons, "historical_transition_check": history,
              "decision": "close_this_fixed_two-natural-draw_precursor_proxy",
              "decision_basis": "独有、保住旧能力且跨房的强手方向不足预登记门槛；不产生新评分候选。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"selected": len(stages),
                      "restricted": {k: v for k, v in comparisons["restricted"].items()
                                     if not k.endswith("examples")},
                      "unrestricted": {k: v for k, v in comparisons["unrestricted"].items()
                                       if not k.endswith("examples")},
                      "historical": history["counts"], "decision": result["decision"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
