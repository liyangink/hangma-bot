#!/usr/bin/env python3
"""C31 小工具：重建保真度对拍 + 暗牌泄漏扰动检查（只读）。

两件事：
1. 把「官方牌谱重建的响应窗口观察」与生产视图缓存
   （.team-work/p6-baotou-route/cache/*.jsonl.gz，只含 c23/C27 同口径的冻结 R18 v2 战役）
   按 (game_id, round_no, trigger_seq) 连接，逐字段对拍 my_hand / discards / melds /
   hand_counts / remaining_tile_count / table_scores / rule_state / responding_seats。
   这是「把冻结父代搬到对手窗口上重判」的合法性前提：重建必须与生产同口径。
2. 暗牌扰动不变量：改非主体座位的暗牌（保持张数）不得改变该座视图；
   改主体座位自己的暗牌必须改变视图。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c31_rebuild_validate.py
"""

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

import collections
import gzip
import json
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "freematch-deep-dive-20260925")))

import anatomy_lib as AL  # noqa: E402
import c31_action_layer_gap as C31  # noqa: E402

FIELDS = ("phase", "seat", "turn_seat", "responding_seats", "my_hand", "discards",
          "melds", "hand_counts", "remaining_tile_count", "table_scores",
          "wealth_god", "baotou", "chain_count", "catch_play", "owner")


