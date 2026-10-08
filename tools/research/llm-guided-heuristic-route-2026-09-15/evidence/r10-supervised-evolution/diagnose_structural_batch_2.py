"""重放第二结构批次已消费根，采集T2子代与S3父代在相同可见观察上的分歧。"""
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

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_executor import WorkloadExceeded  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from p12_authorization import unified_document  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/post-close-diagnostic')
CHILD = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/repair-preflight/behavior-preflight-v2/configurations/s2-cfg-04/candidate.py')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/repair-preflight/behavior-preflight-v2/configurations/s2-cfg-01/candidate.py')
EFFECT_C = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/effect-c')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026092169
TARGETS = (
    ("H", 17, 0),
    ("H", 17, 2),
    ("H", 24, 0),
    ("M", 18, 2),
    ("M", 19, 3),
    ("M", 22, 0),
    ("M", 22, 1),
    ("M", 27, 1),
)


def digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def reading(result, view) -> dict:
    ranked = batch_to_ranked_candidates(result, view.actions)
    return {
        "status": result.status,
        "reason": result.reason,
        "preferred": ranked[0].action_key if ranked else None,
        "scores": {entry.action_key: entry.score for entry in result.entries},
        "traces": {entry.action_key: dict(entry.trace) for entry in result.entries},
    }


class ContrastScorer:
    """子代控制真实轨迹；父代只对同一ScoringView做影子评分。"""

    def __init__(self, child, parent, context: dict):
        self.primary = child
        self.shadow = parent
        self.name = child.name
        self.context = context
        self.counts = Counter()
        self.changed: list[dict] = []

    def score(self, view):
        own_batch = self.primary.score(view)
        own = reading(own_batch, view)
        try:
            parent = reading(self.shadow.score(view), view)
        except (Exception, WorkloadExceeded) as exc:
            parent = {"status": "FAILED", "preferred": None,
                      "error": type(exc).__name__ + ": " + str(exc)}
        raw = view.candidate_view()
        changed = (own["status"] != parent["status"]
                   or own["preferred"] != parent["preferred"])
        self.counts["views"] += 1
        self.counts["preferred_changed"] += int(changed)
        self.counts["child_abstain"] += int(own["status"] == "ABSTAIN")
        self.counts["parent_failed"] += int(parent["status"] == "FAILED")
        self.counts["phase:" + view.visible_state.phase] += 1
        if changed:
            actions = {item.get("action_key"): {
                "action_type": item.get("action_type"),
                "fact_kind": item.get("fact_kind"),
                "shanten_after": item.get("shanten_after"),
                "useful_tiles": item.get("useful_tiles"),
                "routes": item.get("routes"),
                "followup_branches": item.get("followup_branches"),
                "family_progress_entries": item.get("family_progress_entries"),
                "immediate_settlement": item.get("immediate_settlement"),
            } for item in raw["actions"]}
            child_action = actions.get(own["preferred"], {})
            parent_action = actions.get(parent["preferred"], {})
            transition = (
                str(parent_action.get("action_type")) + "->"
                + str(child_action.get("action_type"))
            )
            self.counts["transition:" + transition] += 1
            self.changed.append({
                "schema": "r10-structural-parent-child-contrast/1",
                "context": self.context,
                "view_sha256": digest(raw),
                "observation": {
                    "game_id": view.visible_state.game_id,
                    "round_no": view.visible_state.round_no,
                    "snapshot_seq": view.visible_state.snapshot_seq,
                    "seat": view.visible_state.seat,
                    "phase": view.visible_state.phase,
                },
                "child": own,
                "parent": parent,
                "actions": actions,
                "transition": transition,
                "candidate_view": raw,
                "information_boundary": "相同PlayerObservation投影；不读取WorldState或未来结果",
            })
        return own_batch


def utility_delta(mix: str, root: int, seat: int) -> float:
    samples = json.loads((_project_file(_PROJECT_ROOT, EFFECT_C / "phase-c-new-samples.json")).read_text(encoding="utf-8"))
    candidate_id = "action_value_v1:offline-structural-t2:" + hashlib.sha256(
        CHILD.read_bytes()).hexdigest()
    row = next(item for item in samples
               if item["candidate_id"] == candidate_id
               and item["opponent_mix"] == mix
               and item["root_index"] == root
               and item["focal_anchor_seat"] == seat)
    child = row["arms"]["candidate"]
    baseline = row["arms"]["baseline"]
    child_mid = (child["u_low"] + child["u_high"]) / 2.0
    baseline_mid = (baseline["u_low"] + baseline["u_high"]) / 2.0
    return child_mid - baseline_mid


