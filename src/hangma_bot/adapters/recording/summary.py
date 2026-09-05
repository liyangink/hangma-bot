"""运行与身份汇总的纯数据组装。

本模块不做任何 I/O：``jsonl_sink`` 在关闭时调用这里的纯函数生成
``runs/{run_id}/summary.json`` 与 ``participants/{pid}/summary.json`` 的内容。
只使用标准库可序列化类型，保证 ``json.dumps`` 稳定往返。

计数语义（与 ``AuditSummary`` 四桶对齐）：

- ``written``：已成功落盘并 flush 的记录行数。
- ``dropped_low_priority``：低优先级（``RAW_PROTOCOL_STATE``）因队列压力被丢弃、
  或写盘失败被放弃的条数。
- ``missing_high_priority``：高优先级记录未能落盘的条数（入队被拒、写盘失败、
  关闭时限内未排空）；出现即视为本次运行不能宣称“完整可审计”。
- ``serialization_failures``：校验或 JSON 编码失败、从未进入队列的条数。
- ``raw_retention``：原始事件保留模式声明（存在即启用验证器严格检查）。
- 丢失与失败计数为运行级全局值：入队阶段无法可靠归属到单个身份，
  身份级汇总原样引用全局值以避免制造虚假的精确性。
"""

from __future__ import annotations

from typing import Iterable, Mapping

from hangma_bot.adapters.recording.schema import AUDIT_SCHEMA_VERSION

_PARTICIPANT_PATH_PREFIX = "participants/"


def participant_ids_from_paths(paths: Iterable[str]) -> list[str]:
    """从已写文件路径集合提取出现过的参赛身份（排序去重）。"""

    result: set[str] = set()
    for path in paths:
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == _PARTICIPANT_PATH_PREFIX.rstrip("/"):
            result.add(parts[1])
    return sorted(result)


def paths_for_participant(paths: Iterable[str], participant_id: str) -> list[str]:
    """过滤出属于指定参赛身份的文件路径。"""

    prefix = f"{_PARTICIPANT_PATH_PREFIX}{participant_id}/"
    return sorted(path for path in paths if path.startswith(prefix))


def build_run_summary(
    *,
    run_id: str,
    written: int,
    written_by_kind: Mapping[str, int],
    written_by_path: Mapping[str, int],
    dropped_low_priority: int,
    missing_high_priority: int,
    serialization_failures: int,
    write_failures: int,
    audit_degraded: bool,
    participants: Iterable[str],
    raw_retention: Mapping[str, object] | None = None,
    extra_detail: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """组装运行级汇总内容；字段含义见模块 docstring 的计数语义。

    ``raw_retention`` 声明原始事件保留模式（mode/gzip/emitted/dropped）：
    验证器只在存在该键时启用严格完整性检查（缺口/流缺失/动作响应缺失），
    旧目录没有该键则跳过——向后兼容结论不变。缺省为 None（旧调用方）。
    """

    summary: dict[str, object] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "level": "run",
        "run_id": run_id,
        "written": written,
        "written_by_kind": dict(sorted(written_by_kind.items())),
        "written_by_path": dict(sorted(written_by_path.items())),
        "dropped_low_priority": dropped_low_priority,
        "missing_high_priority": missing_high_priority,
        "serialization_failures": serialization_failures,
        "write_failures": write_failures,
        "audit_degraded": audit_degraded,
        "participants": sorted(participants),
    }
    if raw_retention:
        summary["raw_retention"] = dict(raw_retention)
    if extra_detail:
        summary["detail"] = dict(extra_detail)
    return summary


def build_participant_summary(
    *,
    run_id: str,
    participant_id: str,
    written: int,
    written_by_kind: Mapping[str, int],
    written_by_path: Mapping[str, int],
    dropped_low_priority: int,
    missing_high_priority: int,
    serialization_failures: int,
    write_failures: int,
    audit_degraded: bool,
) -> dict[str, object]:
    """组装身份级汇总内容；丢失/失败计数沿用运行级全局值（见模块 docstring）。"""

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "level": "participant",
        "run_id": run_id,
        "participant_id": participant_id,
        "written": written,
        "written_by_kind": dict(sorted(written_by_kind.items())),
        "written_by_path": dict(sorted(written_by_path.items())),
        "dropped_low_priority": dropped_low_priority,
        "missing_high_priority": missing_high_priority,
        "serialization_failures": serialization_failures,
        "write_failures": write_failures,
        "audit_degraded": audit_degraded,
    }
