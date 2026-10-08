#!/usr/bin/env python3
"""G142：沿已发生的首次爆头入口，追查上一正常摸打中强手与父代的分歧。"""

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
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g61_strong_draw_batch as g61
import g138_official_plain_baotou_opportunity as g138
import g140_plain_baotou_precursor_probe as g140
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = g140.OUT / "observed_entry_contrast.json"


def root_facts(observation, candidate) -> dict:
    """取根弃牌旧牌效与即时普通胡容量，用于标出潜在机会成本。"""
    facts = candidate.facts
    if facts is None:
        raise ValueError("G142 根弃牌事实未知")
    opportunity, complete = g138.action_opportunity(candidate)
    if not complete:
        raise ValueError("G142 根弃牌结算见证不全")
    useful = facts.standard_useful_tiles or ()
    return {"standard_shanten": facts.standard_shanten_after,
            "standard_useful_codes": len(useful),
            "standard_useful_public_capacity":
                sum(item.remaining_estimate for item in useful),
            "seven_pairs_shanten": facts.seven_pairs_shanten_after,
            "immediate_plain_capacity": opportunity["plain"],
            "immediate_plain_baotou_capacity": opportunity["plain_baotou"]}


def main() -> None:
    """这批样本按实际后果倒选，只供解释遗漏，不能作为候选收益验证。"""
    if OUT.exists():
        raise FileExistsError("G142 已有证据，拒绝覆盖")
    source = json.loads(g138.OUT.read_text(encoding="utf-8"))
    by_unit = defaultdict(list)
    entry_categories = Counter()
    for record in source["first_plain_baotou_rows"]:
        prior = record["previous_normal_draw"]
        if prior is None:
            category = "no_previous_normal_draw"
        else:
            white_grew = record["first_white_before"] > prior["white_before"]
            meld_grew = record["first_meld_count"] > prior["meld_count"]
            if (record["first_white_before"] < prior["white_before"]
                    or record["first_meld_count"] < prior["meld_count"]):
                category = "other_change"
            elif white_grew and meld_grew:
                category = "white_and_meld_increase"
            elif white_grew:
                category = "white_increase"
            elif meld_grew:
                category = "meld_increase"
            else:
                category = "same_white_meld"
        entry_categories[record["peer"] + "/" + record["actor"] + "/" + category] += 1
        if (record["actor"] == "peer" and prior is not None
                and prior["white_before"] == record["first_white_before"]
                and prior["meld_count"] == record["first_meld_count"]):
            by_unit[record["peer"], record["room"]].append(record)
    counts = Counter()
    rows = []
    input_sha = {}
    for (peer, room), records in sorted(by_unit.items()):
        path = g61.room_dir((peer, room)) / "windows.json"
        input_sha[peer + "/" + room] = g140.sha(path)
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        index = {(row["game_id"], row["round_no"], row["draw_seq"]): row
                 for row in windows}
        for record in records:
            key = (record["game_id"], record["round_no"])
            before = index[key + (record["previous_normal_draw"]["draw_seq"],)]
            after = index[key + (record["first_draw_seq"],)]
            actual = before["actual_action"]
            parent = before["parent_top_action"]
            draw = after["drawn_tile"]
            observation = observation_from_json(before["observation"])
            rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            legal = {item.action_key: item for item in rules.legal_candidates}
            if actual not in legal or parent not in legal:
                raise ValueError("G142 上一实际/父代动作不合法")
            actual_support = g140.precursor(observation, actual)["unrestricted"]
            if draw not in actual_support["first_draw_code_list"]:
                raise ValueError("G142 已发生摸牌不在强手根前驱支持集")
            counts["peer_entries"] += 1
            counts[peer + "/entries"] += 1
            counts["same_action"] += actual == parent
            if not parent.startswith("discard:"):
                counts["parent_not_discard"] += 1
                continue
            parent_support = g140.precursor(observation, parent)["unrestricted"]
            captures = draw in parent_support["first_draw_code_list"]
            counts["parent_captures_realized_draw"] += captures
            counts["different_action"] += actual != parent
            counts["different_action_parent_misses_realized_draw"] += actual != parent and not captures
            a_facts = root_facts(observation, legal[actual])
            p_facts = root_facts(observation, legal[parent])
            protections = {
                "same_standard_shanten": a_facts["standard_shanten"] == p_facts["standard_shanten"],
                "plain": a_facts["immediate_plain_capacity"] >= p_facts["immediate_plain_capacity"],
                "standard_codes": a_facts["standard_useful_codes"] >= p_facts["standard_useful_codes"],
                "standard_capacity": a_facts["standard_useful_public_capacity"] >=
                                     p_facts["standard_useful_public_capacity"],
                "seven_pairs": (p_facts["seven_pairs_shanten"] is None
                                or (a_facts["seven_pairs_shanten"] is not None
                                    and a_facts["seven_pairs_shanten"] <=
                                    p_facts["seven_pairs_shanten"])),
            }
            distinctive = actual != parent and not captures
            counts["distinctive_preserves_all"] += distinctive and all(protections.values())
            if distinctive:
                for name, preserved in protections.items():
                    counts["distinctive_preserves/" + name] += preserved
            rows.append({"peer": peer, "room": room, "game_id": key[0],
                         "round_no": key[1], "previous_draw_seq": before["draw_seq"],
                         "first_entry_draw_seq": after["draw_seq"],
                         "white_before": record["first_white_before"],
                         "meld_count": record["first_meld_count"],
                         "actual_action": actual, "parent_action": parent,
                         "realized_draw": draw,
                         "parent_captures_realized_draw": captures,
                         "actual_support_codes": actual_support.get("first_draw_codes", 0),
                         "parent_support_codes": parent_support.get("first_draw_codes", 0),
                         "actual_root_facts": a_facts, "parent_root_facts": p_facts,
                         "protections": protections})
    if counts["peer_entries"] != 79:
        raise ValueError("G142 已知强手实际首次机会轨迹计数不一致")
    result = {"schema": "g142-observed-baotou-entry-contrast/1",
              "input_sha256": {"g138_result": g140.sha(g138.OUT),
                               "script": g140.sha(Path(__file__)),
                               "strong_windows_by_unit": input_sha},
              "counts": dict(sorted(counts.items())),
              "entry_categories": dict(sorted(entry_categories.items())), "rows": rows,
              "boundary": "按实际首次普通型爆头入口倒选；未来摸牌仅用于诊断，绝不可作为线上输入或候选收益证据。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
