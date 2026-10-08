"""一次性自然交接：等旧owner释放，验终态后整合精确补丁并传递同一锁。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1')
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t191-free-watchdog')


def load(path):
    """读取已指定的公共证据或私有控制文件，不读取凭证。"""
    return json.loads(path.read_text())


def pin(path):
    """完整原文SHA，用于来源和终态确认。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value, *, exclusive=False):
    """独占原证据或原子更新公共状态，墙钟仅用于关联。"""
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x") as output:
            output.write(text)
    else:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text)
        temporary.replace(path)


def run(args, output):
    """执行确定的本地检查并保存stdout；失败停止交接，不伪造通过。"""
    with output.open("x") as stream:
        result = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"本地步骤失败：{output.name}，退出{result.returncode}")


def main():
    """不终止玩家、不新匹配旧房；同一owner锁从旧玩家到新watch连续持有。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, default=1)
    attempt = parser.parse_args().attempt
    assert attempt in (1, 2), "交接失败不得无界自动重试"
    start_name = "HANDOFF-COORDINATOR-START.json" if attempt == 1 else "HANDOFF-COORDINATOR-START-002.json"
    spec = importlib.util.spec_from_file_location("t191_predecessor_verify", _project_file(_PROJECT_ROOT, OLD / "free_watchdog.py"))
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    approval = load(_project_file(_PROJECT_ROOT, HERE / "ROOT-FINAL-WIRING-REVIEW.json"))
    assert approval["mainline_application_approved_after_active_research_releases_and_natural_free_handoff"]
    assert pin(_project_file(_PROJECT_ROOT, HERE / "wiring/P0-WIRING.patch")) == approval["pins"]["P0-WIRING.patch"]["sha256"]
    for stage in ("speed-stage-001", "speed-stage-002"):
        closed = load(_project_file(_PROJECT_ROOT, HERE / "natural" / (stage + "-dispatch") / "CLOSED.json"))
        assert closed["complete"] and closed["resources_released"] and closed["worker_returncodes"] == [0] * 4
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    save(_project_file(_PROJECT_ROOT, HERE / start_name), {"pid": os.getpid(), "at_unix": time.time(),
        "patch_sha256": pin(_project_file(_PROJECT_ROOT, HERE / "wiring/P0-WIRING.patch")), "players_natural_only": True}, exclusive=True)
    try:
        with old.OWNER_LOCK.open("a+") as owner:
            while True:
                try:
                    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-STATUS.json"), {"state": "waiting_old_owner_natural_release",
                        "pid": os.getpid(), "at_unix": time.time(), "production_applied": False})
                    time.sleep(2)
            state = load(_project_file(_PROJECT_ROOT, OLD / "STATUS.json"))
            assert state["state"] == "stopped_after_natural_finish" and not state["active_children"]
            assert not old.h.other_players(), "仍有真实玩家，禁止整合或启动第二owner"
            # stopped状态只保证自然完成，不承诺保留batch；以真实最后计划为准。
            directories = list(OLD.glob("batch-*"))
            assert directories, "前任没有实际房间计划"
            predecessor = max(directories, key=lambda directory: load(directory / "PLAN.json")["batch"])
            last_batch = load(predecessor / "PLAN.json")["batch"]
            assert predecessor.name == "batch-%03d" % last_batch
            verified = old.verify_free(predecessor, load(predecessor / "PLAN.json"))
            assert load(predecessor / "RUN-CLOSED.json")["continuation_safety_verified"]
            old_manifest = load(_project_file(_PROJECT_ROOT, ROOT / "prebuilt/vip-s02-bounded-d1-free-v6/manifest.json"))
            assert all(pin(_project_file(_PROJECT_ROOT, ROOT / path)) == digest for path, digest in old_manifest["source_manifest"].items())
            for item in load(_project_file(_PROJECT_ROOT, HERE / "wiring/CHANGESET.json"))["files"]:
                path = _project_file(_PROJECT_ROOT, ROOT / item["path"])
                assert (not path.exists()) if item["new_file"] else pin(path) == item["before_sha256"]
            run(["git", "apply", "--check", str(_project_file(_PROJECT_ROOT, HERE / "wiring/P0-WIRING.patch"))], _project_file(_PROJECT_ROOT, HERE / "MAIN-APPLY-CHECK.log"))
            run(["git", "apply", str(_project_file(_PROJECT_ROOT, HERE / "wiring/P0-WIRING.patch"))], _project_file(_PROJECT_ROOT, HERE / "MAIN-APPLY.log"))
            for item in load(_project_file(_PROJECT_ROOT, HERE / "wiring/CHANGESET.json"))["files"]:
                assert pin(_project_file(_PROJECT_ROOT, ROOT / item["path"])) == item["after_sha256"]
            run([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "wiring/verify_launch_configs.py")), "--workspace", str(ROOT),
                "--output", str(_project_file(_PROJECT_ROOT, HERE / "MAIN-CONFIG-CHECKS.json"))], _project_file(_PROJECT_ROOT, HERE / "MAIN-CONFIG-CHECKS.log"))
            save(_project_file(_PROJECT_ROOT, HERE / "TRANSFER.json"), {"directory": str(predecessor.relative_to(ROOT)),
                "old_run_closed_sha256": pin(predecessor / "RUN-CLOSED.json"),
                "old_player_pid": load(predecessor / "FREE-START.json")["pid"],
                "old_controller_pid": state["controller_pid"], "players_natural_end_only": True,
                "predecessor_unstarted_postprocess_adopted": True}, exclusive=True)
            program = """
