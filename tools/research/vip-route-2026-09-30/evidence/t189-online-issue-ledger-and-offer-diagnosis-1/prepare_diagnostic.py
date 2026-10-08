"""冻结24公开状态，给c70增加完整估值解释；人工仪器不作为模型候选。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t189-online-issue-ledger-and-offer-diagnosis-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save


def main():
    """仅增加trace，不改评分表达式；不读取自然开发或独立确认池。"""
    destination = _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")
    assert not destination.exists()
    gate = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / "qualification/CLOSED.json")).read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    source_path = _project_file(_PROJECT_ROOT, PREVIOUS / "AUTHOR-model-output/candidate.py")
    source = source_path.read_text()
    assert pin(source_path)["sha256"] == gate["identity"]["source_sha256"]
    old = '            pairs.append(("prep", (facts[3][0], facts[3][1], facts[3][2], round(facts[3][3], 3))))'
    assert source.count(old) == 1
    addition = '''
            # T189人工仪器：展示原公式完整中间量，不改任何分值。
            pairs.append(("diagnostic_offer_full", ready))
            pairs.append(("diagnostic_target_full", facts[2]))
            pairs.append(("diagnostic_routes", (facts[0], facts[1])))'''
    instrument = source.replace(old, old + addition)
    ast.parse(instrument)
    instrument_path = _project_file(_PROJECT_ROOT, HERE / "instrument-c70.py")
    with instrument_path.open("x") as stream:
        stream.write(instrument)
    first_path = _project_file(_PROJECT_ROOT, PREVIOUS / "FIRST-CHOICES.jsonl.gz")
    with gzip.open(first_path, "rt") as stream:
        labels = [json.loads(line)["label"] for line in stream]
    later_path = _project_file(_PROJECT_ROOT, PREVIOUS / "LATER-QUALIFICATION-CASES.json")
    labels.extend(c["label"] for c in json.loads(later_path.read_text())["cases"])
    labels.extend(["anchor:mature-baotou-current-hu", "anchor:early-one-white-route-speed"])
    assert len(labels) == len(set(labels)) == 24
    source_cases = _project_file(_PROJECT_ROOT, HERE.parent / "t187-family-combination-evolution-1/EXPLORATION-QUALIFICATION-PLAN.json")
    row_path = _project_file(_PROJECT_ROOT, PREVIOUS / "qualification/rows.jsonl")
    rows = {r["label"]: r for r in map(json.loads, row_path.read_text().splitlines())}
    assert all(label in rows for label in labels)
    cases = json.loads(source_cases.read_text())["cases"] + json.loads(later_path.read_text())["cases"]
    bylabel = {c["label"]: c for c in cases}
    assert all(rows[label]["view_sha256"] == bylabel[label]["view_sha256"] for label in labels)
    paths = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_diagnostic.py"), source_path, instrument_path,
        _project_file(_PROJECT_ROOT, PREVIOUS / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, PREVIOUS / "qualification/CLOSED.json"),
        source_cases, row_path, first_path, later_path]
    save(destination, {"complete": True, "case_labels": labels, "source_cases_file": str(source_cases),
        "later_cases_file": str(later_path), "cached_rows_file": str(row_path),
        "original_candidate_identity": gate["identity"], "instrument_file": str(instrument_path),
        "model_proposal": False, "instrument_changes_scores": False,
        "planned_actual_score_calls": 48, "repeats_per_case": 2,
        "files": {str(path): pin(path) for path in paths},
        "no_natural_development_or_confirmation_pool_read": True,
        "new_scores_worlds_tables_models_HTTP": 0})
    print(json.dumps({"complete": True, "public_states": 24, "planned_actual_score_calls": 48}))


if __name__ == "__main__":
    main()
