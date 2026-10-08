"""把 P5 补杠严格支配专长并入 R18 第三版机会精英档案。"""

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


ARCHIVE2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-02-20260922/result.json')
P5_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
P5_PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/development-preflight-02/result.json')
P5_HIDDEN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-hidden-admission-01-20260922/result.json')
P5_TABLE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-table-safety-01-20260922/result.json')
ARCHIVE_MODULE = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/offline/opportunity_archive.py")
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-03-20260922')
GANG_OBJECTIVE = "gang_chain/added_gang_strict_dominance"


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
    """从上一版档案的稳定 JSON 重建机会目标值对象。"""

    return OpportunityObjectiveScore(**row)


def table_safety(row: dict[str, Any]) -> TableSafetyEvidence:
    """从上一版档案的稳定 JSON 重建完整桌安全值对象。"""

    return TableSafetyEvidence(**row)


def inherited_candidate(
    row: dict[str, Any], gang_score: OpportunityObjectiveScore,
) -> OpportunityArchiveCandidate:
    """给上一版候选补齐新杠链目标；不改变其既有五维证据。"""

    return OpportunityArchiveCandidate(
        candidate_id=str(row["candidate_id"]),
        source_sha256=str(row["source_sha256"]),
        objectives=tuple(objective(item) for item in row["objectives"]) + (gang_score,),
        table_safety=table_safety(row["table_safety"]),
        author_cost_note=str(row.get("author_cost_note") or ""),
    )


def gang_score(
    *, status: str, gain: float, conservative: float, regret: float,
    paired: bool, evidence: str,
) -> OpportunityObjectiveScore:
    """构造七个新隐藏自然状态对应的杠链机会目标。"""

    return OpportunityObjectiveScore(
        objective_id=GANG_OBJECTIVE,
        family="gang_chain",
        admission_status=status,
        mean_gain=gain,
        conservative_gain=conservative,
        candidate_regret=regret,
        scored_base_scenarios=7,
        expected_base_scenarios=7,
        regression_count=0,
        paired_counterfactual_supported=paired,
        evidence=evidence,
    )


