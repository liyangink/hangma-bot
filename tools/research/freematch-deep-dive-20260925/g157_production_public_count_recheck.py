#!/usr/bin/env python3
"""G157：用生产公开牌去重及剩余张数重算 G156 自然一步进张。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import g11_longitudinal_route_audit as g11
import g156_same_observation_natural_route as g156
import g69_route_chain_analysis as g69
from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.candidate_facts import FactsAnalysisError, _remaining
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G157-PRODUCTION-PUBLIC-COUNT-RECHECK-PREREG-2026-09-28.md')
G156_RESULT = g156.RESULT
G156_ROWS = g156.ROWS
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g157-production-public-count-recheck-20260928')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g157-production-public-count-recheck-20260928/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g157-production-public-count-recheck-20260928/result.json')


def sha(path: Path) -> str:
    """返回源码或已冻结输入的原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def old_rows() -> tuple[dict[tuple, dict], dict]:
    """读取 G156 固定动作对，不以旧或新自然容量筛选。"""
    result = json.loads(G156_RESULT.read_text(encoding="utf-8"))
    if (result["schema"] != "g156-same-observation-natural-route/1"
            or result["windows"] != 279
            or result["rows_sha256"] != sha(G156_ROWS)):
        raise ValueError("G156 固定动作对摘要漂移")
    index = {}
    with gzip.open(G156_ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["peer"], row["room"], row["game_id"],
                   row["round_no"], row["draw_seq"])
            if key in index:
                raise ValueError("G156 动作窗口重复")
            index[key] = row
    if len(index) != 279:
        raise ValueError("G156 固定动作对数量不符")
    return index, result


def production_natural(raw: dict, action: str, old_arm: dict) -> dict:
    """精确复用生产自然缺口及公开牌去重；未来墙一律不可见。"""
    observation = observation_from_json(raw["observation"])
    parsed = g11._hand(raw["observation"])
    if parsed is None:
        raise ValueError("G156 行动前不是已核正常摸打")
    full, _, meld_count = parsed
    after = g11._after_discard(full, action)
    if after is None or after["白"] != 1:
        raise ValueError("G156 固定动作不是弃后留一白的合法动作")
    waiting = counts_from_tiles(tuple(Tile(code) for code in TILE_ORDER
                                      for _ in range(after[code])))
    if sum(waiting) != 13 - 3 * meld_count:
        raise ValueError("弃后暗手张数与副露数矛盾")
    natural = waiting[:33]
    need = hand_analysis._need_std(natural, 0, 4 - meld_count, True)
    if need != old_arm["natural_need"]:
        raise ValueError("G156 自然最小补牌数与生产求解器不符")
    public = count_public_tiles(observation)
    new_public = {action.split(":", 1)[1]: 1}
    vector = {}
    for index, code in enumerate(TILE_ORDER[:33]):
        if natural[index] >= 4:
            continue  # 同码四张已全在本人手中，不存在第五张自然进张。
        next_natural = (natural[:index] + (natural[index] + 1,)
                        + natural[index + 1:])
        if hand_analysis._need_std(next_natural, 0, 4 - meld_count, True) >= need:
            continue
        capacity = _remaining(code, waiting, public, new_public)
        if capacity:
            vector[code] = capacity
    standard = {code: capacity for code, capacity in old_arm["standard_vector"]
                if code != "白" and capacity > 0}
    return {
        "natural_need": need,
        "natural_vector": vector,
        "natural_types": len(vector),
        "natural_capacity_upper": sum(vector.values()),
        "old_vector_match": vector == old_arm["natural_vector"],
        "production_standard_natural_vector_match": vector == standard,
        "standard_natural_vector": standard,
    }


def analyze(raw: dict, old: dict) -> dict:
    """同一官方窗口两动作均算；未知公开牌只标未知，不补零。"""
    if (raw["actual_action"] != old["peer_arm"]["action"]
            or raw["parent_top_action"] != old["parent_arm"]["action"]):
        raise ValueError("G156 双臂与官方行动前原始记录漂移")
    result = {"peer": old["peer"], "room": old["room"],
              "game_id": old["game_id"], "round_no": old["round_no"],
              "draw_seq": old["draw_seq"],
              "same_standard_support": old["same_standard_support"],
              "same_standard_vector": old["same_standard_vector"],
              "same_seven_shanten": old["same_seven_shanten"]}
    arms = {}
    for label in ("peer", "parent"):
        try:
            arms[label] = production_natural(raw, old[label + "_arm"]["action"],
                                             old[label + "_arm"])
        except FactsAnalysisError as exc:
            result["status"] = "unknown_public_count"
            result["reason"] = str(exc)
            return result
    p, a = arms["parent"], arms["peer"]
    result.update({
        "status": "complete", "arms": arms,
        "old_capacity_delta_peer_minus_parent": (
            old["peer_arm"]["natural_capacity_upper"]
            - old["parent_arm"]["natural_capacity_upper"]),
        "new_capacity_delta_peer_minus_parent": (
            a["natural_capacity_upper"] - p["natural_capacity_upper"]),
        "old_types_delta_peer_minus_parent": (
            old["peer_arm"]["natural_types"]
            - old["parent_arm"]["natural_types"]),
        "new_types_delta_peer_minus_parent": (a["natural_types"] - p["natural_types"]),
        "standard_support_delta_peer_minus_parent": (
            old["peer_arm"]["standard_support"]
            - old["parent_arm"]["standard_support"]),
    })
    return result


