"""把 P8 已验证起手域七对专长并入 R18 第四版机会档案。"""

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

from dataclasses import asdict, replace
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


ARCHIVE3 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-03-20260922/result.json')
P8_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922/generation/candidate.py')
P8_DEVELOPMENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922/development-preflight-01/result.json')
P8_HISTORICAL_HIDDEN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-historical-hidden-regression-01-20260922/result.json')
P8_BOUNDARY = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922/natural-boundary-regression-01/result.json')
P7_COUNTERFACTUAL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p7-counterfactual-pilot-01-20260922/result.json')
P8_TABLE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-table-safety-01-20260922/result.json')
ARCHIVE_MODULE = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/offline/opportunity_archive.py")
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-04-20260922')
SEVEN_OBJECTIVE = "seven_pairs_closed/dealer_initial_tradeoff"


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def objective(row: dict[str, Any]) -> OpportunityObjectiveScore:
    """重建上一版机会目标值对象。"""

    return OpportunityObjectiveScore(**row)


def table_safety(row: dict[str, Any]) -> TableSafetyEvidence:
    """重建上一版完整桌安全值对象。"""

    return TableSafetyEvidence(**row)


def inherited_candidate(
    row: dict[str, Any], seven_score: OpportunityObjectiveScore,
) -> OpportunityArchiveCandidate:
    """给上一版候选补齐新七对目标，不改变既有六维证据。"""

    return OpportunityArchiveCandidate(
        candidate_id=str(row["candidate_id"]),
        source_sha256=str(row["source_sha256"]),
        objectives=tuple(objective(item) for item in row["objectives"]) + (seven_score,),
        table_safety=table_safety(row["table_safety"]),
        author_cost_note=str(row.get("author_cost_note") or ""),
    )


def seven_score(
    *, status: str, gain: float, regret: float, paired: bool, evidence: str,
) -> OpportunityObjectiveScore:
    """构造 16 个历史隐藏七对取舍状态的目标值。"""

    return OpportunityObjectiveScore(
        objective_id=SEVEN_OBJECTIVE,
        family="seven_pairs_closed",
        admission_status=status,
        mean_gain=gain,
        conservative_gain=gain,
        candidate_regret=regret,
        scored_base_scenarios=16,
        expected_base_scenarios=16,
        regression_count=0,
        paired_counterfactual_supported=paired,
        evidence=evidence,
    )


