"""决策采集 codec：生产类型与 JSON 的显式双向映射（audit-plus-v1）。

定位（审计增强方案 §3.3）：本文件是"决策请求/预算/计划"编码规范的
**唯一实现**。application 层在动作窗口内调用 '*_to_json' 落审计，
离线评估读取器调用 '*_from_json' 还原同一套生产类型——两端共用本文件，
不再手抄字段、不使用 pickle、不复制第二套 request 模型。

契约：

1. 全部函数为纯函数：输入是生产类型或 JSON 对象，输出是独立值；
   不读文件、不访问时钟和网络。
2. 每个顶层 JSON 带 'codec_version=1'；不兼容主版本、缺必填键、
   错误类型或非有限浮点（NaN/Inf）一律抛 'ValueError'。
3. 嵌套值对象直接复用 kernel 公共 codec（'kernel.serialization'），
   保留其 'schema_version'；本文件不复制 'PlayerObservation' 等字段。
   'RuleAnalysis'/'RuleCandidate'/'CandidateFacts' 等 hangma 公开
   dataclass 由本文件逐字段映射，包含 'None'、'issues'、
   'emergency_candidate' 与完整 'facts'。
4. '*_from_json' 不做规则重算：缺失的历史规则事实不会被当前规则
   补全，缺什么就还原什么（不完整输入由离线验证器标记，不伪造可训练决策）。
5. 未知可选扩展键容忍（忽略）；时间单位说明：预算三个字段是本机单调时钟
   秒值，跨机器比较前必须先平移（见 :func:'translate_monotonic_deadlines'），
   绝不能当 Unix 时间相减。
"""

from __future__ import annotations

import math
from hangma_bot.kernel.outcome_codec import outcome_trace_from_json, outcome_trace_to_json
from collections.abc import Mapping as MappingABC
from typing import List, Mapping, Sequence, Tuple

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    CandidateValueFacts,
    FamilyId,
    FamilyProgress,
    FollowupBranchFacts,
    ProgressKind,
    RouteStatus,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    Settlement,
    UsefulTileFact,
    ValueConditions,
    ValueCoverage,
    ValueRoute,
)
from hangma_bot.kernel.serialization import (
    action_from_json,
    action_to_json,
    competition_from_json,
    competition_to_json,
    observation_from_json,
    observation_to_json,
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.policy.interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    RejectedAttempt,
    ScorePart,
)

# 决策采集 codec 的线格式版本；只在破坏性变更（删键、改含义、改单位）时递增。
DECISION_CODEC_VERSION = 1

# 增强覆盖声明（审计增强方案 §3.1）：新 payload 携带这两个字段，
# 与 raw 的 'source' 词表互不冲突；旧 v1 数据无此字段仍按原规则读取。
CAPTURE_PROFILE_AUDIT_PLUS_V1 = "audit-plus-v1"
AUDIT_PRODUCER_APPLICATION = "application"
AUDIT_PRODUCER_OFFICIAL = "official"


def _require_mapping(payload: object, type_name: str) -> Mapping[str, object]:
    if not isinstance(payload, MappingABC):
        raise ValueError("{0} 负载必须是 JSON 对象，得到 {1!r}".format(type_name, payload))
    return payload


def _get(payload: Mapping[str, object], key: str, type_name: str) -> object:
    if key not in payload:
        raise ValueError("{0} 负载缺少必填键 {1!r}".format(type_name, key))
    return payload[key]


def _check_codec_version(payload: Mapping[str, object], type_name: str) -> None:
    version = _get(payload, "codec_version", type_name)
    if isinstance(version, bool) or not isinstance(version, int) or version != DECISION_CODEC_VERSION:
        raise ValueError(
            "{0} 的 codec_version={1!r} 与当前版本 {2} 不匹配".format(
                type_name, version, DECISION_CODEC_VERSION
            )
        )


