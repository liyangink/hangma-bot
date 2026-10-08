"""记录固定32来源的费用决定，并精确封存已闭第三阶段原件。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from archive_stage1_evidence import archive


def main():
    """沿用事前费用标准，不追加牌桌；未决候选保留，不声称证明其无效。"""
    directory = _project_file(_PROJECT_ROOT, HERE / "natural-stage-003-dispatch")
    followup = _project_file(_PROJECT_ROOT, HERE / "natural-stage-003-followup")
    paths = [directory / n for n in ("CLOSED.json", "READOUT-CLOSED.json", "SUMMARY.json", "CUMULATIVE-SUMMARY.json")]
    ended, audit, block, total = [json.loads(p.read_text()) for p in paths]
    observer = json.loads((followup / "CLOSED.json").read_text())
    assert ended["complete"] and ended["resources_released"] and ended["worker_returncodes"] == [0] * 4
    assert audit["complete"] and audit["source_stable"] and audit["actual_tables"] == 128
    assert block["complete"] and block["independent_roots"] == 16 and block["readout_pin"] == pin(paths[1])
    assert observer["complete"] and [p["exit_code"] for p in observer["phases"]] == [0] * 3
    assert total["complete"] and total["all_stage_audits_and_resources_closed"]
    assert total["independent_roots"] == 32 and total["actual_complete_tables"] == 256
    assert total["actual_single_hands"] == 2048 and total["actual_focal_scores"] == 99952
    assert not total["independent_confirmation_budget_eligible"]
    assert not total["optional_64_source_development_budget_eligible"]
    assert all(pin(Path(p)) == h for p, h in total["files"].items())
    counts = Counter("positive" if s["four_seat_delta_sums"]["net"] > 0 else
                     "negative" if s["four_seat_delta_sums"]["net"] < 0 else "zero" for s in total["sources"])
    output = {"complete": True, "candidate_id": total["candidate_identity"]["candidate_id"],
              "source_sha256": total["candidate_identity"]["source_sha256"],
              "actual_complete_tables": 256, "actual_single_hands": 2048, "actual_focal_scores": 99952,
              "independent_roots": 32, "source_sign_counts": dict(counts),
              "mean_delta_per_complete_table": total["mean_delta_per_complete_table"],
              "net_exploratory_source_bootstrap95": total["net_exploratory_source_bootstrap95"],
              "new_block_net_direction": total["new_block_net_direction"],
              "net_mean_excluding_maximum_positive_source": total["net_mean_excluding_maximum_positive_source"],
              "positive_large_income_sources": total["positive_large_income_sources"],
              "stronger_development_budget_criteria": total["stronger_development_budget_criteria"],
              "decision": "停止357e同版自然扩样；不购买64来源补证或独立1024桌确认；保留未决版本及特长证据，先查机制并修订联合公式。",
              "strength_or_original_deadline_or_online_admission": False,
              "new_scores_worlds_tables_models_HTTP": 0,
              "files": {str(p): pin(p) for p in paths + [followup / "CLOSED.json", Path(__file__), _project_file(_PROJECT_ROOT, HERE / "STAGED-DEVELOPMENT-PROTOCOL.md")]}}
    result = _project_file(_PROJECT_ROOT, HERE / "STAGE-003-BUDGET-DECISION-006.json")
    assert not result.exists()
    save(result, output)
    static = [p for p in directory.rglob("*.json") if p.is_file()]
    static += [p for p in followup.iterdir() if p.is_file()]
    static.append(result)
    manifest = _project_file(_PROJECT_ROOT, HERE / "STAGE-003-EVIDENCE-ARCHIVE-006.json")
    assert not manifest.exists()
    save(manifest, {"archive": archive("STAGE-003-CLOSED-EVIDENCE-006.tar.gz", static),
                    "original_files_retained_unchanged": True,
                    "raw_complete_table_streams_not_in_this_archive": True,
                    "restore": "先核归档及成员摘要；已有不同摘要的目标不得覆盖；恢复后逐文件复核。",
                    "new_scores_worlds_tables_models_HTTP": 0})
    print(json.dumps({"complete": True, "net": total["mean_delta_per_complete_table"]["net"],
                      "large_income": total["mean_delta_per_complete_table"]["large_hu_income"],
                      "next_table_dispatches": 0}))


if __name__ == "__main__":
    main()
