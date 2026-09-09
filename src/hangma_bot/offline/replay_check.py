"""历史核对公开入口：check_hand（parallel-v1 契约 §6 冻结）。

输入为统一牌谱文件（hands.jsonl）的单局行与 HangmaRules；输出
hand_id/status/checked_events/issues。纯函数：不读文件、不改 hand。

核对能力（按能力核对口径，缺必要事实为 not_checked、真实规则冲突为
failed；每个 issue 带 seq（无事件时 null）、code、detail、source_refs）：

- 结构：replay_schema_version、hand_id、events、四家起手与庄家；
- 重放一致性：按事件推进四家暗牌/副露/牌河与回合流转，弃牌与副露必须
  取自手牌（牌张守恒）、动作必须通过同一 HangmaRules.analyze 的合法性
  复核（单一规则源，不在核对器中另写第二套规则）；
- 结果对拍：官方胡牌处引擎必须产生 hu 候选；官方 fan/detail 与四家积分
  增量用同一 settlement 规则重算比对（链/piao/爆头从事件流精确重建）；
- 流局：有初始牌墙时核对可摸区耗尽（tile_drawn 事件计数）；无墙时流局
  成因不可核对 → not_checked（契约向量 full-history-without-wall）；
- 事件流形态：timeout(kind=discard) 是自动出牌通知，与相邻同座位
  tile_discarded 成对不重复推进；pass/timeout(response) 按窗口归属推进；
  未知事件类型无法核对 → not_checked。

官方依据：历史 v14/v15 夹具保留；v26 圈主响应按 2026-09-09 抓取的
v27 指南对齐。旧/未标版本牌谱允许已观察到的圈内直接摸牌时序，并标记兼容。
"""

from __future__ import annotations

from typing import List, Mapping, Optional, Tuple

from hangma_bot.hangma import hand_analysis, settlement
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.observation_rules import enrich_observation
from hangma_bot.hangma.progression import (
    baotou_after_draw,
    chain_after_discard,
    chain_after_gang,
    recompute_baotou,
)
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RulePublicState,
)

_WEALTH = "白"
_RESERVE_TILES = 20

_CONFLICT_PREFIX = "conflict."


class _Seat:
    """核对器的座位影子状态；hand 不含当前摸牌（与推进模型同口径）。"""

    def __init__(self) -> None:
        self.hand: List[str] = []
        self.melds: List[dict] = []
        self.discards: List[str] = []
        self.drawn: Optional[str] = None
        self.catch_play = False
        self.chain_count = 0
        self.chain_piao = 0
        self.baotou = False


def _issue(seq, code: str, detail: str, source_refs=None) -> dict:
    return {
        "seq": seq,
        "code": code,
        "detail": detail,
        "source_refs": list(source_refs or []),
    }


def _remove_one(hand: List[str], code: str) -> bool:
    for index, held in enumerate(hand):
        if held == code:
            del hand[index]
            return True
    return False


def _remove_up_to(hand: List[str], code: str, count: int) -> Tuple[List[str], int]:
    """移除至多 count 张同码牌，返回 (剩余手牌, 实际移除数)。"""
    kept = []
    removed = 0
    for held in hand:
        if removed < count and held == code:
            removed += 1
        else:
            kept.append(held)
    return kept, removed


def _canonical_sorted(codes) -> Tuple[str, ...]:
    return tuple(sorted(codes, key=lambda code: CANONICAL_TILE_ORDER.index(code)))


def _meld_to_public(meld: dict, seat: int) -> PublicMeld:
    return PublicMeld(
        seat=seat,
        kind=meld["kind"],
        tiles=tuple(Tile(code) for code in meld["tiles"]),
        from_seat=meld.get("from_seat"),
    )