def aggregate(rows: list[dict]) -> dict:
    """按强手及即时规则事实层同时报告纠偏、残余和未知。"""
    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        tiers = ["all_changed"]
        if row["same_standard_support"]:
            tiers.append("same_standard_support")
        if row["same_standard_vector"]:
            tiers.append("same_standard_vector")
            if row["same_seven_shanten"]:
                tiers.append("same_standard_vector_and_seven")
        for tier in tiers:
            name = row["peer"] + "/" + tier
            count = groups[name]
            rooms[name].add(row["room"])
            count["windows"] += 1
            if row["status"] != "complete":
                count["unknown"] += 1
                continue
            count["complete"] += 1
            for label in ("peer", "parent"):
                arm = row["arms"][label]
                count[label + "/old_vector_mismatch"] += not arm[
                    "old_vector_match"]
                count[label + "/standard_vector_mismatch"] += not arm[
                    "production_standard_natural_vector_match"]
            for metric in ("capacity", "types"):
                old_delta = row[f"old_{metric}_delta_peer_minus_parent"]
                new_delta = row[f"new_{metric}_delta_peer_minus_parent"]
                count[metric + "/old_delta_changed"] += old_delta != new_delta
                count[metric + "/new_more"] += new_delta > 0
                count[metric + "/new_equal"] += new_delta == 0
                count[metric + "/new_less"] += new_delta < 0
            count["new_capacity_matches_standard_delta"] += (
                row["new_capacity_delta_peer_minus_parent"]
                == row["standard_support_delta_peer_minus_parent"])
    result = {name: {**dict(sorted(count.items())), "rooms": len(rooms[name])}
              for name, count in sorted(groups.items())}
    for name, count in result.items():
        if count["windows"] != count.get("complete", 0) + count.get("unknown", 0):
            raise ValueError("G157 已核与未知计数不守恒: " + name)
    return result


def main() -> None:
    """纠正 G156 全部固定动作对；已有结果拒绝覆盖。"""
    if RESULT.exists() or ROWS.exists():
        raise FileExistsError("G157 已有生产口径纠偏结果，拒绝覆盖")
    index, g156_doc = old_rows()
    source_hashes = {}
    seen = set()
    rows = []
    for peer, room in sorted({key[:2] for key in index}):
        path = g156.g61_room_path(peer, room)
        original, raw_sha = g69.load_windows(path)
        previous = g156_doc["raw_window_hashes"][peer + "/" + room]
        if raw_sha != previous["raw_sha256"] or sha(path) != previous[
                "file_sha256"]:
            raise ValueError("G156 原始官方观察摘要漂移")
        source_hashes[peer + "/" + room] = previous
        for raw in original:
            key = (peer, room, raw["game_id"], raw["round_no"],
                   raw["draw_seq"])
            if key not in index:
                continue
            if key in seen:
                raise ValueError("G157 官方窗口身份重复")
            seen.add(key)
            rows.append(analyze(raw, index[key]))
    if seen != index.keys() or len(rows) != 279:
        raise ValueError("G157 固定 G156 动作对没有完整重算")
    summary = aggregate(rows)
    OUT.mkdir(parents=True, exist_ok=False)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in rows).encode("utf-8")
    ROWS.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    result = {
        "schema": "g157-production-public-count-recheck/1",
        "exploratory": True,
        "source_sha256": {"prereg": sha(PREREG), "script": sha(Path(__file__)),
                          "g156_result": sha(G156_RESULT),
                          "g156_rows": sha(G156_ROWS),
                          "public_tile_counts": sha(
                              _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/public_tile_counts.py")),
                          "candidate_facts": sha(
                              _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/candidate_facts.py"))},
        "raw_window_hashes": source_hashes,
        "rows_sha256": sha(ROWS), "windows": len(rows), "groups": summary,
        "boundary": "只纠正 G156 279 个同观察动作对的一步自然补牌公开上界；未估隐藏墙概率、后继行动、他家先胡或整桌收益。",
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
