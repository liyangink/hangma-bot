"""T199专用自由赛控制入口：固定共享锁、单房意图、自然终态及房界回退。

inspect只导入/核字节，不读Token或连接官方；watch/worker是真实运行能力，
本轮研发不调用它们。当前动作窗口仍完全由既有生产入口和规则保底处理。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter
import fcntl
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from types import FunctionType

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_gate as gate
import phase_rejection

ENTRY_RELATIVE = 'tools/offline/free_match/runtime/controller.py'
OWNER_FD_ENV = "HM_T199_OWNER_FD"
ADOPT_STATE_ENV = "HM_T199_ADOPT_STATE"
ROLLBACK_ACTIVATION_ENV = "HM_T199_ROLLBACK_ACTIVATION"


def write_state(path: Path, value: dict) -> None:
    """状态原子替换并fsync；配置不保存Token，Unix秒只用于关联。"""
    temporary = path.with_name(path.name + ".%d.tmp" % os.getpid())
    with temporary.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def block_next_room(state_dir: Path, reason: dict, *, stop_background=False) -> None:
    """本候选的后台补证与控制器共用更新锁，故障只挡下房，不向玩家发信号。"""
    with (state_dir / "control-update.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        control_path = state_dir / "control.json"
        control = gate.read_json(control_path)
        value = {**control, "continue_after_cycle": False, "candidate_blocked": True,
                 "reason": reason, "at_unix": time.time()}
        if stop_background:
            value["background_enabled"] = False
        write_state(control_path, value)


def protocol_events(body: dict) -> list:
    """官方events缺省/null均为无事件；非列表及非对象成员拒绝，不能静默吞坏报文。"""
    if not isinstance(body, dict):
        raise gate.GateError("官方状态／SSE原文不是对象")
    events = body.get("events")
    if events is None:
        return []
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise gate.GateError("官方events不是对象列表")
    for event in events:
        if (type(event.get("seq")) is not int or event["seq"] < 0 or not isinstance(event.get("type"), str)
                or (event.get("data") is not None and not isinstance(event["data"], dict))):
            raise gate.GateError("官方事件seq/type/data结构不合法")
    return events


def load_tools(root: Path, shared_owner: Path, shared_postprocess: Path, state_dir: Path, credential_path=None):
    """导入指定真实根的可信工具；只借verify/统计，不调用旧watch/worker。"""
    sys.path[:0] = [str(root / "src"), str(root)]
    spec = importlib.util.spec_from_file_location("t199_frozen_free_tools", root / gate.FREE_DRIVER)
    tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools)
    if tools.ROOT.resolve() != root.resolve() or tools.h.ROOT.resolve() != root.resolve():
        raise gate.GateError("可信工具ROOT未指向冻结根")
    tools.OWNER_LOCK, tools.POSTPROCESS_LOCK = shared_owner, shared_postprocess
    tools.PRIVATE, tools.CONTROL = state_dir, state_dir / "control.json"
    # h.PRIVATE还决定其锁/私有文件语义，不能留成新ROOT/.private/t165派生值。
    tools.h.PRIVATE = shared_owner.parent
    tools.n.PRIVATE = shared_owner.parent
    if credential_path is not None:
        tools.h.TOKEN = Path(credential_path)  # 仅保存授权文件位置，本工具不读取内容。
    return tools


def scan_lightweight(run: Path, *, max_bytes: int, max_seconds: float,
                     phase_index_max_bytes: int = 1073741824, phase_index_max_seconds: float = 5.0) -> dict:
    """有界扫描审计事件/原协议，跳过大decision_input；不评分或重算条件图。

    官方timeout按本家座位去重；409未刷新必须有随后完整快照才算恢复。
    读不完、原件缺失或无法证座位时保持未知，不伪造0。
    """
    counts = Counter()
    sources = Counter()
    failures, snapshots, seats, timeout_events = {}, {}, {}, {}
    phase_rejections, phase_snapshots, applied_states = [], [], []
    raw_posts = []
    started, bytes_read, incomplete = time.monotonic(), 0, False

    def learn_seat(gid, snapshot):
        if not isinstance(gid, str) or not gid:
            raise gate.GateError("state/SSE快照缺实际game_id")
        if snapshot.get("game_id") is not None and snapshot["game_id"] != gid:
            raise gate.GateError("快照与审计game_id不符")
        seat = snapshot.get("seat")
        if seat is None or seat == -1:
            return
        if type(seat) is not int or not 0 <= seat < 4:
            raise gate.GateError("本家快照seat不是0—3")
        if gid in seats and seats[gid] != seat:
            raise gate.GateError("同game_id本家seat变化，不能覆盖旧归因")
        seats[gid] = seat

    def remember_events(events, gid, source):
        if events and (not isinstance(gid, str) or not gid):
            raise gate.GateError("官方事件缺实际game_id")
        for event in events:
            counts[source + "_events_loaded"] += 1
            data = event.get("data") or {}
            if event["type"] == "timeout" and data.get("kind") == "discard":
                if type(event.get("seat")) is not int or not 0 <= event["seat"] < 4:
                    raise gate.GateError("官方discard timeout缺有效seat")
                key = gid, event["seq"]
                if key in timeout_events and timeout_events[key] != event:
                    raise gate.GateError("SSE/state timeout同序号内容冲突")
                timeout_events[key] = event
    # 决策输入/整图评分单独存decisions.jsonl；首房不扫描它们。
    # submission非法性取已脱敏官方action原响应，恢复事实取games流。
    files = sorted({*run.glob("lifecycle.jsonl"), *run.glob("participants/*/games/*.jsonl"),
                    *run.glob("participants/*/raw/*.jsonl"), *run.glob("participants/*/raw/*.jsonl.gz"),
                    *run.glob("raw/*.jsonl"), *run.glob("raw/*.jsonl.gz")})
    if not files:
        return {key: None for key in ("real_new_missed_actions", "illegal_submissions", "unrecovered_state")}
    for path in files:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as stream:
            while True:
                prefix = stream.readline(2048)
                if not prefix:
                    break
                bytes_read += len(prefix)
                heavy = re.search(br'"kind"\s*:\s*"(decision_input|decision_planned)"', prefix)
                chunks = [prefix] if not heavy else []
                while not prefix.endswith(b"\n"):
                    prefix = stream.readline(65536)
                    bytes_read += len(prefix)
                    if not prefix:
                        break
                    if not heavy:
                        chunks.append(prefix)
                    if bytes_read > max_bytes or time.monotonic() - started > max_seconds:
                        incomplete = True
                        break
                if heavy:
                    counts[heavy.group(1).decode()] += 1
                elif not incomplete:
                    row = json.loads(b"".join(chunks))
                    kind, payload, context = row["kind"], row.get("payload", {}), row.get("context", {})
                    gid, stamp = context.get("game_id"), row.get("monotonic_ns", 0)
                    counts[kind] += 1
                    if kind == "authoritative_state":
                        consumed = payload.get("consumed_seq", payload.get("seq"))
                        if type(consumed) is int:
                            applied_states.append((gid, consumed, stamp))
                    if kind == "protocol_recovered" and payload.get("trigger") in (
                            "conflict_refresh_unavailable", "conflict_refresh_cancelled"):
                        failures[gid] = max(stamp, failures.get(gid, -1))
                    if kind == "submission_outcome":
                        outcome = payload.get("outcome_type")
                        if outcome == "SubmitRejectedNoRefresh":
                            failures[gid] = max(stamp, failures.get(gid, -1))
                        if outcome in ("SubmitRejectedRetryable", "SubmitRejectedClosed"):
                            counts["explicit_rejection"] += 1
                            if payload.get("official_code") in ("INVALID_ACTION", "NOT_QUALIFIED"):
                                counts["illegal_submissions"] += 1
                    if kind == "raw_protocol_state" and payload.get("source") == "state_response":
                        sources["state_response"] += 1
                        if payload.get("http_status") == 429:
                            counts["state_429"] += 1
                        if payload.get("http_status") == 200:
                            body = json.loads(payload["raw"])
                            if isinstance(body.get("snapshot"), dict):
                                phase_snapshots.append({"gid": gid, "stamp": stamp, "seq_requested": payload.get("seq_requested"), "body": body})
                            events = protocol_events(body)
                            snapshot = body.get("snapshot")
                            if snapshot is not None and not isinstance(snapshot, dict):
                                raise gate.GateError("state snapshot不是对象")
                            if body.get("gap") is True:
                                failures[gid] = max(stamp, failures.get(gid, -1))
                            elif isinstance(snapshot, dict) and payload.get("seq_requested") == 0:
                                snapshots[gid] = max(stamp, snapshots.get(gid, -1))
                            if isinstance(snapshot, dict):
                                learn_seat(gid, snapshot)
                            remember_events(events, gid, "state")
                    if kind == "raw_protocol_state" and payload.get("source") == "sse_frame":
                        sources["sse_frame"] += 1
                        body = json.loads(payload["raw"])
                        events = protocol_events(body)
                        remember_events(events, gid, "sse")
                        snapshot = body.get("snapshot")
                        if snapshot is not None and not isinstance(snapshot, dict):
                            raise gate.GateError("SSE snapshot不是对象")
                        if isinstance(snapshot, dict):
                            learn_seat(gid, snapshot)
                    if kind == "raw_protocol_state" and payload.get("source") == "action_submit_response":
                        sources["action_submit_response"] += 1
                        raw_posts.append(row)
                        if phase_rejection.exact_message(payload):
                            phase_rejections.append(row)
                        if payload.get("http_status") == 429:
                            counts["action_429"] += 1
                        if payload.get("http_status") == 409:
                            counts["explicit_rejection"] += 1
                            body = json.loads(payload["raw"])
                            error = body.get("error")
                            code = body.get("code") or (error.get("code") if isinstance(error, dict) else None)
                            if code in ("INVALID_ACTION", "NOT_QUALIFIED"):
                                counts["illegal_submissions"] += 1
                            elif code is None:
                                counts["rejection_code_unknown"] += 1
                if bytes_read > max_bytes or time.monotonic() - started > max_seconds:
                    incomplete = True
                if incomplete:
                    break
        if incomplete:
            break
    raw_scan_elapsed = time.monotonic() - started
    phase_proofs = []
    applied_index = {}
    applied_times = {}
    for gid, seq, stamp in applied_states:
        applied_index[(gid, seq)] = max(stamp, applied_index.get((gid, seq), -1))
        applied_times.setdefault((gid, seq), []).append(stamp)
    for item in phase_snapshots:
        applied_stamp = applied_index.get((item["gid"], item["body"].get("seq")), -1)
        item["applied"] = applied_stamp >= item["stamp"]
        # 同seq后续可能再次记账；证明“输入前已应用”必须取该raw快照之后最早的应用。
        item["applied_at_monotonic_ns"] = min((stamp for stamp in
            applied_times.get((item["gid"], item["body"].get("seq")), []) if stamp >= item["stamp"]), default=-1)
    # 只纳入每个精确Pass409之后首个已应用的同场/同单局本人摸牌窗口。
    # 其输入和提交证据来自本次decisions流，不依赖后台下载的赛后events。
    recovery_windows = set()
    for rejected in phase_rejections:
        if phase_rejection.rejection_family(rejected["payload"]) != "only_pass": continue
        context = rejected.get("context", {})
        for item in sorted(phase_snapshots, key=lambda item: item["stamp"]):
            body = item["body"]; snap = body.get("snapshot", {})
            if (item["gid"] == context.get("game_id") and item["stamp"] > rejected["monotonic_ns"]
                    and item["seq_requested"] == 0 and body.get("gap") is False and item["applied"]
                    and type(body.get("seq")) is int and type(context.get("trigger_seq")) is int
                    and body["seq"] > context["trigger_seq"] and snap.get("phase") == "draw"
                    and snap.get("round_no") == context.get("round_no")
                    and type(snap.get("seat")) is int and 0 <= snap["seat"] < 4
                    and snap.get("turn") == snap["seat"]):
                recovery_windows.add((item["gid"], snap["round_no"], body["seq"], "draw", snap["seat"]))
                break
    # 原raw/games扫描仍守256MiB/3秒；仅两条精确相位原文触发独立compact证明扫描。
    compact, phase_index, adapter_counts, adapter_attempts = phase_rejection.collect(run,
        {row["context"]["decision_id"] for row in phase_rejections if isinstance(row["context"].get("decision_id"), str)},
        max_bytes=phase_index_max_bytes, max_seconds=phase_index_max_seconds,
        recovery_windows=recovery_windows)
    # 原POST缺五元窗，必须经同game/DID/attempt的唯一可信body意图关联；不能按DID单独放过同窗重复。
    post_counts, post_mapping = ({}, {"complete": True, "unknown": None, "triggered": False})
    if phase_rejections and not incomplete and phase_index["complete"]:
        post_counts, post_mapping = phase_rejection.associate_posts(raw_posts, adapter_attempts)
        post_mapping["triggered"] = True
    if not incomplete and phase_index["complete"] and post_mapping["complete"]:
        proof_records = [record for records in compact.values() for record in records]
        for rejected in phase_rejections:
            proof = phase_rejection.prove(rejected, proof_records, phase_snapshots, post_counts, adapter_counts)
            if proof is not None:
                phase_proofs.append(proof)
        # 只扣本次raw官方拒绝对应一项；NoRefresh事实仍原样、其他INVALID_ACTION/NOT_QUALIFIED保持硬门。
        counts["illegal_submissions"] -= len(phase_proofs)
        if counts["illegal_submissions"] < 0:
            raise gate.GateError("phase重分类数超过原非法计数")
    unknown_seat = any(gid not in seats for gid, _ in timeout_events)
    missing_raw = counts["raw_protocol_state"] == 0
    return {"real_new_missed_actions": None if incomplete or unknown_seat or missing_raw else sum(
                event.get("seat") == seats[gid] for (gid, _), event in timeout_events.items()),
            "illegal_submissions": None if incomplete or counts["rejection_code_unknown"] else counts["illegal_submissions"],
            "unrecovered_state": None if incomplete or missing_raw else sum(snapshots.get(gid, -1) <= stamp for gid, stamp in failures.items()),
            "warnings": {"observed_429": counts["state_429"] + counts["action_429"], "explicit_rejection": counts["explicit_rejection"],
                         "recovered_expired_peng_window": sum(p["classification"] == "recovered_expired_peng_window" for p in phase_proofs),
                         "recovered_expired_chi_window": sum(p["classification"] == "recovered_expired_chi_window" for p in phase_proofs),
                         "recovered_expired_only_pass_window": sum(p["classification"] == "recovered_expired_only_pass_window" for p in phase_proofs),
                         "recovered_server_closed_response_pass": sum(p["classification"] == "recovered_server_closed_response_pass" for p in phase_proofs),
                         "recovered_server_closed_only_pass": sum(p["classification"] == "recovered_server_closed_only_pass" for p in phase_proofs),
                         "possible_lost_chi": sum(p["classification"] == "recovered_server_closed_response_pass" for p in phase_proofs),
                         "clock_unknown": sum(p["classification"] in ("recovered_server_closed_response_pass", "recovered_server_closed_only_pass") for p in phase_proofs),
                         "closure_reason_unknown": sum(p["classification"] in ("recovered_server_closed_response_pass", "recovered_server_closed_only_pass") for p in phase_proofs),
                         "lost_response_opportunity": sum(p["classification"] in ("recovered_expired_peng_window", "recovered_expired_chi_window") for p in phase_proofs),
                         "phase_index_unknown": phase_index.get("unknown") or post_mapping.get("unknown"),
                         "decision_input_records": counts["decision_input"], "decision_planned_records": counts["decision_planned"]},
            "scan_bytes": bytes_read, "scan_elapsed_monotonic_seconds": raw_scan_elapsed,
            "phase_index_scan": phase_index, "phase_post_mapping": post_mapping,
            "phase_reclassification_proofs": phase_proofs,
            "combined_scan_elapsed_monotonic_seconds": time.monotonic() - started,
            "scan_complete": not incomplete, "raw_source_counts": dict(sources),
            "state_events_loaded": counts["state_events_loaded"], "sse_events_loaded": counts["sse_events_loaded"],
            "discard_timeout_events_deduplicated": len(timeout_events),
            "own_seats_by_game": seats}


class Controller:
    """本轮具体发布物的单Token控制器，不修改活跃main或旧控制器。"""

    def __init__(self, spec_path: Path, *, launcher=None, tools=None, process_observer=None):
        """launcher/observer只用于本地人工会话验证；生产默认真实Popen与既有核进程工具。"""
        if not __debug__:
            raise gate.GateError("可信旧终态验证依赖assert，禁止优化模式启动")
        self.spec_path = spec_path.resolve()
        self.spec = gate.read_json(self.spec_path)
        layout = gate.inspect_layout(self.spec)
        self.ROOT = Path(layout["release_root"])
        self.OWNER_LOCK = Path(layout["owner_lock"])
        self.POSTPROCESS_LOCK = Path(layout["postprocess_lock"])
        self.WORKER_LOCK = Path(layout["worker_lock"])
        self.STATE = Path(layout["state_dir"])
        self.CONTROL = self.STATE / "control.json"
        self.launcher = launcher or subprocess.Popen
        self.tools = tools or load_tools(self.ROOT, self.OWNER_LOCK, self.POSTPROCESS_LOCK, self.STATE,
                                        self.spec.get("credential_path"))
        self.observe = process_observer or self.tools.h.process_identity
        self.stop_after_room = False

    def inspect(self) -> dict:
        """实际字段／导入来源与字节预检；不核玩家、不读取凭据、不联网。"""
        result = gate.preflight(self.spec)
        result.update({"runtime_launch_implemented": True, "actual_locks": {
            "OWNER_LOCK": str(self.OWNER_LOCK), "POSTPROCESS_LOCK": str(self.POSTPROCESS_LOCK),
            "WORKER_SINGLETON": str(self.WORKER_LOCK), "helper_PRIVATE": str(self.tools.h.PRIVATE)},
            "actual_helper_fields": {"OWNER_LOCK": str(self.tools.OWNER_LOCK),
                "POSTPROCESS_LOCK": str(self.tools.POSTPROCESS_LOCK)},
            "actual_roots": {"controller": str(self.ROOT), "legacy_helper": str(self.tools.h.ROOT),
                             "postprocess_spawn": str(self.tools.n.ROOT)},
            "actual_other_players_source": self.tools.h.other_players.__code__.co_filename,
            "player_entry": str(self.ROOT / "scripts/run_auto_match.py"),
            "player_cwd": str(self.ROOT), "player_pythonpath": self.player_environment()["PYTHONPATH"],
            "watch_called": False, "token_reads": 0})
        return result

    def check_admission(self) -> dict:
        """每房前核实际四包及适用离线门；P0不要求战胜错误旧世界。"""
        check = gate.preflight(self.spec)
        if Path(__file__).resolve() != self.ROOT / ENTRY_RELATIVE or not Path(gate.__file__).resolve().is_relative_to(self.ROOT):
            raise gate.GateError("真实控制入口和门工具必须来自同一冻结运行根")
        if any(relative not in self.spec["files"] for relative in (ENTRY_RELATIVE,
                str(Path(ENTRY_RELATIVE).parent / "release_gate.py"))):
            raise gate.GateError("完整冻结清单缺控制入口／门工具")
        qualification = self.spec.get("qualification", {})
        required = ["rules_passed", "runtime_passed", "corrected_fallback_passed"]
        kind = qualification.get("release_kind")
        required += ["full_table_impact_passed"] if kind == "P0" else ["strength_confirmation_passed"]
        if kind not in ("P0", "S") or any(qualification.get(k) is not True for k in required):
            raise gate.GateError("发布物离线资格未闭合")
        # 每项准入事实必须绑定真实小型结果文件；状态布尔值本身不授发布。
        for key in required:
            receipt = qualification.get("receipts", {}).get(key)
            if not receipt or gate.pin(Path(receipt["path"])) != receipt["pin"]:
                raise gate.GateError("适用门收据缺失或漂移：" + key)
        import hangma_bot.bootstrap as bootstrap
        if bootstrap._REPO_ROOT.resolve() != self.ROOT:
            raise gate.GateError("组合根已缓存其他运行根，必须用新解释器")
        for mode, relative in self.spec["mode_manifests"].items():
            recorded = gate.read_json(gate.relative_file(self.ROOT, relative))
            assembled = bootstrap._load_vip_manifest(recorded["strategy"], recorded["release_package_id"])
            if assembled["allowed_modes"] != [mode]:
                raise gate.GateError("真实四包装配作用域不符")
        package = bootstrap._load_vip_manifest(self.spec["identity"]["free_strategy"],
                                               self.spec["identity"]["package_ids"]["free"])
        actual = {"free_strategy": package["strategy"], "package_ids": {"free": package["release_package_id"]},
                  "rules_source_hash": bootstrap.compute_rules_hash(self.ROOT),
                  "hand_math": bootstrap.hand_math_runtime_metadata()}
        if package["allowed_modes"] != ["auto_match"] or actual != self.spec["identity"]:
            raise gate.GateError("实际策略／规则／自由赛包身份不符")
        if not self.spec.get("credential_path") or Path(self.spec["credential_path"]).resolve().is_relative_to(self.ROOT):
            raise gate.GateError("缺根外授权凭据路径")
        return check

    def player_environment(self) -> dict:
        """每次spawn显式指向当前冻结根；移除owner环境避免后台误继承。"""
        environment = self.tools.h.env()
        environment["PYTHONPATH"] = os.pathsep.join((str(self.ROOT / "src"), str(self.ROOT)))
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment.pop(OWNER_FD_ENV, None)
        environment.pop(ADOPT_STATE_ENV, None)
        environment.pop(ROLLBACK_ACTIVATION_ENV, None)
        return environment

    def publish(self, **value) -> None:
        """根外状态写真实PID与候选接续状态，不改旧watchdog的false标志。"""
        write_state(self.STATE / "STATUS.json", {"controller_pid": os.getpid(), "updated_at_unix": time.time(),
            "release_root": str(self.ROOT), "spec_sha256": gate.digest(self.spec), **value})

    def status(self) -> dict:
        """只读本版本真实命令身份；当前房PID与控制器／后台分开，不读Token。"""
        value = gate.read_json(self.STATE / "STATUS.json")
        value["controller_process_now"] = self.observe(value.get("controller_pid"), str(self.ROOT / ENTRY_RELATIVE) + " watch")
        value["active_children_now"] = {key: self.observe(pid, str(self.ROOT / "scripts/run_auto_match.py"))
            for key, pid in value.get("active_children", {}).items()}
        value["control"] = gate.read_json(self.CONTROL)
        return value

    def prepare_room(self, number: int) -> tuple[Path, dict]:
        """单房使用全新数据目录与配置；不发送匹配请求，凭据仅由玩家子进程注入。"""
        directory = self.STATE / ("batch-%03d" % number)
        session = directory / "session"
        config = gate.read_json(gate.relative_file(self.ROOT, self.spec["free_config"]))
        if "token" in config:
            raise gate.GateError("运行模板不能含Token原文")
        config.pop("token_env", None)
        if config.get("expected_tournament_id") is not None or config.get("strategy") != self.spec["identity"]["free_strategy"]:
            raise gate.GateError("自由赛配置作用域／策略不符")
        if (config.get("mode") != "auto_match" or config.get("sse_enabled") is not True
                or config.get("token_kind") != "official"
                or config.get("expected_policy_release_id") != self.spec["identity"]["package_ids"]["free"]
                or config.get("auto_match", {}).get("declared_max_games") != 10
                or config.get("auto_match", {}).get("declared_rounds") != 8):
            raise gate.GateError("自由赛包绑定或本轮M10/R8接线不符")
        directory.mkdir()
        config["audit_root"] = str(session / "audit")
        config["discard_pacing_enabled"] = False
        private_config = directory / "free.json"
        write_state(private_config, config)
        plan = {"batch": number, "identity": self.spec["identity"], "free_session": str(session),
                "release_root": str(self.ROOT), "runtime_spec_path": str(self.spec_path),
                "config_path": str(private_config), "spec_sha256": gate.digest(self.spec)}
        gate.save_exclusive(directory / "PLAN.json", plan)
        return directory, plan

    def run_room(self, number: int, owner_fd: int) -> dict:
        """持久意图先落盘，恰好启动一次；只wait自然结束，绝无terminate/kill路径。"""
        gate.verify_owner_fd(owner_fd, self.OWNER_LOCK)
        if not gate.read_json(self.CONTROL).get("continue_after_cycle"):
            raise gate.GateError("本候选已禁止下一房")
        precheck = self.check_admission()
        directory, plan = self.prepare_room(number)
        ledger = gate.ReleaseLedger(directory / "handoff")
        ledger.append("prechecked", precheck)
        ledger.append("pause_requested", {"no_predecessor_control_write": True})
        ledger.append("boundary_verified", {"engineering_passed": True,
            "other_players_live": bool(self.tools.h.other_players()), "owner_lock_acquired": True})
        # 子进程创建有不确定性：意图落盘后的任何失败均由恢复核状态，不再调用launcher。
        ledger.append("dispatch_intent", {"activation_prechecked": True, "spec_sha256": precheck["spec_sha256"]})
        command = [sys.executable, "-B", str(self.ROOT / "scripts/run_auto_match.py"),
                   "--config", plan["config_path"], "--token-file", self.spec["credential_path"]]
        with (directory / "FREE-STDOUT-STDERR.log").open("x") as stream:
            child = self.launcher(command, cwd=self.ROOT, env=self.player_environment(), stdout=stream,
                                  stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(owner_fd,))
            gate.save_exclusive(directory / "FREE-START.json", {"pid": child.pid, "inherits_owner_lock": True,
                                "at_unix": time.time(), "entry": command[2], "cwd": str(self.ROOT)})
            live = self.observe(child.pid, command[2])
            # 即使新PID暂未验证也必须等待这个真实child；不能丢下子进程或杀玩家。
            if live.get("expected_command_live") is True:
                ledger.append("started", {"controller_pid": child.pid, "expected_command_live": True,
                                           "owner_fd_inherited": True})
            self.publish(state="players_running", batch=number, active_children={"free": child.pid})
            code = child.wait()
        gate.save_exclusive(directory / "FREE-CHILD-TERMINAL.json", {"actual_exit_code": code,
            "controller_sent_termination_signal": False, "at_unix": time.time()})
        return self.finalize_room(directory, plan)

    def finalize_room(self, directory: Path, plan: dict) -> dict:
        """复用旧verify_free真实终态；只适配数据路径展示，不改其验证字节码。"""
        namespace = Path(self.spec["active_root"]).resolve()
        session = Path(plan["free_session"])
        if not session.resolve().is_relative_to(namespace):
            raise gate.GateError("审计数据不在声明的根外命名空间")
        original = self.tools.n.tail_finished
        adapted = FunctionType(original.__code__, {**original.__globals__, "ROOT": namespace},
                               original.__name__, original.__defaults__, original.__closure__)
        self.tools.n.tail_finished = adapted
        try:
            verified = self.tools.verify_free(directory, plan)
        finally:
            self.tools.n.tail_finished = original
        terminal = self.tools.a.end_records(directory / "FREE-STDOUT-STDERR.log", "free")[0]
        run = session / "audit/runs" / verified["run_id"]
        summary = gate.read_json(run / "summary.json")
        light = scan_lightweight(run, **self.spec.get("light_scan", {"max_bytes": 268435456, "max_seconds": 3.0}))
        evidence = {"identity": plan["identity"], **light,
            "critical_audit_missing": summary["missing_high_priority"],
            "compute_faults": terminal["decision_compute"]["faults"] + terminal["decision_compute"]["policy_failures"],
            "identity_drift": 0, "serialization_failures": summary["serialization_failures"],
            "write_failures": summary["write_failures"], "raw_audit_present": True,
            "owner_released_by_player": not self.tools.h.other_players(),
            "terminal": {"actual_exit_code": gate.read_json(directory / "FREE-CHILD-TERMINAL.json")["actual_exit_code"],
                         "terminal_reason": terminal["terminal_reason"], "termination_signal_sent": False},
            "compute": terminal["decision_compute"], "tables": verified["game_finished"]}
        if summary["raw_retention"]["dropped"]:
            evidence["real_new_missed_actions"] = None
            evidence["warnings"]["raw_dropped"] = summary["raw_retention"]["dropped"]
        evidence["warnings"].update({"written_" + key: value for key, value in summary.get("written_by_kind", {}).items()
                                    if key in ("decision_input", "decision_planned", "submission_outcome")})
        result = gate.room_gate(evidence, self.spec["identity"])
        gate.save_exclusive(directory / "LIGHT-GATE.json", {"evidence": evidence, "result": result})
        gate.save_exclusive(directory / "RUN-CLOSED.json", {"continuation_safety_verified": True,
            "natural_boundary_verified": True, "free": verified, "gate": result,
            "at_unix": time.time(), "does_not_wait_for_postprocess": True})
        if result["block_next_candidate_room"]:
            block_next_room(self.STATE, result)
            gate.ReleaseLedger(directory / "handoff").append("fault", result)
        else:
            ledger = gate.ReleaseLedger(directory / "handoff")
            if ledger.status()["phase"] == "started":
                ledger.append("first_room", result)
        self.publish(state="run_closed", batch=plan["batch"], active_children={}, gate=result)
        return {"directory": str(directory), "gate": result, "natural_boundary_verified": True}

    def recover_closed(self) -> list[int]:
        """启动意图后缺玩家终态保持待查；有真实终态可补关闭，不重匹配该房。"""
        prior = []
        for directory in sorted(self.STATE.glob("batch-*")):
            if not (directory / "PLAN.json").is_file():
                raise gate.GateError("已有批次准备不完整；需核真实状态，不自动再匹配")
            plan = gate.read_json(directory / "PLAN.json")
            if plan["spec_sha256"] != gate.digest(self.spec):
                raise gate.GateError("控制状态被其他发布物复用")
            if not (directory / "FREE-CHILD-TERMINAL.json").exists():
                raise gate.GateError("原启动/匹配结果未知；禁止重发")
            if not (directory / "RUN-CLOSED.json").exists():
                self.finalize_room(directory, plan)
            prior.append(plan["batch"])
        return prior

    def rollback(self, closed: dict, owner_fd: int) -> None:
        """自然房界将同一锁FD交给修后父控制器；不恢复旧错误核心、不等待统计。"""
        parent_path = self.spec.get("rollback_spec")
        if not parent_path or closed.get("natural_boundary_verified") is not True:
            self.publish(state="blocked_no_verified_parent", active_children={})
            return
        parent_path = Path(parent_path).resolve()
        parent = gate.read_json(parent_path)
        gate.preflight(parent)
        if parent["shared"] != {**self.spec["shared"], "state_dir": parent["shared"]["state_dir"]}:
            raise gate.GateError("回退父版未共用三把固定锁")
        if parent.get("qualification", {}).get("corrected_fallback_passed") is not True:
            raise gate.GateError("回退父版不是修后合格包")
        if Path(parent["shared"]["state_dir"]).resolve() == self.STATE:
            raise gate.GateError("回退父版不能复用被阻止的候选状态目录")
        parent_control = Path(parent["shared"]["state_dir"]) / "control.json"
        if parent_control.exists() and gate.read_json(parent_control).get("candidate_blocked"):
            raise gate.GateError("父版已有硬故障，不能用旧准入布尔值重新启动")
        directory = Path(closed["directory"])
        intent = directory / "ROLLBACK-DISPATCH-INTENT.json"
        if intent.exists():
            raise gate.GateError("回退已留启动意图；核真实owner，不自动再启动")
        gate.verify_owner_fd(owner_fd, self.OWNER_LOCK)
        block_next_room(self.STATE, {"rollback_parent": str(parent_path)}, stop_background=True)
        gate.save_exclusive(intent, {"parent_spec": str(parent_path), "parent_spec_sha256": gate.digest(parent),
                                    "at_unix": time.time(), "players_natural_only": True})
        environment = self.player_environment()
        environment["PYTHONPATH"] = os.pathsep.join((str(Path(parent["release_root"]) / "src"), parent["release_root"]))
        environment[OWNER_FD_ENV] = str(owner_fd)
        environment[ADOPT_STATE_ENV] = str(self.STATE)
        environment[ROLLBACK_ACTIVATION_ENV] = str(intent)
        command = [sys.executable, "-B", str(Path(parent["release_root"]) / ENTRY_RELATIVE),
                   "watch", "--spec", str(parent_path)]
        with (self.STATE / "rollback.stdout.log").open("a") as stream:
            child = self.launcher(command, cwd=Path(parent["release_root"]), env=environment,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(owner_fd,))
        gate.save_exclusive(directory / "ROLLBACK-DISPATCHED.json", {"controller_pid": child.pid,
            "owner_lock_continuously_inherited": True, "live_verification_pending": True, "at_unix": time.time()})
        self.publish(state="rollback_dispatched", active_children={}, successor_controller_pid=child.pid)

    def watch(self) -> None:
        """真正运行入口；SIGINT/TERM只阻止下一房，当前玩家始终自然wait。"""
        self.STATE.mkdir(parents=True, exist_ok=True)
        self.check_admission()
        inherited = os.environ.pop(OWNER_FD_ENV, None)
        owner = os.fdopen(int(inherited), "a+") if inherited is not None else self.OWNER_LOCK.open("a+")
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "stop_after_room", True))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stop_after_room", True))
        with owner:
            if inherited is not None:
                gate.verify_owner_fd(owner.fileno(), self.OWNER_LOCK)
            while True:
                try:
                    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    self.publish(state="waiting_existing_owner_natural_finish", active_children={})
                    if self.stop_after_room:
                        return
                    time.sleep(2)
            if self.tools.h.other_players():
                raise gate.GateError("仍有真实玩家；不启动第二owner")
            predecessor_state = os.environ.pop(ADOPT_STATE_ENV, None)
            if predecessor_state is not None:
                predecessor = Path(predecessor_state).resolve()
                if predecessor == self.STATE or predecessor.is_relative_to(self.ROOT):
                    raise gate.GateError("继承后台队列不是独立根外旧状态")
                transfer = self.STATE / "TRANSFER-QUEUE.json"
                if not transfer.exists():
                    gate.save_exclusive(transfer, {"predecessor_state": str(predecessor),
                        "only_unstarted_adopted": True, "at_unix": time.time()})
            if not self.CONTROL.exists():
                write_state(self.CONTROL, {"continue_after_cycle": True, "background_enabled": True,
                                         "minimum_free_bytes": 8589934592})
            activation = os.environ.pop(ROLLBACK_ACTIVATION_ENV, None)
            if activation is not None:
                ticket = gate.read_json(Path(activation))
                if inherited is None or ticket.get("parent_spec_sha256") != gate.digest(self.spec):
                    raise gate.GateError("回退激活票据与继承锁／父包不符")
                predecessor_closed = gate.read_json(Path(activation).parent / "RUN-CLOSED.json")
                if predecessor_closed.get("natural_boundary_verified") is not True:
                    raise gate.GateError("回退前房未自然闭合")
                control = gate.read_json(self.CONTROL)
                if control.get("candidate_blocked"):
                    raise gate.GateError("父版已有硬故障，不能重启")
                write_state(self.CONTROL, {**control, "continue_after_cycle": True, "background_enabled": True})
                gate.save_exclusive(self.STATE / ("ROLLBACK-ACTIVATION-%s.json" % gate.digest(ticket)[:16]),
                    {"ticket_pin": gate.pin(Path(activation)), "same_owner_fd": True, "at_unix": time.time()})
            prior = self.recover_closed()
            control = gate.read_json(self.CONTROL)
            if control.get("candidate_blocked") and prior:
                last = self.STATE / ("batch-%03d" % max(prior))
                closed = gate.read_json(last / "RUN-CLOSED.json")
                self.rollback({"directory": str(last), "natural_boundary_verified": closed["natural_boundary_verified"]},
                              owner.fileno())
                return
            # worker不继承Token owner FD；其共享后处理锁等待不会卡住此处续赛。
            with (self.STATE / "worker.stdout.log").open("a") as stream:
                self.launcher([sys.executable, "-B", str(self.ROOT / ENTRY_RELATIVE), "worker", "--spec", str(self.spec_path)],
                    cwd=self.ROOT, env=self.player_environment(), stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            number = 1 + max(prior, default=0)
            while not self.stop_after_room and gate.read_json(self.CONTROL)["continue_after_cycle"]:
                if self.tools.h.other_players():
                    raise gate.GateError("真实玩家仍活，不续下一房")
                import shutil
                if shutil.disk_usage(self.STATE).free < gate.read_json(self.CONTROL)["minimum_free_bytes"]:
                    raise gate.GateError("审计磁盘余量不足")
                closed = self.run_room(number, owner.fileno())
                number += 1
                if closed["gate"]["block_next_candidate_room"] or gate.read_json(self.CONTROL).get("candidate_blocked"):
                    self.rollback(closed, owner.fileno())
                    return
            self.publish(state="stopped_after_natural_finish", active_children={})

    def pending_jobs(self) -> list[Path]:
        """只收纳已自然闭合且未START任务；历史START失败/未知任务不自动重做。"""
        jobs = sorted(self.STATE.glob("batch-*")) + [Path(row["directory"]) for row in self.spec.get("adopted_jobs", [])]
        transfer = self.STATE / "TRANSFER-QUEUE.json"
        if transfer.exists():
            jobs += sorted(Path(gate.read_json(transfer)["predecessor_state"]).glob("batch-*"))
        return [p for p in jobs if (p / "RUN-CLOSED.json").exists() and not (p / "POSTPROCESS-START.json").exists()]

    def worker(self) -> None:
        """真实低优先级单worker；每项spawn到原任务根，且继承共用postprocess锁。"""
        with self.WORKER_LOCK.open("a+") as singleton:
            while gate.read_json(self.CONTROL).get("background_enabled", True):
                try:
                    fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(5)  # 旧当前统计自然完；只让后台等，不让匹配等。
            else:
                return
            os.nice(15)
            priority = subprocess.run(["taskpolicy", "-b", "-p", str(os.getpid())], capture_output=True)
            if priority.returncode:
                raise gate.GateError("后台IO优先级未确认，不启动重任务")
            with self.POSTPROCESS_LOCK.open("a+") as lock:
                while gate.read_json(self.CONTROL).get("background_enabled", True):
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        time.sleep(5)
                        continue
                    try:
                        jobs = self.pending_jobs()
                        if jobs:
                            job = jobs[0]
                            gate.save_exclusive(job / "POSTPROCESS-START.json", {"worker_pid": os.getpid(),
                                "at_unix": time.time(), "single_shared_postprocess_lock": True})
                            # 子进程全新解释器，按PLAN/明确继承清单选择该房原源码根。
                            with (job / "T199-POSTPROCESS.log").open("x") as stream:
                                child = self.launcher([sys.executable, "-B", str(self.ROOT / ENTRY_RELATIVE),
                                    "postprocess-job", "--spec", str(self.spec_path), "--batch", str(job),
                                    "--postprocess-fd", str(lock.fileno())], cwd=self.ROOT,
                                    env=self.player_environment(), stdout=stream, stderr=subprocess.STDOUT,
                                    start_new_session=True, pass_fds=(lock.fileno(),))
                                code = child.wait()
                            gate.save_exclusive(job / "T199-POSTPROCESS-TERMINAL.json", {"actual_exit_code": code,
                                "at_unix": time.time(), "does_not_block_next_match": True})
                    finally:
                        fcntl.flock(lock, fcntl.LOCK_UN)
                    time.sleep(5)


def postprocess_job(spec_path: Path, directory: Path, lock_fd: int) -> None:
    """复用原捕获、postgame封存与analyze_lane；每房始终用自己的旧/新root。"""
    spec = gate.read_json(spec_path)
    gate.verify_owner_fd(lock_fd, Path(spec["shared"]["postprocess_lock"]))
    plan = gate.read_json(directory / "PLAN.json")
    if "release_root" in plan:
        root = Path(plan["release_root"]).resolve()
        config_path = Path(plan["config_path"])
    else:
        inherited = [r for r in spec.get("adopted_jobs", []) if Path(r["directory"]).resolve() == directory.resolve()]
        if len(inherited) != 1 or gate.pin(directory / "PLAN.json") != inherited[0]["plan_pin"]:
            raise gate.GateError("历史后台任务未明确绑定原根/配置")
        root, config_path = Path(inherited[0]["release_root"]).resolve(), Path(inherited[0]["config_path"])
    os.environ["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root)))
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    tools = load_tools(root, Path(spec["shared"]["owner_lock"]), Path(spec["shared"]["postprocess_lock"]),
                       Path(spec["shared"]["state_dir"]), spec.get("credential_path"))
    failures = []
    try:
        session = root / plan["free_session"]
        tools.h.capture(session, gate.read_json(config_path), tools.h.free_room(session), directory / "free-capture")
        runs = list((session / "audit/runs").glob("*"))
        if len(runs) != 1:
            raise gate.GateError("后台原房run数量不为1")
        actual = gate.read_json(runs[0] / "manifest.json")["payload"]
        rules = {"base_score": actual["base_score"], "you_cai_bi_kao": actual["you_cai_bi_kao"]}
        if type(rules["base_score"]) is not int or rules["base_score"] <= 0 or type(rules["you_cai_bi_kao"]) is not bool:
            raise gate.GateError("原房规则配置未知，不能为赛后任务填默认值")
        gate.save_exclusive(directory / "ACTUAL-RULE-CONFIG.json", rules)
        code = tools.n.run_postprocess_step(directory, "FREE-POSTGAME",
            [sys.executable, str(root / "scripts/audit_tool.py"), "postgame", str(session),
             "--rule-config", str(directory / "ACTUAL-RULE-CONFIG.json")], directory / "FREE-POSTGAME.log", lock_fd)
        if code != 0:
            raise gate.GateError("postgame失败；不自动重做")
        analysis = tools.a.analyze_lane(directory, plan, "free")
        gate.save_exclusive(directory / "SUMMARY.json", analysis)
        hard_timeouts = sum(row.get("kind") == "official_discard_timeout"
            for rows in analysis["engineering_contaminated_tables"].values() for row in rows)
        # 旧包历史问题只保留；相同发布物的迟到硬故障可以挡当前候选的下一房。
        if (plan.get("spec_sha256") == gate.digest(spec)
                and (hard_timeouts or analysis["compute_faults"] or not analysis["postgame_audit_complete"]
                     or not analysis["postgame_bundle_verified"])):
            block_next_room(Path(spec["shared"]["state_dir"]), {"late_postprocess_hard_fault": True,
                "real_discard_timeouts": hard_timeouts, "compute_faults": analysis["compute_faults"],
                "source_batch": str(directory)})
    except Exception as error:
        failures.append({"type": type(error).__name__, "reason": str(error)})
    gate.save_exclusive(directory / "POSTPROCESS-CLOSED.json", {"failures": failures,
        "at_unix": time.time(), "does_not_block_next_match": True, "source_root": str(root)})
    if failures:
        raise gate.GateError("后台失败已保存，不影响当前玩家")


def main() -> None:
    """inspect为无网络预检；真实watch/worker首次由总筹在自然房界调用。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "status", "watch", "worker", "postprocess-job"))
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--postprocess-fd", type=int)
    args = parser.parse_args()
    if args.command == "postprocess-job":
        postprocess_job(args.spec, args.batch, args.postprocess_fd)
        return
    value = Controller(args.spec)
    if args.command == "inspect":
        print(json.dumps(value.inspect(), ensure_ascii=False, indent=2))
    elif args.command == "status":
        print(json.dumps(value.status(), ensure_ascii=False, indent=2))
    elif args.command == "watch":
        value.watch()
    else:
        value.worker()


if __name__ == "__main__":
    main()