def check_hand(hand: Mapping[str, object], rules: HangmaRules) -> dict[str, object]:
    """按已记录抽牌与真实动作核对单局行；不读文件、不改 hand。

    返回：hand_id / status(passed|failed|not_checked) / checked_events /
    issues。结构或来源不足 → not_checked；实际规则冲突 → failed。
    """
    issues: List[dict] = []
    hand_id = hand.get("hand_id") if isinstance(hand, Mapping) else None
    if not isinstance(hand, Mapping):
        return _result(hand_id, "not_checked", 0, [
            _issue(None, "not_checked.initial_missing", "hand 不是 Mapping，无法核对"),
        ])
    if not isinstance(hand_id, str) or not hand_id:
        issues.append(_issue(None, "not_checked.hand_id_missing", "缺少 hand_id"))
    replay_version = hand.get("replay_schema_version")
    if replay_version != 1:
        return _result(hand_id, "not_checked", 0, issues + [
            _issue(None, "not_checked.unknown_replay_version",
                   "replay_schema_version 必须是 1，得到 {0!r}".format(replay_version)),
        ])
    events = hand.get("events")
    if not isinstance(events, list) or not events:
        return _result(hand_id, "not_checked", 0, issues + [
            _issue(None, "not_checked.events_missing", "缺少事件数组"),
        ])
    guide_version = hand.get("guide_version")
    owner_windows = isinstance(guide_version, int) and not isinstance(guide_version, bool) and guide_version >= 26
    # 规则配置一致性：缺失为 not_checked，不一致为 failed。
    rule_config = hand.get("rule_config")
    if isinstance(rule_config, Mapping):
        expected = {
            "ruleset_version": rules.config.ruleset_version,
            "base_score": rules.config.base_score,
            "you_cai_bi_kao": rules.config.you_cai_bi_kao,
        }
        if dict(rule_config) != expected:
            issues.append(_issue(None, "conflict.rule_config_conflict",
                "rule_config 与核对规则配置不一致：{0} != {1}".format(dict(rule_config), expected)))
    else:
        issues.append(_issue(None, "not_checked.rule_config_missing",
            "单局行缺少 rule_config；按调用方规则配置核对（结果依赖该配置）"))
    # 起手与庄家。
    initial = hand.get("initial") if isinstance(hand.get("initial"), Mapping) else {}
    hands_raw = initial.get("hands")
    dealer_raw = initial.get("dealer_seat")
    if (
        not isinstance(hands_raw, list)
        or len(hands_raw) != 4
        or not all(isinstance(row, list) for row in hands_raw)
    ):
        return _result(hand_id, "not_checked", 0, issues + [
            _issue(None, "not_checked.initial_missing", "缺少四家起手手牌，无法重放"),
        ])
    if isinstance(dealer_raw, bool) or not isinstance(dealer_raw, int) or not 0 <= dealer_raw <= 3:
        return _result(hand_id, "not_checked", 0, issues + [
            _issue(None, "not_checked.dealer_missing", "缺少合法庄家座位（0-3）"),
        ])
    dealer = dealer_raw
    # 局号与场次身份：观察投影取真实值（缺局号按 not_checked 口径回退 1）。
    round_no = hand.get("round_no")
    if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
        issues.append(_issue(None, "not_checked.round_no_missing",
            "缺少正整数 round_no（观察投影回退为 1）"))
        round_no = 1
    game_key = hand.get("game_key")
    game_id = hand_id or "check"
    if isinstance(game_key, Mapping):
        raw_game_id = game_key.get("game_id")
        if isinstance(raw_game_id, str) and raw_game_id:
            game_id = raw_game_id
    for row in hands_raw:
        for code in row:
            if code not in CANONICAL_TILE_ORDER:
                return _result(hand_id, "failed", 0, issues + [
                    _issue(None, "conflict.unknown_tile_code", "起手含未知牌码 {0!r}".format(code)),
                ])
    seats = [_Seat() for _ in range(4)]
    for seat_no, row in enumerate(hands_raw):
        seats[seat_no].hand = list(row)
        # 闲家起手已任意听时，首次摸牌前的吃碰杠也须继承；庄家直抽在下方处理。
        if len(row) == 13:
            seats[seat_no].baotou = recompute_baotou(
                tuple(Tile(code) for code in row), 0, row.count(_WEALTH),
            )
    if len(seats[dealer].hand) >= 14:
        seats[dealer].drawn = seats[dealer].hand.pop()
        seats[dealer].baotou = baotou_after_draw(
            False, tuple(Tile(code) for code in seats[dealer].hand), 0,
            Tile(seats[dealer].drawn), replacement=False,
        )
    wall_raw = initial.get("wall")
    wall_known = isinstance(wall_raw, list) and wall_raw
    wall_drawable = len(wall_raw) - _RESERVE_TILES if wall_known else None
    consumed = 0
    scores_before = hand.get("scores_before")
    scores_after = hand.get("scores_after")

    # 回合流转状态机。
    window = ("discard", dealer)  # 庄家直抽窗口（官方 v10：无摸牌事件）
    last_discard = None  # (discarder, tile, seq)
    round_seen = False
    done = False
    previous_seq = None
    processed = 0
    event_index = 0
    history: List[dict] = []  # 已处理事件（构造公开历史用）
    while event_index < len(events):
        event = events[event_index]
        if not isinstance(event, Mapping):
            issues.append(_issue(None, "not_checked.event_shape", "事件不是对象"))
            break
        seq = event.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int):
            issues.append(_issue(None, "conflict.seq_missing", "事件缺少整数 seq"))
            break
        if previous_seq is not None and seq <= previous_seq:
            issues.append(_issue(seq, "conflict.seq_not_increasing",
                "事件 seq 未严格递增（{0} 之后为 {1}）".format(previous_seq, seq)))
            break
        previous_seq = seq
        kind = event.get("type")
        seat_no = event.get("seat")
        tile = event.get("tile") or ""
        data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
        source_refs = event.get("source_refs")
        processed += 1
        if kind == "timeout" and data.get("kind") == "discard":
            # 自动出牌通知：与相邻同座位 tile_discarded 成对，不重复推进。
            prev_event = events[event_index - 1] if event_index > 0 else None
            next_event = events[event_index + 1] if event_index + 1 < len(events) else None
            paired_prev = (
                isinstance(prev_event, Mapping)
                and prev_event.get("type") == "tile_discarded"
                and prev_event.get("seat") == seat_no
            )
            paired_next = (
                isinstance(next_event, Mapping)
                and next_event.get("type") == "tile_discarded"
                and next_event.get("seat") == seat_no
            )
            if not paired_prev and not paired_next:
                issues.append(_issue(seq, "conflict.timeout_discard_unpaired",
                    "timeout(kind=discard) 没有相邻的同座位 tile_discarded，无法定位自动出牌"))
            history.append(dict(event))
            event_index += 1
            continue
        if kind == "timeout" and data.get("kind") == "response":
            kind = "pass"  # 响应超时=自动过（指南 2.1 超时兜底口径）
        if kind == "tile_drawn":
            if (not owner_windows and isinstance(window, tuple)
                    and window[0] in ("peng_window", "chi_window")
                    and any(s.catch_play for s in seats) and seat_no == (window[1] + 1) % 4):
                # v24 实测圈内直接摸牌。只兼容旧/未知版本已发生的轨迹，不能
                # 据此让 v26 新牌谱跳过响应，也不改写保存的版本或事件。
                window, last_discard = ("draw", seat_no), None
                issues.append(_issue(seq, "info.legacy_catch_play_window",
                    "旧/未标版本牌谱圈内直接摸牌，按历史平台时序核对"))
            if not (isinstance(window, tuple) and window[0] == "draw" and window[1] == seat_no):
                issues.append(_issue(seq, "conflict.event_out_of_turn",
                    "tile_drawn 出现在非该座位摸牌阶段（当前窗口 {0!r}）".format(window)))
                break
            if tile not in CANONICAL_TILE_ORDER:
                issues.append(_issue(seq, "conflict.unknown_tile_code", "摸牌事件未知牌码 {0!r}".format(tile)))
                break
            # hand 恒为「不含当前摸牌」的暗牌：摸牌只置 drawn（与推进模型同口径）。
            seats[seat_no].drawn = tile
            # 明确事件字段优先；旧牌谱只有连续相邻本人杠→摸才能确认杠补。
            # 缺前史时不把“没有看见杠”解释成普通摸牌。
            replacement = data.get("gang_replenish")
            if not isinstance(replacement, bool):
                previous = history[-1] if history else None
                replacement = None
                if previous is not None and previous.get("seq") == seq - 1:
                    if previous.get("type") == "gang":
                        replacement = previous.get("seat") == seat_no
                    elif previous.get("type") in ("pass", "tile_discarded", "tile_drawn") or (
                        previous.get("type") == "timeout"
                        and isinstance(previous.get("data"), Mapping)
                        and previous["data"].get("kind") == "response"
                    ):
                        replacement = False
            try:
                seats[seat_no].baotou = baotou_after_draw(
                    seats[seat_no].baotou, tuple(Tile(c) for c in seats[seat_no].hand),
                    len(seats[seat_no].melds), Tile(tile), replacement=replacement,
                )
            except ValueError as error:
                issues.append(_issue(seq, "not_checked.baotou_draw_source", str(error)))
                break
            consumed += 1
            window = ("discard", seat_no)
            history.append(dict(event))
        elif kind == "tile_discarded":
            if not (isinstance(window, tuple) and window[0] == "discard" and window[1] == seat_no):
                issues.append(_issue(seq, "conflict.event_out_of_turn",
                    "tile_discarded 出现在非该座位出牌阶段（当前窗口 {0!r}）".format(window)))
                break
            if any(s.catch_play for s in seats) and not _validate_via_analyze(
                rules, issues, seats, seat_no, "draw", (), None, history,
                wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id,
                seq, _key_of("discard", tile),
            ):
                break
            combined = list(seats[seat_no].hand)
            if seats[seat_no].drawn is not None:
                combined.append(seats[seat_no].drawn)
            if not _remove_one(combined, tile):
                issues.append(_issue(seq, "conflict.discard_not_in_hand",
                    "座位 {0} 弃牌 {1} 不在其暗牌中".format(seat_no, tile)))
                break
            seats[seat_no].hand = combined
            seats[seat_no].drawn = None
            seats[seat_no].discards.append(tile)
            seats[seat_no].catch_play = tile == _WEALTH
            if tile == _WEALTH:
                for other_seat, other in enumerate(seats):
                    if other_seat != seat_no:
                        other.catch_play = False
            chain_count, chain_piao = chain_after_discard(
                seats[seat_no].chain_count, seats[seat_no].chain_piao,
                seats[seat_no].baotou, Tile(tile),
            )
            seats[seat_no].chain_count, seats[seat_no].chain_piao = chain_count, chain_piao
            # 飘的计数使用动作前爆头；弃后完整暗牌决定下一听牌态。
            seats[seat_no].baotou = recompute_baotou(
                tuple(Tile(code) for code in combined), len(seats[seat_no].melds),
                combined.count(_WEALTH),
            )
            history.append(dict(event))
            if tile == _WEALTH:
                # 弃白本身不开响应窗口（v14 夹具 4/4：下一事件直接是下家摸牌）。
                window = ("draw", (seat_no + 1) % 4)
            else:
                owners = {index for index, other in enumerate(seats) if other.catch_play}
                responders = owners if owner_windows and owners else {index for index in range(4) if index != seat_no}
                window = ("peng_window", seat_no, tile, seq, responders)
                last_discard = (seat_no, tile, seq)
        elif kind == "pass":
            owner = next((index for index, other in enumerate(seats) if other.catch_play), None)
            ok, window, last_discard = _apply_pass(
                issues, window, last_discard, seat_no, seq, owner if owner_windows else None)
            if not ok:
                break
            history.append(dict(event))
        elif kind in ("peng", "chi", "gang"):
            ok, window, last_discard, seats = _apply_meld(
                rules, issues, seats, window, last_discard, kind, seat_no, tile, data, seq,
                history, wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id,
            )
            if not ok:
                break
            history.append(dict(event))
        elif kind == "round_ended":
            round_seen = True
            ok, done = _verify_round_ended(
                rules, issues, seats, window, seat_no, data, seq, history,
                dealer, scores_before, scores_after, wall_known, wall_drawable, consumed, hand_id,
                round_no, game_id,
            )
            if not ok:
                break
        elif kind == "game_ended":
            final_scores = data.get("final_scores") if isinstance(data, Mapping) else None
            if scores_after is not None and final_scores is not None:
                if list(scores_after) != list(final_scores):
                    issues.append(_issue(seq, "conflict.game_ended_mismatch",
                        "game_ended.final_scores 与 scores_after 不一致：{0} != {1}".format(
                            final_scores, scores_after)))
            done = True
        else:
            issues.append(_issue(seq, "not_checked.unknown_event_kind",
                "未知事件类型 {0!r}，事件流完整性无法保证".format(kind)))
        event_index += 1

    if not round_seen:
        issues.append(_issue(None, "not_checked.round_ended_missing", "事件流未包含 round_ended"))
    status = _status_from_issues(issues)
    return _result(hand_id, status, processed, issues)


