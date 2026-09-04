"""离线审计验证器：读取一次运行的审计目录，真实报告记录是否完整。

定位（模块说明 §validator）：在赛事结束后独立运行，不参与线上动作路径；
它只读取 ``runs/{run_id}/`` 下的 JSONL 与 JSON 文件，输出机器可读报告。

检查项（对应模块完成定义与 ``mvp-acceptance.md`` §4）：

- 悬空动作尝试：``SUBMISSION_INTENT`` 没有配对的 ``SUBMISSION_OUTCOME``；
- 孤立结果：没有 intent 的 outcome；
- 重复记录（warning 级）：同一 ``(decision_id, attempt_no)`` 的 intent/outcome、
  同一场次的 ``GAME_FINISHED`` 可能被应用层与官方适配器各记录一次，
  双层记录属常态，仅作为冗余提示，不影响完整判定；
- 阶段尝试混用：同一 ``(participant_id, game_id)`` 出现多个 ``stage_attempt_id``，
  或缺失 ``stage_attempt_id`` 的记录与有值的记录混在同一局；
- 损坏行：无法 JSON 解码或信封字段不完整的行，逐行报告位置；
- 密文扫描：复用写入侧同一组形态判定，要求认证原文扫描结果为 0；
- 覆盖率与统计：各类计数、规则降级、显式拒绝（409 族）、模糊提交、
  未发送/超时，以及"最早 intent → 最晚 outcome"的尝试级 P50/P95/P99 时延；
  提交结果词表经 :func:`canonical_outcome` 归并规范值与封闭类名两种生产形态。

结论语义：报告中的 ``audit_complete`` 只在没有任何 ``violation`` 级发现时为真；
``warning`` 级发现不改变结论。验证器"失败"即 ``audit_complete=false``，
不允许在关键信封缺失时默认成功。

命令行用法：``python -m hangma_bot.adapters.recording.validator <run_dir>``，
报告以 UTF-8 JSON 打印到标准输出；发现 violation 时退出码为 1。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hangma_bot.adapters.recording.redact import (
    REDACTED,
    is_sensitive_key,
    unredacted_secret_matches,
)
from hangma_bot.adapters.recording.schema import AUDIT_SCHEMA_VERSION, canonical_outcome
from hangma_bot.application.contracts import AuditKind


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
        if name.endswith(".jsonl"):
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
) -> None:
    """递归扫描结构：敏感键未脱敏或字符串值残留凭证形态都算命中。"""

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
            _walk_secrets(value, hits, location, child_path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_secrets(value, hits, location, f"{path}[{index}]")
    elif isinstance(node, str):
        for match in unredacted_secret_matches(node):
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
        with path.open("r", encoding="utf-8", errors="replace") as handle:
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
            if len(entries) > 1:
                # 应用层与官方适配器都会为同一次尝试记录意图：双层记录属常态，
                # 只按冗余提示报告，不作为完整性违规。
                self.findings.append(_Finding(
                    "warning",
                    "duplicate_intent",
                    f"同一 decision_id+attempt_no 出现 {len(entries)} 条提交意图（双层记录常态）",
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
            if len(entries) > 1:
                self.findings.append(_Finding(
                    "warning",
                    "duplicate_outcome",
                    f"同一 decision_id+attempt_no 出现 {len(entries)} 条提交结果（双层记录常态）",
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
            "rejected_total": histogram["rejected_retryable"] + histogram["rejected_closed"],
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
            if len(stages) > 1:
                locations: list[RecordLocation] = []
                for entries in stages.values():
                    locations.append(entries[0].location)
                self.findings.append(_Finding(
                    "violation",
                    "stage_attempt_mixing",
                    f"同一 participant+game 混用多个 stage_attempt_id: {sorted(stages)}；中断尝试的成绩不得混入有效成绩",
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
            if len(entries) > 1:
                # 应用层与官方适配器各记录一次权威终局：双层记录属常态。
                self.findings.append(_Finding(
                    "warning",
                    "duplicate_game_finished",
                    f"同一场次出现 {len(entries)} 条 GAME_FINISHED 终局记录（双层记录常态）",
                    tuple(entry.location for entry in entries),
                ))

        return {
            "games_total": len(games),
            "games_finished": len(finished_games),
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


def validate_run(run_dir: str | Path) -> dict[str, Any]:
    """验证一次运行的审计目录，返回 JSON 可序列化的完整报告。"""

    directory = Path(run_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"审计运行目录不存在: {directory}")
    scanner = _RunScanner(directory)
    scanner.scan()
    submissions = scanner.check_submissions()
    coverage = scanner.check_stage_and_games()
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