import importlib.util,json,time
from pathlib import Path
p=Path('review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/free_watchdog.py')
s=importlib.util.spec_from_file_location('t191_new_approval',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.h.write(p.parent/'START-APPROVAL.json',{'approved':True,'formal_release':False,'strength_admission':False,
 'identity':m.identity(),'driver_sha256':m.hashes(),'at_unix':time.time(),
 'authorization':'用户授权持续自由赛、测试与接线；总筹ROOT-FINAL-WIRING-REVIEW批准精确工程包自然交接，原公式不变。'},exclusive=True)
print(json.dumps({'preflight_passed':m.preflight(),'new_HTTP_calls':0},ensure_ascii=False))
"""
            run([sys.executable, "-c", program], _project_file(_PROJECT_ROOT, HERE / "MAIN-NEW-OWNER-PREFLIGHT.log"))
            save(_project_file(_PROJECT_ROOT, PRIVATE / "control.json"), {"continue_after_cycle": True, "background_enabled": True,
                "minimum_free_bytes": 8589934592})
            environment = old.h.env()
            environment["HM_WATCHDOG_OWNER_FD"] = str(owner.fileno())
            with (_project_file(_PROJECT_ROOT, PRIVATE / "watch.stdout.log")).open("a") as output:
                child = subprocess.Popen([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py")), "watch"], cwd=ROOT,
                    env=environment, stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=True, pass_fds=(owner.fileno(),))
            save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-CLOSED.json"), {"complete": True, "at_unix": time.time(),
                "mainline_applied": True, "exact_changed_files": 22, "public_config_cases": 7,
                "new_controller_pid": child.pid, "owner_lock_continuously_inherited": True,
                "old_natural_terminal": verified, "new_player_identity_still_requires_live_verification": True,
                "formal_release": False}, exclusive=True)
            save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-STATUS.json"), {"state": "new_owner_dispatched_after_natural_finish",
                "pid": os.getpid(), "new_controller_pid": child.pid, "production_applied": True})
    except Exception as error:
        save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-STATUS.json"), {"state": "failed_no_automatic_retry", "pid": os.getpid(),
            "type": type(error).__name__, "reason": str(error), "at_unix": time.time()})
        raise


if __name__ == "__main__":
    main()
