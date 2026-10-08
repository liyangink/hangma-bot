"""T155完整工程核验后的单房实验自由赛，不授正式赛事或相对R18增强信用。

默认只做本地准备检查；--execute才调用已授权全局Token的自由赛入口。
全局Token仅一个进程使用，根代理必须在实际启动前确认独占状态。
一房自然结束后下载全部十桌，再执行一次完整赛后入口；没有主动终止。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t155-pruned-s02-engineering-testroom-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t157-pruned-s02-experimental-free-1')
SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t157-vip-s02-free-v3")
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t157-vip-s02-free-v3')
TOKEN = _project_file(_PROJECT_ROOT, ROOT / "token/global/全局自由赛token")
PACKAGE = "cce8c84c5f6bd6128a9843a3407bf7bf0b09d118c667eaa2600c898b2dd0bd6f"


def write_new(path, body, *, private=False):
    """只写新制品；不覆盖失败或终态，私有配置0600，Token不复制进证据。"""
    with path.open("x") as stream:
        if private:
            os.fchmod(stream.fileno(), 0o600)
        json.dump(body, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def require_engineering():
    """验证本房实际计算／规则／超时结果，保留唯一无选择窗口的预算降级。"""
    summary = json.loads((_project_file(_PROJECT_ROOT, HERE / "ROOM-AUDIT-SUMMARY.json")).read_text())
    assert summary["unique_tables"] == 10 and summary["unique_hands"] == 80
    assert summary["postgame_audit_complete"] is True
    assert not summary["official_discard_timeouts"] and not summary["official_origin_conflicts"]
    assert all(x is True for x in summary["official_final_scores_match"])
    assert not set(summary["official_rule_statuses"]) - {"passed", "not_checked"}
    failures = []
    for slot in summary["all_slots"]:
        assert not slot["full_plan_legal_key_mismatches"] and slot["inputs_without_plan_count"] == 0
        assert set(slot["http_categories"]["state"]) == {"200"}
        assert set(slot["http_categories"]["action"]) == {"200"}
        failures.extend(slot["failed_plans"])
    assert len(failures) == 1
    failure = failures[0]
    assert failure["context"]["decision_id"] == "dec-5762f8ab4dd84dab9e40e119d8bb486d"
    assert failure["input"]["legal"] == ["pass"]
    assert failure["input"]["input_monotonic"] > failure["input"]["budget"]["fallback_deadline_monotonic"]
    for terminal in summary["participant_terminal_records"]:
        counts = terminal["decision_compute"]
        assert counts["closed"] is True
        for name in ("faults", "restarts", "policy_failures", "discarded", "rejected", "owned", "pending", "active",
                     "live_processes", "current", "transport_inflight", "transport_threads_alive",
                     "late_reap_inflight", "late_reap_threads_alive"):
            assert counts[name] == 0, (terminal["slot"], name)
        assert counts["submitted"] == counts["dispatched"] == counts["completed"]
    sys.path[:0] = [str(ROOT), str(_project_file(_PROJECT_ROOT, ROOT / "src"))]
    from hangma_bot.bootstrap import _load_vip_free_manifest
    manifest = _load_vip_free_manifest(PACKAGE)
    assert manifest["strength_admission"] is manifest["production_default"] is False
    return summary


def main():
    """实际执行只运行一房；保留真实子进程终态及所有官方采集结果。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    summary = require_engineering()
    if not args.execute:
        print(json.dumps({"prepared": True, "http_calls": 0, "rooms_started": 0, "strength_admission": False}))
        return
    assert OUT.exists() and not SESSION.exists() and not PRIVATE.exists()
    exclusive = json.loads((_project_file(_PROJECT_ROOT, OUT / "GLOBAL-TOKEN-EXCLUSIVITY.json")).read_text())
    assert exclusive["no_existing_auto_match_process"] is True
    assert TOKEN.is_file() and TOKEN.read_text().strip()
    PRIVATE.mkdir(mode=0o700)
    SESSION.mkdir(parents=True)
    config = json.loads((_project_file(_PROJECT_ROOT, ROOT / "configs/vip-s02-bounded-d1-v3.free-match.example.json")).read_text())
    config.pop("token_env")
    config["audit_root"] = str(_project_file(_PROJECT_ROOT, SESSION / "audit"))
    write_new(_project_file(_PROJECT_ROOT, PRIVATE / "run.json"), config, private=True)
    write_new(_project_file(_PROJECT_ROOT, PRIVATE / "rule-config.json"), {"base_score": 1, "you_cai_bi_kao": False}, private=True)
    from scripts.run_auto_match import load_config
    runtime, settings = load_config(_project_file(_PROJECT_ROOT, PRIVATE / "run.json"), token_file=str(TOKEN))
    assert runtime.expected_policy_release_id == PACKAGE and runtime.sse_enabled is True
    assert settings.declared_max_games == 10 and settings.declared_rounds == 8
    write_new(_project_file(_PROJECT_ROOT, OUT / "ROOT-EXPERIMENTAL-START-DECISION.json"), {
        "release_package_id": PACKAGE, "max_new_rooms": 1, "all_tables_natural_finish": True,
        "authorization": "用户持续授权候选测试房和实验自由赛；无需再次授权",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "t155_summary_sha256": hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / "ROOM-AUDIT-SUMMARY.json")).read_bytes()).hexdigest(),
        "strict_full_plan_zero_fault_gate": summary["strict_full_plan_zero_fault_gate"],
        "known_exception": "唯一无法评分窗口只有pass，输入到达时评分预算已过；完整保留，不授零降级",
        "engineering_eligible_for_one_experimental_room": True,
        "remaining_limits": ["未知补杠牌墙的规则复核仍有未检查分支", "T148独立强度确认未通过",
                             "本实验不能代替测试赛事完整生命周期门禁"],
        "strength_admission": False, "formal_release": False, "llm_author_calls": 0})
    runtime_env = dict(os.environ)
    for key in ("NO_PROXY", "no_proxy"):
        runtime_env[key] = ",".join(filter(None, (runtime_env.get(key, ""), "10.240.169.190")))
    result = subprocess.run([sys.executable, "scripts/run_auto_match.py", "--config", str(_project_file(_PROJECT_ROOT, PRIVATE / "run.json")),
                             "--token-file", str(TOKEN)], env=runtime_env)
    write_new(_project_file(_PROJECT_ROOT, OUT / "AUTO-MATCH-CHILD-TERMINAL.json"), {"exit_code": result.returncode,
                                                    "controller_sent_termination_signal": False})
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    runs = list(SESSION.glob("audit/runs/*"))
    assert len(runs) == 1 and (runs[0] / "summary.json").is_file()
    rooms = set()
    for path in runs[0].glob("participants/*/games/*.jsonl"):
        rooms.add(path.stem.split("_r", 1)[0])
    assert len(rooms) == 1 and next(iter(rooms)).startswith("a_")
    room = next(iter(rooms))
    from hangma_bot.bootstrap import build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    captures = []
    with build_public_archive_client(config) as client:
        for batch in range(10):
            # T155补采第三桌的指南GET触发429；既有4次请求间隔不足以
            # 保证跨桌指南额度。只在完赛后的公开采集增加间隔，不改变线上圈速。
            time.sleep(2)
            captures.append(collect_test_room(client, room, batch, SESSION))
    write_new(_project_file(_PROJECT_ROOT, OUT / "OFFICIAL-CAPTURE.json"), {"room_id": room, "ten_tables": captures})
    postgame = subprocess.run([sys.executable, "scripts/audit_tool.py", "postgame", str(SESSION),
                              "--rule-config", str(_project_file(_PROJECT_ROOT, PRIVATE / "rule-config.json"))], env=runtime_env)
    write_new(_project_file(_PROJECT_ROOT, OUT / "POSTGAME-CHILD-TERMINAL.json"), {"exit_code": postgame.returncode})
    raise SystemExit(postgame.returncode)


if __name__ == "__main__":
    main()
