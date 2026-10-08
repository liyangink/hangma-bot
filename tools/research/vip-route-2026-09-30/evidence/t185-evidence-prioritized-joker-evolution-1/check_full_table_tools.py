"""开新桌前核T185读回器：使用旧已闭合首四桌，只验收据不比较积分。"""

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
import copy
import gzip
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

from common import HERE, OLD, ROOT, pin, save
import t185_close_development as reader
from prepare_development import build_plan


def main():
    """验证实际1686份排名/收据及非法、缺根、非有限、未知诊断等负例。"""
    old_plan = json.loads((OLD / "DEVELOPMENT-PLAN.json").read_text())
    tables, totals = [], 0
    files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "t185_close_development.py"),
        _project_file(_PROJECT_ROOT, HERE / "t185_run_development.py"), _project_file(_PROJECT_ROOT, HERE / "prepare_development.py"), _project_file(_PROJECT_ROOT, HERE / "run_development_workers.py"),
        _project_file(_PROJECT_ROOT, HERE / "FULL-TABLE-TOOLS-PREPARED.json"), OLD / "DEVELOPMENT-PLAN.json")}
    for arm in range(4):
        directory = OLD / "natural-development/root-001" / f"seat-0-arm-{arm}"
        closure = json.loads((directory / "CLOSURE.json").read_text())
        assert closure["complete"] and closure["source_stable"] and closure["failure"] is None
        table = reader.TableEvidence(1, 0, arm, directory, pin(directory / "START.json"),
                                     pin(directory / "CLOSURE.json"), pin(directory / "PAIRING-IDENTITY.json"))
        audit, pins = reader.score_receipts(table, closure, old_plan)
        totals += audit["actual_score_calls"]
        files.update(pins)
        files.update({str(directory / n): pin(directory / n) for n in ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json")})
        tables.append((table, closure))
    assert totals == 1686
    table, closure = tables[0]
    negative = {}

    def rejected(name, fn):
        """只记录拒绝原因，不为验证失败修改原件。"""
        try:
            fn()
        except (ValueError, TypeError, KeyError, AssertionError) as error:
            negative[name] = {"rejected": True, "type": type(error).__name__, "message": str(error)}
        else:
            raise ValueError("读回器错误接受负例：" + name)

    focal = next(d for d in closure["outcome"]["decisions"] if d["seat"] == 0)
    normal = next(d for d in closure["outcome"]["decisions"] if d["seat"] == 2)
    for name, original, changes in (
        ("unknown_opponent_diagnostic", normal, {"degraded_reasons": ["UNKNOWN_DIAGNOSTIC_NEGATIVE"]}),
        ("focal_information_not_allowed", focal, {"degraded_reasons": [reader.LEGACY_INFORMATION]}),
        ("illegal_action", focal, {"legal": False}),
        ("fallback_action", focal, {"fallback_reason": "timeout"}),
    ):
        altered = copy.deepcopy(original)
        altered.update(changes)
        bad = {**closure, "outcome": {**closure["outcome"], "decisions": [altered]}}
        rejected(name, lambda bad=bad: reader.decision_metadata(table, bad, old_plan))
    with gzip.open(table.directory / "focal-decisions.jsonl.gz", "rb") as stream:
        first = reader.decode(stream.readline())
    original_open = gzip.open

    def corrupt_first(changes):
        """内存替换首收据；不写旧gzip，不提取或比较终局积分。"""
        altered = copy.deepcopy(first)
        changes(altered)
        def opener(path, mode, *args, **kwargs):
            if Path(path) == table.directory / "focal-decisions.jsonl.gz":
                return io.BytesIO(json.dumps(altered, ensure_ascii=False, allow_nan=True).encode() + b"\n")
            return original_open(path, mode, *args, **kwargs)
        with patch.object(reader.gzip, "open", opener):
            reader.score_receipts(table, closure, old_plan)

    rejected("missing_legal_rank", lambda: corrupt_first(lambda r: r["candidates"].pop()))
    rejected("wrong_rank_sequence", lambda: corrupt_first(lambda r: r["candidates"][0].update(rank=0)))
    rejected("bool_score", lambda: corrupt_first(lambda r: r["candidates"][0].update(score=True)))
    rejected("nonfinite_score", lambda: corrupt_first(lambda r: r["candidates"][0].update(score=float("nan"))))
    rejected("missing_before_score_capture", lambda: corrupt_first(lambda r: r["scoring_calls"][0]["input_capture"].update(saved_before_score=False)))
    packages = [_project_file(_PROJECT_ROOT, HERE / "AUTHOR-speed-model-output"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-model-output")]
    prospective = build_plan(packages)
    reader.validate_plan(prospective)
    reader.frozen(prospective)
    wrong_roots = copy.deepcopy(prospective)
    wrong_roots["roots"][1]["seed"] = wrong_roots["roots"][0]["seed"]
    rejected("duplicate_source_seed", lambda: reader.validate_plan(wrong_roots))
    wrong_budget = copy.deepcopy(prospective)
    wrong_budget["planned_table_instances"] += 1
    rejected("table_denominator_drift", lambda: reader.validate_plan(wrong_budget))
    assert all(pin(Path(p)) == h for p, h in files.items())
    save(_project_file(_PROJECT_ROOT, HERE / "FULL-TABLE-TOOLS-CHECKED.json"), {"schema": "t185-full-table-tools-checked/1", "success": True,
        "files": files, "actual_old_closed_tables_receipts_checked": 4, "actual_focal_scores_checked": totals,
        "negative_checks": negative, "original_files_mutated": False, "scores_or_outcomes_compared": False,
        "prospective_two_candidate_plan_checked_not_saved": True, "new_worlds_tables_or_model_calls": 0,
        "strength_or_deadline_admission": False})
    print({"success": True, "receipt_count": totals, "negative_checks": len(negative), "new_worlds_tables": 0}, flush=True)


if __name__ == "__main__":
    main()