def main() -> None:
    if OUT.exists():
        raise SystemExit("第二结构批次诊断目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "windows")).mkdir()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    authorization = unified_document(
        batch_label="r10-structural-search-02-post-close-diagnostic",
        authorization_id="r10-structural-search-02-diagnostic-16-tables",
        accounts={"tables_full": 16}, issued_by="lead",
        issued_at_utc=search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "第二结构批次无正向冠军；按文献复盘重放已消费开发根定位父子机制",
        "scope": "8个已消费对手族×根×座位阶段，子代控制轨迹、父代只影子评分；诊断不选留",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    natural.require_authorization(authorization)
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 16})
    sources = {"child": CHILD.read_text(encoding="utf-8"),
               "parent": PARENT.read_text(encoding="utf-8")}
    manifest = {
        "schema": "r10-structural-search-02-diagnostic/1",
        "sources": {name: {"path": str(path), "sha256": hashlib.sha256(
            sources[name].encode("utf-8")).hexdigest()}
            for name, path in (("child", CHILD), ("parent", PARENT))},
        "panel_seed": PANEL_SEED,
        "targets": [{"opponent_mix": mix, "root_index": root,
                     "focal_anchor_seat": seat,
                     "observed_child_vs_stable_v2_utility_delta": utility_delta(mix, root, seat)}
                    for mix, root, seat in TARGETS],
        "planned_tables": 16,
        "selection_eligible": False,
        "confirmation_eligible": False,
        "purpose": "已消费开发根的同观察父子机制诊断；终端差只作分层，不作为单步动作标签",
    }
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)

    all_changed: list[dict] = []
    stages: list[dict] = []
    totals = Counter()
    for mix, root, seat in TARGETS:
        plans = natural.build_seat_stage_plans(
            contract=contract, opponent=mix, root_index=root,
            focal_seat=seat, panel_seed=PANEL_SEED)
        context = {"opponent_mix": mix, "root_index": root,
                   "focal_anchor_seat": seat, "panel_seed": PANEL_SEED,
                   "tables": [plan.table_id for plan in plans],
                   "observed_child_vs_stable_v2_utility_delta": utility_delta(mix, root, seat)}
        scorer = ContrastScorer(
            ActionValueScorer("t2-cfg-04", sources["child"]),
            ActionValueScorer("s3-parent-zero", sources["parent"]), context)
        step_id = f"diagnostic-{mix}-r{root:02d}-s{seat}"
        reservation = ledger.reserve(
            step_id=step_id, account="tables_full", amount=len(plans),
            note="已消费开发根重放；父代影子评分不改变子代轨迹")
        try:
            result = natural.run_arm_stage(
                arm="candidate", plans=plans, candidate_scorer=scorer,
                opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
                versions_block=natural.stage.contract_versions_block(contract),
                step_limit=int(contract["stop"]["step_limit"]),
                value_limits=natural.ValueAnalysisLimits())
        finally:
            ledger.settle(reservation, usage_unknown=True,
                          note="失败或中断保守计费；完成后复核实际桌数")
        if result["status"] == "complete":
            ledger.settle(reservation, actual=len(result["tables"]))
        expected_path = _project_file(_PROJECT_ROOT, EFFECT_C / "candidates/t2-cfg-04" / (
            f"c-t2-cfg-04-{mix}-r{root:02d}-s{seat}/result.json"))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))["raw"]
        reproduced = (result["stage_totals_by_participant"]
                      == expected["stage_totals_by_participant"])
        stages.append({"context": context, "status": result["status"],
                       "counts": dict(scorer.counts),
                       "stage_totals_by_participant": result["stage_totals_by_participant"],
                       "reproduced_original_stage_totals": reproduced})
        all_changed.extend(scorer.changed)
        totals.update(scorer.counts)
        print(json.dumps({"target": [mix, root, seat], "status": result["status"],
                          "views": scorer.counts["views"],
                          "preferred_changed": scorer.counts["preferred_changed"],
                          "reproduced": reproduced}, ensure_ascii=False), flush=True)

    for index, row in enumerate(all_changed):
        natural.write_json(_project_file(_PROJECT_ROOT, OUT / "windows" / f"{index:04d}-{row['view_sha256']}.json"), row)
    transition_by_outcome = Counter()
    for row in all_changed:
        delta = row["context"]["observed_child_vs_stable_v2_utility_delta"]
        outcome = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
        transition_by_outcome[outcome + ":" + row["transition"]] += 1
    summary = {
        "schema": "r10-structural-search-02-diagnostic-summary/1",
        "status": "COMPLETE_DIAGNOSTIC_ONLY",
        "targets": len(TARGETS),
        "tables": ledger.spent("tables_full"),
        "counts": dict(totals),
        "changed_windows": len(all_changed),
        "transition_by_observed_stage_outcome": dict(sorted(transition_by_outcome.items())),
        "all_original_totals_reproduced": all(
            row["reproduced_original_stage_totals"] for row in stages),
        "selection_eligible": False,
        "confirmation_eligible": False,
        "model_calls": 0,
        "limitations": "终端阶段差不能归因为任一单窗动作；输出只用于构造下一批可证伪题面",
    }
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "stages.json"), stages)
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not summary["all_original_totals_reproduced"]:
        raise SystemExit("诊断插桩未复现原阶段总分；不得使用其机制结论")


if __name__ == "__main__":
    main()
