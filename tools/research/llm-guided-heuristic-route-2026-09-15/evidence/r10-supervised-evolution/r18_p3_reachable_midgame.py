"""R18 P3 三财神飘：真实模拟前缀可达中局与配对续打复核。

本程序先在完全不调用候选评分器的 ``prepare`` 阶段生成新三财神爆头形状，
把它们放入完整 136 张物理世界，再通过 ``SimulationEngine`` 和正式
``BotPolicy`` 接缝执行合法前缀。目标请求必须带有真实牌河、减少后的牌墙、
轮转后的事件序号，并由 ``hangma`` 重新生产完整动作价值事实。

``run`` 阶段才读取冻结的 P3/P4 源码：一方面复核 P3 是否在这些新请求上
选择飘白，另一方面从同一完整世界重放两臂，只在目标窗口分别强制胡与
飘白，比较焦点座位本局终局积分。该证据仍是定向机会确认，不替代完整
桌赛非劣门或发布门。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_multi_wealth_bank as bank  # noqa: E402
import r18_p4_counterfactual_pilot as pilot  # noqa: E402
import r18_wealth_gap_bank as gap_bank  # noqa: E402
from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_request_from_json,
    decision_request_to_json,
)
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER  # noqa: E402
from hangma_bot.kernel.serialization import (  # noqa: E402
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.offline.evaluate import (  # noqa: E402
    frame_observation_summary,
    resume_match,
)
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.offline.opportunity_capability import (  # noqa: E402
    OpportunityCapabilityCase,
    OracleActionValue,
    evaluate_pair,
)
from hangma_bot.offline.opportunity_oracle import (  # noqa: E402
    ORACLE_VERSION,
    build_one_draw_self_win_oracle,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate  # noqa: E402
from hangma_bot.simulation import (  # noqa: E402
    DEAL_ALGORITHM,
    GUIDE_CAPTURED_AT,
    GUIDE_VERSION,
    RESERVE_TILES,
    SimulationChoice,
    SimulationEngine,
    hand_id,
    split_group_id,
)
from hangma_bot.simulation.engine import WORLD_SCHEMA  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-reachable-midgame-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
PARENT = gap_bank.PARENT
GENERATOR_SEED = 202609220701
CASES_PER_ROLE = 16
ROLES = ("dealer_after_rotation", "nondealer_after_dealer_discard")
WHITE = "白"
SAFE_HONORS = ("东", "南", "西", "北", "中", "发")
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)
BOOTSTRAP_REPLICATES = 20_000


def canonical_bytes(value: Any) -> bytes:
    """返回稳定 JSON 字节；用于绑定题面、前缀和结果身份。"""

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _rerank(plan: DecisionPlan, action_key: str, reason: str) -> DecisionPlan:
    """只把计划中已经存在的合法动作提升到首位，不生成新动作。"""

    forced = next(
        (item for item in plan.candidates if item.action_key == action_key), None
    )
    if forced is None:
        raise ValueError("前缀动作不在策略完整计划中：" + action_key)
    ordered = (forced,) + tuple(
        item for item in plan.candidates if item.action_key != action_key
    )
    candidates = tuple(
        RankedCandidate(
            action=item.action,
            action_key=item.action_key,
            rank=index + 1,
            total_score=item.total_score,
            score_parts=item.score_parts,
            reasons=item.reasons,
            is_emergency=item.is_emergency,
            score_trace=item.score_trace,
        )
        for index, item in enumerate(ordered)
    )
    return DecisionPlan(
        decision_id=plan.decision_id,
        window_key=plan.window_key,
        based_on_authoritative_seq=plan.based_on_authoritative_seq,
        revision=plan.revision,
        candidates=candidates,
        degraded_reasons=plan.degraded_reasons + (reason,),
        outcome_trace=plan.outcome_trace,
    )


class ForceWhenLegalOncePolicy:
    """题库生成专用：指定动作首次合法时强制一次，并记录实际窗口。"""

    def __init__(self, inner: Any, action_key: str, label: str) -> None:
        self.inner = inner
        self.action_key = action_key
        self.label = label
        self.policy_id = "r18-midgame-prefix-" + label
        self.max_operations = getattr(inner, "max_operations", None)
        self.force_count = 0
        self.event: dict[str, Any] | None = None

    async def choose(self, request: Any, budget: Any) -> DecisionPlan:
        plan = await self.inner.choose(request, budget)
        legal = {item.action_key for item in request.rules.legal_candidates}
        if self.force_count or self.action_key not in legal:
            return plan
        self.force_count = 1
        self.event = {
            "label": self.label,
            "seat": request.observation.seat,
            "window_key": window_key_to_json(request.window_key),
            "action_key": self.action_key,
        }
        return _rerank(
            plan,
            self.action_key,
            "offline_reachable_prefix_force:" + self.action_key,
        )


class CapturePolicy:
    """记录焦点正式请求后原样委托；不读完整世界。"""

    def __init__(self, inner: Any, sink: list[Any]) -> None:
        self.inner = inner
        self.sink = sink
        self.policy_id = "r18-midgame-capture"
        self.max_operations = getattr(inner, "max_operations", None)

    async def choose(self, request: Any, budget: Any) -> DecisionPlan:
        self.sink.append(request)
        return await self.inner.choose(request, budget)


def excluded_hands() -> set[tuple[str, ...]]:
    """排除先前所有多财神开发/隐藏题，保证新形状零重叠。"""

    directories = (
        _project_file(_PROJECT_ROOT, HERE / "r18-multi-wealth-bank-02-20260922"),
        _project_file(_PROJECT_ROOT, HERE / "r18-p4-shape-bank-01-20260922"),
        _project_file(_PROJECT_ROOT, HERE / "r18-wealth-gap-bank-01-20260922"),
    )
    values: set[tuple[str, ...]] = set()
    for directory in directories:
        for split in ("development", "hidden"):
            document = json.loads((directory / (split + ".json")).read_text(encoding="utf-8"))
            for row in document["cases"]:
                values.add(tuple(row["reachability_witness"]["hand13"]))
    return values


def generate_shapes(count: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """仅用规则与一次自摸代理筛出新的三财神飘形状。"""

    rng = random.Random(GENERATOR_SEED)
    excluded = excluded_hands()
    seen: set[tuple[str, ...]] = set()
    selected = []
    attempts = analyzed = 0
    rules_hash = bank.rules_sha256()
    generator_hash = digest(Path(__file__))
    while len(selected) < count:
        attempts += 1
        if attempts > 1_000_000:
            raise RuntimeError("达到形状生成上限仍未填满可达中局题库")
        hand = gap_bank.candidate_hand(rng, 3)
        if hand in excluded or hand in seen:
            continue
        seen.add(hand)
        if not gap_bank.recompute_baotou(
            tuple(gap_bank.Tile(code) for code in hand), 0, 3
        ):
            continue
        for drawn in gap_bank.possible_draws(hand, rng):
            analyzed += 1
            probe = gap_bank.build_case(
                hand=hand,
                draw=drawn,
                ordinal=len(selected) + 1,
                generator_hash=generator_hash,
                rules_hash=rules_hash,
            )
            if probe["opportunity_stratum"] != "three_wealth_piao":
                continue
            absent = [
                code for code in SAFE_HONORS
                if code not in hand and code != drawn
            ]
            if len(absent) < 3:
                continue
            selected.append(probe)
            break
    return selected, {
        "hand_attempts": attempts,
        "analyzed_hand_draw_states": analyzed,
        "excluded_prior_hands": len(excluded),
    }


def _remove(deck: list[str], values: list[str]) -> None:
    for code in values:
        deck.remove(code)


def _can_chi(hand: list[str], tile: str) -> bool:
    if len(tile) != 2 or tile[0] not in "123456789" or tile[1] not in "wbt":
        return False
    rank = int(tile[0])
    suit = tile[1]
    counts = Counter(hand)
    for left, right in ((rank - 2, rank - 1), (rank - 1, rank + 1), (rank + 1, rank + 2)):
        if 1 <= left <= 9 and 1 <= right <= 9:
            if counts[str(left) + suit] and counts[str(right) + suit]:
                return True
    return False


def _prefix_discard_unclaimable(
    hands: list[list[str]], *, discarder: int, tile: str
) -> bool:
    """保证前缀弃牌不会产生吃碰杠响应，路径长度因而可复算。"""

    for seat, hand in enumerate(hands):
        if seat != discarder and hand.count(tile) >= 2:
            return False
    next_seat = (discarder + 1) % 4
    return not _can_chi(hands[next_seat], tile)


def _world_row(
    shape: dict[str, Any], *, case_index: int, role: str
) -> tuple[dict[str, Any], int, list[tuple[int, str, str]]]:
    """构造完整起点与候选无关的前缀动作规格。"""

    witness = shape["reachability_witness"]
    focal_hand = list(witness["hand13"])
    target_draw = str(witness["draw"])
    rng = random.Random(GENERATOR_SEED + 10_000 + case_index)
    focal_seat = (case_index - 1) % 4
    dealer_seat = focal_seat if role == "dealer_after_rotation" else (focal_seat - 1) % 4
    absent = [
        code for code in SAFE_HONORS
        if code not in focal_hand and code != target_draw
    ]
    needed_honors = 3 if role == "dealer_after_rotation" else 1
    scheduled_honors = absent[:needed_honors]
    if len(scheduled_honors) != needed_honors:
        raise ValueError("目标手牌没有足够的无响应安全字牌")

    deck = [code for code in CANONICAL_TILE_ORDER for _ in range(4)]
    hands: list[list[str]] = [[] for _ in range(4)]
    hands[focal_seat] = focal_hand
    _remove(deck, focal_hand)
    prefix_specs: list[tuple[int, str, str]] = []
    if role == "dealer_after_rotation":
        dealer_draw = target_draw
        _remove(deck, [dealer_draw, target_draw] + scheduled_honors)
        wall_prefix = scheduled_honors + [target_draw]
        prefix_specs.append((focal_seat, "discard:" + target_draw, "dealer_initial"))
        for offset, code in enumerate(scheduled_honors, 1):
            seat = (dealer_seat + offset) % 4
            prefix_specs.append((seat, "discard:" + code, "rotation_" + str(offset)))
    else:
        dealer_draw = scheduled_honors[0]
        _remove(deck, [dealer_draw, target_draw])
        wall_prefix = [target_draw]
        prefix_specs.append((dealer_seat, "discard:" + dealer_draw, "dealer_initial"))

    # 白板和安全字牌的其余副本留在墙内，避免前缀发生财神替代或字牌响应。
    forbidden_for_other_hands = set(scheduled_honors) | {WHITE}
    allowed = [code for code in deck if code not in forbidden_for_other_hands]
    held = [code for code in deck if code in forbidden_for_other_hands]
    other_seats = [seat for seat in range(4) if seat != focal_seat]
    for _ in range(20_000):
        rng.shuffle(allowed)
        trial = [list(hand) for hand in hands]
        cursor = 0
        for seat in other_seats:
            trial[seat] = allowed[cursor : cursor + 13]
            cursor += 13
        first_discard = target_draw if role == "dealer_after_rotation" else dealer_draw
        if _prefix_discard_unclaimable(
            trial, discarder=dealer_seat, tile=first_discard
        ):
            hands = trial
            break
    else:
        raise RuntimeError("无法分配无响应前缀的三家暗牌")
    used_other = Counter(code for seat in other_seats for code in hands[seat])
    remainder = list(deck)
    for code, amount in used_other.items():
        _remove(remainder, [code] * amount)
    # target_draw 与 scheduled_honors 已从 deck 提前移除，因此显式放回墙前缀。
    rng.shuffle(remainder)
    wall = wall_prefix + remainder
    if len(wall) != 83:
        raise AssertionError("完整世界剩余墙必须为 83 张")
    physical = Counter(code for hand in hands for code in hand)
    physical[dealer_draw] += 1
    physical.update(wall)
    if any(physical[code] != 4 for code in CANONICAL_TILE_ORDER):
        raise AssertionError("完整世界牌张不守恒")

    case_id = "r18-p3-mid-{0:03d}".format(case_index)
    match_id = case_id + "-match"
    scenario_id = case_id + "-scenario"
    payload = {
        "world_schema": WORLD_SCHEMA,
        "deal_algorithm": DEAL_ALGORITHM,
        "seed": GENERATOR_SEED + case_index,
        "scenario_id": scenario_id,
        "match_id": match_id,
        "round_no": 1,
        "rounds_per_game": 1,
        "parent_hand_id": None,
        "dealer_seat": dealer_seat,
        "initial_scores": [0, 0, 0, 0],
        "rule_config": {
            "ruleset_version": pilot.RULE_CONFIG.ruleset_version,
            "base_score": pilot.RULE_CONFIG.base_score,
            "you_cai_bi_kao": pilot.RULE_CONFIG.you_cai_bi_kao,
        },
        "timing": {
            "peng_timeout_sec": 1.0,
            "chi_timeout_sec": 1.0,
            "discard_timeout_sec": 3.0,
        },
        "rules_hash": shape["rules_hash"],
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "hands": hands,
        "dealer_drawn_tile": dealer_draw,
        "wall": wall,
        "wall_front": 0,
        "wall_back": len(wall) - RESERVE_TILES,
        "seq": 0,
    }
    initial_hands = [
        hand + ([dealer_draw] if seat == dealer_seat else [])
        for seat, hand in enumerate(hands)
    ]
    row = {
        "replay_schema_version": 1,
        "hand_id": hand_id("hangma-simulation", scenario_id, match_id, 1),
        "split_group_id": split_group_id(["hangma-simulation", scenario_id]),
        "origin": "simulated",
        "parent_hand_id": None,
        "coverage": "full_world",
        "game_key": {
            "source_namespace": "hangma-simulation",
            "tournament_id": scenario_id,
            "game_id": match_id,
        },
        "round_no": 1,
        "rule_config": payload["rule_config"],
        "rules_hash": shape["rules_hash"],
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "initial": {
            "dealer_seat": dealer_seat,
            "hands": initial_hands,
            "drawn_tile": dealer_draw,
            "drawn_seat": dealer_seat,
            "draw_identity_known": True,
            "wall": wall,
            "world_schema": WORLD_SCHEMA,
            "world_payload": payload,
            "source_refs": [],
        },
        "events": [],
        "scores_before": [0, 0, 0, 0],
        "scores_after": None,
        "score_delta": None,
        "winner_seat": None,
        "is_draw": None,
        "attempt_status": "unknown",
        "result_confirmed": False,
        "missing_fields": [],
        "source_refs": [],
    }
    return row, focal_seat, prefix_specs


async def _capture_target(
    world_row: dict[str, Any],
    focal_seat: int,
    prefix_specs: list[tuple[int, str, str]],
    shape: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    """用正式驱动执行前缀并返回唯一目标请求。"""

    engine = SimulationEngine(pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    world = engine.from_replay(world_row)
    frame = engine.frame(world)
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    forces: list[ForceWhenLegalOncePolicy] = []
    for seat, action_key, label in prefix_specs:
        wrapper = ForceWhenLegalOncePolicy(policies[seat], action_key, label)
        policies[seat] = wrapper
        forces.append(wrapper)
    captured: list[Any] = []
    policies[focal_seat] = CapturePolicy(policies[focal_seat], captured)
    outcome = await resume_match(
        engine=engine,
        world=world,
        policies_by_seat=tuple(policies),
        rules=pilot.RULES,
        choice_factory=SimulationChoice,
        config=pilot.driver_config(),
        now_monotonic=lambda: 800.0,
        wall_clock=None,
        remaining_schedule={"declared_endpoint": "hand_complete"},
        stage_snapshot={
            "observation_summary": frame_observation_summary(frame),
            "match_spec": {
                "match_id": world_row["initial"]["world_payload"]["match_id"]
            },
        },
        value_limits=LIMITS,
    )
    if outcome.status != "complete" or any(item.force_count != 1 for item in forces):
        raise RuntimeError("可达前缀未完整执行：" + str(outcome.error_reason))
    target_hand = sorted(shape["reachability_witness"]["hand13"])
    target_draw = shape["reachability_witness"]["draw"]
    matches = []
    for request in captured:
        observation = request.observation
        legal = {item.action_key for item in request.rules.legal_candidates}
        if (
            observation.seat == focal_seat
            and sorted(tile.code for tile in observation.my_hand) == target_hand
            and observation.drawn_tile is not None
            and observation.drawn_tile.code == target_draw
            and sum(len(river) for river in observation.discards) > 0
            and observation.remaining_tile_count is not None
            and observation.remaining_tile_count < 83
            and observation.rule_state.baotou is True
            and {"hu", "discard:白"} <= legal
        ):
            oracle = build_one_draw_self_win_oracle(request)
            if not oracle.issues and {item.action_key for item in oracle.values} == legal:
                best = max(item.value for item in oracle.values)
                if "discard:白" in {
                    item.action_key for item in oracle.values if item.value == best
                }:
                    matches.append(request)
    if len(matches) != 1:
        raise RuntimeError("合法前缀未产生唯一三财神飘目标请求：" + str(len(matches)))
    events = [item.event for item in forces if item.event is not None]
    runtime = {
        "status": outcome.status,
        "completed_hands": outcome.completed_hands,
        "steps": outcome.steps,
        "decisions": len(outcome.decisions),
        "runtime_counts": asdict(outcome.runtime_counts),
    }
    return matches[0], events, runtime


def _public_summary(request: Any) -> dict[str, Any]:
    observation = request.observation
    return {
        "seat": observation.seat,
        "dealer_seat": observation.dealer_seat,
        "snapshot_seq": observation.snapshot_seq,
        "remaining_tile_count": observation.remaining_tile_count,
        "river_lengths": [len(river) for river in observation.discards],
        "meld_counts": [len(melds) for melds in observation.melds],
        "public_history_events": len(observation.public_history),
        "wealth_count": sum(
            tile.code == observation.rule_state.wealth_god.code
            for tile in observation.my_hand
        ) + int(
            observation.drawn_tile is not None
            and observation.drawn_tile.code == observation.rule_state.wealth_god.code
        ),
        "baotou": observation.rule_state.baotou,
        "legal_action_keys": [
            item.action_key for item in request.rules.legal_candidates
        ],
    }


async def prepare_async() -> None:
    if OUT.exists():
        raise SystemExit("可达中局证据目录已存在；拒绝覆盖")
    shapes, work = generate_shapes(CASES_PER_ROLE * len(ROLES))
    cases = []
    for index, shape in enumerate(shapes, 1):
        role = ROLES[(index - 1) // CASES_PER_ROLE]
        world, focal_seat, prefix_specs = _world_row(
            shape, case_index=index, role=role
        )
        request, prefix_events, runtime = await _capture_target(
            world, focal_seat, prefix_specs, shape
        )
        request_json = decision_request_to_json(request)
        oracle = build_one_draw_self_win_oracle(request)
        cases.append({
            "case_id": "r18-p3-mid-{0:03d}".format(index),
            "base_scenario_id": "r18-p3-mid-shape-{0:03d}".format(index),
            "family": "multi_wealth_baotou",
            "split": "hidden",
            "role": role,
            "focal_seat": focal_seat,
            "generator_seed": GENERATOR_SEED,
            "rules_hash": shape["rules_hash"],
            "generator_sha256": digest(Path(__file__)),
            "oracle_version": ORACLE_VERSION,
            "oracle_level": "declared_conditional_proxy",
            "request_sha256": digest_value(request_json),
            "reachability_witness_sha256": digest_value({
                "world_sha256": digest_value(world["initial"]["world_payload"]),
                "prefix_events": prefix_events,
            }),
            "shape_witness": shape["reachability_witness"],
            "request": request_json,
            "action_values": [asdict(item) for item in oracle.values],
            "full_world": world,
            "prefix_events": prefix_events,
            "public_summary": _public_summary(request),
            "generation_runtime": runtime,
        })
    counts = Counter((row["role"], row["focal_seat"]) for row in cases)
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "bank.json"), {
        "schema": "r18-p3-reachable-midgame-bank/1",
        "cases": cases,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p3-reachable-midgame-manifest/1",
        "phase": "PREPARED_CANDIDATE_UNREAD_FOR_SCORING",
        "generator_seed": GENERATOR_SEED,
        "generator_sha256": digest(Path(__file__)),
        "bank_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "bank.json")),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "candidate_evaluated_during_generation": False,
        "candidate_adaptation_after_generation_allowed": False,
        "cases": len(cases),
        "roles": list(ROLES),
        "counts": [
            {"role": role, "focal_seat": seat, "count": amount}
            for (role, seat), amount in sorted(counts.items())
        ],
        "generation_work": work,
        "required_public_state": {
            "nonempty_river": True,
            "remaining_tile_count_less_than": 83,
            "baotou": True,
            "wealth_count": 3,
            "legal_actions_include": ["hu", "discard:白"],
        },
        "gate_frozen_before_candidate_evaluation": {
            "all_cases_scored": True,
            "candidate_optimal_cases": len(cases),
            "candidate_piao_choices": len(cases),
            "zero_candidate_regressions": True,
            "all_counterfactual_arms_complete": True,
            "all_forced_actions_exactly_once": True,
            "overall_positive_pair_fraction_at_least": 0.75,
            "each_role_mean_piao_minus_hu_greater_than": 32.0,
            "each_role_bootstrap_95_lower_greater_than": 0.0,
        },
        "scope": "新形状、完整物理世界、正式规则与策略接缝执行后的可达中局；不替代完整桌赛非劣门",
    })
    print(json.dumps({
        "status": "PREPARED",
        "cases": len(cases),
        "counts": {f"{role}:seat{seat}": amount for (role, seat), amount in sorted(counts.items())},
        "bank_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "bank.json")),
    }, ensure_ascii=False, indent=2))


def _policy(path: Path, identity: str) -> ActionValuePolicy:
    return ActionValuePolicy(ActionValueScorer(
        identity, path.read_text(encoding="utf-8")
    ))


def _case(row: dict[str, Any]) -> OpportunityCapabilityCase:
    request = decision_request_from_json(row["request"])
    values = tuple(
        OracleActionValue(**item) for item in row["action_values"]
    )
    return OpportunityCapabilityCase(
        case_id=row["case_id"],
        base_scenario_id=row["base_scenario_id"],
        family=row["family"],
        split=row["split"],
        generator_seed=row["generator_seed"],
        rules_hash=row["rules_hash"],
        generator_sha256=row["generator_sha256"],
        oracle_version=row["oracle_version"],
        oracle_level=row["oracle_level"],
        request_sha256=row["request_sha256"],
        reachability_witness_sha256=row["reachability_witness_sha256"],
        request=request,
        action_values=values,
    )


def verify_prepared() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "bank.json")).read_text(encoding="utf-8"))
    if manifest["phase"] != "PREPARED_CANDIDATE_UNREAD_FOR_SCORING":
        raise ValueError("可达中局题库不在冻结待评阶段")
    if manifest["generator_sha256"] != digest(Path(__file__)):
        raise ValueError("生成器源码漂移")
    if manifest["bank_sha256"] != digest(_project_file(_PROJECT_ROOT, OUT / "bank.json")):
        raise ValueError("冻结题库漂移")
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P3 候选身份漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P4 父代身份漂移")
    for row in document["cases"]:
        if row["request_sha256"] != digest_value(row["request"]):
            raise ValueError(row["case_id"] + " 请求摘要漂移")
    return manifest, document["cases"]


async def _counterfactual_arm(
    row: dict[str, Any], target_action: str
) -> dict[str, Any]:
    world_row = row["full_world"]
    engine = SimulationEngine(pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    world = engine.from_replay(world_row)
    frame = engine.frame(world)
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    wrappers: list[ForceFirstActionPolicy] = []
    for event in row["prefix_events"]:
        seat = int(event["seat"])
        wrapper = ForceFirstActionPolicy(
            policies[seat],
            target_window=window_key_from_json(event["window_key"]),
            forced_action_key=event["action_key"],
            policy_id="r18-mid-replay-prefix-" + event["label"],
        )
        policies[seat] = wrapper
        wrappers.append(wrapper)
    target_request = decision_request_from_json(row["request"])
    target = ForceFirstActionPolicy(
        policies[row["focal_seat"]],
        target_window=target_request.window_key,
        forced_action_key=target_action,
        policy_id="r18-mid-replay-target-" + target_action,
    )
    policies[row["focal_seat"]] = target
    wrappers.append(target)
    outcome = await resume_match(
        engine=engine,
        world=world,
        policies_by_seat=tuple(policies),
        rules=pilot.RULES,
        choice_factory=SimulationChoice,
        config=pilot.driver_config(),
        now_monotonic=lambda: 800.0,
        wall_clock=None,
        remaining_schedule={"declared_endpoint": "hand_complete"},
        stage_snapshot={
            "observation_summary": frame_observation_summary(frame),
            "match_spec": {
                "match_id": world_row["initial"]["world_payload"]["match_id"]
            },
        },
        value_limits=LIMITS,
    )
    final_scores = None if outcome.final_scores is None else list(outcome.final_scores)
    return {
        "status": outcome.status,
        "completed_hands": outcome.completed_hands,
        "final_scores": final_scores,
        "focal_score": None if final_scores is None else final_scores[row["focal_seat"]],
        "steps": outcome.steps,
        "decisions": len(outcome.decisions),
        "all_forces_once": all(item.force_count == 1 for item in wrappers),
        "runtime_counts": asdict(outcome.runtime_counts),
        "error_reason": outcome.error_reason,
    }


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    rng = random.Random(GENERATOR_SEED + salt)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(len(values))] for _ in values) / len(values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


async def run_async() -> None:
    manifest, rows = verify_prepared()
    candidate = _policy(CANDIDATE, "r18-p3-reachable-midgame")
    parent = _policy(PARENT, "r18-p4-reachable-midgame")
    capability_rows = []
    pair_rows = []
    for row in rows:
        result = await evaluate_pair(candidate, parent, _case(row), bank.budget)
        capability_rows.append({
            "case_id": row["case_id"],
            "role": row["role"],
            "focal_seat": row["focal_seat"],
            "candidate_status": result.candidate.status,
            "candidate_action": result.candidate.chosen_action_key,
            "candidate_optimal": result.candidate.chosen_action_key in result.candidate.optimal_action_keys,
            "candidate_regret": result.candidate.regret,
            "parent_status": result.baseline.status,
            "parent_action": result.baseline.chosen_action_key,
            "parent_regret": result.baseline.regret,
            "capability_gain": result.capability_gain,
        })
        hu = await _counterfactual_arm(row, "hu")
        piao = await _counterfactual_arm(row, "discard:白")
        delta = None
        if hu["focal_score"] is not None and piao["focal_score"] is not None:
            delta = piao["focal_score"] - hu["focal_score"]
        pair_rows.append({
            "case_id": row["case_id"],
            "role": row["role"],
            "focal_seat": row["focal_seat"],
            "hu": hu,
            "piao": piao,
            "piao_minus_hu_focal_score": delta,
            "mechanical_ok": all(
                arm["status"] == "complete"
                and arm["completed_hands"] == 1
                and arm["all_forces_once"]
                and all(value == 0 for value in arm["runtime_counts"].values())
                for arm in (hu, piao)
            ),
        })

    role_summaries = {}
    for salt, role in enumerate(ROLES, 1):
        values = [
            float(item["piao_minus_hu_focal_score"])
            for item in pair_rows
            if item["role"] == role and item["piao_minus_hu_focal_score"] is not None
        ]
        lo, hi = bootstrap_interval(values, salt)
        role_summaries[role] = {
            "pairs": len(values),
            "mean_piao_minus_hu": statistics.fmean(values),
            "median_piao_minus_hu": statistics.median(values),
            "positive_pairs": sum(value > 0 for value in values),
            "zero_pairs": sum(value == 0 for value in values),
            "negative_pairs": sum(value < 0 for value in values),
            "bootstrap_95_mean": [lo, hi],
        }
    all_values = [
        float(item["piao_minus_hu_focal_score"])
        for item in pair_rows if item["piao_minus_hu_focal_score"] is not None
    ]
    checks = {
        "all_cases_scored": all(
            item["candidate_status"] == "SCORED" and item["parent_status"] == "SCORED"
            for item in capability_rows
        ),
        "candidate_all_optimal": all(item["candidate_optimal"] for item in capability_rows),
        "candidate_all_piao": all(
            item["candidate_action"] == "discard:白" for item in capability_rows
        ),
        "zero_candidate_regressions": all(
            item["capability_gain"] is not None and item["capability_gain"] >= 0
            for item in capability_rows
        ),
        "all_counterfactual_arms_complete": all(
            item["mechanical_ok"] for item in pair_rows
        ),
        "overall_positive_pair_fraction": (
            sum(value > 0 for value in all_values) / len(all_values) >= 0.75
        ),
        "each_role_mean_above_32": all(
            summary["mean_piao_minus_hu"] > 32.0
            for summary in role_summaries.values()
        ),
        "each_role_bootstrap_lower_positive": all(
            summary["bootstrap_95_mean"][0] > 0.0
            for summary in role_summaries.values()
        ),
    }
    passed = all(checks.values())
    write_json(_project_file(_PROJECT_ROOT, OUT / "capability-rows.json"), {"rows": capability_rows})
    write_json(_project_file(_PROJECT_ROOT, OUT / "counterfactual-pairs.json"), {"rows": pair_rows})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p3-reachable-midgame-result/1",
        "status": "PASS_REACHABLE_MIDGAME" if passed else "FAIL_REACHABLE_MIDGAME",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "bank_sha256": manifest["bank_sha256"],
        "checks": checks,
        "capability": {
            "cases": len(capability_rows),
            "candidate_optimal": sum(item["candidate_optimal"] for item in capability_rows),
            "candidate_piao": sum(item["candidate_action"] == "discard:白" for item in capability_rows),
            "parent_hu": sum(item["parent_action"] == "hu" for item in capability_rows),
            "mean_gain_over_parent": statistics.fmean(
                float(item["capability_gain"]) for item in capability_rows
                if item["capability_gain"] is not None
            ),
        },
        "counterfactual": {
            "pairs": len(pair_rows),
            "mechanical_ok": sum(item["mechanical_ok"] for item in pair_rows),
            "positive_pairs": sum(value > 0 for value in all_values),
            "mean_piao_minus_hu": statistics.fmean(all_values),
            "role_summaries": role_summaries,
        },
        "interpretation": "P3 三财神飘已外推到模拟器真实推进得到的庄家轮转后与非庄家中局；仍需估计自然暴露率并由完整桌赛守住非劣",
        "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8")), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    args = parser.parse_args()
    if args.command == "prepare":
        asyncio.run(prepare_async())
    else:
        asyncio.run(run_async())


if __name__ == "__main__":
    main()