def _result(hand_id, status: str, checked_events: int, issues: List[dict]) -> dict:
    return {
        "hand_id": hand_id,
        "status": status,
        "checked_events": checked_events,
        "issues": issues,
    }


def _status_from_issues(issues: List[dict]) -> str:
    if any(issue["code"].startswith(_CONFLICT_PREFIX) for issue in issues):
        return "failed"
    if any(issue["code"].startswith("not_checked.") for issue in issues):
        return "not_checked"
    return "passed"


def _apply_pass(issues, window, last_discard, seat_no, seq, owner_seat=None):
    """pass/timeout(response) 推进；返回 (ok, window, last_discard)。"""
    if not isinstance(window, tuple) or window[0] not in ("peng_window", "chi_window"):
        issues.append(_issue(seq, "conflict.event_out_of_turn",
            "pass 出现在非响应窗口（当前 {0!r}）".format(window)))
        return False, window, last_discard
    kind, discarder, tile, seq0, responders = window
    if seat_no not in responders:
        issues.append(_issue(seq, "info.pass_after_window_closed",
            "座位 {0} 的 pass 出现在已关闭/非成员窗口，忽略（兼容重复通知）".format(seat_no)))
        return True, window, last_discard
    responders = set(responders)
    responders.discard(seat_no)
    if kind == "peng_window" and responders:
        return True, ("peng_window", discarder, tile, seq0, responders), last_discard
    if kind == "peng_window":
        # 碰窗口全过 → 吃窗口对下家开放（官方 v15：碰窗口先于吃窗口）。
        next_seat = (discarder + 1) % 4
        if owner_seat is not None and owner_seat != next_seat:
            return True, ("draw", next_seat), None
        return True, ("chi_window", discarder, tile, seq0, {next_seat}), last_discard
    if responders:
        return True, ("chi_window", discarder, tile, seq0, responders), last_discard
    return True, ("draw", (discarder + 1) % 4), None


