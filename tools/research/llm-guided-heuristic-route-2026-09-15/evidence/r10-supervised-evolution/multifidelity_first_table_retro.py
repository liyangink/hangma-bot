"""R13-MF0：用冻结 V2 参数批检验第一桌多保真筛选。"""

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
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/multifidelity-first-table-retro-01-20260921')
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R13-MULTI-FIDELITY-EVOLUTION-FUNNEL-PLAN-2026-09-21.md')
SOURCE_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920/manifest.json')
SOURCE_SAMPLES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parameter-search-a-20260920/phase-a-samples.json')
CANDIDATE_PATTERN = re.compile(r"a-(v2_joint_\d+)-([HM])-r(\d+)-s(\d+)$")
BASELINE_PATTERN = re.compile(r"a-baseline-([HM])-r(\d+)-s(\d+)$")


def digest(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _result_tree_digest() -> str:
    """绑定 1,600 个实际阶段结果的相对路径与内容，避免汇总文件替代原件。"""

    import hashlib
    hasher = hashlib.sha256()
    paths = sorted((_project_file(_PROJECT_ROOT, SOURCE / "baseline")).glob("*/result.json"))
    paths.extend(sorted((_project_file(_PROJECT_ROOT, SOURCE / "candidates")).glob("*/*/result.json")))
    for path in paths:
        hasher.update(str(path.relative_to(SOURCE)).encode())
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _raw(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(path.read_text())
    raw = payload.get("raw")
    expected = payload.get("expected")
    if not isinstance(raw, dict) or not isinstance(expected, dict):
        raise ValueError("阶段结果缺 expected/raw：" + str(path))
    if raw.get("status") != "complete" or not raw.get("usable"):
        raise ValueError("阶段结果不可用：" + str(path))
    if len(raw.get("tables") or ()) != 2:
        raise ValueError("阶段不含两桌：" + str(path))
    return expected, raw


def _first_focal_score(raw: Mapping[str, Any]) -> int:
    table = raw["tables"][0]
    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index("focal")
    return int(table["scores_by_seat"][seat])


def _percentile(values: Sequence[float], fraction: float) -> float:
    """训练折最近秩分位数；不在留出折插值。"""

    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        rank = (start + end + 2) / 2.0
        for offset in range(start, end + 1):
            ranks[order[offset]] = rank
        start = end + 1
    return ranks


def _spearman(left: Sequence[float], right: Sequence[float]) -> float:
    left_ranks, right_ranks = _ranks(left), _ranks(right)
    left_mean, right_mean = statistics.fmean(left_ranks), statistics.fmean(right_ranks)
    numerator = sum((a - left_mean) * (b - right_mean)
                    for a, b in zip(left_ranks, right_ranks))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left_ranks)
                            * sum((b - right_mean) ** 2 for b in right_ranks))
    return numerator / denominator if denominator else 0.0


def _load_units() -> list[dict[str, Any]]:
    baselines: dict[tuple[str, int, int], dict[str, Any]] = {}
    for path in sorted((_project_file(_PROJECT_ROOT, SOURCE / "baseline")).glob("*/result.json")):
        expected, raw = _raw(path)
        match = BASELINE_PATTERN.fullmatch(str(expected["step_id"]))
        if not match:
            raise ValueError("未知基线步标识：" + str(expected["step_id"]))
        key = (match.group(1), int(match.group(2)), int(match.group(3)))
        baselines[key] = raw
    if len(baselines) != 64:
        raise ValueError(f"预期64个基线阶段，得到{len(baselines)}")
    units = []
    for path in sorted((_project_file(_PROJECT_ROOT, SOURCE / "candidates")).glob("*/*/result.json")):
        expected, raw = _raw(path)
        match = CANDIDATE_PATTERN.fullmatch(str(expected["step_id"]))
        if not match:
            raise ValueError("未知候选步标识：" + str(expected["step_id"]))
        candidate, mix, root, seat = (match.group(1), match.group(2),
                                      int(match.group(3)), int(match.group(4)))
        baseline = baselines[(mix, root, seat)]
        units.append({
            "candidate_id": candidate, "mix": mix, "root_index": root,
            "focal_seat": seat,
            "first_table_delta": _first_focal_score(raw) - _first_focal_score(baseline),
            "full_stage_score_delta": int(raw["focal_stage_score"])
                                      - int(baseline["focal_stage_score"]),
            "u_delta_low": float(raw["u_low"]) - float(baseline["u_high"]),
            "u_delta_high": float(raw["u_high"]) - float(baseline["u_low"]),
            "candidate_u_interval": [float(raw["u_low"]), float(raw["u_high"])],
            "baseline_u_interval": [float(baseline["u_low"]), float(baseline["u_high"])],
        })
    if len(units) != 1536:
        raise ValueError(f"预期1,536个候选阶段，得到{len(units)}")
    counts = {candidate: sum(row["candidate_id"] == candidate for row in units)
              for candidate in {row["candidate_id"] for row in units}}
    if len(counts) != 24 or set(counts.values()) != {64}:
        raise ValueError("候选数或每候选阶段数不完整：" + str(counts))
    return units


