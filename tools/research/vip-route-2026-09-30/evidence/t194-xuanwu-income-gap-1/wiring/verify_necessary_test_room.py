"""四席自然完赛后核原审计、下载官方十桌并对拍；不是算法强度重确认。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring/necessary-testroom-1')
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t194-s03-e2-necessary-testroom-1')


def load(path):
    """读取指定证据文件；私有配置不输出。"""
    return json.loads(path.read_text())


def pin(path):
    """原文件的完整字节SHA。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    """独占保存实际结果，失败不覆盖或自动重做。"""
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def module(name, path):
    """只复用既有读回与采集函数，不执行历史watch入口。"""
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    """验证全部十桌/二十单局，四视角去重；完整评分缺口如实保留。"""
    sys.path[:0] = [str(_project_file(_PROJECT_ROOT, ROOT / "src")), str(ROOT)]
    assert load(_project_file(_PROJECT_ROOT, OUT / "PLAYERS-TERMINAL.json"))["actual_exit_code"] == 0
    assert not (_project_file(_PROJECT_ROOT, OUT / "CLOSED.json")).exists()
    plan, release = load(_project_file(_PROJECT_ROOT, OUT / "PLAN.json")), load(_project_file(_PROJECT_ROOT, OUT / "RELEASE-SNAPSHOT.json"))
    old = _project_file(_PROJECT_ROOT, HERE.parents[1] / "t165-live-watchdog-1")
    h = module("t194_s03_e2_test_h", old / "watchdog.py")
    a = module("t194_s03_e2_test_a", old / "analyze.py")
    r = module("t194_s03_e2_test_raw", a.HELPER)
    session = _project_file(_PROJECT_ROOT, ROOT / plan["session"])
    r.BASE = session
    terminal = a.end_records(_project_file(_PROJECT_ROOT, OUT / "PLAYERS.log"), "mixed")
    assert {t["slot"] for t in terminal} == {"qinglong", "baihu", "zhuque", "xuanwu"}
    assert all(t["exit_code"] == 0 and t["outcome"] == "completed"
        and t["terminal_reason"] == "tournament_finished" for t in terminal)
    audit, sources = [], {}
    for t in terminal:
        assert not h.process_identity(load(_project_file(_PROJECT_ROOT, OUT / "PLAYERS-START.json"))["pid"], "run_test_room.py")["expected_command_live"]
        runs = list((session / "audit" / ("slot-" + t["slot"]) / "runs").glob("*"))
        assert len(runs) == 1 and runs[0].name == t["run_id"]
        run = runs[0]
        payload = load(run / "manifest.json")["payload"]
        assert payload["policy_version"] == plan["strategy"]
        assert payload["policy_release"]["release_package_id"] == plan["package_id"]
        assert payload["policy_release"]["source_sha256"] == release["source_sha256"]
        assert payload["sse_effective"] and not payload["discard_pacing_enabled"]
        assert payload["max_games"] == 10 and payload["rounds_per_game"] == 2
        compute = t["decision_compute"]
        assert compute["closed"] is True
        for key in ("active", "current", "live_processes", "owned", "pending", "ready",
                "transport_inflight", "transport_threads_alive", "late_reap_inflight",
                "late_reap_threads_alive", "bound_games", "releasing_games"):
            assert key in compute and compute[key] == 0, "计算资源未回收: " + key
        audit.append({"slot": t["slot"], **r.audit_run(run, sources)})
        sources[str((run / "manifest.json").relative_to(session))] = pin(run / "manifest.json")
        sources[str((run / "summary.json").relative_to(session))] = pin(run / "summary.json")
    # 已自然结束；与持续自由赛后台使用同一统计锁和低优先级。
    os.nice(15)
    priority = subprocess.run(["taskpolicy", "-b", "-p", str(os.getpid())], capture_output=True)
    assert priority.returncode == 0
    save(_project_file(_PROJECT_ROOT, OUT / "READBACK-START.json"), {"pid": os.getpid(), "source_sha256": sources,
        "players_naturally_closed": True, "cpu_nice": os.nice(0), "io_priority_actual_exit_code": priority.returncode})
    with (h.PRIVATE / "postprocess.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        h.capture(session, load(_project_file(_PROJECT_ROOT, PRIVATE / "room.json")), plan["room_id"], _project_file(_PROJECT_ROOT, OUT / "official-capture"))
        with (_project_file(_PROJECT_ROOT, OUT / "POSTGAME.log")).open("x") as stream:
            code = subprocess.run([sys.executable, "scripts/audit_tool.py", "postgame", plan["session"],
                "--rule-config", str(_project_file(_PROJECT_ROOT, PRIVATE / "rules.json"))], cwd=ROOT,
                stdout=stream, stderr=subprocess.STDOUT).returncode
        save(_project_file(_PROJECT_ROOT, OUT / "POSTGAME-TERMINAL.json"), {"actual_exit_code": code})
        assert code == 0
    tables, official_pins = a.official_tables(session)
    timeouts, counts = [], Counter()
    endings = 0
    for game, doc in tables.items():
        events = {}
        for block in doc["blocks"]:
            for event in block["events"]:
                seq = event["seq"]
                assert seq not in events or events[seq] == event
                events[seq] = event
        rounds = [e for e in events.values() if e["type"] == "round_ended"]
        assert {e["data"]["round_no"] for e in rounds} == {1, 2} and len(rounds) == 2
        assert len([e for e in events.values() if e["type"] == "game_ended"]) == 1
        endings += len(rounds)
        for event in events.values():
            counts[event["type"]] += 1
            if event["type"] == "timeout":
                timeouts.append({"game_id": game, "event": event})
    assert len(tables) == 10 and endings == 20
    latest = load(session / "latest-postgame.json")
    report = load(session / latest["job"] / "report.json")
    checks = report["official_rule_checks"]
    assert len(checks) == 10
    discard_timeouts = [x for x in timeouts if x["event"].get("data", {}).get("kind") == "discard"]
    conflicts = [x for c in checks for x in c.get("origin_conflicts", [])]
    finite_legal = all(not x["full_plan_legal_key_mismatches"] and not x["policy_errors"] for x in audit)
    passed = (not discard_timeouts and not conflicts and finite_legal and report["bundle_verified"] is True
        and report["audit_complete"] is True
        and all(x["http_started"] == x["http_finished"] and not x["actual_audit_summary"]["audit_degraded"] for x in audit)
        and all(c.get("final_scores_match") is True for c in checks)
        and all(t["decision_compute"]["faults"] == t["decision_compute"]["policy_failures"] == 0 for t in terminal))
    save(_project_file(_PROJECT_ROOT, OUT / "CLOSED.json"), {"complete": True, "engineering_gate_passed": passed,
        "room_id": plan["room_id"], "strategy": plan["strategy"], "package_id": plan["package_id"],
        "unique_tables": 10, "unique_hands": 20, "four_views_not_40_tables": True,
        "participant_terminals": terminal, "audit": audit, "source_sha256": sources,
        "official_table_sha256": official_pins, "official_event_counts": dict(counts),
        "official_timeouts": timeouts, "official_discard_timeouts": discard_timeouts,
        "rule_origin_conflicts": conflicts, "official_final_scores_match": [c.get("final_scores_match") for c in checks],
        "postgame_audit_complete": report["audit_complete"], "postgame_bundle_verified": report["bundle_verified"],
        "strict_full_score_gate": all(x["complete_plans"] == x["plans"] and x["inputs_without_plan_count"] == 0 for x in audit),
        "strength_or_official_tournament_admission": False, "no_renew": True})
    print({"engineering_gate_passed": passed, "unique_tables": 10, "unique_hands": 20,
        "actual_plans": sum(x["plans"] for x in audit), "actual_complete_plans": sum(x["complete_plans"] for x in audit),
        "discard_timeouts": len(discard_timeouts)})
    assert passed, "真实工程门未通过；原结果保留，不上线新owner"


if __name__ == "__main__":
    main()
