"""离线差分测试：归档测试房间全量事件流重放 vs 引擎胡牌判定。

背景与官方依据：2026-09-04 官方测试赛（t_dee58824c308，M=10、Rounds=16）
审计显示我方 120 次自摸胡提交中 97 次被官方 409 INVALID_ACTION 拒绝。
经差分定位（见 doc/implementation/notes/rules-hu-gate-and-win-detection.md），
两个根因均落在规则引擎：

1. 缺「刚摸牌」门禁（指南变更日志 v1，2026-09-02「碰后禁止胡牌」）：
   碰/吃/杠后、下次摸牌前提交 hu 官方返回 409；引擎此前只按阶段判定。
2. 摸牌双计（官方快照 my_hand 已含刚摸的牌、又单列 drawn_tile，见
   tests/fixtures/official/captures/state-draw-phase-t_714a42392cba.json）：
   引擎把暗牌算成 15-3×副露数 张，胡牌判定「多余牌可弃」语义被幻影
   摸牌副本放宽，产生官方不认可的胡候选（七对/白板替换边界尤甚）。

本测试离线重放三个归档测试房间的最新轮场次（夹具见 tests/fixtures/hangma/，
含四家开局手牌与官方每局结算），逐次摸牌把引擎判定与官方实际结果对拍，
并把「摸牌窗口无 drawn_tile 时不产生胡候选」的门禁一起回归：

- 官方赢家摸牌处，引擎必须产生 hu 候选（不漏胡）；
- 其余每次摸牌处，引擎不得产生 hu 候选（不误报）；
- 两种官方 my_hand 形态（含摸牌/不含摸牌）判定必须一致（双计已归一化）；
- 碰/吃后、未摸牌前的出牌窗口，任何手牌形状都不得产生 hu 候选（v1 门禁）。

全部数据离线读取，测试不访问网络（hangma 模块纯净性由构造保证）。
夹具来源、指南版本与抓取日期见 tests/fixtures/hangma/README.md。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pytest

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicMeld,
    RulePublicState,
)
from hangma_bot.hangma.engine import HangmaRules


_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "hangma"
_ARCHIVE_DIR = _FIXTURE_DIR / "archived-rooms"

_ROOM_GAMES = (
    ("t_6c121bfda7e8", "t_6c121bfda7e8_r4_b0_t0", "t_6c121bfda7e8_b0.json"),
    ("t_cee1db65a074", "t_cee1db65a074_r7_b0_t0", "t_cee1db65a074_b0.json"),
    ("t_714a42392cba", "t_714a42392cba_r4_b0_t0", "t_714a42392cba_b0.json"),
)
"""三个归档房间 batch 0 解析到的最新轮场次（批次与轮次重号，指南 v4）。"""


def _rules() -> HangmaRules:
    """YouCaiBiKao=false 的规则引擎（与归档房间配置一致，见 fixture README）。"""

    return HangmaRules(
        RuleConfig(ruleset_version="test", base_score=1, you_cai_bi_kao=False)
    )


def _meld(kind: str, codes: Tuple[str, ...]) -> PublicMeld:
    return PublicMeld(
        seat=0, kind=kind, tiles=tuple(Tile(c) for c in codes), from_seat=None
    )


def _observation(
    game_id: str,
    seat: int,
    seq: int,
    my_hand: Tuple[str, ...],
    drawn: str,
    melds: Tuple[PublicMeld, ...],
) -> PlayerObservation:
    """构造摸牌窗口观察（其余座位事实留空不影响胡牌判定）。"""

    empty_melds = ((melds), (), (), ())
    return PlayerObservation(
        game_id=game_id,
        seat=seat,
        round_no=1,
        snapshot_seq=seq,
        phase="draw",
        dealer_seat=0,
        turn_seat=seat,
        responding_seats=(),
        my_hand=tuple(Tile(c) for c in my_hand),
        drawn_tile=Tile(drawn) if drawn else None,
        discards=((), (), (), ()),
        melds=empty_melds,
        hand_counts=(14, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )


class _Replayer:
    """把一场归档场次的事件流重放成 (摸牌窗口, 官方结果) 序列。"""

    def __init__(self, path: Path):
        self.doc = json.loads(path.read_text(encoding="utf-8"))
        self.game_id = self.doc["game_id"]
        self.blocks = self.doc["blocks"]
        first = self.blocks[0]
        self.start_hands: List[List[str]] = [list(h) for h in first["start_hands"]]
        self.dealer: int = first.get("dealer", 0)
        self.official_wins: List[Tuple[int, int, Dict]] = []

    def events(self):
        for block in self.blocks:
            yield from block["events"]

    def replay(self):
        """产出 [(seq, seat, concealed_incl_drawn, drawn, melds)]，按事件推进。

        胜家摸牌窗口的 seq 由 round_ended 回推（该座位在该局结束前
        最后一次摸牌），调用方据此逐窗口对拍官方结果。
        """

        hands = [list(h) for h in self.start_hands]
        melds: List[List[PublicMeld]] = [[] for _ in range(4)]
        windows = []
        winning_draw_seqs = set()
        # 庄家首局「发牌直抽」：第 14 张已含在 start_hands，无 tile_drawn 事件
        # （指南 v10）；该窗口 drawn_tile 官方照常单列（2026-09-04 实测）。
        concealed = list(hands[self.dealer])
        windows.append((0, self.dealer, concealed[:], concealed[-1], tuple(melds[self.dealer])))
        for event in self.events():
            kind = event["type"]
            seat = event["seat"]
            tile = event["tile"]
            if kind == "tile_drawn":
                hands[seat].append(tile)
                windows.append(
                    (event["seq"], seat, list(hands[seat]), tile, tuple(melds[seat]))
                )
            elif kind == "tile_discarded":
                if tile in hands[seat]:
                    hands[seat].remove(tile)
                else:
                    raise AssertionError(
                        "重放失败：弃牌 {0} 不在座位 {1} 手牌中（seq {2}）".format(
                            tile, seat, event["seq"],
                        )
                    )
            elif kind == "chi":
                data = event.get("data") or {}
                meld_tiles = data.get("tiles") or [tile]
                for code in meld_tiles:
                    if code == tile:
                        continue
                    if code in hands[seat]:
                        hands[seat].remove(code)
                    else:
                        raise AssertionError("重放失败：吃牌缺手牌 {0}".format(code))
                melds[seat].append(_meld("chi", tuple(meld_tiles)))
                # 吃后、未摸牌前的出牌窗口：v1 门禁回归点。
                windows.append(
                    (event["seq"], seat, list(hands[seat]), "", tuple(melds[seat]))
                )
            elif kind == "peng":
                for _ in range(2):
                    if tile in hands[seat]:
                        hands[seat].remove(tile)
                    else:
                        raise AssertionError("重放失败：碰缺手牌 {0}".format(tile))
                melds[seat].append(_meld("peng", (tile, tile, tile)))
                # 碰后、未摸牌前的出牌窗口：v1 门禁回归点。
                windows.append(
                    (event["seq"], seat, list(hands[seat]), "", tuple(melds[seat]))
                )
            elif kind == "gang":
                data = event.get("data")
                gang_kind = data.get("kind") if isinstance(data, dict) else None
                if gang_kind == "bu":
                    if tile in hands[seat]:
                        hands[seat].remove(tile)
                elif gang_kind == "ming":
                    for _ in range(3):
                        if tile in hands[seat]:
                            hands[seat].remove(tile)
                    melds[seat].append(_meld("gang", (tile, tile, tile, tile)))
                else:  # an 暗杠
                    for _ in range(4):
                        if tile in hands[seat]:
                            hands[seat].remove(tile)
                    melds[seat].append(_meld("gang", (tile, tile, tile, tile)))
            elif kind == "round_ended":
                data = event.get("data") or {}
                if not data.get("draw") and seat >= 0:
                    self.official_wins.append((event["seq"], seat, data))
                    # 胜家摸牌窗口 = 该局结束前胜家最后一次摸牌（含杠上摸）。
                    for win_seq, win_seat, win_concealed, win_drawn, win_melds in reversed(windows):
                        if win_seat == seat and win_drawn:
                            winning_draw_seqs.add(win_seq)
                            break
        return windows, winning_draw_seqs


def _collect_games():
    """读取全部归档场次；缺失夹具时跳过（数据可重跑 archived_room_tools.py 刷新）。"""

    games = []
    for room_id, game_id, filename in _ROOM_GAMES:
        path = _ARCHIVE_DIR / filename
        if not path.exists():
            pytest.skip(
                "归档房间夹具缺失：{0}（运行 tests/unit/hangma/archived_room_tools.py 拉取）".format(
                    filename,
                )
            )
        doc = json.loads(path.read_text(encoding="utf-8"))
        games.append((room_id, game_id, doc))
    return games


def test_archived_room_hu_differential():
    """对拍断言：引擎判定胡 ⟺ 官方该局该座位实际胡。"""

    rules = _rules()
    checked_draws = 0
    checked_meld_windows = 0
    total_official_wins = 0
    for room_id, game_id, doc in _collect_games():
        replayer = _Replayer(_ARCHIVE_DIR / "{0}_b0.json".format(room_id))
        windows, winning_draw_seqs = replayer.replay()
        total_official_wins += len(winning_draw_seqs)
        for seq, seat, concealed, drawn, melds in windows:
            if not drawn:
                # 碰/吃后未摸牌的出牌窗口：v1「刚摸牌」门禁——任何形状都不给 hu。
                observation = _observation(
                    game_id, seat, seq, tuple(concealed), drawn, melds
                )
                analysis = rules.analyze(observation)
                assert "hu" not in [
                    c.action_key for c in analysis.legal_candidates
                ], (
                    "门禁失效：{0} seq {1} 座位 {2} 未摸牌窗口产生了 hu 候选".format(
                        game_id, seq, seat,
                    )
                )
                checked_meld_windows += 1
                continue
            # 摸牌窗口：两种官方 my_hand 形态必须给出相同判定，且与官方一致。
            official_hu = seq in winning_draw_seqs
            # 形态 A：契约形态（my_hand 不含摸牌）——从暗牌全集移除一个
            # 摸牌同码实例（同码多张时只移除一个，保持物理张数正确）。
            hand_a = list(concealed)
            for _index in range(len(hand_a) - 1, -1, -1):
                if hand_a[_index] == drawn:
                    hand_a.pop(_index)
                    break
            assert len(hand_a) == len(concealed) - 1
            obs_a = _observation(game_id, seat, seq, tuple(hand_a), drawn, melds)
            engine_a = any(
                c.action_key == "hu" for c in rules.analyze(obs_a).legal_candidates
            )
            # 形态 B：官方实测形态（my_hand 含刚摸的牌，drawn_tile 再单列）。
            obs_b = _observation(game_id, seat, seq, tuple(concealed), drawn, melds)
            engine_b = any(
                c.action_key == "hu" for c in rules.analyze(obs_b).legal_candidates
            )
            assert engine_a == engine_b, (
                "摸牌双计未归一化：{0} seq {1} 座位 {2} 两种 my_hand 形态判定不一致".format(
                    game_id, seq, seat,
                )
            )
            assert engine_a == official_hu, (
                "胡牌判定与官方不一致：{0} seq {1} 座位 {2} 引擎 {3} 官方 {4}".format(
                    game_id, seq, seat, engine_a, official_hu,
                )
            )
            checked_draws += 1
    assert total_official_wins >= 1, "归档场次应至少含一场官方胡牌用于正例锚定"
    assert checked_draws >= 50, "对拍样本过少，夹具可能损坏"
    assert checked_meld_windows >= 2, "缺少碰/吃后未摸牌窗口，门禁回归无覆盖"


def test_golden_hu_shapes_after_fix():
    """金例回归：差分发现的边界牌型在修复后判定与官方一致。"""

    rules = _rules()
    path = _FIXTURE_DIR / "golden-hu-shapes.jsonl"
    if not path.exists():
        pytest.skip("金例夹具缺失：golden-hu-shapes.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 4
    for row in rows:
        melds = tuple(
            _meld(m["kind"], tuple(m["tiles"])) for m in row["my_melds"]
        )
        concealed = tuple(row["hand14"])
        # 平台形态（my_hand 含摸牌）：修复后必须给出与官方一致的判定。
        obs = _observation(
            row["provenance"]["game_id"],
            row["seat"],
            row["provenance"]["trigger_seq"],
            concealed,
            row["drawn"],
            melds,
        )
        analysis = rules.analyze(obs)
        engine_hu = any(
            c.action_key == "hu" for c in analysis.legal_candidates
        )
        assert engine_hu == row["expected_engine_hu"], (
            "金例 {0} 判定 {1} != 期望 {2}（官方 {3}）".format(
                row["tag"], engine_hu, row["expected_engine_hu"], row["official"],
            )
        )
