"""用冻结隐藏题和完整桌证据建立 R18 首份机会优先研究档案。"""

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

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.offline.opportunity_archive import (  # noqa: E402
    OpportunityArchiveCandidate,
    OpportunityObjectiveScore,
    TableSafetyEvidence,
    build_opportunity_archive,
)


P4 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
K3 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/K3/normalized-v2/candidate.py')
V2 = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/heuristic_v2.py")
ARCHIVE_MODULE = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/offline/opportunity_archive.py")
HIDDEN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-hidden-admission-01-20260922/result.json')
COUNTERFACTUAL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-multishape-counterfactual-01-20260922/result.json')
TABLE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-table-preflight-01-20260922/result-v2.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-01-20260922')

OBJECTIVES = (
    "multi_wealth_baotou/four_wealth_piao",
    "multi_wealth_baotou/four_wealth_take_hu",
    "multi_wealth_baotou/four_wealth_keep_wealth",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def source_paths() -> tuple[Path, ...]:
    return (
        Path(__file__), ARCHIVE_MODULE, P4, K3, V2,
        HIDDEN, COUNTERFACTUAL, TABLE,
    )


def score(
    objective_id: str,
    *,
    status: str,
    mean_gain: float,
    candidate_regret: float,
    cases: int,
    counterfactual: bool,
    evidence: str,
) -> OpportunityObjectiveScore:
    return OpportunityObjectiveScore(
        objective_id=objective_id,
        family="multi_wealth_baotou",
        admission_status=status,
        mean_gain=mean_gain,
        conservative_gain=mean_gain,
        candidate_regret=candidate_regret,
        scored_base_scenarios=cases,
        expected_base_scenarios=cases,
        regression_count=0,
        paired_counterfactual_supported=counterfactual,
        evidence=evidence,
    )


def main() -> None:
    """冻结输入摘要并生成首份可机器复算的机会精英档案。"""

    if OUT.exists():
        raise SystemExit("R18 机会档案目录已存在；拒绝覆盖")
    hidden = json.loads(HIDDEN.read_text(encoding="utf-8"))
    counterfactual = json.loads(COUNTERFACTUAL.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    if hidden.get("status") != "PASS_P4_MULTISHAPE_HIDDEN":
        raise ValueError("P4 跨手牌隐藏准入未通过")
    if counterfactual.get("status") != "PASS_ALL_SHAPES_DIRECTION":
        raise ValueError("P4 跨手牌配对反事实未通过")
    if table.get("status") != "PASS_R18_P4_TABLE_PREFLIGHT":
        raise ValueError("P4 完整桌安全预检未通过")
    if hidden.get("candidate_sha256") != digest(P4):
        raise ValueError("P4 源码与隐藏证据不再一致")
    if table.get("candidate_sha256") != digest(P4):
        raise ValueError("P4 源码与完整桌证据不再一致")

    strata = hidden["strata"]
    piao = strata["piao"]
    take_hu = strata["take_hu"]
    keep = strata["keep_wealth"]
    hidden_summary = hidden["summary"]
    total_candidate_regret = (
        float(hidden_summary["mean_candidate_regret"])
        * int(hidden_summary["scored_base_scenario_count"])
    )
    # piao 与 take_hu 的候选在全部题上最优，因此隐藏总 regret 全部来自 keep。
    keep_candidate_regret = total_candidate_regret / int(keep["scored"])
    piao_gain = float(piao["capability_gain_sum"]) / int(piao["scored"])

    baseline_scores = (
        score(
            OBJECTIVES[0], status="BASELINE_ANCHOR", mean_gain=0.0,
            candidate_regret=piao_gain, cases=int(piao["scored"]),
            counterfactual=False, evidence="稳定 V2 隐藏集锚点",
        ),
        score(
            OBJECTIVES[1], status="BASELINE_ANCHOR", mean_gain=0.0,
            candidate_regret=0.0, cases=int(take_hu["scored"]),
            counterfactual=False, evidence="稳定 V2 隐藏集锚点",
        ),
        score(
            OBJECTIVES[2], status="BASELINE_ANCHOR", mean_gain=0.0,
            candidate_regret=keep_candidate_regret, cases=int(keep["scored"]),
            counterfactual=False, evidence="稳定 V2 隐藏集锚点",
        ),
    )
    p4_scores = (
        score(
            OBJECTIVES[0], status="SPECIALIST_PASS", mean_gain=piao_gain,
            candidate_regret=0.0, cases=int(piao["scored"]),
            counterfactual=True,
            evidence="P4 跨手牌隐藏准入与 12 形状 × 64 世界配对反事实",
        ),
        score(
            OBJECTIVES[1], status="MEASURED", mean_gain=0.0,
            candidate_regret=0.0, cases=int(take_hu["scored"]),
            counterfactual=False, evidence="P4 跨手牌隐藏 take_hu 分层",
        ),
        score(
            OBJECTIVES[2], status="MEASURED", mean_gain=0.0,
            candidate_regret=keep_candidate_regret, cases=int(keep["scored"]),
            counterfactual=False,
            evidence="P4 跨手牌隐藏 keep_wealth 分层；仍有绝对 regret",
        ),
    )

    candidates = (
        OpportunityArchiveCandidate(
            candidate_id="stable-v2",
            source_sha256=digest(V2),
            objectives=baseline_scores,
            table_safety=TableSafetyEvidence(
                status="BASELINE_ANCHOR",
                source_units=16,
                complete_tables=64,
                paired_score_delta_mean=0.0,
                execution_failure_count=0,
                evidence="P4 完整桌同墙配对的稳定 V2 锚点",
            ),
        ),
        OpportunityArchiveCandidate(
            candidate_id="r18-p4-four-wealth-piao",
            source_sha256=digest(P4),
            objectives=p4_scores,
            table_safety=TableSafetyEvidence(
                status="PASS_NONINFERIOR",
                source_units=int(table["source_units"]),
                complete_tables=int(table["tables"]),
                paired_score_delta_mean=float(table["overall"]["stage_score_delta_mean"]),
                execution_failure_count=int(table["action_value_failure_windows"]),
                evidence="R18 P4 64 张完整桌安全预检 result-v2",
            ),
            author_cost_note="作者成本只作诊断，不进入能力排序",
        ),
        OpportunityArchiveCandidate(
            candidate_id="r18-k3-zero-change-control",
            source_sha256=digest(K3),
            objectives=(),
            table_safety=TableSafetyEvidence(
                status="NOT_EVALUATED",
                source_units=0,
                complete_tables=0,
                paired_score_delta_mean=None,
                execution_failure_count=0,
                evidence="K3 仅有开发零变化结果，未消费隐藏准入和完整桌安全门",
            ),
            author_cost_note="保留为高风险阈值的零变化控制",
        ),
    )
    archive = build_opportunity_archive(
        candidates,
        active_objective_ids=OBJECTIVES,
        baseline_candidate_id="stable-v2",
    )
    decisions = {item.candidate_id: item for item in archive.decisions}
    passed = (
        archive.pareto_elite_ids == ("r18-p4-four-wealth-piao",)
        and archive.lexicase_parent_ids == ("r18-p4-four-wealth-piao",)
        and decisions["stable-v2"].dominated_by == ("r18-p4-four-wealth-piao",)
        and decisions["r18-k3-zero-change-control"].eligible is False
    )

    source_hashes = {str(path.relative_to(ROOT)): digest(path) for path in source_paths()}
    manifest = {
        "schema": "r18-opportunity-archive-manifest/1",
        "source_hashes": source_hashes,
        "active_objective_ids": OBJECTIVES,
        "hidden_case_content_read": False,
        "hidden_aggregate_only": True,
        "ranking_contract": {
            "capability": "逐目标 conservative_gain Pareto；禁止跨目标求总均分",
            "parent_pool": "每个目标轮流置首的确定性 Lexicase 并集",
            "table_safety": "完整桌实质退化、未评价或执行失败退出",
            "cost": "仅诊断，不进入能力排序",
        },
    }
    result = {
        "schema": "r18-opportunity-archive-result/1",
        "status": "PASS_ARCHIVE_BOOTSTRAP" if passed else "FAIL_ARCHIVE_BOOTSTRAP",
        "release_eligible": False,
        "archive": asdict(archive),
        "candidate_inputs": [asdict(item) for item in candidates],
        "findings": {
            "p4_preserved_as_specialist": decisions["r18-p4-four-wealth-piao"].pareto_elite,
            "stable_v2_dominated_on_active_vector": bool(decisions["stable-v2"].dominated_by),
            "k3_not_misreported_as_improvement": not decisions["r18-k3-zero-change-control"].eligible,
            "p4_keep_wealth_gap_remains": keep_candidate_regret,
            "p4_piao_hidden_mean_gain": piao_gain,
        },
        "next": (
            "冻结四财神保财与三财神新开发/隐藏来源，并让新候选在全部活跃目标上复算"
            if passed else
            "停止作者调用并修复机会档案输入或裁定合同"
        ),
    }
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    result["manifest_sha256"] = digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
