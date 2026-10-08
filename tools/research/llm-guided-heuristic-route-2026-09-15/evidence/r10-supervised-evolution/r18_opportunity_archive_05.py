"""把 P37 双财神与 P47 累计父代并入 R18 第五版机会档案。"""

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


ARCHIVE4 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-04-20260922/result.json')
P37_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p37-two-wealth-active-parent-01-20260922/candidate.py')
P40A = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40a-two-wealth-directed-confirmation-01-20260922/result.json')
P40B = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40b-two-wealth-table-confirmation-01-20260922/result.json')
P45_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p45-integrated-positive-parent-01-20260922/candidate.py')
P45 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p45-integrated-positive-parent-01-20260922/result.json')
P46 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p46-integrated-parent-table-safety-01-20260922/result.json')
P47 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p47-integrated-parent-registration-01-20260922/result.json')
ARCHIVE_MODULE = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/offline/opportunity_archive.py")
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-05-20260922')
TWO_WEALTH_OBJECTIVE = "multi_wealth_baotou/two_wealth_piao_keeps_baotou"
P37_ID = "r18-p37-two-wealth-baotou"
P47_ID = "r18-p47-integrated-positive"


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


def two_wealth_score(
    *, status: str, mean: float, conservative: float, regret: float,
    paired: bool, evidence: str,
) -> OpportunityObjectiveScore:
    """构造八根独立自然确认的双财神保爆头目标。"""

    return OpportunityObjectiveScore(
        objective_id=TWO_WEALTH_OBJECTIVE,
        family="multi_wealth_baotou",
        admission_status=status,
        mean_gain=mean,
        conservative_gain=conservative,
        candidate_regret=regret,
        scored_base_scenarios=8,
        expected_base_scenarios=8,
        regression_count=0,
        paired_counterfactual_supported=paired,
        evidence=evidence,
    )


def append_score(
    row: dict[str, Any], score: OpportunityObjectiveScore,
) -> OpportunityArchiveCandidate:
    """给第四版候选追加新目标，不改变既有七维证据。"""

    return OpportunityArchiveCandidate(
        candidate_id=str(row["candidate_id"]),
        source_sha256=str(row["source_sha256"]),
        objectives=tuple(objective(item) for item in row["objectives"]) + (score,),
        table_safety=table_safety(row["table_safety"]),
        author_cost_note=str(row.get("author_cost_note") or ""),
    )


