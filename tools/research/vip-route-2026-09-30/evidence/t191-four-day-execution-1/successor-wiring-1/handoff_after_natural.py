"""S02到S03一次自然交接：先实际测试房通过，后在同Token锁内换精确接线。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

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
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1')
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t191-s03-free-watchdog')
WORK = _project_file(_PROJECT_ROOT, '.private/t191-successor-wiring/workspace')


def load(path):
    """读取指定控制/公共证据，不输出凭证。"""
    return json.loads(path.read_text())


def pin(path):
    """完整文件字节身份。"""
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value, *, exclusive=False):
    """原结果独占保存；状态原子更新。时间单位Unix秒，仅用于关联。"""
    body = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x") as stream:
            stream.write(body)
    else:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(body)
        temporary.replace(path)


def main():
    """没有玩家terminate路径；复用原关闭验证与共享锁，未知失败不自动重试。"""
    spec = importlib.util.spec_from_file_location("t191_s03_predecessor", _project_file(_PROJECT_ROOT, OLD / "free_watchdog.py"))
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    review = load(_project_file(_PROJECT_ROOT, HERE / "ROOT-REVIEW.json"))
    assert review["main_application_approved_after_testroom_and_predecessor_natural_finish"]
    assert pin(_project_file(_PROJECT_ROOT, HERE / "CHANGESET.json")) == review["changeset_pin"]
    assert pin(_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py")) == review["successor_watchdog_pin"]
    room = load(_project_file(_PROJECT_ROOT, HERE / "necessary-testroom-1/CLOSED.json"))
    assert room["complete"] and room["engineering_gate_passed"]
    assert room["unique_tables"] == 10 and room["unique_hands"] == 20
    assert load(_project_file(_PROJECT_ROOT, HERE / "necessary-testroom-1/PLAYERS-TERMINAL.json"))["actual_exit_code"] == 0
    changeset = load(_project_file(_PROJECT_ROOT, HERE / "CHANGESET.json"))
    for relative, expected in changeset["mandatory_gates"].items():
        assert pin(_project_file(_PROJECT_ROOT, HERE / relative)) == expected
    for row in changeset["files"]:
        path = _project_file(_PROJECT_ROOT, ROOT / row["path"])
        assert pin(_project_file(_PROJECT_ROOT, WORK / row["path"])) == row["after"]
        assert (pin(path) if path.exists() else None) == row["before"]
    old.preflight()
    state = load(_project_file(_PROJECT_ROOT, OLD / "STATUS.json"))
    assert old.h.process_identity(state["controller_pid"], str(_project_file(_PROJECT_ROOT, OLD / "free_watchdog.py")) + " watch")["expected_command_live"]
    PRIVATE.mkdir(mode=0o700, exist_ok=False)
    save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-START.json"), {"pid": os.getpid(), "at_unix": time.time(),
        "changeset_pin": pin(_project_file(_PROJECT_ROOT, HERE / "CHANGESET.json")), "players_natural_only": True}, exclusive=True)
    control = load(old.CONTROL)
    save(_project_file(_PROJECT_ROOT, HERE / "PREDECESSOR-CONTROL-BEFORE.json"), control, exclusive=True)
    # 只停止下一房创建；原玩家wait、原关闭核验和全部终态继续完成。
    old.h.write(old.CONTROL, {**control, "continue_after_cycle": False})
    try:
        with old.OWNER_LOCK.open("a+") as owner:
            while True:
                try:
                    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-STATUS.json"), {"state": "waiting_predecessor_natural_finish",
                        "pid": os.getpid(), "at_unix": time.time(), "main_applied": False})
                    time.sleep(2)
            state = load(_project_file(_PROJECT_ROOT, OLD / "STATUS.json"))
            assert state["state"] == "stopped_after_natural_finish" and not state["active_children"]
            assert not old.h.other_players(), "真实玩家未全部自然结束，禁止修改主线"
            predecessor = max(OLD.glob("batch-*"), key=lambda d: load(d / "PLAN.json")["batch"])
            verified = old.verify_free(predecessor, load(predecessor / "PLAN.json"))
            assert load(predecessor / "RUN-CLOSED.json")["continuation_safety_verified"]
            # 只禁旧后台的下一项；当前统计自然完成，绝不能让它挡新自由赛。
            old.h.write(old.CONTROL, {**load(old.CONTROL), "background_enabled": False})
            save(_project_file(_PROJECT_ROOT, HERE / "PREDECESSOR-BACKGROUND-HANDOFF.json"), {
                "old_background_next_job_disabled": True, "current_job_natural_finish": True,
                "new_match_does_not_wait_for_postprocess_lock": True,
                "only_unstarted_jobs_adopted_by_new_worker": True,
                "player_or_worker_signal_sent": False}, exclusive=True)
            for row in changeset["files"]:
                target, source = _project_file(_PROJECT_ROOT, ROOT / row["path"]), _project_file(_PROJECT_ROOT, WORK / row["path"])
                assert (pin(target) if target.exists() else None) == row["before"]
                assert pin(source) == row["after"]
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".t191-s03-apply")
                with temporary.open("xb") as stream:
                    stream.write(source.read_bytes())
                temporary.replace(target)
                assert pin(target) == row["after"]
            save(_project_file(_PROJECT_ROOT, HERE / "MAIN-APPLIED.json"), {"complete": True, "changed_files": changeset["files"],
                "source_manifest": changeset["runtime_source_manifest"], "at_unix": time.time()}, exclusive=True)
            save(_project_file(_PROJECT_ROOT, HERE / "TRANSFER.json"), {"directory": str(predecessor.relative_to(ROOT)),
                "predecessor_run_closed_pin": pin(predecessor / "RUN-CLOSED.json"),
                "predecessor_natural_terminal": verified, "only_unstarted_postprocess_adopted": True}, exclusive=True)
            program = """
