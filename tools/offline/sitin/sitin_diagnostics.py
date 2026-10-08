"""坐隐 1.7：最小诊断记录——影子包装策略 + JSONL sink。

**目的**：把"跑完完整桌赛没涨分"拆成两件不同的事——
**机制方向错**（触发了但改错了）与**机制没走到**（根本没触发）。
做法是在**同一臂内部、对同一个 `DecisionRequest`** 同时记录驱动策略与影子策略的
完整候选排序与评分分项。

**为什么必须行内影子，不能跨臂配对**（实测，见
[SEAM-INVESTIGATION](../../evidence/1.7-diagnostics/SEAM-INVESTIGATION.md) §4）：

- `run_match_experiment` 是**逐桌串行、两臂各跑一整场**，不是同进程逐窗口对照；
- 两臂同牌山（墙由 `(scenario_id, seed, round_no)` 派生）但**必然分叉**：
  实测 baseline 342 窗口 / challenger 369 窗口，同序号前缀只有 28，
  按窗口标识只能对齐 35 个，**按动作序号硬配错配 314/342**。

⇒ 一行记录里天然含"同一 request 的两套计划"，不需要任何配对算法。
跨臂只在**聚合层**按 `(scenario_id, arm)` 比较。

**硬性要求**（不满足会污染 L1 效果结论）：

1. `ShadowPolicy.choose` 必须**原样返回驱动策略的计划对象**（逐字段不变）；
2. 影子异常/超时**绝不**影响真实动作，只记 `shadow_error`；
3. 转发 `policy_id`（否则驱动记录该字段变 null）。

**边界**：本模块只做"记录"，不改任何排序、保底或截止时间行为；
影子策略必须是纯计算（不读 `WorldState`、不写文件、不发 HTTP）。
落盘由外层 sink 完成，策略本身不写文件（`policy/interface.py` 契约）。
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

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.identity import identity_digest
from hangma_bot.simulation.identity import simulation_hand_id, simulation_split_group_id

DIAGNOSTIC_SCHEMA = "sitin-diagnostics/1"

# 观察摘要的**显式冻结口径**：只摘要依法可见且与决策相关的字段，
# 不含他家手牌与牌墙。名单写入产物，便于日后复现与口径对齐
# （SEAM-INVESTIGATION §8-3 指出该口径当时未定，这里显式定下来）。
OBSERVATION_DIGEST_FIELDS: Tuple[str, ...] = (
    "game_id", "seat", "round_no", "snapshot_seq", "phase", "dealer_seat",
    "turn_seat", "responding_seats", "my_hand", "drawn_tile", "melds",
    "discards", "hand_counts", "last_discard", "remaining_tile_count",
    "scores", "rule_state", "public_history",
)


def observation_digest(observation: Any) -> str:
    """观察内容摘要（sha256）。口径见 `OBSERVATION_DIGEST_FIELDS`。"""

    parts: List[Any] = []
    for name in OBSERVATION_DIGEST_FIELDS:
        parts.append(name)
        parts.append(_canonical(getattr(observation, name, None)))
    return identity_digest(parts)


def _canonical(value: Any) -> Any:
    """把观察字段收敛为可稳定 JSON 化的形式（保序、不改写内容）。"""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    to_json = getattr(value, "to_json", None)
    if callable(to_json):
        return _canonical(to_json())
    code = getattr(value, "code", None)
    if isinstance(code, str):
        return code
    if hasattr(value, "__dict__"):
        return {key: _canonical(val) for key, val in sorted(vars(value).items())}
    return str(value)


def _facts_summary(facts: Any) -> Optional[Dict[str, Any]]:
    """候选事实摘要：等待（动作后）向听与有效牌剩余估计之和。

    这是 REVIEW-6 §4 要求的"等待与动作后事实"，也是判 `facts_sufficient` 的依据。
    """

    if facts is None:
        return None
    useful = getattr(facts, "useful_tiles", None) or ()
    return {
        "fact_kind": getattr(getattr(facts, "fact_kind", None), "value", None),
        "completeness": getattr(getattr(facts, "completeness", None), "value", None),
        "shanten_after": getattr(facts, "shanten_after", None),
        "useful_tiles": {getattr(u, "code", None): getattr(u, "remaining_estimate", None)
                         for u in useful},
        "useful_total": sum(getattr(u, "remaining_estimate", 0) or 0 for u in useful),
        "best_followup_discard": _canonical(getattr(facts, "best_followup_discard", None)),
        "replacement_draw_unknown": getattr(facts, "replacement_draw_unknown", None),
    }


def candidate_to_json(candidate: Any) -> Dict[str, Any]:
    """单个规则候选：动作键 + 事实摘要（事实是唯一规则来源给的，本模块不重算）。"""

    return {"action_key": candidate.action_key,
            "facts": _facts_summary(getattr(candidate, "facts", None))}


def plan_to_json(plan: Any, include_reasons: bool = True) -> Optional[Dict[str, Any]]:
    """完整候选排序与评分分项；**不重排**，按计划自己的 `rank` 顺序。

    驱动只消费 `candidates[0]`，但诊断必须看到**完整**排序与分项，
    否则无法回答"评分变了没有、为什么首要选没变"。
    """

    if plan is None:
        return None
    rows = []
    for candidate in sorted(plan.candidates, key=lambda c: c.rank):
        row = {
            "rank": candidate.rank,
            "action_key": candidate.action_key,
            "total_score": candidate.total_score,
            "is_emergency": candidate.is_emergency,
            "score_parts": {part.name: part.value for part in candidate.score_parts},
        }
        if include_reasons:
            row["reasons"] = list(candidate.reasons)
        rows.append(row)
    totals = [row["total_score"] for row in rows if row["total_score"] is not None]
    return {
        "candidates": rows,
        "first": rows[0]["action_key"] if rows else None,
        "degraded_reasons": list(plan.degraded_reasons),
        # 计划顺序是否就是分值降序。为 False 说明跨了可信层，
        # 此时"最佳 X − 最佳 Y"的分差是跨层相减，方向无意义（REVIEW-6 S6-1）。
        "scores_monotone_non_increasing": all(
            totals[i] >= totals[i + 1] for i in range(len(totals) - 1)),
    }


@dataclass(frozen=True)
class ArmContext:
    """实验设计级标识；**不在 `DecisionRequest` 里**，由驱动按桌注入。

    全部可由 `match_id`（形如 `{prefix}:{scenario_id}:{perm_label}:{policy_id}`，
    `offline/evaluate.py:1500-1505`）加 `scenario_id → seed` 表推得。
    """

    match_id: str
    scenario_id: str
    perm_label: str
    arm_policy_id: str
    arm_role: str
    seed: Optional[int]

    def to_json(self) -> Dict[str, Any]:
        return {"match_id": self.match_id, "scenario_id": self.scenario_id,
                "pair_id": "{0}:{1}".format(self.scenario_id, self.perm_label),
                "split_group_id": simulation_split_group_id(self.scenario_id),
                "seat_permutation_label": self.perm_label,
                "arm_role": self.arm_role, "arm_policy_id": self.arm_policy_id,
                "seed": self.seed}


class DiagnosticSink:
    """逐行 JSONL sink；线程安全，只追加。

    `BotPolicy` 契约要求策略不写文件，因此策略只调用 `emit`，
    真正的落盘发生在这里（由驱动持有并关闭）。
    """

    def __init__(self, path: Path, *, include_reasons: bool = True) -> None:
        self._path = Path(path)
        self._include_reasons = include_reasons
        self._lock = threading.Lock()
        self._handle = None
        self.count = 0
        self.error_count = 0
        self.triggered_count = 0
        # 漏斗聚合：把"没涨分"拆成方向错与没走到，必须能直接读出各阶段计数。
        self.stage_counts: Dict[str, int] = {}

    def emit(self, record: Mapping[str, Any]) -> None:
        with self._lock:
            if self._handle is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = self._path.open("w", encoding="utf-8")
            self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.count += 1
            if record.get("shadow_error"):
                self.error_count += 1
            funnel = record.get("funnel") or {}
            if funnel.get("triggered"):
                self.triggered_count += 1
            # 只按"最深阶段"计数，保证各阶段计数之和 == 记录数（严格漏斗）。
            stage = funnel.get("deepest_stage")
            if stage:
                key = str(stage)
                self.stage_counts[key] = self.stage_counts.get(key, 0) + 1

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None

    def __enter__(self) -> "DiagnosticSink":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# --- 机制漏斗：区分"方向错"与"没走到" --------------------------------------

M4_SCOPE_KINDS = ("chi", "peng")


def _kind(action_key: Optional[str]) -> str:
    return action_key.split(":")[0] if action_key else "none"


def _best(rows: Sequence[Mapping[str, Any]], kinds: Sequence[str]) -> Optional[Mapping[str, Any]]:
    pool = [row for row in rows if _kind(row["action_key"]) in kinds
            and row["total_score"] is not None]
    return max(pool, key=lambda r: (r["total_score"], r["action_key"])) if pool else None


def m4_funnel(request: Any, baseline_plan_json: Mapping[str, Any],
              candidate_plan_json: Mapping[str, Any],
              natural: Optional[int]) -> Dict[str, Any]:
    """四段漏斗（REVIEW-6 §4 第二步要求分别记录的四件事）。

    `目标窗口` → `事实足够` → `评分发生变化` → `首选发生变化`

    `not_triggered_reason` 是第一个未通过的阶段，用于把"没涨分"归因。
    """

    legal = request.rules.legal_candidates
    kinds = {_kind(c.action_key) for c in legal}
    has_scope = bool(kinds & set(M4_SCOPE_KINDS))
    has_pass = "pass" in kinds
    # **严格嵌套的漏斗**：每一阶段都以上一阶段成立为前提，
    # 否则"事实足够 529 > 目标窗口 41"这种计数无法解释（阶段互相独立会误导读者）。
    mechanism_applicable = bool(has_scope and has_pass)
    facts_sufficient = mechanism_applicable and natural is not None and natural > 0

    baseline_scores = {row["action_key"]: row["total_score"]
                       for row in baseline_plan_json["candidates"]}
    candidate_scores = {row["action_key"]: row["total_score"]
                        for row in candidate_plan_json["candidates"]}
    deltas = {key: round(candidate_scores[key] - baseline_scores[key], 6)
              for key in baseline_scores
              if key in candidate_scores and baseline_scores[key] is not None
              and candidate_scores[key] is not None}
    affected_deltas = {key: delta for key, delta in deltas.items()
                       if _kind(key) in M4_SCOPE_KINDS and delta != 0.0}
    score_changed = facts_sufficient and any(delta != 0.0 for delta in deltas.values())
    first_changed = score_changed and (
        baseline_plan_json["first"] != candidate_plan_json["first"])

    best_affected = _best(baseline_plan_json["candidates"], M4_SCOPE_KINDS)
    best_pass = _best(baseline_plan_json["candidates"], ("pass",))
    gap = None
    if best_affected is not None and best_pass is not None:
        gap = round(best_affected["total_score"] - best_pass["total_score"], 3)

    reason = None
    if not mechanism_applicable:
        reason = "not_mechanism_window"
    elif not facts_sufficient:
        reason = "facts_insufficient"
    elif not score_changed:
        reason = "score_unchanged"
    elif not first_changed:
        reason = "first_choice_unchanged"
    # 最深到达的阶段；四种未触发原因 + 触发，恰好构成一个划分，
    # 计数之和等于记录总数，可直接读作"没涨分"的归因分解。
    deepest_stage = "first_changed" if first_changed else reason

    return {
        "deepest_stage": deepest_stage,
        "mechanism_applicable": mechanism_applicable,
        "facts_sufficient": facts_sufficient,
        "score_changed": score_changed,
        "first_changed": first_changed,
        "triggered": bool(first_changed),
        "not_triggered_reason": reason,
        "baseline_first_kind": _kind(baseline_plan_json["first"]),
        "candidate_first_kind": _kind(candidate_plan_json["first"]),
        "affected_score_deltas": affected_deltas,
        # 分差是**未分层**的原始差：只有当两侧计划都按分值单调时才可当同层解释，
        # 因此连同单调标志一起记录，避免复现 REVIEW-6 S6-1 的跨层相减。
        "best_affected_minus_best_pass": gap,
        "baseline_scores_monotone": baseline_plan_json["scores_monotone_non_increasing"],
    }


class ShadowPolicy:
    """`BotPolicy` 包装器：先算驱动计划，再对**同一 request** 算影子计划并记录。

    返回的是**驱动策略的原计划对象**（不是副本），保证该臂的真实轨迹逐字段不变。
    """

    def __init__(
        self,
        driver: Any,
        shadow: Any,
        sink: DiagnosticSink,
        *,
        arm_role: str,
        driver_identity: str,
        shadow_identity: str,
        baseline_identity: str,
        candidate_identity: str,
        ruleset_version: str,
        rule_config: Mapping[str, Any],
        rules_hash: Optional[str],
        source_fingerprints: Mapping[str, Optional[str]],
        seed_by_scenario: Mapping[str, int],
        funnel: Optional[Callable[..., Dict[str, Any]]] = None,
        natural_of: Optional[Callable[[Any], Optional[int]]] = None,
        include_reasons: bool = True,
    ) -> None:
        self._driver = driver
        self._shadow = shadow
        self._sink = sink
        self._arm_role = arm_role
        self._driver_identity = driver_identity
        self._shadow_identity = shadow_identity
        self._baseline_identity = baseline_identity
        self._candidate_identity = candidate_identity
        self._ruleset_version = ruleset_version
        self._rule_config = dict(rule_config)
        self._rules_hash = rules_hash
        self._source_fingerprints = dict(source_fingerprints)
        self._seed_by_scenario = dict(seed_by_scenario)
        self._funnel = funnel
        self._natural_of = natural_of
        self._include_reasons = include_reasons

    @property
    def policy_id(self) -> Optional[str]:
        """转发驱动策略的 policy_id，否则驱动记录该字段会变 null。"""

        return getattr(self._driver, "policy_id", None)

    @property
    def driver(self) -> Any:
        return self._driver

    def _arm_context(self, request: Any) -> ArmContext:
        match_id = request.window_key.game_id
        scenario_id = request.competition.tournament_id
        parts = match_id.split(":")
        perm_label = parts[-2] if len(parts) >= 2 else ""
        return ArmContext(
            match_id=match_id, scenario_id=scenario_id, perm_label=perm_label,
            arm_policy_id=parts[-1] if parts else "",
            arm_role=self._arm_role,
            seed=self._seed_by_scenario.get(scenario_id))

    async def choose(self, request: Any, budget: Any) -> Any:
        # ① 先算驱动计划：真实动作必须在任何影子开销之前确定下来。
        plan = await self._driver.choose(request, budget)

        shadow_plan = None
        shadow_error = None
        try:
            shadow_plan = await self._shadow.choose(request, budget)
        except Exception as exc:  # 影子失败绝不影响真实动作（硬性要求 ②）
            shadow_error = "{0}: {1}".format(type(exc).__name__, exc)

        try:
            self._record(request, plan, shadow_plan, shadow_error)
        except Exception as exc:  # 记录失败同样不得影响真实动作
            try:
                self._sink.emit({"schema": DIAGNOSTIC_SCHEMA,
                                 "record_error": "{0}: {1}".format(type(exc).__name__, exc),
                                 "decision_id": request.decision_id})
            except Exception:
                pass
        return plan  # ③ 原样返回，逐字段不变

    def _record(self, request: Any, plan: Any, shadow_plan: Any,
                shadow_error: Optional[str]) -> None:
        context = self._arm_context(request)
        # 候选项是哪一侧取决于臂角色：基线臂 shadow=M4，候选臂 driver=M4。
        if self._arm_role == "baseline":
            baseline_plan, candidate_plan = plan, shadow_plan
        else:
            baseline_plan, candidate_plan = shadow_plan, plan

        baseline_json = plan_to_json(baseline_plan, self._include_reasons)
        candidate_json = plan_to_json(candidate_plan, self._include_reasons)

        natural = None
        if self._natural_of is not None:
            natural = self._natural_of(request.rules.legal_candidates)

        funnel = None
        if baseline_json is not None and candidate_json is not None and self._funnel is not None:
            funnel = self._funnel(request, baseline_json, candidate_json, natural)

        observation = request.observation
        record: Dict[str, Any] = {
            "schema": DIAGNOSTIC_SCHEMA,
            # --- 标识（REVIEW-6 §4 第二步要求的第一组） ---
            "decision_id": request.decision_id,
            "match_id": context.match_id,
            "scenario_id": context.scenario_id,
            "pair_id": "{0}:{1}".format(context.scenario_id, context.perm_label),
            "split_group_id": simulation_split_group_id(context.scenario_id),
            "seat_permutation_label": context.perm_label,
            "arm_role": context.arm_role,
            "arm_policy_id": context.arm_policy_id,
            "seed": context.seed,
            "seat": request.window_key.seat,
            "round_no": request.window_key.round_no,
            "trigger_seq": request.window_key.trigger_seq,
            "phase": getattr(request.window_key.phase, "value", request.window_key.phase),
            "hand_id": simulation_hand_id(context.scenario_id, context.match_id,
                                          request.window_key.round_no),
            "snapshot_seq": observation.snapshot_seq,
            "observation_digest": observation_digest(observation),
            # 该桌赛最终结果的关联键：与 results.jsonl 的 result_id 同源
            "result_id": "r-" + context.match_id,
            # --- 规则与候选身份 ---
            "ruleset_version": self._ruleset_version,
            "rule_config": dict(self._rule_config),
            "rules_hash": self._rules_hash,
            "rules_complete": request.rules.completeness is RuleCompleteness.COMPLETE,
            "rules_issues": [{"area": i.area, "reason": i.reason}
                             for i in request.rules.issues],
            "baseline_identity": self._baseline_identity,
            "candidate_identity": self._candidate_identity,
            "driver_identity": self._driver_identity,
            "shadow_identity": self._shadow_identity,
            "source_fingerprints": dict(self._source_fingerprints),
            # --- 事实与触发 ---
            "waiting_tiles": natural,
            "legal_candidates": [candidate_to_json(c)
                                 for c in request.rules.legal_candidates],
            "funnel": funnel,
            # --- 两套完整计划 ---
            "driver_plan": plan_to_json(plan, self._include_reasons),
            "shadow_plan": plan_to_json(shadow_plan, self._include_reasons),
            "driver_choice": plan_to_json(plan, False)["first"] if plan is not None else None,
            "shadow_choice": (plan_to_json(shadow_plan, False)["first"]
                              if shadow_plan is not None else None),
            "baseline_plan": baseline_json,
            "candidate_plan": candidate_json,
            # --- 异常与排除 ---
            "shadow_error": shadow_error,
        }
        self._sink.emit(record)
