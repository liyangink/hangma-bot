"""补两个未用于T184的自然完赛房：每桌前两次本人摸牌窗，不按成绩筛选。"""

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
import hashlib
import json
from pathlib import Path

from common import HERE, ROOT, pin, save


def main():
    """先冻结读取范围，再读最多40MiB审计前缀；不全扫大型审计。"""
    live = _project_file(_PROJECT_ROOT, HERE.parent / "t179-production-wiring-1")
    inputs, games = [], []
    for number in (25, 26):
        batch = live / f"batch-{number:03d}"
        start = json.loads((batch / "FREE-START.json").read_text())
        close = json.loads((batch / "RUN-CLOSED.json").read_text())
        assert close["continuation_safety_verified"] and len(close["free"]["game_finished"]) == close["free"]["unique_tables"] == 10
        session = _project_file(_PROJECT_ROOT, ROOT / start["session"])
        manifests = list((session / "audit/runs").glob("*/manifest.json"))
        assert len(manifests) == 1
        manifest = manifests[0]
        assert pin(manifest)["sha256"] == close["free"]["manifest_sha256"]
        game_files = sorted(manifest.parent.glob("participants/*/games/*.jsonl"))
        assert len(game_files) == 10
        inputs += [batch / "FREE-START.json", batch / "RUN-CLOSED.json", manifest]
        games += [{"batch": number, "room_id": close["free"]["room_id"], "path": str(path)} for path in game_files]
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-EXTRACTION-PLAN.json"), {"files": {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), *inputs]},
        "games": games, "selection": "每个已自然结束完整桌原顺序前两个不同window_key的本人draw输入；不看终局或胡型",
        "planned_windows": 40, "maximum_bytes_per_game": 2097152,
        "score_or_ending_used_to_select": False, "new_worlds_tables_calls": 0,
        "cluster": "2个房，不把40窗当40独立样本", "preparation_no_original_draw_scores_read_yet": True})
    cases, prefixes = [], []
    raw_selected = []
    for game in games:
        path = Path(game["path"])
        selected, keys, matched = [], set(), {}
        prefix = bytearray()
        with path.open("rb") as stream:
            while len(prefix) < 2097152:
                line = stream.readline(2097152 - len(prefix) + 1)
                if not line or len(prefix) + len(line) > 2097152:
                    break
                prefix.extend(line)
                record = json.loads(line)
                payload = record.get("payload", {})
                if record["kind"] == "decision_input":
                    request = payload["request"]
                    key = tuple(sorted(request["window_key"].items()))
                    if request["window_key"]["phase"] == "draw" and key not in keys and len(selected) < 2:
                        selected.append(record)
                        keys.add(key)
                        raw_selected.append(record)
                elif record["kind"] == "decision_planned":
                    for source in selected:
                        if payload["trigger_seq"] == source["payload"]["request"]["trigger_seq"] and payload["plan_revision"] == source["payload"]["plan_revision"]:
                            matched[source["payload"]["request"]["decision_id"]] = record
                            raw_selected.append(record)
                if len(selected) == 2 and len(matched) == 2:
                    break
        assert len(selected) == 2 and len(matched) == 2, f"固定审计前缀不足两窗：{path.name}"
        with path.open("rb") as stream:
            assert stream.read(len(prefix)) == bytes(prefix), "原审计前缀读取期间改变"
        prefixes.append({"path": str(path), "bytes": len(prefix), "sha256": hashlib.sha256(prefix).hexdigest(),
                         "scanned_whole_file": False, "prefix_stable": True})
        for index, record in enumerate(selected):
            request = record["payload"]["request"]
            plan = matched[request["decision_id"]]["payload"]
            assert not plan["filter_reasons"] and not plan["degraded_reasons"], "固定窗口原评分有缺口，必须显式处理不能换题"
            entries = plan["returned_plan"]["candidates"]
            assert entries and all(type(e["total_score"]) in (int, float) for e in entries)
            hand = request["observation"]["my_hand"]
            whites = sum(t == "白" or isinstance(t, dict) and t.get("code") == "白" for t in hand)
            cases.append({"label": f"new-official:{game['batch']}:{path.stem}:{index + 1}", "root_id": game["room_id"],
                "scope": "additional_public_development_not_independent_confirmation", "classes": [f"first_two_draws_white_{whites}"],
                "observation": request["observation"], "window_key": request["window_key"],
                "legal_action_keys": sorted(e["action_key"] for e in entries), "expected_parent_view_sha256": None,
                "expected_actual_parent_entries": [{"action_key": e["action_key"], "score": e["total_score"]} for e in entries]})
    assert len(cases) == 40
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-CASES.json"), {"cases": cases, "all_selected_denominator": 40, "room_sources": 2,
        "prefixes": prefixes, "raw_selected_record_count": len(raw_selected), "ending_labels_included": False})
    # 新脚本以完全相同的typed构图/计费/精确原分核对跑固定40窗，旧95窗与失败均不覆盖。
    program = (_project_file(_PROJECT_ROOT, HERE / "compare_prototypes_v2.py")).read_text()
    replacements = [("PLAN.json", "SUPPLEMENT-PLAN.json"), ("CASES.json", "SUPPLEMENT-CASES.json"),
        ('out = HERE / "mechanism-comparison-v2"', 'out = HERE / "mechanism-comparison-supplement"'),
        ('"planned_views": 95, "planned_actual_scores": 760', '"planned_views": 40, "planned_actual_scores": 320'),
        ('len(rows) == 95', 'len(rows) == 40')]
    for before, after in replacements:
        assert program.count(before) == 1
        program = program.replace(before, after, 1)
    with (_project_file(_PROJECT_ROOT, HERE / "compare_official_supplement.py")).open("x") as stream:
        stream.write(program)
    original = json.loads((_project_file(_PROJECT_ROOT, HERE / "PLAN.json")).read_text())
    files = [_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-EXTRACTION-PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-CASES.json"),
        _project_file(_PROJECT_ROOT, HERE / "compare_official_supplement.py"), _project_file(_PROJECT_ROOT, HERE / "compare_prototypes_v2.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "common.py"), Path(__file__)]
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-PLAN.json"), {"schema": "t185-additional-public-window-plan/1",
        "files": {str(p): pin(p) for p in files}, "source_manifest": original["source_manifest"],
        "first_prototypes": original["first_prototypes"], "planned_windows": 40,
        "room_sources": 2, "new_actual_scores_planned": 320,
        "score_ending_or_highfan_used_to_select": False, "first_author_already_received_this_panel": False})
    print({"prepared": True, "windows": 40, "rooms": 2, "audit_prefix_bytes_read": sum(p["bytes"] for p in prefixes)}, flush=True)


if __name__ == "__main__":
    main()
