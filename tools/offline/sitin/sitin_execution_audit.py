"""离线评分执行诊断：绑定物理座位策略，保留内部降级，独立于驱动保底计数。"""
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

import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA = "sitin-policy-execution/1"
COUNT_KEYS = (
    "decision_count", "action_value_scored", "action_value_failed",
    "other_policy_decisions", "ambiguous_diagnostics", "unclassified_action_value",
)
FAILURE_KINDS = (
    "operation_limit", "resource_or_numeric_limit", "abstain",
    "scoring_error", "unclassified_failure",
)
FAILED_PREFIX = "action_value_failed:"
SCORING_POLICY_PREFIXES = (
    "action_value_v1:", "protected-r17:",
    "release:r18-integrated-positive-v1:",
    "release:r18-integrated-positive-v2:",
)


def digest(value: Any) -> str:
    """规范JSON摘要：数组保持物理座位0到3顺序，非有限数拒绝。"""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _counts() -> dict[str, int]:
    return {key: 0 for key in COUNT_KEYS}


def _policy_ids(values: Any) -> list[str]:
    if (not isinstance(values, (tuple, list)) or len(values) != 4
            or any(not isinstance(value, str) or not value for value in values)):
        raise ValueError("评分审计需要物理座位0到3的四个实际策略身份")
    return list(values)


def _failure_kind(reasons: Sequence[str]) -> str:
    # 只接受固定生产骨架的主错误前缀；附带保底说明不重复计窗口。
    if any(reason.startswith("action_value_failed: ABSTAIN ") for reason in reasons):
        return "abstain"
    errors = [reason for reason in reasons
              if reason.startswith("action_value_failed: 候选整批失败 ")]
    if len(set(errors)) != 1:
        return "unclassified_failure"
    error = errors[0]
    if error.startswith("action_value_failed: 候选整批失败 WorkloadExceeded: 计数操作超限："):
        return "operation_limit"
    if error.startswith("action_value_failed: 候选整批失败 WorkloadExceeded:"):
        return "resource_or_numeric_limit"
    return "scoring_error"


def summarize(decisions: Sequence[Any], *, policy_ids_by_seat: Sequence[str]) -> dict[str, Any]:
    """只读已完成驱动记录；每窗口唯一分类，策略名缺失按装配身份识别未知。

    输入是驱动公开的MatchDecisionRecord序列，不读取完整世界。输出含实际
    策略身份、总数及物理座位0到3的分项；失败原因次数不能相加当窗口数。
    非法座位、重复决策标识或坏诊断拒绝，不能静默丢记录。
    """
    policy_ids = _policy_ids(policy_ids_by_seat)
    totals = _counts()
    seats = [_counts() for _ in range(4)]
    kinds = {key: 0 for key in FAILURE_KINDS}
    failure_reasons: dict[str, int] = {}
    seen: set[str] = set()
    for row in decisions:
        if type(row.seat) is not int or not 0 <= row.seat < 4:
            raise ValueError("评分审计窗口座位越界")
        if not isinstance(row.decision_id, str) or not row.decision_id or row.decision_id in seen:
            raise ValueError("评分审计决策标识缺失或重复")
        seen.add(row.decision_id)
        reasons = row.degraded_reasons
        if (not isinstance(reasons, (list, tuple))
                or any(not isinstance(reason, str) for reason in reasons)):
            raise ValueError("评分审计诊断原因格式错误")
        expected = policy_ids[row.seat]
        # protected-r17 先执行 ActionValue 基线，再选择是否重排弃牌；其
        # action_value 成功/失败诊断仍属于真实评分执行，不能因包装策略 ID
        # 不再以 action_value_v1 开头而记成歧义。
        is_scoring = expected.startswith(SCORING_POLICY_PREFIXES)
        scored = any(reason.startswith("action_value: ") and reason.endswith(" 评分完成")
                     for reason in reasons)
        failed = any(reason.startswith(FAILED_PREFIX) for reason in reasons)
        mismatch = row.policy_id is not None and row.policy_id != expected
        ambiguous = mismatch or (scored and failed) or ((scored or failed) and not is_scoring)
        bucket = ("ambiguous_diagnostics" if ambiguous else "action_value_failed" if failed
                  else "action_value_scored" if scored else "unclassified_action_value"
                  if is_scoring else "other_policy_decisions")
        for counts in (totals, seats[row.seat]):
            counts["decision_count"] += 1
            counts[bucket] += 1
        if bucket == "action_value_failed":
            kinds[_failure_kind(reasons)] += 1
        for reason in set(reason for reason in reasons if reason.startswith(FAILED_PREFIX)):
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    audit = {"schema": SCHEMA, "policy_ids_by_seat": policy_ids, **totals,
             "by_seat": seats, "failure_kinds": kinds,
             "failure_reason_counts": dict(sorted(failure_reasons.items()))}
    validate(audit, policy_ids_by_seat=policy_ids)
    return audit


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("评分审计计数必须为非负整数，bool不可冒充计数")
    return value


