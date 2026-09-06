"""P0 观战器的只读审计投影。

本模块只处理已经由赛事进程写入磁盘的审计记录。它不会导入官方传输、
策略或应用运行时，也不会写入观战目录；因此观战器停止或解析失败不会改变
任何官方场次的动作、截止时间或网络请求。

P0 的牌桌以最近一份完整玩家观察（``DECISION_INPUT``）或权威快照为基线。
增量事件单独展示并标明其最高 ``seq``，而不凭不完整事件猜造完整牌桌。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


VIEW_SCHEMA_VERSION = 1
"""观战器 HTTP 输出格式版本；与审计信封版本独立演进。"""

_RAW_STATE_SOURCE = "state_response"
_MAX_EVENTS_PER_GAME = 40
_MAX_ISSUES_PER_RUN = 20


def _mapping(value: object) -> Mapping[str, Any] | None:
    """仅接受 JSON 对象；审计损坏或新增字段不能中断观战。"""

    return value if isinstance(value, Mapping) else None


def _int_or_none(value: object) -> int | None:
    """把非布尔整数保留为序号/墙钟值，其他形态视为未知。"""

    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str_or_none(value: object) -> str | None:
    """把非空字符串保留，避免把空或畸形身份显示成官方事实。"""

    return value if isinstance(value, str) and value else None


def _list(value: object) -> list[Any]:
    """把 JSON 数组安全转为列表；未知字段返回空数组。"""

    return list(value) if isinstance(value, list) else []


def discover_run_directories(watch_dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """从用户配置的观战目录自动发现新旧两种运行审计目录。

    ``watch_dirs`` 可直接是某个运行目录、通常的 ``audit_root``，或测试房间
    的父目录。支持当前 ``runs/{run_id}`` 布局和已归档测试房的
    ``bot-audit/{角色}/run-*`` 布局。只把内容是 ``run_manifest`` 审计信封的
    ``manifest.json`` 认作来源；不读取运行配置文件，从而不会接触 Token。
    """

    found: dict[str, Path] = {}
    for raw_root in watch_dirs:
        root = Path(raw_root).expanduser()
        try:
            resolved = root.resolve(strict=False)
        except OSError:
            continue
        if not resolved.is_dir():
            continue
        direct = resolved / "manifest.json"
        candidates = [direct] if direct.is_file() else sorted(resolved.rglob("manifest.json"))
        for manifest in candidates:
            run_dir = manifest.parent
            if not _is_audit_run_manifest(manifest):
                continue
            try:
                key = str(run_dir.resolve())
            except OSError:
                key = str(run_dir)
            found[key] = run_dir
    return tuple(sorted(found.values(), key=lambda item: str(item)))


def _is_audit_run_manifest(path: Path) -> bool:
    """只接受运行审计清单，排除 bundle、derived 与数据集的同名文件。"""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    envelope = _mapping(document)
    return envelope is not None and envelope.get("schema_version") == 1 and envelope.get("kind") == "run_manifest"


@dataclass
class _TailCursor:
    """一条活动 JSONL 文件的读取游标；offset 是字节偏移而非行号。"""

    inode: tuple[int, int] | None = None
    offset: int = 0
    trailing: bytes = b""  # 尚未写入换行符的最后半行，下一次再尝试解析


class _JsonlTail:
    """只增量读取普通 JSONL 文件，避免观战轮询反复扫描原始事件全量。"""

    def __init__(self) -> None:
        self._cursors: dict[Path, _TailCursor] = {}

    def read_new(self, path: Path) -> tuple[list[Mapping[str, Any]], list[str]]:
        """返回新写入的 JSON 对象和位置化读取问题。

        审计写线程每行都 ``flush``，但观察者仍把无换行尾部视为未完成；
        文件轮转、截断或 inode 改变时从头重读当前文件，绝不跨文件拼接半行。
        """

        try:
            stat = path.stat()
        except OSError as exc:
            return [], [f"{path.name}: 无法读取文件状态: {type(exc).__name__}"]
        identity = (stat.st_dev, stat.st_ino)
        cursor = self._cursors.setdefault(path, _TailCursor())
        if cursor.inode != identity or stat.st_size < cursor.offset:
            cursor.inode = identity
            cursor.offset = 0
            cursor.trailing = b""
        try:
            with path.open("rb") as handle:
                handle.seek(cursor.offset)
                fresh = handle.read()
        except OSError as exc:
            return [], [f"{path.name}: 读取失败: {type(exc).__name__}"]
        cursor.offset += len(fresh)
        if not fresh and not cursor.trailing:
            return [], []

        combined = cursor.trailing + fresh
        parts = combined.split(b"\n")
        cursor.trailing = parts.pop()  # 末尾无换行的一段延后到下次
        records: list[Mapping[str, Any]] = []
        issues: list[str] = []
        for line in parts:
            if not line.strip():
                continue
            try:
                decoded = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                issues.append(f"{path.name}: JSONL 行无法解析: {type(exc).__name__}")
                continue
            record = _mapping(decoded)
            if record is None:
                issues.append(f"{path.name}: JSONL 行不是对象")
                continue
            records.append(record)
        return records, issues


def _observation_from_snapshot(
    snapshot: Mapping[str, Any], *, game_id: str, authoritative_seq: int | None
) -> dict[str, Any]:
    """把官方原始快照裁成观战器所需的玩家观察形态。

    原始快照仍是官方按当前 Token 返回的单一玩家视角：仅保留其中本家手牌与
    已公开桌面，绝不合成他家暗手或未来牌墙。字段缺失以 ``None``/空数组展示。
    """

    god = _mapping(snapshot.get("god")) or {}
    return {
        "game_id": game_id,
        "seat": _int_or_none(snapshot.get("seat")),
        "round_no": _int_or_none(snapshot.get("round_no")),
        "snapshot_seq": authoritative_seq,
        "phase": _str_or_none(snapshot.get("phase")),
        "dealer_seat": _int_or_none(snapshot.get("dealer")),
        "turn_seat": _int_or_none(snapshot.get("turn")),
        "responding_seats": _list(snapshot.get("responding_seats")),
        "my_hand": _list(snapshot.get("my_hand")),
        "drawn_tile": snapshot.get("drawn_tile") if isinstance(snapshot.get("drawn_tile"), str) else None,
        "discards": _list(snapshot.get("discards")),
        "melds": _list(snapshot.get("melds")),
        "hand_counts": _list(snapshot.get("hand_counts")),
        "last_discard": snapshot.get("last_discard"),
        "remaining_tile_count": _int_or_none(snapshot.get("wall_remaining")),
        "scores": _list(snapshot.get("scores")),
        "rule_state": {
            "wealth_god": "白",  # 当前已确认规则；原快照不传该静态配置字段
            "baotou": god.get("baotou") if isinstance(god.get("baotou"), bool) else None,
            "chain_count": _int_or_none(god.get("chain_count")),
            "catch_play": god.get("catch_play") if isinstance(god.get("catch_play"), bool) else None,
        },
        "observation_issues": [],
    }


def _candidate_hint(candidate: Mapping[str, Any], facts: Mapping[str, Any] | None) -> dict[str, Any]:
    """裁剪规则候选为面向人的牌效提示；数值仍沿用规则模块原口径。"""

    action = _mapping(candidate.get("action")) or {}
    result: dict[str, Any] = {
        "rank": _int_or_none(candidate.get("rank")),
        "action_key": _str_or_none(candidate.get("action_key")),
        "action": dict(action),
        "reasons": _list(candidate.get("reasons")),
        "is_emergency": candidate.get("is_emergency") is True,
        "total_score": candidate.get("total_score"),
        "facts": None,
    }
    if facts is not None:
        result["facts"] = {
            "fact_kind": _str_or_none(facts.get("fact_kind")),
            "shanten_after": _int_or_none(facts.get("shanten_after")),
            "useful_tiles": _list(facts.get("useful_tiles")),
            "best_followup_discard": _str_or_none(facts.get("best_followup_discard")),
            "replacement_draw_unknown": facts.get("replacement_draw_unknown") is True,
            "completeness": _str_or_none(facts.get("completeness")),
            "note": _str_or_none(facts.get("note")),
        }
    return result


@dataclass
class _GameProjection:
    """一个官方场次的只读显示投影，所有时间均为审计墙钟 Unix 毫秒。"""

    game_id: str
    observation: dict[str, Any] | None = None
    observation_source: str | None = None
    observation_wall_time_unix_ms: int | None = None
    snapshot_seq: int | None = None
    latest_event_seq: int | None = None
    latest_event_wall_time_unix_ms: int | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    facts_by_action_key: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    latest_submission: dict[str, Any] | None = None
    final_scores: list[Any] | None = None
    finished: bool = False

    @property
    def is_active(self) -> bool:
        """判断该官方场次是否仍可用于实时观战。

        ``game_finished`` 是审计的终局事实；完整玩家观察也可能先于该记录到达
        ``phase=finished``。两者任一出现就不把场次混入实时选择器，避免历史审计
        与正在进行的牌局并列。
        """

        if self.finished:
            return False
        return self.observation is None or self.observation.get("phase") != "finished"

    def set_observation(
        self,
        observation: Mapping[str, Any],
        *,
        source: str,
        wall_time_unix_ms: int | None,
        overwrite_equal_seq: bool,
    ) -> None:
        """接纳更晚的完整观察；同序号时优先完整 ``DECISION_INPUT``。"""

        incoming_seq = _int_or_none(observation.get("snapshot_seq"))
        current_seq = self.snapshot_seq
        if (
            current_seq is not None
            and incoming_seq is not None
            and incoming_seq < current_seq
        ):
            return
        if incoming_seq == current_seq and not overwrite_equal_seq:
            return
        self.observation = dict(observation)
        self.observation_source = source
        self.observation_wall_time_unix_ms = wall_time_unix_ms
        self.snapshot_seq = incoming_seq

    def add_event(self, event: Mapping[str, Any], wall_time_unix_ms: int | None) -> None:
        """保存公开增量事件；未知事件也透传给界面，不据此推演完整牌桌。"""

        seq = _int_or_none(event.get("seq"))
        if seq is not None and self.latest_event_seq is not None and seq <= self.latest_event_seq:
            return
        display = {
            "seq": seq,
            "type": _str_or_none(event.get("type")),
            "seat": _int_or_none(event.get("seat")),
            "tile": event.get("tile") if isinstance(event.get("tile"), str) else None,
            "data": dict(_mapping(event.get("data")) or {}),
            "occurred_at_unix_sec": _int_or_none(event.get("ts")),
        }
        self.events.append(display)
        if len(self.events) > _MAX_EVENTS_PER_GAME:
            del self.events[:-_MAX_EVENTS_PER_GAME]
        if seq is not None:
            self.latest_event_seq = seq
        self.latest_event_wall_time_unix_ms = wall_time_unix_ms

    def as_json(self, now_unix_ms: int) -> dict[str, Any]:
        """输出单场显示模型，显式声明数据新鲜度与未投影事件。"""

        last_time = self.latest_event_wall_time_unix_ms or self.observation_wall_time_unix_ms
        age_ms = None if last_time is None else max(0, now_unix_ms - last_time)
        event_ahead = (
            self.latest_event_seq is not None
            and (self.snapshot_seq is None or self.latest_event_seq > self.snapshot_seq)
        )
        return {
            "game_id": self.game_id,
            "observation": self.observation,
            "observation_source": self.observation_source,
            "candidates": self.candidates,
            "events": list(reversed(self.events)),
            "latest_submission": self.latest_submission,
            "finished": self.finished,
            "final_scores": self.final_scores,
            "freshness": {
                "snapshot_seq": self.snapshot_seq,
                "latest_event_seq": self.latest_event_seq,
                "event_ahead_of_table_snapshot": event_ahead,
                "last_record_wall_time_unix_ms": last_time,
                "age_ms": age_ms,
                "message": (
                    "牌桌快照落后于已收到的增量事件；事件已列出，未用不完整事件重建牌桌"
                    if event_ahead
                    else "牌桌来自最近完整玩家观察或权威快照"
                ),
            },
        }


class _RunProjection:
    """一个运行目录的增量读取器与显示投影；不对目录做任何写入。"""

    def __init__(self, run_dir: Path, configured_root: Path) -> None:
        self.run_dir = run_dir
        self.configured_root = configured_root
        self.tail = _JsonlTail()
        self.manifest_signature: tuple[int, int] | None = None
        self.manifest_payload: dict[str, Any] = {}
        self.participant_id: str | None = None
        self.tournament_id: str | None = None
        self.games: dict[str, _GameProjection] = {}
        self.issues: list[str] = []
        self.updated_at_unix_ms: int | None = None

    @property
    def source_id(self) -> str:
        """稳定但不泄露本机绝对路径的来源标识。"""

        digest = hashlib.sha256(str(self.run_dir).encode("utf-8")).hexdigest()[:12]
        return "source-" + digest

    def _role_label(self) -> str:
        """优先显示测试房间角色目录，否则显示审计参赛身份或运行目录名。"""

        try:
            parts = self.run_dir.relative_to(self.configured_root).parts
        except ValueError:
            parts = ()
        for part in parts:
            if part.startswith("slot-"):
                return part
        # 已归档测试房使用 bot-audit/{xuanwu,baihu,...}/run-*，没有 slot-*。
        # 父目录名是人工配置的角色标签，优先级高于不可读的 participant_id。
        if self.run_dir.name.startswith("run-") and self.run_dir.parent.name != "runs":
            return self.run_dir.parent.name
        return self.participant_id or self.run_dir.name

    def _note(self, issue: str) -> None:
        self.issues.append(issue)
        if len(self.issues) > _MAX_ISSUES_PER_RUN:
            del self.issues[:-_MAX_ISSUES_PER_RUN]

    def _load_manifest(self) -> None:
        path = self.run_dir / "manifest.json"
        try:
            stat = path.stat()
        except OSError:
            return
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature == self.manifest_signature:
            return
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # 覆盖写 manifest 时可能恰好读到中间态；不记签名，下次继续尝试。
            self._note("manifest.json 正在写入或无法解析，下一次刷新会重试")
            return
        envelope = _mapping(document)
        payload = _mapping(envelope.get("payload")) if envelope else None
        context = _mapping(envelope.get("context")) if envelope else None
        if payload is None:
            self._note("manifest.json 不是有效审计信封")
            return
        self.manifest_signature = signature
        self.manifest_payload = dict(payload)
        if context:
            self.participant_id = _str_or_none(context.get("participant_id")) or self.participant_id
            self.tournament_id = _str_or_none(context.get("tournament_id")) or self.tournament_id
        self.participant_id = _str_or_none(payload.get("participant_id")) or self.participant_id

    def _game(self, game_id: str) -> _GameProjection:
        return self.games.setdefault(game_id, _GameProjection(game_id=game_id))

    def _apply_raw_state(
        self, game: _GameProjection, payload: Mapping[str, Any], wall_time_unix_ms: int | None
    ) -> None:
        if payload.get("source") != _RAW_STATE_SOURCE:
            return
        raw = payload.get("raw")
        if not isinstance(raw, str) or not raw:
            return
        try:
            response = _mapping(json.loads(raw))
        except json.JSONDecodeError:
            self._note(f"{game.game_id}: state_response 原文无法解析")
            return
        if response is None:
            self._note(f"{game.game_id}: state_response 原文不是对象")
            return
        seq = _int_or_none(response.get("seq"))
        snapshot = _mapping(response.get("snapshot"))
        if snapshot is not None:
            game.set_observation(
                _observation_from_snapshot(snapshot, game_id=game.game_id, authoritative_seq=seq),
                source="权威快照",
                wall_time_unix_ms=wall_time_unix_ms,
                overwrite_equal_seq=False,
            )
        for event in _list(response.get("events")):
            parsed = _mapping(event)
            if parsed is not None:
                game.add_event(parsed, wall_time_unix_ms)

    def _apply(self, record: Mapping[str, Any]) -> None:
        if record.get("schema_version") != 1:
            return
        kind = _str_or_none(record.get("kind"))
        context = _mapping(record.get("context")) or {}
        payload = _mapping(record.get("payload")) or {}
        wall_time = _int_or_none(record.get("wall_time_unix_ms"))
        participant = _str_or_none(context.get("participant_id"))
        tournament = _str_or_none(context.get("tournament_id"))
        self.participant_id = participant or self.participant_id
        self.tournament_id = tournament or self.tournament_id
        if wall_time is not None:
            self.updated_at_unix_ms = max(self.updated_at_unix_ms or wall_time, wall_time)

        game_id = _str_or_none(context.get("game_id"))
        if kind == "run_manifest":
            self.manifest_payload = dict(payload)
            self.participant_id = _str_or_none(payload.get("participant_id")) or self.participant_id
            return
        if not game_id:
            return
        game = self._game(game_id)
        if kind == "decision_input":
            request = _mapping(payload.get("request")) or {}
            observation = _mapping(request.get("observation"))
            if observation is not None:
                game.set_observation(
                    observation,
                    source="决策输入",
                    wall_time_unix_ms=wall_time,
                    overwrite_equal_seq=True,
                )
            rules = _mapping(request.get("rules")) or {}
            for candidate in _list(rules.get("legal_candidates")):
                parsed = _mapping(candidate)
                if parsed is None:
                    continue
                key = _str_or_none(parsed.get("action_key"))
                facts = _mapping(parsed.get("facts"))
                if key and facts is not None:
                    game.facts_by_action_key[key] = facts
            return
        if kind == "decision_planned":
            effective = _list(payload.get("effective_candidates"))
            candidates = effective or _list(payload.get("candidates"))
            view: list[dict[str, Any]] = []
            for item in candidates:
                candidate = _mapping(item)
                if candidate is None:
                    continue
                key = _str_or_none(candidate.get("action_key"))
                view.append(_candidate_hint(candidate, game.facts_by_action_key.get(key or "")))
            game.candidates = sorted(
                view,
                key=lambda item: item["rank"] if isinstance(item["rank"], int) else 1_000_000,
            )
            return
        if kind == "raw_protocol_state":
            self._apply_raw_state(game, payload, wall_time)
            return
        if kind == "submission_outcome":
            game.latest_submission = {
                "action_key": _str_or_none(payload.get("action_key")),
                "outcome": _str_or_none(payload.get("outcome"))
                or _str_or_none(payload.get("outcome_type")),
                "official_code": _str_or_none(payload.get("official_code")),
                "wall_time_unix_ms": wall_time,
            }
            return
        if kind == "game_finished":
            scores = _list(payload.get("final_scores"))
            game.final_scores = scores or game.final_scores
            game.finished = True

    def refresh(self) -> None:
        """读取 manifest 和所有新增审计行；只读取文件末尾的新字节。"""

        self._load_manifest()
        try:
            paths = sorted(path for path in self.run_dir.rglob("*.jsonl") if path.is_file())
        except OSError as exc:
            self._note(f"扫描审计目录失败: {type(exc).__name__}")
            return
        for path in paths:
            records, issues = self.tail.read_new(path)
            for issue in issues:
                self._note(issue)
            for record in records:
                self._apply(record)

    def as_json(self, now_unix_ms: int, *, active_games_only: bool = False) -> dict[str, Any]:
        """输出一个可供前端选择的 Token 身份来源。

        P0 只服务实时观战时，调用方传入 ``active_games_only=True``。历史牌局
        仍保留在内存投影中以便持续尾随同一运行目录，但不会随每次轮询传给浏览器。
        """

        mode = _str_or_none(self.manifest_payload.get("mode"))
        return {
            "source_id": self.source_id,
            "role": self._role_label(),
            "participant_id": self.participant_id,
            "run_id": self.run_dir.name,
            "mode": mode,
            "tournament_id": self.tournament_id,
            "updated_at_unix_ms": self.updated_at_unix_ms,
            "issues": list(self.issues),
            "games": [
                game.as_json(now_unix_ms)
                for _game_id, game in sorted(self.games.items())
                if not active_games_only or game.is_active
            ],
        }


class SpectatorRepository:
    """P0 的公开读取入口：观战目录自动发现、增量尾随和显示模型输出。

    线程安全仅服务于本地 HTTP 处理线程。所有文件操作都是读操作，且无论
    审计目录不存在、正在写入或含未知记录，均返回带问题提示的快照而不抛出。
    """

    def __init__(self, watch_dirs: Iterable[str | Path]) -> None:
        configured: list[Path] = []
        for item in watch_dirs:
            root = Path(item).expanduser()
            try:
                # 与目录发现使用同一规范形式，保证 slot-* 可从相对路径识别。
                root = root.resolve(strict=False)
            except OSError:
                pass
            configured.append(root)
        if not configured:
            raise ValueError("至少提供一个观战目录")
        self._configured = tuple(configured)
        self._runs: dict[Path, _RunProjection] = {}
        self._lock = threading.RLock()

    def refresh(self) -> None:
        """发现新增运行目录并增量读取所有已发现来源。"""

        with self._lock:
            discovered: dict[Path, Path] = {}
            for configured in self._configured:
                for run_dir in discover_run_directories((configured,)):
                    discovered[run_dir] = configured
            for run_dir, configured in discovered.items():
                projection = self._runs.get(run_dir)
                if projection is None:
                    projection = _RunProjection(run_dir, configured)
                    self._runs[run_dir] = projection
                projection.refresh()

    def snapshot(self) -> dict[str, Any]:
        """返回当前可显示事实；时间字段为 Unix 毫秒墙钟。"""

        self.refresh()
        now_unix_ms = int(time.time() * 1000)
        with self._lock:
            # P0 尚未提供历史牌谱或赛后回放，因而 API 只暴露实时场次。这样既使
            # 选择器保持简洁，也不会在浏览器轮询中重复传输完整历史牌局。
            sources = [
                source
                for projection in self._runs.values()
                if (source := projection.as_json(now_unix_ms, active_games_only=True))["games"]
            ]
        sources.sort(
            key=lambda item: (
                item.get("role") or "",
                item.get("participant_id") or "",
                item.get("run_id") or "",
            )
        )
        return {
            "schema_version": VIEW_SCHEMA_VERSION,
            "generated_at_unix_ms": now_unix_ms,
            "visibility": "single_player_observation",
            "sources": sources,
        }
