"""只读统计已自然结束的T157自由赛，不评分、不续打、不发送HTTP。

复用T155规范审计统计；官方响应超时只存数量，摸打超时保留逐事件证据。
一房十桌是观察性实战数据，没有同牌山R18对照，不能授因果增强。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t157-pruned-s02-experimental-free-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t157-vip-s02-free-v3")


def load(path):
    """读取本批次JSON，失败直接退出，不推断成功。"""
    return json.loads(path.read_text())


def main():
    """真实外层、运行及赛后入口都结束后，写唯一完整房汇总。"""
    assert load(_project_file(_PROJECT_ROOT, HERE / "ACTUAL-OUTER-TERMINAL.json"))["actual_exit_code"] == 1
    assert load(_project_file(_PROJECT_ROOT, HERE / "CAPTURE-RETRY-TOOL-TERMINAL.json"))["actual_exit_code"] == 0
    assert load(_project_file(_PROJECT_ROOT, HERE / "AUTO-MATCH-CHILD-TERMINAL.json"))["exit_code"] == 0
    assert load(_project_file(_PROJECT_ROOT, HERE / "POSTGAME-CHILD-TERMINAL.json"))["exit_code"] == 0
    helper = _project_file(_PROJECT_ROOT, HERE.parent / "t155-pruned-s02-engineering-testroom-1/summarize_closed.py")
    spec = importlib.util.spec_from_file_location("t155_closed_audit", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 只调整独立离线模块的原件根；不修改文件、生产代码或T155闭合数据。
    module.BASE = BASE
    runs = sorted(BASE.glob("audit/runs/*"))
    assert len(runs) == 1
    run = runs[0]
    sources = {}
    audit = module.audit_run(run, sources)
    owners = [p.name for p in (run / "participants").glob("u_*") if p.is_dir()]
    assert len(owners) == 1
    own = owners[0]
    terminals = [json.loads(line[len("RESULT "):]) for line in (_project_file(_PROJECT_ROOT, HERE / "FREE-STDOUT-STDERR.log")).read_text().splitlines()
                 if line.startswith("RESULT ")]
    assert len(terminals) == 1 and terminals[0]["run_id"] == run.name
    local_scores = {}
    for path in run.glob("participants/*/games/*.jsonl"):
        for line in path.open():
            record = json.loads(line)
            if record["kind"] == "game_finished" and record["payload"].get("final_scores") is not None:
                game = record["context"]["game_id"]
                scores = record["payload"]["final_scores"]
                if game in local_scores:
                    assert local_scores[game] == scores
                local_scores[game] = scores
    tables, timeout_counts, discard_timeouts, events_count = [], Counter(), [], Counter()
    all_wins, our_wins = Counter(), Counter()
    room = load(_project_file(_PROJECT_ROOT, HERE / "OFFICIAL-CAPTURE.json"))["room_id"]
    for path in sorted(BASE.glob("official/dl-*/events.json")):
        if not (path.parent / "source.json").exists() or (path.parent / "download-error.json").exists():
            continue
        body = load(path)
        assert body["room_id"] == room and body["status"] == "finished"
        sources[str(path.relative_to(BASE))] = hashlib.sha256(path.read_bytes()).hexdigest()
        seat = next(i for i, player in enumerate(body["seats"]) if player["user_id"] == own)
        events = {}
        for block in body["blocks"]:
            for event in block["events"]:
                if event["seq"] in events:
                    assert events[event["seq"]] == event
                events[event["seq"]] = event
        finals = [event["data"]["final_scores"] for event in events.values() if event["type"] == "game_ended"]
        assert len(finals) == 1 and finals[0] == local_scores[body["game_id"]]
        scores = finals[0]
        tables.append({"game_id": body["game_id"], "batch": body["batch"], "rounds": len(body["rounds"]),
                       "our_seat": seat, "scores_seat_order": scores, "our_score": scores[seat],
                       "rank_ties_shared": 1 + sum(score > scores[seat] for score in scores),
                       "opponents": [p for i, p in enumerate(body["seats"]) if i != seat]})
        for event in events.values():
            events_count[event["type"]] += 1
            if event["type"] == "timeout":
                timeout_counts[str(event.get("data", {}).get("kind"))] += 1
                if event.get("data", {}).get("kind") == "discard":
                    discard_timeouts.append({"game_id": body["game_id"], "is_ours": event["seat"] == seat,
                                             "event": event})
        for hand in body["rounds"]:
            if not hand["is_draw"]:
                all_wins[str(hand["multiplier"])] += 1
                if hand["winner"] == seat:
                    our_wins[str(hand["multiplier"])] += 1
    assert len(tables) == len(local_scores) == 10
    assert len({table["game_id"] for table in tables}) == 10
    assert sum(table["rounds"] for table in tables) == 80
    job = _project_file(_PROJECT_ROOT, BASE / load(BASE / "latest-postgame.json")["job"])
    postgame = load(job / "report.json")
    assert postgame["official_documents"] == 10
    checks = postgame["official_rule_checks"]
    assert len(checks) == 10
    summary = {"room_id": room, "package_id": load(_project_file(_PROJECT_ROOT, HERE / "ROOT-EXPERIMENTAL-START-DECISION.json"))["release_package_id"],
               "scope": "one_observational_free_match_room", "unique_tables": 10, "unique_hands": 80,
               "audit": audit, "participant_terminal_record": terminals[0], "all_tables": sorted(tables, key=lambda x: x["batch"]),
               "official_unique_event_counts": dict(events_count), "official_timeout_counts_by_kind": dict(timeout_counts),
               "official_discard_timeouts": discard_timeouts, "our_discard_timeouts": sum(x["is_ours"] for x in discard_timeouts),
               "our_total_score": sum(t["our_score"] for t in tables),
               "our_mean_score_per_table": statistics.mean(t["our_score"] for t in tables),
               "our_table_rank_counts": dict(Counter(str(t["rank_ties_shared"]) for t in tables)),
               "all_wins_by_official_multiplier": dict(all_wins), "our_wins_by_official_multiplier": dict(our_wins),
               "official_rule_statuses": dict(Counter(h["status"] for c in checks for h in c.get("rounds", []))),
               "official_summary_statuses": dict(Counter(h["status"] for c in checks for h in c.get("summary_comparisons", []))),
               "official_origin_conflicts": [x for c in checks for x in c.get("origin_conflicts", [])],
               "official_final_scores_match": [c.get("final_scores_match") for c in checks],
               "postgame_audit_complete": postgame["audit_complete"], "postgame_bundle_verified": postgame["bundle_verified"],
               "strict_full_plan_zero_fault_gate": (audit["plans"] == audit["complete_plans"] and
                   terminals[0]["decision_compute"]["faults"] == terminals[0]["decision_compute"]["policy_failures"] == 0),
               "causal_strength_admission": False, "formal_release": False,
               "interpretation": "单房无R18同牌山对照，成绩只作实战观察；对手不凭昵称分类强弱。指南429与对局状态／动作分开，他家摸打超时与我方分开。",
               "audit_counter_helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(), "source_sha256": sources}
    with (_project_file(_PROJECT_ROOT, HERE / "ROOM-AUDIT-SUMMARY.json")).open("x") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: summary[k] for k in ["room_id", "unique_tables", "unique_hands", "our_total_score",
                    "our_discard_timeouts", "official_rule_statuses", "strict_full_plan_zero_fault_gate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
