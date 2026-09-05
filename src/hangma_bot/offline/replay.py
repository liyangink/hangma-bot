"""统一牌谱 v1：跨进程身份、视角合并、决策行与单局行组装。

审计线是统一牌谱文件的读写器所有者（parallel-contracts §2）。本模块
从不可变证据包（bundle）读取运行审计与官方下载，产出可训练的
derived/{dataset_id}/ 数据集：

- manifest.json：契约、来源、代码与规则哈希、已知缺失；
- index.jsonl：跨进程单局身份与划分映射（hand_id 对 views/official_refs）；
- decisions.jsonl：完整决策行（只含当时可见信息）；
- hands.jsonl：官方下载转换的单局行（最多 full_history，绝不 full_world）；
- validation.json：文件完整性 / 决策完整性 / 历史覆盖 / 世界可导入性 /
  规则一致性分项报告（passed/failed/not_checked，不用一个 ok 代替）。

身份算法（契约 §4.1，与 contract-vectors.json 锁定向量一致）：

- hand_id = "hand-" + sha256(json([source_namespace, tournament_id,
  game_id, round_no]))：四项按给定顺序编码为 JSON 数组
  （ensure_ascii=False、separators=(",", ":")、allow_nan=False），
  取 UTF-8 SHA-256 全长十六进制；
- split_group_id：官方取 "split-" + 同算法处理 [source_namespace,
  tournament_id]，整个赛事/反复使用的测试房间不跨训练划分；
- 前三项是非空字符串且不做 strip/大小写改写，round_no 是排除 bool
  的正整数；错误输入抛 ValueError。

信息权限：决策行只还原当时 PlayerObservation 可见信息；官方下载的
隐藏信息（起手四家、完整事件流）只进入 hands.jsonl 供离线标签，
绝不回写 request。缺完整 request 的旧记录只进入 validation 的缺失
列表，不伪造可训练决策。
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hangma_bot.adapters.official.replay import (
    parse_room_document,
    round_data as official_round_data,
)
from hangma_bot.adapters.recording.bundle import verify_bundle
from hangma_bot.adapters.recording.reader import read_bundle_manifest, read_records
from hangma_bot.adapters.recording.schema import canonical_outcome

REPLAY_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
CONTRACT_ID = "parallel-v1"

# 决策终结原因词表（契约 §5.1）；无完整结束证据为 unknown。
END_REASON_VALUES = frozenset(
    {"submitted", "exhausted", "deadline", "cancelled", "error", "unknown"}
)

# 提交结果 → execution_status（契约 §5.1）：
# confirmed = 平台已接受提交（权威执行与否由事件/结果另行确认，
# 200 接受不自动等同于动作已权威执行）；unresolved = 结果不确定；
# not_executed = 平台明确未执行或未发出。
_EXECUTION_STATUS = {
    "accepted": "confirmed",
    "ambiguous": "unresolved",
    "rejected_retryable": "not_executed",
    "rejected_closed": "not_executed",
    "rejected_no_refresh": "not_executed",
    "not_sent": "not_executed",
    "fatal": "not_executed",
}


def _encode_identity(fields: Sequence[object]) -> str:
    """契约 §4.1 的稳定身份编码：JSON 数组 → UTF-8 SHA-256 全长十六进制。"""

    text = json.dumps(
        list(fields), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_identity_component(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise ValueError(label + " 必须是非空字符串（不做 strip/大小写改写）")
    return value


def hand_id(source_namespace: str, tournament_id: str, game_id: str, round_no: int) -> str:
    """从权威场次身份生成跨机器稳定单局标识，不包含本地 run/attempt。

    round_no 是排除 bool 的正整数；牌谱缺失时不得猜测，错误输入抛
    ValueError。直接使用返回的完整 game_id，不解析其命名规律。
    """

    namespace = _require_identity_component(source_namespace, "source_namespace")
    tournament = _require_identity_component(tournament_id, "tournament_id")
    game = _require_identity_component(game_id, "game_id")
    if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no <= 0:
        raise ValueError("round_no 必须是排除 bool 的正整数，得到 {!r}".format(round_no))
    return "hand-" + _encode_identity([namespace, tournament, game, round_no])


def split_group_id(source_namespace: str, tournament_id: str) -> str:
    """官方口径的训练划分键：同一赛事/测试房间不跨训练划分。

    模拟线使用 [source_namespace, scenario_id] 的独立口径（契约 §4.1），
    本函数只实现官方分支。
    """

    namespace = _require_identity_component(source_namespace, "source_namespace")
    tournament = _require_identity_component(tournament_id, "tournament_id")
    return "split-" + _encode_identity([namespace, tournament])


def _jsonl_lines(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """把行对象编码为严格 JSONL 文本；NaN/Inf 拒绝（有限数值契约）。"""

    return [
        json.dumps(dict(row), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + chr(10)
        for row in rows
    ]


def _atomic_write_text(path: Path, text: str) -> None:
    """先写临时文件再原子改名；中途失败不留下半成品产物。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_write_json(path: Path, document: Mapping[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(dict(document), ensure_ascii=False, indent=2, allow_nan=False)
        + chr(10),
    )


def load_hand_rows(path: str | Path) -> list[dict[str, Any]]:
    """读取 hands.jsonl；未知主版本拒绝并保留原文件（契约 §4.2）。

    replay_schema_version 不等于当前版本的行整体拒绝：删除/改类型/改
    信息权限/改标识算法属于破坏性变更，必须升级版本并提供迁移说明，
    不能静默按新字段读取旧数据。
    """

    handle = Path(path)
    if not handle.is_file():
        raise FileNotFoundError("hands.jsonl 不存在: {}".format(handle))
    rows: list[dict[str, Any]] = []
    with handle.open("r", encoding="utf-8") as stream:
        for line_no, raw in enumerate(stream, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "hands.jsonl 第 {} 行无法解析: {}".format(line_no, exc.msg)
                ) from None
            if not isinstance(row, dict):
                raise ValueError("hands.jsonl 第 {} 行必须是 JSON 对象".format(line_no))
            version = row.get("replay_schema_version")
            if isinstance(version, bool) or not isinstance(version, int):
                raise ValueError(
                    "hands.jsonl 第 {} 行缺少 replay_schema_version".format(line_no)
                )
            if version != REPLAY_SCHEMA_VERSION:
                raise ValueError(
                    "hands.jsonl 第 {} 行 replay_schema_version={!r} 与当前版本 {} "
                    "不匹配，拒绝读取未知主版本".format(line_no, version, REPLAY_SCHEMA_VERSION)
                )
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 决策行组装
# ---------------------------------------------------------------------------


def _group_records_by_kind(result) -> OrderedDict[str, list[Any]]:
    """按 kind 分组读取结果；保留文件序（同文件内按行号）。"""

    groups: OrderedDict[str, list[Any]] = OrderedDict()
    for record in result.records:
        if record.kind is None or record.error is not None:
            continue
        groups.setdefault(record.kind, []).append(record)
    return groups


def _decision_source_refs(records: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "run_id": record.context.get("run_id"),
            "file": record.relative_path,
            "line_no": record.line_no,
        }
        for record in records
        if record.context is not None
    ]


