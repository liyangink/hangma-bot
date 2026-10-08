#!/usr/bin/env python3
"""C23：强手的副露多是「机会更多」还是「更愿意鸣」（官方牌谱四家手牌重建）。

实验 ID：C23-CLAIM-OPPORTUNITY。口径、量与判定分支见同目录
C23-PREREG-CLAIM-OPPORTUNITY.md（本脚本在该文件落盘之后编写，未改口径）。

信息权限（赛后完整信息，非线上可见）：
* 只读官方牌谱 events.json：每个 block 的 start_hands（官方对**四家**公开的起手牌，
  是赛后字段）与公开事件流（tile_drawn 带牌码、tile_discarded、chi/peng/gang、
  pass/timeout）。
* 不读任何 audit/、decisions.jsonl、raw 报文或我方私有观察；脚本末尾对读取路径做断言。

规则单一来源纪律（根 AGENTS.md 第 5 节）：本脚本**不实现**任何吃/碰/杠合法性规则，
一律调用 hangma.action_families 的候选生成函数（peng_candidates / chi_candidates /
gang_candidates），窗口成员由 hangma.progression 的窗口语义推导（PREREG 第 3/4 节）。
手牌逐事件扣减口径与 review/baotou-anatomy-20260925/anatomy_lib.py:reconstruct_round
逐字一致，并在全量语料上**机器对拍**（PREREG 第 9.2 节），不构成第二套规则。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \\
        review/freematch-deep-dive-20260925/c23_claim_opportunity.py
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
import glob
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import anatomy_lib as AL  # noqa: E402
import stats_lib as SL  # noqa: E402

from hangma_bot.hangma import action_families, hand_analysis  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_ORDER, WindowContext  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.kernel.observation import PublicDiscard  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c23-claim-opportunity")
ROUNDS_JSONL = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')
LB_GLOB = str(_project_file(_PROJECT_ROOT, ROOT / "datasets" / "leaderboard" / "snapshots" / "*" / "leaderboard-week.json"))

ME = AL.ME
WEALTH = AL.WEALTH            # 财神（白）
WALL_TOTAL = 136
TILE_INDEX = {code: index for index, code in enumerate(TILE_ORDER)}

# 已知读数（C22-ELITE-BEHAVIOUR-PAIRED.md 第一节），用于 PREREG 第 9.1 节自检。
KNOWN = {
    "melds_end": {"mean": {"me": 1.033, "elite": 1.199, "other": 1.101},
                  "paired": -0.183, "lo": -0.223, "hi": -0.141},
    "entered_baotou": {"mean": {"me": 0.0456, "elite": 0.0970, "other": 0.0608},
                       "paired": -0.0520, "lo": -0.0641, "hi": -0.0400},
    "won": {"mean": {"me": 0.2536, "elite": 0.2609, "other": 0.2256},
            "paired": None, "lo": None, "hi": None},
    "rounds_with_elite": 2800,
    "rounds": 3920,
}

READ_PATHS = []
"""本脚本实际读取的文件路径（泄漏检查用；断言只含官方牌谱与公开榜单）。"""


# ---------------------------------------------------------------------------
# 公开榜标签（与 C22 同口径）
# ---------------------------------------------------------------------------


def load_board():
    """周榜 top-32 标签（含 prev.top，与 c22_elite_behaviour_paired.py 同口径）。"""

    paths = sorted(glob.glob(LB_GLOB))
    path = paths[-1]
    READ_PATHS.append(path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = {}
    for row in payload.get("top") or []:
        if row.get("user_id"):
            ids[row["user_id"]] = row
    for row in (payload.get("prev") or {}).get("top") or []:
        if row.get("user_id"):
            ids.setdefault(row["user_id"], row)
    return ids, path


# ---------------------------------------------------------------------------
# 窗口模型（PREREG 第 4 节；规则依据 PREREG 第 3 节）
# ---------------------------------------------------------------------------


def window_members(discarder, tile, owner):
    """一次弃牌开启的（碰/明杠窗口成员, 吃窗口成员）。

    owner 是该次弃牌**应用之后**的圈主座位（无圈为 None）：
    - 弃白不开窗（R4）：P=C=空；
    - 圈活跃（R5/R6）：P={圈主}；C={(D+1)%4} 仅当圈主恰为下家；
    - 无圈：P=除弃牌者外三家；C={(D+1)%4}。
    """

    if tile == WEALTH:
        return (), ()
    if owner is not None:
        peng = (owner,)
        nxt = (discarder + 1) % 4
        chi = (nxt,) if owner == nxt else ()
        return peng, chi
    peng = tuple(index for index in range(4) if index != discarder)
    return peng, ((discarder + 1) % 4,)


def _tiles(counter):
    """计数 → 规范牌序的 Tile 元组（与 anatomy_lib._tiles 同口径）。"""

    result = []
    for code in TILE_ORDER:
        result.extend([Tile(code)] * counter[code])
    return tuple(result)


def claim_shapes(hand_counter, seat, discarder, tile, seq, chi_count, peng_codes,
                 restricted, in_peng, in_chi, wall_remaining):
    """该弃牌上本座的合法鸣牌形状（全部由 hangma 判定，不另写规则）。

    返回 {peng, chi, ming_gang} 三个布尔；窗口成员之外的族一律不调用
    （responding_seats 与 phase 由调用方按 PREREG 第 4 节给出）。
    """

    hand_tiles = _tiles(hand_counter)
    discard = PublicDiscard(seat=discarder, tile=Tile(tile), seq=seq)
    common = dict(
        seat=seat,
        turn_seat=discarder,
        hand_tiles=hand_tiles,
        drawn_tile=None,
        my_chi_count=chi_count,
        my_peng_codes=tuple(peng_codes),
        last_discard=discard,
        catch_play=restricted,
        remaining_tile_count=wall_remaining,
    )
    result = {"peng": False, "chi": False, "ming_gang": False}
    if in_peng:
        context = WindowContext(phase="response_peng", responding_seats=(seat,), **common)
        result["peng"] = bool(action_families.peng_candidates(context).candidates)
        result["ming_gang"] = bool(action_families.gang_candidates(context).candidates)
    if in_chi:
        context = WindowContext(phase="response_chi", responding_seats=(seat,), **common)
        result["chi"] = bool(action_families.chi_candidates(context).candidates)
    return result


# ---------------------------------------------------------------------------
# 单局扫描：逐事件重建 + 机会统计 + Q4 弃牌窗口结构
# ---------------------------------------------------------------------------


def scan_round(events, start_hands, verbose=False):
    """重建一局的四家暗牌，并在每张弃牌上统计机会、实际鸣牌与 Q4 结构。

    返回 (summary, audit, verbose_lines)。逐事件扣减口径与
    anatomy_lib.reconstruct_round 逐字一致；summary["windows"] 用于第 9.2 节对拍。
    """

    hands = [collections.Counter(hand) for hand in start_hands]
    melds = [0, 0, 0, 0]
    chi_counts = [0, 0, 0, 0]
    peng_codes = [list() for _ in range(4)]
    meld_tiles = [list() for _ in range(4)]
    rivers = [list() for _ in range(4)]
    catch = [False, False, False, False]

    claims = [0, 0, 0, 0]
    peng_claims = [0, 0, 0, 0]
    chi_claims = [0, 0, 0, 0]
    minggang_claims = [0, 0, 0, 0]
    an_gang = [0, 0, 0, 0]
    bu_gang = [0, 0, 0, 0]
    discards_n = [0, 0, 0, 0]
    draws_n = [0, 0, 0, 0]

    opp_a = [0, 0, 0, 0]          # 口径 A：有鸣牌机会的他人弃牌张数
    opp_a_peng = [0, 0, 0, 0]
    opp_a_chi = [0, 0, 0, 0]
    opp_a_gang = [0, 0, 0, 0]
    base_a = [0, 0, 0, 0]         # 分母 = 他方弃牌总数（开窗的非白弃牌）
    opp_b_keys = [set() for _ in range(4)]   # 口径 B：有 >=1 次机会的回合号
    # 机会发生那一刻本座的向听分档（0 / 1 / 2 / >=3），以及其中被实际用掉的数量：
    # 用于区分「阈值不同」与「更早成形」（PREREG 第 6 节分支 2 要求说明这一点）。
    opp_by_shanten = [collections.Counter() for _ in range(4)]
    taken_by_shanten = [collections.Counter() for _ in range(4)]

    q4 = {seat: collections.Counter() for seat in range(4)}

    windows = []
    audit = {
        "discards": 0, "missing_catch_flag": 0, "catch_flag_mismatch": 0,
        "trace_seat_outside_window": 0, "claim_seat_outside_window": 0,
        "circle_peng_window_not_single": 0, "windows_checked": 0,
        "claims_without_opportunity": 0, "claims_weighted": 0,
        "wall_remaining_min": None, "wall_remaining_max": None,
    }
    verbose_lines = []

    def walk(index):
        """沿事件流走一段响应轨迹，返回 (响应事件列表, 终止事件或 None)。"""

        seen = []
        while index < len(events):
            item = events[index]
            if item["type"] not in ("pass", "timeout"):
                return seen, item
            data = item.get("data") or {}
            if item["type"] == "timeout" and data.get("kind") not in (None, "response"):
                return seen, item
            seen.append(item)
            index += 1
        return seen, None

    for position, event in enumerate(events):
        kind = event["type"]
        seat = event.get("seat")
        tile = event.get("tile")
        data = event.get("data") or {}

        if kind in ("round_ended", "game_ended"):
            break
        if kind == "tile_drawn":
            hands[seat][tile] += 1
            draws_n[seat] += 1
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
            if verbose:
                verbose_lines.append("        >>> 实际鸣牌：座%d 碰 %s（seq=%s）"
                                     % (seat, tile, event["seq"]))
            continue
        if kind == "chi":
            consumed = list(data["tiles"])
            consumed.remove(tile)          # 第三张来自他家弃牌，不在本人暗牌
            melds[seat] += 1
            chi_counts[seat] += 1
            meld_tiles[seat].append(tuple(sorted(consumed)))
            for own in consumed:
                hands[seat][own] -= 1
            claims[seat] += 1
            chi_claims[seat] += 1
            if verbose:
                verbose_lines.append("        >>> 实际鸣牌：座%d 吃 %s（组合 %s，seq=%s）"
                                     % (seat, tile, "".join(data["tiles"]), event["seq"]))
            continue
        if kind == "gang":
            gang_kind = data.get("kind")
            consumed = {"ming": 3, "an": 4, "bu": 1}[gang_kind]
            if gang_kind == "bu":
                bu_gang[seat] += 1
                for index, group in enumerate(meld_tiles[seat]):
                    if group and group[0] == tile and len(group) == 3:
                        meld_tiles[seat][index] = tuple([tile] * 4)
                        break
            else:
                melds[seat] += 1
                extra = 1 if gang_kind == "ming" else 0
                meld_tiles[seat].append(tuple([tile] * (consumed + extra)))
                if gang_kind == "an":
                    an_gang[seat] += 1
                else:
                    claims[seat] += 1
                    minggang_claims[seat] += 1
                    if verbose:
                        verbose_lines.append("        >>> 实际鸣牌：座%d 明杠 %s（seq=%s）"
                                             % (seat, tile, event["seq"]))
            hands[seat][tile] -= consumed
            continue
        if kind != "tile_discarded":
            continue

        # ---- 弃牌 ----
        audit["discards"] += 1
        hand_before = _tiles(hands[seat])
        melds_before = melds[seat]
        if verbose:
            verbose_lines.append(
                "seq=%-5s 座%d 弃 %-2s  暗牌14=%d 副露=%d"
                % (event["seq"], seat, tile, len(hand_before), melds_before))
        # 先应用弃牌（含抓打圈生命周期，PREREG 第 3 节 R7），再按弃后状态定窗口。
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

        flag = data.get("catch_play")
        if flag is None:
            audit["missing_catch_flag"] += 1
        elif bool(flag) != (owner is not None):
            audit["catch_flag_mismatch"] += 1

        peng_members, chi_members = window_members(seat, tile, owner)
        if owner is not None and tile != WEALTH and len(peng_members) != 1:
            audit["circle_peng_window_not_single"] += 1

        # 牌墙余量估计：136 - Σ暗牌 - Σ牌河 - Σ副露牌（被鸣走的弃牌已从牌河移除，
        # 新平台口径 v34+；该量只用于最后 20 张禁杠门禁，不影响碰/吃机会）。
        known = sum(sum(hands[i].values()) for i in range(4))
        known += sum(len(river) for river in rivers)
        known += sum(len(group) for groups in meld_tiles for group in groups)
        wall_remaining = WALL_TOTAL - known
        low, high = audit["wall_remaining_min"], audit["wall_remaining_max"]
        audit["wall_remaining_min"] = wall_remaining if low is None else min(low, wall_remaining)
        audit["wall_remaining_max"] = wall_remaining if high is None else max(high, wall_remaining)

        if verbose:
            verbose_lines.append(
                "        窗口：圈主=%s 碰窗={%s} 吃窗={%s} 墙余≈%d"
                % ("无" if owner is None else owner,
                   ",".join(str(item) for item in peng_members),
                   ",".join(str(item) for item in chi_members), wall_remaining))

        # 官方响应轨迹：只作对拍。平台在有人鸣牌时会先发鸣牌事件、其余响应事件
        # 不补齐，因此轨迹不能反过来当窗口成员来源（见结果文档窗口对拍一节）。
        observed, terminator = walk(position + 1)
        allowed = set(peng_members) | set(chi_members)
        if any(item["seat"] not in allowed for item in observed):
            audit["trace_seat_outside_window"] += 1
        if tile != WEALTH:
            audit["windows_checked"] += 1

        pending = {}
        for responder in range(4):
            if responder == seat:
                continue
            in_peng = responder in peng_members
            in_chi = responder in chi_members
            if not in_peng and not in_chi:
                continue
            restricted = owner is not None and responder != owner
            shapes = claim_shapes(
                hands[responder], responder, seat, tile, event["seq"],
                chi_counts[responder], peng_codes[responder],
                restricted, in_peng, in_chi, wall_remaining,
            )
            if tile != WEALTH:
                base_a[responder] += 1
            if in_peng and shapes["peng"]:
                opp_a_peng[responder] += 1
            if in_peng and shapes["ming_gang"]:
                opp_a_gang[responder] += 1
            if in_chi and shapes["chi"]:
                opp_a_chi[responder] += 1
            hit = shapes["peng"] or shapes["chi"]
            if hit:
                opp_a[responder] += 1
                opp_b_keys[responder].add(discards_n[responder])
                bucket = min(3, hand_analysis.analyse_hand(
                    _tiles(hands[responder]), melds[responder]).shanten)
                pending[responder] = bucket
                opp_by_shanten[responder][bucket] += 1
            if verbose:
                held = hands[responder].get(tile, 0)
                pieces = []
                if in_peng:
                    pieces.append("碰窗内 持%s×%d %s"
                                  % (tile, held, "→碰机会✓" if shapes["peng"] else "→无碰机会"))
                    if shapes["ming_gang"]:
                        pieces.append("明杠机会✓")
                if in_chi:
                    pieces.append("下家吃窗 %s"
                                  % ("→吃机会✓" if shapes["chi"] else "→无吃机会"))
                verbose_lines.append("        座%d %s" % (responder, "；".join(pieces)))

        # 该窗口的终止事件是鸣牌时，把它记成「机会被用掉」（同一座位、同一张弃牌）。
        if terminator is not None and terminator["type"] in ("peng", "chi", "gang"):
            claim_seat = terminator["seat"]
            audit["claims_weighted"] += 1
            if terminator["type"] == "chi":
                if claim_seat not in chi_members:
                    audit["claim_seat_outside_window"] += 1
            elif claim_seat not in peng_members:
                audit["claim_seat_outside_window"] += 1
            if claim_seat in pending:
                taken_by_shanten[claim_seat][pending[claim_seat]] += 1
            else:
                audit["claims_without_opportunity"] += 1
                if verbose:
                    verbose_lines.append(
                        "        !! 座%d 的鸣牌在其窗口内没有被本模型记为机会"
                        % claim_seat)

        # Q4：弃牌者自身在弃牌那一刻的可鸣结构（14 张 -> 弃后 13 张）。
        before_counts = collections.Counter(item.code for item in hand_before)
        after_counts = collections.Counter(hands[seat])
        pairs_natural = sum(1 for code, count in before_counts.items()
                            if code != WEALTH and count >= 2)
        whites = before_counts.get(WEALTH, 0)
        left_river = sorted({code for code in rivers[(seat - 1) % 4] if code != WEALTH})
        whole_river = sorted({code for river in rivers for code in river if code != WEALTH})
        after_tiles = _tiles(after_counts)

        def chi_hit(code):
            """本座 13 张手牌能否吃下上家牌河的 code（hangma 判定）。"""

            context = WindowContext(
                seat=seat, phase="response_chi", turn_seat=(seat - 1) % 4,
                responding_seats=(seat,), hand_tiles=after_tiles, drawn_tile=None,
                my_chi_count=chi_counts[seat], my_peng_codes=tuple(peng_codes[seat]),
                last_discard=PublicDiscard(seat=(seat - 1) % 4, tile=Tile(code), seq=0),
                catch_play=False, remaining_tile_count=wall_remaining,
            )
            return bool(action_families.chi_candidates(context).candidates)

        left_chi = sum(1 for code in left_river if chi_hit(code))
        river_peng = sum(1 for code in whole_river if after_counts.get(code, 0) >= 2)
        union = {code for code in whole_river if after_counts.get(code, 0) >= 2}
        union.update(code for code in left_river if chi_hit(code))
        summary13 = hand_analysis.analyse_hand(after_tiles, melds[seat])
        q4[seat]["windows"] += 1
        q4[seat]["pairs"] += pairs_natural
        q4[seat]["whites"] += whites
        q4[seat]["left_chi"] += left_chi
        q4[seat]["river_peng"] += river_peng
        q4[seat]["union"] += len(union)
        q4[seat]["width"] += len(summary13.useful_tiles)
        q4[seat]["shanten"] += summary13.shanten

        if len(hand_before) == 14 - 3 * melds_before:
            windows.append((event["seq"], seat,
                            tuple(sorted(item.code for item in hand_before)),
                            melds_before, tile))

    summary = {
        "hands_end": [dict(hand) for hand in hands],
        "melds_end": list(melds),
        "claims": claims,
        "peng_claims": peng_claims,
        "chi_claims": chi_claims,
        "minggang_claims": minggang_claims,
        "opp_by_shanten": [{str(level): opp_by_shanten[seat].get(level, 0)
                            for level in range(4)} for seat in range(4)],
        "taken_by_shanten": [{str(level): taken_by_shanten[seat].get(level, 0)
                              for level in range(4)} for seat in range(4)],
        "an_gang": an_gang,
        "bu_gang": bu_gang,
        "discards_n": discards_n,
        "draws_n": draws_n,
        "opp_a": opp_a,
        "opp_a_peng": opp_a_peng,
        "opp_a_chi": opp_a_chi,
        "opp_a_gang": opp_a_gang,
        "base_a": base_a,
        "opp_b": [len(item) for item in opp_b_keys],
        "base_b": list(discards_n),
        "q4": {seat: dict(counter) for seat, counter in q4.items()},
        "windows": windows,
    }
    return summary, audit, verbose_lines


# ---------------------------------------------------------------------------
# 统计：局内配对 + 按房聚类 CI
# ---------------------------------------------------------------------------

GROUPS = ("me", "elite", "other")
FENCE = chr(96) * 3   # markdown 代码围栏，避免源码里出现反引号导致模板串截断


def c22_bootstrap(values, draws=1200, seed=5):
    """复刻 c22_elite_behaviour_paired.py 的逐局 bootstrap（用于自检对拍）。"""

    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        picked = [rng.choice(values) for _ in values]
        means.append(statistics.fmean(picked))
    means.sort()
    return means[30], means[1170]


def metric_report(name, label, fn, rounds, digits=4):
    """一个量的三组均值 + 局内配对差 + 按房聚类 95% CI。

    fn(seat_record) -> float | None：座-局层面取值；None 表示该座-局不可定义
    （例如机会数为 0 时的使用率），该座从本轮该组均值中剔除。
    """

    marginal = {group: [] for group in GROUPS}
    paired = {"me_minus_elite": [], "other_minus_elite": [], "elite_minus_me": []}
    clusters = []
    other_clusters = []
    for row in rounds:
        per_group = {}
        for group in GROUPS:
            values = []
            for seat in row["seats"]:
                if seat["group"] != group:
                    continue
                value = fn(seat)
                if value is not None:
                    values.append(float(value))
            per_group[group] = statistics.fmean(values) if values else None
            marginal[group].extend(values)
        if per_group["me"] is not None and per_group["elite"] is not None:
            diff = per_group["me"] - per_group["elite"]
            paired["me_minus_elite"].append(diff)
            paired["elite_minus_me"].append(-diff)
            clusters.append(row["room"])
        if per_group["other"] is not None and per_group["elite"] is not None:
            paired["other_minus_elite"].append(per_group["other"] - per_group["elite"])
            other_clusters.append(row["room"])

    result = {"name": name, "label": label,
              "mean": {group: (statistics.fmean(values) if values else None)
                       for group, values in marginal.items()},
              "n": {group: len(values) for group, values in marginal.items()},
              "paired_n": {key: len(values) for key, values in paired.items()}}
    for key, values in paired.items():
        keys = other_clusters if key == "other_minus_elite" else clusters
        entry = {"cluster": SL.cluster_ci(values, keys),
                 "bootstrap": SL.cluster_bootstrap(values, keys, draws=4000,
                                                   seed=20260926)}
        if key == "me_minus_elite" and values:
            entry["c22"] = c22_bootstrap(values)
        result["paired_" + key] = entry
    return result


def fmt(value, digits=4):
    return "n/a" if value is None else ("%+.*f" % (digits, value))


def render(result, digits=4):
    """把 metric_report 的结果渲染成一行 markdown 表格行。"""

    mean = result["mean"]
    paired = result["paired_me_minus_elite"]
    cluster = paired["cluster"]
    return "| %s | %s | %s | %s | %s | [%s, %s] | [%s, %s] |" % (
        result["label"],
        "%.*f" % (digits, mean["me"]) if mean["me"] is not None else "n/a",
        "%.*f" % (digits, mean["elite"]) if mean["elite"] is not None else "n/a",
        "%.*f" % (digits, mean["other"]) if mean["other"] is not None else "n/a",
        fmt(cluster["mean"], digits),
        fmt(cluster["lo"], digits), fmt(cluster["hi"], digits),
        fmt(paired["bootstrap"]["lo"], digits), fmt(paired["bootstrap"]["hi"], digits),
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    board, board_path = load_board()
    print("榜单快照 %s：top+prev 标签 %d 人" % (Path(board_path).name, len(board)))

    primary_rows = [json.loads(line) for line in ROUNDS_JSONL.open(encoding="utf-8")
                    if line.strip()]
    READ_PATHS.append(str(ROUNDS_JSONL))
    primary_index = {(row["game_id"], row["round_no"]): row for row in primary_rows}
    print("主语料 rounds.jsonl：%d 局 / %d 场 / %d 房"
          % (len(primary_rows), len(set(r["game_id"] for r in primary_rows)),
             len(set(r["room_id"] for r in primary_rows))))

    games = AL.load_games()
    READ_PATHS.extend(game["path"] for game in games)
    print("官方牌谱去重后 %d 场" % len(games))
    # 冒烟/调试用：C23_GAME_LIMIT 只截断场次，不改变任何口径（默认 0 = 全量）。
    limit = int(os.environ.get("C23_GAME_LIMIT", "0") or 0)
    if limit:
        games = games[:limit]
        print("C23_GAME_LIMIT=%d：只跑前 %d 场（仅冒烟用，不用于结论）" % (limit, limit))

    rounds = []
    equality = {"rounds": 0, "hands_mismatch": 0, "melds_mismatch": 0,
                "windows_mismatch": 0, "rounds_jsonl_melds_mismatch": 0,
                "rounds_jsonl_baotou_mismatch": 0, "details": []}
    window_audit = collections.Counter()
    verbose_targets = []

    for game in games:
        document = game["doc"]
        seats_meta = document.get("seats") or []
        room = document.get("room_id") or game["session"]
        users = [item.get("user_id") for item in seats_meta]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            recon = AL.reconstruct_round(events, start_hands)
            summary, audit, _ = scan_round(events, start_hands)
            for key, value in audit.items():
                if value is None:
                    continue
                if key.startswith("wall_remaining"):
                    prior = window_audit.get(key)
                    if prior is None:
                        window_audit[key] = value
                    elif key.endswith("min"):
                        window_audit[key] = min(prior, value)
                    else:
                        window_audit[key] = max(prior, value)
                else:
                    window_audit[key] += value

            # —— 第 9.2 节：重建等价性 ——
            equality["rounds"] += 1
            for seat in range(4):
                mine = {code: count for code, count in summary["hands_end"][seat].items()
                        if count}
                theirs = {code: count for code, count in recon["hands_end"][seat].items()
                          if count}
                if mine != theirs:
                    equality["hands_mismatch"] += 1
                    if len(equality["details"]) < 5:
                        equality["details"].append(
                            ["hands", game["game_id"], round_no, seat])
            if summary["melds_end"] != recon["melds_end"]:
                equality["melds_mismatch"] += 1
            mine_windows = [tuple(item) for item in summary["windows"]]
            their_windows = [(item["seq"], item["seat"],
                              tuple(sorted(tile.code for tile in item["hand_before"])),
                              item["meld_count"], item["chosen"])
                             for item in recon["discard_windows"]]
            if mine_windows != their_windows:
                equality["windows_mismatch"] += 1
                if len(equality["details"]) < 5:
                    equality["details"].append(
                        ["windows", game["game_id"], round_no,
                         len(mine_windows), len(their_windows)])

            key = (game["game_id"], round_no)
            in_primary = key in primary_index
            reference = primary_index.get(key)
            if reference is not None:
                for seat in range(4):
                    seat_row = reference["seats"][seat]
                    if seat_row["melds_end"] != recon["melds_end"][seat]:
                        equality["rounds_jsonl_melds_mismatch"] += 1
                    entered = any(item["baotou"] for item in recon["waits"][seat])
                    if bool(seat_row["entered_baotou"]) != bool(entered):
                        equality["rounds_jsonl_baotou_mismatch"] += 1

            ended = next((item for item in events if item["type"] == "round_ended"), None)
            data = (ended or {}).get("data") or {}
            winner = ended.get("seat") if ended else None
            winner = winner if type(winner) is int and 0 <= winner < 4 else None
            is_draw = bool(data.get("draw"))

            # —— 人工核对候选（PREREG 第 9.5 节：三个条件下各取字典序最小局）——
            if any(summary["claims"]):
                has_circle = any(event["type"] == "tile_discarded"
                                 and event["tile"] == WEALTH for event in events)
                verbose_targets.append(("with_circle" if has_circle else "", game["game_id"],
                                        round_no, events, start_hands, tuple(users)))

            seat_records = []
            for seat in range(4):
                user = users[seat] if seat < len(users) else None
                if user == ME:
                    group = "me"
                elif user in board:
                    group = "elite"
                else:
                    group = "other"
                entered = any(item["baotou"] for item in recon["waits"][seat])
                q4 = summary["q4"][seat]
                seat_records.append({
                    "seat": seat, "user_id": user, "group": group,
                    "melds_end": recon["melds_end"][seat],
                    "claims": summary["claims"][seat],
                    "peng_claims": summary["peng_claims"][seat],
                    "chi_claims": summary["chi_claims"][seat],
                    "minggang_claims": summary["minggang_claims"][seat],
                    "opp_by_shanten": summary["opp_by_shanten"][seat],
                    "taken_by_shanten": summary["taken_by_shanten"][seat],
                    "an_gang": summary["an_gang"][seat],
                    "bu_gang": summary["bu_gang"][seat],
                    "opp_a": summary["opp_a"][seat],
                    "opp_a_peng": summary["opp_a_peng"][seat],
                    "opp_a_chi": summary["opp_a_chi"][seat],
                    "opp_a_gang": summary["opp_a_gang"][seat],
                    "base_a": summary["base_a"][seat],
                    "opp_b": summary["opp_b"][seat],
                    "base_b": summary["base_b"][seat],
                    "entered_baotou": 1 if entered else 0,
                    "won": 1 if (winner == seat and not is_draw) else 0,
                    "discards_n": summary["discards_n"][seat],
                    "draws_n": summary["draws_n"][seat],
                    "q4_windows": q4.get("windows", 0),
                    "q4_pairs": q4.get("pairs", 0),
                    "q4_whites": q4.get("whites", 0),
                    "q4_left_chi": q4.get("left_chi", 0),
                    "q4_river_peng": q4.get("river_peng", 0),
                    "q4_union": q4.get("union", 0),
                    "q4_width": q4.get("width", 0),
                })
            group_has = {group: any(seat["group"] == group for seat in seat_records)
                         for group in GROUPS}
            rounds.append({
                "game_id": game["game_id"], "room": room, "round_no": round_no,
                "session": game["session"], "primary": in_primary, "is_draw": is_draw,
                "seats": seat_records, "group_has": group_has,
            })

    primary = [row for row in rounds if row["primary"]]
    print("重建 %d 局（其中主语料 %d 局），用时 %.1f 秒"
          % (len(rounds), len(primary), time.time() - started))

    # —— 第 9.2 节断言 ——
    ok = (equality["hands_mismatch"] == 0 and equality["melds_mismatch"] == 0
          and equality["windows_mismatch"] == 0)
    print("重建等价性：局数 %d，暗牌不符 %d，副露不符 %d，弃牌窗口不符 %d -> %s"
          % (equality["rounds"], equality["hands_mismatch"], equality["melds_mismatch"],
             equality["windows_mismatch"], "通过" if ok else "**失败**"))
    print("对 rounds.jsonl 复核：终局副露不符 %d，爆头进入不符 %d"
          % (equality["rounds_jsonl_melds_mismatch"],
             equality["rounds_jsonl_baotou_mismatch"]))

    # —— 第 9.3 节：窗口模型对拍 ——
    print("鸣牌归属：终止事件里的鸣牌 %d 次，其中未在本模型窗口内记成机会 %d 次"
          % (window_audit["claims_weighted"], window_audit["claims_without_opportunity"]))
    print("窗口对拍：弃牌 %d 张，开窗弃牌 %d 张，catch_play 字段缺失 %d，圈标记不符 %d，"
          "轨迹座位越窗 %d，鸣牌座位越窗 %d，圈内碰窗非单座 %d，墙余区间 [%s, %s]"
          % (window_audit["discards"], window_audit["windows_checked"],
             window_audit["missing_catch_flag"], window_audit["catch_flag_mismatch"],
             window_audit["trace_seat_outside_window"],
             window_audit["claim_seat_outside_window"],
             window_audit["circle_peng_window_not_single"],
             window_audit.get("wall_remaining_min"), window_audit.get("wall_remaining_max")))

    # —— 第 9.1 节：三条已知读数 ——
    rounds_with_elite = [row for row in primary if row["group_has"]["elite"]]

    def c22_mean(rows, key, group):
        """C22 报告里组均值的真实口径：**排除流局局**。

        c22_elite_behaviour_paired.py 的 totals 累加写在 won 计数之后的
        `if row.get("is_draw"): continue` 之下，于是流局局的座值不进入组均值，
        但配对差是在另一个循环里算的、**包含**流局局。该差异在本语料上是 17/2800
        （0.61%）局，影响组均值第 3 位小数，不影响配对差（对拍见下）。
        """

        values = []
        for row in rows:
            if row.get("is_draw"):
                continue
            for seat in row["seats"]:
                if seat["group"] == group:
                    values.append(float(seat[key]))
        return statistics.fmean(values) if values else None

    # 「已知读数」的组均值口径逐项不同：melds_end / entered_baotou 来自 C22 的
    # totals（被 is_draw 的 continue 跳过），胡牌率来自 won 计数（分母含流局局）。
    c22_style = {"melds_end": True, "entered_baotou": True, "won": False}

    checks = []
    for name, label in (("melds_end", "终局副露数"), ("entered_baotou", "曾进入爆头"),
                        ("won", "胡牌率")):
        result = metric_report(name, label, lambda seat, key=name: seat[key],
                               rounds_with_elite)
        known = KNOWN[name]
        row = {"name": name, "label": label,
               "mean": result["mean"],
               "mean_c22_style": {group: c22_mean(rounds_with_elite, name, group)
                                  for group in GROUPS}}
        basis = row["mean_c22_style"] if c22_style[name] else result["mean"]
        row["check_basis"] = "C22口径（排除流局局）" if c22_style[name] else "全量口径（含流局局）"
        row["mean_diff"] = {group: (abs(basis[group] - known["mean"][group])
                                    if basis[group] is not None else None)
                            for group in GROUPS}
        row["mean_diff_all_rounds"] = {
            group: (abs(result["mean"][group] - known["mean"][group])
                    if result["mean"][group] is not None else None)
            for group in GROUPS}
        if known["paired"] is not None:
            cluster = result["paired_me_minus_elite"]["cluster"]
            c22 = result["paired_me_minus_elite"]["c22"]
            row["paired_diff"] = abs(cluster["mean"] - known["paired"])
            row["c22_ci"] = list(c22)
            row["paired_inside_known_ci"] = (known["lo"] - 0.002 <= c22[0]
                                             and c22[1] <= known["hi"] + 0.002)
        checks.append(row)
        c22_ci = row.get("c22_ci")
        cluster = result["paired_me_minus_elite"]["cluster"]
        print("%s：C22口径 我方 %.4f 强手 %.4f 其他 %.4f | 全量口径 我方 %.4f 强手 %.4f 其他 %.4f"
              % (label, row["mean_c22_style"]["me"], row["mean_c22_style"]["elite"],
                 row["mean_c22_style"]["other"], result["mean"]["me"],
                 result["mean"]["elite"], result["mean"]["other"]))
        print("    配对(我-强) %s [%s, %s] | C22 口径 [%s, %s]"
              % (fmt(cluster["mean"]), fmt(cluster["lo"]), fmt(cluster["hi"]),
                 fmt(c22_ci[0]) if c22_ci else "—",
                 fmt(c22_ci[1]) if c22_ci else "—"))

    selfcheck_ok = all(
        all(value is not None and value <= 1e-3 for value in row["mean_diff"].values())
        and (row.get("paired_diff") is None or row["paired_diff"] <= 2e-3)
        and row.get("paired_inside_known_ci", True)
        for row in checks)
    print("自检（第 9.1 节）：%s（含强手的局 %d）"
          % ("通过" if selfcheck_ok else "**失败**", len(rounds_with_elite)))
    json.dump({"checks": checks, "ok": selfcheck_ok,
               "rounds_with_elite": len(rounds_with_elite)},
              (_project_file(_PROJECT_ROOT, OUT / "selfcheck.json")).open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)

    if not (ok and selfcheck_ok) and not os.environ.get("C23_SKIP_SELFCHECK"):
        print("自检未通过：按 PREREG 第 9 节停止分析。"
              "（仅冒烟调试可设 C23_SKIP_SELFCHECK=1 绕过，结论必须用不绕过的一次运行。）")
        return 1
    if not (ok and selfcheck_ok):
        print("!! C23_SKIP_SELFCHECK=1：自检未通过仍继续，本次输出不得用于结论。")

    # —— Q1 / Q2 / Q4 ——
    per_window = lambda key: (lambda seat: (seat[key] / seat["q4_windows"])
                              if seat["q4_windows"] else None)
    metrics = [
        ("melds_end", "终局副露数", lambda seat: seat["melds_end"]),
        ("claims", "鸣牌次数（碰+吃+明杠）", lambda seat: seat["claims"]),
        ("opp_a", "机会数A（按打出的牌计）", lambda seat: seat["opp_a"]),
        ("opp_a_peng", "　碰机会数A", lambda seat: seat["opp_a_peng"]),
        ("opp_a_chi", "　吃机会数A", lambda seat: seat["opp_a_chi"]),
        ("opp_a_gang", "　明杠机会数A", lambda seat: seat["opp_a_gang"]),
        ("base_a", "　他方弃牌数（分母）", lambda seat: seat["base_a"]),
        ("base_b", "回合数（本座弃牌次数）", lambda seat: seat["base_b"]),
        ("opp_b", "机会数B（按回合计）", lambda seat: seat["opp_b"]),
        ("opp_a_rate", "机会率A = 机会数A/他方弃牌数",
         lambda seat: (seat["opp_a"] / seat["base_a"]) if seat["base_a"] else None),
        ("opp_b_rate", "机会率B = 机会数B/回合数",
         lambda seat: (seat["opp_b"] / seat["base_b"]) if seat["base_b"] else None),
        ("q4_pairs", "Q4 每窗口自然对子数", per_window("q4_pairs")),
        ("q4_whites", "Q4 每窗口白板张数", per_window("q4_whites")),
        ("q4_left_chi", "Q4 每窗口上家牌河可吃种类数", per_window("q4_left_chi")),
        ("q4_river_peng", "Q4 每窗口全场牌河可碰种类数", per_window("q4_river_peng")),
        ("q4_union", "Q4 每窗口可鸣种类数（并集）", per_window("q4_union")),
        ("q4_width", "Q4 每窗口有效牌宽度（hangma）", per_window("q4_width")),
        ("discards_n", "弃牌数", lambda seat: seat["discards_n"]),
    ]
    reports = {}
    print()
    print("== Q1/Q2：机会、使用率与可比量（主语料 %d 局，含强手 %d 局；按房聚类 G=%d）"
          % (len(primary), len(rounds_with_elite),
             len(set(row["room"] for row in rounds_with_elite))))
    print("| 量 | 我方 | 强手 | 其他 | 配对差(我-强) | 95%CI(按房) | 房 bootstrap |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    metric_fns = {name: fn for name, _label, fn in metrics}
    metric_labels = {name: label for name, label, _fn in metrics}
    for name, label, fn in metrics:
        result = metric_report(name, label, fn, rounds_with_elite)
        reports[name] = result
        print(render(result))

    for tag, opp_key in (("A", "opp_a"), ("B", "opp_b")):
        totals = {group: [0.0, 0.0] for group in GROUPS}
        per_round = {"me_minus_elite": [], "elite_minus_me": [], "other_minus_elite": []}
        keys = []
        other_keys = []
        for row in rounds_with_elite:
            group_pair = {}
            for group in GROUPS:
                claims = sum(seat["claims"] for seat in row["seats"]
                             if seat["group"] == group)
                chances = sum(seat[opp_key] for seat in row["seats"]
                              if seat["group"] == group)
                totals[group][0] += claims
                totals[group][1] += chances
                group_pair[group] = (claims / chances) if chances else None
            if group_pair["me"] is not None and group_pair["elite"] is not None:
                per_round["me_minus_elite"].append(group_pair["me"] - group_pair["elite"])
                per_round["elite_minus_me"].append(group_pair["elite"] - group_pair["me"])
                keys.append(row["room"])
            if group_pair["other"] is not None and group_pair["elite"] is not None:
                per_round["other_minus_elite"].append(
                    group_pair["other"] - group_pair["elite"])
                other_keys.append(row["room"])
        entry = {"usage": {group: (totals[group][0] / totals[group][1]
                                   if totals[group][1] else None) for group in GROUPS},
                 "claims": {group: totals[group][0] for group in GROUPS},
                 "chances": {group: totals[group][1] for group in GROUPS},
                 "rounds_defined": len(keys),
                 "cluster": SL.cluster_ci(per_round["me_minus_elite"], keys),
                 "bootstrap": SL.cluster_bootstrap(per_round["me_minus_elite"], keys,
                                                   draws=4000, seed=20260926),
                 "elite_minus_me": SL.cluster_ci(per_round["elite_minus_me"], keys),
                 "other_minus_elite": SL.cluster_ci(per_round["other_minus_elite"],
                                                    other_keys)}
        if per_round["me_minus_elite"]:
            entry["c22"] = c22_bootstrap(per_round["me_minus_elite"])
        reports["usage_" + tag] = entry
        cluster = entry["cluster"]
        print("| 使用率%s = 鸣牌次数/机会数%s | %.4f | %.4f | %.4f | %s | [%s, %s] | [%s, %s] |"
              % (tag, tag, entry["usage"]["me"], entry["usage"]["elite"],
                 entry["usage"]["other"], fmt(cluster["mean"]),
                 fmt(cluster["lo"]), fmt(cluster["hi"]),
                 fmt(entry["bootstrap"]["lo"]), fmt(entry["bootstrap"]["hi"])))

    # —— 使用率子类：碰 vs 吃（都按「局内组比值」配对，按房聚类）——
    for tag, claim_key, opp_key in (("碰", "peng_claims", "opp_a_peng"),
                                    ("吃", "chi_claims", "opp_a_chi")):
        totals = {group: [0.0, 0.0] for group in GROUPS}
        per_round = []
        keys = []
        for row in rounds_with_elite:
            pair = {}
            for group in GROUPS:
                claims = sum(seat[claim_key] for seat in row["seats"]
                             if seat["group"] == group)
                chances = sum(seat[opp_key] for seat in row["seats"]
                              if seat["group"] == group)
                totals[group][0] += claims
                totals[group][1] += chances
                pair[group] = (claims / chances) if chances else None
            if pair["me"] is not None and pair["elite"] is not None:
                per_round.append(pair["me"] - pair["elite"])
                keys.append(row["room"])
        usage = {group: (totals[group][0] / totals[group][1] if totals[group][1] else None)
                 for group in GROUPS}
        cluster = SL.cluster_ci(per_round, keys)
        reports["usage_" + claim_key] = {
            "usage": usage, "cluster": cluster, "rounds_defined": len(keys),
            "claims": {group: totals[group][0] for group in GROUPS},
            "chances": {group: totals[group][1] for group in GROUPS}}
        print("| 使用率%s = %s鸣牌数/%s机会数 | %.4f | %.4f | %.4f | %s | [%s, %s] | 定义局 %d |"
              % (tag, tag, tag, usage["me"], usage["elite"], usage["other"],
                 fmt(cluster["mean"]), fmt(cluster["lo"]), fmt(cluster["hi"]), len(keys)))

    # —— 机会的向听分档：区分「阈值不同」与「更早成形」——
    print()
    print("== 机会发生那一刻本座的 hangma 向听分档（0=听牌 / 1 / 2 / >=3）")
    print("| 向听档 | 我方 机会(用掉) 使用率 | 强手 机会(用掉) 使用率 | 其他 机会(用掉) 使用率"
          " | 强手−我方 使用率 | 95%CI(按房) |")
    for level in range(4):
        cells = {}
        for group in GROUPS:
            chances = taken = 0
            for row in rounds_with_elite:
                for seat in row["seats"]:
                    if seat["group"] != group:
                        continue
                    chances += seat["opp_by_shanten"][str(level)]
                    taken += seat["taken_by_shanten"][str(level)]
            cells[group] = (chances, taken)
        per_round = []
        keys = []
        for row in rounds_with_elite:
            pair = {}
            for group in GROUPS:
                chances = sum(seat["opp_by_shanten"][str(level)] for seat in row["seats"]
                              if seat["group"] == group)
                taken = sum(seat["taken_by_shanten"][str(level)] for seat in row["seats"]
                            if seat["group"] == group)
                pair[group] = (taken / chances) if chances else None
            if pair["me"] is not None and pair["elite"] is not None:
                per_round.append(pair["elite"] - pair["me"])
                keys.append(row["room"])
        cluster = SL.cluster_ci(per_round, keys)
        reports["shanten_%d" % level] = {
            "counts": {group: {"chances": cells[group][0], "taken": cells[group][1],
                               "usage": (cells[group][1] / cells[group][0]
                                         if cells[group][0] else None)}
                       for group in GROUPS},
            "elite_minus_me": cluster, "rounds_defined": len(keys)}
        text = []
        for group in GROUPS:
            chances, taken = cells[group]
            text.append("%d (%d) %s" % (chances, taken,
                                        "%.4f" % (taken / chances) if chances else "n/a"))
        print("| %s | %s | %s | %s | %s | [%s, %s] |"
              % ("听牌" if level == 0 else ("%d 向听" % level if level < 3 else ">=3 向听"),
                 text[0], text[1], text[2], fmt(cluster["mean"]),
                 fmt(cluster["lo"]), fmt(cluster["hi"])))

    # —— 逐房符号检查：使用率配对差的稳健性 ——
    by_room = collections.defaultdict(list)
    room_keys = []
    for row in rounds_with_elite:
        claims = {group: sum(seat["claims"] for seat in row["seats"]
                             if seat["group"] == group) for group in GROUPS}
        chances = {group: sum(seat["opp_a"] for seat in row["seats"]
                              if seat["group"] == group) for group in GROUPS}
        if not chances["me"] or not chances["elite"]:
            continue
        by_room[row["room"]].append(claims["me"] / chances["me"]
                                    - claims["elite"] / chances["elite"])
        room_keys.append(row["room"])
    room_means = {room: statistics.fmean(values) for room, values in by_room.items()}
    positive = sum(1 for value in room_means.values() if value > 0)
    negative = sum(1 for value in room_means.values() if value < 0)
    print("    使用率A 配对差的逐房符号：我方更高的房 %d 个，强手更高的房 %d 个（共 %d 房）"
          % (positive, negative, len(room_means)))
    reports["usage_A_rooms"] = {"rooms": len(room_means), "me_higher": positive,
                                "elite_higher": negative, "room_means": room_means}

    # —— 鲁棒性对照（PREREG 第 2 节）：当前全量语料，只作方向一致性，不作判定 ——
    secondary = [row for row in rounds if row["group_has"]["elite"]]
    print()
    print("== 鲁棒性对照：当前全量语料（共 %d 局，含强手 %d 局，房数 %d）"
          % (len(rounds), len(secondary), len(set(row["room"] for row in secondary))))
    print("| 量 | 我方 | 强手 | 其他 | 配对差(我-强) | 95%CI(按房) |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name in ("melds_end", "claims", "opp_a", "opp_b", "opp_a_rate"):
        result = metric_report(name, metric_labels[name], metric_fns[name], secondary)
        reports["secondary_" + name] = result
        paired = result["paired_me_minus_elite"]["cluster"]
        print("| %s | %.4f | %.4f | %.4f | %s | [%s, %s] |"
              % (metric_labels[name], result["mean"]["me"], result["mean"]["elite"],
                 result["mean"]["other"], fmt(paired["mean"]),
                 fmt(paired["lo"]), fmt(paired["hi"])))

    # —— Q3 分解 ——
    decomposition = {}
    for tag, out_key in (("claims", "claims"), ("melds", "melds_end")):
        me_o = reports["opp_a"]["mean"]["me"]
        el_o = reports["opp_a"]["mean"]["elite"]
        me_c = reports[out_key]["mean"]["me"]
        el_c = reports[out_key]["mean"]["elite"]
        u_me = reports["usage_A"]["usage"]["me"]
        u_el = reports["usage_A"]["usage"]["elite"]
        d_o = el_o - me_o
        d_c = el_c - me_c
        seq1 = {"opportunity": u_el * d_o, "usage": me_o * (u_el - u_me)}
        seq2 = {"opportunity": u_me * d_o, "usage": el_o * (u_el - u_me)}
        decomposition[tag] = {
            "d_opportunity": d_o, "d_outcome": d_c,
            "u_me": u_me, "u_elite": u_el, "O_me": me_o, "O_elite": el_o,
            "sequential_1": dict(seq1, sum=seq1["opportunity"] + seq1["usage"]),
            "sequential_2": dict(seq2, sum=seq2["opportunity"] + seq2["usage"]),
            "symmetric": {"opportunity": (seq1["opportunity"] + seq2["opportunity"]) / 2,
                          "usage": (seq1["usage"] + seq2["usage"]) / 2,
                          "sum": (seq1["opportunity"] + seq1["usage"]
                                  + seq2["opportunity"] + seq2["usage"]) / 2},
        }
    # 配对分解：逐局用精确恒等式 C_强−C_我 = u_强·ΔO + O_我·Δu 后取均值，
    # 与 PREREG 第 5 节的局内配对统计同口径（−0.183 就是这一口径）。
    paired_parts = []
    keys = []
    for row in rounds_with_elite:
        agg = {}
        for group in GROUPS:
            # 与 PREREG 第 5 节的「局内组均值」同口径：先按组取座均值，
            # 才能与 −0.183 那条配对差对齐（我方恒 1 座、强手 1—3 座，
            # 用求和会把组规模混进分解）。
            seats = [seat for seat in row["seats"] if seat["group"] == group]
            if not seats:
                agg[group] = None
                continue
            agg[group] = (statistics.fmean(seat["claims"] for seat in seats),
                          statistics.fmean(seat["opp_a"] for seat in seats))
        if agg["me"] is None or agg["elite"] is None:
            continue
        (c_me, o_me), (c_el, o_el) = agg["me"], agg["elite"]
        if not o_me or not o_el:
            continue
        u_me, u_el = c_me / o_me, c_el / o_el
        d_o = o_el - o_me
        paired_parts.append({
            "total": c_el - c_me,
            "seq1_opportunity": u_el * d_o,
            "seq1_usage": o_me * (u_el - u_me),
            "seq2_opportunity": u_me * d_o,
            "seq2_usage": o_el * (u_el - u_me),
        })
        keys.append(row["room"])
    paired_decomposition = {name: SL.cluster_ci([part[name] for part in paired_parts], keys)
                            for name in ("total", "seq1_opportunity", "seq1_usage",
                                         "seq2_opportunity", "seq2_usage")}
    paired_decomposition["rounds_defined"] = len(keys)
    # 暗杠桥接：终局副露 = 鸣牌次数 + 暗杠数（补杠不改副露数）。
    an_gang_paired = metric_report("an_gang", "暗杠数", lambda seat: seat["an_gang"],
                                   rounds_with_elite)["paired_me_minus_elite"]["cluster"]
    paired_decomposition["an_gang"] = an_gang_paired
    print()
    print("== Q3 配对分解（逐局精确恒等式后取均值；方向：强手 − 我方）")
    print("  Δ鸣牌次数(配对) = 机会项 + 使用率项 = %s + %s = %s（定义局 %d）"
          % (fmt(paired_decomposition["seq1_opportunity"]["mean"]),
             fmt(paired_decomposition["seq1_usage"]["mean"]),
             fmt(paired_decomposition["total"]["mean"]), len(keys)))
    print("    机会项 CI [%s, %s]；使用率项 CI [%s, %s]；总差 CI [%s, %s]"
          % (fmt(paired_decomposition["seq1_opportunity"]["lo"]),
             fmt(paired_decomposition["seq1_opportunity"]["hi"]),
             fmt(paired_decomposition["seq1_usage"]["lo"]),
             fmt(paired_decomposition["seq1_usage"]["hi"]),
             fmt(paired_decomposition["total"]["lo"]),
             fmt(paired_decomposition["total"]["hi"])))
    print("    另一种归属：机会项 %s（u_我·ΔO），使用率项 %s（O_强·Δu），和 %s"
          % (fmt(paired_decomposition["seq2_opportunity"]["mean"]),
             fmt(paired_decomposition["seq2_usage"]["mean"]),
             fmt(paired_decomposition["total"]["mean"])))
    print("    暗杠数配对差（我−强）%s [%s, %s]；Δ终局副露 ≈ Δ鸣牌 + Δ暗杠 的桥接见结果文档"
          % (fmt(an_gang_paired["mean"]), fmt(an_gang_paired["lo"]),
             fmt(an_gang_paired["hi"])))

    bridge = {"d_melds": reports["melds_end"]["paired_me_minus_elite"]["cluster"]["mean"],
              "d_claims": reports["claims"]["paired_me_minus_elite"]["cluster"]["mean"],
              "paired_decomposition": paired_decomposition}
    print()
    print("== Q3 分解（方向：强手 − 我方；主语料、含强手的局）")
    for tag, item in decomposition.items():
        print("%s：Δ机会=%+.4f  Δ结果=%+.4f  u_我=%.4f u_强=%.4f  O_我=%.4f O_强=%.4f"
              % (tag, item["d_opportunity"], item["d_outcome"],
                 item["u_me"], item["u_elite"], item["O_me"], item["O_elite"]))
        print("    式1 = u_强*ΔO + O_我*Δu = %+.4f + %+.4f = %+.4f"
              % (item["sequential_1"]["opportunity"], item["sequential_1"]["usage"],
                 item["sequential_1"]["sum"]))
        print("    式2 = u_我*ΔO + O_强*Δu = %+.4f + %+.4f = %+.4f"
              % (item["sequential_2"]["opportunity"], item["sequential_2"]["usage"],
                 item["sequential_2"]["sum"]))
        print("    对称 = %+.4f + %+.4f = %+.4f"
              % (item["symmetric"]["opportunity"], item["symmetric"]["usage"],
                 item["symmetric"]["sum"]))
    print("桥接：Δ终局副露数(配对，我-强) = %+.4f，Δ鸣牌次数(配对) = %+.4f"
          % (bridge["d_melds"], bridge["d_claims"]))

    json.dump({"reports": reports, "decomposition": decomposition, "bridge": bridge,
               "window_audit": dict(window_audit),
               "equality": {k: v for k, v in equality.items() if k != "details"},
               "checks": checks},
              (_project_file(_PROJECT_ROOT, OUT / "q1-q4.json")).open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    json.dump(equality, (_project_file(_PROJECT_ROOT, OUT / "equality.json")).open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    json.dump(dict(window_audit), (_project_file(_PROJECT_ROOT, OUT / "window-audit.json")).open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)

    write_manual(verbose_targets, board, rounds_with_elite)

    bad = [path for path in READ_PATHS
           if "events.json" not in path and "leaderboard-week.json" not in path
           and "rounds.jsonl" not in path]
    print()
    print("泄漏检查：读取路径 %d 条，非官方牌谱/公开榜单/既有重建产物者 %d 条 -> %s"
          % (len(READ_PATHS), len(bad), "通过" if not bad else "**失败**"))
    assert not bad, bad
    print("总用时 %.1f 秒" % (time.time() - started))
    return 0


def write_manual(targets, board, rounds_with_elite):
    """按 PREREG 第 9.5 节的条件抽 3 局，输出人可读的机会/鸣牌逐条明细。"""

    ordered = sorted(targets, key=lambda item: (item[0], item[1], item[2]))
    picked = []
    circle = [item for item in ordered if item[0] == "with_circle"]
    if circle:
        picked.append(("含圈（弃白）且发生鸣牌", circle[0]))

    def seat_mean(row, group, key):
        values = [seat[key] for seat in row["seats"] if seat["group"] == group]
        return statistics.fmean(values) if values else 0.0

    gap = sorted(rounds_with_elite,
                 key=lambda row: -(seat_mean(row, "me", "melds_end")
                                   - seat_mean(row, "elite", "melds_end")))
    if gap:
        row = gap[0]
        match = [item for item in ordered
                 if item[1] == row["game_id"] and item[2] == row["round_no"]]
        if match:
            picked.append(("我方与强手同局且副露差最大", match[0]))

    rng = random.Random(20260926)
    ordered_rows = sorted(rounds_with_elite, key=lambda row: row["game_id"])
    if ordered_rows:
        row = ordered_rows[rng.randrange(len(ordered_rows))]
        match = [item for item in ordered
                 if item[1] == row["game_id"] and item[2] == row["round_no"]]
        if match and match[0] not in [item for _, item in picked]:
            picked.append(("随机 seed=20260926 一局", match[0]))

    lines = ["# C23 人工核对：机会 / 实际鸣牌 逐条明细", "",
             "口径见 C23-PREREG-CLAIM-OPPORTUNITY.md 第 4 节：窗口成员由规则推导，",
             "机会由 hangma.action_families 判定。轨迹行只作参考——平台在有人鸣牌时",
             "会先发鸣牌事件，其余响应事件不再补齐。", ""]
    for label, (tag, game_id, round_no, events, start_hands, users) in picked:
        summary, audit, verbose = scan_round(events, start_hands, verbose=True)
        groups = []
        for user in users:
            groups.append("我方" if user == AL.ME else ("强手" if user in board else "其他"))
        lines.append("## %s：%s 第 %d 局" % (label, game_id, round_no))
        lines.append("")
        lines.append("座位：%s" % "；".join(
            "%d=%s(%s)" % (seat, users[seat], groups[seat]) for seat in range(4)))
        lines.append("")
        lines.append("终局副露 %s；鸣牌次数 %s；机会数A %s；碰机会 %s；吃机会 %s；明杠机会 %s"
                     % (summary["melds_end"], summary["claims"], summary["opp_a"],
                        summary["opp_a_peng"], summary["opp_a_chi"],
                        summary["opp_a_gang"]))
        lines.append("")
        lines.append(FENCE + "text")
        lines.extend(verbose)
        lines.append(FENCE)
        lines.append("")
    (_project_file(_PROJECT_ROOT, OUT / "manual-verify-3rounds.md")).write_text("\n".join(lines), encoding="utf-8")
    print("人工核对明细写入 %s（%d 局）"
          % (_project_file(_PROJECT_ROOT, OUT / "manual-verify-3rounds.md"), len(picked)))


if __name__ == "__main__":
    raise SystemExit(main())