def validate(audit: Any, *, policy_ids_by_seat: Sequence[str]) -> dict[str, Any]:
    """校验持久化计数与座位归属；只检查一致性，不冒充重新执行原始窗口。"""
    if not isinstance(audit, dict) or audit.get("schema") != SCHEMA:
        raise ValueError("评分执行审计缺失或版本错误")
    if audit.get("policy_ids_by_seat") != _policy_ids(policy_ids_by_seat):
        raise ValueError("评分执行审计实际策略身份不符")
    expected_keys = {"schema", "policy_ids_by_seat", "by_seat", "failure_kinds",
                     "failure_reason_counts", *COUNT_KEYS}
    if set(audit) != expected_keys:
        raise ValueError("评分执行审计字段缺失或未声明")
    seats = audit["by_seat"]
    if not isinstance(seats, list) or len(seats) != 4:
        raise ValueError("评分审计需要四个物理座位计数")
    for counts in [audit, *seats]:
        if not isinstance(counts, dict) or any(key not in counts for key in COUNT_KEYS):
            raise ValueError("评分审计缺少窗口计数")
        if sum(_integer(counts[key]) for key in COUNT_KEYS[1:]) != _integer(counts["decision_count"]):
            raise ValueError("评分审计窗口分类合计不符")
    for seat, counts in enumerate(seats):
        if set(counts) != set(COUNT_KEYS):
            raise ValueError("评分审计座位计数字段不符")
        if not policy_ids_by_seat[seat].startswith(SCORING_POLICY_PREFIXES) and any(
                counts[key] for key in ("action_value_scored", "action_value_failed",
                                       "unclassified_action_value")):
            raise ValueError("非评分策略座位包含评分计数")
        if policy_ids_by_seat[seat].startswith(SCORING_POLICY_PREFIXES) and counts["other_policy_decisions"]:
            raise ValueError("评分策略未知窗口不能记为普通策略")
    for key in COUNT_KEYS:
        if sum(counts[key] for counts in seats) != audit[key]:
            raise ValueError("评分审计座位合计不符")
    kinds = audit["failure_kinds"]
    if (not isinstance(kinds, dict) or set(kinds) != set(FAILURE_KINDS)
            or sum(_integer(value) for value in kinds.values()) != audit["action_value_failed"]):
        raise ValueError("评分失败原因分类合计不符")
    reasons = audit["failure_reason_counts"]
    if not isinstance(reasons, dict):
        raise ValueError("评分失败原因计数格式错误")
    for reason, value in reasons.items():
        if (not isinstance(reason, str) or not reason.startswith(FAILED_PREFIX)
                or not 0 < _integer(value) <= audit["action_value_failed"] + audit["ambiguous_diagnostics"]):
            raise ValueError("评分失败原因计数越界")
    return audit