def _apply_meld(
    rules, issues, seats, window, last_discard, kind, seat_no, tile, data, seq,
    history, wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id,
):
    """碰/吃/杠推进：合法性复核 + 牌张移动；返回 (ok, window, last_discard, seats)。"""
    seat = seats[seat_no]
    if kind == "peng":
        if not isinstance(window, tuple) or window[0] != "peng_window" or seat_no not in window[4]:
            issues.append(_issue(seq, "conflict.event_out_of_turn",
                "peng 出现在非碰窗口（当前 {0!r}）".format(window)))
            return False, window, last_discard, seats
        discarder, discard_tile = window[1], window[2]
        if tile != discard_tile:
            issues.append(_issue(seq, "conflict.meld_tile_mismatch",
                "peng 牌 {0} 与触发弃牌 {1} 不一致".format(tile, discard_tile)))
            return False, window, last_discard, seats
        legal = _validate_via_analyze(
            rules, issues, seats, seat_no, "response_peng", window[4],
            last_discard, history, wall_known, wall_drawable, consumed, hand_id,
            dealer, round_no, game_id, seq,
            _key_of("peng", tile),
        )
        if legal is False:
            return False, window, last_discard, seats
        for _ in range(2):
            if not _remove_one(seat.hand, tile):
                issues.append(_issue(seq, "conflict.meld_missing_tiles",
                    "peng {0} 暗牌不足 2 张".format(tile)))
                return False, window, last_discard, seats
        seat.drawn = None
        seat.melds.append({
            "kind": "peng", "tiles": [tile, tile, tile], "from_seat": discarder,
        })
        return True, ("discard", seat_no), None, seats
    if kind == "chi":
        if not isinstance(window, tuple) or window[0] != "chi_window" or seat_no not in window[4]:
            issues.append(_issue(seq, "conflict.event_out_of_turn",
                "chi 出现在非吃窗口（当前 {0!r}）".format(window)))
            return False, window, last_discard, seats
        discarder, discard_tile = window[1], window[2]
        tiles_raw = data.get("tiles") if isinstance(data, Mapping) else None
        if not isinstance(tiles_raw, list) or len(tiles_raw) != 3:
            issues.append(_issue(seq, "conflict.meld_shape", "chi 事件缺少三张 tiles"))
            return False, window, last_discard, seats
        chi_tiles = _canonical_sorted(list(tiles_raw))
        if discard_tile not in chi_tiles:
            issues.append(_issue(seq, "conflict.meld_tile_mismatch",
                "chi 组合不含触发弃牌 {0}".format(discard_tile)))
            return False, window, last_discard, seats
        legal = _validate_via_analyze(
            rules, issues, seats, seat_no, "response_chi", window[4],
            last_discard, history, wall_known, wall_drawable, consumed, hand_id,
            dealer, round_no, game_id, seq,
            _key_of("chi", chi_tiles),
        )
        if legal is False:
            return False, window, last_discard, seats
        for partner in chi_tiles:
            if partner == discard_tile:
                continue
            if not _remove_one(seat.hand, partner):
                issues.append(_issue(seq, "conflict.meld_missing_tiles",
                    "chi 组合缺手牌 {0}".format(partner)))
                return False, window, last_discard, seats
        seat.drawn = None
        seat.melds.append({
            "kind": "chi", "tiles": list(chi_tiles), "from_seat": discarder,
        })
        return True, ("discard", seat_no), None, seats
    # gang：an/ming/bu。
    gang_kind = data.get("kind") if isinstance(data, Mapping) else None
    if gang_kind not in ("an", "ming", "bu"):
        issues.append(_issue(seq, "conflict.meld_shape",
            "gang 事件缺少合法 kind（an/ming/bu），得到 {0!r}".format(gang_kind)))
        return False, window, last_discard, seats
    if gang_kind == "ming":
        if not isinstance(window, tuple) or window[0] != "peng_window" or seat_no not in window[4]:
            issues.append(_issue(seq, "conflict.event_out_of_turn",
                "明杠出现在非碰窗口（当前 {0!r}）".format(window)))
            return False, window, last_discard, seats
        discarder, discard_tile = window[1], window[2]
        if tile != discard_tile:
            issues.append(_issue(seq, "conflict.meld_tile_mismatch",
                "明杠牌 {0} 与触发弃牌 {1} 不一致".format(tile, discard_tile)))
            return False, window, last_discard, seats
        if not wall_known:
            issues.append(_issue(seq, "not_checked.gang_wall_boundary",
                "牌墙未知，明杠的最后 10 墩禁杠边界无法核对（仅做结构核对）"))
        else:
            legal = _validate_via_analyze(
                rules, issues, seats, seat_no, "response_peng", window[4],
                last_discard, history, wall_known, wall_drawable, consumed, hand_id,
                dealer, round_no, game_id, seq,
                _key_of("gang:exposed", tile),
            )
            if legal is False:
                return False, window, last_discard, seats
        for _ in range(3):
            if not _remove_one(seat.hand, tile):
                issues.append(_issue(seq, "conflict.meld_missing_tiles",
                    "明杠 {0} 暗牌不足 3 张".format(tile)))
                return False, window, last_discard, seats
        seat.drawn = None
        seat.chain_count, seat.chain_piao = chain_after_gang(seat.chain_count, seat.chain_piao)
        seat.melds.append({
            "kind": "gang", "gang_kind": "ming",
            "tiles": [tile, tile, tile, tile], "from_seat": discarder,
        })
        return True, ("draw", seat_no), None, seats
    # an / bu：本人摸牌窗口。
    if not isinstance(window, tuple) or window[0] != "discard" or window[1] != seat_no:
        issues.append(_issue(seq, "conflict.event_out_of_turn",
            "暗杠/补杠出现在非本人出牌阶段（当前 {0!r}）".format(window)))
        return False, window, last_discard, seats
    if not wall_known:
        issues.append(_issue(seq, "not_checked.gang_wall_boundary",
            "牌墙未知，杠的最后 10 墩禁杠边界无法核对（仅做结构核对）"))
    else:
        legal = _validate_via_analyze(
            rules, issues, seats, seat_no, "draw", (seat_no,),
            last_discard, history, wall_known, wall_drawable, consumed, hand_id,
            dealer, round_no, game_id, seq,
            _key_of("gang:" + ("concealed" if gang_kind == "an" else "added"), tile),
        )
        if legal is False:
            return False, window, last_discard, seats
    combined = list(seat.hand)
    if seat.drawn is not None:
        combined.append(seat.drawn)
    if gang_kind == "bu":
        peng_index = None
        for index, meld in enumerate(seat.melds):
            if meld["kind"] == "peng" and meld["tiles"][0] == tile:
                peng_index = index
                break
        if peng_index is None:
            issues.append(_issue(seq, "conflict.meld_missing_tiles",
                "补杠 {0} 缺少既有碰副露".format(tile)))
            return False, window, last_discard, seats
        kept, removed = _remove_up_to(combined, tile, 1)
        if removed != 1:
            issues.append(_issue(seq, "conflict.meld_missing_tiles",
                "补杠 {0} 暗牌缺少第 4 张".format(tile)))
            return False, window, last_discard, seats
        seat.hand = kept
        seat.drawn = None
        old = seat.melds[peng_index]
        seat.melds[peng_index] = {
            "kind": "gang", "gang_kind": "bu",
            "tiles": [tile, tile, tile, tile], "from_seat": old.get("from_seat"),
        }
    else:
        kept, removed = _remove_up_to(combined, tile, 4)
        if removed != 4:
            issues.append(_issue(seq, "conflict.meld_missing_tiles",
                "暗杠 {0} 暗牌不足 4 张".format(tile)))
            return False, window, last_discard, seats
        seat.hand = kept
        seat.drawn = None
        seat.melds.append({
            "kind": "gang", "gang_kind": "an",
            "tiles": [tile, tile, tile, tile], "from_seat": None,
        })
    seat.chain_count, seat.chain_piao = chain_after_gang(seat.chain_count, seat.chain_piao)
    return True, ("draw", seat_no), None, seats


