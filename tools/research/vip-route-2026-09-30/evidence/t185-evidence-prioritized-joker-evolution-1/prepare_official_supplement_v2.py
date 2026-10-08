"""从决策流提取两房40个早期窗口；每场状态流没有决策，原错误保留。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ctypes
import hashlib
import json
import os
from pathlib import Path

from common import HERE, ROOT, canonical, pin, save


def main():
    """固定前16MiB与每桌前两摸，不读取桌赛终分来筛窗口。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    live = _project_file(_PROJECT_ROOT, HERE.parent / "t179-production-wiring-1")
    inputs, rooms = [], []
    for number in (25, 26):
        batch = live / f"batch-{number:03d}"
        start = json.loads((batch / "FREE-START.json").read_text())
        close = json.loads((batch / "RUN-CLOSED.json").read_text())
        assert close["continuation_safety_verified"] and len(close["free"]["game_finished"]) == close["free"]["unique_tables"] == 10
        manifests = list((_project_file(_PROJECT_ROOT, ROOT / start["session"] / "audit/runs")).glob("*/manifest.json"))
        assert len(manifests) == 1
        manifest = manifests[0]
        assert pin(manifest)["sha256"] == close["free"]["manifest_sha256"]
        paths = sorted(manifest.parent.glob("participants/*/decisions.jsonl"))
        # unknown是认证/匹配控制身份，不是实际十桌参赛者的决策。
        paths = [p for p in paths if p.parent.name != "unknown"]
        assert len(paths) == 1
        rooms.append({"batch": number, "room_id": close["free"]["room_id"], "path": str(paths[0]),
                      "game_ids": sorted(g["game_id"] for g in close["free"]["game_finished"])})
        inputs += [batch / "FREE-START.json", batch / "RUN-CLOSED.json", manifest]
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-EXTRACTION-PLAN-V2.json"), {"files": {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), *inputs]},
        "rooms": rooms, "selection": "每个已闭合桌原顺序前两次不同window_key的本人draw；不看终局或胡型",
        "planned_windows": 40, "maximum_decisions_prefix_bytes_per_room": 16777216,
        "score_or_ending_used_to_select": False, "room_clusters": 2, "first_author_received_this": False,
        "original_wrong_stream_failure": pin(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-EXTRACTION-FIRST-FAILED.json"))})
    cases, prefixes, selected_raw = [], [], []
    for room in rooms:
        path = Path(room["path"])
        with path.open("rb") as stream:
            raw = stream.read(16777216)
        raw = raw[:raw.rfind(b"\n") + 1]
        with path.open("rb") as stream:
            assert stream.read(len(raw)) == raw
        prefixes.append({"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "prefix_stable": True})
        selected = {g: [] for g in room["game_ids"]}
        keys, planned = set(), {}
        for line in raw.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            payload = record.get("payload", {})
            if record["kind"] == "decision_input":
                request = payload["request"]
                game = request["observation"]["game_id"]
                key = canonical(request["window_key"])
                if game in selected and request["window_key"]["phase"] == "draw" and key not in keys and len(selected[game]) < 2:
                    selected[game].append(record)
                    keys.add(key)
            elif record["kind"] == "decision_planned":
                game = record["context"].get("game_id")
                if game in selected:
                    for source in selected[game]:
                        q = source["payload"]
                        if payload["trigger_seq"] == q["request"]["trigger_seq"] and payload["plan_revision"] == q["plan_revision"]:
                            planned[q["request"]["decision_id"]] = record
            if all(len(v) == 2 for v in selected.values()) and len(planned) == 20:
                break
        assert all(len(v) == 2 for v in selected.values()) and len(planned) == 20, "固定16MiB决策前缀不足40窗，保留失败不得换有利题"
        for game in room["game_ids"]:
            for index, record in enumerate(selected[game]):
                request = record["payload"]["request"]
                plan_record = planned[request["decision_id"]]
                plan = plan_record["payload"]
                assert not plan["filter_reasons"] and not plan["degraded_reasons"], "原评分有缺口，不可换题"
                entries = plan["returned_plan"]["candidates"]
                assert entries and all(type(e["total_score"]) in (int, float) for e in entries)
                whites = request["observation"]["my_hand"].count("白")
                cases.append({"label": f"new-official:{room['batch']}:{game}:{index + 1}", "root_id": room["room_id"],
                    "scope": "additional_public_development_not_confirmation", "classes": [f"first_two_draws_white_{whites}"],
                    "observation": request["observation"], "window_key": request["window_key"],
                    "legal_action_keys": sorted(e["action_key"] for e in entries), "expected_parent_view_sha256": None,
                    "expected_actual_parent_entries": [{"action_key": e["action_key"], "score": e["total_score"]} for e in entries]})
                selected_raw += [record, plan_record]
    assert len(cases) == 40
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-CASES.json"), {"cases": cases, "all_selected_denominator": 40, "room_sources": 2, "prefixes": prefixes,
        "raw_selected_record_count": len(selected_raw), "ending_labels_included": False})
    with (_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-ORIGINAL-AUDIT.jsonl")).open("x") as stream:
        for record in selected_raw:
            stream.write(canonical(record).decode() + "\n")
    program = (_project_file(_PROJECT_ROOT, HERE / "compare_prototypes_v2.py")).read_text()
    for before, after in [("PLAN.json", "SUPPLEMENT-PLAN.json"), ("CASES.json", "SUPPLEMENT-CASES.json"),
        ('out = HERE / "mechanism-comparison-v2"', 'out = HERE / "mechanism-comparison-supplement"'),
        ('"planned_views": 95, "planned_actual_scores": 760', '"planned_views": 40, "planned_actual_scores": 320'), ('len(rows) == 95', 'len(rows) == 40')]:
        assert program.count(before) == 1
        program = program.replace(before, after, 1)
    with (_project_file(_PROJECT_ROOT, HERE / "compare_official_supplement.py")).open("x") as stream:
        stream.write(program)
    old = json.loads((_project_file(_PROJECT_ROOT, HERE / "PLAN.json")).read_text())
    files = [_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-EXTRACTION-PLAN-V2.json"), _project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-CASES.json"), _project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-ORIGINAL-AUDIT.jsonl"),
        _project_file(_PROJECT_ROOT, HERE / "compare_official_supplement.py"), _project_file(_PROJECT_ROOT, HERE / "compare_prototypes_v2.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "common.py"), Path(__file__)]
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-PLAN.json"), {"schema": "t185-additional-public-window-plan/1", "files": {str(p): pin(p) for p in files},
        "source_manifest": old["source_manifest"], "first_prototypes": old["first_prototypes"], "planned_windows": 40,
        "room_sources": 2, "new_actual_scores_planned": 320, "score_ending_or_highfan_used_to_select": False,
        "first_author_already_received_this_panel": False})
    print({"prepared": True, "windows": 40, "rooms": 2, "decisions_prefix_bytes": sum(p["bytes"] for p in prefixes)}, flush=True)


if __name__ == "__main__":
    main()
