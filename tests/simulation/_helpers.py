"""模拟/历史核对测试的共享辅助（测试专用，不构成生产规则或转换器）。

构造世界（full_world 单局行）、驱动完整桌赛、把真实归档房间事件流映射为
统一牌谱单局行（仅测试侧映射，供 check_hand 按能力核对三份真实分块资料；
生产转换器归审计线，本文件不冒充转换算法）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.progression import EventRecord
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_ORDER,
    Discard,
    Hu,
    Pass,
    Tile,
    action_key,
)
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.simulation import (
    DEAL_ALGORITHM,
    GUIDE_CAPTURED_AT,
    GUIDE_VERSION,
    RESERVE_TILES,
    MatchSpec,
    SimulationChoice,
    SimulationEngine,
    WorldState,
    hand_id as _hand_id,
    split_group_id as _split_group_id,
)
from hangma_bot.simulation.engine import WORLD_SCHEMA

ALL_TILE_CODES = CANONICAL_TILE_ORDER


def make_rules(ruleset="test", base=1, youcai=False) -> HangmaRules:
    return HangmaRules(
        RuleConfig(ruleset_version=ruleset, base_score=base, you_cai_bi_kao=youcai)
    )


def make_timing(peng=1.0, chi=1.0, discard=3.0) -> TimingConfig:
    return TimingConfig(peng, chi, discard)


def make_spec(
    rules: HangmaRules,
    *,
    match_id="match-1",
    scenario_id="scenario-1",
    rounds=2,
    seed=7,
    dealer=0,
    scores=(0, 0, 0, 0),
    timing=None,
) -> MatchSpec:
    return MatchSpec(
        match_id=match_id,
        scenario_id=scenario_id,
        config=TournamentConfig(
            max_games=1,
            rounds_per_game=rounds,
            rules=rules.config,
            timing=timing or make_timing(),
        ),
        seed=seed,
        initial_dealer=dealer,
        initial_scores=scores,
    )


def simple_chooser(rules: HangmaRules) -> Callable:
    """最小确定性策略：胡 > 出牌 > 过；响应窗口一律过（官方示例口径）。"""

    def choose(decision):
        analysis = rules.analyze(decision.observation)
        candidates = analysis.legal_candidates
        if not candidates:
            raise AssertionError("无合法候选，无法驱动世界")
        if decision.window_key.phase.value in ("response_peng", "response_chi"):
            return Pass()
        for candidate in candidates:
            if isinstance(candidate.action, Hu):
                return candidate.action
        for candidate in candidates:
            if isinstance(candidate.action, Discard):
                return candidate.action
        return candidates[0].action

    return choose


def drive(engine: SimulationEngine, world: WorldState, chooser: Callable, max_steps=8000) -> WorldState:
    """按帧循环推进直到终局或阻塞；返回终态世界。"""
    steps = 0
    while True:
        frame = engine.frame(world)
        if frame.blocked_reason is not None or frame.final_scores is not None:
            return world
        choices = tuple(
            SimulationChoice(decision.window_key, chooser(decision))
            for decision in frame.decisions
        )
        world = engine.advance(world, frame.revision, choices)
        steps += 1
        if steps > max_steps:
            raise AssertionError("驱动步数超限（可能进入空转）")


class QueuedChooser:
    """脚本化选择器：按 (phase, seat) 队列消费预设动作，其余走默认。"""

    def __init__(self, rules: HangmaRules, default: Optional[Callable] = None):
        self.rules = rules
        self.queue: List[Tuple[str, int, object]] = []
        self.default = default or simple_chooser(rules)

    def enqueue(self, phase: str, seat: int, action):
        self.queue.append((phase, seat, action))

    def __call__(self, decision):
        phase = decision.window_key.phase.value
        seat = decision.window_key.seat
        if self.queue and self.queue[0][0] == phase and self.queue[0][1] == seat:
            return self.queue.pop(0)[2]
        return self.default(decision)


def total_tiles(world: WorldState) -> int:
    """当前局牌张守恒计数：暗牌（含摸牌）+ 副露 + 牌河 + 剩余牌墙 = 136。"""
    state = world.progression
    count = 0
    for seat in state.seats:
        count += len(seat.hand) + (1 if seat.drawn is not None else 0)
        for meld in seat.melds:
            count += len(meld.tiles)
        count += len(seat.discards)
    # 剩余墙 = 可摸区（back - front）+ 保留区 20：杠上补牌只收缩 wall_back，
    # 不能用 len(wall) - wall_front（会把已补走的牌仍计入墙内，高估 1）。
    count += (world.wall_back - world.wall_front) + RESERVE_TILES
    return count


def build_full_world_row(
    rules: HangmaRules,
    *,
    hands13: List[List[str]],
    dealer_drawn: str,
    wall: List[str],
    match_id="match-1",
    scenario_id="scenario-1",
    round_no=1,
    seed=123,
    dealer=0,
    scores_before=(0, 0, 0, 0),
    parent_hand_id=None,
    rounds_per_game=1,
    timing=None,
    rules_hash="fixture-hash",
) -> dict:
    """手工构造 full_world 单局行（牌墙可任意指定，供脚本化场景）。"""
    wall_back = len(wall) - RESERVE_TILES
    payload = {
        "world_schema": WORLD_SCHEMA,
        "deal_algorithm": DEAL_ALGORITHM,
        "seed": seed,
        "scenario_id": scenario_id,
        "match_id": match_id,
        "round_no": round_no,
        "rounds_per_game": rounds_per_game,
        "parent_hand_id": parent_hand_id,
        "dealer_seat": dealer,
        "initial_scores": list(scores_before),
        "rule_config": {
            "ruleset_version": rules.config.ruleset_version,
            "base_score": rules.config.base_score,
            "you_cai_bi_kao": rules.config.you_cai_bi_kao,
        },
        "timing": {
            "peng_timeout_sec": 1.0,
            "chi_timeout_sec": 1.0,
            "discard_timeout_sec": 3.0,
        },
        "rules_hash": rules_hash,
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "hands": [list(hand) for hand in hands13],
        "dealer_drawn_tile": dealer_drawn,
        "wall": list(wall),
        "wall_front": 0,
        "wall_back": wall_back,
        "seq": 0,
    }
    initial_hands = []
    for index, hand in enumerate(hands13):
        initial_hands.append(list(hand) + ([dealer_drawn] if index == dealer else []))
    return {
        "replay_schema_version": 1,
        "hand_id": _hand_id("hangma-simulation", scenario_id, match_id, round_no),
        "split_group_id": _split_group_id(["hangma-simulation", scenario_id]),
        "origin": "simulated",
        "parent_hand_id": parent_hand_id,
        "coverage": "full_world",
        "game_key": {
            "source_namespace": "hangma-simulation",
            "tournament_id": scenario_id,
            "game_id": match_id,
        },
        "round_no": round_no,
        "rule_config": payload["rule_config"],
        "rules_hash": rules_hash,
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "initial": {
            "dealer_seat": dealer,
            "hands": initial_hands,
            "drawn_tile": dealer_drawn,
            "drawn_seat": dealer,
            "draw_identity_known": True,
            "wall": list(wall),
            "world_schema": WORLD_SCHEMA,
            "world_payload": payload,
            "source_refs": [],
        },
        "events": [],
        "scores_before": list(scores_before),
        "scores_after": None,
        "score_delta": None,
        "winner_seat": None,
        "is_draw": None,
        "attempt_status": "unknown",
        "result_confirmed": False,
        "missing_fields": [],
        "source_refs": [],
    }


def archived_hand_row(path: Path, rules: HangmaRules) -> dict:
    """真实归档房间 JSON → 统一牌谱单局行（测试侧映射，覆盖 full_history）。"""
    doc = json.loads(path.read_text(encoding="utf-8"))
    room_id = doc["room_id"]
    game_id = doc["game_id"]
    blocks = doc["blocks"]
    first = blocks[0]
    result = doc["rounds"][0]
    events = []
    for block in blocks:
        for event in block["events"]:
            events.append({
                "seq": event["seq"],
                "type": event["type"],
                "seat": event["seat"],
                "tile": event.get("tile") or "",
                "data": event.get("data"),
                "ts": event.get("ts"),
                "source_refs": [],
            })
    winner = result.get("winner")
    winner = winner if isinstance(winner, int) and winner >= 0 else None
    delta = result["scores"]
    return {
        "replay_schema_version": 1,
        "hand_id": _hand_id("hangma-official", room_id, game_id, 1),
        "split_group_id": _split_group_id(["hangma-official", room_id]),
        "origin": "official",
        "parent_hand_id": None,
        "coverage": "full_history",
        "game_key": {
            "source_namespace": "hangma-official",
            "tournament_id": room_id,
            "game_id": game_id,
        },
        "round_no": 1,
        "rule_config": {
            "ruleset_version": rules.config.ruleset_version,
            "base_score": rules.config.base_score,
            "you_cai_bi_kao": rules.config.you_cai_bi_kao,
        },
        "rules_hash": None,
        "guide_version": 14,
        "guide_captured_at": "2026-09-05",
        "initial": {
            "dealer_seat": first.get("dealer", 0),
            "hands": first["start_hands"],
            "drawn_tile": None,
            "drawn_seat": None,
            "draw_identity_known": False,
            "wall": None,
            "world_schema": None,
            "world_payload": None,
            "source_refs": [],
        },
        "events": events,
        "scores_before": [0, 0, 0, 0],
        "scores_after": list(delta),
        "score_delta": list(delta),
        "winner_seat": winner,
        "is_draw": bool(result.get("is_draw")),
        "attempt_status": "unknown",
        "result_confirmed": True,
        "missing_fields": ["wall"],
        "source_refs": [],
    }


ARCHIVED_ROOMS = (
    ("t_6c121bfda7e8_b0.json", 448, False, None),
    ("t_cee1db65a074_b0.json", 408, False, None),
    ("t_714a42392cba_b0.json", 346, True, 2),
)
"""三份真实分块资料：(文件名, 事件数, 官方是否胡牌, 赢家座位)。"""


def archived_fixture(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "hangma" / "archived-rooms" / name