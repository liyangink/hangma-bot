#!/usr/bin/env python3
"""G144：按事前起手白板与牌形，对普通型爆头首次机会作房级描述性对照。"""

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
import random


HERE = Path(__file__).resolve().parent
G70 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/initial_shape_rounds.jsonl.gz')
G70_RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/initial_shape_result.json')
G138 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g138-official-plain-baotou-opportunity-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g144-opening-shape-baotou-gap-20260928/result.json')
PEERS = ("xuanwu_2346", "tengshe_0638")
SEED = 20260928
DRAWS = 20000


def sha(path: Path) -> str:
    """冻结复用的官方起手牌形与行动前机会证据字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stratum(row: dict, shape_adjusted: bool) -> str:
    """起手分层只读本人最初手牌；庄家已由 G70 归一成最佳合法十三张。"""
    white = "2plus" if row["initial_white"] >= 2 else str(row["initial_white"])
    if not shape_adjusted:
        return white
    return white + "/" + ("standard_0to2" if row["initial_standard_best"] <= 2
                          else "standard_3plus")


def standardized(room_counts: dict, peer: str, rooms: list[str], *,
                 shape_adjusted: bool) -> dict | None:
    """合并双方的起手分布作共同权重，返回强手减我方每百单局首次机会。"""
    totals = defaultdict(Counter)
    for room in rooms:
        for actor in ("peer", "us"):
            for key, value in room_counts[peer, room, actor, shape_adjusted].items():
                totals[actor][key] += value
    strata = sorted({key[0] for actor in ("peer", "us") for key in totals[actor]})
    all_hands = sum(totals[a][s, "hands"] for a in ("peer", "us") for s in strata)
    if not all_hands:
        raise ValueError("G144 空起手母体")
    components = {}
    difference = 0.0
    for s in strata:
        peer_n, us_n = (totals[a][s, "hands"] for a in ("peer", "us"))
        if not peer_n or not us_n:
            return None
        peer_yes, us_yes = (totals[a][s, "opportunity"] for a in ("peer", "us"))
        weight = (peer_n + us_n) / all_hands
        diff = 100.0 * (peer_yes / peer_n - us_yes / us_n)
        difference += weight * diff
        components[s] = {"peer_hands": peer_n, "us_hands": us_n,
                         "peer_opportunity": peer_yes, "us_opportunity": us_yes,
                         "peer_per100": 100.0 * peer_yes / peer_n,
                         "us_per100": 100.0 * us_yes / us_n,
                         "common_weight": weight,
                         "peer_minus_us_per100": diff}
    return {"peer_minus_us_per100": difference, "strata": components}


def main() -> None:
    """G138 后果已被查看；本试验只校正描述性起手供给，不签发策略因果收益。"""
    if OUT.exists():
        raise FileExistsError("G144 已有结果，拒绝覆盖")
    shape_result = json.loads(G70_RESULT.read_text(encoding="utf-8"))
    opportunity_result = json.loads(G138.read_text(encoding="utf-8"))
    if (shape_result["rows"] != 5120
            or opportunity_result["actor_hands"] != 5120
            or len(opportunity_result["first_plain_baotou_rows"]) != 239):
        raise ValueError("G144 官方起手／机会母体不符")
    offered = {(r["peer"], r["room"], r["game_id"], r["round_no"], r["actor"])
               for r in opportunity_result["first_plain_baotou_rows"]}
    if len(offered) != 239:
        raise ValueError("G144 首次机会座位单局键重复")
    room_counts: dict[tuple[str, str, str, bool], Counter] = defaultdict(Counter)
    seen = set()
    with gzip.open(G70, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["peer"], row["room"], row["game_id"],
                   row["round_no"], row["actor"])
            if key in seen or row["peer"] not in PEERS or row["actor"] not in ("peer", "us"):
                raise ValueError("G144 起手单局身份重复或对手不在母体")
            seen.add(key)
            for shape_adjusted in (False, True):
                s = stratum(row, shape_adjusted)
                counter = room_counts[row["peer"], row["room"],
                                      row["actor"], shape_adjusted]
                counter[s, "hands"] += 1
                counter[s, "opportunity"] += key in offered
    if len(seen) != 5120 or not offered.issubset(seen):
        raise ValueError("G144 起手与机会键不能全量连接")
    rooms_by_peer = defaultdict(set)
    for peer, room, _game, _round, _actor in seen:
        rooms_by_peer[peer].add(room)
    if {peer: len(rooms_by_peer[peer]) for peer in PEERS} != {
            "xuanwu_2346": 15, "tengshe_0638": 17}:
        raise ValueError("G144 强手房覆盖漂移")
    rng = random.Random(SEED)
    results = {}
    for peer in PEERS:
        rooms = sorted(rooms_by_peer[peer])
        by_method = {}
        for shape_adjusted in (False, True):
            observed = standardized(room_counts, peer, rooms,
                                    shape_adjusted=shape_adjusted)
            if observed is None:
                raise ValueError("G144 原始分层存在零分母")
            draws = []
            missing = 0
            for _ in range(DRAWS):
                sampled = [rooms[rng.randrange(len(rooms))] for _ in rooms]
                summary = standardized(room_counts, peer, sampled,
                                       shape_adjusted=shape_adjusted)
                if summary is None:
                    missing += 1
                    continue
                draws.append(summary["peer_minus_us_per100"])
            if len(draws) < DRAWS * .95:
                raise ValueError("G144 房级重采样后分层零分母过多")
            draws.sort()
            by_method["start_white_and_standard" if shape_adjusted else "start_white"] = {
                **observed, "room_bootstrap_95pct": [
                    draws[int(len(draws) * .025)], draws[int(len(draws) * .975)]],
                "valid_resamples": len(draws), "zero_denominator_resamples": missing}
        results[peer] = {"rooms": len(rooms), "actor_hands_each": len(rooms) * 80,
                         "methods": by_method}
    result = {"schema": "g144-opening-shape-baotou-gap/1",
              "inputs_sha256": {"g70_rows": sha(G70),
                                "g70_result": sha(G70_RESULT),
                                "g138_result": sha(G138),
                                "script": sha(Path(__file__))},
              "bootstrap_seed": SEED, "bootstrap_draws": DRAWS,
              "peers": results,
              "boundary": "起手白板与普通型向听的事后分层、房级描述性重采样；起手形状以生产数学计算但不同玩家起手仍非同手牌随机策略对照。机会出现也可能受后续运气、吃碰、抓打和截尾影响。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({peer: {method: {"gap": value["peer_minus_us_per100"],
                                      "ci": value["room_bootstrap_95pct"],
                                      "valid": value["valid_resamples"]}
                                    for method, value in entry["methods"].items()}
                      for peer, entry in results.items()},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