def main() -> None:
    if OUT.exists():
        raise SystemExit("R18 第三版机会档案目录已存在；拒绝覆盖")
    archive2 = json.loads(ARCHIVE2.read_text(encoding="utf-8"))
    preflight = json.loads(P5_PREFLIGHT.read_text(encoding="utf-8"))
    hidden = json.loads(P5_HIDDEN.read_text(encoding="utf-8"))
    table = json.loads(P5_TABLE.read_text(encoding="utf-8"))
    if archive2.get("status") != "PASS_ARCHIVE_P3_SUCCESSOR":
        raise ValueError("第二版 P3 机会档案未通过")
    if preflight.get("status") != "PASS_P5_DEVELOPMENT":
        raise ValueError("P5 开发预检未通过")
    if hidden.get("status") != "PASS_P5_HIDDEN":
        raise ValueError("P5 新来源机会准入未通过")
    if table.get("status") != "PASS_R18_P5_TABLE_SAFETY":
        raise ValueError("P5 完整桌安全门未通过")
    if hidden.get("candidate_sha256") != digest(P5_SOURCE):
        raise ValueError("P5 源码与隐藏准入证据漂移")
    if table.get("candidate_sha256") != digest(P5_SOURCE):
        raise ValueError("P5 源码与完整桌证据漂移")

    gains = [float(value) for value in hidden["strict_evidence"]["local_gains"]]
    if len(gains) != 7 or any(value <= 0 for value in gains):
        raise ValueError("P5 隐藏严格支配增益不完整")
    mean_gain = sum(gains) / len(gains)
    conservative_gain = min(gains)
    baseline_gang = gang_score(
        status="BASELINE_ANCHOR",
        gain=0.0,
        conservative=0.0,
        regret=mean_gain,
        paired=False,
        evidence="P5新来源隐藏集中的稳定V2/P3立即胡锚点",
    )
    measured_gang = gang_score(
        status="MEASURED",
        gain=0.0,
        conservative=0.0,
        regret=mean_gain,
        paired=False,
        evidence="P5新来源隐藏集中的P3立即胡锚点；尚无补杠严格支配覆盖",
    )
    specialist_gang = gang_score(
        status="SPECIALIST_PASS",
        gain=mean_gain,
        conservative=conservative_gain,
        regret=0.0,
        paired=True,
        evidence="7个新自然来源根全部命中；规则支配证明与4状态×32未来墙复核支持",
    )

    old_rows = {
        row["candidate_id"]: row for row in archive2["candidate_inputs"]
    }
    inherited = []
    for candidate_id in (
        "stable-v2",
        "r18-p4-four-wealth-piao",
        "r18-p3-three-and-four-wealth-piao",
        "r18-k3-zero-change-control",
    ):
        row = old_rows[candidate_id]
        if candidate_id == "stable-v2":
            extra = baseline_gang
        else:
            extra = measured_gang
        inherited.append(inherited_candidate(row, extra))
    p3 = inherited[2]
    p5_objectives = tuple(
        replace(
            score,
            evidence=score.evidence + "；P5在2,646个非目标自然杠窗口逐点评分保持P3",
        )
        for score in p3.objectives[:-1]
    ) + (specialist_gang,)
    p5 = OpportunityArchiveCandidate(
        candidate_id="r18-p5-added-gang-strict-dominance",
        source_sha256=digest(P5_SOURCE),
        objectives=p5_objectives,
        table_safety=TableSafetyEvidence(
            status="PASS_NONINFERIOR",
            source_units=int(table["source_units"]),
            complete_tables=int(table["tables"]),
            paired_score_delta_mean=float(table["overall"]["stage_score_delta_mean"]),
            execution_failure_count=int(table["action_value_failure_windows"]),
            evidence="P5相对P3的128张全新同墙换座完整桌安全门；32/32阶段轨迹相同",
        ),
        author_cost_note="规则证明后机械实现；零模型作者调用",
    )
    candidates = tuple(inherited[:3]) + (p5, inherited[3])
    old_objectives = tuple(archive2["archive"]["active_objective_ids"])
    active_objectives = old_objectives + (GANG_OBJECTIVE,)
    archive = build_opportunity_archive(
        candidates,
        active_objective_ids=active_objectives,
        baseline_candidate_id="stable-v2",
    )
    decisions = {row.candidate_id: row for row in archive.decisions}
    passed = (
        archive.pareto_elite_ids == ("r18-p5-added-gang-strict-dominance",)
        and archive.lexicase_parent_ids == ("r18-p5-added-gang-strict-dominance",)
        and decisions["r18-p3-three-and-four-wealth-piao"].dominated_by
        == ("r18-p5-added-gang-strict-dominance",)
    )
    inputs = (
        Path(__file__), ARCHIVE_MODULE, ARCHIVE2, P5_SOURCE,
        P5_PREFLIGHT, P5_HIDDEN, P5_TABLE,
    )
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-opportunity-archive-manifest/3",
        "source_hashes": {str(path.relative_to(ROOT)): digest(path) for path in inputs},
        "active_objective_ids": active_objectives,
        "hidden_aggregate_only": True,
        "p3_inheritance_rule": "P5只在公开事实严格支配时改变补杠排序；六类缺失负控、2,646个非严格自然杠窗口及128桌安全面板保持P3",
        "ranking_contract": "逐目标保守增益Pareto；目标轮流置首Lexicase；完整桌为安全门；成本不排序",
    })
    result = {
        "schema": "r18-opportunity-archive-result/3",
        "status": "PASS_ARCHIVE_P5_SUCCESSOR" if passed else "FAIL_ARCHIVE_P5_SUCCESSOR",
        "release_eligible": False,
        "archive": asdict(archive),
        "candidate_inputs": [asdict(row) for row in candidates],
        "findings": {
            "p5_dominates_p3_on_active_vector": bool(
                decisions["r18-p3-three-and-four-wealth-piao"].dominated_by
            ),
            "added_gang_hidden_mean_gain": mean_gain,
            "added_gang_hidden_conservative_gain": conservative_gain,
            "added_gang_hidden_states": len(gains),
            "nonstrict_natural_windows_exact_p3": int(hidden["counts"]["nonstrict_windows"]),
        },
        "next": (
            "冻结P5为当前机会父代；转向抓打圈或七对门清家族，同时保留完整桌发布门"
            if passed else "停止晋级并检查P3继承或P5档案输入"
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
