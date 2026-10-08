"""R18 P4 跨手牌新隐藏集的一次性准入。"""

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
import asyncio
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import r18_multi_wealth_bank as bank  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.offline.opportunity_capability import (  # noqa: E402
    OpportunityCapabilityCase,
    OracleActionValue,
    evaluate_pair,
    summarize_family,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402


BANK_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-bank-01-20260922')
HIDDEN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-bank-01-20260922/hidden.json')
CANDIDATE = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
)
COUNTERFACTUAL = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-multishape-counterfactual-01-20260922/result.json')
)
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-hidden-admission-01-20260922')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> dict[str, str]:
    paths = (
        Path(__file__),
        _project_file(_PROJECT_ROOT, BANK_DIR / "manifest.json"),
        HIDDEN,
        _project_file(_PROJECT_ROOT, BANK_DIR / "development-score.json"),
        COUNTERFACTUAL,
        CANDIDATE,
    )
    return {str(path): digest(path) for path in paths}


def prepare() -> None:
    """冻结候选与判据；只读公开 manifest，不解析 hidden 内容。"""

    if OUT.exists():
        raise SystemExit("P4 跨手牌隐藏准入目录已存在；拒绝覆盖")
    bank_manifest = json.loads((_project_file(_PROJECT_ROOT, BANK_DIR / "manifest.json")).read_text(encoding="utf-8"))
    cf = json.loads(COUNTERFACTUAL.read_text(encoding="utf-8"))
    if cf.get("status") != "PASS_ALL_SHAPES_DIRECTION":
        raise ValueError("跨手牌反事实未通过，不能开启隐藏集")
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p4-shape-hidden-admission-manifest/1",
        "candidate_sha256": digest(CANDIDATE),
        "source_hashes": sources(),
        "public_hidden_counts": [
            row for row in bank_manifest["counts"] if row["split"] == "hidden"
        ],
        "pre_run_hidden_content_inspected": False,
        "one_shot": True,
        "pass_rule": {
            "all_scored": "16/16候选与基线均SCORED",
            "piao_generalization": "8/8隐藏piao题改善且候选最优",
            "control_stability": "4个take_hu和4个keep_wealth题均不改变首选",
            "no_regression": "全隐藏集capability_gain<0为0",
        },
        "on_pass": "P4获得跨手牌四财神飘机会精英资格；仍不覆盖keep_wealth或其他家族",
        "on_fail": "隐藏集视为消耗；不得围绕失败题修补后复用",
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED_WITHOUT_HIDDEN_PARSE"}, ensure_ascii=False))


def verify(manifest: dict[str, Any]) -> None:
    if manifest.get("source_hashes") != sources():
        raise ValueError("P4 跨手牌隐藏准入冻结来源漂移")


def load_hidden() -> tuple[list[OpportunityCapabilityCase], list[dict[str, Any]]]:
    doc = json.loads(HIDDEN.read_text(encoding="utf-8"))
    cases = []
    metadata = []
    for row in doc["cases"]:
        if bank.digest_value(row["request"]) != row["request_sha256"]:
            raise ValueError("隐藏题请求摘要不符")
        if bank.digest_value(row["reachability_witness"]) != row["reachability_witness_sha256"]:
            raise ValueError("隐藏题可达见证摘要不符")
        cases.append(OpportunityCapabilityCase(
            case_id=row["case_id"],
            base_scenario_id=row["base_scenario_id"],
            family=row["family"],
            split=row["split"],
            generator_seed=row["generator_seed"],
            rules_hash=row["rules_hash"],
            generator_sha256=row["generator_sha256"],
            oracle_version=row["oracle_version"],
            oracle_level=row["oracle_level"],
            request_sha256=row["request_sha256"],
            reachability_witness_sha256=row["reachability_witness_sha256"],
            request=decision_request_from_json(row["request"]),
            action_values=tuple(OracleActionValue(**item) for item in row["action_values"]),
        ))
        metadata.append({"decision_type": row["decision_type"]})
    return cases, metadata


async def evaluate() -> tuple[list[Any], list[dict[str, Any]]]:
    cases, metadata = load_hidden()
    candidate = ActionValuePolicy(ActionValueScorer(
        "r18-P4-shape-hidden", CANDIDATE.read_text(encoding="utf-8")
    ))
    baseline = ComparableHeuristicPolicyV2()
    rows = [
        await evaluate_pair(candidate, baseline, case, bank.budget) for case in cases
    ]
    return rows, metadata


def run() -> None:
    """一次性评价，并只输出按预声明题型聚合的结果。"""

    target = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if target.exists():
        raise SystemExit("P4 跨手牌隐藏集已执行；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(manifest)
    rows, metadata = asyncio.run(evaluate())
    summary = asdict(summarize_family(
        rows, family="multi_wealth_baotou", split="hidden"
    ))
    strata = defaultdict(lambda: {
        "cases": 0,
        "scored": 0,
        "changed": 0,
        "improved": 0,
        "regressed": 0,
        "candidate_optimal": 0,
        "baseline_optimal": 0,
        "capability_gain_sum": 0.0,
    })
    for row, meta in zip(rows, metadata):
        cell = strata[meta["decision_type"]]
        cell["cases"] += 1
        if row.capability_gain is not None:
            cell["scored"] += 1
            cell["capability_gain_sum"] += float(row.capability_gain)
            if row.capability_gain > 0:
                cell["improved"] += 1
            elif row.capability_gain < 0:
                cell["regressed"] += 1
        if row.candidate.chosen_action_key != row.baseline.chosen_action_key:
            cell["changed"] += 1
        if row.candidate.chosen_action_key in row.candidate.optimal_action_keys:
            cell["candidate_optimal"] += 1
        if row.baseline.chosen_action_key in row.baseline.optimal_action_keys:
            cell["baseline_optimal"] += 1
    expected = {"piao": 8, "take_hu": 4, "keep_wealth": 4}
    pass_hidden = (
        len(rows) == 16
        and all(strata[dtype]["scored"] == count for dtype, count in expected.items())
        and strata["piao"]["improved"] == 8
        and strata["piao"]["candidate_optimal"] == 8
        and strata["piao"]["regressed"] == 0
        and strata["take_hu"]["changed"] == 0
        and strata["keep_wealth"]["changed"] == 0
        and sum(cell["regressed"] for cell in strata.values()) == 0
    )
    result = {
        "schema": "r18-p4-shape-hidden-admission-result/1",
        "status": "PASS_P4_MULTISHAPE_HIDDEN" if pass_hidden else "FAIL_P4_MULTISHAPE_HIDDEN",
        "hidden_consumed": True,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": digest(CANDIDATE),
        "case_count": len(rows),
        "summary": summary,
        "strata": dict(sorted(strata.items())),
        "case_ids_emitted": False,
        "hands_emitted": False,
        "release_eligible": False,
        "next": (
            "冻结P4为跨手牌机会精英；下一代转攻四财神保财和三财神边界"
            if pass_hidden else
            "隐藏集已消耗；停止P4晋级并用全新开发/隐藏来源重构机制"
        ),
    }
    write_json(target, result)
    verify(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
