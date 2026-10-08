#!/usr/bin/env python3
"""C27 第一步：把「鸣牌使用率差」定位到具体条件格（逐格对照 + 分解 + 听牌族去向）。

口径、格族、判定格选取规则与阈值见同目录 C27-PREREG-CLAIM-CELLS.md（该文件在本脚本
运行之前落盘，运行中不改口径）。

纪律：
* 复用 C23 的窗口模型与规则入口（C23.window_members / C23._tiles / C23.load_board），
  本脚本不实现任何吃碰杠合法性、向听、听牌或爆头规则，全部经 hangma；
* 鸣后状态按父代 CandidateFacts 的同一选键 (向听, -有效牌剩余张数和, 规范牌序下标)
  取最佳后续弃牌；有效牌剩余张数与 candidate_facts._remaining 同一式子；
* 信息权限：只读官方牌谱 events.json（四家 start_hands + 公开事件流）与公开周榜快照；
  脚本末尾对读取路径做断言。赛后观察性研究，不主张线上可达性。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c27_claim_cells.py
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
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(HERE))

import anatomy_lib as AL  # noqa: E402
import c23_claim_opportunity as C23  # noqa: E402
import stats_lib as SL  # noqa: E402

from hangma_bot.hangma import action_families, hand_analysis, progression  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_ORDER, WindowContext  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.kernel.observation import PublicDiscard  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c27-claim-cells")
ROUNDS_JSONL = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')

ME = AL.ME
WEALTH = AL.WEALTH
WALL_TOTAL = 136
TILE_INDEX = {code: index for index, code in enumerate(TILE_ORDER)}

READ_PATHS = []
"""本脚本实际读取的文件路径（泄漏检查用）。"""

KNOWN = {
    "chances_me": 5965, "chances_elite": 10394,
    "usage_me": 0.4801, "usage_elite": 0.5790, "usage_other": 0.5259,
    "opp_a_me": 2.1304, "opp_a_elite": 2.0623,
    "sh0_me": [1607, 202], "sh0_elite": [2906, 934],
}
"""C23 已发布读数（自检对拍目标，见 PREREG 第三节第 8 条）。"""

GROUPS = ("me", "elite", "other")
NL = chr(10)


# ---------------------------------------------------------------------------
# 有效牌宽度口径（与 candidate_facts._remaining 同一式子）
# ---------------------------------------------------------------------------


class Width:
    """有效牌剩余张数估计器：一次状态分析的 (向听, 张数, 种数)。"""

    __slots__ = ("public", "negative", "calls")

    def __init__(self, public_counts):
        self.public = public_counts
        self.negative = 0
        self.calls = 0

    def remaining(self, code, hand_counts, newly_hidden):
        value = (4 - hand_counts.get(code, 0) - self.public.get(code, 0)
                 - newly_hidden.get(code, 0))
        if value < 0:
            self.negative += 1
            value = 0
        return value

    def state(self, hand_tiles, melds, newly_hidden):
        """(向听, 有效牌剩余张数和, 有效牌种数)。"""

        self.calls += 1
        summary = hand_analysis.analyse_hand(hand_tiles, melds)
        counts = collections.Counter(tile.code for tile in hand_tiles)
        support = 0
        for useful in summary.useful_tiles:
            support += self.remaining(useful.code, counts, newly_hidden)
        return summary.shanten, support, len(summary.useful_tiles)


def _tiles_of(counter):
    """计数 → 规范牌序的 Tile 元组（复用 C23._tiles）。"""

    return C23._tiles(counter)


def _claim_after(width, hand_counter, melds, removal):
    """吃/碰后按父代同键取最佳后续弃牌，返回 (key, 弃牌码, 向听, 张数, 种数)。"""

    counts = collections.Counter(hand_counter)
    for code, amount in removal.items():
        counts[code] -= amount
    codes = sorted({code for code, amount in counts.items() if amount > 0},
                   key=TILE_INDEX.get)
    best = None
    for code in codes:
        after = collections.Counter(counts)
        after[code] -= 1
        newly = dict(removal)
        newly[code] = newly.get(code, 0) + 1
        shanten, support, kinds = width.state(_tiles_of(after), melds + 1, newly)
        key = (shanten, -support, TILE_INDEX[code])
        if best is None or key < best[0]:
            best = (key, code, shanten, support, kinds)
    return best


def _gang_after(width, hand_counter, melds, code):
    """明杠：补牌前余牌口径（父代 replacement_draw_unknown=True 同口径）。"""

    counts = collections.Counter(hand_counter)
    counts[code] -= 3
    shanten, support, kinds = width.state(_tiles_of(counts), melds + 1, {code: 3})
    return shanten, support, kinds


def _removal_of(kind, action, tile):
    """鸣牌从暗牌移出的牌计数（与 candidate_facts._claim_removal 同口径）。"""

    if kind == "peng":
        return {tile: 2}
    if kind == "chi":
        partners = [item.code for item in action.tiles if item.code != tile]
        removal = {}
        for code in partners:
            removal[code] = removal.get(code, 0) + 1
        return removal
    return {}


def _families(hand_counter, seat, discarder, tile, seq, chi_count, peng_codes,
              restricted, in_peng, in_chi, wall_remaining):
    """本座在该弃牌上的合法鸣牌候选（全部由 hangma.action_families 产出）。

    窗口成员之外的族一律不调用（与 C23.claim_shapes 同口径）：碰/明杠只在碰窗口内、
    吃只在吃窗口内生成。
    """

    hand_tiles = _tiles_of(hand_counter)
    common = dict(
        seat=seat, turn_seat=discarder, hand_tiles=hand_tiles, drawn_tile=None,
        my_chi_count=chi_count, my_peng_codes=tuple(peng_codes),
        last_discard=PublicDiscard(seat=discarder, tile=Tile(tile), seq=seq),
        catch_play=restricted, remaining_tile_count=wall_remaining,
    )
    peng_c = chi_c = gang_c = ()
    if in_peng:
        peng_ctx = WindowContext(phase="response_peng", responding_seats=(seat,),
                                 **common)
        peng_c = tuple(action_families.peng_candidates(peng_ctx).candidates)
        gang_c = tuple(action_families.gang_candidates(peng_ctx).candidates)
    if in_chi:
        chi_ctx = WindowContext(phase="response_chi", responding_seats=(seat,),
                                **common)
        chi_c = tuple(action_families.chi_candidates(chi_ctx).candidates)
    return peng_c, chi_c, gang_c


# ---------------------------------------------------------------------------
# 条件格定义（唯一一份；官方重建侧与审计侧共用同一份 key）
# ---------------------------------------------------------------------------


def cells(feature):
    """9 个特征 → 15 个登记格（F1–F9 单格 + G1–G5 组合格），见 PREREG 第四节。"""

    sh = feature["sh"]
    sh_label = ("sh0" if sh == 0 else "sh1" if sh == 1 else
                "sh2" if sh == 2 else "sh3p")
    labels = {
        "F1": sh_label,
        "F2": feature["fam"],
        "F3": feature["dsh"],
        "F4": feature["dw"],
        "F5": feature["ml"],
        "F6": feature["tn"],
        "F7": feature["wl"],
        "F8": feature["tc"],
        "F9": feature["bt"],
    }
    labels["G1"] = sh_label + "|" + labels["F2"]
    labels["G2"] = sh_label + "|" + labels["F3"]
    labels["G3"] = sh_label + "|" + labels["F4"]
    labels["G4"] = labels["F2"] + "|" + labels["F3"]
    labels["G5"] = sh_label + "|" + labels["F5"]
    return {family: family + ":" + label for family, label in labels.items()}


def feature_of_record(record):
    """官方重建记录 → 特征字典（键与审计侧逐字相同）。"""

    delta_sh = record["sa"] - record["sb"]
    delta_w = record["wa"] - record["wb"]
    melds = record["ml"]
    turn = record["tn"]
    wall = record["wl"]
    return {
        "sh": record["sb"],
        "fam": record["fam"],
        "dsh": "down" if delta_sh < 0 else ("same" if delta_sh == 0 else "up"),
        "dw": "wider" if delta_w > 0 else ("equal" if delta_w == 0 else "narrower"),
        "ml": "m0" if melds == 0 else ("m1" if melds == 1 else "m2p"),
        "tn": "t0_2" if turn <= 2 else ("t3_6" if turn <= 6 else "t7p"),
        "wl": "w60p" if wall >= 60 else ("w40_59" if wall >= 40 else "wlt40"),
        "tc": record["tc"],
        "bt": "yes" if record["bb"] is True else "no",
    }


# ---------------------------------------------------------------------------
# 单局扫描
# ---------------------------------------------------------------------------


def scan_round_cells(events, start_hands, game_id, round_no):
    """重建一局并记录每个鸣牌机会的条件格特征。

    返回 (summary, records, audit)；summary 的计数键与 C23.scan_round 同名，
    供自检对拍（本脚本的机会定义与 C23 完全一致：hit = 合法碰 或 合法吃）。
    """

    hands = [collections.Counter(hand) for hand in start_hands]
    melds = [0, 0, 0, 0]
    chi_counts = [0, 0, 0, 0]
    peng_codes = [list() for _ in range(4)]
    meld_tiles = [list() for _ in range(4)]
    rivers = [list() for _ in range(4)]
    catch = [False, False, False, False]
    baotou = []
    for hand in start_hands:
        if len(hand) == 14:
            baotou.append(None)
        else:
            try:
                baotou.append(progression.baotou_after_discard(
                    _tiles_of(collections.Counter(hand)), 0))
            except Exception:  # noqa: BLE001
                baotou.append(None)

    claims = [0, 0, 0, 0]
    peng_claims = [0, 0, 0, 0]
    chi_claims = [0, 0, 0, 0]
    minggang_claims = [0, 0, 0, 0]
    discards_n = [0, 0, 0, 0]
    opp_a = [0, 0, 0, 0]
    opp_a_peng = [0, 0, 0, 0]
    opp_a_chi = [0, 0, 0, 0]
    opp_a_gang = [0, 0, 0, 0]
    base_a = [0, 0, 0, 0]
    opp_by_shanten = [collections.Counter() for _ in range(4)]
    taken_by_shanten = [collections.Counter() for _ in range(4)]
    walk_taken_by_shanten = [collections.Counter() for _ in range(4)]

    records = []
    audit = collections.Counter()

    def walk(index):
        """C23 的窗口终止事件走法（逐字复制，只用于对拍 C23 的已发布读数）。

        注意它会把 `timeout(kind=discard)` 当成窗口终止事件，从而漏掉其后发生的
        鸣牌；本脚本主口径改用下面的「响应段归属」，两者都算、只对拍不回写。
        """

        seen = []
        while index < len(events):
            item = events[index]
            if item["type"] not in ("pass", "timeout"):
                return seen, item
            inner = item.get("data") or {}
            if item["type"] == "timeout" and inner.get("kind") not in (None, "response"):
                return seen, item
            seen.append(item)
            index += 1
        return seen, None

    # 响应段归属：一张弃牌到下一张弃牌之间出现的**响应型**鸣牌（碰/吃/明杠）就是
    # 该弃牌窗口被用掉的证据。暗杠/补杠是本人摸牌回合的动作，不算响应型。
    total_events = len(events)
    first_discard_from = [None] * (total_events + 1)
    first_claim_from = [None] * (total_events + 1)
    cursor_discard = None
    cursor_claim = None
    for index in range(total_events - 1, -1, -1):
        item = events[index]
        if item["type"] == "tile_discarded":
            cursor_discard = index
        elif item["type"] in ("peng", "chi"):
            cursor_claim = index
        elif item["type"] == "gang" and (item.get("data") or {}).get("kind") == "ming":
            cursor_claim = index
        first_discard_from[index] = cursor_discard
        first_claim_from[index] = cursor_claim

    def public_counts():
        counts = collections.Counter()
        for river in rivers:
            counts.update(river)
        for groups in meld_tiles:
            for group in groups:
                counts.update(group)
        return counts

    for position, event in enumerate(events):
        kind = event["type"]
        seat = event.get("seat")
        tile = event.get("tile")
        data = event.get("data") or {}

        if kind in ("round_ended", "game_ended"):
            break
        if kind == "tile_drawn":
            before = _tiles_of(hands[seat])
            hands[seat][tile] += 1
            try:
                baotou[seat] = progression.baotou_after_draw(
                    bool(baotou[seat]), before, melds[seat], Tile(tile))
            except ValueError:
                baotou[seat] = None
                audit["baotou_draw_unknown"] += 1
            continue
        if kind in ("pass", "timeout"):
            continue
        if kind == "peng":
            melds[seat] += 1
            peng_codes[seat].append(tile)
            meld_tiles[seat].append(tuple([tile] * 3))
            hands[seat][tile] -= 2
            claims[seat] += 1
            peng_claims[seat] += 1
            continue
        if kind == "chi":
            consumed = list(data["tiles"])
            consumed.remove(tile)
            melds[seat] += 1
            chi_counts[seat] += 1
            meld_tiles[seat].append(tuple(sorted(consumed)))
            for own in consumed:
                hands[seat][own] -= 1
            claims[seat] += 1
            chi_claims[seat] += 1
            continue
        if kind == "gang":
            gang_kind = data.get("kind")
            consumed = {"ming": 3, "an": 4, "bu": 1}[gang_kind]
            if gang_kind == "bu":
                for index, group in enumerate(meld_tiles[seat]):
                    if group and group[0] == tile and len(group) == 3:
                        meld_tiles[seat][index] = tuple([tile] * 4)
                        break
            else:
                melds[seat] += 1
                extra = 1 if gang_kind == "ming" else 0
                meld_tiles[seat].append(tuple([tile] * (consumed + extra)))
                if gang_kind == "ming":
                    claims[seat] += 1
                    minggang_claims[seat] += 1
            hands[seat][tile] -= consumed
            baotou[seat] = None
            continue
        if kind != "tile_discarded":
            continue

        # ---- 弃牌（与 C23 同序：先应用弃牌，再定窗口）----
        hands[seat][tile] -= 1
        rivers[seat].append(tile)
        discards_n[seat] += 1
        if tile == WEALTH:
            catch = [False, False, False, False]
            catch[seat] = True
        else:
            catch[seat] = False
        owners = [index for index in range(4) if catch[index]]
        owner = owners[0] if owners else None
        try:
            baotou[seat] = progression.baotou_after_discard(
                _tiles_of(hands[seat]), melds[seat])
        except Exception:  # noqa: BLE001
            baotou[seat] = None
            audit["baotou_discard_failed"] += 1

        peng_members, chi_members = C23.window_members(seat, tile, owner)
        known = sum(sum(hands[i].values()) for i in range(4))
        known += sum(len(river) for river in rivers)
        known += sum(len(group) for groups in meld_tiles for group in groups)
        wall_remaining = WALL_TOTAL - known
        public = public_counts()
        width = Width(public)

        # —— 主口径：响应段归属 ——
        segment_end = first_discard_from[position + 1]
        claim_index = first_claim_from[position + 1]
        claimed_seat = None
        claimed_kind = None
        terminator = None
        if claim_index is not None and (segment_end is None or claim_index < segment_end):
            terminator = events[claim_index]
            claimed_seat = terminator["seat"]
            claimed_kind = terminator["type"]
        # —— 对拍口径：C23 的终止事件走法（只用于复现其已发布读数）——
        _observed, walk_terminator = walk(position + 1)
        walk_seat = None
        if walk_terminator is not None and walk_terminator["type"] in ("peng", "chi",
                                                                       "gang"):
            walk_seat = walk_terminator["seat"]
        if claimed_seat is not None and claimed_seat != walk_seat:
            audit["claim_attribution_differs_from_walk"] += 1

        for responder in range(4):
            if responder == seat:
                continue
            in_peng = responder in peng_members
            in_chi = responder in chi_members
            if not in_peng and not in_chi:
                continue
            restricted = owner is not None and responder != owner
            peng_c, chi_c, gang_c = _families(
                hands[responder], responder, seat, tile, event["seq"],
                chi_counts[responder], peng_codes[responder], restricted,
                in_peng, in_chi, wall_remaining,
            )
            if tile != WEALTH:
                base_a[responder] += 1
            if in_peng and peng_c:
                opp_a_peng[responder] += 1
            if in_peng and gang_c:
                opp_a_gang[responder] += 1
            if in_chi and chi_c:
                opp_a_chi[responder] += 1
            if not (peng_c or chi_c):
                continue

            opp_a[responder] += 1
            before_shanten, before_support, before_kinds = width.state(
                _tiles_of(hands[responder]), melds[responder], {})
            bucket = min(3, before_shanten)
            opp_by_shanten[responder][bucket] += 1
            mine = claimed_seat == responder and claimed_kind in ("peng", "chi", "gang")
            if mine:
                taken_by_shanten[responder][bucket] += 1
            if walk_seat == responder:
                walk_taken_by_shanten[responder][bucket] += 1

            best = None
            for family, candidates in (("peng", peng_c), ("chi", chi_c)):
                for candidate in candidates:
                    removal = _removal_of(family, candidate.action, tile)
                    outcome = _claim_after(width, hands[responder],
                                           melds[responder], removal)
                    if outcome is None:
                        continue
                    if best is None or outcome[0] < best[0]:
                        best = (outcome[0], outcome[1], outcome[2], outcome[3],
                                outcome[4], family)
            if best is None:
                audit["opportunity_without_after"] += 1
                continue

            record = {
                "g": game_id, "r": round_no, "s": responder,
                "seq": event["seq"], "tile": tile,
                "fam": "peng" if peng_c else "chi",
                "has_peng": bool(peng_c), "has_chi": bool(chi_c),
                "has_gang": bool(gang_c),
                "sb": before_shanten, "wb": before_support, "kb": before_kinds,
                "sa": best[2], "wa": best[3], "ka": best[4],
                "after_family": best[5], "followup": best[1],
                "bb": baotou[responder],
                "ml": melds[responder], "tn": discards_n[responder] - 1,
                "wl": wall_remaining,
                "tc": "number" if tile[0] in "123456789" else "honor",
                "claimed": bool(mine),
                "ckind": claimed_kind if claimed_seat == responder else None,
            }
            if claimed_seat == responder and claimed_kind == "gang":
                record["a_sa"], record["a_wa"], record["a_ka"] = _gang_after(
                    width, hands[responder], melds[responder], tile)
            elif claimed_seat == responder and claimed_kind in ("peng", "chi"):
                removal = None
                if claimed_kind == "peng":
                    removal = {tile: 2}
                else:
                    consumed = list((terminator.get("data") or {}).get("tiles") or [])
                    if tile in consumed:
                        consumed.remove(tile)
                    removal = {}
                    for code in consumed:
                        removal[code] = removal.get(code, 0) + 1
                actual = _claim_after(width, hands[responder], melds[responder], removal)
                if actual is not None:
                    record["a_sa"] = actual[2]
                    record["a_wa"] = actual[3]
                    record["a_ka"] = actual[4]
            records.append(record)

    summary = {
        "melds_end": list(melds),
        "claims": claims, "peng_claims": peng_claims, "chi_claims": chi_claims,
        "minggang_claims": minggang_claims,
        "opp_a": opp_a, "opp_a_peng": opp_a_peng, "opp_a_chi": opp_a_chi,
        "opp_a_gang": opp_a_gang, "base_a": base_a,
        "opp_by_shanten": [{str(level): opp_by_shanten[seat].get(level, 0)
                            for level in range(4)} for seat in range(4)],
        "taken_by_shanten": [{str(level): taken_by_shanten[seat].get(level, 0)
                              for level in range(4)} for seat in range(4)],
        "walk_taken_by_shanten": [{str(level): walk_taken_by_shanten[seat].get(level, 0)
                                   for level in range(4)} for seat in range(4)],
    }
    return summary, records, dict(audit)


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class CellStats:
    """一个 (族, 格) 上的两组机会数 / 用掉数与房级配对差。"""

    def __init__(self):
        self.chances = {group: 0 for group in GROUPS}
        self.taken = {group: 0 for group in GROUPS}
        self.room_chances = collections.defaultdict(collections.Counter)
        self.room_taken = collections.defaultdict(collections.Counter)

    def add(self, group, room, claimed):
        self.chances[group] += 1
        self.taken[group] += claimed
        self.room_chances[room][group] += 1
        self.room_taken[room][group] += claimed

    def usage(self, group):
        chances = self.chances[group]
        return (self.taken[group] / chances) if chances else None

    def room_paired(self):
        values, keys = [], []
        for room in sorted(self.room_chances):
            me_c = self.room_chances[room]["me"]
            el_c = self.room_chances[room]["elite"]
            if not me_c or not el_c:
                continue
            values.append(self.room_taken[room]["me"] / me_c
                          - self.room_taken[room]["elite"] / el_c)
            keys.append(room)
        return values, keys


def build_rows(records_by_round):
    """把 (组, 房, 是否主语料) 贴到每条机会记录上，并算出格标签。"""

    rows = []
    for (group, room, primary), records in records_by_round:
        for record in records:
            feature = feature_of_record(record)
            rows.append({
                "group": group, "room": room, "primary": primary,
                "claimed": 1 if record["claimed"] else 0,
                "feature": feature, "labels": cells(feature), "record": record,
            })
    return rows


def decompose(rows, family_filter=None):
    """按登记格做 Kitagawa 精确分解（Σ contrib = 池化总差）。

    方向：我方 − 强手（负 = 我方更低 = 缺口）。
    """

    chances_me = sum(1 for row in rows if row["group"] == "me")
    chances_elite = sum(1 for row in rows if row["group"] == "elite")
    taken_me = sum(row["claimed"] for row in rows if row["group"] == "me")
    taken_elite = sum(row["claimed"] for row in rows if row["group"] == "elite")
    u_me = taken_me / chances_me
    u_elite = taken_elite / chances_elite
    total_gap = u_me - u_elite

    cells_seen = set()
    for row in rows:
        cells_seen.update(row["labels"].values())
    stats = {key: CellStats() for key in cells_seen}
    for row in rows:
        if row["group"] not in ("me", "elite"):
            continue
        for key in row["labels"].values():
            stats[key].add(row["group"], row["room"], row["claimed"])

    entries = []
    for key, cell in stats.items():
        if family_filter is not None and not key.startswith(family_filter + ":"):
            continue
        c_me, c_el = cell.chances["me"], cell.chances["elite"]
        u_c_me, u_c_el = cell.usage("me"), cell.usage("elite")
        if not c_me + c_el or u_c_me is None or u_c_el is None:
            continue
        p_me = c_me / chances_me
        p_el = c_el / chances_elite
        p_bar = (p_me + p_el) / 2
        u_bar = (u_c_me + u_c_el) / 2
        rate = p_bar * (u_c_me - u_c_el)
        comp = u_bar * (p_me - p_el)
        simple = ((c_me + c_el) / (chances_me + chances_elite)) * (u_c_me - u_c_el)
        values, keys = cell.room_paired()
        ci = SL.cluster_ci(values, keys)
        entries.append({
            "cell": key, "chances": c_me + c_el, "chances_me": c_me,
            "chances_elite": c_el, "taken_me": cell.taken["me"],
            "taken_elite": cell.taken["elite"],
            "u_me": u_c_me, "u_elite": u_c_el, "d_u": u_c_me - u_c_el,
            "p_me": p_me, "p_el": p_el,
            "share": (c_me + c_el) / (chances_me + chances_elite),
            "rate_part": rate, "composition_part": comp,
            "contribution": rate + comp, "simple": simple,
            "ci": ci, "rooms_defined": len(values),
        })
    entries.sort(key=lambda item: item["contribution"])
    return {
        "u_me": u_me, "u_elite": u_elite, "total_gap": total_gap,
        "chances_me": chances_me, "chances_elite": chances_elite,
        "taken_me": taken_me, "taken_elite": taken_elite,
        "cells": entries,
    }


def fmt(value, digits=4):
    return "n/a" if value is None else ("%.*f" % (digits, value))


def fmt_signed(value, digits=4):
    return "n/a" if value is None else ("%+.*f" % (digits, value))


def render_cell_table(entries, title, lines, top=None, min_chances=1):
    lines.append("#### " + title)
    lines.append("")
    lines.append("| 格 | 机会数 | 我方机会占比 | 强手机会占比 | 我方使用率 | 强手使用率 | 差(我−强) | 房级CR0 95%CI | 贡献(精确式) | 贡献(简单式) | 占缺口 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in entries:
        if entry["chances"] < min_chances:
            continue
        ci = entry["ci"]
        ci_text = ("[%s, %s]" % (fmt_signed(ci["lo"]), fmt_signed(ci["hi"]))
                   if ci["lo"] is not None else "n/a")
        lines.append("| %s | %d | %.4f | %.4f | %.4f | %.4f | %s | %s | %s | %s | %s |"
                     % (entry["cell"], entry["chances"], entry["p_me"], entry["p_el"],
                        entry["u_me"], entry["u_elite"], fmt_signed(entry["d_u"]),
                        ci_text, fmt_signed(entry["contribution"]),
                        fmt_signed(entry["simple"]),
                        "n/a" if not entry["contribution"] else
                        "%.1f%%" % (100 * entry["contribution"] / TOTAL_GAP_HOLDER[0])))
        if top is not None and len([1 for _ in ()]) >= top:
            break
    lines.append("")


TOTAL_GAP_HOLDER = [0.0]
"""池化总差（我方 − 强手）；在 main 里填。渲染时用于「占缺口」列。"""


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    board, board_path = C23.load_board()
    READ_PATHS.append(board_path)
    print("榜单快照 %s：top+prev 标签 %d 人" % (Path(board_path).name, len(board)))

    primary_rows = [json.loads(line) for line in ROUNDS_JSONL.open(encoding="utf-8")
                    if line.strip()]
    READ_PATHS.append(str(ROUNDS_JSONL))
    primary_index = {(row["game_id"], row["round_no"]) for row in primary_rows}
    print("主语料 rounds.jsonl：%d 局" % len(primary_rows))

    games = AL.load_games()
    READ_PATHS.extend(game["path"] for game in games)
    print("官方牌谱去重后 %d 场" % len(games))
    limit = int(os.environ.get("C27_GAME_LIMIT", "0") or 0)
    if limit:
        games = games[:limit]
        print("C27_GAME_LIMIT=%d：只跑前 %d 场（冒烟用，不得用于结论）" % (limit, limit))

    per_round = []
    audit = collections.Counter()
    rounds = 0
    for game in games:
        document = game["doc"]
        seats_meta = document.get("seats") or []
        room = document.get("room_id") or game["session"]
        users = [item.get("user_id") for item in seats_meta]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            summary, records, round_audit = scan_round_cells(
                events, start_hands, game["game_id"], round_no)
            audit.update(round_audit)
            groups = []
            for seat in range(4):
                user = users[seat] if seat < len(users) else None
                if user == ME:
                    groups.append("me")
                elif user in board:
                    groups.append("elite")
                else:
                    groups.append("other")
            if "elite" not in groups:
                continue
            rounds += 1
            primary = (game["game_id"], round_no) in primary_index
            per_round.append({
                "room": room, "primary": primary, "groups": groups,
                "records": records, "summary": summary,
            })

    print("重建 %d 局（含强手），用时 %.1f 秒" % (rounds, time.time() - started))

    def rows_of(only_primary):
        rows = []
        for item in per_round:
            if only_primary and not item["primary"]:
                continue
            for record in item["records"]:
                feature = feature_of_record(record)
                rows.append({
                    "group": item["groups"][record["s"]], "room": item["room"],
                    "primary": item["primary"],
                    "claimed": 1 if record["claimed"] else 0,
                    "feature": feature, "labels": cells(feature), "record": record,
                })
        return rows

    primary_rows_list = rows_of(True)
    all_rows = rows_of(False)

    # ---- 自检：与 C23 已发布读数对拍 ----
    def pooled(rows, group):
        chances = sum(1 for row in rows if row["group"] == group)
        taken = sum(row["claimed"] for row in rows if row["group"] == group)
        return chances, taken

    checks = []
    for group, key in (("me", "chances_me"), ("elite", "chances_elite")):
        chances, _ = pooled(primary_rows_list, group)
        checks.append(("机会数 %s = %d（C23 %d）" % (group, chances, KNOWN[key]),
                       abs(chances - KNOWN[key]) <= 2))
    for group, key in (("me", "usage_me"), ("elite", "usage_elite"),
                       ("other", "usage_other")):
        # C23 的 usage_A 分子 = 该座该局**全部**鸣牌次数（碰+吃+明杠），不是
        # 只算归因到窗口的那些；这里按同一分子口径复现其已发布读数。
        chances = sum(1 for row in primary_rows_list if row["group"] == group)
        claims_by_group = 0
        for item in per_round:
            if not item["primary"]:
                continue
            for index in range(4):
                if item["groups"][index] == group:
                    claims_by_group += item["summary"]["claims"][index]
        usage = claims_by_group / chances
        checks.append(("使用率A(C23分子口径) %s = %.4f（C23 %.4f）"
                       % (group, usage, KNOWN[key]),
                       abs(usage - KNOWN[key]) <= 5e-4))
    for group, key in (("me", "opp_a_me"), ("elite", "opp_a_elite")):
        # 与 C23 的 marginal mean 同口径：全部座-局机会数之和 / 座-局数
        values = []
        for item in per_round:
            if not item["primary"]:
                continue
            for index in range(4):
                if item["groups"][index] == group:
                    values.append(item["summary"]["opp_a"][index])
        mean = statistics.fmean(values)
        checks.append(("机会数A/局 %s = %.4f（C23 %.4f）" % (group, mean, KNOWN[key]),
                       abs(mean - KNOWN[key]) <= 5e-4))
    for group, key in (("me", "sh0_me"), ("elite", "sh0_elite")):
        chances = taken = 0
        for item in per_round:
            if not item["primary"]:
                continue
            for index in range(4):
                if item["groups"][index] != group:
                    continue
                chances += item["summary"]["opp_by_shanten"][index]["0"]
                taken += item["summary"]["walk_taken_by_shanten"][index]["0"]
        want = KNOWN[key]
        checks.append(("听牌格 %s = %d 机会 %d 用掉（C23 %d/%d）"
                       % (group, chances, taken, want[0], want[1]),
                       abs(chances - want[0]) <= 2 and abs(taken - want[1]) <= 2))

    print()
    print("== 自检（与 C23 已发布读数对拍，主语料含强手的局）")
    ok = True
    for text, passed in checks:
        ok = ok and passed
        print("  %s %s" % ("通过" if passed else "**不符**", text))
    print("自检总体：%s" % ("通过" if ok else "**失败**"))
    if not ok and not os.environ.get("C27_SKIP_SELFCHECK"):
        print("自检未通过：按 PREREG 第三节第 8 条停止分析。")
        return 1

    data = decompose(primary_rows_list)
    TOTAL_GAP_HOLDER[0] = data["total_gap"]
    print()
    print("== 池化总差（我方 − 强手）：u_me = %.4f（%d/%d），u_elite = %.4f（%d/%d），"
          "总差 = %+.4f"
          % (data["u_me"], data["taken_me"], data["chances_me"], data["u_elite"],
             data["taken_elite"], data["chances_elite"], data["total_gap"]))

    families = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
                "G1", "G2", "G3", "G4", "G5"]
    by_family = {}
    for family in families:
        subset = [entry for entry in data["cells"]
                  if entry["cell"].startswith(family + ":")]
        total = sum(entry["contribution"] for entry in subset)
        by_family[family] = {"cells": subset, "sum": total,
                             "residual": total - data["total_gap"]}

    lines = ["# C27 第一步：鸣牌使用率的条件格对照（脚本输出，非最终报告）", ""]
    for family in families:
        subset = by_family[family]["cells"]
        if not subset:
            continue
        render_cell_table(subset, "%s（%d 格；Σ贡献 = %s，残差 %s）"
                          % (family, len(subset),
                             fmt_signed(by_family[family]["sum"]),
                             fmt_signed(by_family[family]["residual"])), lines)
    (_project_file(_PROJECT_ROOT, OUT / "cell-tables.md")).write_text(NL.join(lines), encoding="utf-8")
    print("逐格表写入 %s" % (_project_file(_PROJECT_ROOT, OUT / "cell-tables.md")))

    # ---- 判定格：登记格池里贡献最小者（我方不利方向最大），至少 200 机会 ----
    pool = []
    for entry in data["cells"]:
        if entry["chances"] >= 200:
            pool.append(entry)
    pool.sort(key=lambda item: (item["contribution"], -item["chances"], item["cell"]))
    located = pool[0] if pool else None
    print()
    print("== 判定格（argmin 贡献，机会数 >= 200）：%s 贡献 %s（占缺口 %.1f%%），机会 %d"
          % (located["cell"] if located else "无",
             fmt_signed(located["contribution"]) if located else "n/a",
             100 * located["contribution"] / data["total_gap"] if located else 0.0,
             located["chances"] if located else 0))
    # 追加规则（预登记缺失的补丁，见结果文档「预登记偏离」一节）：
    # 字面 argmin 会被**近全集格**（如 F9:no 占 99.2% 机会）捕获——那不是条件格，
    # 是全集。因此另给一个机械的「非退化定位」：机会占比 < 90% 且 >= 200 机会的
    # argmin。两条读数都报，判定用后者。
    refined_pool = [entry for entry in data["cells"]
                    if entry["chances"] >= 200 and entry["share"] < 0.90]
    refined_pool.sort(key=lambda item: (item["contribution"], -item["chances"],
                                        item["cell"]))
    located_refined = refined_pool[0] if refined_pool else None
    print("非退化判定格（机会占比 < 90%% 的 argmin）：%s 贡献 %s（占缺口 %.1f%%），"
          "机会 %d（占比 %.1f%%）"
          % (located_refined["cell"] if located_refined else "无",
             fmt_signed(located_refined["contribution"]) if located_refined else "n/a",
             100 * located_refined["contribution"] / data["total_gap"]
             if located_refined else 0.0,
             located_refined["chances"] if located_refined else 0,
             100 * located_refined["share"] if located_refined else 0.0))
    top = sorted(data["cells"], key=lambda item: item["contribution"])[:10]
    print("贡献最大的 10 格：")
    for entry in top:
        print("  %-22s 机会 %6d  u_me %.4f  u_el %.4f  差 %s  贡献 %s（占缺口 %5.1f%%）"
              % (entry["cell"], entry["chances"], entry["u_me"], entry["u_elite"],
                 fmt_signed(entry["d_u"]), fmt_signed(entry["contribution"]),
                 100 * entry["contribution"] / data["total_gap"]))

    # ---- 每个分区内累计到 80% ----
    # 只有**同一分区**的格才互斥、贡献才相加等于总差；跨分区相加没有意义
    # （格互相重叠），所以累计逐分区算。
    cumulative_by_family = {}
    print()
    print("== 各分区内累计到 80% 缺口的格（分区内贡献相加 = 总差）")
    for family in families:
        subset = sorted(by_family[family]["cells"],
                        key=lambda item: item["contribution"])
        cumulative = 0.0
        chain = []
        for entry in subset:
            cumulative += entry["contribution"]
            chain.append({"cell": entry["cell"],
                          "contribution": entry["contribution"],
                          "cumulative": cumulative,
                          "cumulative_pct": 100 * cumulative / data["total_gap"]})
            if cumulative <= 0.8 * data["total_gap"]:
                pass
        cumulative_by_family[family] = {
            "sum": by_family[family]["sum"],
            "residual": by_family[family]["residual"],
            "chain": chain,
        }
        reached = None
        for item in chain:
            if item["cumulative"] <= 0.8 * data["total_gap"]:
                reached = item
        text = "；".join("%s %s(累计%5.1f%%)"
                         % (item["cell"], fmt_signed(item["contribution"]),
                            item["cumulative_pct"])
                         for item in chain[:4])
        print("  %s：%s%s" % (family, text, "" if reached is None else ""))

    # ---- 听牌族的鸣后去向 ----
    tenpai = {}
    for group in ("me", "elite", "other"):
        subset = [row for row in primary_rows_list
                  if row["group"] == group and row["record"]["sb"] == 0]
        taken = [row for row in subset if row["record"]["claimed"]]
        after_sh = collections.Counter()
        delta_w = collections.Counter()
        after_melds = collections.Counter()
        kinds = collections.Counter()
        tiles = collections.Counter()
        width_delta = []
        for row in taken:
            record = row["record"]
            if "a_sa" not in record:
                continue
            after_sh[record["a_sa"]] += 1
            change = record["a_wa"] - record["wb"]
            width_delta.append(change)
            delta_w["wider" if change > 0 else
                    ("equal" if change == 0 else "narrower")] += 1
            after_melds[record["ml"] + 1] += 1
            kinds[record["ckind"]] += 1
            tiles[record["tc"]] += 1
        tenpai[group] = {
            "opportunities": len(subset), "taken": len(taken),
            "usage": (len(taken) / len(subset)) if subset else None,
            "after_shanten": dict(sorted(after_sh.items())),
            "delta_width": dict(delta_w),
            "width_delta_mean": (statistics.fmean(width_delta) if width_delta else None),
            "after_melds": dict(sorted(after_melds.items())),
            "claim_kind": dict(kinds), "tile_class": dict(tiles),
            "baotou_after": sum(1 for row in taken if row["record"]["bb"] is True),
        }
    print()
    print("== 听牌（鸣前 0 向听）机会的鸣后去向（只统计实际发生且能算鸣后态的）")
    for group in ("me", "elite", "other"):
        item = tenpai[group]
        print("  %-6s 机会 %5d 用掉 %4d 使用率 %s | 鸣后向听 %s | 宽度变化 %s（均值 %s）"
              " | 鸣后副露 %s | 类型 %s | 牌类 %s | 鸣后爆头 %d"
              % (group, item["opportunities"], item["taken"],
                 fmt(item["usage"]), item["after_shanten"], item["delta_width"],
                 fmt(item["width_delta_mean"]), item["after_melds"],
                 item["claim_kind"], item["tile_class"], item["baotou_after"]))

    # ---- 稳健性：全量语料 ----
    full = decompose(all_rows)
    print()
    print("== 稳健性对照（全量语料 %d 局含强手）：u_me %.4f / u_elite %.4f，总差 %+.4f"
          % (rounds, full["u_me"], full["u_elite"], full["total_gap"]))
    full_top = sorted(full["cells"], key=lambda item: item["contribution"])[:5]
    for entry in full_top:
        print("  %-22s 机会 %6d  差 %s  贡献 %s（占缺口 %5.1f%%）"
              % (entry["cell"], entry["chances"], fmt_signed(entry["d_u"]),
                 fmt_signed(entry["contribution"]),
                 100 * entry["contribution"] / full["total_gap"]))

    payload = {
        "selfcheck": [{"text": text, "ok": passed} for text, passed in checks],
        "selfcheck_ok": ok,
        "primary": data,
        "full": full,
        "cumulative_80_by_family": cumulative_by_family,
        "located_cell": located,
        "located_cell_refined": located_refined,
        "tenpai": tenpai,
        "families": {key: {"sum": value["sum"], "residual": value["residual"]}
                     for key, value in by_family.items()},
        "audit": dict(audit),
        "rounds_with_elite": rounds,
        "registry_cells": sorted({key for row in primary_rows_list
                                  for key in row["labels"].values()}),
    }
    (_project_file(_PROJECT_ROOT, OUT / "cells.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print()
    print("结果写入 %s" % (_project_file(_PROJECT_ROOT, OUT / "cells.json")))
    print("总用时 %.1f 秒" % (time.time() - started))

    bad = [path for path in READ_PATHS
           if "events.json" not in path and "leaderboard-week.json" not in path
           and "rounds.jsonl" not in path]
    print("泄漏检查：读取路径 %d 条，非官方牌谱/公开榜单/既有重建产物者 %d 条 -> %s"
          % (len(READ_PATHS), len(bad), "通过" if not bad else "**失败**"))
    assert not bad, bad
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