def _as_str(value: object, type_name: str, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError("{0}.{1} 必须是字符串，得到 {2!r}".format(type_name, key, value))
    return value


def _as_int(value: object, type_name: str, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{0}.{1} 必须是整数，得到 {2!r}".format(type_name, key, value))
    return value


def _as_bool(value: object, type_name: str, key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError("{0}.{1} 必须是布尔值，得到 {2!r}".format(type_name, key, value))
    return value


def _as_list(value: object, type_name: str, key: str) -> List[object]:
    if not isinstance(value, list):
        raise ValueError("{0}.{1} 必须是数组，得到 {2!r}".format(type_name, key, value))
    return value


def _as_optional_str(value: object, type_name: str, key: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, type_name, key)


def _as_optional_int(value: object, type_name: str, key: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, type_name, key)


def _as_finite_number(value: object, type_name: str, key: str) -> float:
    """数值字段必须是有限数；NaN/Inf 无法稳定往返，入审计前必须拒绝。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{0}.{1} 必须是数值，得到 {2!r}".format(type_name, key, value))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("{0}.{1} 必须是有限数值，得到 {2!r}".format(type_name, key, value))
    return number


def _enum_value(value: object, allowed: Sequence[str], type_name: str, key: str) -> str:
    text = _as_str(value, type_name, key)
    if text not in allowed:
        raise ValueError(
            "{0}.{1} 必须是 {2} 之一，得到 {3!r}".format(type_name, key, list(allowed), text)
        )
    return text


# ---------------------------------------------------------------------------
# 候选牌效事实（hangma.interface 公开 dataclass）
# ---------------------------------------------------------------------------


def candidate_facts_to_json(facts: CandidateFacts) -> dict[str, object]:
    """把候选牌效事实转为 JSON；缺失数值字段原样保留 None/空，不伪造。"""
    payload = {
        "codec_version": DECISION_CODEC_VERSION,
        "fact_kind": facts.fact_kind.value,
        "shanten_after": facts.shanten_after,
        "useful_tiles": [
            {"code": item.code, "remaining_estimate": item.remaining_estimate}
            for item in facts.useful_tiles
        ],
        "best_followup_discard": facts.best_followup_discard,
        "replacement_draw_unknown": facts.replacement_draw_unknown,
        "completeness": facts.completeness.value,
        "note": facts.note,
    }
    # 可选扩展只在已分析时写入；旧审计缺字段仍表示未知，不补零或重算。
    for name in ("standard_shanten_after", "seven_pairs_shanten_after"):
        value = getattr(facts, name)
        if value is not None:
            payload[name] = value
    for name in ("standard_useful_tiles", "seven_pairs_useful_tiles"):
        value = getattr(facts, name)
        if value is not None:
            payload[name] = [
                {"code": item.code, "remaining_estimate": item.remaining_estimate}
                for item in value
            ]
    if facts.pattern_progress_note is not None:
        payload["pattern_progress_note"] = facts.pattern_progress_note
    if facts.baotou_after is not None:
        payload["baotou_after"] = facts.baotou_after
    # B3 编解码升级（B1 分支进展载荷）：沿用 pattern_progress_v2 兼容先例——
    # 新键仅在非默认（非 None/非空）时写入，旧 JSON 缺键还原 None/()；
    # 字段名与 dataclass 一致（snake_case），枚举写 .value 字符串。
    if facts.followup_branches is not None:
        payload["followup_branches"] = [
            {
                "followup_key": branch.followup_key,
                "followup_discard": branch.followup_discard,
                "combined_shanten": branch.combined_shanten,
                "standard_shanten_after": branch.standard_shanten_after,
                "seven_pairs_shanten_after": branch.seven_pairs_shanten_after,
                "useful_tiles": [
                    {"code": item.code, "remaining_estimate": item.remaining_estimate}
                    for item in branch.useful_tiles
                ],
                "support_remaining": branch.support_remaining,
            }
            for branch in facts.followup_branches
        ]
    if facts.family_progress:
        payload["family_progress"] = [
            {
                "family": entry.family.value,
                "progress": entry.progress.value,
                "route_status": entry.route_status.value,
                "basis": entry.basis,
            }
            for entry in facts.family_progress
        ]
    return payload


def _optional_pattern_tiles_from_json(value: object, key: str) -> Tuple[UsefulTileFact, ...] | None:
    """区分未分析与已知空集合；每张牌复用生产事实类型的校验。"""
    if value is None:
        return None
    type_name = "candidate_facts"
    result = []
    for item in _as_list(value, type_name, key):
        entry = _require_mapping(item, type_name + "." + key + " 元素")
        result.append(UsefulTileFact(
            code=_as_str(_get(entry, "code", type_name), type_name, "code"),
            remaining_estimate=_as_int(
                _get(entry, "remaining_estimate", type_name), type_name, "remaining_estimate"
            ),
        ))
    return tuple(result)


def _branch_facts_from_json(value: object) -> Tuple[FollowupBranchFacts, ...] | None:
    """还原吃/碰分支载荷；旧 JSON 缺键时由调用方保持 None（未分析口径）。"""
    if value is None:
        return None
    type_name = "candidate_facts"
    result = []
    for item in _as_list(value, type_name, "followup_branches"):
        entry = _require_mapping(item, type_name + ".followup_branches 元素")
        useful = _optional_pattern_tiles_from_json(
            _get(entry, "useful_tiles", type_name), "useful_tiles"
        )
        result.append(FollowupBranchFacts(
            followup_key=_as_str(
                _get(entry, "followup_key", type_name), type_name, "followup_key"
            ),
            followup_discard=_as_str(
                _get(entry, "followup_discard", type_name), type_name, "followup_discard"
            ),
            combined_shanten=_as_optional_int(
                entry.get("combined_shanten"), type_name, "combined_shanten"
            ),
            standard_shanten_after=_as_optional_int(
                entry.get("standard_shanten_after"), type_name, "standard_shanten_after"
            ),
            seven_pairs_shanten_after=_as_optional_int(
                entry.get("seven_pairs_shanten_after"), type_name, "seven_pairs_shanten_after"
            ),
            useful_tiles=() if useful is None else useful,
            support_remaining=_as_optional_int(
                entry.get("support_remaining"), type_name, "support_remaining"
            ),
        ))
    return tuple(result)


def _family_progress_from_json(value: object) -> Tuple[FamilyProgress, ...] | None:
    """还原家族进展载荷；旧 JSON 缺键时由调用方还原空元组（未分析）。"""
    if value is None:
        return None
    type_name = "candidate_facts"
    result = []
    for item in _as_list(value, type_name, "family_progress"):
        entry = _require_mapping(item, type_name + ".family_progress 元素")
        result.append(FamilyProgress(
            family=FamilyId(_as_str(_get(entry, "family", type_name), type_name, "family")),
            progress=ProgressKind(
                _as_str(_get(entry, "progress", type_name), type_name, "progress")
            ),
            route_status=RouteStatus(
                _as_str(_get(entry, "route_status", type_name), type_name, "route_status")
            ),
            basis=_as_str(_get(entry, "basis", type_name), type_name, "basis"),
        ))
    return tuple(result)


def candidate_facts_from_json(payload: object) -> CandidateFacts:
    """还原候选牌效事实；语义校验由 CandidateFacts 构造函数完成。"""
    type_name = "candidate_facts"
    data = _require_mapping(payload, type_name)
    _check_codec_version(data, type_name)
    fact_kind = CandidateFactKind(
        _enum_value(
            _get(data, "fact_kind", type_name),
            [member.value for member in CandidateFactKind],
            type_name,
            "fact_kind",
        )
    )
    useful_tiles: list[UsefulTileFact] = []
    for item in _as_list(_get(data, "useful_tiles", type_name), type_name, "useful_tiles"):
        entry = _require_mapping(item, type_name + ".useful_tiles 元素")
        useful_tiles.append(
            UsefulTileFact(
                code=_as_str(_get(entry, "code", type_name), type_name, "code"),
                remaining_estimate=_as_int(
                    _get(entry, "remaining_estimate", type_name),
                    type_name,
                    "remaining_estimate",
                ),
            )
        )
    best_followup = _get(data, "best_followup_discard", type_name)
    return CandidateFacts(
        fact_kind=fact_kind,
        shanten_after=_as_optional_int(
            _get(data, "shanten_after", type_name), type_name, "shanten_after"
        ),
        useful_tiles=tuple(useful_tiles),
        best_followup_discard=(
            None if best_followup is None else _as_str(best_followup, type_name, "best_followup_discard")
        ),
        replacement_draw_unknown=_as_bool(
            _get(data, "replacement_draw_unknown", type_name), type_name, "replacement_draw_unknown"
        ),
        completeness=RuleCompleteness(
            _enum_value(
                _get(data, "completeness", type_name),
                [member.value for member in RuleCompleteness],
                type_name,
                "completeness",
            )
        ),
        note=_as_optional_str(_get(data, "note", type_name), type_name, "note"),
        standard_shanten_after=_as_optional_int(
            data.get("standard_shanten_after"), type_name, "standard_shanten_after"
        ),
        seven_pairs_shanten_after=_as_optional_int(
            data.get("seven_pairs_shanten_after"), type_name, "seven_pairs_shanten_after"
        ),
        standard_useful_tiles=_optional_pattern_tiles_from_json(
            data.get("standard_useful_tiles"), "standard_useful_tiles"
        ),
        seven_pairs_useful_tiles=_optional_pattern_tiles_from_json(
            data.get("seven_pairs_useful_tiles"), "seven_pairs_useful_tiles"
        ),
        pattern_progress_note=_as_optional_str(
            data.get("pattern_progress_note"), type_name, "pattern_progress_note"
        ),
        # B3 编解码升级：旧 JSON 缺键还原 None/()；语义校验（吃/碰适用口径、
        # 家族不重复、分支键形状）交给 CandidateFacts 构造函数完成。
        followup_branches=_branch_facts_from_json(data.get("followup_branches")),
        family_progress=(_family_progress_from_json(data.get("family_progress")) or ()),
        baotou_after=(
            None
            if data.get("baotou_after") is None
            else _as_bool(data.get("baotou_after"), type_name, "baotou_after")
        ),
    )


# ---------------------------------------------------------------------------
# 规则候选与规则分析（hangma.interface 公开 dataclass）
# ---------------------------------------------------------------------------


def _settlement_to_json(value: Settlement) -> dict:
    return {"fan": value.fan, "score_delta": list(value.score_delta), "details": list(value.details)}


def _settlement_from_json(payload: object) -> Settlement:
    name = "conditional_settlement"
    data = _require_mapping(payload, name)
    scores = tuple(_as_int(item, name, "score_delta") for item in _as_list(_get(data, "score_delta", name), name, "score_delta"))
    fan = _as_int(_get(data, "fan", name), name, "fan")
    if len(scores) != 4 or sum(scores) != 0 or fan <= 0:
        raise ValueError("成胡结算必须为正番，四座位分数守恒")
    return Settlement(
        score_delta=scores, fan=fan,
        details=tuple(_as_str(item, name, "details") for item in _as_list(_get(data, "details", name), name, "details")),
    )


def candidate_value_facts_to_json(facts: CandidateValueFacts) -> dict:
    """保存有限分值事实与未来条件，不能合并不同后续弃牌的有效牌张数。"""
    return {
        "codec_version": DECISION_CODEC_VERSION,
        "immediate_settlement": None if facts.immediate_settlement is None else _settlement_to_json(facts.immediate_settlement),
        "coverage": facts.coverage.value,
        "issues": [{"area": issue.area, "reason": issue.reason} for issue in facts.issues],
        "routes": [{
            "conditional_settlement": _settlement_to_json(route.conditional_settlement),
            "shanten": route.shanten,
            "useful_tiles": [{"code": tile.code, "remaining_estimate": tile.remaining_estimate} for tile in route.useful_tiles],
            "followup_discard": route.followup_discard,
            "conditions": {
                "draw_kind": route.conditions.draw_kind,
                "pre_draw_hand": list(route.conditions.pre_draw_hand),
                "meld_count": route.conditions.meld_count,
                "chain_count": route.conditions.chain_count,
                "chain_piao": route.conditions.chain_piao,
                "baotou": route.conditions.baotou,
            },
            "support": route.support,
        } for route in facts.routes],
    }


def candidate_value_facts_from_json(payload: object) -> CandidateValueFacts:
    """逐字段还原可选条件结算；未保存的增强由上层还原为 None，不补算。"""
    name = "candidate_value_facts"
    data = _require_mapping(payload, name)
    _check_codec_version(data, name)
    routes = []
    for item in _as_list(_get(data, "routes", name), name, "routes"):
        row = _require_mapping(item, name + ".routes")
        conditions = _require_mapping(_get(row, "conditions", name), name + ".conditions")
        useful = []
        for tile_raw in _as_list(_get(row, "useful_tiles", name), name, "useful_tiles"):
            tile = _require_mapping(tile_raw, name + ".useful_tiles")
            useful.append(UsefulTileFact(
                code=_as_str(_get(tile, "code", name), name, "code"),
                remaining_estimate=_as_int(_get(tile, "remaining_estimate", name), name, "remaining_estimate"),
            ))
        routes.append(ValueRoute(
            conditional_settlement=_settlement_from_json(_get(row, "conditional_settlement", name)),
            shanten=_as_int(_get(row, "shanten", name), name, "shanten"),
            useful_tiles=tuple(useful),
            followup_discard=_as_optional_str(_get(row, "followup_discard", name), name, "followup_discard"),
            support=_as_str(_get(row, "support", name), name, "support"),
            conditions=ValueConditions(
                draw_kind=_as_str(_get(conditions, "draw_kind", name), name, "draw_kind"),
                pre_draw_hand=tuple(_as_str(code, name, "pre_draw_hand") for code in _as_list(_get(conditions, "pre_draw_hand", name), name, "pre_draw_hand")),
                meld_count=_as_int(_get(conditions, "meld_count", name), name, "meld_count"),
                chain_count=_as_int(_get(conditions, "chain_count", name), name, "chain_count"),
                chain_piao=_as_int(_get(conditions, "chain_piao", name), name, "chain_piao"),
                baotou=_as_bool(_get(conditions, "baotou", name), name, "baotou"),
            ),
        ))
    issues = []
    for item in _as_list(_get(data, "issues", name), name, "issues"):
        row = _require_mapping(item, name + ".issues")
        issues.append(RuleIssue(
            area=_as_str(_get(row, "area", name), name, "area"),
            reason=_as_str(_get(row, "reason", name), name, "reason"),
        ))
    immediate = _get(data, "immediate_settlement", name)
    return CandidateValueFacts(
        immediate_settlement=None if immediate is None else _settlement_from_json(immediate),
        routes=tuple(routes),
        coverage=ValueCoverage(_as_str(_get(data, "coverage", name), name, "coverage")),
        issues=tuple(issues),
    )


def rule_candidate_to_json(candidate: RuleCandidate) -> dict[str, object]:
    """把规则候选转为 JSON；动作复用 kernel 稳定序列化，facts 完整保留。"""
    result = {
        "codec_version": DECISION_CODEC_VERSION,
        "action_key": candidate.action_key,
        "action": action_to_json(candidate.action),
        "evidence": list(candidate.evidence),
        "facts": None if candidate.facts is None else candidate_facts_to_json(candidate.facts),
    }
    if candidate.value_facts is not None:
        result["value_facts"] = candidate_value_facts_to_json(candidate.value_facts)
    return result


def rule_candidate_from_json(payload: object) -> RuleCandidate:
    """还原规则候选；动作键与动作一致性由调用方复核（本函数不重算）。"""
    type_name = "rule_candidate"
    data = _require_mapping(payload, type_name)
    _check_codec_version(data, type_name)
    facts_raw = _get(data, "facts", type_name)
    return RuleCandidate(
        action=action_from_json(_get(data, "action", type_name)),
        action_key=_as_str(_get(data, "action_key", type_name), type_name, "action_key"),
        evidence=tuple(
            _as_str(item, type_name, "evidence")
            for item in _as_list(_get(data, "evidence", type_name), type_name, "evidence")
        ),
        facts=None if facts_raw is None else candidate_facts_from_json(facts_raw),
        value_facts=None if data.get("value_facts") is None else candidate_value_facts_from_json(data["value_facts"]),
    )


def rule_analysis_to_json(analysis: RuleAnalysis) -> dict[str, object]:
    """把规则分析转为 JSON；紧急候选为空时保留 null，不用空数组冒充。"""
    return {
        "codec_version": DECISION_CODEC_VERSION,
        "legal_candidates": [rule_candidate_to_json(item) for item in analysis.legal_candidates],
        "emergency_candidate": (
            None
            if analysis.emergency_candidate is None
            else rule_candidate_to_json(analysis.emergency_candidate)
        ),
        "completeness": analysis.completeness.value,
        "ruleset_version": analysis.ruleset_version,
        "issues": [{"area": issue.area, "reason": issue.reason} for issue in analysis.issues],
    }


def rule_analysis_from_json(payload: object) -> RuleAnalysis:
    """还原规则分析；只恢复保存的规则事实，不补算缺失分支。"""
    type_name = "rule_analysis"
    data = _require_mapping(payload, type_name)
    _check_codec_version(data, type_name)
    emergency_raw = _get(data, "emergency_candidate", type_name)
    issues: list[RuleIssue] = []
    for item in _as_list(_get(data, "issues", type_name), type_name, "issues"):
        entry = _require_mapping(item, type_name + ".issues 元素")
        issues.append(
            RuleIssue(
                area=_as_str(_get(entry, "area", type_name), type_name, "area"),
                reason=_as_str(_get(entry, "reason", type_name), type_name, "reason"),
            )
        )
    return RuleAnalysis(
        legal_candidates=tuple(
            rule_candidate_from_json(item)
            for item in _as_list(
                _get(data, "legal_candidates", type_name), type_name, "legal_candidates"
            )
        ),
        emergency_candidate=(
            None if emergency_raw is None else rule_candidate_from_json(emergency_raw)
        ),
        completeness=RuleCompleteness(
            _enum_value(
                _get(data, "completeness", type_name),
                [member.value for member in RuleCompleteness],
                type_name,
                "completeness",
            )
        ),
        ruleset_version=_as_str(
            _get(data, "ruleset_version", type_name), type_name, "ruleset_version"
        ),
        issues=tuple(issues),
    )


# ---------------------------------------------------------------------------
# 决策请求 / 预算 / 计划
# ---------------------------------------------------------------------------


def _rejected_attempt_to_json(attempt: RejectedAttempt) -> dict[str, object]:
    return {
        "action_key": attempt.action_key,
        "official_code": attempt.official_code,
        "attempt_no": attempt.attempt_no,
        "based_on_authoritative_seq": attempt.based_on_authoritative_seq,
    }


def _rejected_attempt_from_json(payload: object) -> RejectedAttempt:
    type_name = "rejected_attempt"
    data = _require_mapping(payload, type_name)
    return RejectedAttempt(
        action_key=_as_str(_get(data, "action_key", type_name), type_name, "action_key"),
        official_code=_as_str(_get(data, "official_code", type_name), type_name, "official_code"),
        attempt_no=_as_int(_get(data, "attempt_no", type_name), type_name, "attempt_no"),
        based_on_authoritative_seq=_as_int(
            _get(data, "based_on_authoritative_seq", type_name),
            type_name,
            "based_on_authoritative_seq",
        ),
    )


def decision_request_to_json(request: DecisionRequest) -> dict[str, object]:
    """编码完整当时输入；保留玩家观察权限、手牌顺序、规则候选和拒绝历史。"""
    return {
        "codec_version": DECISION_CODEC_VERSION,
        "decision_id": request.decision_id,
        "trigger_seq": request.trigger_seq,
        "window_key": window_key_to_json(request.window_key),
        "observation": observation_to_json(request.observation),
        "competition": competition_to_json(request.competition),
        "rules": rule_analysis_to_json(request.rules),
        "rejected_attempts": [
            _rejected_attempt_to_json(item) for item in request.rejected_attempts
        ],
    }


def decision_request_from_json(payload: object) -> DecisionRequest:
    """解码并检查类型；不以当前规则补算缺失的历史规则事实。"""
    type_name = "decision_request"
    data = _require_mapping(payload, type_name)
    _check_codec_version(data, type_name)
    return DecisionRequest(
        observation=observation_from_json(_get(data, "observation", type_name)),
        competition=competition_from_json(_get(data, "competition", type_name)),
        rules=rule_analysis_from_json(_get(data, "rules", type_name)),
        decision_id=_as_str(_get(data, "decision_id", type_name), type_name, "decision_id"),
        trigger_seq=_as_int(_get(data, "trigger_seq", type_name), type_name, "trigger_seq"),
        window_key=window_key_from_json(_get(data, "window_key", type_name)),
        rejected_attempts=tuple(
            _rejected_attempt_from_json(item)
            for item in _as_list(
                _get(data, "rejected_attempts", type_name), type_name, "rejected_attempts"
            )
        ),
    )


def decision_budget_to_json(budget: DecisionBudget) -> dict[str, object]:
    """保存三个原单调时钟秒值；跨机器重算前必须平移，不能当 Unix 时间。"""
    return {
        "codec_version": DECISION_CODEC_VERSION,
        "enhancement_deadline_monotonic": budget.enhancement_deadline_monotonic,
        "fallback_deadline_monotonic": budget.fallback_deadline_monotonic,
        "latest_send_at_monotonic": budget.latest_send_at_monotonic,
    }


def decision_budget_from_json(payload: object) -> DecisionBudget:
    """恢复原预算值并检查先后关系；不自动延长截止时间。"""
    type_name = "decision_budget"
    data = _require_mapping(payload, type_name)
    _check_codec_version(data, type_name)
    return DecisionBudget(
        enhancement_deadline_monotonic=_as_finite_number(
            _get(data, "enhancement_deadline_monotonic", type_name),
            type_name,
            "enhancement_deadline_monotonic",
        ),
        fallback_deadline_monotonic=_as_finite_number(
            _get(data, "fallback_deadline_monotonic", type_name),
            type_name,
            "fallback_deadline_monotonic",
        ),
        latest_send_at_monotonic=_as_finite_number(
            _get(data, "latest_send_at_monotonic", type_name),
            type_name,
            "latest_send_at_monotonic",
        ),
    )


def translate_monotonic_deadlines(
    old_origin: float,
    deadlines: Sequence[float],
    new_origin: float,
) -> Tuple[float, ...]:
    """把单调时钟截止值按新原点平移；只改变基准，不改变相对截止。

    为什么存在：DecisionBudget 的三个值记录的是**本机**单调时钟秒数，
    不同机器/进程的原点不同，直接相减没有意义。离线重算时以
    'budget_origin_monotonic' 为新原点，把全部截止值平移同一偏移。
    所有输入必须是有限数值，否则抛 'ValueError'（拒绝 NaN/Inf）。
    """
    for value in (old_origin, new_origin):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("单调时钟原点必须是数值，得到 {0!r}".format(value))
        if not math.isfinite(float(value)):
            raise ValueError("单调时钟原点必须是有限数值，得到 {0!r}".format(value))
    offset = float(new_origin) - float(old_origin)
    translated: list[float] = []
    for deadline in deadlines:
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise ValueError("截止值必须是数值，得到 {0!r}".format(deadline))
        if not math.isfinite(float(deadline)):
            raise ValueError("截止值必须是有限数值，得到 {0!r}".format(deadline))
        translated.append(float(deadline) + offset)
    return tuple(translated)


def _ranked_candidate_to_json(candidate: RankedCandidate) -> dict[str, object]:
    result = {
        "action_key": candidate.action_key,
        "action": action_to_json(candidate.action),
        "rank": candidate.rank,
        "total_score": candidate.total_score,
        "score_parts": [
            {"name": part.name, "value": part.value} for part in candidate.score_parts
        ],
        "reasons": list(candidate.reasons),
        "is_emergency": candidate.is_emergency,
    }
    # R2/S5：版本化完整评分解释只在携带时写入（有界结构化 trace 原样保留，
    # 不再截成 reasons 摘要）；旧策略与旧记录缺键还原 None（pattern 先例）。
    if candidate.score_trace is not None:
        result["score_trace"] = dict(candidate.score_trace)
    return result


def _score_trace_from_json(value: object) -> dict | None:
    """还原完整评分解释；缺键/显式 null 还原 None，不补算摘要。"""
    if value is None:
        return None
    data = _require_mapping(value, "ranked_candidate.score_trace")
    for key in data:
        if not isinstance(key, str):
            raise ValueError("ranked_candidate.score_trace 的键必须是字符串")
    return dict(data)


def _ranked_candidate_from_json(payload: object) -> RankedCandidate:
    type_name = "ranked_candidate"
    data = _require_mapping(payload, type_name)
    score_parts: list[ScorePart] = []
    for item in _as_list(_get(data, "score_parts", type_name), type_name, "score_parts"):
        entry = _require_mapping(item, type_name + ".score_parts 元素")
        score_parts.append(
            ScorePart(
                name=_as_str(_get(entry, "name", type_name), type_name, "name"),
                value=_as_finite_number(_get(entry, "value", type_name), type_name, "value"),
            )
        )
    return RankedCandidate(
        action=action_from_json(_get(data, "action", type_name)),
        action_key=_as_str(_get(data, "action_key", type_name), type_name, "action_key"),
        rank=_as_int(_get(data, "rank", type_name), type_name, "rank"),
        total_score=_as_finite_number(
            _get(data, "total_score", type_name), type_name, "total_score"
        ),
        score_parts=tuple(score_parts),
        score_trace=_score_trace_from_json(data.get("score_trace")),
        reasons=tuple(
            _as_str(item, type_name, "reasons")
            for item in _as_list(_get(data, "reasons", type_name), type_name, "reasons")
        ),
        is_emergency=_as_bool(_get(data, "is_emergency", type_name), type_name, "is_emergency"),
    )


def decision_plan_to_json(plan: DecisionPlan) -> dict[str, object]:
    """保存完整候选顺序、策略评分分项和原因；评分不是桌内积分。"""
    result = {
        "codec_version": DECISION_CODEC_VERSION,
        "decision_id": plan.decision_id,
        "window_key": window_key_to_json(plan.window_key),
        "based_on_authoritative_seq": plan.based_on_authoritative_seq,
        "revision": plan.revision,
        "candidates": [_ranked_candidate_to_json(item) for item in plan.candidates],
        "degraded_reasons": list(plan.degraded_reasons),
    }
    # 不给原计划强加空键，保持已有审计线格式逐字节兼容。
    if plan.outcome_trace is not None:
        result["outcome_trace"] = outcome_trace_to_json(plan.outcome_trace)
    return result


def decision_plan_from_json(payload: object) -> DecisionPlan:
    """恢复计划，检查动作键与名次；不决定哪个动作实际提交。"""
    type_name = "decision_plan"
    data = _require_mapping(payload, type_name)
    _check_codec_version(data, type_name)
    return DecisionPlan(
        decision_id=_as_str(_get(data, "decision_id", type_name), type_name, "decision_id"),
        window_key=window_key_from_json(_get(data, "window_key", type_name)),
        based_on_authoritative_seq=_as_int(
            _get(data, "based_on_authoritative_seq", type_name),
            type_name,
            "based_on_authoritative_seq",
        ),
        revision=_as_int(_get(data, "revision", type_name), type_name, "revision"),
        candidates=tuple(
            _ranked_candidate_from_json(item)
            for item in _as_list(_get(data, "candidates", type_name), type_name, "candidates")
        ),
        degraded_reasons=tuple(
            _as_str(item, type_name, "degraded_reasons")
            for item in _as_list(
                _get(data, "degraded_reasons", type_name), type_name, "degraded_reasons"
            )
        ),
        outcome_trace=(None if data.get("outcome_trace") is None else outcome_trace_from_json(data["outcome_trace"])),
    )


__all__ = [
    "AUDIT_PRODUCER_APPLICATION",
    "AUDIT_PRODUCER_OFFICIAL",
    "CAPTURE_PROFILE_AUDIT_PLUS_V1",
    "DECISION_CODEC_VERSION",
    "candidate_facts_from_json",
    "candidate_facts_to_json",
    "decision_budget_from_json",
    "decision_budget_to_json",
    "decision_plan_from_json",
    "decision_plan_to_json",
    "decision_request_from_json",
    "decision_request_to_json",
    "rule_analysis_from_json",
    "rule_analysis_to_json",
    "rule_candidate_from_json",
    "rule_candidate_to_json",
    "translate_monotonic_deadlines",
]
