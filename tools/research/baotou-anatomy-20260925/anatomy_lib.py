#!/usr/bin/env python3
"""爆头通道拆解：官方牌谱的手牌重建与规则判定公共库。

信息权限：本模块只读**赛后**官方牌谱 `events.json`（四家起手牌 + 事件流），
属于赛后完整信息；不读取线上 `PlayerObservation`，不访问网络。

单一规则来源纪律（根 AGENTS.md §5）：本模块**不实现**任何向听、听牌、爆头、
分解或财神判定，全部经 `hangma`：

- 爆头结构：`hangma.progression.baotou_after_discard` / `baotou_after_draw`
  → 最终落到 `hand_analysis.any_tile_win`；
- 向听与有效牌：`hand_analysis.analyse_hand`；
- 成胡分解与财神用法：`hand_analysis.win_split(...).evidence`。

重建口径来自 `review/r18-four-arm-evaluation-2026-09-23/audit_claim_opportunities.py`
的 `analyze()` 事件循环（吃/碰/杠的暗牌扣减规则与其逐字一致），此处**复用其口径**
并把每巡暗牌完整留存，不另写第二套。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = _PROJECT_ROOT
if str(_project_file(_PROJECT_ROOT, ROOT / "src")) not in sys.path:
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_ORDER  # noqa: E402
from hangma_bot.hangma.progression import (  # noqa: E402
    baotou_after_discard,
    baotou_after_draw,
    chain_after_discard,
    chain_after_gang,
)
from hangma_bot.hangma.settlement import compute_fan  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

ME = "u_13495c3d79c8"
"""我方账号标识；本目录所有报告的「我方」均指该账号。"""

WEALTH = "白"
ALL_CODES = tuple(TILE_ORDER)


# ---------------------------------------------------------------------------
# 牌谱加载（按 game_id 去重）
# ---------------------------------------------------------------------------


def load_games():
    """全部唯一官方牌谱；同一 game_id 多份副本时取 mtime 最新的一份。

    官方牌谱会被重复下载（本次实测 627 份文件 → 560 个唯一 game_id，
    67 份重复副本），不去重会重复计入。
    """

    paths = []
    paths.extend(glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / "*" / "official" / "dl-*" / "events.json"))))
    paths.extend(glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / "datasets" / "derived" / "*" / "official" / "*" / "official" / "dl-*" / "events.json"))))
    seen = {}
    for path in sorted(set(paths)):
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        game_id = document.get("game_id")
        if not game_id:
            continue
        prior = seen.get(game_id)
        if prior is not None and os.path.getmtime(path) < prior[0]:
            continue
        seen[game_id] = (os.path.getmtime(path), path, document)
    games = []
    for game_id, (_mt, path, document) in sorted(seen.items()):
        games.append({"game_id": game_id, "path": path, "doc": document,
                      "session": session_of(path)})
    return games


def session_of(path):
    """牌谱所属的战役目录名（P6 报告里的「房」用的就是这一层名字）。

    `artifacts/sessions/<session>/official/dl-*/events.json` → `<session>`；
    `datasets/derived/<name>/...` → `derived:<name>`。
    """

    parts = Path(path).parts
    for anchor in ("sessions", "derived"):
        if anchor in parts:
            index = len(parts) - 1 - parts[::-1].index(anchor)
            if index + 1 < len(parts):
                name = parts[index + 1]
                return name if anchor == "sessions" else "derived:" + name
    return "unknown"


def round_blocks(doc):
    """把一个牌谱按 `round_no` 切成单局；块内事件按 seq 全局有序。

    官方 `events.json` 的 block 是**序号分片**（约 128 事件一块），与单局
    边界无关；只有每局第一块带 `start_hands`。因此按 round_no 归并。
    """

    grouped = {}
    starts = {}
    for block in doc.get("blocks") or []:
        round_no = block["round_no"]
        grouped.setdefault(round_no, []).extend(block.get("events") or [])
        initial = block.get("start_hands")
        if initial and all(isinstance(hand, list) for hand in initial):
            starts[round_no] = initial
    for round_no in sorted(grouped):
        events = sorted(grouped[round_no], key=lambda event: event["seq"])
        yield round_no, events, starts.get(round_no)


# ---------------------------------------------------------------------------
# 单局重建
# ---------------------------------------------------------------------------


def _tiles(counter):
    """计数 → 按规范牌序展开的 Tile 元组（规则入口只接受牌元组）。"""

    result = []
    for code in ALL_CODES:
        result.extend([Tile(code)] * counter[code])
    return tuple(result)


def coverage(hand13, meld_count):
    """13 张等待手牌的「爆头宽度」：成胡牌种数 / 物理可得牌种数。

    两个数都由 hangma 产出：成胡判定用 `win_split`（该牌入手的 14 张口径）。
    爆头 ⟺ 两个数相等（与 `any_tile_win` 等价）；本库在自检里对拍一次，
    不在分析中另写胡牌判定。
    """

    counts = Counter(tile.code for tile in hand13)
    available = 0
    winning = 0
    for code in ALL_CODES:
        if counts[code] >= 4:
            continue
        available += 1
        if hand_analysis.win_split(hand13 + (Tile(code),), meld_count) is not None:
            winning += 1
    return winning, available


def drop_tile(hand, code):
    """从暗牌元组里去掉首个同码实例（弃牌后的暗牌）。"""

    held = list(hand)
    for index, tile in enumerate(held):
        if tile.code == code:
            del held[index]
            return tuple(held)
    return None


def reachability(hand_before, meld_count, chosen, graded=True):
    """一个弃牌窗口上的「爆头可达性」事实；全部判定经 hangma。

    口径：
    - 必要条件 is_win：14 张口径的该手牌本身已是一副成胡牌。理由是
      any_tile_win 要求「弃后 13 张 + 任意一张都胡」，而「任意一张」包含
      刚弃掉的那种牌（弃后该种仍有 ≤3 张，物理可得），于是
      「弃后 13 张 + 弃掉的那张」= 原 14 张必须也胡。该必要条件在
      step4_route_loss.py 的暴力对拍里验证，不当作免检假设。
    - n_targets：合法弃牌中能让弃后暗牌满足爆头的那些（经
      hangma 的 baotou_after_discard）。
    - better_than_chosen：以 hangma 的 analyse_hand 为准的描述性比较——
      在该窗口上对每个候选弃牌取 (向听, 有效牌种数) 字典序，统计严格优于
      实际所选的候选个数；只作描述，不参与 Q4 的判定。
    """

    codes = sorted({tile.code for tile in hand_before})
    is_win = hand_analysis.win_split(hand_before, meld_count) is not None
    record = {
        "is_win": is_win,
        "n_candidates": len(codes),
        "n_targets": 0,
        "chosen_target": None,
        "better_than_chosen": 0,
    }
    if not is_win:
        return record
    chosen_after = drop_tile(hand_before, chosen)
    if chosen_after is not None:
        record["chosen_target"] = bool(baotou_after_discard(chosen_after, meld_count))
    targets = 0
    keys = {}
    for code in codes:
        after = drop_tile(hand_before, code)
        if after is None:
            continue
        if baotou_after_discard(after, meld_count):
            targets += 1
        if graded:
            summary = hand_analysis.analyse_hand(after, meld_count)
            keys[code] = (summary.shanten, -len(summary.useful_tiles))
    record["n_targets"] = targets
    if graded and chosen in keys:
        chosen_key = keys[chosen]
        record["better_than_chosen"] = sum(1 for key in keys.values() if key < chosen_key)
    return record


def reconstruct_round(events, start_hands):
    """重建一局的四家暗牌与全部等待态。

    口径与 `audit_claim_opportunities.py:analyze` 的扣减规则逐字一致：
    摸牌 +1；弃牌 -1；碰 -2；吃扣掉除被吃牌外的两张；杠按
    明 3 / 暗 4 / 补 1 扣暗牌。该脚本自报「手牌重建错误 0」，本库在每个
    扣减后立即检查负计数，任何为负即记为该局重建失败。
    """

    discard_profile = [[], [], [], []]
    hands = [Counter(hand) for hand in start_hands]
    melds = [0, 0, 0, 0]
    meld_tiles = [[], [], [], []]
    # 起手状态：13 张的座位是一个合法等待态，用 hangma 的弃牌后判定入口
    # （同为 "弃后暗牌重新判定" 语义）；庄家起手 14 张，其摸前 13 张不可从
    # 牌谱唯一还原（见报告「重建口径与已知缺口」），故置 None=未知。
    baotou = [
        None if len(hand) == 14 else baotou_after_discard(_tiles(Counter(hand)), 0)
        for hand in start_hands
    ]
    # 动作链：链次数与链内飘出数。用 hangma 的转移函数逐动作推进，不另写规则。
    chain = [0, 0, 0, 0]
    piao = [0, 0, 0, 0]
    chain_unknown = []
    waits = [[], [], [], []]
    discards = [[], [], [], []]
    draws = [[], [], [], []]
    discard_windows = []
    errors = []

    def snapshot(seat, kind, seq, turn):
        """记录一个等待态（暗牌张数应为 13-3×副露数），并做爆头与向听判定。"""

        hand = _tiles(hands[seat])
        expected = 13 - 3 * melds[seat]
        if len(hand) != expected:
            errors.append("等待态张数异常 seat=%d seq=%d 得到 %d 期望 %d" % (seat, seq, len(hand), expected))
            return
        summary = hand_analysis.analyse_hand(hand, melds[seat])
        waits[seat].append({
            "kind": kind,
            "seq": seq,
            "turn": turn,
            "draws_so_far": len(draws[seat]),
            "discards_so_far": len(discards[seat]),
            "baotou": bool(baotou[seat]),
            "state_known": baotou[seat] is not None,
            "whites": hands[seat][WEALTH],
            "shanten": summary.shanten,
            "standard_shanten": summary.standard_shanten,
            "chiitoi_shanten": summary.chiitoi_shanten,
            "useful_n": len(summary.useful_tiles),
        })

    for seat in range(4):
        if baotou[seat] is not None:
            snapshot(seat, "deal", 0, -1)

    last_action = [None, None, None, None]
    hu_windows = []
    pending_hu = None
    previous_event = None
    for event in events:
        kind = event["type"]
        seat = event.get("seat")
        tile = event.get("tile")
        data = event.get("data") or {}

        if kind == "round_ended":
            if pending_hu is not None and pending_hu["chosen"] is None:
                pending_hu["chosen"] = "hu" if event.get("seat") == pending_hu["seat"] else "none"
                pending_hu = None
            break
        if kind in ("pass", "timeout"):
            previous_event = event
            continue
        if kind == "tile_drawn":
            drawn = Tile(tile)
            replacement = (
                previous_event is not None
                and previous_event["type"] == "gang"
                and previous_event.get("seat") == seat
                and previous_event["seq"] == event["seq"] - 1
            )
            pre = _tiles(hands[seat])
            hands[seat][tile] += 1
            draws[seat].append(tile)
            baotou[seat] = baotou_after_draw(
                baotou[seat], pre, melds[seat], drawn, replacement=bool(replacement)
            )
            # 摸牌窗口上的「已成胡」判定：这是「自摸胡 vs 弃胡换爆头」的决策点。
            # 该决策在事件流里可直接观察：随后是 round_ended（选胡）还是本人
            # tile_discarded（弃胡）。
            full = _tiles(hands[seat])
            if len(full) == 14 - 3 * melds[seat] and \
                    hand_analysis.win_split(full, melds[seat]) is not None:
                targets = []
                for code in sorted({t.code for t in full}):
                    after = drop_tile(full, code)
                    if after is not None and baotou_after_discard(after, melds[seat]):
                        targets.append(code)
                pending_hu = {
                    "seat": seat,
                    "seq": event["seq"],
                    "turn": len(draws[seat]) - 1,
                    "melds": melds[seat],
                    "whites": hands[seat][WEALTH],
                    "baotou_after_draw": bool(baotou[seat]),
                    "targets": targets,
                    "chosen": None,
                }
                hu_windows.append(pending_hu)
        elif kind == "tile_discarded":
            if pending_hu is not None and pending_hu["seat"] == seat and pending_hu["chosen"] is None:
                pending_hu["chosen"] = "discard:" + str(tile)
                pending_hu = None
            hand_before = _tiles(hands[seat])
            discards[seat].append(tile)
            if seat is not None:
                discard_profile[seat].append({
                    "turn": len(discards[seat]) - 1,
                    "whites": hands[seat][WEALTH],
                    "chose_white": 1 if tile == WEALTH else 0,
                    "melds": melds[seat],
                    "hand_size": len(hand_before),
                })
            if seat is not None and len(hand_before) == 14 - 3 * melds[seat]:
                # 该窗口的来路：本人上一次**非被动**事件是摸牌还是鸣牌。
                # 必须忽略 pass/timeout（平台固定走满会插进大量响应窗事件），
                # 否则鸣牌后的弃牌会被误判成摸牌后。
                origin = "meld" if last_action[seat] in ("peng", "chi", "gang") else "draw"
                discard_windows.append({
                    "origin": origin,
                    "seat": seat,
                    "seq": event["seq"],
                    "turn": len(discards[seat]) - 1,
                    "hand_before": hand_before,
                    "meld_count": melds[seat],
                    "chosen": tile,
                    "whites_held": hands[seat][WEALTH],
                    "reach": reachability(hand_before, melds[seat], tile),
                })
            # 链状态用**弃牌前**的爆头态判定（chain_after_discard 的入参语义）。
            if baotou[seat] is None and tile == WEALTH:
                # 庄家第一手打白：其摸前 13 张不可唯一还原，链是否 +1 未知。
                # 只有这一种窗口会真正影响链重建（否则必然断链清零）。
                chain_unknown.append((event["seq"], seat))
            chain[seat], piao[seat] = chain_after_discard(
                chain[seat], piao[seat], bool(baotou[seat]), Tile(tile))
            hands[seat][tile] -= 1
            after = _tiles(hands[seat])
            baotou[seat] = baotou_after_discard(after, melds[seat])
            snapshot(seat, "after_discard", event["seq"], len(discards[seat]) - 1)
        elif kind == "peng":
            melds[seat] += 1
            meld_tiles[seat].append(tuple([tile] * 3))
            hands[seat][tile] -= 2
        elif kind == "chi":
            consumed = list(data["tiles"])
            consumed.remove(tile)  # 第三张来自他家弃牌，不在本人暗牌
            melds[seat] += 1
            meld_tiles[seat].append(tuple(sorted(consumed)))
            for own in consumed:
                hands[seat][own] -= 1
        elif kind == "gang":
            gang_kind = data.get("kind")
            consumed = {"ming": 3, "an": 4, "bu": 1}.get(gang_kind)
            if consumed is None:
                errors.append("未知杠类别 %r" % (gang_kind,))
            else:
                # 明杠/暗杠各自组成一副新面子（明杠第 4 张来自他家弃牌，暗杠
                # 四张全在暗牌）；补杠只是把已有碰升级为杠，**副露数不变**。
                if gang_kind == "bu":
                    for index, group in enumerate(meld_tiles[seat]):
                        if group and group[0] == tile and len(group) == 3:
                            meld_tiles[seat][index] = tuple([tile] * 4)
                            break
                    else:
                        errors.append("补杠找不到对应碰副露 %r" % (tile,))
                else:
                    melds[seat] += 1
                    extra = 1 if gang_kind == "ming" else 0
                    meld_tiles[seat].append(tuple([tile] * (consumed + extra)))
                hands[seat][tile] -= consumed
                chain[seat], piao[seat] = chain_after_gang(chain[seat], piao[seat])
        elif kind == "game_ended":
            pass
        else:
            errors.append("未知事件类型 %r" % (kind,))

        if kind in ("tile_drawn", "tile_discarded", "peng", "chi", "gang"):
            for owner in range(4):
                if any(value < 0 for value in hands[owner].values()):
                    errors.append("暗牌负计数 seq=%d seat=%d" % (event["seq"], owner))
                if melds[owner] > 4:
                    errors.append("副露数越界 seq=%d seat=%d 得到 %d" % (event["seq"], owner, melds[owner]))
            if seat is not None:
                last_action[seat] = kind
        previous_event = event

    return {
        "hands_end": [dict(hand) for hand in hands],
        "melds_end": list(melds),
        "meld_tiles": meld_tiles,
        "baotou_end": list(baotou),
        "waits": waits,
        "discards": discards,
        "draws": draws,
        "discard_windows": discard_windows,
        "discard_profile": discard_profile,
        "hu_windows": hu_windows,
        "chain_end": list(chain),
        "piao_end": list(piao),
        "chain_unknown": chain_unknown,
        "errors": errors,
    }


def round_facts(doc, round_no, events, start_hands):
    """一局的完整事实：重建 + 官方终局 + 每座派生量。"""

    recon = reconstruct_round(events, start_hands)
    ended = None
    for event in events:
        if event["type"] == "round_ended":
            ended = event
            break
    if ended is None:
        return {"round_no": round_no, "fatal": "缺 round_ended"}
    data = ended.get("data") or {}
    winner = ended.get("seat")
    winner = winner if type(winner) is int and 0 <= winner < 4 else None
    seats = [item.get("user_id") for item in doc.get("seats") or []]
    dealer = data.get("dealer")
    by_start = None
    for index, hand in enumerate(start_hands):
        if len(hand) == 14:
            by_start = index
    dealer_agree = (dealer == by_start) if type(dealer) is int and by_start is not None else None

    # 番值自检：用重建的手牌 + 链 + 爆头态，经 hangma 的 compute_fan 重算总番，
    # 与官方 round_ended.data.fan 对拍。这是对整条重建链（暗牌、副露、财神、
    # 爆头生命周期、动作链）的一次端到端校验。
    fan_check = {"status": "no_win"}
    if winner is not None:
        hand = _tiles(Counter(recon["hands_end"][winner]))
        split = hand_analysis.win_split(hand, recon["melds_end"][winner])
        if split is None:
            fan_check = {"status": "hand_not_win", "hand": [t.code for t in hand]}
        else:
            ch, pi = recon["chain_end"][winner], recon["piao_end"][winner]
            state = recon["baotou_end"][winner]
            try:
                recomputed = compute_fan(split, ch, pi, bool(state))
                detail_match = list(recomputed.details) == list(data.get("detail") or [])
                fan_check = {
                    "status": "ok" if recomputed.fan == data.get("fan") else "fan_mismatch",
                    "detail_match": detail_match,
                    "recomputed_fan": recomputed.fan,
                    "official_fan": data.get("fan"),
                    "recomputed_details": list(recomputed.details),
                    "official_details": list(data.get("detail") or []),
                    "branch": split.branch,
                    "chain": ch,
                    "piao": pi,
                    "baotou_known": state is not None,
                }
            except ValueError as exc:
                fan_check = {"status": "fan_error", "reason": str(exc), "chain": ch, "piao": pi}

    per_seat = []
    for seat in range(4):
        waits = recon["waits"][seat]
        entered = [index for index, item in enumerate(waits) if item["baotou"]]
        hand_end = _tiles(Counter(recon["hands_end"][seat]))
        won = winner == seat
        entry_turn = None
        if entered:
            entry_turn = waits[entered[0]]["turn"]
        # 胡牌家的成胡分解（hangma 的确定性证据），用于判「财神用作面子/将/浮牌」。
        split = None
        if won:
            split = hand_analysis.win_split(
                _tiles(Counter(recon["hands_end"][seat])), recon["melds_end"][seat])
        white_face = white_pair = white_float = None
        if split is not None:
            face = pair = 0
            for label in split.evidence:
                if ":" not in label:
                    continue
                kind, body = label.split(":", 1)
                used = body.count(WEALTH)
                if not used:
                    continue
                if kind == "将":
                    pair += used
                elif kind in ("顺子", "刻子"):
                    face += used
            white_face, white_pair = face, pair
            white_float = (recon["hands_end"][seat].get(WEALTH, 0) - face - pair)

        # 弃牌窗口的爆头可达性聚合（Q4）；明细只留「14 张本身已胡」的稀有窗口。
        mine_windows = [w for w in recon["discard_windows"] if w["seat"] == seat]
        win_hand = [w for w in mine_windows if w["reach"]["is_win"]]
        target = [w for w in win_hand if w["reach"]["n_targets"] > 0]
        chosen_ok = [w for w in target if w["reach"]["chosen_target"]]
        reach_summary = {
            "windows": len(mine_windows),
            "win_hand_windows": len(win_hand),
            "target_windows": len(target),
            "chosen_target_windows": len(chosen_ok),
            "missed_windows": len(target) - len(chosen_ok),
            "better_than_chosen_windows": sum(
                1 for w in win_hand if w["reach"]["better_than_chosen"] > 0),
        }
        reach_windows = [
            [w["seq"], w["turn"], w["reach"]["n_targets"],
             w["reach"]["chosen_target"], w["reach"]["better_than_chosen"],
             w["whites_held"], w["meld_count"], w["chosen"], w["origin"]]
            for w in win_hand
        ]
        # 按副露数分层的「窗口 → 已胡」转化率：用于区分「鸣牌更多」与
        # 「同样的鸣牌数下牌更差」两种解释。
        win_by_melds = Counter(w["meld_count"] for w in win_hand)
        target_by_melds = Counter(w["meld_count"] for w in target)
        windows_by_melds = Counter(w["meld_count"] for w in mine_windows)
        reach_summary["win_by_melds"] = {str(k): win_by_melds.get(k, 0) for k in range(5)}
        reach_summary["target_by_melds"] = {str(k): target_by_melds.get(k, 0) for k in range(5)}
        reach_summary["windows_by_melds"] = {str(k): windows_by_melds.get(k, 0) for k in range(5)}

        by_origin = Counter(w["origin"] for w in mine_windows)
        origin_win = Counter(w["origin"] for w in win_hand)
        origin_target = Counter(w["origin"] for w in target)
        reach_summary["windows_draw"] = by_origin.get("draw", 0)
        reach_summary["windows_meld"] = by_origin.get("meld", 0)
        reach_summary["win_hand_draw"] = origin_win.get("draw", 0)
        reach_summary["win_hand_meld"] = origin_win.get("meld", 0)
        reach_summary["target_draw"] = origin_target.get("draw", 0)
        reach_summary["target_meld"] = origin_target.get("meld", 0)

        per_seat.append({
            "seat": seat,
            "user_id": seats[seat] if seat < len(seats) else None,
            "is_me": (seat < len(seats) and seats[seat] == ME),
            "is_dealer": (dealer == seat),
            "entered_baotou": bool(entered),
            "entry_turn": entry_turn,
            "entry_seq": waits[entered[0]]["seq"] if entered else None,
            "entry_whites": waits[entered[0]]["whites"] if entered else None,
            "final_baotou": waits[-1]["baotou"] if waits else None,
            "wait_states": len(waits),
            "whites_drawn": recon["draws"][seat].count(WEALTH),
            "whites_discarded": recon["discards"][seat].count(WEALTH),
            "whites_end": recon["hands_end"][seat].get(WEALTH, 0),
            "hand_end": [tile.code for tile in hand_end],
            "melds_end": recon["melds_end"][seat],
            "meld_tiles": [list(item) for item in recon["meld_tiles"][seat]],
            "won": won,
            "draws_n": len(recon["draws"][seat]),
            "discards_n": len(recon["discards"][seat]),
            "first_tenpai_turn": next((item["turn"] for item in waits if item["shanten"] == 0), None),
            "first_std_tenpai_turn": next((item["turn"] for item in waits if item["standard_shanten"] == 0), None),
            "first_natural_tenpai_turn": next(
                (item["turn"] for item in waits
                 if item["whites"] == 0 and item["standard_shanten"] == 0), None),
            "win_branch": split.branch if split is not None else None,
            "win_evidence": list(split.evidence) if split is not None else None,
            "white_in_face": white_face,
            "white_in_pair": white_pair,
            "white_float": white_float,
            "discard_profile": recon["discard_profile"][seat],
            "hu_windows": [
                [w["seq"], w["turn"], w["melds"], w["whites"], w["baotou_after_draw"],
                 len(w["targets"]), w["chosen"], ",".join(w["targets"])]
                for w in recon["hu_windows"] if w["seat"] == seat
            ],
            "reach_summary": reach_summary,
            "reach_windows": reach_windows,
            "waits": waits,
        })

    return {
        "round_no": round_no,
        "winner_seat": winner,
        "is_draw": bool(data.get("draw")),
        "fan": data.get("fan"),
        "detail": data.get("detail"),
        "scores": data.get("scores"),
        "dealer": dealer,
        "dealer_by_start_hands": by_start,
        "dealer_agree": dealer_agree,
        "per_seat": per_seat,
        "discard_windows": recon["discard_windows"],
        "hand_reconstruction_errors": recon["errors"],
        "fan_check": fan_check,
        "chain_unknown": recon["chain_unknown"],
    }