def verify_table(table: Mapping[str, Any], *, required: bool = True) -> dict[str, Any] | None:
    """读取桌结果并核验审计摘要和策略身份；旧记录返回未知，绝不补零。

    required=True用于新冻结执行配置；False只允许完全未声明审计的历史结果。
    任何半份记录、版本矛盾或摘要改变都拒绝。摘要能发现产物不同步，不能
    独立证明生产者真实执行过所有窗口。
    """
    if "policy_execution_binding" in table:
        binding = table["policy_execution_binding"]
        if not isinstance(binding, dict) or binding.get("schema") != "sitin-conditional-execution-binding/1":
            raise ValueError("条件桌评分审计绑定缺失或版本错误")
        raw = table.get("policy_execution")
        validate(raw, policy_ids_by_seat=binding.get("policy_ids_by_seat"))
        if binding.get("table_id") != table.get("table_id"):
            raise ValueError("条件桌评分审计场次身份不符")
        if type(table.get("decisions")) is not int or table["decisions"] != raw["decision_count"]:
            raise ValueError("条件桌评分审计决策数与驱动记录不符")
        limits = binding.get("max_operations_by_seat")
        if (not isinstance(limits, list) or len(limits) != 4
                or any(value is not None and (type(value) is not int or value <= 0) for value in limits)):
            raise ValueError("条件桌实际评分额度格式错误")
        expected = digest({"table_id": table["table_id"], "max_operations_by_seat": limits,
                           "policy_execution": raw})
        if binding.get("record_sha256") != expected:
            raise ValueError("条件桌评分审计摘要不符")
        return raw
    versions = (table.get("result") or {}).get("versions") or {}
    raw = table.get("policy_execution")
    if (raw is None and "policy_execution_schema" not in versions
            and "policy_execution_sha256" not in versions):
        if required:
            raise ValueError("新桌结果缺少评分执行审计")
        return None
    if versions.get("policy_execution_schema") != SCHEMA:
        raise ValueError("桌结果评分审计版本不符")
    policies = [versions.get("natural_seat_policy:{0}".format(seat)) for seat in range(4)]
    validate(raw, policy_ids_by_seat=_policy_ids(policies))
    if versions.get("policy_execution_sha256") != digest(raw):
        raise ValueError("桌结果评分审计摘要不符")
    return raw


def conditional_fields(table_id: str, decisions: Sequence[Any], policies_by_seat: Sequence[Any]) -> dict[str, Any]:
    """给条件续打桌生成独立审计绑定；不伪造完整MatchResult或重演前缀决策。

    当前桌只含截取帧之后的决策，余下完整桌含其全部决策。额度向量按物理
    座位0到3，非评分策略或未声明的替身使用None，不猜默认额度。
    """
    policies = [str(getattr(policy, "policy_id", type(policy).__name__)) for policy in policies_by_seat]
    limits = [getattr(policy, "max_operations", None) for policy in policies_by_seat]
    raw = summarize(decisions, policy_ids_by_seat=policies)
    binding = {"schema": "sitin-conditional-execution-binding/1", "table_id": table_id,
               "policy_ids_by_seat": policies, "max_operations_by_seat": limits,
               "record_sha256": digest({"table_id": table_id, "max_operations_by_seat": limits,
                                        "policy_execution": raw})}
    return {"policy_execution": raw, "policy_execution_binding": binding}


def review_tables(tables: Sequence[Mapping[str, Any]], *, required: bool = True) -> dict[str, Any]:
    """聚合已执行桌的诊断，缺失不默认零；不改变阶段得分或签发发布资格。"""
    totals = _counts()
    kinds = {key: 0 for key in FAILURE_KINDS}
    recorded = 0
    for table in tables:
        audit = verify_table(table, required=required)
        if audit is None:
            continue
        recorded += 1
        for key in COUNT_KEYS:
            totals[key] += audit[key]
        for key in FAILURE_KINDS:
            kinds[key] += audit["failure_kinds"][key]
    known = bool(tables) and recorded == len(tables)
    needs_review = any(totals[key] for key in (
        "action_value_failed", "ambiguous_diagnostics", "unclassified_action_value"))
    return {"schema": "sitin-policy-execution-review/1",
            "status": "unknown" if not known else "requires_review" if needs_review else "complete",
            "tables": len(tables), "recorded_tables": recorded,
            "missing_tables": len(tables) - recorded,
            "recorded_counts": totals, "recorded_failure_kinds": kinds,
            "zero_internal_failures_verified": known and not needs_review}
