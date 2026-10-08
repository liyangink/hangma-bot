"""按线上深度与额度冻结当前父代研究身份及八个新来源采样，不调用模型/评分。"""

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
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.scoring_sources import source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def pin(path):
    """绑定实际文件字节，不继承其历史结果或身份。"""
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def save(path, value):
    """只新建证据，拒绝覆盖冻结方案及已发生费用。"""
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    """仅研究装载；保持原S02源码，明确与旧生成包的工程身份不同。"""
    start = json.loads((_project_file(_PROJECT_ROOT, HERE / "START-CLOSED.json")).read_text())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in start["files"].items())
    source = (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()
    old = _project_file(_PROJECT_ROOT, HERE.parent / "t110-compact-target-cost-joint-evolution-1")
    old_source = old / "S02-model-output/candidate.py"
    assert old_source.read_bytes() == source.encode()
    raw = json.loads((old / "AUTHOR-BATCH.json").read_text())
    raw.update(batch_id="t182-current-parent-d1-diagnostic-execution-20261004",
               input_bound=None)
    raw["budgets"] = {k: 0 for k in raw["budgets"]}
    raw["projection_limits"]["max_replacement_depth"] = 1
    batch_file = _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json")
    save(batch_file, raw)
    batch = VipEohBatch.read(batch_file)
    identity = batch.identity(source)
    assert identity["params"]["projection_limits"]["max_replacement_depth"] == 1
    assert batch.max_operations == 4_800_000
    executor = ActionValueExecutor(source, max_operations=batch.max_operations,
                                  max_local_collection_size=batch.projection_limits.max_nodes)
    original = json.loads((old / "S02-model-output/generation.json").read_text())
    save(_project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json"), {
        "schema": "t182-current-research-baseline/1", "identity": identity,
        "role": "byte_exact_existing_formula_current_engineering_execution",
        "original_generation_file": str((old / "S02-model-output/generation.json").relative_to(ROOT)),
        "original_generation_pin": pin(old / "S02-model-output/generation.json"),
        "original_generation_identity": original["identity"],
        "original_source_pin": pin(old_source), "current_source_pin": pin(_project_file(_PROJECT_ROOT, HERE / "parent-source.py")),
        "source_unchanged": True, "engineering_identity_changed": original["identity"] != identity,
        "old_generation_results_transferred": False, "new_model_calls": 0,
        "load_ok": True, "load_method": "ActionValueExecutor_constructor",
        "scored_or_admitted": False,
    })
    roots = json.loads((_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json")).read_text())["diagnostic"]
    compositions = json.loads((_project_file(_PROJECT_ROOT, HERE / "COMPOSITIONS.json")).read_text())["pools"]["diagnostic"]
    assert len(roots) == len(compositions) == 8
    assert [r["root_id"] for r in roots] == [r["root_id"] for r in compositions]
    manifest = source_manifest(("hangma_bot.offline.qualifier_opponents",
                               "hangma_bot.offline.evaluate",
                               "hangma_bot.offline.scoring_input_capture"))
    manifest.update(identity["source_manifest"])
    manifest[identity["contract_path"]] = pin(_project_file(_PROJECT_ROOT, ROOT / identity["contract_path"]))
    save(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-SOURCE-MANIFEST.json"), manifest)
    save(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json"), {
        "schema": "t182-result-blind-source-panel/1", "roots": compositions,
        "baseline_identity": identity, "planned_tables": 8, "rounds_per_table": 8,
        "initial_dealer": 0, "focal_seat": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
        "source_kind": "simulation", "clock_mode": "logical_not_official_deadline_evidence",
        "selection": "first eligible before-choice window per public opportunity class, at most eight per root",
        "classes": ["early_no_white", "early_one_white", "early_multi_white", "current_hu",
                    "claim_option", "gang_option", "late_draw", "later_draw"],
        "outcome_or_score_used_for_selection": False, "step_limit_per_table": 50000,
        "wall_clock_limit_per_table_seconds": 600,
        "capture_limits": {"max_view_json_bytes": 67108864,
                           "max_total_json_bytes": 536870912, "max_unique_views": 8},
        "source_manifest": manifest,
        "frozen_files": {str(p.relative_to(ROOT)): pin(p) for p in (
            Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_diagnostic_sources.py"), batch_file,
            _project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json"), _project_file(_PROJECT_ROOT, HERE / "parent-source.py"),
            _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"), _project_file(_PROJECT_ROOT, HERE / "COMPOSITIONS.json"))},
        "actual_models_scores_worlds_tables": 0, "published_or_admitted": False,
    })
    print(json.dumps({"current_parent_loaded": True, "sources_reserved": len(roots),
                      "depth": 1, "new_models_scores_worlds_tables": 0}))


if __name__ == "__main__":
    main()