def main() -> None:
    """复算七维 Pareto/Lexicase 档案。"""

    if OUT.exists():
        raise SystemExit("R18 第四版机会档案目录已存在；拒绝覆盖")
    archive3 = json.loads(ARCHIVE3.read_text(encoding="utf-8"))
    development = json.loads(P8_DEVELOPMENT.read_text(encoding="utf-8"))
    historical_hidden = json.loads(P8_HISTORICAL_HIDDEN.read_text(encoding="utf-8"))
    boundary = json.loads(P8_BOUNDARY.read_text(encoding="utf-8"))
    counterfactual = json.loads(P7_COUNTERFACTUAL.read_text(encoding="utf-8"))
    table = json.loads(P8_TABLE.read_text(encoding="utf-8"))
    if archive3.get("status") != "PASS_ARCHIVE_P5_SUCCESSOR":
        raise ValueError("第三版 P5 机会档案未通过")
    if development.get("status") != "PASS_P8_DEVELOPMENT":
        raise ValueError("P8 开发题回归未通过")
    if historical_hidden.get("status") != "PASS_P8_HISTORICAL_HIDDEN_REGRESSION":
        raise ValueError("P8 历史隐藏继承回归未通过")
    if boundary.get("status") != "PASS_P8_NATURAL_BOUNDARY":
        raise ValueError("P8 自然越域边界回归未通过")
    if counterfactual.get("status") != "PASS_MECHANICS" or counterfactual.get("direction") != "SUPPORT":
        raise ValueError("P7/P8 起手域完整世界反事实不支持")
    if table.get("status") != "PASS_R18_P8_TABLE_SAFETY":
        raise ValueError("P8 独立完整桌安全回归未通过")
    if historical_hidden.get("candidate_sha256") != digest(P8_SOURCE):
        raise ValueError("P8 源码与历史隐藏回归漂移")
    if table.get("candidate_sha256") != digest(P8_SOURCE):
        raise ValueError("P8 源码与完整桌安全回归漂移")

    hidden_target = historical_hidden["by_type"]["seven_pairs_tradeoff"]
    hidden_gain = float(hidden_target["mean_capability_gain"])
    if (
        int(hidden_target["cases"]) != 16
        or int(hidden_target["candidate_optimal_hits"]) != 16
        or int(hidden_target["parent_optimal_hits"]) != 0
    ):
        raise ValueError("P8 七对隐藏目标不完整")
    baseline_seven = seven_score(
        status="BASELINE_ANCHOR",
        gain=0.0,
        regret=hidden_gain,
        paired=False,
        evidence="P8历史隐藏七对取舍中的稳定V2/P5锚点",
    )
    measured_seven = seven_score(
        status="MEASURED",
        gain=0.0,
        regret=hidden_gain,
        paired=False,
        evidence="P8历史隐藏七对取舍中的旧候选锚点；未实现起手七对价值覆盖",
    )
    specialist_seven = seven_score(
        status="SPECIALIST_PASS",
        gain=hidden_gain,
        regret=0.0,
        paired=True,
        evidence=(
            "P7冻结隐藏16/16改善；P8在该已验证域逐点评分等价继承；"
            "16种起手×32完整世界方向支持；29个自然中后段反例严格回退P5"
        ),
    )

    old_rows = {row["candidate_id"]: row for row in archive3["candidate_inputs"]}
    ordered_ids = (
        "stable-v2",
        "r18-p4-four-wealth-piao",
        "r18-p3-three-and-four-wealth-piao",
        "r18-p5-added-gang-strict-dominance",
        "r18-k3-zero-change-control",
    )
    inherited = []
    for candidate_id in ordered_ids:
        inherited.append(inherited_candidate(
            old_rows[candidate_id],
            baseline_seven if candidate_id == "stable-v2" else measured_seven,
        ))
    p5 = inherited[3]
    p8_objectives = tuple(
        replace(
            score,
            evidence=score.evidence + "；P8在自然越域反例和512张全新完整桌保持P5",
        )
        for score in p5.objectives[:-1]
    ) + (specialist_seven,)
    p8 = OpportunityArchiveCandidate(
        candidate_id="r18-p8-dealer-initial-seven-pairs",
        source_sha256=digest(P8_SOURCE),
        objectives=p8_objectives,
        table_safety=TableSafetyEvidence(
            status="PASS_NONINFERIOR",
            source_units=int(table["source_units"]),
            complete_tables=int(table["tables"]),
            paired_score_delta_mean=float(table["overall"]["stage_score_delta_mean"]),
            execution_failure_count=int(table["action_value_failure_windows"]),
            evidence="P8相对P5的512张全新同墙换座安全回归；128/128来源单元积分轨迹相同",
        ),
        author_cost_note="由P7越域反例机械收紧；零模型作者调用",
    )
    candidates = tuple(inherited[:4]) + (p8, inherited[4])
    active_objectives = tuple(archive3["archive"]["active_objective_ids"]) + (SEVEN_OBJECTIVE,)
    archive = build_opportunity_archive(
        candidates,
        active_objective_ids=active_objectives,
        baseline_candidate_id="stable-v2",
    )
    decisions = {row.candidate_id: row for row in archive.decisions}
    passed = (
        archive.pareto_elite_ids == ("r18-p8-dealer-initial-seven-pairs",)
        and archive.lexicase_parent_ids == ("r18-p8-dealer-initial-seven-pairs",)
        and decisions["r18-p5-added-gang-strict-dominance"].dominated_by
        == ("r18-p8-dealer-initial-seven-pairs",)
    )
    inputs = (
        Path(__file__), ARCHIVE_MODULE, ARCHIVE3, P8_SOURCE, P8_DEVELOPMENT,
        P8_HISTORICAL_HIDDEN, P8_BOUNDARY, P7_COUNTERFACTUAL, P8_TABLE,
    )
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-opportunity-archive-manifest/4",
        "source_hashes": {str(path.relative_to(ROOT)): digest(path) for path in inputs},
        "active_objective_ids": active_objectives,
        "historical_hidden_inheritance": "P8只增加公开可见的已验证起手域边界；在P7冻结隐藏24题上逐点评分与P7等价，不把已打开题重新冒充新隐藏",
        "ranking_contract": "逐目标保守增益Pareto；目标轮流置首Lexicase；完整桌为安全门；成本不排序",
    })
    result = {
        "schema": "r18-opportunity-archive-result/4",
        "status": "PASS_ARCHIVE_P8_SUCCESSOR" if passed else "FAIL_ARCHIVE_P8_SUCCESSOR",
        "release_eligible": False,
        "archive": asdict(archive),
        "candidate_inputs": [asdict(row) for row in candidates],
        "findings": {
            "p8_dominates_p5_on_active_vector": bool(
                decisions["r18-p5-added-gang-strict-dominance"].dominated_by
            ),
            "seven_pairs_hidden_mean_gain": hidden_gain,
            "seven_pairs_counterfactual_mean_score_gain": float(
                counterfactual["summary"]["overall_mean_candidate_minus_parent"]
            ),
            "seven_pairs_counterfactual_bootstrap_lower": float(
                counterfactual["summary"]["overall_bootstrap_mean_95_interval"][0]
            ),
            "natural_midgame_regressions_exact_p5": int(boundary["cases"]),
            "fresh_table_equal_source_units": int(table["overall"]["score_trajectory_equal_units"]),
        },
        "next": (
            "冻结P8为当前机会研究父代；建立可重采样的中后段七对完整世界题库，验证后再扩大P8作用域"
            if passed else "停止晋级并检查P5继承、P8边界或七对档案输入"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"],
        "pareto_elite_ids": archive.pareto_elite_ids,
        "lexicase_parent_ids": archive.lexicase_parent_ids,
        "findings": result["findings"],
        "next": result["next"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
