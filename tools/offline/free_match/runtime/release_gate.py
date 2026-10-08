"""T199无网络发布准备：核不可变字节、保存一次交接意图并裁定下一房。

本工具不读取Token，不启动玩家，不写活跃守护器控制文件。真实启动器必须
消费本工具的状态和固定共享锁；当前只交付预检／收据接缝，不宣称已能交接。
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
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

SCHEMA = "t199-release-preparation/1"
MODES = ("test_room", "auto_match", "test_tournament", "official_tournament")
LEGACY_DIR = 'tools/offline/free_match/legacy'
FREE_DRIVER = 'tools/offline/free_match/legacy/free_watchdog.py'
LEGACY_TOOLS = (
    FREE_DRIVER,
    LEGACY_DIR + "/watchdog_nonblocking.py",
    LEGACY_DIR + "/watchdog.py",
    LEGACY_DIR + "/analyze.py",
    'tools/offline/free_match/legacy/summarize_closed.py',
    "scripts/audit_tool.py",
    "scripts/test_room_campaign_watchdog.py",
)
HARD_COUNTS = (
    "real_new_missed_actions", "illegal_submissions", "unrecovered_state",
    "critical_audit_missing", "compute_faults", "identity_drift",
)
RESOURCE_COUNTS = (
    "active", "current", "live_processes", "owned", "pending", "ready",
    "transport_inflight", "transport_threads_alive", "late_reap_inflight",
    "late_reap_threads_alive", "bound_games", "releasing_games",
)


class GateError(ValueError):
    """证据不够、身份不符或禁止重复启动时拒绝；调用方不能据此重匹配。"""


def digest(value: Any) -> str:
    """规范JSON摘要；不参与线上动作计时。"""
    body = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode()).hexdigest()


def read_json(path: Path) -> Any:
    """只读指定公开证据；拒绝Token目录，错误由调用方记录。"""
    if "token" in path.parts:
        raise GateError("禁止读取Token目录")
    return json.loads(path.read_text())


def pin(path: Path) -> dict[str, Any]:
    """完整文件字节摘要；仅适用于代码、制品和小型公共证据。"""
    if "token" in path.parts:
        raise GateError("禁止读取Token目录")
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def relative_file(root: Path, relative: str) -> Path:
    """源码必须是根内真实文件；不接受绝对路径、父目录或逃逸符号链接。"""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts or "token" in relative_path.parts:
        raise GateError("非法冻结相对路径：" + relative)
    path = root / relative_path
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise GateError("冻结文件缺失或逃逸：" + relative)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
        raise GateError("冻结执行文件不得经符号链接：" + relative)
    return path


def inventory(root: Path) -> dict[str, Any]:
    """静态盘点当前S03四包及动态旧工具闭包，不导入业务、不复制大原件。"""
    root = root.resolve()
    packages = sorted(root.glob("prebuilt/vip-s03-bounded-d1-*-v3/manifest.json"))
    if len(packages) != 4:
        raise GateError("当前S03四作用域包数量不为4")
    paths: set[str] = set(LEGACY_TOOLS)
    modes: dict[str, str] = {}
    mismatches: list[str] = []
    expected: dict[str, str] = {}
    for package_path in packages:
        package = read_json(package_path)
        mode = package["allowed_modes"]
        if len(mode) != 1 or mode[0] not in MODES or mode[0] in modes:
            raise GateError("四包作用域重复或未知")
        modes[mode[0]] = package_path.relative_to(root).as_posix()
        paths.add(modes[mode[0]])
        for relative, sha256 in package["source_manifest"].items():
            if relative in expected and expected[relative] != sha256:
                raise GateError("四包源码身份互相矛盾")
            expected[relative] = sha256
            paths.add(relative)
        paths.update(package["evidence_sha256"])
        compiled = package["compiled_runtime"]
        directory = compiled["directory"]
        paths.add(directory + "/manifest.json")
        paths.update(directory + "/" + name for name in compiled["manifest"]["files"])
        identity = compiled["manifest"]["identity"]
        paths.add(identity["contract_path"])
        shared = compiled["manifest"]["shared_original_helpers"]
        shared_dir = shared["directory"]
        paths.add(shared_dir + "/manifest.json")
        paths.update(shared_dir + "/" + row["filename"] for row in shared["manifest"]["binaries"].values())
        paths.update(shared_dir + "/" + name for name in shared["manifest"]["generated_source_sha256"])
    paths.update(p.relative_to(root).as_posix() for p in (root / "src/hangma_bot/hangma").glob("_grouped_native*.so"))
    paths.update(p.relative_to(root).as_posix() for p in root.glob("configs/vip-s03-bounded-d1-v3.*.example.json"))
    # 动态旧工具只按上述已核真实边收纳；普通scripts导入用AST继续闭合。
    queue = list(paths)
    while queue:
        relative = queue.pop()
        path = relative_file(root, relative)
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(), filename=relative)
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                if name.startswith("scripts."):
                    dependency = name.replace(".", "/") + ".py"
                    if (root / dependency).is_file() and dependency not in paths:
                        paths.add(dependency)
                        queue.append(dependency)
    files = {}
    for relative in sorted(paths):
        files[relative] = pin(relative_file(root, relative))
        if relative in expected and files[relative]["sha256"] != expected[relative]:
            mismatches.append(relative)
    return {"schema": SCHEMA, "source_root": str(root), "files": files,
            "mode_manifests": modes, "production_source_count": len(expected),
            "source_manifest_mismatches": mismatches, "inventory_static_only": True,
            "import_spawn_verified": False, "runtime_launch_implemented": False,
            "made_at_unix": time.time()}


def inspect_layout(spec: Mapping[str, Any]) -> dict[str, Any]:
    """核冻结根和实际门对象共用路径；共享锁位于冻结根外，Unix时间只供关联。"""
    root = Path(spec["release_root"])
    active = Path(spec["active_root"])
    if not root.is_absolute() or root.resolve() == active.resolve() or root.is_symlink():
        raise GateError("发布根必须是独立真实绝对路径")
    values = {}
    for key in ("owner_lock", "postprocess_lock", "worker_lock", "state_dir"):
        path = Path(spec["shared"][key])
        if not path.is_absolute() or path.resolve().is_relative_to(root.resolve()):
            raise GateError("共享路径必须在冻结根外：" + key)
        values[key] = str(path.resolve())
    if len({values[k] for k in ("owner_lock", "postprocess_lock", "worker_lock")}) != 3:
        raise GateError("owner／后处理／worker锁不能共用同一文件")
    return {"release_root": str(root.resolve()), **values}


def preflight(spec: Mapping[str, Any]) -> dict[str, Any]:
    """无网络验证新根字节和四作用域，不授规则／增强／性能或参赛通过。"""
    layout = inspect_layout(spec)
    root = Path(layout["release_root"])
    if not spec.get("files"):
        raise GateError("缺完整运行清单")
    for relative, expected in spec["files"].items():
        if pin(relative_file(root, relative)) != expected:
            raise GateError("冻结身份漂移：" + relative)
    if set(spec["mode_manifests"]) != set(MODES):
        raise GateError("缺四种包作用域")
    for mode, relative in spec["mode_manifests"].items():
        if relative not in spec["files"] or read_json(relative_file(root, relative))["allowed_modes"] != [mode]:
            raise GateError("包作用域不符：" + mode)
    return {"complete": True, "spec_sha256": digest(spec), "layout": layout,
            "verified_files": len(spec["files"]), "network_calls": 0,
            "runtime_launch_implemented": False}


def verify_owner_fd(fd: int, shared_owner_lock: Path) -> dict[str, Any]:
    """核真实继承FD与同Token锁inode；不新建或获取活跃锁，不允许旁路新锁。"""
    actual, expected = os.fstat(fd), shared_owner_lock.stat()
    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise GateError("继承FD不是同Token共享owner锁")
    return {"owner_fd_verified": True, "device": actual.st_dev, "inode": actual.st_ino}


def room_gate(evidence: Mapping[str, Any], expected_identity: Mapping[str, Any]) -> dict[str, Any]:
    """轻量终态裁定：数值0才算无故障，缺关键事实保持未知；不重算策略。"""
    hard = []
    unknown = []
    if evidence.get("identity") != expected_identity:
        hard.append("identity_mismatch")
    for key in HARD_COUNTS:
        value = evidence.get(key)
        if type(value) is not int or value < 0:
            unknown.append(key)
        elif value:
            hard.append(key)
    for key in ("serialization_failures", "write_failures"):
        value = evidence.get(key)
        if type(value) is not int or value < 0:
            unknown.append(key)
        elif value:
            hard.append(key)
    terminal = evidence.get("terminal", {})
    if (terminal.get("actual_exit_code") != 0 or type(terminal.get("actual_exit_code")) is not int
            or terminal.get("terminal_reason") != "tournament_finished"
            or terminal.get("termination_signal_sent") is not False):
        unknown.append("natural_terminal")
    if evidence.get("raw_audit_present") is not True or evidence.get("owner_released_by_player") is not True:
        unknown.append("raw_audit_or_player_lock")
    compute = evidence.get("compute", {})
    if compute.get("closed") is not True:
        unknown.append("compute.closed")
    for key in RESOURCE_COUNTS:
        if type(compute.get(key)) is not int or compute[key] != 0:
            unknown.append("compute." + key)
    tables = evidence.get("tables", [])
    if len(tables) != 10 or len({r.get("game_id") for r in tables}) != 10:
        unknown.append("ten_unique_tables")
    for table in tables:
        scores = table.get("final_scores_seat_order_0_3", [])
        if (not table.get("game_id") or not table.get("source") or len(scores) != 4
                or any(type(x) is not int for x in scores) or sum(scores) != 0):
            unknown.append("official_final_scores")
    return {"engineering_passed": not hard and not unknown, "continuation_allowed": not hard and not unknown,
            "block_next_candidate_room": bool(hard or unknown), "rollback_required": bool(hard),
            "hard_failures": sorted(set(hard)), "unknown": sorted(set(unknown)),
            "warnings": evidence.get("warnings", {}), "scores_not_used_for_admission": True,
            "does_not_wait_for_postprocess": True}


def save_exclusive(path: Path, value: Any) -> None:
    """写持久独占收据；已存在不覆盖，fsync后才让调用方执行外部副作用。"""
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ReleaseLedger:
    """T199一次交接的持久收据；dispatch-intent存在后禁止自动再启动。"""

    def __init__(self, directory: Path):
        """目录必须是调用方为此次发布独占的新目录，不能指向旧watchdog。"""
        if not any(part.startswith("t199-") for part in directory.resolve().parts):
            raise GateError("交接收据只允许T199新目录，不能写旧watchdog")
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """依序记录证据，不触碰当前比赛；本地journal锁与owner锁用途分开。"""
        with (self.directory / "journal.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self.status()
            phase = state["phase"]
            required = {"prechecked": "new", "pause_requested": "prechecked",
                        "boundary_verified": "pause_requested", "dispatch_intent": "boundary_verified",
                        "started": "dispatch_intent", "first_room": "started"}
            if event in required and phase != required[event]:
                raise GateError("阶段不符或已有启动意图：" + phase + " -> " + event)
            if event == "prechecked" and payload.get("complete") is not True:
                raise GateError("预检未通过")
            if event == "boundary_verified":
                if (payload.get("engineering_passed") is not True or payload.get("other_players_live") is not False
                        or payload.get("owner_lock_acquired") is not True):
                    raise GateError("房界、玩家或同Token锁未闭合")
            if event == "dispatch_intent":
                if payload.get("activation_prechecked") is not True or not payload.get("spec_sha256"):
                    raise GateError("激活前实际身份预检缺失")
                original = read_json(self.directory / "001.json")["payload"]
                if payload["spec_sha256"] != original.get("spec_sha256"):
                    raise GateError("激活身份不是原预检发布物")
            if event == "started" and (type(payload.get("controller_pid")) is not int or payload["controller_pid"] <= 0
                                       or payload.get("expected_command_live") is not True
                                       or payload.get("owner_fd_inherited") is not True):
                raise GateError("新owner未取得真实启动／锁继承收据；不得重匹配")
            if event == "first_room" and payload.get("engineering_passed") is not True:
                raise GateError("首房不能登记工程合格")
            if event not in (*required, "fault", "rollback_requested"):
                raise GateError("未知交接事件")
            if event == "fault" and payload.get("block_next_candidate_room") is not True:
                raise GateError("普通告警不作为停线故障")
            if event == "rollback_requested" and (not state.get("block_next_candidate_room")
                    or payload.get("corrected_rules_parent_verified") is not True):
                raise GateError("无停线事实或修后父包收据")
            rows = sorted(self.directory.glob("[0-9]*.json"))
            value = {"event": event, "payload": dict(payload), "at_unix": time.time(),
                     "previous_sha256": pin(rows[-1])["sha256"] if rows else None}
            save_exclusive(self.directory / ("%03d.json" % (len(rows) + 1)), value)
            return self.status()

    def status(self) -> dict[str, Any]:
        """重启只读真实收据；有启动意图无启动收据时保持待查，不准重发POST。"""
        phase = "new"
        blocked = False
        previous = None
        for path in sorted(self.directory.glob("[0-9]*.json")):
            row = read_json(path)
            if row["previous_sha256"] != previous:
                raise GateError("持久阶段收据断链")
            previous = pin(path)["sha256"]
            phase = row["event"]
            if phase in ("fault", "rollback_requested"):
                blocked = True
        return {"phase": phase, "block_next_candidate_room": blocked,
                "new_dispatch_intent_allowed": phase == "boundary_verified" and not blocked,
                "dispatch_ambiguity": phase == "dispatch_intent",
                "automatic_rematch_allowed": False, "players_termination_allowed": False,
                "runtime_launch_implemented": False}


def main() -> None:
    """命令只盘点、预检、读取状态；状态机由root调用公开ReleaseLedger接缝。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "preflight", "status"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            if args.root is None:
                raise GateError("inventory需要--root")
            value = inventory(args.root)
        elif args.command == "preflight":
            if args.spec is None:
                raise GateError("preflight需要--spec")
            value = preflight(read_json(args.spec))
        else:
            if args.ledger is None or not args.ledger.is_dir():
                raise GateError("status需要已有ledger目录")
            value = ReleaseLedger(args.ledger).status()
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            save_exclusive(args.out, value)
        print(json.dumps(value if args.command != "inventory" else {
            "files": len(value["files"]), "production_source_count": value["production_source_count"],
            "source_manifest_mismatches": value["source_manifest_mismatches"],
            "import_spawn_verified": False, "runtime_launch_implemented": False}, ensure_ascii=False, indent=2))
    except (GateError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"complete": False, "error": str(error), "network_calls": 0}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
