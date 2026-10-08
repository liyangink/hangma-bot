"""R18 P4 一次性隐藏题准入；候选冻结后才读取 hidden 题库。"""

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


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
BANK_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922')
HIDDEN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922/hidden.json')
PUBLIC_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922/manifest.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-hidden-admission-01-20260922')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def frozen_sources() -> dict[str, str]:
    """冻结候选、公开题库合同、开发效果与反事实校准。"""

    paths = (
        Path(__file__),
        CANDIDATE,
        PUBLIC_MANIFEST,
        HIDDEN,
        _project_file(_PROJECT_ROOT, AUTHOR / "normalized-v2-ingest-summary.json"),
        _project_file(_PROJECT_ROOT, AUTHOR / "development-preflight-v2.json"),
        _project_file(_PROJECT_ROOT, HERE / "r18-p4-counterfactual-pilot-01-20260922/result.json"),
        _project_file(_PROJECT_ROOT, HERE / "r18-p4-counterfactual-pilot-01-20260922/event-audit-v2.json"),
        _project_file(_PROJECT_ROOT, HERE / "r18-p4-tail-stress-01-20260922/result.json"),
    )
    return {str(path): digest(path) for path in paths}


def prepare() -> None:
    """只使用公开清单冻结判据；不解析 hidden 内容。"""

    if OUT.exists():
        raise SystemExit("P4 隐藏准入目录已存在；拒绝覆盖")
    public = json.loads(PUBLIC_MANIFEST.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p4-hidden-admission-manifest/1",
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
        "source_hashes": frozen_sources(),
        "hidden_cases_from_public_manifest": public["hidden_cases"],
        "public_hidden_strata": [
            row for row in public["counts"] if row["split"] == "hidden"
        ],
        "pre_run_hidden_content_inspected": False,
        "one_shot": True,
        "pass_rule": {
            "all_scored": "8/8候选与基线均SCORED",
            "no_regression": "capability_gain<0 为0题",
            "real_improvement": "capability_gain>0 至少1题",
            "mean_gain": "mean_capability_gain>0",
            "hit_rate": "candidate_optimal_hit_rate>baseline_optimal_hit_rate",
        },
        "on_fail": "本隐藏集视为已消耗；候选不得按失败题修补后复用本集准入",
        "on_pass": "只准进入正式策略接缝与完整桌赛非劣门，不直接发布",
        "table_strength_claim": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED_WITHOUT_HIDDEN_PARSE",
        "candidate_sha256": digest(CANDIDATE),
        "hidden_cases": public["hidden_cases"],
    }, ensure_ascii=False))


def verify(manifest: dict[str, Any]) -> None:
    if manifest.get("source_hashes") != frozen_sources():
        raise ValueError("P4 隐藏准入冻结来源漂移")


def load_hidden() -> tuple[list[OpportunityCapabilityCase], list[dict[str, Any]]]:
    """运行阶段才解析隐藏题，并核对请求与可达见证摘要。"""

    payload = json.loads(HIDDEN.read_text(encoding="utf-8"))
    cases = []
    metadata = []
    for row in payload["cases"]:
        if bank.digest_value(row["request"]) != row["request_sha256"]:
            raise RuntimeError("隐藏题 request 哈希不符")
        if (
            bank.digest_value(row["reachability_witness"])
            != row["reachability_witness_sha256"]
        ):
            raise RuntimeError("隐藏题可达见证哈希不符")
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
        metadata.append({
            "wealth_count": int(row["wealth_count"]),
            "decision_type": str(row["decision_type"]),
        })
    return cases, metadata


async def evaluate() -> tuple[list[Any], list[dict[str, Any]]]:
    cases, metadata = load_hidden()
    source = CANDIDATE.read_text(encoding="utf-8")
    candidate = ActionValuePolicy(ActionValueScorer("r18-P4-hidden", source))
    baseline = ComparableHeuristicPolicyV2()
    rows = [
        await evaluate_pair(candidate, baseline, case, bank.budget)
        for case in cases
    ]
    return rows, metadata


def run() -> None:
    """一次性执行并只输出聚合/分层计数，不落 case id、手牌或牌墙。"""

    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("P4 隐藏准入已执行；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(manifest)
    rows, metadata = asyncio.run(evaluate())
    summary = asdict(summarize_family(
        rows, family="multi_wealth_baotou", split="hidden"
    ))
    strata: dict[tuple[int, str], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "scored": 0,
            "changed": 0,
            "improved": 0,
            "regressed": 0,
            "candidate_optimal": 0,
            "baseline_optimal": 0,
            "candidate_regret_sum": 0.0,
            "baseline_regret_sum": 0.0,
        }
    )
    improved = regressed = changed = scored = 0
    for row, meta in zip(rows, metadata):
        cell = strata[(meta["wealth_count"], meta["decision_type"])]
        cell["count"] += 1
        if row.capability_gain is not None:
            scored += 1
            cell["scored"] += 1
            cell["candidate_regret_sum"] += float(row.candidate.regret)
            cell["baseline_regret_sum"] += float(row.baseline.regret)
            if row.capability_gain > 0:
                improved += 1
                cell["improved"] += 1
            elif row.capability_gain < 0:
                regressed += 1
                cell["regressed"] += 1
        if row.candidate.chosen_action_key != row.baseline.chosen_action_key:
            changed += 1
            cell["changed"] += 1
        if row.candidate.chosen_action_key in row.candidate.optimal_action_keys:
            cell["candidate_optimal"] += 1
        if row.baseline.chosen_action_key in row.baseline.optimal_action_keys:
            cell["baseline_optimal"] += 1
    pass_hidden = (
        scored == len(rows) == int(manifest["hidden_cases_from_public_manifest"])
        and regressed == 0
        and improved >= 1
        and summary["mean_capability_gain"] is not None
        and summary["mean_capability_gain"] > 0
        and summary["candidate_optimal_hit_rate"]
        > summary["baseline_optimal_hit_rate"]
    )
    result = {
        "schema": "r18-p4-hidden-admission-result/1",
        "status": "PASS_HIDDEN_OPPORTUNITY" if pass_hidden else "FAIL_HIDDEN_OPPORTUNITY",
        "hidden_consumed": True,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": digest(CANDIDATE),
        "case_count": len(rows),
        "scored_count": scored,
        "changed_count": changed,
        "improved_count": improved,
        "regressed_count": regressed,
        "summary": summary,
        "strata": [
            {"wealth_count": wealth, "decision_type": dtype, **values}
            for (wealth, dtype), values in sorted(strata.items())
        ],
        "case_ids_emitted": False,
        "hands_emitted": False,
        "table_strength_claim": False,
        "release_eligible": False,
        "next_gate": (
            "正式BotPolicy接缝与同牌墙换座完整桌赛非劣门"
            if pass_hidden else
            "废弃本隐藏集作准入；扩展新开发题并生成独立新隐藏集"
        ),
    }
    write_json(result_path, result)
    verify(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
