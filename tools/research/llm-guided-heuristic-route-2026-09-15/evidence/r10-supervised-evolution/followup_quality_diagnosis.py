"""后继改良原型M层一正一负的完整双臂复演；不追加效果样本。"""

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
from collections import Counter
from time import monotonic

import followup_quality_panel as parent
from diagnose_route_decisions import plan_view

b = parent.b
natural = parent.natural
OUT = b.HERE / "followup-quality-diagnostic-20260920"


def prepare():
    """固定最早严格正负配置、8桌和每阶段前8个分歧，先冻结再复演。"""
    assert not OUT.exists()
    old = b.read(parent.OUT / "evaluation-plan.json")
    parent.verify_inputs(old)
    assert b.read(parent.OUT / "development-decision.json")["status"] == "NOT_PROMOTED_AFTER_CORE"
    path = parent.OUT / "effect-samples.json"
    samples = b.read(path)
    cases = []
    for direction in ("negative", "positive"):
        for sample in sorted(samples, key=lambda s: (s["root_index"], s["focal_anchor_seat"])):
            if sample["opponent_mix"] != "M":
                continue
            a, z = sample["arms"]["candidate"], sample["arms"]["baseline"]
            low, high = a["u_low"] - z["u_high"], a["u_high"] - z["u_low"]
            if (high < 0 if direction == "negative" else low > 0):
                cases.append({"direction": direction, "root_index": sample["root_index"],
                    "focal_anchor_seat": sample["focal_anchor_seat"], "delta_low": low, "delta_high": high})
                break
    assert len(cases) == 2
    OUT.mkdir()
    b.write(OUT / "manifest.json", {"schema": "followup-quality-diagnostic/1",
        "created_at_utc": b.search.utc_now(), "cases": cases,
        "source_samples": str(path), "source_samples_sha256": b.digest(path.read_bytes()),
        "parent_plan_sha256": b.digest((parent.OUT / "evaluation-plan.json").read_bytes()),
        "runtime": parent.guard.capture(source_paths=[*b.HERE.glob("*.py")]),
        "max_full_tables": 8, "max_requests_per_table": 20000, "max_saved_per_stage": 8,
        "max_process_seconds": 300, "model_calls": 0, "confirmation_roots": 0, "release_eligible": False,
        "selection": "M层按根/座位顺序各取最早严格负和正配置；两臂完整阶段复演，首8个分歧仅作解释材料",
        "scope": "同一可见请求比较完整原型与V2；阶段终端必须复现，记录分项取舍，不从终局正负倒推单步因果"})
    auth = b.unified_document(batch_label="followup-quality-diagnostic", authorization_id="r10-followup-quality-diagnostic",
        accounts={"tables_full": 8}, issued_by="lead", issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户持续推进授权；旧开发清单正负配置8桌诊断，0新效果来源、0作者与正式确认"
    natural.require_authorization(auth)
    b.write(OUT / "authorization.json", auth)
    print("frozen", cases, flush=True)


class ComparedPolicy:
    """原样返回实际臂计划，另一策略只旁路解释；两者都只接收合法可见请求。"""

    def __init__(self, arm, config, context):
        self.arm = arm
        self.enhanced = parent.policy.FollowupQualityPolicy(config, lambda: 800.0)
        self.baseline = natural.stage.build_panel_policy(natural.BASELINE_FOCAL_POLICY, lambda: 800.0)
        self.policy_id = self.enhanced.policy_id if arm == "candidate" else type(self.baseline).__name__
        self.context = context

    async def choose(self, request, budget):
        """保存有限分歧的可见输入及两套完整计划；不把旁路计划交给模拟驱动。"""
        base = await self.baseline.choose(request, budget)
        proposal = await self.enhanced.choose(request, budget)
        audit = self.enhanced.audit[-1]
        assert audit["status"] in ("EVALUATED", "NOT_APPLICABLE"), audit
        counts = self.context["counts"]
        counts["requests"] += 1
        counts["evaluated"] += int(audit["status"] == "EVALUATED")
        if audit["changed"]:
            counts["first_changed"] += 1
            a = base.candidates[0]
            z = next(c for c in base.candidates if c.action_key == proposal.candidates[0].action_key)
            before, after = {p.name: p.value for p in a.score_parts}, {p.name: p.value for p in z.score_parts}
            differences = {key: after.get(key, 0) - before.get(key, 0) for key in sorted(set(before) | set(after))
                           if after.get(key, 0) != before.get(key, 0)}
            assert abs(sum(differences.values()) - (z.total_score - a.total_score)) < 1e-8
            counts["v2_total_tie"] += int(z.total_score == a.total_score)
            counts["overrode_v2_preference"] += int(z.total_score < a.total_score)
            for name, delta in differences.items():
                counts["part:" + name + (":loss" if delta < 0 else ":gain")] += 1
            obs = request.observation
            if len(self.context["saved"]) < self.context["max_saved"]:
                record = b.behavior.capture_request(request)
                self.context["saved"].append({"record": record, "arm": self.arm,
                    "round_no": obs.round_no, "snapshot_seq": obs.snapshot_seq,
                    "table_rank": 1 + sum(s > obs.scores[obs.seat] for s in obs.scores),
                    "current_table_scores_seat_order": list(obs.scores),
                    "candidate_audit": dict(audit), "v2_total_gap": z.total_score - a.total_score,
                    "part_differences_new_minus_v2": differences,
                    "v2": plan_view(base), "candidate": plan_view(proposal)})
        return proposal if self.arm == "candidate" else base


def replay(plans, arm, contract, context):
    """复用原组合的公开组件，新增旁路观察器；结果仍按原完整阶段核验。"""
    versions = natural.stage.contract_versions_block(contract)
    config = parent.RuleConfig(**{k: versions[k] for k in ("ruleset_version", "base_score", "you_cai_bi_kao")})
    totals, points, tables = {}, {}, []
    start = monotonic()
    for index, table_plan in enumerate(plans):
        situation = natural.build_stage_situation(plan=table_plan, table_no=index + 1, tables_completed=index,
            totals=totals, place_totals=points, rounds_per_game=versions["rounds_per_game"])
        logical = natural.arm_logical_policies(arm="baseline", candidate_scorer=None,
            logical_participants=table_plan.logical_participants,
            opponent_policies=contract["panel"]["opponent_scenarios"]["M"]["opponent_policies"], monotonic=lambda: 800.0)
        observed = ComparedPolicy(arm, config, context)
        logical[natural.FOCAL_PARTICIPANT] = observed
        row = natural.execute_natural_table(plan=table_plan,
            policies_by_seat=natural.seat_policies_from(logical, table_plan.permutation, table_plan.logical_participants),
            versions_block=versions, step_limit=contract["stop"]["step_limit"],
            value_limits=natural.ValueAnalysisLimits(), stage_situation=situation)
        row["stage_situation"] = situation.to_json()
        if arm == "candidate":
            row["prototype_audit"] = observed.enhanced.audit
        tables.append(row)
        assert row["match_status"] == "complete"
        ranks = natural.stage.place_points_for_table(row["scores_by_seat"])
        for seat, person in enumerate(table_plan.seats()):
            totals[person] = totals.get(person, 0) + row["scores_by_seat"][seat]
            points[person] = points.get(person, 0) + ranks[seat]
    utility = natural.stage.group_advance_utility([natural.stage.LedgerRow(participant_id=p, total_score=totals[p],
        place_points=points[p]) for p in sorted(totals)], focal_id=natural.FOCAL_PARTICIPANT)
    return {"arm": arm, "status": "complete", "usable": True, "error": None, "tables": tables,
        "stage_totals_by_participant": totals, "stage_place_points_by_participant": points,
        "focal_stage_score": totals[natural.FOCAL_PARTICIPANT], "u_low": float(utility["u_low"]),
        "u_high": float(utility["u_high"]), "u": float(utility["u_low"]) if utility["u_low"] == utility["u_high"] else None,
        "unresolved": utility["unresolved"], "u_interval": {k: utility[k] for k in ("a", "b", "tie_block")},
        "elapsed_ms": (monotonic() - start) * 1000,
        "execution_review": natural.execution_audit.review_tables(tables),
        "diagnostic": {"counts": dict(context["counts"]), "saved": context["saved"]}}


def run():
    """执行四个已见阶段，逐阶段预留、保存、验证，终端不复现则拒绝采用解释。"""
    plan = b.read(OUT / "manifest.json")
    old = b.read(parent.OUT / "evaluation-plan.json")
    parent.verify_inputs(old)
    parent.guard.verify(plan["runtime"])
    assert b.digest((parent.OUT / "evaluation-plan.json").read_bytes()) == plan["parent_plan_sha256"]
    path = b.Path(plan["source_samples"])
    assert b.digest(path.read_bytes()) == plan["source_samples_sha256"]
    samples = b.read(path)
    contract = b.read(b.Path(old["contract"]))
    auth = b.read(OUT / "authorization.json")
    natural.require_authorization(auth)
    ledger = b.search.ActionValueLedger.load(OUT / "ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    entries, reports = {}, []
    for case in plan["cases"]:
        sample = next(s for s in samples if s["opponent_mix"] == "M" and s["root_index"] == case["root_index"] and s["focal_anchor_seat"] == case["focal_anchor_seat"])
        plans = natural.build_seat_stage_plans(contract=contract, opponent="M", root_index=case["root_index"],
            focal_seat=case["focal_anchor_seat"], panel_seed=old["panel_seed"])
        for arm in ("baseline", "candidate"):
            parent.guard.verify(plan["runtime"])
            label = case["direction"] + "-" + arm
            context = {"counts": Counter(), "saved": [], "max_saved": plan["max_saved_per_stage"]}
            folder = OUT / "arms" / label
            expected = {"step_id": label, "planned_tables": 2, "manifest_digest": parent._digest(plan), "arm": arm}
            parent.execute_arm(folder, expected=expected, ledger=ledger,
                runner=lambda: replay(plans, arm, contract, context),
                verifier=lambda raw: parent.verify_stage(raw, plans, contract, old, arm))
            raw = b.read(folder / "result.json")["raw"]
            parent.terminal_equal(raw, sample["raw_arms"][arm])
            if arm == "candidate":
                for new_table, old_table in zip(raw["tables"], sample["raw_arms"][arm]["tables"], strict=True):
                    for a, z in zip(new_table["prototype_audit"], old_table["prototype_audit"], strict=True):
                        assert {k: v for k, v in a.items() if k != "elapsed_seconds"} == {k: v for k, v in z.items() if k != "elapsed_seconds"}
            detail = []
            for item in raw["diagnostic"]["saved"]:
                item = dict(item)
                record = item.pop("record")
                key = record["candidate_view_sha256"]
                file = "windows/" + key + ".json"
                if key not in entries:
                    b.write(OUT / file, record)
                    entries[key] = {"file": file, "candidate_view_sha256": key, "record_sha256": b.behavior.digest(record)}
                detail.append({"window_id": key, **item})
            report = {"label": label, **case, "arm": arm, "terminal_reproduced": True,
                "counts": raw["diagnostic"]["counts"], "rows": detail}
            b.write(OUT / (label + "-diagnostic.json"), report)
            reports.append({k: v for k, v in report.items() if k != "rows"})
            print(reports[-1], flush=True)
    parent.guard.verify(plan["runtime"])
    assert ledger.spent("tables_full") == 8
    b.write(OUT / "panel.json", {"schema": "sitin-real-behavior-panel/1", "purpose": "development_behavior",
        "selection_eligible": False, "windows": list(entries.values()), "source": "manifest.json"})
    b.behavior.load_panel(OUT / "panel.json")
    b.write(OUT / "summary.json", {"status": "COMPLETE_PAIRED_DIAGNOSTIC_ONLY", "full_tables": 8,
        "reports": reports, "saved_windows": len(entries), "spent": ledger.account_summary(),
        "model_calls": 0, "confirmation_roots": 0, "release_eligible": False,
        "limits": "事后挑选一正一负；前8窗有早期偏差。两臂轨迹及同阶段窗口不独立，不能把终局正负当单步因果标签；V2风格分项只读当前桌积分名次，不使用阶段总账"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run()