import importlib.util,json
from pathlib import Path
from hangma_bot import bootstrap as b
p=Path('review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1')
c=json.loads((p/'CHANGESET.json').read_text())
assert b._vip_runtime_sources()==c['runtime_source_manifest']
rows=json.loads((p/'PACKAGES-CLOSED.json').read_text())['rows']
for r in rows:
 m=b._load_vip_manifest(r['strategy'],r['package_id'])
 assert m['allowed_modes']==[r['mode']]
s=importlib.util.spec_from_file_location('t191_s03_new_watch',p/'free_watchdog.py')
w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
w.h.write(p/'START-APPROVAL.json',{'approved':True,'formal_release':False,'strength_admission':False,
 'identity':w.identity(),'driver_sha256':w.hashes(),
 'authorization':'用户授权候选接线、持续自由赛；ROOT精确审核及实际测试房通过后自然交接。'},exclusive=True)
assert w.preflight()==w.identity()
w.h.write(p/'MAIN-PREFLIGHT-CLOSED.json',{'complete':True,'verified_packages':len(rows),
 'source_manifest':b._vip_runtime_sources(),'actual_scoring_HTTP_workers':0},exclusive=True)
print({'verified_packages':len(rows),'HTTP_calls':0,'scoring_calls':0})
"""
            with (_project_file(_PROJECT_ROOT, HERE / "MAIN-PREFLIGHT.log")).open("x") as stream:
                result = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                    stdout=stream, stderr=subprocess.STDOUT)
            assert result.returncode == 0, "主线实际八包装配失败；不启动第二owner"
            save(_project_file(_PROJECT_ROOT, PRIVATE / "control.json"), {"continue_after_cycle": True, "background_enabled": True,
                "minimum_free_bytes": 8589934592})
            environment = old.h.env()
            environment["HM_WATCHDOG_OWNER_FD"] = str(owner.fileno())
            with (_project_file(_PROJECT_ROOT, PRIVATE / "watch.stdout.log")).open("a") as stream:
                child = subprocess.Popen([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py")), "watch"], cwd=ROOT,
                    env=environment, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                    pass_fds=(owner.fileno(),))
            save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-CLOSED.json"), {"complete": True, "main_applied": True,
                "new_controller_pid": child.pid, "owner_lock_continuously_inherited": True,
                "old_free_naturally_complete": verified, "new_player_live_verification_pending": True,
                "formal_tournament_field_admission": False, "at_unix": time.time()}, exclusive=True)
            save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-STATUS.json"), {"state": "successor_dispatched", "main_applied": True,
                "new_controller_pid": child.pid, "pid": os.getpid()})
    except Exception as error:
        save(_project_file(_PROJECT_ROOT, HERE / "HANDOFF-STATUS.json"), {"state": "failed_no_automatic_retry", "pid": os.getpid(),
            "type": type(error).__name__, "reason": str(error), "at_unix": time.time()})
        raise


if __name__ == "__main__":
    main()
