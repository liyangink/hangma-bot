"""四席自然闭合后机械分账；原件只读，160单局按唯一桌去重，不测算法强度。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t227-rf1-default-and-live-1'

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
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
WORK = _project_file(_PROJECT_ROOT, '.private/t227-rf1-default-and-live-1')
SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t227-rf1-stress-10x16-r1")


def read(path):
    """读指定非凭据JSON；未知原件不伪造。"""
    return json.loads(Path(path).read_bytes())


def pin(path):
    """完整文件字节摘要，原始牌谱不入Git。"""
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def load_module(name, path):
    """只复用原审查过的解析函数，不执行其旧main或网络入口。"""
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def main(output: Path):
    """必须四席关闭、10份官方牌谱和外层自然终态齐；缺件拒绝，不重跑玩家。"""
    if output.exists():
        raise FileExistsError("原件已存在，不覆盖或自动重做")
    runs = sorted((_project_file(_PROJECT_ROOT, SESSION / "audit")).glob("slot-*/runs/*"))
    assert len(runs) == 4 and all((r / "summary.json").is_file() for r in runs), "四席未自然闭合"
    assert read(_project_file(_PROJECT_ROOT, WORK / "TESTROOM-OUTER-TERMINAL.json"))["exit_code"] == 0, "外层非正常自然终态"
    campaign = read(_project_file(_PROJECT_ROOT, ROOT / "runs/t227-rf1-stress-10x16/campaign.json"))
    assert campaign["m"] == 10 and campaign["rounds"] == 16
    helper_path = _project_file(_PROJECT_ROOT, ROOT / "review/vip-route-2026-09-30/evidence/t163-received-fix-fast-four-seat-testroom-1/summarize_closed.py")
    original = load_module("_t227_audit_readback", helper_path)
    original.BASE = SESSION
    spec = read(_project_file(_PROJECT_ROOT, WORK / "RUNTIME-SPEC-003.json"))
    scan_source = Path(spec["release_root"]) / 'tools/offline/free_match/rf1_controller.py'
    parser = load_module("_t227_actual_light_scan", scan_source)
    sources = {}
    audit, light, errors = [], [], []
    started = time.monotonic()
    # 全决策解析低优先级，并和自由赛后台共享锁；不得让在线等待它。
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for run in runs:
            try:
                audit.append(original.audit_run(run, sources))
            except Exception as error:
                errors.append({"run_id": run.name, "phase": "full_decision_readback", "type": type(error).__name__, "error": str(error)})
            light.append({"run_id": run.name, **parser.original.scan_lightweight(run,
                max_bytes=1073741824, max_seconds=30.0,
                phase_index_max_bytes=17179869184, phase_index_max_seconds=60.0)})
    terminals = []
    current = None
    for line in (_project_file(_PROJECT_ROOT, WORK / "TESTROOM-PLAYER.stdout.log")).read_text().splitlines():
        match = re.match(r"\[([^]]+)\] (\w+) \| 终态: ([^|]+)\| .*exit=(-?\d+)$", line)
        if match:
            current = {"slot": match[1], "outcome": match[2], "reason": match[3].strip(), "exit_code": int(match[4])}
            terminals.append(current)
        elif current is not None and line.strip().startswith("run_id:"):
            current["run_id"] = line.split(":", 1)[1].strip()
        elif current is not None and "计算服务退出:" in line:
            current["compute"] = json.loads(line[line.index("{"):])
    resource_keys = parser.gate.RESOURCE_COUNTS
    natural = (len(terminals) == 4 and {t.get("run_id") for t in terminals} == {r.name for r in runs}
        and all(t["exit_code"] == 0 and t["outcome"] == "completed" and t["reason"] == "tournament_finished" for t in terminals))
    reclaimed = natural and all(t.get("compute", {}).get("closed") is True
        and all(type(t["compute"].get(k)) is int and t["compute"][k] == 0 for k in resource_keys) for t in terminals)
    manifests = []
    for run in runs:
        j = read(run / "manifest.json")["payload"]
        manifests.append({"run_id": run.name, "strategy": j["policy_version"], "release_id": j["policy_release"]["release_package_id"],
            "M": j["max_games"], "Rounds": j["rounds_per_game"], "SSE": j["sse_effective"]})
    identity = all(m["strategy"] == "vip_g37_rf1_testroom_v1"
        and m["release_id"] == "7663bef2d2d1c2a1d17e7081334244eb6072f634ae0934bf365ee0443bdd4033"
        and m["M"] == 10 and m["Rounds"] == 16 and m["SSE"] is True for m in manifests)
    tables, timeouts, events_count, round_count = {}, {}, Counter(), 0
    for path in sorted((_project_file(_PROJECT_ROOT, SESSION / "official")).glob("dl-*/events.json")):
        if (path.parent / "download-error.json").exists() or not (path.parent / "source.json").is_file():
            continue
        doc = read(path)
        assert doc["room_id"] == campaign["room_id"] and doc["status"] == "finished"
        gid = doc["game_id"]
        if gid in tables:
            assert tables[gid]["pin"] == pin(path), "同桌官方原件冲突"
            continue
        events = {}
        for block in doc["blocks"]:
            for event in block["events"]:
                if event["seq"] in events:
                    assert events[event["seq"]] == event, "同seq事件冲突"
                events[event["seq"]] = event
        ended = [e for e in events.values() if e["type"] == "game_ended"]
        assert len(ended) == 1
        scores = ended[0]["data"]["final_scores"]
        assert len(scores) == 4 and all(type(x) is int for x in scores) and sum(scores) == 0
        hands = len(doc["rounds"])
        assert hands == 16
        tables[gid] = {"rounds": hands, "final_scores_seat_order_0_3": scores, "pin": pin(path)}
        round_count += hands
        for event in events.values():
            events_count[event["type"]] += 1
            if event["type"] == "timeout":
                timeouts[gid, event["seq"]] = {"game_id": gid, "event": event}
    complete_tables = len(tables) == 10 and round_count == 160
    discard = [t for t in timeouts.values() if t["event"].get("data", {}).get("kind") == "discard"]
    known_light = all(x.get("scan_complete") is True and all(type(x.get(k)) is int for k in
        ["real_new_missed_actions", "illegal_submissions", "unrecovered_state"]) for x in light)
    violations = {"timeouts": len(discard), "illegal_submissions": sum(x.get("illegal_submissions", 0) or 0 for x in light),
                  "unrecovered_state": sum(x.get("unrecovered_state", 0) or 0 for x in light),
                  "compute_faults": sum(t.get("compute", {}).get("faults", 0) for t in terminals),
                  "policy_failures": sum(t.get("compute", {}).get("policy_failures", 0) for t in terminals)}
    score_errors = sum(len(x["policy_errors"]) + len(x["full_plan_legal_key_mismatches"]) for x in audit)
    complete = natural and reclaimed and identity and complete_tables and known_light and not errors
    passed = complete and not any(violations.values()) and score_errors == 0
    result = {"schema": "t227-RF1-stress-readback/1", "complete": complete, "mechanical_passed_for_covered_room": passed,
        "room_id": campaign["room_id"], "unique_tables": len(tables), "unique_hands": round_count,
        "not_four_independent_copies": True, "natural_four_terminal": natural, "resources_reclaimed": reclaimed,
        "identity_exact": identity, "audit": audit, "light": light, "terminals": terminals, "manifests": manifests,
        "tables": tables, "official_events": dict(events_count), "official_timeouts": list(timeouts.values()),
        "discard_timeouts": discard, "mechanical_violations": violations, "score_errors": score_errors,
        "errors": errors, "total_plans": sum(x["plans"] for x in audit),
        "full_plans": sum(x["complete_plans"] for x in audit), "input_without_plan": sum(x["inputs_without_plan_count"] for x in audit),
        "new_HTTP": 0, "new_scores": 0, "new_players": 0, "causal_strength_admission": False,
        "source_sha256": sources, "original_helper_pin": pin(helper_path), "actual_scanner_source_pin": pin(scan_source),
        "elapsed_monotonic_seconds": time.monotonic()-started}
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ["complete", "mechanical_passed_for_covered_room", "unique_tables", "unique_hands", "mechanical_violations", "score_errors", "errors", "total_plans", "full_plans"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
