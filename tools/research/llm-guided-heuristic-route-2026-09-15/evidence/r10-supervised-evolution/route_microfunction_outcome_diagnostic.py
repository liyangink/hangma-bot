"""重放新来源正/零/负根，收集稳定 V2 与路线冠军的同观察动作分歧。"""
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
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import sitin_natural_panel as natural  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921')
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/new-source-01')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/outcome-diagnostic-01')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
CHILD = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/configurations/r2-cfg-02/candidate.py')
PANEL_SEEDS = (2026092198, 2026092199)
MIXES = ("H", "M")
ACTIVE_POLICIES = ("parent", "child")
SEATS = tuple(range(4))
TABLE_BUDGET = 192


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def source_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reading(scored, view) -> dict:
    ranked = batch_to_ranked_candidates(scored, view.actions)
    return {
        "status": scored.status,
        "preferred": ranked[0].action_key if ranked else None,
        "scores": {item.action_key: item.score for item in scored.entries},
        "traces": {item.action_key: dict(item.trace) for item in scored.entries},
        "reason": scored.reason,
    }


class ShadowScorer:
    """主评分器控制轨迹；影子评分器只读取相同公开视图并记录分歧。"""

    def __init__(self, *, active: str, parent_source: str, child_source: str,
                 context: dict) -> None:
        self.active = active
        self.parent = ActionValueScorer("diagnostic-parent", parent_source)
        self.child = ActionValueScorer("diagnostic-child", child_source)
        primary = self.parent if active == "parent" else self.child
        self.name = primary.name
        self.context = context
        self.counts = Counter()
        self.changed: list[dict] = []

    def score(self, view):
        """返回活动评分器原结果；比较不会改变轨迹、预算或合法动作。"""
        parent_batch = self.parent.score(view)
        child_batch = self.child.score(view)
        parent = reading(parent_batch, view)
        child = reading(child_batch, view)
        self.counts["views"] += 1
        self.counts["phase:" + view.visible_state.phase] += 1
        changed = parent["preferred"] != child["preferred"]
        self.counts["preferred_changed"] += int(changed)
        if changed:
            raw = view.candidate_view()
            self.changed.append({
                "context": self.context,
                "view_sha256": digest(raw),
                "observation": {
                    "game_id": view.visible_state.game_id,
                    "round_no": view.visible_state.round_no,
                    "snapshot_seq": view.visible_state.snapshot_seq,
                    "seat": view.visible_state.seat,
                    "phase": view.visible_state.phase,
                },
                "parent": parent,
                "child": child,
                "candidate_view": raw,
                "preferred_changed": True,
                "information_boundary": "ScoringView.candidate_view only",
            })
        return parent_batch if self.active == "parent" else child_batch