def load_cache():
    """生产视图缓存：只保留响应窗口。"""

    index = collections.defaultdict(list)
    for path in sorted(Path(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache")).glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("phase") not in ("response_peng", "response_chi"):
                    continue
                index[(row.get("game_id"), row.get("round_no"), row.get("trigger_seq"))].append(row)
    return index


def compare(production, snap, phase, game_id, round_no, seat):
    """逐字段对拍；返回不匹配的字段名列表。"""

    observation = C31.build_observation(snap, seat, phase, game_id, round_no)
    visible = production["view"]["visible_state"]
    mismatches = []
    if observation.phase != visible["phase"]:
        mismatches.append("phase")
    if observation.seat != visible["seat"]:
        mismatches.append("seat")
    if observation.turn_seat != visible["turn_seat"]:
        mismatches.append("turn_seat")
    if sorted(observation.responding_seats) != sorted(visible["responding_seats"]):
        mismatches.append("responding_seats")
    if collections.Counter(tile.code for tile in observation.my_hand) != collections.Counter(
            visible["my_hand"]):
        mismatches.append("my_hand")
    mine = tuple(tuple(tile.code for tile in river) for river in observation.discards)
    theirs = tuple(tuple(river) for river in visible["discards"])
    if mine != theirs:
        mismatches.append("discards")
    mine_melds = tuple(sorted(
        (index, group.kind, tuple(sorted(tile.code for tile in group.tiles)))
        for index, row in enumerate(observation.melds) for group in row))
    their_melds = tuple(sorted(
        (index, group["kind"], tuple(sorted(group["tiles"])))
        for index, row in enumerate(visible["melds"]) for group in row))
    if mine_melds != their_melds:
        mismatches.append("melds")
    if tuple(observation.hand_counts) != tuple(visible["hand_counts"]):
        mismatches.append("hand_counts")
    if observation.remaining_tile_count != visible["remaining_tile_count"]:
        mismatches.append("remaining_tile_count")
    if tuple(observation.scores) != tuple(visible["table_scores"]):
        mismatches.append("table_scores")
    state = observation.rule_state
    their_state = visible["rule_state"]
    if state.wealth_god.code != their_state["wealth_god"]:
        mismatches.append("wealth_god")
    if bool(state.baotou) != bool(their_state["baotou"]):
        mismatches.append("baotou")
    if int(state.chain_count) != int(their_state["chain_count"]):
        mismatches.append("chain_count")
    if bool(state.catch_play) != bool(their_state["catch_play"]):
        mismatches.append("catch_play")
    if state.catch_play_owner_seat != their_state["catch_play_owner_seat"]:
        mismatches.append("owner")
    return mismatches, observation


def main():
    cache = load_cache()
    print("生产响应窗口缓存：%d 个 (game,round,seq) 键 / %d 条窗口"
          % (len(cache), sum(len(v) for v in cache.values())))
    games = {game["game_id"]: game for game in AL.load_games()}
    wanted = {key[0] for key in cache}
    print("缓存涉及 %d 场；本地牌谱命中 %d 场" % (len(wanted), len(wanted & set(games))))

    counts = collections.Counter()
    examples = []
    checked = 0
    for game_id in sorted(wanted & set(games)):
        document = games[game_id]["doc"]
        block_meta = C31.round_metadata(document)
        table = [0, 0, 0, 0]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            ended_dealer, ended_scores = C31.round_end_facts(events)
            dealer = (block_meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                dealer = ended_dealer
            if dealer is None:
                dealer = next((index for index, hand in enumerate(start_hands)
                               if len(hand) == 14), None)
            if dealer is None:
                continue
            snaps = C31.reconstruct(events, start_hands, table, dealer)
            for key in [item for item in cache if item[0] == game_id and item[1] == round_no]:
                snap = snaps.get(key[2])
                if snap is None:
                    counts["missing_snapshot"] += 1
                    seqs = {event["seq"] for event in events}
                    counts["missing_snapshot_event_seq" if key[2] in seqs
                           else "missing_snapshot_unknown_seq"] += 1
                    continue
                for production in cache[key]:
                    seat = production["view"]["visible_state"]["seat"]
                    checked += 1
                    mismatches, observation = compare(
                        production, snap, production["phase"], game_id, round_no, seat)
                    if not mismatches:
                        counts["ok"] += 1
                        continue
                    for name in mismatches:
                        counts["mismatch:" + name] += 1
                    their_state = production["view"]["visible_state"]["rule_state"]
                    if "chain_count" in mismatches:
                        counts["chain_pair:%s->%s" % (
                            their_state["chain_count"], observation.rule_state.chain_count)] += 1
                    if len(examples) < 5:
                        examples.append({
                            "key": list(key), "phase": production["phase"], "seat": seat,
                            "mismatches": mismatches,
                            "prod_chain": their_state["chain_count"],
                            "prod_baotou": their_state["baotou"],
                            "mine_chain": observation.rule_state.chain_count,
                            "mine_baotou": observation.rule_state.baotou,
                            "prod_hand_counts": production["view"]["visible_state"]["hand_counts"],
                        })
            if ended_scores is not None:
                table = [a + b for a, b in zip(table, ended_scores)]

    print()
    print("逐字段对拍：受检窗口 %d，完全一致 %d" % (checked, counts["ok"]))
    for name in FIELDS:
        value = counts["mismatch:" + name]
        if value:
            print("  不符 %-22s %d（%.2f%%）" % (name, value, 100.0 * value / max(1, checked)))
    if counts["missing_snapshot"]:
        print("  缓存里有、重建里没有的快照：%d" % counts["missing_snapshot"])
    for name, value in sorted(counts.items()):
        if name.startswith("chain_pair:"):
            print("  chain_count 对（生产->重建）：%s 共 %d" % (name.split(":", 1)[1], value))
    if counts["missing_snapshot_event_seq"] or counts["missing_snapshot_unknown_seq"]:
        print("  缺快照细分：seq 在该局事件流里 %d 条（非弃牌事件，生产 trigger 退化），"
              "不在事件流里 %d 条" % (counts["missing_snapshot_event_seq"],
                                      counts["missing_snapshot_unknown_seq"]))
    for item in examples:
        print("  样例 %s" % json.dumps(item, ensure_ascii=False)[:400])

    # ---- 泄漏扰动检查 ----
    print()
    print("== 暗牌扰动不变量")
    probed = 0
    violated = 0
    sensitivity = 0
    insensitive = 0
    for game_id in sorted(wanted & set(games))[:8]:
        document = games[game_id]["doc"]
        block_meta = C31.round_metadata(document)
        table = [0, 0, 0, 0]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            ended_dealer, ended_scores = C31.round_end_facts(events)
            dealer = (block_meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                dealer = ended_dealer
            if dealer is None:
                dealer = next((index for index, hand in enumerate(start_hands)
                               if len(hand) == 14), None)
            if dealer is None:
                continue
            snaps = C31.reconstruct(events, start_hands, table, dealer)
            for seq in sorted(snaps)[:4]:
                snap = snaps[seq]
                for seat in range(4):
                    if seat == snap["discarder"]:
                        continue
                    phase = "response_peng"
                    baseline = C31.build_observation(snap, seat, phase, game_id, round_no)
                    # 改其它三家的暗牌（保持张数 ⇒ hand_counts 不变、公开事实不变）
                    others = [index for index in range(4) if index != seat]
                    snapshot2 = dict(snap)
                    snapshot2["hands"] = [collections.Counter(snap["hands"][index])
                                          for index in range(4)]
                    a, b = others[0], others[1]
                    codes_a = sorted(snapshot2["hands"][a].elements())
                    codes_b = sorted(snapshot2["hands"][b].elements())
                    if codes_a and codes_b:
                        snapshot2["hands"][a][codes_a[0]] -= 1
                        snapshot2["hands"][b][codes_a[0]] += 1
                        snapshot2["hands"][b][codes_b[0]] -= 1
                        snapshot2["hands"][a][codes_b[0]] += 1
                    perturbed = C31.build_observation(snapshot2, seat, phase, game_id, round_no)
                    probed += 1
                    if str(baseline) != str(perturbed):
                        violated += 1
                    # 反向对照：改主体**自己**的暗牌必须改变视图（探针灵敏度）
                    snapshot3 = dict(snap)
                    snapshot3["hands"] = [collections.Counter(snap["hands"][index])
                                          for index in range(4)]
                    own = sorted(snapshot3["hands"][seat].elements())
                    replacement = next((code for code in C31.TILE_ORDER
                                        if code != own[0]
                                        and snapshot3["hands"][seat][code] < 4), None)
                    if own and replacement is not None:
                        snapshot3["hands"][seat][own[0]] -= 1
                        snapshot3["hands"][seat][replacement] += 1
                        changed = C31.build_observation(
                            snapshot3, seat, phase, game_id, round_no)
                        sensitivity += 1
                        if str(changed) == str(baseline):
                            insensitive += 1
            if ended_scores is not None:
                table = [a + b for a, b in zip(table, ended_scores)]
    print("扰动探针 %d 次；非主体座位暗牌改动导致视图变化 %d 次 -> %s"
          % (probed, violated, "通过" if violated == 0 else "**失败**"))
    print("灵敏度对照：改主体自己暗牌 %d 次，视图未变 %d 次 -> %s"
          % (sensitivity, insensitive, "通过" if insensitive == 0 else "**失败**"))

    bad = [path for path in C31.READ_PATHS
           if "events.json" not in path and "leaderboard-week.json" not in path
           and "rounds.jsonl" not in path and ".jsonl.gz" not in path]
    print("读取路径断言：%d 条，越界 %d 条" % (len(C31.READ_PATHS), len(bad)))
    return 0 if not violated else 1


if __name__ == "__main__":
    raise SystemExit(main())