def main() -> None:
    """复算八维 Pareto/Lexicase 档案并冻结强制继承合同。"""

    if OUT.exists():
        raise SystemExit("R18 第五版机会档案目录已存在；拒绝覆盖")
    archive4 = json.loads(ARCHIVE4.read_text(encoding="utf-8"))
    p40a = json.loads(P40A.read_text(encoding="utf-8"))
    p40b = json.loads(P40B.read_text(encoding="utf-8"))
    p45 = json.loads(P45.read_text(encoding="utf-8"))
    p46 = json.loads(P46.read_text(encoding="utf-8"))
    p47 = json.loads(P47.read_text(encoding="utf-8"))
    prerequisite_checks = {
        "archive4_passed": archive4.get("status") == "PASS_ARCHIVE_P8_SUCCESSOR",
        "p40a_passed": p40a.get("status") == "PASS_P40A_DIRECTED_CONFIRMATION",
        "p40b_passed": p40b.get("status") == "PASS_P40B_TABLE_CONFIRMATION",
        "p45_passed": p45.get("status") == "PASS_P45_INTEGRATED_PREFLIGHT",
        "p46_passed": p46.get("status") == "PASS_P46_INTEGRATED_TABLE_SAFETY",
        "p47_passed": p47.get("status") == "PASS_P47_INTEGRATED_PARENT_REGISTRATION",
        "p37_identity": p40a.get("candidate_sha256") == digest(P37_SOURCE),
        "p40b_identity": p40b.get("candidate_sha256") == digest(P37_SOURCE),
        "p45_identity": p45.get("candidate_sha256") == digest(P45_SOURCE),
        "p46_identity": p46.get("candidate_sha256") == digest(P45_SOURCE),
        "p47_identity": p47.get("candidate_sha256") == digest(P45_SOURCE),
        "p45_inheritance_checks_all": all((p45.get("checks") or {}).values()),
        "p46_safety_checks_all": all((p46.get("gate_checks") or {}).values()),
    }
    if not all(prerequisite_checks.values()):
        raise ValueError("第五版档案前置证据失败：" + repr(prerequisite_checks))

    mean_gain = float(p40a["aggregate"]["mean_current_round_settlement_delta"])
    conservative_gain = float(p40a["aggregate"]["bootstrap_95"][0])
    baseline_two = two_wealth_score(
        status="BASELINE_ANCHOR", mean=0.0, conservative=0.0,
        regret=conservative_gain, paired=False,
        evidence="P40a八根独立自然确认中的稳定P5锚点",
    )
    measured_two = two_wealth_score(
        status="MEASURED", mean=0.0, conservative=0.0,
        regret=conservative_gain, paired=False,
        evidence="P40a以前的候选未实现双财神保爆头覆盖",
    )
    specialist_two = two_wealth_score(
        status="SPECIALIST_PASS", mean=mean_gain,
        conservative=conservative_gain, regret=0.0, paired=True,
        evidence=(
            "P40a全新自然根8/8为正并且bootstrap下界大于零；"
            "P40b另一全新seed的2,048桌自然触发12次并通过非劣门"
        ),
    )

    old_rows = {row["candidate_id"]: row for row in archive4["candidate_inputs"]}
    inherited = []
    for row in archive4["candidate_inputs"]:
        inherited.append(append_score(
            row,
            baseline_two if row["candidate_id"] == "stable-v2" else measured_two,
        ))

    p5_row = old_rows["r18-p5-added-gang-strict-dominance"]
    p8_row = old_rows["r18-p8-dealer-initial-seven-pairs"]
    p37 = OpportunityArchiveCandidate(
        candidate_id=P37_ID,
        source_sha256=digest(P37_SOURCE),
        objectives=tuple(objective(item) for item in p5_row["objectives"]) + (
            specialist_two,
        ),
        table_safety=TableSafetyEvidence(
            status="PASS_NONINFERIOR",
            source_units=int(p40b["source_units"]),
            complete_tables=int(p40b["tables"]),
            paired_score_delta_mean=float(p40b["overall"]["stage_score_delta_mean"]),
            execution_failure_count=int(p40b["action_value_failure_windows"]),
            evidence=(
                "P40b相对P5的2,048张全新同墙换座确认；"
                "512来源均值+0.421875，95%区间下界+0.0546875"
            ),
        ),
        author_cost_note="机械窄覆盖；作者模型只参与更早候选探索，不计入当前合并",
    )
    p47_objectives = tuple(
        replace(
            objective(item),
            evidence=objective(item).evidence + "；P45/P46证明P47累计继承且零回归",
        )
        for item in p8_row["objectives"]
    ) + (replace(
        specialist_two,
        evidence=specialist_two.evidence + "；P46另在新完整桌自然触发5次且与P37同轨迹",
    ),)
    p47_candidate = OpportunityArchiveCandidate(
        candidate_id=P47_ID,
        source_sha256=digest(P45_SOURCE),
        objectives=p47_objectives,
        table_safety=TableSafetyEvidence(
            status="PASS_NONINFERIOR",
            source_units=int(p40b["source_units"]),
            complete_tables=int(p40b["tables"]) + int(p46["tables"]),
            paired_score_delta_mean=float(p40b["overall"]["stage_score_delta_mean"]),
            execution_failure_count=(
                int(p40b["action_value_failure_windows"])
                + int(p46["action_value_failure_windows"])
            ),
            evidence=(
                "P40b确认双财神父代相对P5非劣；P46再以2,048张新桌证明"
                "P47相对P37的512/512来源积分轨迹完全相同"
            ),
        ),
        author_cost_note="确定性谱系合并；零模型作者调用",
    )

    candidates = tuple(inherited) + (p37, p47_candidate)
    active_objectives = tuple(archive4["archive"]["active_objective_ids"]) + (
        TWO_WEALTH_OBJECTIVE,
    )
    archive = build_opportunity_archive(
        candidates,
        active_objective_ids=active_objectives,
        baseline_candidate_id="stable-v2",
    )
    decisions = {row.candidate_id: row for row in archive.decisions}
    passed = (
        archive.pareto_elite_ids == (P47_ID,)
        and archive.lexicase_parent_ids == (P47_ID,)
        and decisions[P37_ID].dominated_by == (P47_ID,)
        and decisions["r18-p8-dealer-initial-seven-pairs"].dominated_by == (P47_ID,)
    )

    inputs = (
        Path(__file__), ARCHIVE_MODULE, ARCHIVE4, P37_SOURCE, P40A, P40B,
        P45_SOURCE, P45, P46, P47,
    )
    OUT.mkdir(parents=True)
    inheritance_contract = {
        "schema": "r18-capability-inheritance-contract/1",
        "active_parent_id": P47_ID,
        "active_parent_sha256": digest(P45_SOURCE),
        "locked_objective_ids": list(active_objectives),
        "default_successor_rule": (
            "任何新家族候选必须在全部既有能力视图上保持完整ScoreBatch和首选动作一致；"
            "若要修改既有目标，必须先冻结该目标的新开发/隐藏/配对反事实证据并显式列为替代目标"
        ),
        "required_suites": {
            "capability_and_boundary_views": {
                "result_path": str(P45.relative_to(ROOT)),
                "result_sha256": digest(P45),
                "views": int(p45["dynamic_views"]),
                "groups": p45["dynamic_groups"],
            },
            "fresh_table_safety": {
                "result_path": str(P46.relative_to(ROOT)),
                "result_sha256": digest(P46),
                "tables": int(p46["tables"]),
                "source_units": int(p46["source_units"]),
            },
            "formal_policy_replay": {
                "result_path": str(P47.relative_to(ROOT)),
                "result_sha256": digest(P47),
                "requests": int(p47["choose_replay"]["requests"]),
            },
        },
        "author_parent_rule": "新作者任务只能以active_parent_sha256对应源码为父代",
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "inheritance-contract.json"), inheritance_contract)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-opportunity-archive-manifest/5",
        "source_hashes": {str(path.relative_to(ROOT)): digest(path) for path in inputs},
        "active_objective_ids": active_objectives,
        "inheritance_contract_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "inheritance-contract.json")),
        "ranking_contract": (
            "逐目标保守增益Pareto；目标轮流置首Lexicase；完整桌为安全门；"
            "作者成本不排序；父代身份与既有能力继承另由inheritance-contract强制"
        ),
    })
    result = {
        "schema": "r18-opportunity-archive-result/5",
        "status": "PASS_ARCHIVE_P47_SUCCESSOR" if passed else "FAIL_ARCHIVE_P47_SUCCESSOR",
        "release_eligible": False,
        "prerequisite_checks": prerequisite_checks,
        "archive": asdict(archive),
        "candidate_inputs": [asdict(row) for row in candidates],
        "findings": {
            "p47_dominates_p8": decisions["r18-p8-dealer-initial-seven-pairs"].dominated_by == (P47_ID,),
            "p47_dominates_p37": decisions[P37_ID].dominated_by == (P47_ID,),
            "two_wealth_independent_mean_gain": mean_gain,
            "two_wealth_independent_conservative_gain": conservative_gain,
            "p47_exact_table_units_vs_p37": int(p46["overall"]["score_trajectory_equal_units"]),
            "p47_formal_replay_requests": int(p47["choose_replay"]["requests"]),
        },
        "next": (
            "所有新作者任务改用P47摘要；先过强制能力继承门，再开放新目标开发/隐藏门"
            if passed else "停止新作者调用并检查双财神证据继承、P45合并或P46安全门"
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