def selected_roots() -> list[dict]:
    """每个新种子×H/M 固定取最高、最低和首个零保守差根。"""
    stats = batch.read(_project_file(_PROJECT_ROOT, SOURCE / "statistics.json"))
    normal = next(iter(stats["by_candidate"].values()))["panels"]["normal"]
    result = []
    for mix in MIXES:
        rows = normal["panels"][mix]["root_rows"]
        for seed in PANEL_SEEDS:
            current = [row for row in rows if f"-{seed}-" in row["root_id"]]
            if len(current) != 64:
                raise ValueError("新来源根清单漂移")
            high = sorted(current, key=lambda row: (-row["d_low"], row["root_id"]))[0]
            low = sorted(current, key=lambda row: (row["d_low"], row["root_id"]))[0]
            zero = next(row for row in sorted(current, key=lambda row: row["root_id"])
                        if row["d_low"] == 0 and row["root_id"] not in
                        {high["root_id"], low["root_id"]})
            for label, row in (("positive_extreme", high),
                               ("negative_extreme", low), ("zero", zero)):
                root = int(row["root_id"].rsplit("root", 1)[1])
                result.append({
                    "panel_seed": seed,
                    "mix": mix,
                    "root_index": root,
                    "outcome_class": label,
                    "d_point": row["d_point"],
                    "d_low": row["d_low"],
                    "d_high": row["d_high"],
                    "unresolved": row["unresolved"],
                    "root_id": row["root_id"],
                })
    if len(result) != 12 or len({row["root_id"] for row in result}) != 12:
        raise ValueError("分层诊断必须冻结12个唯一已消费根")
    return result


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("路线微函数结果诊断目录已存在；拒绝覆盖")
    summary = batch.read(_project_file(_PROJECT_ROOT, SOURCE / "summary.json"))
    if summary.get("disposition") != "INCONCLUSIVE_DEVELOPMENT":
        raise ValueError("只有新来源结果不确定时才执行本诊断")
    roots = selected_roots()
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-route-microfunction-outcome-diagnostic",
        authorization_id="r10-route-microfunction-outcome-diagnostic-20260921",
        accounts={"tables_full": TABLE_BUDGET}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": (
            "4,096桌新来源复核为正但区间跨0；按ReEvo比较反馈和MEoH行为多样性"
            "重放已消费根定位稳定/不稳定触发，不产生新效果样本"
        ),
        "scope": (
            "每个新种子×H/M取保守根差最高、最低、零各一根；父/子轨迹、"
            "4座位、2桌；只收集PlayerObservation投影的同观察评分分歧"
        ),
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r10-route-microfunction-outcome-diagnostic/1",
        "created_at_utc": batch.search.utc_now(),
        "source_summary": str(_project_file(_PROJECT_ROOT, SOURCE / "summary.json")),
        "source_summary_sha256": source_digest(_project_file(_PROJECT_ROOT, SOURCE / "summary.json")),
        "source_statistics": str(_project_file(_PROJECT_ROOT, SOURCE / "statistics.json")),
        "source_statistics_sha256": source_digest(_project_file(_PROJECT_ROOT, SOURCE / "statistics.json")),
        "contract": str(CONTRACT),
        "contract_sha256": source_digest(CONTRACT),
        "sources": {
            "parent": {"path": str(PARENT), "sha256": source_digest(PARENT)},
            "child": {"path": str(CHILD), "sha256": source_digest(CHILD)},
        },
        "selected_roots": roots,
        "active_policies": list(ACTIVE_POLICIES),
        "focal_seats": list(SEATS),
        "tables_per_stage": 2,
        "max_full_tables": TABLE_BUDGET,
        "workers": 4,
        "selection_eligible": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "model_calls": 0,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET}).save()
    print(json.dumps({"status": "PREPARED", "roots": roots,
                      "tables": TABLE_BUDGET}, ensure_ascii=False))


def verify(plan: dict) -> None:
    for key, sha_key in (("source_summary", "source_summary_sha256"),
                         ("source_statistics", "source_statistics_sha256"),
                         ("contract", "contract_sha256")):
        if source_digest(Path(plan[key])) != plan[sha_key]:
            raise ValueError(key + " 漂移")
    for name, path in (("parent", PARENT), ("child", CHILD)):
        if source_digest(path) != plan["sources"][name]["sha256"]:
            raise ValueError(name + " 源码漂移")
    if selected_roots() != plan["selected_roots"]:
        raise ValueError("分层根清单漂移")


def original_result(context: dict) -> dict:
    slot = PANEL_SEEDS.index(context["panel_seed"]) + 1
    arm = "baseline" if context["active"] == "parent" else "candidate"
    label = (f"nd-p{slot}-{arm}-{context['mix']}-"
             f"r{context['root_index']:02d}-s{context['seat']}")
    path = _project_file(_PROJECT_ROOT, SOURCE / "arms" / f"p{slot}-{arm}-{context['mix']}" / label / "result.json")
    return batch.read(path)["raw"]