def _key_of(prefix: str, tile_or_tiles) -> str:
    if isinstance(tile_or_tiles, str):
        return "{0}:{1}".format(prefix, tile_or_tiles)
    return "{0}:{1}".format(prefix, ",".join(tile_or_tiles))


def _validate_via_analyze(
    rules, issues, seats, seat_no, phase, responding, last_discard, history,
    wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id, seq, expected_key,
):
    """同一 HangmaRules 复核动作合法性；返回 True/False（False=已记冲突）。"""
    observation = _shadow_observation(
        seats, seat_no, phase, responding, last_discard, history,
        wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id,
    )
    analysis = rules.analyze(observation)
    if any(candidate.action_key == expected_key for candidate in analysis.legal_candidates):
        return True
    issues.append(_issue(seq, "conflict.action_illegal",
        "动作 {0} 不在座位 {1} 的 {2} 窗口合法候选中（候选 {3} 个）".format(
            expected_key, seat_no, phase, len(analysis.legal_candidates))))
    return False


def _shadow_observation(
    seats, seat_no, phase, responding, last_discard, history,
    wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id,
) -> PlayerObservation:
    """影子状态 → PlayerObservation（他家摸牌保留事件序号，隐藏牌值）。

    dealer/round_no/game_id 取单局行真实值（缺局号已在入口按 not_checked
    口径回退），不硬编码 0/1——避免未来 analyze 消费这些字段时静默失真。
    """
    seat = seats[seat_no]
    my_hand = tuple(Tile(code) for code in seat.hand)
    drawn_tile = Tile(seat.drawn) if seat.drawn is not None else None
    discards = tuple(tuple(Tile(code) for code in s.discards) for s in seats)
    melds = tuple(
        tuple(_meld_to_public(meld, index) for meld in s.melds)
        for index, s in enumerate(seats)
    )
    hand_counts = tuple(
        len(s.hand) + (1 if s.drawn is not None else 0) for s in seats
    )
    last = None
    if last_discard is not None and phase in ("response_peng", "response_chi"):
        last = PublicDiscard(seat=last_discard[0], tile=Tile(last_discard[1]), seq=last_discard[2])
    remaining = None
    if wall_known:
        remaining = (wall_drawable - consumed) + _RESERVE_TILES
    # god 是公开全局圈标记；本人是否受限由同一 hangma 规则结合圈主决定。
    circle_active = any(s.catch_play for s in seats)
    public_history = []
    for event in history:
        event_seat = event.get("seat")
        if isinstance(event_seat, bool) or not isinstance(event_seat, int) or not 0 <= event_seat <= 3:
            event_seat = None
        tile_value = event.get("tile") or ""
        data = event.get("data") if isinstance(event.get("data"), Mapping) else {}
        masked_draw = event.get("type") == "tile_drawn" and event_seat != seat_no
        tiles = data.get("tiles") if event.get("type") == "chi" else None
        public_history.append(PublicEvent(
            seq=event["seq"],
            kind=event.get("type"),
            seat=event_seat,
            tiles=() if masked_draw else (
                tuple(Tile(code) for code in tiles) if isinstance(tiles, list)
                else (Tile(tile_value),) if tile_value else ()
            ),
            detail_kind=data.get("kind"),
            catch_play=data.get("catch_play") if isinstance(data.get("catch_play"), bool) else None,
            # 完整牌谱可能含在线他家摸牌未公开的 data，不能投影给该座位。
            gang_replenish=(data.get("gang_replenish") if not masked_draw and isinstance(data.get("gang_replenish"), bool) else None),
            response_window=data.get("window"),
        ))
    continuous = all(right.seq == left.seq + 1 for left, right in zip(public_history, public_history[1:]))
    return enrich_observation(PlayerObservation(
        game_id=game_id,
        seat=seat_no,
        round_no=round_no,
        snapshot_seq=seq_of_last(history),
        phase=phase,
        dealer_seat=dealer,
        turn_seat=seat_no if phase == "draw" else (last_discard[0] if last_discard else 0),
        responding_seats=tuple(responding),
        my_hand=my_hand,
        drawn_tile=drawn_tile,
        discards=discards,
        melds=melds,
        hand_counts=hand_counts,
        last_discard=last,
        remaining_tile_count=remaining,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile(_WEALTH),
            baotou=seat.baotou,
            chain_count=seat.chain_count,
            catch_play=circle_active,
            catch_play_owner_seat=(next((index for index, other in enumerate(seats) if other.catch_play), None)
                                   if continuous else None),
        ),
        public_history=tuple(public_history),
        consumed_seq=seq_of_last(history),
        history_complete=continuous,
        chain_piao=seat.chain_piao if continuous else None,
    ))