def _summaries(units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for candidate in sorted({str(row["candidate_id"]) for row in units}):
        selected = [row for row in units if row["candidate_id"] == candidate]
        by_mix = {}
        for mix in ("H", "M"):
            layer = [row for row in selected if row["mix"] == mix]
            by_mix[mix] = {
                "first_table_delta_mean": statistics.fmean(row["first_table_delta"] for row in layer),
                "full_stage_score_delta_mean": statistics.fmean(row["full_stage_score_delta"] for row in layer),
                "u_delta_low_mean": statistics.fmean(row["u_delta_low"] for row in layer),
            }
        summaries.append({
            "candidate_id": candidate, "stage_count": len(selected),
            "first_table_delta_mean": statistics.fmean(row["first_table_delta"] for row in selected),
            "full_stage_score_delta_mean": statistics.fmean(row["full_stage_score_delta"] for row in selected),
            "u_delta_low_mean": statistics.fmean(row["u_delta_low"] for row in selected),
            "u_delta_high_mean": statistics.fmean(row["u_delta_high"] for row in selected),
            "by_mix": by_mix,
        })
    return summaries


def prepare() -> None:
    """冻结历史来源、四折候选分组和漏斗继续门。"""

    if OUT.exists():
        raise SystemExit("MF0 输出已存在，拒绝覆盖")
    source_manifest = json.loads(SOURCE_MANIFEST.read_text())
    if source_manifest.get("candidate_tables") != 3072 or source_manifest.get("baseline_tables") != 128:
        raise ValueError("V2 参数阶段 A 不是预期完整批次")
    if len(json.loads(SOURCE_SAMPLES.read_text())) != 1536:
        raise ValueError("V2 参数阶段 A 样本清单不完整")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r13-mf0-first-table-retro-01",
        accounts={}, issued_by="lead", issued_at_utc=batch.search.utc_now(),
        legacy_alias=False)
    authorization.update({
        "issuance_basis": "R12学习价值模型关闭后，按AlphaEvolve级联评价方向验证无需学习的第一桌代理",
        "scope": "只读V2联合参数阶段A；24候选×64阶段；候选四折留出；零新桌零模型调用",
        "max_model_calls": 0, "max_full_tables": 0, "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    candidates = [f"v2_joint_{index:02d}" for index in range(1, 25)]
    folds = [[candidate for index, candidate in enumerate(candidates) if index % 4 == fold]
             for fold in range(4)]
    manifest = {
        "schema": "r13-multifidelity-first-table-retro/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": guard.capture(source_paths=[Path(__file__), PLAN, SOURCE_MANIFEST,
                                                SOURCE_SAMPLES, _project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "source_manifest": str(SOURCE_MANIFEST), "source_manifest_sha256": digest(SOURCE_MANIFEST),
        "source_samples": str(SOURCE_SAMPLES), "source_samples_sha256": digest(SOURCE_SAMPLES),
        "source_result_tree": str(SOURCE), "source_result_tree_sha256": _result_tree_digest(),
        "expected": {"candidate_count": 24, "candidate_stages": 1536,
                     "baseline_stages": 64, "tables_per_stage": 2},
        "folds": folds,
        "training_thresholds": {
            "retain": "训练候选first_table_delta_mean的最近秩中位数",
            "competitive": "训练候选u_delta_low_mean的最近秩上四分位数",
        },
        "continue_gate": {"competitive_false_negative_rate_max": 0.05,
                          "candidate_table_savings_min": 0.25,
                          "overall_spearman_min": 0.50,
                          "mix_spearman_min": 0.0,
                          "global_best_retained": True},
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False, "model_calls": 0, "new_tables": 0,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_R13_MF0", "folds": folds}, ensure_ascii=False))


def verify(manifest: Mapping[str, Any]) -> None:
    guard.verify(manifest["runtime"])
    for key, sha in (("plan", "plan_sha256"), ("source_manifest", "source_manifest_sha256"),
                     ("source_samples", "source_samples_sha256")):
        if digest(Path(str(manifest[key]))) != manifest[sha]:
            raise ValueError(key + " 摘要漂移")
    if _result_tree_digest() != manifest["source_result_tree_sha256"]:
        raise ValueError("source_result_tree 摘要漂移")


def run() -> None:
    """执行候选级四折阈值回溯并量化误淘汰与节省。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    verify(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("MF0 已执行，拒绝覆盖")
    units = _load_units()
    summaries = _summaries(units)
    by_id = {row["candidate_id"]: row for row in summaries}
    decisions = []
    fold_reports = []
    for fold_index, held in enumerate(manifest["folds"]):
        train = [row for row in summaries if row["candidate_id"] not in held]
        test = [by_id[candidate] for candidate in held]
        retain_threshold = _percentile([row["first_table_delta_mean"] for row in train], 0.5)
        competitive_threshold = _percentile([row["u_delta_low_mean"] for row in train], 0.75)
        fold_rows = []
        for row in test:
            decision = {
                "fold": fold_index, "candidate_id": row["candidate_id"],
                "first_table_delta_mean": row["first_table_delta_mean"],
                "u_delta_low_mean": row["u_delta_low_mean"],
                "retain_threshold": retain_threshold,
                "competitive_threshold": competitive_threshold,
                "retained": row["first_table_delta_mean"] >= retain_threshold,
                "competitive": row["u_delta_low_mean"] >= competitive_threshold,
            }
            decision["false_negative"] = decision["competitive"] and not decision["retained"]
            decisions.append(decision)
            fold_rows.append(decision)
        fold_reports.append({"fold": fold_index, "held_candidates": held,
                             "retain_threshold": retain_threshold,
                             "competitive_threshold": competitive_threshold,
                             "retained": sum(row["retained"] for row in fold_rows),
                             "competitive": sum(row["competitive"] for row in fold_rows),
                             "false_negatives": sum(row["false_negative"] for row in fold_rows)})
    competitive = sum(row["competitive"] for row in decisions)
    false_negatives = sum(row["false_negative"] for row in decisions)
    culled = sum(not row["retained"] for row in decisions)
    false_negative_rate = false_negatives / competitive if competitive else 0.0
    # 每候选原需两桌；漏斗全部跑第一桌，仅保留者跑第二桌。
    savings = culled / (2.0 * len(decisions))
    first = [float(row["first_table_delta_mean"]) for row in summaries]
    u_low = [float(row["u_delta_low_mean"]) for row in summaries]
    full_score = [float(row["full_stage_score_delta_mean"]) for row in summaries]
    correlations = {"overall_first_vs_u_low": _spearman(first, u_low),
                    "overall_first_vs_full_score": _spearman(first, full_score)}
    for mix in ("H", "M"):
        correlations[f"{mix}_first_vs_u_low"] = _spearman(
            [row["by_mix"][mix]["first_table_delta_mean"] for row in summaries],
            [row["by_mix"][mix]["u_delta_low_mean"] for row in summaries])
    best = max(summaries, key=lambda row: (row["u_delta_low_mean"],
                                           row["full_stage_score_delta_mean"],
                                           row["candidate_id"]))
    best_decision = next(row for row in decisions if row["candidate_id"] == best["candidate_id"])
    gate = manifest["continue_gate"]
    checks = {
        "competitive_false_negative_rate": false_negative_rate
                                            <= gate["competitive_false_negative_rate_max"],
        "candidate_table_savings": savings >= gate["candidate_table_savings_min"],
        "overall_spearman": correlations["overall_first_vs_u_low"] >= gate["overall_spearman_min"],
        "mix_spearman": all(correlations[f"{mix}_first_vs_u_low"] >= gate["mix_spearman_min"]
                            for mix in ("H", "M")),
        "global_best_retained": bool(best_decision["retained"]),
    }
    passed = all(checks.values())
    result = {
        "schema": "r13-multifidelity-first-table-retro-result/1",
        "status": ("PASS_R13_MF0_FOR_PROSPECTIVE_AUDIT" if passed
                   else "CLOSE_R13_FIRST_TABLE_FUNNEL_RETROSPECTIVE_FAILED"),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "counts": {"candidates": len(summaries), "candidate_stages": len(units),
                   "competitive": competitive, "false_negatives": false_negatives,
                   "retained": sum(row["retained"] for row in decisions), "culled": culled},
        "competitive_false_negative_rate": false_negative_rate,
        "candidate_table_savings": savings,
        "correlations": correlations,
        "global_best": {"candidate_id": best["candidate_id"],
                        "u_delta_low_mean": best["u_delta_low_mean"],
                        "full_stage_score_delta_mean": best["full_stage_score_delta_mean"],
                        "retained": best_decision["retained"]},
        "folds": fold_reports, "decisions": decisions, "candidate_summaries": summaries,
        "gate_checks": checks, "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
        "next": ("按R13执行带被淘汰补跑审计的全新来源MF1" if passed
                 else "关闭第一桌漏斗；按完整两桌评价恢复有界种群搜索"),
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {"schema": "r13-mf0-paired-units/1", "rows": units})
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": result["status"],
                      "competitive_false_negative_rate": false_negative_rate,
                      "candidate_table_savings": savings,
                      "correlations": correlations, "gate_checks": checks},
                     ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run}[args.command]()


if __name__ == "__main__":
    main()
