"""离线审计验证器：读取一次运行的审计目录，真实报告记录是否完整。

定位（模块说明 §validator）：在赛事结束后独立运行，不参与线上动作路径；
它只读取 ``runs/{run_id}/`` 下的 JSONL 与 JSON 文件，输出机器可读报告。

检查项（对应模块完成定义与 ``mvp-acceptance.md`` §4）：

- 悬空动作尝试：``SUBMISSION_INTENT`` 没有配对的 ``SUBMISSION_OUTCOME``；
- 孤立结果：没有 intent 的 outcome；
- 重复记录（warning 级）：应用层与官方适配器双层各记录一次同一事实
  （intent/outcome/GAME_FINISHED）是正常形态，不报告；同一关联键出现
  三条及以上同层记录才识别为真正重复并报告 warning（接口协议 §7.1），
  不影响完整判定；
- 阶段尝试混用：同一 ``(participant_id, game_id)`` 出现两个及以上不同的
  非空 ``stage_attempt_id``。缺失与非空共存的形态是双层记录的合法常态
  （官方适配器按契约不生产 ``stage_attempt_id``，接口协议 §7.1），不算混用；
- 损坏行：无法 JSON 解码或信封字段不完整的行，逐行报告位置；
- 密文扫描：复用写入侧同一组形态判定，要求认证原文扫描结果为 0；
- 覆盖率与统计：各类计数、规则降级、显式拒绝（409 族）、模糊提交、
  未发送/超时，以及"最早 intent → 最晚 outcome"的尝试级 P50/P95/P99 时延；
  提交结果词表经 :func:`canonical_outcome` 归并规范值与封闭类名两种生产形态。
- 原始协议事件（RAW_PROTOCOL_STATE，2026-09-04 审计增强）：按
  source/endpoint/http_status 覆盖统计与原文字节数；运行级 summary.json
  声明 raw_retention 模式后启用严格完整性检查——做过状态请求的场必须有
  state_response 原文流、request_no 按会话段连续（进程重启归零 = 新段
  起点，段首/段内缺失都报）、每个实际发出的动作 POST 都有
  action_submit_response 原文。旧目录无该声明则整体跳过，验证结论
  与升级前一致（向后兼容回归锚点：run-29a71a10ad12441eb15e0ac4cfb55c1d）。

结论语义：报告中的 ``audit_complete`` 只在没有任何 ``violation`` 级发现时为真；
``warning`` 级发现不改变结论。验证器"失败"即 ``audit_complete=false``，
不允许在关键信封缺失时默认成功。

命令行用法：``python -m hangma_bot.adapters.recording.validator <run_dir>``，
报告以 UTF-8 JSON 打印到标准输出；发现 violation 时退出码为 1。
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hangma_bot.adapters.recording.raw_events import (
    RAW_PAYLOAD_SCHEMA_VERSION,
    RAW_SOURCE_ACTION_RESPONSE,
    RAW_SOURCE_STATE_RESPONSE,
    is_new_shape_raw_payload,
)
from hangma_bot.adapters.recording.redact import (
    ENDPOINT_KEY,
    REDACTED,
    is_sensitive_key,
    unredacted_secret_matches,
    unredacted_secret_matches_weak,
)
from hangma_bot.adapters.recording.schema import AUDIT_SCHEMA_VERSION, canonical_outcome
from hangma_bot.application.contracts import (
    AuditKind,
    SUBMISSION_CANCELLED_IN_FLIGHT,
)


def _percentile(sorted_values: list[int], pct: float) -> int | None:
    """最近邻秩分位数：确定性且无需插值；空序列返回 None。"""

    if not sorted_values:
        return None
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


@dataclass(frozen=True)
class RecordLocation:
    """一条发现的文件级定位；相对路径便于在报告和工单中引用。"""

    file: str  # 相对 run_dir 的 POSIX 风格路径
    line_no: int  # 1 起；manifest/summary 等整文件发现为 0


@dataclass(frozen=True)
class _Finding:
    """一条审计发现；severity 为 violation（失败）或 warning（仅提示）。"""

    severity: str
    code: str
    detail: str
    locations: tuple[RecordLocation, ...]


@dataclass
class _Parsed:
    """解析成功且信封完整的记录及来源定位。"""

    location: RecordLocation
    kind: str
    context: dict[str, Any]
    payload: dict[str, Any]
    wall_time_unix_ms: int


def _iter_audit_files(run_dir: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """收集 jsonl 记录文件、manifest 与 summary 文件。"""

    jsonl_files: list[Path] = []
    manifests: list[Path] = []
    summaries: list[Path] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        name = path.name
        # 原始事件 gzip 轮转段（.NNNNN.jsonl.gz）与普通 jsonl 同权扫描：
        # 轮转只改变存储形态，不改变审计语义。
        if name.endswith(".jsonl") or name.endswith(".jsonl.gz"):
            jsonl_files.append(path)
        elif name == "manifest.json":
            manifests.append(path)
        elif name == "summary.json":
            summaries.append(path)
    return jsonl_files, manifests, summaries


def _walk_secrets(
    node: Any,
    hits: list[dict[str, Any]],
    location: RecordLocation,
    path: str,
    endpoint_value: bool = False,
) -> None:
    """递归扫描结构：敏感键未脱敏或字符串值残留凭证形态都算命中。

    endpoint 键的值只做弱形态扫描（不应用裸长串规则）：场次 URL 的
    40+ 字符路径段不是凭证，写入侧已同样豁免（见 redact.py）。
    """

    if isinstance(node, dict):
        for key, value in node.items():
            key_text = key if isinstance(key, str) else str(key)
            child_path = f"{path}.{key_text}"
            if (
                is_sensitive_key(key_text)
                and value != REDACTED
                and not (isinstance(value, str) and REDACTED in value)
            ):
                hits.append({
                    "location": {"file": location.file, "line_no": location.line_no},
                    "kind": "sensitive_key",
                    "path": child_path,
                })
            _walk_secrets(
                value,
                hits,
                location,
                child_path,
                endpoint_value=(key_text == ENDPOINT_KEY),
            )
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_secrets(
                value, hits, location, f"{path}[{index}]", endpoint_value=endpoint_value
            )
    elif isinstance(node, str):
        matcher = unredacted_secret_matches_weak if endpoint_value else unredacted_secret_matches
        for match in matcher(node):
            # 只报告形态与长度，不回显原文，避免验证报告本身泄漏秘密。
            hits.append({
                "location": {"file": location.file, "line_no": location.line_no},
                "kind": "secret_shape",
                "path": path,
                "shape_length": len(match),
            })


class _RunScanner:
    """单次运行目录的解析与检查状态；由 validate_run 驱动。"""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self.findings: list[_Finding] = []
        self.records: list[_Parsed] = []
        self.corrupt_lines: list[dict[str, Any]] = []
        self.malformed_records: list[dict[str, Any]] = []
        self.manifest_present = False
        self.manifest_ok = True
        self.summary_files = 0
        self.files_scanned = 0
        # 运行级 summary.json 中的原始事件保留模式声明；None = 旧目录（legacy），
        # 严格完整性检查整体跳过，保证向后兼容的验证结论不变。
        self.raw_retention: dict[str, Any] | None = None
        # manifest 声明的增强覆盖 profile；None = 旧目录（legacy），
        # audit-plus-v1 校验（producer_summary/决策输入配对）只在开启时生效。
        self.capture_profile: str | None = None

    # ---- 解析 ----------------------------------------------------------

    def _location(self, path: Path, line_no: int) -> RecordLocation:
        return RecordLocation(
            file=path.relative_to(self._run_dir).as_posix(),
            line_no=line_no,
        )

    def scan(self) -> None:
        jsonl_files, manifests, summaries = _iter_audit_files(self._run_dir)
        for path in jsonl_files:
            self._scan_jsonl(path)
        for path in manifests:
            self._scan_manifest(path)
        for path in summaries:
            self._scan_summary(path)
        if self.malformed_records:
            self.findings.append(_Finding(
                "violation",
                "malformed_record",
                f"存在 {len(self.malformed_records)} 条信封结构不完整的记录，无法参与关联检查",
                tuple(
                    RecordLocation(file=item["file"], line_no=item["line_no"])
                    for item in self.malformed_records[:10]
                ),
            ))
        self.files_scanned = len(jsonl_files) + len(manifests)
        if not self.manifest_present:
            self.findings.append(_Finding(
                "violation",
                "missing_manifest",
                "运行目录缺少 manifest.json，无法证明运行身份与目标核对发生",
                (RecordLocation(file="manifest.json", line_no=0),),
            ))

    def _scan_jsonl(self, path: Path) -> None:
        try:
            if path.name.endswith(".jsonl.gz"):
                handle = gzip.open(
                    path, "rt", encoding="utf-8", errors="replace", newline="\n"
                )
            else:
                handle = path.open("r", encoding="utf-8", errors="replace")
            with handle:
                # gzip.BadGzipFile 等错误在读取时抛出（open 只建句柄）：
                # try 必须覆盖整个读取循环，损坏段报 violation 而不是崩溃。
                # 截断段（进程被杀、无 gzip trailer）在读取尾部抛 EOFError，
                # 不是 OSError 子类（F-10 修复，实测实证）：一并捕获。
                for line_no, raw in enumerate(handle, start=1):
                    line = raw.rstrip("\n")
                    if not line.strip():
                        continue  # 空行按可忽略空白处理
                    try:
                        envelope = json.loads(line)
                    except json.JSONDecodeError as exc:
                        self.corrupt_lines.append({
                            "file": self._location(path, line_no).file,
                            "line_no": line_no,
                            "reason": f"json_decode_error: {exc.msg}",
                        })
                        # 损坏行同样可能是秘密载体：对原文做形态扫描。
                        self._scan_text_secrets(line, self._location(path, line_no), "corrupt_line")
                        continue
                    self._accept_envelope(envelope, self._location(path, line_no))
        except (OSError, EOFError) as exc:
            # EOFError：截断的 gzip 段（F-10）；报 unreadable_audit_file
            # violation 而不是让 validate_run 裸抛。
            self.findings.append(_Finding(
                "violation",
                "unreadable_audit_file",
                f"审计文件无法读取: {type(exc).__name__}",
                (self._location(path, 0),),
            ))

    def _scan_manifest(self, path: Path) -> None:
        self.manifest_present = True
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self.manifest_ok = False
            self.findings.append(_Finding(
                "violation",
                "corrupt_manifest",
                f"manifest.json 无法解析: {type(exc).__name__}",
                (self._location(path, 0),),
            ))
            return
        if isinstance(document, dict) and document.get("schema_version") != AUDIT_SCHEMA_VERSION:
            observed_schema = document.get("schema_version")
            self.findings.append(_Finding(
                "warning",
                "unknown_manifest_schema",
                f"manifest schema_version={observed_schema!r} 与验证器基线 {AUDIT_SCHEMA_VERSION} 不同，按已知结构尽力检查",
                (self._location(path, 0),),
            ))
        if isinstance(document, dict):
            payload = document.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("capture_profile"), str):
                # audit-plus-v1 profile 声明：启用增强校验（producer_summary
                # 关闭证据与决策输入/终结配对）。旧 manifest 无该字段 → legacy。
                self.capture_profile = payload["capture_profile"]
        hits: list[dict[str, Any]] = []
        _walk_secrets(document, hits, self._location(path, 0), "manifest")
        self._collect_secret_hits(hits)

    def _scan_summary(self, path: Path) -> None:
        self.summary_files += 1
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self.findings.append(_Finding(
                "violation",
                "corrupt_summary",
                f"summary.json 无法解析: {type(exc).__name__}",
                (self._location(path, 0),),
            ))
            return
        if isinstance(document, dict) and document.get("audit_degraded"):
            self.findings.append(_Finding(
                "violation",
                "sink_reported_degraded",
                "记录器关闭汇总声明 audit_degraded=true，本次运行不能宣称完整可审计",
                (self._location(path, 0),),
            ))
        if (
            isinstance(document, dict)
            and self._location(path, 0).file == "summary.json"
            and isinstance(document.get("raw_retention"), dict)
        ):
            self.raw_retention = document["raw_retention"]

    def _collect_secret_hits(self, hits: list[dict[str, Any]]) -> None:
        if not hits:
            return
        detail_parts: list[str] = []
        for hit in hits[:10]:
            detail_parts.append(hit["kind"] + "@" + hit["path"])
        detail = "; ".join(detail_parts)
        self.findings.append(_Finding(
            "violation",
            "secret_found",
            f"认证原文或凭证形态扫描命中 {len(hits)} 处: {detail}",
            tuple(
                RecordLocation(file=hit["location"]["file"], line_no=hit["location"]["line_no"])
                for hit in hits[:10]
            ),
        ))

    def _scan_text_secrets(self, text: str, location: RecordLocation, label: str) -> None:
        hits: list[dict[str, Any]] = []
        for match in unredacted_secret_matches(text):
            hits.append({
                "location": {"file": location.file, "line_no": location.line_no},
                "kind": label,
                "shape_length": len(match),
            })
        self._collect_secret_hits(hits)

    def _accept_envelope(self, envelope: Any, location: RecordLocation) -> None:
        hits: list[dict[str, Any]] = []
        _walk_secrets(envelope, hits, location, "record")
        self._collect_secret_hits(hits)

        problem = self._envelope_problem(envelope)
        if problem is not None:
            self.malformed_records.append({
                "file": location.file,
                "line_no": location.line_no,
                "reason": problem,
            })
            return
        context = envelope["context"]
        self.records.append(
            _Parsed(
                location=location,
                kind=envelope["kind"],
                context=context,
                payload=envelope.get("payload") or {},
                wall_time_unix_ms=envelope["wall_time_unix_ms"],
            )
        )

    def _envelope_problem(self, envelope: Any) -> str | None:
        """返回信封结构问题；None 表示可以参与后续关联检查。"""

        if not isinstance(envelope, dict):
            return "记录不是 JSON 对象"
        observed_schema = envelope.get("schema_version")
        if observed_schema != AUDIT_SCHEMA_VERSION:
            return f"未知 schema_version={observed_schema!r}"
        kind = envelope.get("kind")
        try:
            AuditKind(kind)
        except ValueError:
            return f"未知审计种类 kind={kind!r}"
        context = envelope.get("context")
        if not isinstance(context, dict):
            return "context 缺失或不是对象"
        for field in ("run_id", "tournament_id", "participant_id"):
            if not isinstance(context.get(field), str) or not context.get(field):
                return f"context.{field} 缺失"
        if not isinstance(envelope.get("wall_time_unix_ms"), int):
            return "wall_time_unix_ms 缺失或不是整数"
        return None

    # ---- 关联检查 ------------------------------------------------------

    def _pair_key(self, record: _Parsed, kind_name: str) -> tuple[str, str, int] | None:
        """提取 (participant, decision_id, attempt_no) 关联键；缺失返回 None。"""

        decision_id = record.context.get("decision_id")
        attempt_no = record.context.get("attempt_no")
        if not isinstance(decision_id, str) or not decision_id:
            self.findings.append(_Finding(
                "violation",
                f"uncorrelatable_{kind_name}",
                f"{kind_name} 记录缺少 decision_id，无法用关联键定位动作尝试",
                (record.location,),
            ))
            return None
        if not isinstance(attempt_no, int) or isinstance(attempt_no, bool) or attempt_no <= 0:
            self.findings.append(_Finding(
                "violation",
                f"uncorrelatable_{kind_name}",
                f"{kind_name} 记录缺少合法 attempt_no，无法用关联键定位动作尝试",
                (record.location,),
            ))
            return None
        return (record.context["participant_id"], decision_id, attempt_no)

    def check_submissions(self) -> dict[str, Any]:
        """intent/outcome 配对、重复键与孤立记录检查；返回提交统计。"""

        intents: dict[tuple[str, str, int], list[_Parsed]] = {}
        outcomes: dict[tuple[str, str, int], list[_Parsed]] = {}
        histogram: Counter[str] = Counter()
        official_codes: Counter[str] = Counter()
        not_sent = 0
        not_sent_timeouts = 0
        latencies: list[int] = []

        for record in self.records:
            if record.kind == AuditKind.SUBMISSION_INTENT.value:
                key = self._pair_key(record, "intent")
                if key is not None:
                    intents.setdefault(key, []).append(record)
            elif record.kind == AuditKind.SUBMISSION_OUTCOME.value:
                key = self._pair_key(record, "outcome")
                if key is not None:
                    outcomes.setdefault(key, []).append(record)
                    # 应用层写 "outcome"，官方适配器写 "outcome_type"；
                    # 两者都归并到规范词表，未知值原样计数不拒绝。
                    raw_outcome = record.payload.get("outcome")
                    if raw_outcome is None:
                        raw_outcome = record.payload.get("outcome_type")
                    canonical = (
                        canonical_outcome(raw_outcome)
                        if isinstance(raw_outcome, str)
                        else "missing_outcome"
                    )
                    histogram[canonical] += 1
                    official = record.payload.get("official_code")
                    if isinstance(official, str):
                        official_codes[official] += 1
                    if canonical == "not_sent":
                        not_sent += 1
                        reason = str(record.payload.get("reason", ""))
                        lowered = reason.lower()
                        # 真实生产方的未发送原因形如 deadline_passed /
                        # deadline_passed_after_schedule；在稳定原因词表
                        # 登记前，以 deadline/timeout 形态识别动作超时。
                        if "timeout" in lowered or "deadline" in lowered:
                            not_sent_timeouts += 1

        for key, entries in intents.items():
            if len(entries) >= 3:
                # 应用层与官方适配器双层各记一次属常态（接口协议 §7.1）；
                # 三条及以上同层重复才识别为异常，按 warning 报告。
                self.findings.append(_Finding(
                    "warning",
                    "duplicate_intent",
                    f"同一 decision_id+attempt_no 出现 {len(entries)} 条提交意图，超过双层记录常态",
                    tuple(entry.location for entry in entries),
                ))
            if key not in outcomes:
                self.findings.append(_Finding(
                    "violation",
                    "dangling_intent",
                    "提交意图没有配对的提交结果：进程中断或结果记录丢失，该次尝试悬空",
                    (entries[0].location,),
                ))
            else:
                # 尝试级时延：最早 intent 到最晚 outcome，双层记录时覆盖完整提交。
                started = min(entry.wall_time_unix_ms for entry in entries)
                finished = max(
                    entry.wall_time_unix_ms for entry in outcomes[key]
                )
                latency = finished - started
                if latency < 0:
                    self.findings.append(_Finding(
                        "warning",
                        "negative_latency",
                        f"outcome 早于 intent {abs(latency)}ms，时钟或记录顺序异常",
                        (entries[0].location, outcomes[key][0].location),
                    ))
                else:
                    latencies.append(latency)

        for key, entries in outcomes.items():
            if len(entries) >= 3:
                # 双层各记一次属常态；三条及以上同层重复才识别为异常。
                self.findings.append(_Finding(
                    "warning",
                    "duplicate_outcome",
                    f"同一 decision_id+attempt_no 出现 {len(entries)} 条提交结果，超过双层记录常态",
                    tuple(entry.location for entry in entries),
                ))
            if key not in intents:
                self.findings.append(_Finding(
                    "violation",
                    "orphan_outcome",
                    "提交结果没有对应的提交意图：无法证明提交前已记录 intent",
                    (entries[0].location,),
                ))

        latencies.sort()
        return {
            "intents": sum(len(v) for v in intents.values()),
            "distinct_attempts": len(intents),
            "outcomes": sum(len(v) for v in outcomes.values()),
            "outcome_histogram": dict(sorted(histogram.items())),
            "official_code_histogram": dict(sorted(official_codes.items())),
            "rejected_total": (
                histogram["rejected_retryable"]
                + histogram["rejected_closed"]
                + histogram["rejected_no_refresh"]
            ),
            "ambiguous": histogram["ambiguous"],
            "not_sent": not_sent,
            "not_sent_timeouts": not_sent_timeouts,
            "latency_ms": {
                "attempts": len(latencies),
                "p50": _percentile(latencies, 50),
                "p95": _percentile(latencies, 95),
                "p99": _percentile(latencies, 99),
                "max": latencies[-1] if latencies else None,
            },
        }

    def check_stage_and_games(self) -> dict[str, Any]:
        """阶段尝试混用、重复终局与覆盖率检查；返回覆盖率统计。"""

        game_stages: dict[tuple[str, str], dict[str, list[_Parsed]]] = {}
        attempt_tournaments: dict[tuple[str, str], set[str]] = {}
        finished_games: dict[tuple[str, str], list[_Parsed]] = {}
        finished_participants: dict[str, list[_Parsed]] = {}
        games: set[tuple[str, str]] = set()
        participants: set[str] = set()
        planned_decisions: set[tuple[str, str]] = set()
        windows: set[tuple[str, str, int, int]] = set()
        degraded_count = 0
        degraded_decisions: list[str] = []

        for record in self.records:
            pid = record.context["participant_id"]
            participants.add(pid)
            game_id = record.context.get("game_id")
            if isinstance(game_id, str) and game_id:
                games.add((pid, game_id))
                stage_attempt = record.context.get("stage_attempt_id")
                stage_key = stage_attempt if isinstance(stage_attempt, str) and stage_attempt else "(缺失)"
                bucket = game_stages.setdefault((pid, game_id), {})
                bucket.setdefault(stage_key, []).append(record)
                if isinstance(stage_attempt, str) and stage_attempt:
                    attempt_tournaments.setdefault((pid, stage_attempt), set()).add(
                        record.context["tournament_id"]
                    )
            if record.kind == AuditKind.GAME_FINISHED.value:
                if isinstance(game_id, str) and game_id:
                    finished_games.setdefault((pid, game_id), []).append(record)
            elif record.kind == AuditKind.PARTICIPANT_FINISHED.value:
                finished_participants.setdefault(pid, []).append(record)
            elif record.kind == AuditKind.DECISION_PLANNED.value:
                decision_id = record.context.get("decision_id")
                if isinstance(decision_id, str) and decision_id:
                    planned_decisions.add((pid, decision_id))
                reasons = record.payload.get("degraded_reasons")
                if isinstance(reasons, list) and reasons:
                    degraded_count += 1
                    if len(degraded_decisions) < 20:
                        degraded_decisions.append(decision_id)
            elif record.kind == AuditKind.AUTHORITATIVE_STATE.value:
                round_no = record.context.get("round_no")
                trigger_seq = record.context.get("trigger_seq")
                if isinstance(game_id, str) and game_id and isinstance(round_no, int) and isinstance(trigger_seq, int):
                    windows.add((pid, game_id, round_no, trigger_seq))

        for (pid, game_id), stages in sorted(game_stages.items()):
            # 混用判定只看「两个及以上不同的非空 stage_attempt_id」：
            # 缺失与非空共存是双层记录的合法形态（官方适配器按契约
            # 不生产 stage_attempt_id，接口协议 §7.1），不算混用。
            named = sorted({key for key in stages if key != "(缺失)"})
            if len(named) > 1:
                locations: list[RecordLocation] = []
                for entries in stages.values():
                    locations.append(entries[0].location)
                self.findings.append(_Finding(
                    "violation",
                    "stage_attempt_mixing",
                    f"同一 participant+game 混用多个不同 stage_attempt_id: {named}；中断尝试的成绩不得混入有效成绩",
                    tuple(locations[:10]),
                ))

        for (pid, stage_attempt), tournament_ids in sorted(attempt_tournaments.items()):
            if len(tournament_ids) > 1:
                self.findings.append(_Finding(
                    "violation",
                    "tournament_mixing",
                    f"同一 participant+stage_attempt 指向多个 tournament_id: {sorted(tournament_ids)}",
                    (),
                ))

        for (pid, game_id), entries in sorted(finished_games.items()):
            if len(entries) >= 3:
                # 应用层与官方适配器各记一次权威终局属常态；三条及以上
                # 同层重复才识别为异常（接口协议 §7.1）。
                self.findings.append(_Finding(
                    "warning",
                    "duplicate_game_finished",
                    f"同一场次出现 {len(entries)} 条 GAME_FINISHED 终局记录，超过双层记录常态",
                    tuple(entry.location for entry in entries),
                ))

        # 终局分数（接口协议 §7.1：双层终局分数一致性由验证器负责）。
        # 合法形态为座位 0—3 的四个整数；双层记录必须一致，否则只报告
        # 不一致而不猜测哪一层正确。
        final_scores_by_game: dict[str, list[int]] = {}
        malformed_scores = 0
        for (pid, game_id), entries in sorted(finished_games.items()):
            observed: list[tuple[int, int, int, int]] = []
            for entry in entries:
                raw = entry.payload.get("final_scores")
                if (
                    isinstance(raw, list)
                    and len(raw) == 4
                    and all(
                        isinstance(value, int) and not isinstance(value, bool)
                        for value in raw
                    )
                ):
                    observed.append((raw[0], raw[1], raw[2], raw[3]))
                else:
                    malformed_scores += 1
                    self.findings.append(_Finding(
                        "warning",
                        "malformed_final_scores",
                        f"GAME_FINISHED 的 final_scores 不是座位 0—3 的四个整数: {raw!r}",
                        (entry.location,),
                    ))
            distinct = set(observed)
            if len(distinct) > 1:
                self.findings.append(_Finding(
                    "warning",
                    "game_finished_score_mismatch",
                    f"同一场次的双层 GAME_FINISHED 终局分数不一致: {sorted(distinct)}",
                    tuple(entry.location for entry in entries),
                ))
                continue
            if distinct:
                final_scores_by_game[f"{pid}/{game_id}"] = list(distinct.pop())
        if malformed_scores:
            self.findings.append(_Finding(
                "warning",
                "malformed_final_scores_summary",
                f"共 {malformed_scores} 条 GAME_FINISHED 记录携带无法解析的 final_scores，已从终局分数汇总中排除",
                (),
            ))

        return {
            "games_total": len(games),
            "games_finished": len(finished_games),
            "final_scores_by_game": final_scores_by_game,
            "participants_total": len(participants),
            "participants_finished": len(finished_participants),
            "decisions_planned": len(planned_decisions),
            "windows_observed": len(windows),
            "rule_degradations": degraded_count,
            "rule_degradation_decisions": degraded_decisions,
            "manifest_present": self.manifest_present,
            "summary_files": self.summary_files,
        }

    def check_required_files(self) -> None:
        """有记录的运行必须具备生命周期流与汇总文件。"""

        if not self.records:
            return
        has_lifecycle = any(
            record.kind == AuditKind.LIFECYCLE_CHANGED.value for record in self.records
        )
        if not has_lifecycle:
            self.findings.append(_Finding(
                "violation",
                "missing_lifecycle",
                "运行存在审计记录但没有 lifecycle.jsonl 生命周期事件",
                (),
            ))
        if self.summary_files == 0:
            self.findings.append(_Finding(
                "violation",
                "missing_summary",
                "运行存在审计记录但没有 summary.json 关闭汇总",
                (),
            ))


    @staticmethod
    def _is_adapter_game_state(payload: dict[str, Any]) -> bool:
        """判定 AUTHORITATIVE_STATE 是否为官方场次适配器的场次层事实。

        场次层形态（official/game.py）：窗口投递带 ``window`` 键，
        快照投影提示带 ``last_discard_projection_note`` /
        ``trigger_seq_projection_note``。这些记录只在 /state 轮询真实发生
        时才会出现，是"该场确实做过状态请求"的可审计证据。
        """

        return any(
            key in payload
            for key in ("window", "last_discard_projection_note", "trigger_seq_projection_note")
        )

    def check_raw_events(self) -> dict[str, Any]:
        """原始协议事件（RAW_PROTOCOL_STATE）的覆盖统计与完整性检查。

        统计：按 source/endpoint/http_status 分组、原文总字节数、legacy 容忍数。
        完整性（仅当运行级 summary.json 声明 raw_retention.mode，即本次运行
        启用全量保留模式时）：

        - ``raw_state_stream_empty``：存在场次层 AUTHORITATIVE_STATE 证据的
          (participant, game) 必须有 state_response 原始事件；
        - ``raw_state_gap``：同一 (participant, game) 的 state_response
          request_no 按会话段连续——request_no 是每场次会话内的成功轮询
          计数（official/game.py _state_request_no），会话/进程重启后归零
          重新从 1 编号：记录顺序中严格回退即为新会话段起点而非缺口；
          每段期望 1 起连续，段首缺失（段内不从 1 起）与段内缺号
          （缺中间值 = 该次响应原文丢失）都按 violation 上报；
        - ``raw_action_missing``：每个实际发出的动作 POST（adapter 层
          SUBMISSION_OUTCOME 且 outcome_type != SubmitNotSent）必须有对应
          action_submit_response 原文；在途取消（submit_cancelled_in_flight）
          没有响应可录，按例外排除。

        旧目录没有 raw_retention 声明时上述检查全部跳过，结论与升级前一致。
        """

        by_source: Counter[str] = Counter()
        by_endpoint: Counter[str] = Counter()
        by_http_status: Counter[str] = Counter()
        raw_bytes_total = 0
        legacy_count = 0
        state_request_nos: dict[tuple[str, str], list[int]] = {}
        action_raw_keys: set[tuple[str, str, int]] = set()
        # 场次层权威证据：出现过状态请求的 (participant, game)。
        state_polled: set[tuple[str, str]] = set()
        for record in self.records:
            pid = record.context.get("participant_id") or ""
            game_id = record.context.get("game_id")
            if record.kind == AuditKind.AUTHORITATIVE_STATE.value:
                if isinstance(game_id, str) and game_id and self._is_adapter_game_state(record.payload):
                    state_polled.add((pid, game_id))
                continue
            if record.kind != AuditKind.RAW_PROTOCOL_STATE.value:
                continue
            raw_text = record.payload.get("raw")
            if isinstance(raw_text, str):
                raw_bytes_total += len(raw_text.encode("utf-8"))
            if not is_new_shape_raw_payload(record.payload):
                legacy_count += 1
                continue
            payload_schema_version = record.payload.get("payload_schema_version")
            if payload_schema_version != RAW_PAYLOAD_SCHEMA_VERSION:
                # 子结构版本演进：新版本仍按已知结构尽力统计与脱敏扫描，
                # 只提示不拒绝（未知字段可能影响严格检查的精确性）。
                self.findings.append(_Finding(
                    "warning",
                    "unknown_raw_payload_schema",
                    f"原始事件 payload_schema_version={payload_schema_version!r} 与当前基线 {RAW_PAYLOAD_SCHEMA_VERSION} 不同，按已知结构尽力检查",
                    (record.location,),
                ))
            source = record.payload.get("source")
            by_source[str(source)] += 1
            endpoint = record.payload.get("endpoint")
            if isinstance(endpoint, str):
                by_endpoint[endpoint] += 1
            http_status = record.payload.get("http_status")
            if isinstance(http_status, int):
                by_http_status[str(http_status)] += 1
            if source == RAW_SOURCE_STATE_RESPONSE:
                if isinstance(game_id, str) and game_id and pid:
                    request_no = record.payload.get("request_no")
                    if isinstance(request_no, int) and not isinstance(request_no, bool):
                        state_request_nos.setdefault((pid, game_id), []).append(request_no)
                    else:
                        self.findings.append(_Finding(
                            "warning",
                            "malformed_raw_request_no",
                            "state_response 原始事件的 request_no 缺失或不是整数，无法参与连续性检查",
                            (record.location,),
                        ))
            elif source == RAW_SOURCE_ACTION_RESPONSE:
                decision_id = record.context.get("decision_id")
                attempt_no = record.context.get("attempt_no")
                if not isinstance(decision_id, str) or not decision_id:
                    decision_id = record.payload.get("decision_id")
                if not isinstance(attempt_no, int) or isinstance(attempt_no, bool):
                    attempt_no = record.payload.get("attempt_no")
                if isinstance(decision_id, str) and decision_id and isinstance(attempt_no, int) and not isinstance(attempt_no, bool):
                    action_raw_keys.add((pid, decision_id, attempt_no))

        # ---- 严格完整性检查（raw_retention 模式启用时才生效） ----
        if self.raw_retention is None:
            return {
                "retention_mode": "legacy",
                "records_total": sum(by_source.values()) + legacy_count,
                "records_legacy": legacy_count,
                "by_source": dict(sorted(by_source.items())),
                "by_endpoint": dict(sorted(by_endpoint.items())),
                "by_http_status": dict(sorted(by_http_status.items())),
                "raw_bytes_total": raw_bytes_total,
            }

        # 1) 每个做过状态请求的场都必须有原始事件流。
        for pid, game_id in sorted(state_polled):
            if (pid, game_id) not in state_request_nos:
                self.findings.append(_Finding(
                    "violation",
                    "raw_state_stream_empty",
                    f"场次存在状态请求证据但没有 state_response 原始事件记录：participant={pid} game={game_id}"
                    + self._raw_dropped_suffix(),
                    (),
                ))

        # 2) request_no 会话分段连续性。request_no 是"每场次会话内成功
        #    轮询计数"（official/game.py _state_request_no 注释：跨会话
        #    重启归零安全），同 (participant, game) 的原始事件跨进程重启
        #    后重新从 1 编号。记录按落盘顺序单调不减（失败事件复用当前
        #    计数，允许相等重复），出现严格回退即新会话段起点——不是
        #    缺口（d6-c3c77a 登记项：旧"全局取值集合连续"把重启误当断号，
        #    且数值被上一段覆盖时检不出新段首段丢失）。每段期望 1 起
        #    连续：段首缺失与段内缺号都按该段响应原文丢失上报。
        for (pid, game_id), numbers in sorted(state_request_nos.items()):
            segments: list[list[int]] = []
            for number in numbers:
                if segments and number < segments[-1][-1]:
                    segments.append([number])  # 严格回退：新会话段起点
                elif segments:
                    segments[-1].append(number)
                else:
                    segments.append([number])
            gap_parts: list[str] = []
            for seg_index, segment in enumerate(segments, start=1):
                seg_max = max(segment)
                if seg_max <= 0:
                    # 段内只有 request_no=0 的错误占位（重启后首批请求
                    # 失败、成功计数尚未发生），无成功响应可对账
                    continue
                observed = set(segment)
                # 期望覆盖 1..段内最大值；段首缺失与段内缺号统一列出
                missing = sorted(n for n in range(1, seg_max + 1) if n not in observed)
                if not missing:
                    continue
                sample = missing[:10]
                ellipsis = "..." if len(missing) > 10 else ""
                if 1 in observed:
                    gap_parts.append(
                        f"第{seg_index}会话段段内缺号：request_no 缺失 {sample}{ellipsis}"
                    )
                else:
                    # 段内 request_no 不从 1 起 = 该段首条记录缺失（数值
                    # 可能被上一段的同号记录掩盖，按段独立对账才能检出）
                    gap_parts.append(
                        f"第{seg_index}会话段段首缺失（request_no 不从 1 起）："
                        f"request_no 缺失 {sample}{ellipsis}"
                    )
            if gap_parts:
                self.findings.append(_Finding(
                    "violation",
                    "raw_state_gap",
                    f"participant={pid} game={game_id} 的 state 响应原文存在缺口："
                    + "；".join(gap_parts)
                    + self._raw_dropped_suffix(),
                    (),
                ))

        # 3) 实际发出的动作 POST 必须有响应原文（在途取消例外）。
        for record in self.records:
            if record.kind != AuditKind.SUBMISSION_OUTCOME.value:
                continue
            if "outcome_type" not in record.payload:
                continue  # 应用层 outcome 记录不参与本检查（adapter 层才有 outcome_type）
            outcome_type = record.payload.get("outcome_type")
            if outcome_type == "SubmitNotSent":
                continue  # 未发 POST：没有响应可录
            if outcome_type == "SubmitAmbiguous" and record.payload.get("reason") == SUBMISSION_CANCELLED_IN_FLIGHT:
                continue  # 在途取消：POST 是否发出未知，响应原文不存在属预期
            pid = record.context.get("participant_id") or ""
            decision_id = record.context.get("decision_id")
            attempt_no = record.context.get("attempt_no")
            if isinstance(decision_id, str) and decision_id and isinstance(attempt_no, int) and not isinstance(attempt_no, bool):
                key = (pid, decision_id, attempt_no)
                if key not in action_raw_keys:
                    self.findings.append(_Finding(
                        "violation",
                        "raw_action_missing",
                        f"动作 POST 已发出但没有 action_submit_response 原始事件："
                        f"decision_id={decision_id} attempt_no={attempt_no}"
                        + self._raw_dropped_suffix(),
                        (record.location,),
                    ))

        mode = self.raw_retention.get("mode")
        return {
            "retention_mode": mode if isinstance(mode, str) else "unknown",
            "records_total": sum(by_source.values()) + legacy_count,
            "records_legacy": legacy_count,
            "by_source": dict(sorted(by_source.items())),
            "by_endpoint": dict(sorted(by_endpoint.items())),
            "by_http_status": dict(sorted(by_http_status.items())),
            "raw_bytes_total": raw_bytes_total,
            "state_polled_games": len(state_polled),
            "state_stream_games": len(state_request_nos),
            "action_responses": len(action_raw_keys),
        }
    def _raw_dropped_suffix(self) -> str:
        """violation 报告附注背压丢弃计数（F-21）：接线缺失与背压丢弃两种红因可区分。"""

        if self.raw_retention is None:
            return ""
        dropped = self.raw_retention.get("dropped")
        if not isinstance(dropped, int):
            return ""
        return "；raw_retention.dropped={0}".format(dropped)

    def check_audit_plus(self) -> dict[str, Any]:
        """audit-plus-v1 增强校验；profile 未声明时返回 legacy 不收紧旧日志。

        只在 manifest 声明 capture_profile=audit-plus-v1 时执行（方案
        §7.2）：旧目录结论与升级前完全一致。检查项：

        - missing_producer_summary（violation）：profile 运行必须有
          LIFECYCLE_CHANGED(area=audit, event=producer_summary) 关闭证据，
          否则尾部完整性未知——不能从文件没有报错推断完整（方案 §3.4，
          审查 S1）；
        - decision_input_without_end（violation）：同一决策输入没有
          终结证据，说明进程在决策中途死亡或终结记录丢失；
        - ended_without_input（warning）：终结无输入属合法形态（窗口在
          规划前到达截止），只提示不失败。
        """

        if self.capture_profile != "audit-plus-v1":
            return {"profile": "legacy"}
        producer_summaries: list[_Parsed] = []
        producer_failures: list[_Parsed] = []
        inputs: dict[tuple[str, str], _Parsed] = {}
        ended: dict[tuple[str, str], _Parsed] = {}
        for record in self.records:
            if record.kind != AuditKind.LIFECYCLE_CHANGED.value:
                if record.kind == AuditKind.DECISION_INPUT.value:
                    pid = record.context.get("participant_id") or ""
                    decision_id = record.context.get("decision_id")
                    if isinstance(decision_id, str) and decision_id:
                        inputs.setdefault((pid, decision_id), record)
                elif record.kind == AuditKind.DECISION_ENDED.value:
                    pid = record.context.get("participant_id") or ""
                    decision_id = record.context.get("decision_id")
                    if isinstance(decision_id, str) and decision_id:
                        ended.setdefault((pid, decision_id), record)
                continue
            payload = record.payload
            if payload.get("area") != "audit":
                continue
            event = payload.get("event")
            if event == "producer_summary":
                producer_summaries.append(record)
            elif event == "producer_failure":
                producer_failures.append(record)
        tail_complete = False
        if producer_failures:
            # S1（前次审查）：构造失败持久化后，运行必须标记不完整——
            # 高优先级决策记录已丢失，不能靠"没有报错"推断完整。
            self.findings.append(_Finding(
                "violation",
                "producer_failure_occurred",
                "profile=audit-plus-v1 运行存在 {} 条生产端构造失败（producer_failure），关键决策记录缺失，不能宣称完整可审计".format(len(producer_failures)),
                tuple(record.location for record in producer_failures[:10]),
            ))
        if not producer_summaries:
            self.findings.append(_Finding(
                "violation",
                "missing_producer_summary",
                "profile=audit-plus-v1 运行缺少 producer_summary 关闭证据：尾部完整性未知，不能从文件没有报错推断完整",
                (),
            ))
        else:
            # 关闭证据存在且 summary.json 已写入（missing_summary 检查
            # 另行负责）即可判断尾部已完整关闭。
            tail_complete = self.summary_files > 0
            summary_payload = producer_summaries[-1].payload
            attempts = summary_payload.get("attempts")
            construction = summary_payload.get("construction_failures")
            if not isinstance(attempts, int) or not isinstance(construction, int):
                self.findings.append(_Finding(
                    "warning",
                    "malformed_producer_summary",
                    "producer_summary 的 attempts/construction_failures 缺失或不是整数，无法对账",
                    (producer_summaries[-1].location,),
                ))
            elif attempts < construction or construction != len(producer_failures):
                # producer_failure 最小失败记录自身写不下时允许少计数
                # （方案 §3.4：依靠失败计数和缺失关闭证明报告不完整），
                # 不一致按 warning 提示人工裁决。
                self.findings.append(_Finding(
                    "warning",
                    "producer_summary_mismatch",
                    "producer_summary 计数与 producer_failure 记录数不一致：attempts={} construction_failures={} failure_records={}".format(
                        attempts, construction, len(producer_failures)
                    ),
                    (producer_summaries[-1].location,),
                ))
        for (pid, decision_id), record in sorted(inputs.items()):
            if (pid, decision_id) not in ended:
                self.findings.append(_Finding(
                    "violation",
                    "decision_input_without_end",
                    f"DECISION_INPUT 没有配对的 DECISION_ENDED：participant={pid} decision_id={decision_id}，决策中途死亡或终结记录丢失",
                    (record.location,),
                ))
        for (pid, decision_id), record in sorted(ended.items()):
            if (pid, decision_id) not in inputs:
                self.findings.append(_Finding(
                    "warning",
                    "ended_without_input",
                    f"DECISION_ENDED 没有对应的 DECISION_INPUT：participant={pid} decision_id={decision_id}（窗口在规划前到达截止属合法形态）",
                    (record.location,),
                ))
        return {
            "profile": "audit-plus-v1",
            "tail_complete": tail_complete,
            "producer_summary": (
                producer_summaries[-1].payload if producer_summaries else None
            ),
            "producer_failure_records": len(producer_failures),
            "decisions_with_input": len(inputs),
            "decisions_ended": len(ended),
        }



def validate_run(run_dir: str | Path) -> dict[str, Any]:
    """验证一次运行的审计目录，返回 JSON 可序列化的完整报告。"""

    directory = Path(run_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"审计运行目录不存在: {directory}")
    scanner = _RunScanner(directory)
    scanner.scan()
    submissions = scanner.check_submissions()
    coverage = scanner.check_stage_and_games()
    raw_events = scanner.check_raw_events()
    audit_plus = scanner.check_audit_plus()
    scanner.check_required_files()

    counts_by_kind = Counter(record.kind for record in scanner.records)
    violations = [f for f in scanner.findings if f.severity == "violation"]
    return {
        "run_dir": str(directory),
        "files_scanned": scanner.files_scanned,
        "lines_total": len(scanner.records) + len(scanner.corrupt_lines) + len(scanner.malformed_records),
        "counts_by_kind": dict(sorted(counts_by_kind.items())),
        "corrupt_lines": scanner.corrupt_lines,
        "malformed_records": scanner.malformed_records,
        "secret_scan_clean": not any(f.code == "secret_found" for f in scanner.findings),
        "submissions": submissions,
        "coverage": coverage,
        "raw_events": raw_events,
        "audit_plus": audit_plus,
        "findings": [
            {
                "severity": finding.severity,
                "code": finding.code,
                "detail": finding.detail,
                "locations": [
                    {"file": loc.file, "line_no": loc.line_no} for loc in finding.locations
                ],
            }
            for finding in scanner.findings
        ],
        "violation_count": len(violations),
        "audit_complete": not violations,
        "ok": not violations,
    }


def main(argv: list[str] | None = None) -> int:
    """命令行入口：打印 JSON 报告；存在 violation 时退出码 1。"""

    parser = argparse.ArgumentParser(
        prog="python -m hangma_bot.adapters.recording.validator",
        description="离线验证一次运行的审计记录完整性",
    )
    parser.add_argument("run_dir", help="runs/{run_id} 目录路径")
    args = parser.parse_args(argv)
    report = validate_run(args.run_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["audit_complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