def run_root(row: dict, active: str) -> dict:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify(plan)
    contract = batch.read(CONTRACT)
    parent_source = PARENT.read_text(encoding="utf-8")
    child_source = CHILD.read_text(encoding="utf-8")
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET})
    step_id = (f"diag-{row['panel_seed']}-{row['mix']}-"
               f"r{row['root_index']:02d}-{active}")
    reservation = ledger.reserve(step_id=step_id, account="tables_full", amount=8,
                                 note="已消费根的父/子同观察分歧诊断；4座位×2桌")
    records, stages, counts = [], [], Counter()
    try:
        for seat in SEATS:
            context = {**row, "active": active, "seat": seat}
            plans = natural.build_seat_stage_plans(
                contract=contract, opponent=row["mix"], root_index=row["root_index"],
                focal_seat=seat, panel_seed=row["panel_seed"])
            scorer = ShadowScorer(active=active, parent_source=parent_source,
                                  child_source=child_source, context=context)
            result = natural.run_arm_stage(
                arm="candidate", plans=plans, candidate_scorer=scorer,
                opponent_policies=contract["panel"]["opponent_scenarios"][row["mix"]]["opponent_policies"],
                versions_block=natural.stage.contract_versions_block(contract),
                step_limit=int(contract["stop"]["step_limit"]),
                value_limits=natural.ValueAnalysisLimits(),
            )
            expected = original_result(context)
            reproduced = (
                result["stage_totals_by_participant"] == expected["stage_totals_by_participant"]
                and result["focal_stage_score"] == expected["focal_stage_score"]
            )
            stages.append({"context": context, "status": result["status"],
                           "reproduced_original": reproduced,
                           "views": scorer.counts["views"],
                           "preferred_changed": scorer.counts["preferred_changed"]})
            records.extend(scorer.changed)
            counts.update(scorer.counts)
            if result["status"] != "complete" or not reproduced:
                raise ValueError("诊断轨迹未复现冻结效果臂")
    except BaseException:
        ledger.settle(reservation, usage_unknown=True,
                      note="诊断异常；按启动前预留8桌保守结算")
        raise
    ledger.settle(reservation, actual=8)
    verify(plan)
    return {"row": row, "active": active, "counts": dict(counts),
            "stages": stages, "changed": records, "tables": 8}


def summarize(results: list[dict]) -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify(plan)
    if len(results) != 24 or sum(row["tables"] for row in results) != TABLE_BUDGET:
        raise ValueError("诊断工作单元不完整")
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": TABLE_BUDGET})
    if ledger.spent("tables_full") != TABLE_BUDGET:
        raise ValueError("诊断费用未完整结算")
    records = [record for result in results for record in result["changed"]]
    stages = [stage for result in results for stage in result["stages"]]
    counters: dict[str, Counter] = defaultdict(Counter)
    transitions = Counter()
    phases = Counter()
    for result in results:
        key = result["row"]["outcome_class"]
        counters[key].update(result["counts"])
    for record in records:
        parent = str(record["parent"]["preferred"])
        child = str(record["child"]["preferred"])
        transitions[parent.split(":", 1)[0] + "->" + child.split(":", 1)[0]] += 1
        phases[record["observation"]["phase"]] += 1
    with (_project_file(_PROJECT_ROOT, OUT / "disagreements.jsonl")).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "stages.json"), stages)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {
        "schema": "r10-route-microfunction-outcome-diagnostic-summary/1",
        "status": "COMPLETE",
        "selected_roots": len(plan["selected_roots"]),
        "stages": len(stages),
        "tables": TABLE_BUDGET,
        "all_original_totals_reproduced": all(row["reproduced_original"] for row in stages),
        "counts_by_outcome_class": {key: dict(value) for key, value in sorted(counters.items())},
        "preferred_disagreements": len(records),
        "transitions": dict(transitions.most_common()),
        "phases": dict(phases.most_common()),
        "spent": ledger.account_summary(),
        "selection_eligible": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": "用正/零/负根的同观察分歧和路线trace构造多父代条件化重组任务",
    })
    print(json.dumps(batch.read(_project_file(_PROJECT_ROOT, OUT / "summary.json")), ensure_ascii=False), flush=True)


def run() -> None:
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify(plan)
    context = multiprocessing.get_context("spawn")
    results = []
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=plan["workers"], mp_context=context) as pool:
        futures = [pool.submit(run_root, row, active)
                   for row in plan["selected_roots"] for active in ACTIVE_POLICIES]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print("complete", result["row"]["root_id"], result["active"],
                  result["counts"].get("preferred_changed", 0), flush=True)
    summarize(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run}[args.operation]()