def seq_of_last(history) -> int:
    return history[-1]["seq"] if history else 0


def _verify_round_ended(
    rules, issues, seats, window, seat_no, data, seq, history,
    dealer, scores_before, scores_after, wall_known, wall_drawable, consumed, hand_id,
    round_no, game_id,
):
    """round_ended 对拍：胡牌重算 fan/detail/积分；流局核对牌墙耗尽。"""
    is_draw = bool(data.get("draw")) if isinstance(data, Mapping) else False
    if not is_draw:
        winner = seat_no
        if not isinstance(winner, int) or not 0 <= winner <= 3:
            issues.append(_issue(seq, "conflict.round_ended_in_wrong_state",
                "round_ended 声明胡牌但缺少 0-3 的赢家座位（seat={0!r}）".format(winner)))
            return False, True
        if not (isinstance(window, tuple) and window[0] == "discard" and window[1] == winner):
            issues.append(_issue(seq, "conflict.round_ended_in_wrong_state",
                "赢家 {0} 不在本人摸牌窗口（当前 {1!r}）".format(winner, window)))
            return False, True
        win_seat = seats[winner]
        # 引擎复核：官方胡牌处必须产生 hu 候选。
        observation = _shadow_observation(
            seats, winner, "draw", (winner,), None, history,
            wall_known, wall_drawable, consumed, hand_id, dealer, round_no, game_id,
        )
        analysis = rules.analyze(observation)
        if not any(candidate.action_key == "hu" for candidate in analysis.legal_candidates):
            issues.append(_issue(seq, "conflict.winner_hand_not_win",
                "官方胡牌处引擎未产生 hu 候选（座位 {0}）".format(winner)))
            return False, True
        concealed = tuple(Tile(code) for code in win_seat.hand)
        if win_seat.drawn is not None:
            concealed = concealed + (Tile(win_seat.drawn),)
        split = hand_analysis.win_split(concealed, len(win_seat.melds))
        if split is None:
            issues.append(_issue(seq, "conflict.winner_hand_not_win",
                "官方赢家手牌无法分解成胡牌"))
            return False, True
        fan_result = settlement.compute_fan(
            split, win_seat.chain_count, win_seat.chain_piao, win_seat.baotou
        )
        official_fan = data.get("fan")
        if isinstance(official_fan, int) and official_fan != fan_result.fan:
            issues.append(_issue(seq, "conflict.fan_mismatch",
                "官方 fan={0} != 本地重算 fan={1}".format(official_fan, fan_result.fan)))
        official_detail = data.get("detail")
        if isinstance(official_detail, list):
            if list(official_detail) != list(fan_result.details):
                issues.append(_issue(seq, "conflict.detail_mismatch",
                    "官方 detail={0} != 本地重算 detail={1}".format(
                        official_detail, list(fan_result.details))))
        recomputed_delta = settlement.settle_scores(
            fan_result.fan, rules.config.base_score, winner, dealer
        )
        official_scores = data.get("scores")
        if isinstance(official_scores, list) and len(official_scores) == 4:
            if list(official_scores) != list(recomputed_delta):
                issues.append(_issue(seq, "conflict.score_mismatch",
                    "官方 scores={0} != 本地重算增量 {1}".format(
                        official_scores, list(recomputed_delta))))
        if (
            isinstance(scores_before, list) and len(scores_before) == 4
            and isinstance(scores_after, list) and len(scores_after) == 4
        ):
            row_delta = [
                scores_after[i] - scores_before[i] for i in range(4)
            ]
            if row_delta != list(recomputed_delta):
                issues.append(_issue(seq, "conflict.score_mismatch",
                    "scores_after-scores_before={0} != 本地重算增量 {1}".format(
                        row_delta, list(recomputed_delta))))
        return True, True
    # 流局。
    if not (isinstance(window, tuple) and window[0] == "draw"):
        issues.append(_issue(seq, "conflict.round_ended_in_wrong_state",
            "流局 round_ended 出现在非待摸牌阶段（当前 {0!r}）".format(window)))
        return False, True
    if wall_known:
        remaining_drawable = wall_drawable - consumed
        if remaining_drawable > 0:
            issues.append(_issue(seq, "conflict.draw_wall_not_exhausted",
                "流局但可摸区仍余 {0} 张（初始 {1} 张，已摸 {2} 张）".format(
                    remaining_drawable, wall_drawable, consumed)))
        elif remaining_drawable < 0:
            issues.append(_issue(seq, "conflict.wall_overconsumed",
                "摸牌数超过初始可摸区（初始 {0} 张，已摸 {1} 张）".format(
                    wall_drawable, consumed)))
    else:
        issues.append(_issue(seq, "not_checked.wall_unknown_draw_cause",
            "牌墙未知，流局成因（摸完无人胡）无法核对（契约向量：缺墙 full_history 不冒充完整世界）"))
    if (
        isinstance(scores_before, list) and len(scores_before) == 4
        and isinstance(scores_after, list) and len(scores_after) == 4
    ):
        if any(scores_after[i] != scores_before[i] for i in range(4)):
            issues.append(_issue(seq, "conflict.delta_not_zero_on_draw",
                "流局但积分发生变动：{0} -> {1}".format(scores_before, scores_after)))
    return True, True
