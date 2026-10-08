# -*- coding: utf-8 -*-
"""C1/R3 公开契约验证替身（Q1 夹具验收专用；0 真实桌赛）。

用途：验证 v2_behavior **真实路径代码**（run_real_prefix_attempt / rebuild_world /
run_conditional_stage_arm）在组合根运行时契约 {"engine", "spec_factory",
"choice_factory"} 上正确工作。本替身与 scripted_fixture 生成器
（ScriptedFixtureEngine/build_fixture_frames）完全独立——它模拟真实引擎的
关键性质：**帧序列与终局积分只由 spec（seed/match_id）确定**，因此跨进程
重建（持久化快照→新进程 start+重放前缀）得到逐键相同的观察摘要。

红线：本模块不是强度证据、不属于任何生成器版本；真实执行必须用组合根
SimulationEngine（批次 7 授权，R6 E 重验）。不设置 fixture_mode 属性。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
_HERE = Path(__file__).resolve().parent
for _entry in (str(_project_file(_PROJECT_ROOT, REPO / "src")), str(_HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from hangma_bot.kernel.actions import Tile, WindowKey, WindowPhase, action_key  # noqa: E402
from hangma_bot.kernel.observation import (  # noqa: E402
    PlayerObservation,
    PublicDiscard,
    RulePublicState,
)

#: 前缀窗口（座位 1 摸牌）与焦点窗口（座位 0 响应）的手牌模板；与
#: sitin_opportunities 的夹具模板表刻意独立（验证无隐藏耦合）。
_PREFIX_HAND = "2b 4b 6b 8b 1t 2t 3t 7t 8t 9t 3w 5w 7w"
_FOCUS_HIT_HAND = "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b"   # 偶数种子：branch_open TRUE
_FOCUS_MISS_HAND = "2t 2t 3t 4t 5t 6t 7t 8t 9t 1b 2b 3b 4b"  # 奇数种子：FALSE
#: 焦点窗口选择 → 终局积分映射（确定性；与 scripted_fixture 的映射独立取值）。
_OUTCOME = {
    "seat0:peng:5w": (5, -1, -2, -2),
    "default": (1, 1, -1, -1),
}


def _observation(game_id: str, seat: int, phase: str, hand: str, trigger_seq: int,
                 scores: Tuple[int, int, int, int]) -> PlayerObservation:
    tiles = tuple(Tile(code) for code in hand.split())
    return PlayerObservation(
        game_id=game_id, seat=seat, round_no=1, snapshot_seq=trigger_seq,
        phase=phase, dealer_seat=0,
        turn_seat=(seat if phase == "draw" else 3),
        responding_seats=(() if phase == "draw" else (seat,)),
        my_hand=tiles, drawn_tile=(Tile("5b") if phase == "draw" else None),
        discards=((), (), (), (Tile("5w"),) if phase != "draw" else ()),
        melds=((), (), (), ()), hand_counts=(len(tiles), 13, 13, 13),
        last_discard=(None if phase == "draw"
                      else __import__("hangma_bot.kernel.observation",
                                      fromlist=["PublicDiscard"]).PublicDiscard(
                          3, Tile("5w"), trigger_seq)),
        remaining_tile_count=55, scores=scores,
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


class _World:
    """替身世界（不透明 token + 派生自 spec 的确定性脚本游标）。"""

    def __init__(self, token: int, seed: int, match_id: str) -> None:
        self.token = token
        self.seed = int(seed)
        self.match_id = match_id


class DeterministicPublicEngine:
    """公开契约引擎替身：start/frame/advance；帧只由 spec.seed 决定。

    - 每个世界三帧：[座位 1 摸牌（前缀帧）, 座位 0 焦点响应帧, 终局帧]；
    - 焦点帧形状由 seed 奇偶决定（偶=branch_open TRUE 种子手，奇=FALSE）；
    - 终局积分由焦点帧座位 0 的选择映射（_OUTCOME）；
    - advance 用注入规则 rules.analyze 验证每个选择合法（合法动作见证）。
    """

    def __init__(self, rules: Any, value_limits: Any = None) -> None:
        self._rules = rules
        self._value_limits = value_limits
        self._next_token = 0
        self._cursor = {}
        self._pending = {}
        self._last = {}
        self.advance_calls = []

    def start(self, spec: Any) -> _World:
        token = self._next_token
        self._next_token += 1
        self._cursor[token] = 0
        return _World(token, spec.seed, spec.match_id)

    def _analyze(self, observation: PlayerObservation) -> Any:
        if self._value_limits is None:
            return self._rules.analyze(observation)
        return self._rules.analyze(observation, value_limits=self._value_limits)

    def frame(self, world: _World) -> Any:
        cursor = self._cursor.get(world.token, 0)
        if cursor >= 3:
            raise AssertionError("替身脚本帧已耗尽；驱动不应在终态后继续取帧")
        if cursor == 0:
            decision = SimpleNamespace(
                window_key=WindowKey(game_id=world.match_id, round_no=1, trigger_seq=5,
                                     phase=WindowPhase.DRAW, seat=1),
                observation=_observation(world.match_id, 1, "draw", _PREFIX_HAND, 5,
                                         (0, 0, 0, 0)),
                timeout_seconds=3.0,
            )
            frame = SimpleNamespace(revision=1, decisions=(decision,),
                                    completed_hands=0, final_scores=None,
                                    blocked_reason=None)
        elif cursor == 1:
            # 焦点帧固定用 branch_open TRUE 种子手（确定性命中：帧形状不受派生
            # seed 影响，避免 attempts_cap 内的命中随机性）。
            hand = _FOCUS_HIT_HAND
            decision = SimpleNamespace(
                window_key=WindowKey(game_id=world.match_id, round_no=1, trigger_seq=9,
                                     phase=WindowPhase.RESPONSE_PENG, seat=0),
                observation=_observation(world.match_id, 0, "response_peng", hand, 9,
                                         (0, 0, 0, 0)),
                timeout_seconds=1.0,
            )
            frame = SimpleNamespace(revision=2, decisions=(decision,),
                                    completed_hands=0, final_scores=None,
                                    blocked_reason=None)
        else:
            scores = self._pending.get(world.token)
            if scores is None:
                raise ValueError("替身终局帧缺少上一帧选择映射的积分")
            frame = SimpleNamespace(revision=3, decisions=(), completed_hands=1,
                                    final_scores=scores, blocked_reason=None)
        self._last[world.token] = frame
        return frame

    def advance(self, world: _World, revision: int, choices: Tuple[Any, ...]) -> _World:
        last = self._last.get(world.token)
        if last is None or revision != last.revision:
            raise ValueError("旧 revision 拒绝：{0}".format(revision))
        expected = [decision.window_key for decision in last.decisions]
        provided = [choice.window_key for choice in choices]
        if provided != expected:
            raise ValueError("窗口集合不匹配：{0} vs {1}".format(expected, provided))
        for decision, choice in zip(last.decisions, choices):
            key = action_key(choice.action)
            analysis = self._analyze(decision.observation)
            if not any(c.action_key == key for c in analysis.legal_candidates):
                raise ValueError("动作 {0} 不在座位 {1} 合法候选中（替身合法动作见证）".format(
                    key, decision.window_key.seat))
        if revision == 2:
            focal_key = action_key(choices[0].action)
            self._pending[world.token] = _OUTCOME.get(
                "seat0:{0}".format(focal_key), _OUTCOME["default"])
        self.advance_calls.append((world.token, revision, tuple(choices)))
        self._cursor[world.token] = self._cursor[world.token] + 1
        return _World(world.token, world.seed, world.match_id)


def build_runtime_double(rules: Any, value_limits: Any = None) -> Mapping[str, Any]:
    """组装公开契约运行时替身：{"engine", "spec_factory", "choice_factory"}。"""
    engine = DeterministicPublicEngine(rules, value_limits)

    def spec_factory(*, match_id: str, scenario_id: str, config: Any, seed: int,
                     initial_dealer: int, initial_scores: Sequence[int]) -> Any:
        return SimpleNamespace(match_id=match_id, scenario_id=scenario_id,
                               config=config, seed=int(seed),
                               initial_dealer=initial_dealer,
                               initial_scores=tuple(initial_scores))

    def choice_factory(window_key: WindowKey, action: Any) -> Any:
        return SimpleNamespace(window_key=window_key, action=action)

    return {"engine": engine, "spec_factory": spec_factory,
            "choice_factory": choice_factory}
