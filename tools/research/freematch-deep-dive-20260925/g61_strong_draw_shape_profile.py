#!/usr/bin/env python3
"""G61：仅用动作前合法规则事实，量化强手严格弃牌分歧的牌效方向。"""

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

import c31_action_layer_gap as c31
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/shape_profile.json')
PEERS = ("xuanwu_2346", "tengshe_0638")


def sha(path: Path) -> str:
    """摘要绑定房间结果及本地分析源码。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def bucket(value: int) -> str:
    """白板张数分层，不推断任何隐藏牌。"""

    return "2plus" if value >= 2 else str(value)


def support(facts, field: str) -> dict | None:
    """规则公开未见支持：码数和物理张数，不冒充墙中概率。"""

    entries = getattr(facts, field)
    if entries is None:
        return None
    return {"codes": sum(item.remaining_estimate > 0 for item in entries),
            "capacity": sum(item.remaining_estimate for item in entries),
            "by_tile": {item.code: item.remaining_estimate for item in entries}}


def fact(facts) -> dict | None:
    """保留可空规则事实，不能用零代表未知。"""

    if facts is None:
        return None
    return {"fact_kind": facts.fact_kind.value,
            "combined": facts.shanten_after,
            "ordinary": facts.standard_shanten_after,
            "seven": facts.seven_pairs_shanten_after,
            "support": support(facts, "useful_tiles"),
            "ordinary_support": support(facts, "standard_useful_tiles"),
            "seven_support": support(facts, "seven_pairs_useful_tiles"),
            "baotou_after": facts.baotou_after,
            "completeness": facts.completeness.value}


def compare(parent: dict, actual: dict) -> dict:
    """同动作窗比较生产事实；只在同向听层比较容量。"""

    ans = {}
    for field in ("combined", "ordinary", "seven"):
        a, p = actual[field], parent[field]
        ans[field + "_delta"] = None if a is None or p is None else a - p
    for field in ("support", "ordinary_support", "seven_support"):
        a, p = actual[field], parent[field]
        level = {"support": "combined", "ordinary_support": "ordinary",
                 "seven_support": "seven"}[field]
        if a is None or p is None or ans[level + "_delta"] != 0:
            ans[field + "_capacity_delta_same_layer"] = None
            ans[field + "_codes_delta_same_layer"] = None
            continue
        ans[field + "_capacity_delta_same_layer"] = a["capacity"] - p["capacity"]
        ans[field + "_codes_delta_same_layer"] = a["codes"] - p["codes"]
    ans["baotou_parent"] = parent["baotou_after"]
    ans["baotou_actual"] = actual["baotou_after"]
    return ans


def main() -> None:
    """按房保存行为与牌效事实；拒绝读取 G60 收益或动作后事件。"""

    if OUT.exists():
        raise SystemExit("G61 形状画像已存在，拒绝覆盖")
    batch_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if len(batch["units"]) != 32 or batch["outcome_labels_opened"] is not False:
        raise ValueError("G61 动作批次未完整或结算标签边界变化")
    counts: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    strict = []
    for key in sorted(batch["units"]):
        peer, room = key.split("/", 1)
        if peer not in PEERS:
            raise ValueError("未知强手身份")
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != batch["units"][key]["windows_sha256"]:
            raise ValueError("G61 逐窗证据摘要漂移")
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for row in windows:
            white = row["observation"]["my_hand"].count("白")
            strata = [peer + "/all", peer + "/white_" + bucket(white)]
            if row["seat"] == row["dealer_seat"]:
                strata.append(peer + "/dealer")
            if row["own_meld_count"]:
                strata.append(peer + "/melded")
            for group in strata:
                counts[group]["clean_windows"] += 1
            if row["parent_agrees"]:
                for group in strata:
                    counts[group]["agrees"] += 1
                continue
            gap = row["parent_score_gap_top_minus_actual"]
            if type(gap) not in (float, int) or gap < 0:
                raise ValueError("冻结父代分差非法")
            family = row["parent_top_action"].split(":", 1)[0]
            for group in strata:
                counts[group]["disagrees"] += 1
                counts[group]["ties" if gap == 0 else "strict"] += 1
                counts[group]["parent_" + family] += 1
                rooms[group]["disagreement"].add(room)
                if gap > 0:
                    rooms[group]["strict"].add(room)
            if gap == 0 or family != "discard":
                continue
            observation = observation_from_json(row["observation"])
            rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            legal = {item.action_key: item.facts for item in rules.legal_candidates}
            if row["actual_action"] not in legal or row["parent_top_action"] not in legal:
                raise ValueError("G61 重算规则缺强手动作或父代首选")
            parent = fact(legal[row["parent_top_action"]])
            actual = fact(legal[row["actual_action"]])
            if parent is None or actual is None:
                raise ValueError("G61 弃牌规则事实缺失")
            delta = compare(parent, actual)
            record = {"peer": peer, "room": room,
                      "game_id": row["game_id"], "round_no": row["round_no"],
                      "draw_seq": row["draw_seq"],
                      "strong_action": row["actual_action"],
                      "parent_action": row["parent_top_action"],
                      "parent_score_gap": gap,
                      "white_before": white,
                      "dealer": row["seat"] == row["dealer_seat"],
                      "own_meld_count": row["own_meld_count"],
                      "wall_remaining": row["remaining_tile_count"],
                      "parent_fact": parent, "strong_fact": actual,
                      "delta": delta}
            strict.append(record)
            for group in strata:
                counts[group]["strict_discard_vs_discard"] += 1
                for field in ("combined_delta", "ordinary_delta", "seven_delta"):
                    value = delta[field]
                    if value is not None:
                        counts[group][field + "_better" if value < 0 else
                                      field + "_worse" if value > 0 else
                                      field + "_same"] += 1
                for field in ("support_capacity_delta_same_layer",
                              "support_codes_delta_same_layer",
                              "ordinary_support_capacity_delta_same_layer",
                              "ordinary_support_codes_delta_same_layer"):
                    value = delta[field]
                    if value is not None:
                        counts[group][field + "_wider" if value > 0 else
                                      field + "_narrower" if value < 0 else
                                      field + "_same"] += 1
    result = {"schema": "g61-strong-draw-shape-profile/1",
              "batch_sha256": sha(batch_path),
              "script_sha256": sha(Path(__file__)),
              "outcome_labels_opened": False,
              "counts": {key: dict(sorted(value.items())) for key, value in sorted(counts.items())},
              "room_coverage": {key: {kind: len(ids) for kind, ids in row.items()}
                                for key, row in sorted(rooms.items())},
              "strict_discard_rows": strict,
              "boundary": "只比较生产 CandidateFacts 和已记录父代评分；公开未见容量不是牌墙概率，强手动作不是收益标签。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": {peer: result["counts"][peer + "/all"]
                                 for peer in PEERS},
                      "strict_discard_rows": len(strict)},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
