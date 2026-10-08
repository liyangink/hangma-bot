"""把历史机会题库归一化为当前 R18 可审计的题目登记表。

这个工具不重算题目真值，也不把历史命中率升级为强度证据。它只完成三件事：

1. 从题目编号恢复独立的 ``base_scenario_id``；
2. 给每题登记真值等级、当前用途和基础场景等权权重；
3. 检查题库规模、区分度与当前 ``sitin-scoring-view/4`` 合同。

输入是 ``sitin-question-bank/1`` 历史产物，输出是只读并轨审计。历史产物保持
原样，便于复算和追溯。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SOURCE_BRANCH = "origin/feat/opportunity-capability-probe"
SOURCE_COMMIT = "bf180ace9dc31910b60484617e77d5f4b5553c30"
EXPECTED_SCHEMA = "sitin-question-bank/1"
CURRENT_SCORING_SCHEMA = "sitin-scoring-view/4"
VARIANT_ID = re.compile(
    r"^(?P<base>L[34]-(?:baotou|near)-\d+)-chain(?P<chain>\d+)-k(?P<horizon>\d+)$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _classification(layer: str) -> tuple[str, str, str]:
    """返回真值等级、当前选择用途和配对校准状态。"""
    if layer == "L1_rule_constraints":
        return "rule_constraint", "hard_gate", "not_required_for_legality"
    if layer == "L3_dominance":
        return (
            "declared_world_conditional_exact",
            "proposal_and_regression",
            "paired_counterfactual_required",
        )
    if layer == "L4_exact_k_turn":
        return (
            "declared_world_conditional_exact",
            "inactive_no_discrimination",
            "paired_counterfactual_required",
        )
    raise ValueError(f"未知题库层：{layer}")


def _base_scenario(question_id: str) -> tuple[str, dict[str, int | None]]:
    match = VARIANT_ID.fullmatch(question_id)
    if match is None:
        return question_id, {"chain_count": None, "horizon": None}
    return match.group("base"), {
        "chain_count": int(match.group("chain")),
        "horizon": int(match.group("horizon")),
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    return value


def _corpus_availability(
    manifest_path: Path | None, repo_root: Path
) -> dict[str, Any]:
    if manifest_path is None:
        return {"checked": False}
    manifest = _load_json(manifest_path)
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("语料 manifest.files 缺失或不是列表")
    missing: list[str] = []
    present = 0
    for entry in entries:
        raw = Path(str(entry["path"]))
        path = raw if raw.is_absolute() else repo_root / raw
        if path.is_file():
            present += 1
        elif len(missing) < 10:
            missing.append(str(raw))
    return {
        "checked": True,
        "manifest": str(manifest_path.relative_to(repo_root)),
        "manifest_sha256": _sha256(manifest_path),
        "files_declared": len(entries),
        "files_present": present,
        "files_missing": len(entries) - present,
        "missing_examples": missing,
        "end_to_end_regeneration_available": present == len(entries),
    }


def integrate(
    bank_path: Path,
    repo_root: Path,
    corpus_manifest: Path | None = None,
) -> dict[str, Any]:
    bank = _load_json(bank_path)
    if bank.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(
            f"题库 schema={bank.get('schema')!r}，预期 {EXPECTED_SCHEMA!r}"
        )
    detail = bank.get("detail")
    if not isinstance(detail, list) or not detail:
        raise ValueError("题库 detail 缺失或为空")

    base_counts: Counter[str] = Counter()
    layer_case_counts: Counter[str] = Counter()
    layer_bases: defaultdict[str, set[str]] = defaultdict(set)
    parsed: list[tuple[dict[str, Any], str, dict[str, int | None]]] = []
    for case in detail:
        question_id = str(case["id"])
        layer = str(case["layer"])
        _classification(layer)
        base_id, variant = _base_scenario(question_id)
        base_counts[base_id] += 1
        layer_case_counts[layer] += 1
        layer_bases[layer].add(base_id)
        parsed.append((case, base_id, variant))

    policies = sorted(
        key
        for key in detail[0]
        if key not in {"id", "layer", "note", "answer"}
    )
    registry = []
    policy_weighted_hits: defaultdict[str, defaultdict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for case, base_id, variant in parsed:
        layer = str(case["layer"])
        truth_tier, role, calibration = _classification(layer)
        weight = 1.0 / base_counts[base_id]
        verdicts: dict[str, str] = {}
        for policy in policies:
            raw = case.get(policy)
            verdict = raw[0] if isinstance(raw, list) and raw else "MISSING"
            verdicts[policy] = str(verdict)
            if verdict == "HIT":
                policy_weighted_hits[layer][policy] += weight
        registry.append(
            {
                "question_id": str(case["id"]),
                "base_scenario_id": base_id,
                "family": layer,
                "truth_tier": truth_tier,
                "selection_role": role,
                "effect_calibration": calibration,
                "independent_weight": weight,
                "variant": variant,
                "answer": case.get("answer"),
                "policy_verdicts": verdicts,
            }
        )

    action_value_path = repo_root / "src/hangma_bot/policy/action_value.py"
    progression_path = repo_root / "src/hangma_bot/hangma/progression_payload.py"
    action_value_source = action_value_path.read_text(encoding="utf-8")
    progression_source = progression_path.read_text(encoding="utf-8")
    schema_ok = f'SCORING_VIEW_SCHEMA_VERSION = "{CURRENT_SCORING_SCHEMA}"' in action_value_source
    baotou_owner_ok = "facts, family_progress=entries, baotou_after=baotou_after" in progression_source

    layer_summary: dict[str, Any] = {}
    for layer in sorted(layer_case_counts):
        truth_tier, role, calibration = _classification(layer)
        scores = {
            policy: policy_weighted_hits[layer][policy] / len(layer_bases[layer])
            for policy in policies
        }
        distinct_scores = sorted({round(value, 12) for value in scores.values()})
        layer_summary[layer] = {
            "raw_cases": layer_case_counts[layer],
            "independent_base_scenarios": len(layer_bases[layer]),
            "variants_per_base": sorted(
                {base_counts[base] for base in layer_bases[layer]}
            ),
            "truth_tier": truth_tier,
            "selection_role": role,
            "effect_calibration": calibration,
            "discriminates_current_policy_set": len(distinct_scores) > 1,
            "distinct_base_weighted_hit_rates": distinct_scores,
            "base_weighted_hit_rate": {
                policy: round(value, 12) for policy, value in scores.items()
            },
        }

    expected_counts = {
        "L1_rule_constraints": (2, 2),
        "L3_dominance": (48, 6),
        "L4_exact_k_turn": (96, 12),
    }
    count_checks = {
        layer: {
            "expected_raw_cases": raw,
            "actual_raw_cases": layer_case_counts[layer],
            "expected_independent_bases": bases,
            "actual_independent_bases": len(layer_bases[layer]),
            "pass": layer_case_counts[layer] == raw
            and len(layer_bases[layer]) == bases,
        }
        for layer, (raw, bases) in expected_counts.items()
    }
    all_checks = [item["pass"] for item in count_checks.values()]
    all_checks.extend([schema_ok, baotou_owner_ok, len(detail) == bank.get("cases")])

    return {
        "schema": "sitin-opportunity-bank-integration/1",
        "status": (
            "ADMIT_AS_PROPOSAL_AND_REGRESSION_ASSET"
            if all(all_checks)
            else "REJECT_INTEGRATION_CONTRACT_MISMATCH"
        ),
        "provenance": {
            "source_branch": SOURCE_BRANCH,
            "source_commit": SOURCE_COMMIT,
            "source_bank": str(bank_path.relative_to(repo_root)),
            "source_bank_sha256": _sha256(bank_path),
        },
        "historical_regeneration": _corpus_availability(
            corpus_manifest, repo_root
        ),
        "scope": {
            "raw_cases": len(detail),
            "independent_base_scenarios": len(base_counts),
            "policies": policies,
        },
        "contract_checks": {
            "source_schema": bank.get("schema"),
            "source_case_count_matches_detail": len(detail) == bank.get("cases"),
            "layer_counts": count_checks,
            "current_scoring_schema": CURRENT_SCORING_SCHEMA,
            "current_scoring_schema_verified": schema_ok,
            "baotou_after_owned_by_hangma_verified": baotou_owner_ok,
        },
        "layer_summary": layer_summary,
        "observational_validity_evidence": {
            "selection_eligible": False,
            "reason": (
                "历史 kept/not_kept 分组同时受窗口类型、牌力和是否已胡等选择偏差影响；"
                "只作题库动机材料，不能估计动作因果收益。"
            ),
        },
        "fitness_decision": {
            "raw_total_hit_rate_eligible": False,
            "reason": (
                "146 题只有 20 个独立基础场景，且 L4 对全部当前策略无区分度；"
                "L3 尚未通过同墙配对反事实校准。"
            ),
            "next_calibration_family": "piao_with_baotou_after_true_multi_white",
        },
        "registry": registry,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--corpus-manifest", type=Path)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    bank_path = args.bank.resolve()
    corpus_manifest = (
        None if args.corpus_manifest is None else args.corpus_manifest.resolve()
    )
    output = integrate(bank_path, repo_root, corpus_manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        output["status"],
        "raw_cases=", output["scope"]["raw_cases"],
        "independent_bases=", output["scope"]["independent_base_scenarios"],
    )
    for layer, summary in output["layer_summary"].items():
        print(
            layer,
            "cases=", summary["raw_cases"],
            "bases=", summary["independent_base_scenarios"],
            "role=", summary["selection_role"],
            "discriminates=", summary["discriminates_current_policy_set"],
        )
    return 0 if output["status"] == "ADMIT_AS_PROPOSAL_AND_REGRESSION_ASSET" else 2


if __name__ == "__main__":
    raise SystemExit(main())
