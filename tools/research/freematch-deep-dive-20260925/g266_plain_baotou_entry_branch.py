#!/usr/bin/env python3
"""G266：当前规则 R18 父代的结果盲分层捕获与同世界一次改弃完整桌诊断。

仅供离线研究；入选只读 PlayerObservation、规则候选与父代计划。
``scan`` 把两个池的行动前暴露完整落盘，``branch`` 只读取冻结入选清单。
程序拒绝旧发布包规则哈希，且不会把诊断均值称作在线候选收益。
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

import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import random
import time
from typing import Any

import g138_official_plain_baotou_opportunity as opportunity
import g182_full_table_branch_preflight as old_branch
import g261_current_rules_panel as current
import g93_same_hand_branch_preflight as g93
from g13_hand_accounting import summarize_hands
from hangma_bot.policy.evaluation_v1 import _hand_codes_without_double_count
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18_V2_RULES_20260929_SOURCE_HASH,
)


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G266-PLAIN-BAOTOU-ENTRY-BRANCH-PREREG-2026-09-29.md')
GUIDE_METADATA = _project_file(_PROJECT_ROOT, ROOT / "doc/references/official-guide-version-v35.json")
LAYERS = ("B_nonready", "B_ready", "C", "A")
MIXES = ("H", "M")
SEATS = tuple(range(4))
BLOCKS = ((2026122966, range(3, 67)), (2026122967, range(3, 67)))
SMOKE_ROOTS = (1, 2)
SAMPLES = ("historical",) + tuple(f"g266-{index:02d}" for index in range(1, 9))
QUOTAS = {"B_nonready": 32, "B_ready": 4, "C": 8, "A": 4}
RUNTIME_ZERO = ("fallbacks", "illegal_choices", "timeouts", "auto_actions", "audit_missing")
SCORE_PARTS = ("base_score", "wealth_part", "wealth_discard_part",
               "river_part", "style_part")
HAND_CLASSES = ("plain_no_baotou", "plain_baotou", "seven_pairs",
                "other_self_special", "other_win", "draw")
SETTLEMENT_FIELDS = old_branch.SETTLEMENT_FIELDS
SUCCESS_REASON = f"action_value: {R18_INTEGRATED_POSITIVE_V2_NAME} 评分完成"
NEGATIVE_CONTROL_REASONS = frozenset((
    "immediate_hu", "already_plain_baotou_opportunity", "zero_white",
    "no_layer_qualified", "response_window"))


def digest(path: Path) -> str:
    """返回输入文件原始字节摘要，供断点重跑核冻结身份。"""
    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    """原子落盘；已有文件仅允许同一字节内容，防止覆写证据。"""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError("G266 已有证据不同：" + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    tmp.replace(path)


def manifest() -> dict[str, Any]:
    """固定规则、版本元数据、R18 评分源码、面板和诊断代码身份。"""
    metadata = json.loads(GUIDE_METADATA.read_text(encoding="utf-8"))
    if metadata.get("version") != 35:
        raise ValueError("G266 官方指南 v35 元数据漂移；仓库无 v35 全文快照")
    rules_hash = g93.natural.compute_rules_hash(ROOT)
    if rules_hash != R18_V2_RULES_20260929_SOURCE_HASH:
        raise ValueError("G266 当前生产 HangmaRules 摘要与 G194 绑定不同")
    if sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest() != (
            R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("G266 冻结 R18 v2 评分源码摘要漂移")
    contract = json.loads(g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    if int(versions["rounds_per_game"]) != 8:
        raise ValueError("G266 完整桌合同不再是八单局")
    inputs = (PREREG, GUIDE_METADATA, g93.paired.CONTRACT,
              Path(g93.paired.__file__), Path(__file__),
              _project_file(_PROJECT_ROOT, HERE / "g93_same_hand_branch_preflight.py"),
              _project_file(_PROJECT_ROOT, HERE / "g182_full_table_branch_preflight.py"),
              _project_file(_PROJECT_ROOT, HERE / "g261_current_rules_panel.py"),
              _project_file(_PROJECT_ROOT, HERE / "g193_early_shape_policy.py"),
              _project_file(_PROJECT_ROOT, HERE / "g138_official_plain_baotou_opportunity.py"),
              _project_file(_PROJECT_ROOT, HERE / "g13_hand_accounting.py"),
              _project_file(_PROJECT_ROOT, ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools/sitin_natural_panel.py"),
              _project_file(_PROJECT_ROOT, ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py"),
              _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/simulation/engine.py"),
              _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/action_value_policy.py"),
              _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/evaluation_v1.py"))
    return {
        "schema": "g266-plain-baotou-entry-branch-manifest/1",
        "blocks": [{"panel_seed": seed, "roots": [min(roots), max(roots)]}
                   for seed, roots in BLOCKS],
        "smoke_roots": list(SMOKE_ROOTS),
        "mixes": list(MIXES), "focal_seats": list(SEATS),
        "samples": list(SAMPLES), "layer_priority": list(LAYERS),
        "quotas_per_mix": QUOTAS,
        "half_hash_parity_rule": "SHA256(ASCII panel_seed|mix|root_index) 最后一个字节 mod 2",
        "guide_version_metadata": 35,
        "guide_full_text_available": False,
        "rules_source_hash": rules_hash,
        "parent_algorithm_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "parent_binding": "research_current_rules_not_release_package",
        "versions": versions,
        "input_identity": {str(path.relative_to(ROOT)): digest(path)
                           for path in inputs},
        "boundary": "纯离线一次改弃机制诊断；非线上策略或发布准入。",
    }


def stage_path(out: Path, seed: int, mix: str, root: int, seat: int) -> Path:
    """用种子、对手池、牌山根和焦点座位唯一命名第一桌证据。"""
    return out / "stages" / f"p{seed}-{mix}-r{root:04d}-s{seat}.json"


def branch_path(out: Path, seed: int, mix: str, root: int) -> Path:
    """每个独立牌山根最多一条选定行动窗、九世界双臂分支。"""
    return out / "branches" / f"p{seed}-{mix}-r{root:04d}.json"


def positive_width(tiles: Any, *, excluded_code: str | None = None) -> tuple[int, int] | None:
    """计算正公开未见容量的牌码种数和张数；容量不是暗墙概率。"""
    if tiles is None:
        return None
    codes: set[str] = set()
    positive = []
    for tile in tiles:
        code, remaining = tile.code, tile.remaining_estimate
        if (not isinstance(code, str) or not code or code in codes
                or type(remaining) is not int or not 0 <= remaining <= 4):
            return None
        codes.add(code)
        if code != excluded_code and remaining > 0:
            positive.append(remaining)
    return len(positive), sum(positive)


def tile_vector(tiles: Any) -> list[dict[str, Any]] | None:
    """保留逐码公开容量，零容量也写入以便重算正容量宽度。"""
    if positive_width(tiles) is None:
        return None
    return [{"code": tile.code, "public_capacity": tile.remaining_estimate}
            for tile in sorted(tiles, key=lambda item: item.code)]


def score_record(ranked: Any) -> dict[str, Any] | None:
    """要求 R18 原评分分量、风险和合计完整；bool 不能冒充数字。"""
    trace = ranked.score_trace
    if not isinstance(trace, dict) or trace.get("trace_schema") != (
            "sitin-action-score-trace/1") or not isinstance(trace.get("detail"), dict):
        return None
    detail = trace["detail"]
    values = {name: detail.get(name) for name in (*SCORE_PARTS, "risk_units")}
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in values.values()) or values["risk_units"] < 0:
        return None
    score = ranked.total_score
    if type(score) not in (int, float) or not math.isfinite(score):
        return None
    risk_part = -round(6.0 * values["risk_units"], 1)
    other = float(score) - sum(float(values[name]) for name in SCORE_PARTS) - risk_part
    if not math.isfinite(other):
        return None
    return {"total_score": float(score), "score_trace": trace,
            "parts": {**{name: float(values[name]) for name in SCORE_PARTS},
                      "risk_units": float(values["risk_units"]),
                      "risk_part": risk_part, "other": other}}


def _fact_record(candidate: Any, ranked: Any, wealth_code: str) -> dict[str, Any] | None:
    """将一个合法弃牌的分牌型事实及评分解释转换成可审计标量。"""
    facts = candidate.facts
    if facts is None or getattr(facts.completeness, "value", None) != "complete":
        return None
    shanten = {"combined": facts.shanten_after,
               "standard": facts.standard_shanten_after,
               "seven_pairs": facts.seven_pairs_shanten_after}
    if any(type(value) is not int for value in shanten.values()):
        return None
    combined = positive_width(facts.useful_tiles)
    ordinary_all = positive_width(facts.standard_useful_tiles)
    ordinary_natural = positive_width(facts.standard_useful_tiles,
                                      excluded_code=wealth_code)
    seven = positive_width(facts.seven_pairs_useful_tiles)
    vectors = {"combined": tile_vector(facts.useful_tiles),
               "standard": tile_vector(facts.standard_useful_tiles),
               "seven_pairs": tile_vector(facts.seven_pairs_useful_tiles)}
    score = score_record(ranked)
    if (combined is None or ordinary_all is None or ordinary_natural is None
            or seven is None or any(value is None for value in vectors.values())
            or type(facts.baotou_after) is not bool or score is None):
        return None
    return {"action_key": candidate.action_key, "shanten": shanten,
            "combined_width": list(combined),
            "standard_width_all": list(ordinary_all),
            "standard_width_nonwhite": list(ordinary_natural),
            "standard_white_capacity": ordinary_all[1] - ordinary_natural[1],
            "seven_pairs_width": list(seven),
            "tile_vectors": vectors, "baotou_after": facts.baotou_after,
            "score": score}


def classify_window(request: Any, plan: Any) -> tuple[dict[str, dict[str, Any]], str]:
    """只用当前窗可见事实，给四层各挑一个事前固定备选。"""
    observation = request.observation
    if request.window_key.phase.value != "draw":
        return {}, "response_window"
    if observation.drawn_tile is None or observation.gang_draw is True:
        return {}, "not_normal_draw"
    # ActionValuePolicy 把成功标记也放在 degraded_reasons；不能因字段名
    # 把所有正常动作错判为降级。仅允许唯一的冻结 R18 成功标记。
    if request.rejected_attempts:
        return {}, "rejected_attempt_history"
    if tuple(plan.degraded_reasons) != (SUCCESS_REASON,):
        return {}, "score_not_frozen_success"
    if getattr(request.rules.completeness, "value", None) != "complete":
        return {}, "rules_incomplete"
    ranked = {item.action_key: item for item in plan.candidates}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if (not ranked or len(ranked) != len(plan.candidates)
            or len(legal) != len(request.rules.legal_candidates)
            or set(ranked) != set(legal)):
        return {}, "candidate_identity_mismatch"
    if "hu" in legal:
        return {}, "immediate_hu"
    parent_key = plan.candidates[0].action_key
    if not parent_key.startswith("discard:") or parent_key == "discard:白":
        return {}, "parent_not_nonwhite_discard"
    wealth_code = observation.rule_state.wealth_god.code
    if wealth_code != "白":
        raise ValueError("G266 杭麻财神代码不是白板，须先核官方规则")
    white_count = sum(code == wealth_code
                      for code in _hand_codes_without_double_count(observation))
    if white_count == 0:
        return {}, "zero_white"
    if white_count not in (1, 2):
        return {}, "white_count_not_one_or_two"
    discards = {key: item for key, item in legal.items()
                if key.startswith("discard:")}
    if any(item.value_facts is None or
           getattr(item.value_facts.coverage, "value", None) != "complete"
           for item in discards.values()):
        return {}, "value_facts_incomplete"
    capacities = {key: opportunity.action_opportunity(candidate)[0]
                  for key, candidate in discards.items()}
    if any(value["plain_baotou"] > 0 for value in capacities.values()):
        return {}, "already_plain_baotou_opportunity"
    parent = _fact_record(legal[parent_key], ranked[parent_key], wealth_code)
    if parent is None:
        return {}, "parent_facts_or_score_incomplete"
    standard, seven, combined = (parent["shanten"][name] for name in
                                 ("standard", "seven_pairs", "combined"))
    if not 1 <= standard <= 3:
        return {}, "parent_standard_outside_1_3"
    per_layer: dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]] = defaultdict(list)
    for key, candidate in discards.items():
        if key == parent_key or key == "discard:白" or key not in ranked:
            continue
        other = _fact_record(candidate, ranked[key], wealth_code)
        if other is None:
            continue
        if other["shanten"] != parent["shanten"]:
            continue
        parent_width = parent["standard_width_nonwhite"]
        other_width = other["standard_width_nonwhite"]
        gain_codes = other_width[0] - parent_width[0]
        gain_capacity = other_width[1] - parent_width[1]
        if gain_codes <= 0 or gain_capacity <= 0:
            continue
        if other["baotou_after"] != parent["baotou_after"]:
            continue
        parent_score, alternate_score = (item["score"] for item in (parent, other))
        risk_p = parent_score["parts"]["risk_units"]
        risk_a = alternate_score["parts"]["risk_units"]
        gap = parent_score["total_score"] - alternate_score["total_score"]
        if risk_a > risk_p + 1e-8 or gap <= 1e-8:
            continue
        combined_loss = max(0, parent["combined_width"][1] - other["combined_width"][1])
        seven_loss = max(0, parent["seven_pairs_width"][1] - other["seven_pairs_width"][1])
        cost = combined_loss > 0 or seven_loss > 0
        layers = []
        if (standard, seven) in ((2, 1), (3, 2)) and cost:
            layers.append("B_nonready")
        if (standard, seven) == (1, 0) and cost:
            layers.append("B_ready")
        if standard == seven and cost:
            layers.append("C")
        if ((standard, seven, combined) == (1, 0, 0)
                and other["combined_width"] == parent["combined_width"]
                and other["seven_pairs_width"][1] >= parent["seven_pairs_width"][1]
                and other["score"]["parts"]["base_score"] ==
                parent["score"]["parts"]["base_score"]):
            layers.append("A")
        evidence = {"layer_candidates": layers, "parent_action": parent_key,
                    "alternate_action": key, "parent": parent, "alternate": other,
                    "white_before": white_count,
                    "plain_baotou_legal_capacity": capacities,
                    "nonwhite_standard_width_gain": [gain_codes, gain_capacity],
                    "combined_capacity_loss": combined_loss,
                    "seven_pairs_capacity_loss": seven_loss,
                    "parent_score_gap": gap}
        tie = (-gain_codes, -gain_capacity, combined_loss, seven_loss, gap, key)
        for layer in layers:
            per_layer[layer].append((tie, evidence))
    selected = {layer: min(items, key=lambda item: item[0])[1]
                for layer, items in per_layer.items()}
    return selected, "eligible" if selected else "no_layer_qualified"


@dataclass
class CapturedWindow:
    """仅运行期保存目标世界；选择逻辑没有 WorldState 参数。"""

    world: Any
    request: Any
    parent_key: str
    alternate_key: str
    row: dict[str, Any]


class LayerCapturePolicy:
    """透明返回父代计划；每层只留本座第一张完整桌的最早合法窗。"""

    def __init__(self, inner: Any, engine: g93.CaptureEngine) -> None:
        self.inner, self.engine = inner, engine
        self.policy_id = inner.policy_id
        self.max_operations = getattr(inner, "max_operations", None)
        self.hits: dict[str, CapturedWindow] = {}
        self.rejections: Counter[str] = Counter()
        self.negative_controls: dict[str, dict[str, Any]] = {}
        self.decision_order = 0

    async def choose(self, request: Any, budget: Any) -> Any:
        """只读父代计划与同窗 PlayerObservation，随后才暂存不透明世界。"""
        plan = await self.inner.choose(request, budget)
        self.decision_order += 1
        if len(self.hits) == len(LAYERS):
            return plan
        selected, reason = classify_window(request, plan)
        self.rejections[reason] += 1
        if (reason in NEGATIVE_CONTROL_REASONS
                and reason not in self.negative_controls and plan.candidates):
            self.negative_controls[reason] = {
                "decision_id": request.decision_id,
                "round_no": request.window_key.round_no,
                "trigger_seq": request.trigger_seq,
                "seat": request.observation.seat,
                "phase": request.window_key.phase.value,
                "parent_action": plan.candidates[0].action_key,
            }
        for layer, evidence in selected.items():
            if layer in self.hits:
                continue
            if self.engine.latest_world is None:
                raise ValueError("G266 捕获窗口缺同帧世界")
            row = {"layer": layer, "decision_order": self.decision_order,
                   "decision_id": request.decision_id,
                   "game_id": request.window_key.game_id,
                   "round_no": request.window_key.round_no,
                   "trigger_seq": request.trigger_seq,
                   "seat": request.observation.seat,
                   "scores_by_seat": list(request.observation.scores),
                   **evidence}
            self.hits[layer] = CapturedWindow(
                world=self.engine.latest_world, request=request,
                parent_key=evidence["parent_action"],
                alternate_key=evidence["alternate_action"], row=row)
        return plan


def parent_policies(plan: Any, contract: dict, clock: Any, mix: str) -> tuple[Any, ...]:
    """独立注入当前规则研究父代；不调用 G95 的旧发布包工厂。"""
    natural = g93.natural
    logical = natural.arm_logical_policies(
        arm="candidate", candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        monotonic=clock.now,
        candidate_policy_factory=current.research_parent_factory)
    return natural.seat_policies_from(logical, plan.permutation,
                                      plan.logical_participants)


def _runtime_clean(counts: Any, where: str) -> dict[str, int]:
    """任何自动动作、超时、降级或审计缺口都使该完整桌无效。"""
    values = asdict(counts)
    for name in RUNTIME_ZERO:
        if type(values.get(name)) is not int or values[name] != 0:
            raise ValueError(f"G266 {where} 的 {name} 非零或缺失")
    return values


def _settlement(hand: dict[str, Any]) -> dict[str, Any]:
    """只存规则权威结算字段，独立于模拟器内部隐藏状态。"""
    return {name: hand[name] for name in SETTLEMENT_FIELDS}


def _json_canonical(value: Any) -> Any:
    """内存元组与落盘 JSON 数组按同一线格式比较，拒绝实际字段漂移。"""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                 allow_nan=False))


def run_parent_table(plan: Any, contract: dict, versions: dict, mix: str):
    """完成第一张八单局父代表，并按每层最早窗保存运行期世界引用。"""
    runtime, spec, rules = g93.runtime_for(plan, versions)
    inner = g93.HandAccountingEngine(runtime["engine"])
    engine = g93.CaptureEngine(inner)
    clock = g93.ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(parent_policies(plan, contract, clock, mix))
    focal = plan.seats().index(g93.natural.FOCAL_PARTICIPANT)
    captured = LayerCapturePolicy(policies[focal], engine)
    policies[focal] = captured
    situation = g93.natural.build_stage_situation(
        plan=plan, table_no=1, tables_completed=0, totals={}, place_totals={},
        rounds_per_game=int(versions["rounds_per_game"]))
    config = g93.MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=g93.BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    outcome = asyncio.run(g93.drive_match(
        engine=engine, spec=spec, policies_by_seat=tuple(policies), rules=rules,
        choice_factory=runtime["choice_factory"], config=config,
        now_monotonic=clock.now, wall_clock=None,
        value_limits=g93.paired.LIMITS, stage_situation=situation))
    if outcome.status != "complete" or len(inner.hands) != int(versions["rounds_per_game"]):
        raise ValueError("G266 父代表未完成八单局")
    counts = _runtime_clean(outcome.runtime_counts, "父代表")
    final = list(outcome.final_scores or ())
    if len(final) != 4:
        raise ValueError("G266 父代表终分不是四座向量")
    account = summarize_hands(inner.hands, focal_seat=focal,
                              initial_scores=inner.hands[0]["scores_before"],
                              final_scores=final,
                              expected_hands=int(versions["rounds_per_game"]))
    decision_sequence = [(dict(item.window_key), item.action_key)
                         for item in outcome.decisions]
    actual_by_id = {item.decision_id: item.action_key
                    for item in outcome.decisions}
    if len(actual_by_id) != len(outcome.decisions):
        raise ValueError("G266 父代表决策身份重复")
    for control in captured.negative_controls.values():
        if actual_by_id.get(control["decision_id"]) != control["parent_action"]:
            raise ValueError("G266 负对照包装器改变父代实际首选")
    sequence_hash = sha256(json.dumps(
        decision_sequence, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    row = {"table_id": plan.table_id, "focal_seat": focal,
           "final_scores": final,
           "hands": [_settlement(hand) for hand in inner.hands],
           "account": account, "runtime_counts": counts,
           "decision_sequence_sha256": sequence_hash,
           "layers": {layer: hit.row for layer, hit in captured.hits.items()},
           "rejections": dict(captured.rejections),
           "negative_controls": captured.negative_controls}
    return row, captured, runtime, rules, situation, inner.hands, outcome


def classify_hand(hand: dict[str, Any], focal: int) -> str:
    """按目标单局权威结算划六类，平胡爆头与七对单列。"""
    if hand["is_draw"] is True:
        return "draw"
    if hand["winner_seat"] != focal:
        return "other_win"
    details = hand["details"]
    if not isinstance(details, (list, tuple)) or not details:
        raise ValueError("G266 胡牌明细缺失")
    if details[0] == "平胡":
        return "plain_baotou" if "爆头" in details else "plain_no_baotou"
    if details[0] == "七对" or details[0].startswith("豪华七对×"):
        return "seven_pairs"
    return "other_self_special"


def classify_income(hands: list[dict[str, Any]], focal: int,
                    final_scores: list[int]) -> dict[str, Any]:
    """八单局互斥分账；六类净分必须与本座完整桌终分恒等。"""
    if len(hands) != 8 or len(final_scores) != 4:
        raise ValueError("G266 分类分账需要八局与四座终分")
    by_class = {name: {"count": 0, "focal_net_score": 0}
                for name in HAND_CLASSES}
    labels = []
    piao_tags = []
    for hand in hands:
        label = classify_hand(hand, focal)
        score = hand["score_delta"][focal]
        if type(score) is not int:
            raise ValueError("G266 分类分账非整数积分")
        by_class[label]["count"] += 1
        by_class[label]["focal_net_score"] += score
        labels.append(label)
        piao_tags.append([detail for detail in (hand["details"] or [])
                          if isinstance(detail, str)
                          and ("飘" in detail)]
                         if hand["winner_seat"] == focal else [])
    if (sum(part["count"] for part in by_class.values()) != 8
            or sum(part["focal_net_score"] for part in by_class.values()) !=
            final_scores[focal] - hands[0]["scores_before"][focal]):
        raise ValueError("G266 六类分账与完整桌终分不守恒")
    return {"by_class": by_class, "hand_labels": labels,
            "piao_tags_by_hand": piao_tags}


def _read_manifest(out: Path) -> dict[str, Any]:
    """创建或核验完全相同的清单；源码变更后禁止混合断点证据。"""
    frozen = manifest()
    write_new(out / "manifest.json", frozen)
    return frozen


def _plan(seed: int, mix: str, root: int, seat: int, contract: dict) -> Any:
    """仅取每个阶段的第一张完整桌；后续桌竞争状态不作无据猜测。"""
    if seed not in (BLOCKS[0][0], BLOCKS[1][0]):
        raise ValueError("G266 未预登记的牌山种子")
    if mix not in MIXES or type(root) is not int or not 1 <= root <= 66 or seat not in SEATS:
        raise ValueError("G266 非预登记池、根或座位")
    plans = g93.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=seed)
    if len(plans) < 1:
        raise ValueError("G266 阶段无第一桌")
    return plans[0]


def scan_stage(*, out: Path, seed: int, mix: str, root: int, seat: int,
               contract: dict, versions: dict, manifest_sha256: str) -> dict[str, Any]:
    """单座父代表可断点重跑；入选事实在驱动结算前已经于策略包装器确定。"""
    path = stage_path(out, seed, mix, root, seat)
    if path.exists():
        row = json.loads(path.read_text(encoding="utf-8"))
        if any(row.get(name) != value for name, value in (
                ("panel_seed", seed), ("mix", mix), ("root_index", root),
                ("focal_seat", seat), ("manifest_sha256", manifest_sha256))):
            raise ValueError("G266 已存扫描阶段身份漂移")
        return row
    plan = _plan(seed, mix, root, seat, contract)
    parent, _capture, _runtime, _rules, _situation, _hands, _outcome = (
        run_parent_table(plan, contract, versions, mix))
    if parent["focal_seat"] != seat:
        raise ValueError("G266 计划物理座位与捕获座位漂移")
    row = {"schema": "g266-parent-first-table-stage/1",
           "manifest_sha256": manifest_sha256, "panel_seed": seed,
           "mix": mix, "root_index": root, "focal_seat": seat,
           "table": parent}
    write_new(path, row)
    return row


def _root_identity(seed: int, mix: str, root: int) -> str:
    """两个种子相同编号根严格独立，哈希不含后验结果。"""
    return f"{seed}|{mix}|{root}"


def _hash_order(seed: int, mix: str, root: int, layer: str) -> str:
    """固定超配额子集的字典序排序键。"""
    return sha256(f"{_root_identity(seed, mix, root)}|{layer}".encode()).hexdigest()


def _half(seed: int, mix: str, root: int) -> str:
    """牌山根哈希奇偶固定两个重复诊断半批。"""
    value = sha256(_root_identity(seed, mix, root).encode()).digest()
    return "even" if value[-1] % 2 == 0 else "odd"


def _representative(seed: int, mix: str, root: int, layer: str,
                    out: Path, manifest_sha256: str) -> dict[str, Any] | None:
    """四座各取最早窗后，按单局、序号、轮转座位序选根级代表。"""
    hits = []
    for seat in SEATS:
        row = json.loads(stage_path(out, seed, mix, root, seat).read_text(encoding="utf-8"))
        if row.get("manifest_sha256") != manifest_sha256:
            raise ValueError("G266 扫描阶段清单漂移")
        hit = row["table"]["layers"].get(layer)
        if hit is not None:
            if hit["seat"] != seat or hit["layer"] != layer:
                raise ValueError("G266 行动窗层级或座位身份漂移")
            hits.append(hit)
    if not hits:
        return None
    return min(hits, key=lambda hit: (hit["round_no"], hit["trigger_seq"],
                                      (hit["seat"] - root % 4) % 4))


def _block_roots(out: Path, seed: int, manifest_sha256: str) -> list[dict[str, Any]]:
    """只读取完整父代表的行动前层级事实，绝不打开分支收益文件。"""
    roots = []
    for mix in MIXES:
        for root in range(3, 67):
            paths = [stage_path(out, seed, mix, root, seat) for seat in SEATS]
            if any(not path.is_file() for path in paths):
                raise ValueError("G266 首块／扩样块尚未扫描完四座")
            candidates = {layer: _representative(
                seed, mix, root, layer, out, manifest_sha256) for layer in LAYERS}
            winner = next((layer for layer in LAYERS if candidates[layer] is not None), None)
            roots.append({"panel_seed": seed, "mix": mix, "root_index": root,
                          "root_identity": _root_identity(seed, mix, root),
                          "half": _half(seed, mix, root),
                          "exposed_layers": [layer for layer in LAYERS
                                             if candidates[layer] is not None],
                          "priority_layer": winner,
                          "priority_hit": None if winner is None else candidates[winner]})
    return roots


def freeze_selection(out: Path, manifest_sha256: str) -> dict[str, Any]:
    """先完成 B 主层暴露和条件扩样，才冻结根优先级与配额。"""
    if (out / "branches").exists() and any((out / "branches").iterdir()):
        raise ValueError("G266 分支收益已经落盘，拒绝事后冻结选择")
    first = _block_roots(out, BLOCKS[0][0], manifest_sha256)
    counts = {mix: sum(row["priority_layer"] == "B_nonready" for row in first
                       if row["mix"] == mix) for mix in MIXES}
    extension = any(count < 12 for count in counts.values())
    opened = first + (_block_roots(out, BLOCKS[1][0], manifest_sha256)
                      if extension else [])
    all_counts = {mix: sum(row["priority_layer"] == "B_nonready" for row in opened
                           if row["mix"] == mix) for mix in MIXES}
    branch_allowed = all(count >= 12 for count in all_counts.values())
    selected_identities = set()
    if branch_allowed:
        for mix in MIXES:
            for layer in LAYERS:
                candidates = [row for row in opened if row["mix"] == mix
                              and row["priority_layer"] == layer]
                candidates.sort(key=lambda row: _hash_order(
                    row["panel_seed"], mix, row["root_index"], layer))
                selected_identities.update(
                    row["root_identity"] for row in candidates[:QUOTAS[layer]])
    for row in opened:
        if row["priority_layer"] is None:
            row["selection_status"] = "no_layer_exposure"
        elif not branch_allowed:
            row["selection_status"] = "main_layer_exposure_insufficient"
        elif row["root_identity"] in selected_identities:
            row["selection_status"] = "selected"
        else:
            row["selection_status"] = "quota_not_selected"
    selected = [row for row in opened if row["selection_status"] == "selected"]
    evidence = {
        "schema": "g266-result-blind-root-selection/1",
        "manifest_sha256": manifest_sha256,
        "first_block_main_exposed_roots": counts,
        "second_block_opened": extension,
        "all_main_exposed_roots": all_counts,
        "branch_allowed": branch_allowed,
        "selected_roots": len(selected),
        "roots": opened,
        "result_blind": True,
        "selection_source": "only pre-action per-layer hits from complete parent tables",
    }
    write_new(out / "selection.json", evidence)
    return evidence


def _opportunity_status(request: Any) -> str:
    """同 G138 计算本窗全部合法弃牌；未知保持 unknown。"""
    legal = request.rules.legal_candidates
    discards = [item for item in legal if item.action_key.startswith("discard:")]
    if not discards:
        return "not_discard_window"
    values = [opportunity.action_opportunity(item) for item in discards]
    if any(capacity["plain_baotou"] > 0 for capacity, _complete in values):
        return "yes"
    return "no" if all(complete for _capacity, complete in values) else "unknown"


class OpportunityTimelinePolicy:
    """赛后机制标签旁路：只采集本人目标单局的真实可行动观察。"""

    def __init__(self, inner: Any, target: Any) -> None:
        self.inner, self.target = inner, target
        self.policy_id = inner.policy_id
        self.max_operations = getattr(inner, "max_operations", None)
        self.events: list[dict[str, Any]] = []
        self.started = False

    async def choose(self, request: Any, budget: Any) -> Any:
        """机制旁路不改变计划；G138 状态按动作前全部合法弃牌计算。"""
        plan = await self.inner.choose(request, budget)
        if request.window_key == self.target:
            self.started = True
        if (self.started and request.window_key.round_no == self.target.round_no
                and request.window_key.phase.value == "draw"):
            self.events.append({"round_no": request.window_key.round_no,
                                "trigger_seq": request.trigger_seq,
                                "status": _opportunity_status(request),
                                "selected_action": plan.candidates[0].action_key})
        return plan


def _timeline_summary(events: list[dict[str, Any]], target_class: str) -> dict[str, Any]:
    """首次入机会以所有分支为分母；绝不只观察幸存到本人下一摸者。"""
    if not events or events[0]["status"] != "no":
        raise ValueError("G266 根窗的 G138 普通爆头机会应完整且为无")
    later = events[1:]
    entered = any(event["status"] == "yes" for event in later)
    transitions = []
    exits = []
    maintained = 0
    previous = events[0]["status"]
    for event in later:
        current_status = event["status"]
        if previous == "yes" and current_status == "yes":
            maintained += 1
        if current_status != previous:
            transitions.append({"trigger_seq": event["trigger_seq"],
                                "from": previous, "to": current_status})
            if previous == "yes":
                exits.append({"trigger_seq": event["trigger_seq"],
                              "reason": ("opportunity_disappeared"
                                         if current_status == "no" else
                                         "unknown_coverage")})
        previous = current_status
    if previous == "yes":
        terminal = ("other_player_won" if target_class == "other_win" else
                    "draw" if target_class == "draw" else "own_hu")
        exits.append({"trigger_seq": None, "reason": terminal})
    return {"first_entered_before_target_end": entered,
            "unknown_after_root": any(event["status"] == "unknown" for event in later),
            "transitions": transitions,
            "maintained_yes_windows": maintained,
            "exits": exits,
            "target_end": target_class,
            "entered_then_other_win": entered and target_class == "other_win",
            "events": events}


def run_branch(*, world: Any, captured: CapturedWindow, plan: Any,
               contract: dict, versions: dict, runtime: dict, rules: Any,
               situation: Any, mix: str, forced_key: str | None,
               prefix_hands: list[dict[str, Any]]) -> dict[str, Any]:
    """借用 G182 公开结算引擎，显式注入当前规则父代续至八局。"""
    target = captured.request.window_key
    accounting = old_branch.SettlementOnlyTableEngine(runtime["engine"])
    clock = g93.ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(parent_policies(plan, contract, clock, mix))
    force = None
    if forced_key is not None:
        force = g93.ForceOncePolicy(policies[target.seat], target, forced_key)
        policies[target.seat] = force
    timeline = OpportunityTimelinePolicy(policies[target.seat], target)
    policies[target.seat] = timeline
    initial_frame = runtime["engine"].frame(world)
    if (len(initial_frame.decisions) != 1
            or initial_frame.decisions[0].observation != captured.request.observation
            or list(initial_frame.decisions[0].observation.scores)
            != captured.row["scores_by_seat"]):
        raise ValueError("G266 两臂起点观察或座位积分不恒等")
    snapshot = {"observation_summary": g93.frame_observation_summary(initial_frame),
                "match_spec": {"match_id": plan.match_id}}
    config = g93.MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=g93.BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    start = time.perf_counter()
    outcome = asyncio.run(g93.resume_match(
        engine=accounting, world=world, policies_by_seat=tuple(policies),
        rules=rules, choice_factory=runtime["choice_factory"],
        config=config, now_monotonic=clock.now, wall_clock=None,
        stage_snapshot=snapshot,
        remaining_schedule={"declared_endpoint": "complete_table"},
        value_limits=g93.paired.LIMITS, stage_situation=situation))
    if outcome.status != "complete" or outcome.completed_hands != 8:
        raise ValueError("G266 同世界分支未完成八局")
    if force is not None and force.used != 1:
        raise ValueError("G266 备选动作未恰好执行一次")
    counts = _runtime_clean(outcome.runtime_counts, "分支")
    expected = captured.parent_key if forced_key is None else forced_key
    if not outcome.decisions or outcome.decisions[0].action_key != expected:
        raise ValueError("G266 分支首动作与冻结行动对不符")
    hands = list(prefix_hands) + accounting.hands
    final = list(outcome.final_scores or ())
    account = summarize_hands(
        hands, focal_seat=target.seat,
        initial_scores=hands[0]["scores_before"], final_scores=final,
        expected_hands=8)
    classes = classify_income(hands, target.seat, final)
    target_class = classes["hand_labels"][target.round_no - 1]
    return {"final_scores": final, "hands": hands,
            "account": account, "income": classes,
            "target_hand": _settlement(hands[target.round_no - 1]),
            "target_class": target_class,
            "timeline": _timeline_summary(timeline.events, target_class),
            "first_action": outcome.decisions[0].action_key,
            "decisions": [(dict(item.window_key), item.action_key)
                          for item in outcome.decisions],
            "decision_count": len(outcome.decisions),
            "forced_once": 0 if force is None else force.used,
            "runtime_counts": counts,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3)}


def _compact_branch(row: dict[str, Any]) -> dict[str, Any]:
    """结果只留完整桌结算、机制标签和恒等审计，避免重复决策大数组。"""
    return {name: value for name, value in row.items() if name != "decisions"}


def branch_root(selected: dict[str, Any], *, out: Path, contract: dict,
                versions: dict, manifest_sha256: str,
                selection_sha256: str) -> dict[str, Any]:
    """同根九世界双臂；原历史世界父代逐动作、逐局、终分恒等。"""
    seed, mix, root = (selected[name] for name in
                       ("panel_seed", "mix", "root_index"))
    hit_row = selected["priority_hit"]
    seat, layer = hit_row["seat"], selected["priority_layer"]
    staged = json.loads(stage_path(out, seed, mix, root, seat).read_text(encoding="utf-8"))
    if staged["manifest_sha256"] != manifest_sha256:
        raise ValueError("G266 目标父代表清单漂移")
    plan = _plan(seed, mix, root, seat, contract)
    parent_row, capture, runtime, rules, situation, hands, original = (
        run_parent_table(plan, contract, versions, mix))
    if _json_canonical(parent_row) != staged["table"]:
        raise ValueError("G266 复跑父代表与结果盲扫描证据不恒等")
    if (layer not in capture.hits
            or _json_canonical(capture.hits[layer].row) != hit_row):
        raise ValueError("G266 入选层目标行动前事实复跑漂移")
    captured = capture.hits[layer]
    target = captured.request.window_key
    initial_observation = runtime["engine"].frame(captured.world).decisions[0].observation
    pairs = []
    for sample in SAMPLES:
        world = (captured.world if sample == "historical" else
                 runtime["engine"].resample_public_consistent_hidden_world(
                     captured.world, focal_seat=seat, sample_key=sample))
        frame = runtime["engine"].frame(world)
        if (len(frame.decisions) != 1
                or frame.decisions[0].observation != initial_observation
                or list(frame.decisions[0].observation.scores)
                != hit_row["scores_by_seat"]):
            raise ValueError("G266 隐藏世界重采样改变行动前可见观察／积分")
        prefix = hands[:target.round_no - 1]
        parent = run_branch(
            world=world, captured=captured, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=mix, forced_key=None,
            prefix_hands=prefix)
        alternate = run_branch(
            world=world, captured=captured, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=mix, forced_key=captured.alternate_key,
            prefix_hands=prefix)
        if (parent["hands"][0]["scores_before"]
                != alternate["hands"][0]["scores_before"]):
            raise ValueError("G266 双臂完整桌起点积分不等")
        if sample == "historical":
            if ([_settlement(hand) for hand in parent["hands"]]
                    != [_settlement(hand) for hand in hands]
                    or parent["final_scores"] != list(original.final_scores or ())
                    or parent["decisions"] != old_branch._decisions(original, target)):
                raise ValueError("G266 原历史世界父代分支逐动作／结算／终分不恒等")
        pairs.append({
            "sample_key": sample,
            "focal_complete_table_delta": (alternate["final_scores"][seat]
                                           - parent["final_scores"][seat]),
            "focal_target_hand_delta": (
                alternate["target_hand"]["score_delta"][seat]
                - parent["target_hand"]["score_delta"][seat]),
            "parent": _compact_branch(parent),
            "alternate": _compact_branch(alternate),
        })
    return {"schema": "g266-plain-baotou-entry-root-branch/1",
            "manifest_sha256": manifest_sha256,
            "selection_sha256": selection_sha256,
            "identity": {"panel_seed": seed, "mix": mix, "root_index": root,
                         "root_identity": selected["root_identity"],
                         "half": selected["half"], "focal_seat": seat,
                         "layer": layer, "hit": hit_row},
            "paired_worlds": pairs}


def _mean(values: list[float]) -> float | None:
    """空格不填 0；分支配额未抽中的根没有效果值。"""
    return sum(values) / len(values) if values else None


def _cluster_interval(values: list[float], seed: int) -> list[float] | None:
    """独立牌山根有放回抽样；九隐藏世界先在根内平均。"""
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(5000))
    return [draws[124], draws[4874]]


def _per_root(branch: dict[str, Any]) -> dict[str, Any]:
    """每个独立根的九世界先配对，再供 H/M 与半批聚合。"""
    pairs = branch["paired_worlds"]
    if [pair["sample_key"] for pair in pairs] != list(SAMPLES):
        raise ValueError("G266 根分支九世界清单不完整")
    income = {}
    for category in HAND_CLASSES:
        income[category] = _mean([
            pair["alternate"]["income"]["by_class"][category]["focal_net_score"]
            - pair["parent"]["income"]["by_class"][category]["focal_net_score"]
            for pair in pairs])
    unknown_pairs = sum(
        pair[arm]["timeline"]["unknown_after_root"]
        for pair in pairs for arm in ("parent", "alternate"))
    first_enter_delta = (None if unknown_pairs else _mean([
        int(pair["alternate"]["timeline"]["first_entered_before_target_end"])
        - int(pair["parent"]["timeline"]["first_entered_before_target_end"])
        for pair in pairs]))
    return {"identity": branch["identity"],
            "mean_table_delta": _mean([pair["focal_complete_table_delta"]
                                       for pair in pairs]),
            "mean_target_hand_delta": _mean([pair["focal_target_hand_delta"]
                                             for pair in pairs]),
            "historical_table_delta": pairs[0]["focal_complete_table_delta"],
            "first_four_resampled_table_delta": _mean([
                pair["focal_complete_table_delta"] for pair in pairs[1:5]]),
            "last_four_resampled_table_delta": _mean([
                pair["focal_complete_table_delta"] for pair in pairs[5:]]),
            "first_enter_delta": first_enter_delta,
            "first_enter_unknown_arm_worlds": unknown_pairs,
            "focal_income_delta": income,
            "target_classes": {
                arm: dict(Counter(pair[arm]["target_class"] for pair in pairs))
                for arm in ("parent", "alternate")},
            "entered_then_other_win": {
                arm: sum(pair[arm]["timeline"]["entered_then_other_win"]
                         for pair in pairs)
                for arm in ("parent", "alternate")},
            "resampled_positive_worlds": sum(pair["focal_complete_table_delta"] > 0
                                             for pair in pairs[1:]),
            "resampled_negative_worlds": sum(pair["focal_complete_table_delta"] < 0
                                             for pair in pairs[1:])}


def _group_summary(roots: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    """按根等权；条件效果、先入机会与普通/七对竞争损益分别给出。"""
    values = [row["mean_table_delta"] for row in roots]
    sorted_values = sorted(values, reverse=True)
    incomes = {category: _mean([row["focal_income_delta"][category]
                                for row in roots]) for category in HAND_CLASSES}
    if roots and abs(sum(incomes.values()) - _mean(values)) > 1e-8:
        raise ValueError("G266 分类根均值与完整桌配对效果不守恒")
    first_enter_complete = all(row["first_enter_delta"] is not None for row in roots)
    by_half = {}
    for half in ("even", "odd"):
        subset = [row for row in roots if row["identity"]["half"] == half]
        half_complete = all(row["first_enter_delta"] is not None for row in subset)
        by_half[half] = {"n": len(subset),
                         "mean_table_delta": _mean([
                             row["mean_table_delta"] for row in subset]),
                         "first_enter_complete": half_complete,
                         "mean_first_enter_delta": (_mean([
                             row["first_enter_delta"] for row in subset])
                             if half_complete else None)}
    return {"independent_roots": len(roots),
            "mean_table_delta": _mean(values),
            "root_cluster_95pct_interval": _cluster_interval(values, seed),
            "mean_target_hand_delta": _mean([
                row["mean_target_hand_delta"] for row in roots]),
            "first_enter_complete": first_enter_complete,
            "first_enter_unknown_arm_worlds": sum(
                row["first_enter_unknown_arm_worlds"] for row in roots),
            "mean_first_enter_delta": (_mean([
                row["first_enter_delta"] for row in roots])
                if first_enter_complete else None),
            "mean_focal_income_delta": incomes,
            "half": by_half,
            "mean_without_best_root": _mean(sorted_values[1:]),
            "mean_without_best_two_roots": _mean(sorted_values[2:]),
            "positive_roots": sum(value > 0 for value in values),
            "negative_roots": sum(value < 0 for value in values),
            "zero_roots": sum(value == 0 for value in values),
            "minimum_root_delta": min(values) if values else None,
            "maximum_root_delta": max(values) if values else None,
            "first_four_resampled_mean": _mean([
                row["first_four_resampled_table_delta"] for row in roots]),
            "last_four_resampled_mean": _mean([
                row["last_four_resampled_table_delta"] for row in roots]),
            "target_classes": {arm: dict(sum((Counter(row["target_classes"][arm])
                                               for row in roots), Counter()))
                               for arm in ("parent", "alternate")},
            "entered_then_other_win": {arm: sum(
                row["entered_then_other_win"][arm] for row in roots)
                for arm in ("parent", "alternate")}}


def _main_gate_for_mix(main: dict[str, Any], exposed_roots: int) -> dict[str, Any]:
    """只为 B_nonready 判继续；机会覆盖未知必定 fail-closed。"""
    income = main["mean_focal_income_delta"]
    loss = max(0, -(income["plain_no_baotou"] or 0)) + max(
        0, -(income["seven_pairs"] or 0))
    baotou_gain = max(0, income["plain_baotou"] or 0)
    return {
        "exposure_at_least_12": exposed_roots >= 12,
        "conditional_mean_positive": (main["mean_table_delta"] or 0) > 0,
        "both_halves_positive": all(
            (main["half"][half]["mean_table_delta"] or 0) > 0
            for half in ("even", "odd")),
        "without_best_positive": (main["mean_without_best_root"] or 0) > 0,
        "first_enter_complete": main["first_enter_complete"],
        "first_enter_positive": (main["first_enter_complete"]
                                 and (main["mean_first_enter_delta"] or 0) > 0),
        "ordinary_or_seven_loss": loss,
        "plain_baotou_gain_floor_zero": baotou_gain,
        "route_cost_not_above_baotou_gain": loss <= baotou_gain,
        "two_best_roots_sensitivity_positive": (
            main["mean_without_best_two_roots"] or 0) > 0,
    }


def summarize(out: Path, selection: dict[str, Any],
              manifest_sha256: str) -> dict[str, Any]:
    """只在全数入选根完成后给出各层各池分账与预注册继续门。"""
    if not selection["branch_allowed"]:
        raise ValueError("G266 B_nonready 暴露不足；本轮不打开参照层效果")
    selection_sha = digest(out / "selection.json")
    roots = []
    for selected in selection["roots"]:
        if selected["selection_status"] != "selected":
            continue
        path = branch_path(out, selected["panel_seed"], selected["mix"],
                           selected["root_index"])
        if not path.exists():
            raise ValueError("G266 入选根分支未完成：" + str(path))
        branch = json.loads(path.read_text(encoding="utf-8"))
        if (branch.get("manifest_sha256") != manifest_sha256
                or branch.get("selection_sha256") != selection_sha
                or branch["identity"]["root_identity"]
                != selected["root_identity"]):
            raise ValueError("G266 分支文件冻结身份漂移")
        roots.append(_per_root(branch))
    groups = {}
    for layer in LAYERS:
        groups[layer] = {}
        for mix_index, mix in enumerate(MIXES):
            subset = [row for row in roots
                      if row["identity"]["layer"] == layer
                      and row["identity"]["mix"] == mix]
            groups[layer][mix] = _group_summary(
                subset, seed=2026122966 + LAYERS.index(layer) * 10 + mix_index)
    gates = {mix: _main_gate_for_mix(
        groups["B_nonready"][mix], selection["all_main_exposed_roots"][mix])
        for mix in MIXES}
    hard_names = ("exposure_at_least_12", "conditional_mean_positive",
                  "both_halves_positive", "without_best_positive",
                  "first_enter_complete", "first_enter_positive",
                  "route_cost_not_above_baotou_gain")
    continue_diagnosis = all(gates[mix][name] for mix in MIXES for name in hard_names)
    result = {"schema": "g266-plain-baotou-entry-branch-result/1",
              "manifest_sha256": manifest_sha256,
              "selection_sha256": selection_sha,
              "selected_independent_roots": len(roots),
              "groups": groups,
              "root_rows": roots,
              "B_nonready_continue_diagnosis_gate": {
                  "per_mix": gates,
                  "hard_gate_names": list(hard_names),
                  "all_hard_gates_pass": continue_diagnosis,
                  "scope": "仅允许另开独立更大样本；不得视为在线候选准入。",
                  "two_best_roots_sensitivity_is_diagnostic": True,
              },
              "interpretation_boundary": (
                  "条件一次改弃后回父代的局部完整桌效果；不代表持续策略自然场均，"
                  "隐藏世界重采样未按历史动作后验加权。"),
              }
    write_new(out / "result.json", result)
    return result


@dataclass(frozen=True)
class RunSegment:
    """一段连续主动运行；时间用单调钟计，累计额为所有已闭合段之和。"""

    name: str
    phase: str
    started_monotonic: float
    deadline_monotonic: float
    prior_active_seconds: float
    manifest_sha256: str
    selection_sha256: str | None


def begin_segment(out: Path, *, phase: str, requested_seconds: int,
                  manifest_sha256: str,
                  selection_sha256: str | None = None) -> RunSegment:
    """追加 start 证据；总主动运行额度仅 9000 秒，未闭合段拒绝静默略过。"""
    if phase not in ("scan", "branch") or type(requested_seconds) is not int:
        raise ValueError("G266 运行段阶段或预算类型非法")
    if not 1 <= requested_seconds <= 9000:
        raise ValueError("G266 单段预算需为 1..9000 秒")
    directory = out / "segments"
    prior = 0.0
    for start_path in sorted(directory.glob("*.start.json")):
        finish_path = start_path.with_name(
            start_path.name.replace(".start.json", ".finish.json"))
        if not finish_path.is_file():
            raise ValueError("G266 存在未闭合运行段，须核错误证据后处理：" +
                             str(start_path))
        start_row = json.loads(start_path.read_text(encoding="utf-8"))
        finish_row = json.loads(finish_path.read_text(encoding="utf-8"))
        if (start_row.get("manifest_sha256") != manifest_sha256
                or finish_row.get("manifest_sha256") != manifest_sha256
                or finish_row.get("segment_name") != start_row.get("segment_name")
                or finish_row.get("status") not in ("complete", "paused", "error")
                or type(finish_row.get("active_seconds")) not in (int, float)
                or finish_row["active_seconds"] < 0):
            raise ValueError("G266 历史运行段清单或主动时间漂移")
        if finish_row["status"] == "error":
            raise ValueError("G266 历史运行段异常；先核错误证据，不自动续跑")
        prior += float(finish_row["active_seconds"])
    remaining = 9000.0 - prior
    if remaining <= 0:
        raise ValueError("G266 累计主动运行已达150分钟；停线审资源与设计")
    granted = min(float(requested_seconds), remaining)
    name = f"segment-{time.time_ns()}-{os.getpid()}"
    started = time.monotonic()
    segment = RunSegment(
        name=name, phase=phase, started_monotonic=started,
        deadline_monotonic=started + granted,
        prior_active_seconds=prior, manifest_sha256=manifest_sha256,
        selection_sha256=selection_sha256)
    write_new(directory / f"{name}.start.json", {
        "schema": "g266-run-segment-start/1",
        "segment_name": name, "phase": phase,
        "started_unix_seconds": time.time(),
        "prior_active_seconds": round(prior, 6),
        "remaining_total_seconds_before": round(remaining, 6),
        "requested_segment_seconds": requested_seconds,
        "granted_segment_seconds": round(granted, 6),
        "total_active_limit_seconds": 9000,
        "manifest_sha256": manifest_sha256,
        "selection_sha256": selection_sha256,
    })
    return segment


def finish_segment(out: Path, segment: RunSegment, *, status: str,
                   error: Exception | None = None) -> None:
    """追加 finish 证据，保留主动耗时与根边界状态供恢复审计。"""
    if status not in ("complete", "paused", "error"):
        raise ValueError("G266 运行段结束状态非法")
    elapsed = max(0.0, time.monotonic() - segment.started_monotonic)
    write_new(out / "segments" / f"{segment.name}.finish.json", {
        "schema": "g266-run-segment-finish/1",
        "segment_name": segment.name, "phase": segment.phase,
        "status": status, "ended_unix_seconds": time.time(),
        "active_seconds": round(elapsed, 6),
        "cumulative_active_seconds": round(segment.prior_active_seconds + elapsed, 6),
        "total_active_limit_seconds": 9000,
        "manifest_sha256": segment.manifest_sha256,
        "selection_sha256": segment.selection_sha256,
        "completed_scan_stage_files": len(list((out / "stages").glob("*.json"))),
        "completed_branch_root_files": len(list((out / "branches").glob("*.json"))),
        "error_type": None if error is None else type(error).__name__,
        "error": None if error is None else str(error),
    })


def _scan_block(*, out: Path, seed: int, contract: dict, versions: dict,
                manifest_sha256: str, deadline: float) -> bool:
    """单 worker 逐根四座扫描；完整根边界停机，不看部分收益。"""
    for mix in MIXES:
        for root in range(3, 67):
            if time.monotonic() >= deadline:
                return False
            for seat in SEATS:
                try:
                    scan_stage(out=out, seed=seed, mix=mix, root=root, seat=seat,
                               contract=contract, versions=versions,
                               manifest_sha256=manifest_sha256)
                except Exception as exc:
                    write_new(out / "errors" / f"scan-p{seed}-{mix}-r{root:04d}-s{seat}.json",
                              {"phase": "scan", "panel_seed": seed, "mix": mix,
                               "root_index": root, "seat": seat,
                               "error_type": type(exc).__name__, "error": str(exc)})
                    raise
            print(f"scanned p{seed} {mix} root {root}", flush=True)
    return True


def main() -> None:
    """分离冒烟、结果盲扫描、冻结配额、完整桌续打与最终统计。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--phase", choices=("smoke", "scan", "branch", "summarize"),
                        required=True)
    parser.add_argument("--wall-budget-sec", type=int, default=9000)
    args = parser.parse_args()
    out = args.out.resolve()
    _read_manifest(out)
    manifest_sha = digest(out / "manifest.json")
    contract = json.loads(g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    if args.phase == "smoke":
        for mix in MIXES:
            for root in SMOKE_ROOTS:
                for seat in SEATS:
                    scan_stage(out=out, seed=BLOCKS[0][0], mix=mix, root=root,
                               seat=seat, contract=contract, versions=versions,
                               manifest_sha256=manifest_sha)
                print(f"smoke p{BLOCKS[0][0]} {mix} root {root}", flush=True)
        return
    if args.phase == "scan":
        if (out / "selection.json").exists():
            raise ValueError("G266 结果盲入选清单已冻结，禁止重开扫描")
        segment = begin_segment(out, phase="scan",
                                requested_seconds=args.wall_budget_sec,
                                manifest_sha256=manifest_sha)
        status, segment_error = "error", None
        try:
            if not _scan_block(out=out, seed=BLOCKS[0][0], contract=contract,
                               versions=versions, manifest_sha256=manifest_sha,
                               deadline=segment.deadline_monotonic):
                status = "paused"
                print("G266 暂停：首块扫描在完整根边界用完本段预算", flush=True)
                return
            first = _block_roots(out, BLOCKS[0][0], manifest_sha)
            main_counts = {mix: sum(row["priority_layer"] == "B_nonready"
                                    for row in first if row["mix"] == mix)
                           for mix in MIXES}
            if any(value < 12 for value in main_counts.values()):
                if not _scan_block(out=out, seed=BLOCKS[1][0], contract=contract,
                                   versions=versions, manifest_sha256=manifest_sha,
                                   deadline=segment.deadline_monotonic):
                    status = "paused"
                    print("G266 暂停：扩样块扫描在完整根边界用完本段预算", flush=True)
                    return
            selected = freeze_selection(out, manifest_sha)
            status = "complete"
            print(json.dumps({"branch_allowed": selected["branch_allowed"],
                              "first_block_main_exposed_roots": main_counts,
                              "second_block_opened": selected["second_block_opened"],
                              "all_main_exposed_roots": selected["all_main_exposed_roots"],
                              "selected_roots": selected["selected_roots"]},
                             ensure_ascii=False), flush=True)
        except Exception as exc:
            segment_error = exc
            raise
        finally:
            finish_segment(out, segment, status=status, error=segment_error)
        return
    selection_file = out / "selection.json"
    if not selection_file.is_file():
        raise ValueError("G266 尚无结果盲冻结入选清单；不得读分支结果")
    selection = json.loads(selection_file.read_text(encoding="utf-8"))
    if selection.get("manifest_sha256") != manifest_sha:
        raise ValueError("G266 入选清单与运行清单漂移")
    if args.phase == "summarize":
        result = summarize(out, selection, manifest_sha)
        print(json.dumps({"selected_independent_roots": result["selected_independent_roots"],
                          "B_nonready_continue_diagnosis_gate":
                              result["B_nonready_continue_diagnosis_gate"]["all_hard_gates_pass"]},
                         ensure_ascii=False), flush=True)
        return
    if not selection["branch_allowed"]:
        print("G266 B_nonready 暴露不足；禁止续打参照层分支", flush=True)
        return
    selection_sha = digest(selection_file)
    segment = begin_segment(out, phase="branch",
                            requested_seconds=args.wall_budget_sec,
                            manifest_sha256=manifest_sha,
                            selection_sha256=selection_sha)
    status, segment_error = "error", None
    try:
        for row in selection["roots"]:
            if row["selection_status"] != "selected":
                continue
            seed, mix, root = (row[name] for name in
                               ("panel_seed", "mix", "root_index"))
            if time.monotonic() >= segment.deadline_monotonic:
                status = "paused"
                print("G266 暂停：分支在完整根边界用完本段预算", flush=True)
                return
            path = branch_path(out, seed, mix, root)
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                if (saved.get("manifest_sha256") != manifest_sha
                        or saved.get("selection_sha256") != selection_sha
                        or saved["identity"]["root_identity"] != row["root_identity"]):
                    raise ValueError("G266 已存分支冻结身份漂移")
                continue
            try:
                result = branch_root(row, out=out, contract=contract,
                                     versions=versions, manifest_sha256=manifest_sha,
                                     selection_sha256=selection_sha)
                write_new(path, result)
            except Exception as exc:
                write_new(out / "errors" / f"branch-p{seed}-{mix}-r{root:04d}.json",
                          {"phase": "branch", "panel_seed": seed, "mix": mix,
                           "root_index": root, "error_type": type(exc).__name__,
                           "error": str(exc)})
                raise
            print(f"branched p{seed} {mix} root {root}", flush=True)
        summarize(out, selection, manifest_sha)
        status = "complete"
        print("G266 选定分支完整，已输出结果账；仍非候选准入", flush=True)
    except Exception as exc:
        segment_error = exc
        raise
    finally:
        finish_segment(out, segment, status=status, error=segment_error)


if __name__ == "__main__":
    main()
