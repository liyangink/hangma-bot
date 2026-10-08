"""R10 第二代路线置信结构阶段 A：九配置共同新来源完整阶段筛选。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import concurrent.futures
import hashlib
import json
import multiprocessing
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_archive as archive  # noqa: E402
import structural_search_2a as engine  # noqa: E402
import v2_parameter_policy as parameter  # noqa: E402
import v2_parameter_wiring as wiring  # noqa: E402
import verify_full_natural_results as full  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-confidence-recombination-02-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-confidence-recombination-02-20260921/effect-a')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-confidence-recombination-02-20260921/behavior-preflight-v2/summary.json')
CONFIG_ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-confidence-recombination-02-20260921/behavior-preflight-v2/configurations')
OLD_PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/summary.json')
OLD_PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/configurations/r2-cfg-02/candidate.py')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092201
ROOTS = tuple(range(1, 9))
MIXES = ("H", "M")
SEATS = tuple(range(4))
V2_CONTROL = "c-cfg-00"
OLD_PARENT_CONTROL = "fixed-parent-exact"
TABLE_BUDGET = 1280


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def configurations() -> list[dict]:
    """重建八个第二代配置，并加入上一代冻结冠军的精确源码控制。"""
    summary = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if summary["passed_tasks"] != ["C"] or summary["failed_tasks"]:
        raise ValueError("第二代路线置信行为预检结论漂移")
    task = summary["tasks"][0]
    rows = []
    for item in task["configurations"]:
        path = _project_file(_PROJECT_ROOT, CONFIG_ROOT / item["config_id"] / "candidate.py")
        digest = sha256_bytes(path.read_bytes())
        if digest != item["source_sha256"]:
            raise ValueError("第二代配置源码摘要漂移：" + item["config_id"])
        rows.append({
            "config_id": item["config_id"],
            "kind": "action_value_source",
            "family": "ROUTE_CONFIDENCE_HYBRID",
            "source": str(path),
            "source_sha256": digest,
            "scorer_name": "offline-route-confidence:" + digest,
            "candidate_id": "action_value_v1:offline-route-confidence:" + digest,
            "values": item["values"],
            "is_zero_effect": item["is_zero_effect"],
            "is_author_default": item["is_author_default"],
            "preference_signature": item["preference_signature"],
            "score_signature": item["score_signature"],
            "changed_preferred_vs_parent": item["changed_preferred_vs_base"],
            "changed_scores_vs_parent": item["changed_scores_vs_base"],
        })
    old = json.loads(OLD_PREFLIGHT.read_text(encoding="utf-8"))
    old_task = next(item for item in old["tasks"] if item["task"] == "R2")
    old_row = next(item for item in old_task["configurations"] if item["config_id"] == "r2-cfg-02")
    digest = sha256_bytes(OLD_PARENT.read_bytes())
    if digest != old_row["source_sha256"]:
        raise ValueError("上一代冻结冠军源码摘要漂移")
    rows.append({
        "config_id": OLD_PARENT_CONTROL,
        "kind": "action_value_source",
        "family": "ROUTE_FIXED_FULL_BONUS_PARENT",
        "source": str(OLD_PARENT),
        "source_sha256": digest,
        "scorer_name": "offline-route-fixed-parent:" + digest,
        "candidate_id": "action_value_v1:offline-route-fixed-parent:" + digest,
        "values": {"RMF_SCALE": 8.0, "RMF_SHAPE": 64.0, "RMF_CAP": 8.0},
        "is_zero_effect": False,
        "is_author_default": False,
        "preference_signature": old_row["preference_signature"],
        "score_signature": old_row["score_signature"],
        "changed_preferred_vs_parent": old_row["changed_preferred_vs_base"],
        "changed_scores_vs_parent": old_row["changed_scores_vs_base"],
    })
    if len(rows) != 9 or len({row["config_id"] for row in rows}) != 9:
        raise ValueError("路线置信阶段 A 必须恰有九个唯一配置")
    if [row["config_id"] for row in rows if row["is_zero_effect"]] != [V2_CONTROL]:
        raise ValueError("稳定 V2 零效应身份漂移")
    return rows


def select_for_b(ranking: list[dict]) -> list[str]:
    """取两个新结构，并强制保留稳定 V2 与上一代冠军作为比较父代。"""
    controls = {V2_CONTROL, OLD_PARENT_CONTROL}
    chosen = [row["config_id"] for row in ranking if row["config_id"] not in controls][:2]
    chosen.extend([OLD_PARENT_CONTROL, V2_CONTROL])
    return chosen


def source_paths() -> list[Path]:
    result = [Path(__file__), Path(engine.__file__), Path(engine.first.__file__),
              Path(parameter.__file__), Path(wiring.__file__), Path(archive.__file__),
              Path(full.__file__), PREFLIGHT, OLD_PREFLIGHT, CONTRACT]
    result.extend(Path(row["source"]) for row in configurations())
    return result


def bind_engine() -> None:
    engine.BATCH = BATCH
    engine.OUT = OUT
    engine.PREFLIGHT = PREFLIGHT
    engine.CONFIG_ROOT = CONFIG_ROOT
    engine.CONTRACT = CONTRACT
    engine.PANEL_SEED = PANEL_SEED
    engine.ROOTS = ROOTS
    engine.MIXES = MIXES
    engine.SEATS = SEATS
    engine.PARENT_CONTROL = V2_CONTROL
    engine.TABLE_BUDGET = TABLE_BUDGET
    engine.configurations = configurations
    engine.select_for_b = select_for_b
    engine.source_paths = source_paths
    engine.bind_first_module()


bind_engine()


def prepare() -> None:
    engine.prepare()
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "schema": "r10-route-confidence-search-a/1",
        "candidate_tables": 1152,
        "baseline_tables": 128,
        "max_full_tables": TABLE_BUDGET,
        "selection": {
            "fitness": "H/M 等权的根级保守差 d_low 均值",
            "keep": 4,
            "forced_controls": [OLD_PARENT_CONTROL, V2_CONTROL],
            "rule": (
                "按适应度降序、config_id升序取前2个第二代结构；上一代固定+8冠军和"
                "稳定V2强制保留。阶段A完整结束后才选择。"
            ),
            "meaning": "预算分配，不是显著性检验；未续评记 NOT_SELECTED_WITHIN_BUDGET",
        },
        "phase_plan": {
            "a": "9配置，H/M各8根，共1280桌",
            "b": "4配置追加H/M各8根，共640桌；累计每类16根",
            "c": "新冠军、上一代冠军、V2追加H/M各16根，共1024桌；累计每类32根",
        },
    })
    engine.batch.write(manifest_path, manifest)
    print(json.dumps({"status": "PREPARED_ROUTE_CONFIDENCE_A",
                      "configurations": 9, "tables": TABLE_BUDGET}, ensure_ascii=False))


def run_baseline_all() -> dict:
    bind_engine()
    engine.first.verify_inputs = engine.verify_inputs
    return engine.first.run_baseline_all()


def run_configuration(config_id: str) -> dict:
    bind_engine()
    engine.first.verify_inputs = engine.verify_inputs
    return engine.first.run_configuration(config_id)


def correct_summary() -> None:
    freeze_path = _project_file(_PROJECT_ROOT, OUT / "phase-b-freeze.json")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze.update({
        "schema": "r10-route-confidence-phase-b-freeze/1",
        "forced_controls": [OLD_PARENT_CONTROL, V2_CONTROL],
        "planned_candidate_tables": 512,
        "baseline_new_tables": 128,
        "selection_keep": 3,
    })
    freeze.pop("forced_parent_control", None)
    engine.batch.write(freeze_path, freeze)
    ranking_path = _project_file(_PROJECT_ROOT, OUT / "phase-a-ranking.json")
    ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
    ranking["schema"] = "r10-route-confidence-phase-a-ranking/1"
    engine.batch.write(ranking_path, ranking)
    summary_path = _project_file(_PROJECT_ROOT, OUT / "summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update({
        "status": "COMPLETE_ROUTE_CONFIDENCE_PHASE_A_DEVELOPMENT_RANKING",
        "configurations": 9,
        "families": 2,
        "roots_per_configuration": 16,
        "candidate_tables": 1152,
        "baseline_tables": 128,
        "full_tables": TABLE_BUDGET,
        "old_parent_control": next(
            row for row in ranking["ranking"] if row["config_id"] == OLD_PARENT_CONTROL
        ),
        "v2_control": next(
            row for row in ranking["ranking"] if row["config_id"] == V2_CONTROL
        ),
        "next": "按 phase-b-freeze 追加H/M各8根；阶段A仅分配预算",
    })
    summary.pop("parent_control", None)
    engine.batch.write(summary_path, summary)


def run_a() -> None:
    plan = engine.batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    engine.verify_inputs(plan)
    context = multiprocessing.get_context("spawn")
    completed = []
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=plan["workers"], mp_context=context) as pool:
        futures = [pool.submit(run_baseline_all)]
        futures.extend(pool.submit(run_configuration, config_id)
                       for config_id in plan["configuration_ids"])
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed.append(result)
            print((result.get("config_id") or "baseline"), "complete",
                  result["tables"], "tables", flush=True)
    if len(completed) != 10:
        raise ValueError("路线置信阶段 A 工作单元未全部完成")
    bind_engine()
    engine.summarize_a()
    correct_summary()
    summary = engine.batch.read(_project_file(_PROJECT_ROOT, OUT / "summary.json"))
    print(json.dumps({
        "status": summary["status"],
        "leader": summary["leader"]["config_id"],
        "fitness": summary["leader"]["fitness_mean_delta_low"],
        "selected_for_b": summary["selected_for_b"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run-a"))
    args = parser.parse_args()
    {"prepare": prepare, "run-a": run_a}[args.operation]()