def _view_for_decision_input(record: Any):
    """从 DECISION_INPUT 的 codec JSON 提取观察座位；无法确认时返回 None。"""

    payload = record.payload or {}
    request = payload.get("request")
    seat = None
    if isinstance(request, dict):
        observation = request.get("observation")
        if isinstance(observation, dict) and isinstance(observation.get("seat"), int):
            seat = observation["seat"]
    return seat


def build_decision_rows(
    groups: Mapping[str, Sequence[Any]],
    *,
    source_namespace: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 (participant_id, decision_id) 组装决策行。

    返回 (rows, excluded)：rows 是具备完整身份与输入证据的决策行；
    excluded 是缺失列表条目（旧记录无 DECISION_INPUT 或缺少场次身份），
    只进 validation，不伪造可训练决策。
    """

    inputs: dict[tuple[str, str], list[Any]] = {}
    for record in groups.get("decision_input", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        if isinstance(pid, str) and isinstance(did, str):
            inputs.setdefault((pid, did), []).append(record)
    planned: dict[tuple[str, str], list[Any]] = {}
    for record in groups.get("decision_planned", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        if isinstance(pid, str) and isinstance(did, str):
            planned.setdefault((pid, did), []).append(record)
    validated: dict[tuple[str, str], list[Any]] = {}
    for record in groups.get("candidate_validated", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        if isinstance(pid, str) and isinstance(did, str):
            validated.setdefault((pid, did), []).append(record)
    ended: dict[tuple[str, str], list[Any]] = {}
    for record in groups.get("decision_ended", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        if isinstance(pid, str) and isinstance(did, str):
            ended.setdefault((pid, did), []).append(record)
    intents: dict[tuple[str, str, int], list[Any]] = {}
    outcomes: dict[tuple[str, str, int], list[Any]] = {}
    for record in groups.get("submission_intent", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        attempt = context.get("attempt_no")
        if isinstance(pid, str) and isinstance(did, str) and isinstance(attempt, int):
            intents.setdefault((pid, did, attempt), []).append(record)
    for record in groups.get("submission_outcome", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        attempt = context.get("attempt_no")
        if isinstance(pid, str) and isinstance(did, str) and isinstance(attempt, int):
            outcomes.setdefault((pid, did, attempt), []).append(record)

    all_keys: set[tuple[str, str]] = set()
    for key in inputs:
        all_keys.add(key)
    for key in planned:
        all_keys.add(key)
    for key in ended:
        all_keys.add(key)

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for (pid, did) in sorted(all_keys):
        input_records = inputs.get((pid, did), [])
        if not input_records:
            excluded.append(
                {
                    "participant_id": pid,
                    "decision_id": did,
                    "reason": "missing_decision_input",
                    "source_refs": _decision_source_refs(
                        planned.get((pid, did), []) + ended.get((pid, did), [])
                    ),
                }
            )
            continue
        # 同一决策多次规划：取最大 plan_revision 的输入。
        latest_input = max(
            input_records,
            key=lambda record: (
                record.payload.get("plan_revision") if record.payload else -1
            ),
        )
        context = latest_input.context or {}
        game_id = context.get("game_id")
        round_no = context.get("round_no")
        tournament_id = context.get("tournament_id")
        if not (isinstance(game_id, str) and game_id) or not isinstance(round_no, int) or isinstance(round_no, bool):
            excluded.append(
                {
                    "participant_id": pid,
                    "decision_id": did,
                    "reason": "missing_game_identity",
                    "source_refs": _decision_source_refs(input_records),
                }
            )
            continue
        if not (isinstance(tournament_id, str) and tournament_id):
            excluded.append(
                {
                    "participant_id": pid,
                    "decision_id": did,
                    "reason": "missing_tournament_identity",
                    "source_refs": _decision_source_refs(input_records),
                }
            )
            continue
        hid = hand_id(source_namespace, tournament_id, game_id, round_no)
        sgid = split_group_id(source_namespace, tournament_id)
        payload = latest_input.payload or {}
        plan_revision = payload.get("plan_revision")
        request_json = payload.get("request")
        budget_json = payload.get("budget")
        budget_origin = payload.get("budget_origin_monotonic")
        # 完整性复核：request 必须能经 codec 还原（不补算缺失历史事实）。
        request_ok = False
        if isinstance(request_json, dict):
            try:
                from hangma_bot.application.audit_codec import decision_request_from_json
                decision_request_from_json(request_json)
                request_ok = True
            except (TypeError, ValueError):
                request_ok = False
        returned_plan = None
        effective_candidates: list[Any] = []
        filter_reasons: list[Any] = []
        planned_records = planned.get((pid, did), [])
        if planned_records:
            latest_planned = max(
                planned_records,
                key=lambda record: (
                    record.payload.get("plan_revision") if record.payload else -1
                ),
            )
            planned_payload = latest_planned.payload or {}
            returned_plan = planned_payload.get("returned_plan")
            effective_candidates = planned_payload.get("effective_candidates") or []
            filter_reasons = planned_payload.get("filter_reasons") or []
        validations: list[dict[str, Any]] = []
        for record in validated.get((pid, did), []):
            item = record.payload or {}
            validations.append(
                {
                    "action_key": item.get("action_key"),
                    "legal": item.get("legal"),
                    "reason": item.get("reason"),
                    "elapsed_ms": item.get("elapsed_ms"),
                }
            )
        attempts: list[dict[str, Any]] = []
        attempt_nos = sorted({key[2] for key in intents if key[:2] == (pid, did)})
        for attempt_no in attempt_nos:
            intent_records = intents.get((pid, did, attempt_no), [])
            outcome_records = outcomes.get((pid, did, attempt_no), [])
            intent_payload = intent_records[0].payload if intent_records else {}
            action_key = intent_payload.get("action_key")
            # 完整动作从实际采用候选里按 action_key 关联（含杠种/牌值）。
            action_json = None
            for candidate in effective_candidates:
                if candidate.get("action_key") == action_key:
                    action_json = candidate.get("action")
                    break
            outcome = None
            official_code = None
            reason = None
            if outcome_records:
                outcome_payload = outcome_records[0].payload or {}
                raw_outcome = outcome_payload.get("outcome")
                if raw_outcome is None:
                    raw_outcome = outcome_payload.get("outcome_type")
                if isinstance(raw_outcome, str):
                    outcome = canonical_outcome(raw_outcome)
                official_code = outcome_payload.get("official_code")
                reason = outcome_payload.get("reason")
            execution = _EXECUTION_STATUS.get(outcome) if outcome else None
            attempts.append(
                {
                    "attempt_no": attempt_no,
                    "action_key": action_key,
                    "action": action_json,
                    "outcome": outcome,
                    "official_code": official_code,
                    "reason": reason,
                    "execution_status": execution,
                    "source_refs": _decision_source_refs(
                        intent_records + outcome_records
                    ),
                }
            )
        end_reason = None
        end_source_refs: list[dict[str, Any]] = []
        for record in ended.get((pid, did), []):
            end_payload = record.payload or {}
            end_reason = end_payload.get("end_reason")
            end_source_refs = _decision_source_refs([record])
        if end_reason not in END_REASON_VALUES:
            end_reason = None
        decision_complete = bool(
            request_ok and ended.get((pid, did)) and end_reason not in (None, "unknown")
        )
        rows.append(
            {
                "replay_schema_version": REPLAY_SCHEMA_VERSION,
                "hand_id": hid,
                "split_group_id": sgid,
                "run_id": context.get("run_id"),
                "participant_id": pid,
                "decision_id": did,
                "plan_revision": plan_revision,
                "request": request_json,
                "budget": budget_json,
                "budget_origin_monotonic": budget_origin,
                "returned_plan": returned_plan,
                "effective_candidates": effective_candidates,
                "filter_reasons": filter_reasons,
                "validations": validations,
                "attempts": attempts,
                "end_reason": end_reason,
                "decision_complete": decision_complete,
                "source_refs": _decision_source_refs(input_records)
                + _decision_source_refs(planned_records)
                + end_source_refs,
            }
        )
    return rows, excluded


# ---------------------------------------------------------------------------
# 单局行与跨进程索引
# ---------------------------------------------------------------------------


def _official_downloads(bundle_dir: Path) -> list[dict[str, Any]]:
    """读取 bundle 内 official/{download_id}/ 的 source.json + events.json。

    损坏或缺失的下载**绝不静默丢弃**（审查返工项）：返回条目携带
    error 字段，由 build_hand_rows_and_index 记入 history_issues——
    封存的下载证据无法解析时，历史覆盖必须显式失败，不能把损坏的
    下载当成"从未存在"从而伪造完整。
    """

    downloads: list[dict[str, Any]] = []
    official_root = bundle_dir / "official"
    if not official_root.is_dir():
        return downloads
    for download_dir in sorted(official_root.iterdir()):
        if not download_dir.is_dir():
            continue
        download_id = download_dir.name
        source_path = download_dir / "source.json"
        events_path = download_dir / "events.json"
        missing = [
            name
            for name, path in (("source.json", source_path), ("events.json", events_path))
            if not path.is_file()
        ]
        if missing:
            downloads.append(
                {
                    "download_id": download_id,
                    "error": "incomplete_download",
                    "detail": "缺少文件: " + ", ".join(missing),
                }
            )
            continue
        try:
            source = json.loads(source_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            downloads.append(
                {
                    "download_id": download_id,
                    "error": "corrupt_source_json",
                    "detail": "{}: {}".format(type(exc).__name__, exc),
                }
            )
            continue
        try:
            events = json.loads(events_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            downloads.append(
                {
                    "download_id": download_id,
                    "error": "corrupt_events_json",
                    "detail": "{}: {}".format(type(exc).__name__, exc),
                }
            )
            continue
        if not isinstance(source, dict) or not isinstance(events, dict):
            downloads.append(
                {
                    "download_id": download_id,
                    "error": "invalid_download_shape",
                    "detail": "source.json/events.json 必须是 JSON 对象",
                }
            )
            continue
        downloads.append(
            {
                "download_id": download_id,
                "source": source,
                "events": events,
                "events_relative": events_path.relative_to(bundle_dir).as_posix(),
            }
        )
    return downloads


def build_hand_rows_and_index(
    bundle_dir: Path,
    groups: Mapping[str, Sequence[Any]],
    *,
    source_namespace: str,
    guide_version: int | None,
    guide_captured_at: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """组装单局行与 index 行；返回 (hand_rows, index_rows, history_issues)。

    身份合并（审查 R1）：四个不同 stage_attempt UUID 与重启后的新 run
    通过完整官方场次键（namespace/tournament_id/game_id/round_no）合并
    为同一个 hand_id，共用 split_group_id；views 只追加不覆盖。
    """

    from hangma_bot.adapters.recording.bundle import sha256_file

    downloads = _official_downloads(bundle_dir)
    hand_accumulator: OrderedDict[str, dict[str, Any]] = OrderedDict()
    official_refs_by_hand: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    history_issues: list[dict[str, Any]] = []

    for download in downloads:
        if "error" in download:
            # 下载损坏/缺失：证据必须进入 history_issues，绝不静默丢弃
            # （history_coverage 因此判 failed，不伪造完整覆盖）。
            history_issues.append(
                {
                    "download_id": download["download_id"],
                    "issue": download["error"],
                    "detail": download.get("detail"),
                }
            )
            continue
        source = download["source"]
        events_doc = download["events"]
        room_id = source.get("room_id")
        game_id = source.get("game_id")
        batch = source.get("batch")
        try:
            parsed = parse_room_document(events_doc)
        except ValueError as exc:
            history_issues.append(
                {
                    "download_id": download["download_id"],
                    "issue": "unparseable_room_document",
                    "detail": str(exc),
                }
            )
            continue
        file_sha = sha256_file(bundle_dir / download["events_relative"])
        for round_no in sorted({block.round_no for block in parsed.blocks}):
            if not (isinstance(room_id, str) and room_id and isinstance(game_id, str) and game_id):
                history_issues.append(
                    {
                        "download_id": download["download_id"],
                        "issue": "missing_identity_in_source_json",
                    }
                )
                continue
            try:
                hid = hand_id(source_namespace, room_id, game_id, round_no)
            except ValueError as exc:
                history_issues.append(
                    {
                        "download_id": download["download_id"],
                        "round_no": round_no,
                        "issue": "invalid_identity",
                        "detail": str(exc),
                    }
                )
                continue
            sgid = split_group_id(source_namespace, room_id)
            try:
                data = official_round_data(
                    parsed, round_no, file_sha256=file_sha, json_pointer="#"
                )
            except ValueError as exc:
                history_issues.append(
                    {
                        "download_id": download["download_id"],
                        "round_no": round_no,
                        "issue": "unparseable_round",
                        "detail": str(exc),
                    }
                )
                continue
            events = []
            for event, pointer in zip(data["events"], data["event_pointers"]):
                enriched = dict(event)
                enriched["source_refs"] = [
                    {
                        "file": download["events_relative"],
                        "file_sha256": file_sha,
                        "json_pointer": pointer,
                        "room_id": room_id,
                        "batch": batch,
                    }
                ]
                events.append(enriched)
            ref = {
                "file": download["events_relative"],
                "file_sha256": file_sha,
                "json_pointer": "#",
                "room_id": room_id,
                "batch": batch,
            }
            official_refs_by_hand.setdefault(hid, []).append(ref)
            hand_accumulator.setdefault(
                hid,
                {
                    "replay_schema_version": REPLAY_SCHEMA_VERSION,
                    "hand_id": hid,
                    "split_group_id": sgid,
                    "origin": "official",
                    "parent_hand_id": None,
                    "coverage": data["coverage"],
                    "game_key": {
                        "source_namespace": source_namespace,
                        "tournament_id": room_id,
                        "game_id": game_id,
                    },
                    "round_no": round_no,
                    "rule_config": None,
                    "rules_hash": None,
                    "guide_version": guide_version,
                    "guide_captured_at": guide_captured_at,
                    "initial": data["initial"],
                    "events": events,
                    "scores_before": data["scores_before"],
                    "scores_after": data["scores_after"],
                    "score_delta": data["score_delta"],
                    "winner_seat": data["winner_seat"],
                    "is_draw": data["is_draw"],
                    "attempt_status": "unknown",
                    "result_confirmed": data["result_confirmed"],
                    "missing_fields": list(data["missing_fields"]),
                    "source_refs": [ref],
                },
            )
            hand = hand_accumulator[hid]
            if data["result_confirmed"]:
                hand["attempt_status"] = "valid"
            if data["coverage"] != "full_history":
                # 缺墙/缺摸牌身份是资料的缺失（hand.missing_fields），不改变
                # "已发生轨迹是否完整"的评级；轨迹不完整才报 history_not_full。
                history_issues.append(
                    {
                        "download_id": download["download_id"],
                        "round_no": round_no,
                        "issue": "history_not_full",
                        "coverage": data["coverage"],
                        "missing_fields": data["missing_fields"],
                    }
                )

    # 运行侧视角：从决策记录映射 run/participant/seat/attempt；身份字段
    # 随视图一并登记，供"只有运行证据、没有官方下载"的单局生成 index 行。
    views_by_hand: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    identity_by_hand: OrderedDict[str, dict[str, Any]] = OrderedDict()
    voided_attempts: set[tuple[str, str]] = set()
    for record in groups.get("lifecycle_changed", ()):
        payload = record.payload or {}
        if payload.get("event") == "stage_attempt_voided":
            context = record.context or {}
            run_id = context.get("run_id")
            attempt = payload.get("stage_attempt_id")
            if isinstance(run_id, str) and isinstance(attempt, str):
                voided_attempts.add((run_id, attempt))
    for record in groups.get("decision_input", ()):
        context = record.context or {}
        pid = context.get("participant_id")
        run_id = context.get("run_id")
        game_id = context.get("game_id")
        round_no = context.get("round_no")
        tournament_id = context.get("tournament_id")
        if not (
            isinstance(pid, str)
            and isinstance(run_id, str)
            and isinstance(game_id, str)
            and isinstance(tournament_id, str)
            and isinstance(round_no, int)
            and not isinstance(round_no, bool)
        ):
            continue
        try:
            hid = hand_id(source_namespace, tournament_id, game_id, round_no)
        except ValueError:
            continue
        identity_by_hand.setdefault(
            hid,
            {
                "tournament_id": tournament_id,
                "game_id": game_id,
                "round_no": round_no,
            },
        )
        seat = _view_for_decision_input(record)
        attempt = context.get("stage_attempt_id")
        view = {
            "run_id": run_id,
            "participant_id": pid,
            "seat": seat,
            "local_stage_attempt_id": (
                attempt if isinstance(attempt, str) else None
            ),
        }
        views = views_by_hand.setdefault(hid, [])
        if view not in views:
            views.append(view)

    # index 行：同一 hand_id 一行；attempt_status 优先作废证据，
    # 其次官方结束证据（valid），缺证据为 unknown。
    index_rows: list[dict[str, Any]] = []
    all_hands = sorted(
        set(list(hand_accumulator.keys()) + list(views_by_hand.keys()))
    )
    for hid in all_hands:
        views = views_by_hand.get(hid, [])
        official_refs = official_refs_by_hand.get(hid, [])
        hand = hand_accumulator.get(hid)
        identity = identity_by_hand.get(hid, {})
        attempt_status = "unknown"
        status_refs: list[dict[str, Any]] = []
        for view in views:
            run_id = view["run_id"]
            attempt = view["local_stage_attempt_id"]
            if attempt and (run_id, attempt) in voided_attempts:
                attempt_status = "void"
                status_refs.append(
                    {
                        "kind": "stage_attempt_voided",
                        "run_id": run_id,
                        "stage_attempt_id": attempt,
                    }
                )
        if attempt_status == "unknown" and hand is not None and hand["result_confirmed"]:
            attempt_status = "valid"
            for ref in official_refs:
                status_refs.append({"kind": "official_room_finished", **ref})
        index_rows.append(
            {
                "hand_id": hid,
                "source_namespace": source_namespace,
                "tournament_id": (
                    hand["game_key"]["tournament_id"]
                    if hand is not None
                    else identity.get("tournament_id")
                ),
                "game_id": (
                    hand["game_key"]["game_id"]
                    if hand is not None
                    else identity.get("game_id")
                ),
                "round_no": (
                    hand["round_no"] if hand is not None else identity.get("round_no")
                ),
                "views": views,
                "official_refs": official_refs,
                "attempt_status": attempt_status,
                "status_refs": status_refs,
                "split_group_id": (
                    hand["split_group_id"]
                    if hand is not None
                    else split_group_id(
                        source_namespace, identity.get("tournament_id")
                    )
                    if identity.get("tournament_id")
                    else None
                ),
            }
        )
    return [hand_accumulator[hid] for hid in all_hands if hid in hand_accumulator], index_rows, history_issues



# ---------------------------------------------------------------------------
# 数据集组装
# ---------------------------------------------------------------------------


def _manifest_document(
    *,
    dataset_id: str,
    created_at_unix_ms: int,
    source_namespace: str,
    producer_commit: str | None,
    dirty: bool | None,
    inputs: Sequence[Mapping[str, Any]],
    rules_hash: str | None,
    guide_version: int | None,
    guide_captured_at: str | None,
    config: Mapping[str, Any] | None,
    missing_fields: Sequence[str],
    bundle_id: str,
) -> dict[str, Any]:
    """派生 manifest 固定字段（契约 §4.2）；多值汇总字段为 null 并注明。"""

    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "replay_schema_version": REPLAY_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "created_at_unix_ms": created_at_unix_ms,
        "source_namespace": source_namespace,
        "producer_commit": producer_commit,
        "dirty": dirty,
        "inputs": [dict(item) for item in inputs],
        "rules_hash": rules_hash,
        "guide_version": guide_version,
        "guide_captured_at": guide_captured_at,
        "config": None if config is None else dict(config),
        "missing_fields": list(missing_fields),
        "bundle_id": bundle_id,
    }


def build_dataset(
    bundle_dir: str | Path,
    out_dataset_dir: str | Path,
    *,
    source_namespace: str,
    dataset_id: str | None = None,
    created_at_unix_ms: int | None = None,
    producer_commit: str | None = None,
    dirty: bool | None = None,
    rules_hash: str | None = None,
    guide_version: int | None = None,
    guide_captured_at: str | None = None,
    config: Mapping[str, Any] | None = None,
    missing_fields: Sequence[str] = (),
) -> dict[str, Any]:
    """从不可变 bundle 组装统一牌谱数据集；返回数据摘要报告。

    输入约束：bundle 必须已封存（清单校验通过）；运行侧旧记录缺
    DECISION_INPUT 的只进 excluded 列表；官方下载只提供 full_history
    上限，绝不生成 full_world（无完整牌墙时 from_replay 必须拒绝导入，
    行为向量 full-history-without-wall）。数据集目录已存在同名
    dataset_id 时拒绝覆盖（封存后不可变，重生成用新 ID）。
    """

    bundle = Path(bundle_dir)
    manifest_path = bundle / "bundle.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("缺少 bundle.json: {}".format(manifest_path))
    manifest = read_bundle_manifest(manifest_path)
    verification = verify_bundle(bundle, write_report=False)
    if not verification["ok"]:
        raise ValueError("bundle 清单校验失败，拒绝转换: {}".format(verification))

    out_dir = Path(out_dataset_dir)
    chosen_id = dataset_id if dataset_id is not None else uuid.uuid4().hex
    created_ms = (
        int(created_at_unix_ms) if created_at_unix_ms is not None else _unix_ms()
    )
    dataset_dir = out_dir / "derived" / chosen_id
    if dataset_dir.exists():
        raise FileExistsError("数据集目录已存在，封存后不可覆盖: {}".format(dataset_dir))

    read = read_records(bundle)
    reader_issues = [
        {"file": issue.relative_path, "line_no": issue.line_no, "issue": issue.issue}
        for issue in read.issues
    ]
    groups = _group_records_by_kind(read)
    decision_rows, excluded_decisions = build_decision_rows(
        groups, source_namespace=source_namespace
    )
    hand_rows, index_rows, history_issues = build_hand_rows_and_index(
        bundle,
        groups,
        source_namespace=source_namespace,
        guide_version=guide_version,
        guide_captured_at=guide_captured_at,
    )
    hand_ids_seen: set[str] = set()
    for row in hand_rows:
        if row["hand_id"] in hand_ids_seen:
            history_issues.append(
                {
                    "issue": "duplicate_hand_row",
                    "hand_id": row["hand_id"],
                    "detail": "同一 hand_id 出现多份官方单局行，保留首份并报告冲突",
                }
            )
        else:
            hand_ids_seen.add(row["hand_id"])

    file_integrity = {
        "status": "failed" if not verification["ok"] or reader_issues else "passed",
        "bundle_verification": {
            key: verification[key]
            for key in ("files_total", "files_ok", "mismatched", "missing", "extra", "ok")
        },
        "reader_issues": reader_issues,
    }
    decisions_without_end = [
        item for item in decision_rows if not item["decision_complete"] and item["request"]
    ]
    missing_decision_input = [
        item
        for item in excluded_decisions
        if item["reason"] == "missing_decision_input"
    ]
    decision_completeness = {
        "status": (
            "failed"
            if decisions_without_end or missing_decision_input
            else "passed"
        ),
        "decisions_total": len(decision_rows) + len(excluded_decisions),
        "complete_decisions": sum(
            1 for row in decision_rows if row["decision_complete"]
        ),
        "decisions_without_end": decisions_without_end,
        "excluded_decisions": excluded_decisions,
    }
    history_has_event_issues = any(
        "events:" in field for row in hand_rows for field in row["missing_fields"]
    )
    history_coverage = {
        "status": (
            "failed"
            if history_has_event_issues or history_issues
            else "passed" if hand_rows else "not_checked"
        ),
        "hands_total": len(hand_rows),
        "hands_full_history": sum(
            1 for row in hand_rows if row["coverage"] == "full_history"
        ),
        "issues": history_issues,
    }
    world_importability = {
        "status": "not_checked",
        "reason": (
            "官方下载无完整未来牌墙（wall=null），from_replay 必须拒绝世界导入；"
            "世界可导入性需模拟线 full_world 导出后另测"
        ),
        "hands_with_wall": sum(
            1 for row in hand_rows if row["initial"].get("wall") is not None
        ),
    }
    rule_consistency = {
        "status": "not_checked",
        "reason": "模拟线 replay-check 未交付；结构检查可 passed，规则一致性不做负标签",
    }
    validation: dict[str, Any] = {
        "file_integrity": file_integrity,
        "decision_completeness": decision_completeness,
        "history_coverage": history_coverage,
        "world_importability": world_importability,
        "rule_consistency": rule_consistency,
    }

    manifest_missing = sorted(set(missing_fields))
    if not hand_rows and not decision_rows:
        manifest_missing.append("no_hands_no_decisions")
    document = _manifest_document(
        dataset_id=chosen_id,
        created_at_unix_ms=created_ms,
        source_namespace=source_namespace,
        producer_commit=producer_commit,
        dirty=dirty,
        inputs=[
            {"path": entry.path, "sha256": entry.sha256} for entry in manifest.files
        ],
        rules_hash=rules_hash,
        guide_version=guide_version,
        guide_captured_at=guide_captured_at,
        config=config,
        missing_fields=manifest_missing,
        bundle_id=manifest.bundle_id,
    )
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(dataset_dir / "manifest.json", document)
    _atomic_write_text(
        dataset_dir / "index.jsonl",
        "".join(_jsonl_lines(index_rows)),
    )
    _atomic_write_text(
        dataset_dir / "decisions.jsonl",
        "".join(
            _jsonl_lines(
                sorted(
                    decision_rows,
                    key=lambda row: (row["hand_id"], row["participant_id"], row["decision_id"]),
                )
            )
        ),
    )
    _atomic_write_text(
        dataset_dir / "hands.jsonl",
        "".join(_jsonl_lines(sorted(hand_rows, key=lambda row: row["hand_id"]))),
    )
    _atomic_write_json(dataset_dir / "validation.json", validation)
    return {
        "dataset_dir": str(dataset_dir),
        "dataset_id": chosen_id,
        "hands_total": len(hand_rows),
        "decisions_total": len(decision_rows),
        "excluded_decisions": len(excluded_decisions),
        "index_rows": len(index_rows),
        "validation": validation,
    }


def _unix_ms() -> int:
    """生成节点的墙上时钟 Unix 毫秒（仅离线产物时间戳）。"""

    import time

    return int(time.time() * 1000)


__all__ = [
    "CONTRACT_ID",
    "END_REASON_VALUES",
    "MANIFEST_SCHEMA_VERSION",
    "REPLAY_SCHEMA_VERSION",
    "build_dataset",
    "build_decision_rows",
    "build_hand_rows_and_index",
    "hand_id",
    "load_hand_rows",
    "split_group_id",
]
