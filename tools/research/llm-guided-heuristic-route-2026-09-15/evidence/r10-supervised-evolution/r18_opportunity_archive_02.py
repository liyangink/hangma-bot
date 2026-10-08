"""把 P3 三财神飘专长并入 R18 第二版机会精英档案。"""

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


ARCHIVE1 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-01-20260922/result.json')
P4_TABLE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-table-preflight-01-20260922/result-v2.json')
P3_HIDDEN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-hidden-admission-01-20260922/result.json')
P3_PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/development-preflight-01/result.json')
P3_DIFF = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/development-preflight-01/parent-to-candidate.diff')
P3_TABLE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-table-preflight-02-20260922/result.json')
P3_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
P4_SOURCE = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
)
K3_SOURCE = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/K3/normalized-v2/candidate.py')
)
V2_SOURCE = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/heuristic_v2.py")
ARCHIVE_MODULE = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/offline/opportunity_archive.py")
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-02-20260922')

OBJECTIVES = (
    "multi_wealth_baotou/four_wealth_piao",
    "multi_wealth_baotou/four_wealth_take_hu",
    "multi_wealth_baotou/four_wealth_keep_wealth",
    "multi_wealth_baotou/three_wealth_piao",
    "multi_wealth_baotou/three_wealth_keep_wealth",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def score(
    objective_id: str,
    *,
    status: str,
    gain: float,
    regret: float,
    cases: int,
    counterfactual: bool,
    evidence: str,
) -> OpportunityObjectiveScore:
    return OpportunityObjectiveScore(
        objective_id=objective_id,
        family="multi_wealth_baotou",
        admission_status=status,
        mean_gain=gain,
        conservative_gain=gain,
        candidate_regret=regret,
        scored_base_scenarios=cases,
        expected_base_scenarios=cases,
        regression_count=0,
        paired_counterfactual_supported=counterfactual,
        evidence=evidence,
    )


def main() -> None:
    if OUT.exists():
        raise SystemExit("R18 第二版机会档案目录已存在；拒绝覆盖")
    archive1 = json.loads(ARCHIVE1.read_text(encoding="utf-8"))
    p4_table = json.loads(P4_TABLE.read_text(encoding="utf-8"))
    hidden = json.loads(P3_HIDDEN.read_text(encoding="utf-8"))
    preflight = json.loads(P3_PREFLIGHT.read_text(encoding="utf-8"))
    table = json.loads(P3_TABLE.read_text(encoding="utf-8"))
    if archive1.get("status") != "PASS_ARCHIVE_BOOTSTRAP":
        raise ValueError("第一版机会档案未通过")
    if hidden.get("status") != "PASS_P3_HIDDEN":
        raise ValueError("P3 隐藏准入未通过")
    if preflight.get("status") != "PASS_P3_DEVELOPMENT":
        raise ValueError("P3 开发/P4保持预检未通过")
    if table.get("status") != "PASS_R18_P3_TABLE_PREFLIGHT":
        raise ValueError("P3 完整桌安全预检未通过")
    if hidden.get("candidate_sha256") != digest(P3_SOURCE):
        raise ValueError("P3 源码与隐藏证据漂移")
    if hidden.get("parent_sha256") != digest(P4_SOURCE):
        raise ValueError("P3 父代不再是冻结 P4")
    if table.get("candidate_sha256") != digest(P3_SOURCE):
        raise ValueError("P3 源码与完整桌证据漂移")
    if not preflight["checks"].get("p4_bank_exactly_preserved"):
        raise ValueError("P3 没有证明 P4 开发行为保持")

    first_inputs = {
        row["candidate_id"]: row for row in archive1["candidate_inputs"]
    }
    first_p4 = first_inputs["r18-p4-four-wealth-piao"]
    first_v2 = first_inputs["stable-v2"]
    first_by_id_p4 = {
        row["objective_id"]: row for row in first_p4["objectives"]
    }
    first_by_id_v2 = {
        row["objective_id"]: row for row in first_v2["objectives"]
    }
    strata = hidden["strata"]
    three_piao = strata["three_wealth_piao"]
    three_keep = strata["three_wealth_keep"]
    four_keep = strata["four_wealth_keep"]
    p3_gain = (
        float(three_piao["capability_gain_sum"]) / int(three_piao["scored"])
    )
    three_keep_regret = (
        float(three_keep["candidate_regret_sum"]) / int(three_keep["scored"])
    )
    four_keep_regret = (
        float(four_keep["candidate_regret_sum"]) / int(four_keep["scored"])
    )
    four_piao_gain = float(
        first_by_id_p4["multi_wealth_baotou/four_wealth_piao"]["conservative_gain"]
    )

    baseline_scores = (
        score(OBJECTIVES[0], status="BASELINE_ANCHOR", gain=0.0,
              regret=four_piao_gain, cases=8, counterfactual=False,
              evidence="第一版档案稳定V2四财神隐藏锚点"),
        score(OBJECTIVES[1], status="BASELINE_ANCHOR", gain=0.0,
              regret=0.0, cases=4, counterfactual=False,
              evidence="第一版档案稳定V2四财神立即胡锚点"),
        score(OBJECTIVES[2], status="BASELINE_ANCHOR", gain=0.0,
              regret=four_keep_regret, cases=8, counterfactual=False,
              evidence="P3新隐藏集中的稳定V2/P4四财神保财锚点"),
        score(OBJECTIVES[3], status="BASELINE_ANCHOR", gain=0.0,
              regret=p3_gain, cases=8, counterfactual=False,
              evidence="P3新隐藏集中的稳定V2/P4三财神飘锚点"),
        score(OBJECTIVES[4], status="BASELINE_ANCHOR", gain=0.0,
              regret=three_keep_regret, cases=8, counterfactual=False,
              evidence="P3新隐藏集中的稳定V2/P4三财神保财锚点"),
    )
    p4_scores = (
        score(OBJECTIVES[0], status="SPECIALIST_PASS", gain=four_piao_gain,
              regret=0.0, cases=8, counterfactual=True,
              evidence="P4跨手牌隐藏与768对反事实"),
        score(OBJECTIVES[1], status="MEASURED", gain=0.0,
              regret=0.0, cases=4, counterfactual=False,
              evidence="P4四财神立即胡控制"),
        score(OBJECTIVES[2], status="MEASURED", gain=0.0,
              regret=four_keep_regret, cases=8, counterfactual=False,
              evidence="P3新隐藏集以P4作父代的四财神保财分层"),
        score(OBJECTIVES[3], status="MEASURED", gain=0.0,
              regret=p3_gain, cases=8, counterfactual=False,
              evidence="P3新隐藏集以P4作父代的三财神飘分层"),
        score(OBJECTIVES[4], status="MEASURED", gain=0.0,
              regret=three_keep_regret, cases=8, counterfactual=False,
              evidence="P3新隐藏集以P4作父代的三财神保财分层"),
    )
    p3_scores = (
        score(OBJECTIVES[0], status="SPECIALIST_PASS", gain=four_piao_gain,
              regret=0.0, cases=8, counterfactual=True,
              evidence="P4父代隐藏/反事实资格；P3源码差分限定wealth_count==3且P4开发48题逐点保持"),
        score(OBJECTIVES[1], status="MEASURED", gain=0.0,
              regret=0.0, cases=4, counterfactual=False,
              evidence="P3对P4四财神立即胡开发控制逐点保持"),
        score(OBJECTIVES[2], status="MEASURED", gain=0.0,
              regret=four_keep_regret, cases=8, counterfactual=False,
              evidence="P3新隐藏四财神保财分层与P4首选相同"),
        score(OBJECTIVES[3], status="SPECIALIST_PASS", gain=p3_gain,
              regret=0.0, cases=8, counterfactual=True,
              evidence="P3三财神飘隐藏8/8改善与6形状×32世界反事实"),
        score(OBJECTIVES[4], status="MEASURED", gain=0.0,
              regret=three_keep_regret, cases=8, counterfactual=False,
              evidence="P3新隐藏三财神保财分层与P4首选相同"),
    )

    candidates = (
        OpportunityArchiveCandidate(
            candidate_id="stable-v2",
            source_sha256=digest(V2_SOURCE),
            objectives=baseline_scores,
            table_safety=TableSafetyEvidence(
                status="BASELINE_ANCHOR", source_units=16, complete_tables=64,
                paired_score_delta_mean=0.0, execution_failure_count=0,
                evidence="P3完整桌同墙配对稳定V2锚点",
            ),
        ),
        OpportunityArchiveCandidate(
            candidate_id="r18-p4-four-wealth-piao",
            source_sha256=digest(P4_SOURCE),
            objectives=p4_scores,
            table_safety=TableSafetyEvidence(
                status="PASS_NONINFERIOR",
                source_units=int(p4_table["source_units"]),
                complete_tables=int(p4_table["tables"]),
                paired_score_delta_mean=float(p4_table["overall"]["stage_score_delta_mean"]),
                execution_failure_count=int(p4_table["action_value_failure_windows"]),
                evidence="P4 64张完整桌安全预检",
            ),
        ),
        OpportunityArchiveCandidate(
            candidate_id="r18-p3-three-and-four-wealth-piao",
            source_sha256=digest(P3_SOURCE),
            objectives=p3_scores,
            table_safety=TableSafetyEvidence(
                status="PASS_NONINFERIOR",
                source_units=int(table["source_units"]),
                complete_tables=int(table["tables"]),
                paired_score_delta_mean=float(table["overall"]["stage_score_delta_mean"]),
                execution_failure_count=int(table["action_value_failure_windows"]),
                evidence="P3 64张全新完整桌安全预检",
            ),
            author_cost_note="GLM 5.3单次低推理交付；成本只作诊断",
        ),
        OpportunityArchiveCandidate(
            candidate_id="r18-k3-zero-change-control",
            source_sha256=digest(K3_SOURCE),
            objectives=(),
            table_safety=TableSafetyEvidence(
                status="NOT_EVALUATED", source_units=0, complete_tables=0,
                paired_score_delta_mean=None, execution_failure_count=0,
                evidence="K3仍只有开发零变化结果",
            ),
        ),
    )
    archive = build_opportunity_archive(
        candidates,
        active_objective_ids=OBJECTIVES,
        baseline_candidate_id="stable-v2",
    )
    decisions = {row.candidate_id: row for row in archive.decisions}
    passed = (
        archive.pareto_elite_ids == ("r18-p3-three-and-four-wealth-piao",)
        and archive.lexicase_parent_ids == ("r18-p3-three-and-four-wealth-piao",)
        and decisions["r18-p4-four-wealth-piao"].dominated_by
        == ("r18-p3-three-and-four-wealth-piao",)
    )
    inputs = (
        Path(__file__), ARCHIVE_MODULE, ARCHIVE1, P4_TABLE, P3_HIDDEN,
        P3_PREFLIGHT, P3_DIFF, P3_TABLE, P3_SOURCE, P4_SOURCE, K3_SOURCE, V2_SOURCE,
    )
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-opportunity-archive-manifest/2",
        "source_hashes": {str(path.relative_to(ROOT)): digest(path) for path in inputs},
        "active_objective_ids": OBJECTIVES,
        "hidden_aggregate_only": True,
        "p4_inheritance_rule": "P3只新增wealth_count==3分支；父代差分与P4开发48题逐点保持共同支持四财神专长继承",
        "ranking_contract": "逐目标保守增益Pareto；目标轮流置首Lexicase；完整桌为安全门；成本不排序",
    })
    result = {
        "schema": "r18-opportunity-archive-result/2",
        "status": "PASS_ARCHIVE_P3_SUCCESSOR" if passed else "FAIL_ARCHIVE_P3_SUCCESSOR",
        "release_eligible": False,
        "archive": asdict(archive),
        "candidate_inputs": [asdict(row) for row in candidates],
        "findings": {
            "p3_dominates_p4_on_active_vector": bool(
                decisions["r18-p4-four-wealth-piao"].dominated_by
            ),
            "three_wealth_piao_hidden_mean_gain": p3_gain,
            "three_wealth_keep_gap_remains": three_keep_regret,
            "four_wealth_keep_gap_remains": four_keep_regret,
        },
        "next": (
            "冻结P3为当前机会父代；下一阶段扩展三/四财神牌局中段可达状态与自然机会频率"
            if passed else
            "停止晋级并检查P4资格继承或P3档案输入"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
