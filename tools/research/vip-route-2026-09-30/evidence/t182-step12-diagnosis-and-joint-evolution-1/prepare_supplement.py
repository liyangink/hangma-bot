"""首机会未产生行为分歧后，冻结同源后续机会补层；不按结局或差分选题。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import json
from pathlib import Path
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main():
    """每来源追加最多两可胡、两多白、两后期无白窗；同源不增独立来源。"""
    base = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json")).read_text())
    assert base["complete"]
    known = {json.dumps(c["window_key"], sort_keys=True) for c in base["cases"]}
    files = {str(_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json")): pin(_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json"))}
    diagnostic = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())
    cases = []
    read_bytes = 0
    for index, root in enumerate(diagnostic["roots"], 1):
        source = _project_file(_PROJECT_ROOT, HERE / "diagnostic-sources" / f"root-{index:03d}")
        closure = json.loads((source / "CLOSURE.json").read_text())
        assert closure["complete"]
        files[str(source / "CLOSURE.json")] = pin(source / "CLOSURE.json")
        files[str(source / "decisions.jsonl.gz")] = pin(source / "decisions.jsonl.gz")
        selected = {"later_current_hu": 0, "later_multi_white": 0, "later_no_white": 0}
        with gzip.open(source / "decisions.jsonl.gz", "rt") as stream:
            for line in stream:
                read_bytes += len(line.encode())
                assert read_bytes <= 32 * 1024 * 1024
                row = json.loads(line)
                assert row["status"] == "complete"
                key = json.dumps(row["window_key"], sort_keys=True)
                if key in known or row["window_key"]["phase"] != "draw":
                    continue
                tags = []
                if "hu" in row["legal_action_keys"]:
                    tags.append("later_current_hu")
                if row["white_count_current"] >= 2:
                    tags.append("later_multi_white")
                if row["white_count_current"] == 0 and row["own_draw_ordinal"] >= 4:
                    tags.append("later_no_white")
                chosen = [t for t in tags if selected[t] < 2]
                if not chosen:
                    continue
                for t in chosen:
                    selected[t] += 1
                known.add(key)
                cases.append({"label": f"supplement:{index:03d}:{sum(selected.values()):02d}",
                    "root_id": root["root_id"], "scope": "same_source_later_opportunity_development_supplement",
                    "observation": row["observation"], "window_key": row["window_key"],
                    "legal_action_keys": row["legal_action_keys"], "classes": chosen,
                    "expected_parent_view_sha256": None, "expected_actual_parent_entries": row["scores"],
                    "source_closure": str((source / "CLOSURE.json").relative_to(ROOT))})
        print({"root": index, "selected_class_windows": selected}, flush=True)
    assert len(cases) <= 48 and len(cases) + len(base["cases"]) <= 128
    save(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-PANEL.json"), {"cases": cases, "files": files, "read_bytes": read_bytes,
        "independent_sources_added": 0, "selection": "按行动前公开类别及时间顺序，每层最多两窗；不读取终分，不按原型得分/结局选题"})
    original = (_project_file(_PROJECT_ROOT, HERE / "compare_mechanisms.py")).read_text()
    marker = '    cases, input_pins, root_count = assemble_cases()'
    assert original.count(marker) == 1
    replacement = '''    supplemental = json.loads((HERE / "SUPPLEMENT-PANEL.json").read_text())
    assert all(pin(Path(p)) == h for p, h in supplemental["files"].items())
    cases, input_pins, root_count = supplemental["cases"], dict(supplemental["files"]), 12
    input_pins[str(HERE / "SUPPLEMENT-PANEL.json")] = pin(HERE / "SUPPLEMENT-PANEL.json")'''
    original = original.replace(marker, replacement).replace('out = HERE / "mechanism-comparison"',
                                                             'out = HERE / "mechanism-comparison-supplement"')
    save(_project_file(_PROJECT_ROOT, HERE / "compare_supplement.py"), original.encode().decode()) if False else None
    with (_project_file(_PROJECT_ROOT, HERE / "compare_supplement.py")).open("x") as stream:
        stream.write(original)
    compile(original, "compare_supplement.py", "exec")
    print({"additional_windows": len(cases), "new_scores_worlds_models": 0})


if __name__ == "__main__":
    main()
