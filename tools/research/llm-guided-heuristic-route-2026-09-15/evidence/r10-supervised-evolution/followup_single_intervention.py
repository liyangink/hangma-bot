"""仅对两个已冻结窗口各替换一次首选；诊断身份禁止作为效果候选选留。"""

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
from dataclasses import asdict, replace

import followup_balance_diagnosis as diagnosis
import followup_balance_branch_probe as probe
from hangma_bot.policy.interface import DecisionBudget

b, core, prior, natural = diagnosis.b, diagnosis.core, diagnosis.prior, diagnosis.natural
OUT = b.HERE / "followup-balance-single-intervention-20260920"


class IntervenedPolicy:
    """原建议和实际排序分别记录；只在完整可见视图匹配时移动一个合法动作。"""

    def __init__(self, config, ranker, ranking_id, target, identity, counter, *, enabled=True):
        """注入冻结目标和阶段共享计数；策略内不读文件、不生成随机来源。"""
        self.inner = core.checks.wrapper.BalancedFollowupPolicy(config, lambda: 800., ranker, ranking_id)
        self.target, self.counter, self.enabled = target, counter, enabled
        self.policy_id = identity
        self.audit = []

    async def choose(self, request, budget):
        """非目标完整返回原计划；目标只前移V2合法首选，其余相对顺序不变。"""
        proposal = await self.inner.choose(request, budget)
        p = dict(self.inner.audit[-1])
        order = [c.action_key for c in proposal.candidates]
        row = {k: p[k] for k in ("decision_id", "trigger_seq", "status", "rule_calls", "elapsed_seconds", "base_first", "selected_first", "changed")}
        row.update({"proposal_audit": p, "proposal_order": order, "effective_order": order,
            "intervention_applied": False, "input_view_sha256": None})
        self.audit.append(row)
        if not self.enabled or request.decision_id != self.target["decision_id"]:
            return proposal
        record = b.behavior.capture_request(request)
        if record["candidate_view_sha256"] != self.target["view_sha256"]:
            raise ValueError("目标标识相同但可见视图不符，拒绝替换")
        if self.counter["fires"] != 0:
            raise ValueError("阶段目标窗口重复命中，拒绝第二次替换")
        assert p["status"] == "EVALUATED" and order[0] == self.target["from_action"]
        legal = {c.action_key for c in request.rules.legal_candidates}
        assert self.target["to_action"] in legal and self.target["to_action"] in order
        moved = next(c for c in proposal.candidates if c.action_key == self.target["to_action"])
        candidates = [moved] + [c for c in proposal.candidates if c.action_key != moved.action_key]
        actual = replace(proposal, candidates=tuple(replace(c, rank=i + 1) for i, c in enumerate(candidates)))
        self.counter["fires"] += 1
        row.update({"intervention_applied": True, "input_view_sha256": record["candidate_view_sha256"],
            "effective_order": [c.action_key for c in actual.candidates], "selected_first": moved.action_key,
            "changed": moved.action_key != row["base_first"], "legal_action_keys_at_intervention": sorted(legal)})
        return actual


def prepare():
    """冻结两次单窗干预、4新桌、4旧候选对照，以及30输入的关闭/开启检查。"""
    assert not OUT.exists()
    old = b.read(prior.OUT / "evaluation-plan.json")
    prior.verify_inputs(old)
    probe_plan = b.read(probe.OUT / "manifest.json")
    diagnosis.parent.guard.verify(probe_plan["runtime"])
    assert b.read(probe.OUT / "summary.json")["all_original_q_reproduced"]
    cases = []
    for item, pair in zip(probe_plan["cases"], b.read(diagnosis.OUT / "manifest.json")["cases"], strict=True):
        record = b.read(b.Path(item["input"]))
        assert item["direction"] == pair["direction"]
        cases.append({**pair, "target": {"decision_id": record["request"]["decision_id"],
            "trigger_seq": record["request"]["trigger_seq"], "view_sha256": item["window_id"],
            "from_action": item["actions"][1], "to_action": item["actions"][0], "input": item["input"]}})
    inputs = {str(diagnosis.OUT / row["file"]): b.digest((diagnosis.OUT / row["file"]).read_bytes())
        for row in b.read(diagnosis.OUT / "panel.json")["windows"]}
    assert len(inputs) == 30
    bound = [prior.OUT / n for n in ("evaluation-plan.json", "development-decision.json", "effect-samples.json")]
    bound += [probe.OUT / n for n in ("manifest.json", "summary.json", "interpretation.json")]
    bound += [diagnosis.OUT / n for n in ("manifest.json", "summary.json", "NEXT-INTERVENTION-PLAN.md")]
    plan = {"schema": "followup-single-intervention/1", "created_at_utc": b.search.utc_now(), "cases": cases,
        "behavior_inputs": inputs, "bound_files": {str(p): b.digest(p.read_bytes()) for p in bound},
        "runtime": diagnosis.parent.guard.capture(source_paths=[*b.HERE.glob("*.py"), core.OUT / "ranking.py"]),
        "contract": old["contract"], "contract_sha256": old["contract_sha256"], "rules_hash": old["rules_hash"],
        "rule_config": probe_plan["rule_config"], "panel_seed": old["panel_seed"],
        "source_candidate_id": old["candidate_id"], "max_new_full_tables": 4, "reused_candidate_tables": 4,
        "max_check_seconds": 180, "max_process_seconds": 300, "model_calls": 0, "confirmation_roots": 0,
        "selection_eligible": False, "release_eligible": False,
        "scope": "固定seed单次合法首选替换，后续仍为原候选；只检查该固定阶段差异，不用于效果选留或一般因果外推",
        "prior_goal_turn_classification": "progress: 8桌诊断全复现，两个预选局部观察完成138次规则及1324事实核验"}
    plan["diagnostic_policy_id"] = "offline-single-window-intervention:" + diagnosis.parent._digest(plan)
    OUT.mkdir()
    b.write(OUT / "manifest.json", plan)
    auth = b.unified_document(batch_label="followup-single-intervention", authorization_id="r10-followup-single-intervention",
        accounts={"tables_full": 4}, issued_by="lead", issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户持续推进授权及上一诊断冻结的单次4桌检查；不增加新来源或作者，不继续逐窗扫描"
    natural.require_authorization(auth)
    b.write(OUT / "authorization.json", auth)
    print("frozen two interventions: 4 tables, 30 behavior requests", flush=True)


def verify_inputs(plan):
    """冻结摘要、原失败结案及当前运行闭包须始终一致。"""
    diagnosis.parent.guard.verify(plan["runtime"])
    prior.verify_inputs(b.read(prior.OUT / "evaluation-plan.json"))
    for path, digest in {**plan["bound_files"], **plan["behavior_inputs"]}.items():
        assert b.digest(b.Path(path).read_bytes()) == digest, path


async def check():
    """核验关闭等价、唯一目标排序、错误视图与重复命中拒绝；不执行桌赛。"""
    plan = b.read(OUT / "manifest.json")
    verify_inputs(plan)
    assert not (OUT / "checks-started.json").exists()
    b.write(OUT / "checks-started.json", {"at_utc": b.search.utc_now()})
    ranker, digest = core.checks.load_ranker()
    config = diagnosis.parent.RuleConfig(**plan["rule_config"])
    budget = DecisionBudget(801., 802., 803.)
    reference = core.checks.wrapper.BalancedFollowupPolicy(config, lambda: 800., ranker, digest)
    requests = [b.behavior.decision_request_from_json(b.read(b.Path(p))["request"]) for p in plan["behavior_inputs"]]
    expected = [await reference.choose(request, budget) for request in requests]
    checks = []
    for case in plan["cases"]:
        for enabled in (False, True):
            counter = {"fires": 0}
            policy = IntervenedPolicy(config, ranker, digest, case["target"], plan["diagnostic_policy_id"], counter, enabled=enabled)
            changed = 0
            for request, base in zip(requests, expected, strict=True):
                actual = await policy.choose(request, budget)
                target = enabled and request.decision_id == case["target"]["decision_id"]
                if not target:
                    assert asdict(actual) == asdict(base)
                else:
                    order = [c.action_key for c in base.candidates]
                    key = case["target"]["to_action"]
                    wanted = [key] + [k for k in order if k != key]
                    assert [c.action_key for c in actual.candidates] == wanted
                    assert [c.rank for c in actual.candidates] == list(range(1, len(wanted) + 1))
                    original = {c.action_key: asdict(c) | {"rank": 0} for c in base.candidates}
                    assert original == {c.action_key: asdict(c) | {"rank": 0} for c in actual.candidates}
                    changed += 1
            assert changed == counter["fires"] == int(enabled)
            checks.append({"direction": case["direction"], "enabled": enabled, "requests": len(requests), "changes": changed})
        trigger = next(r for r in requests if r.decision_id == case["target"]["decision_id"])
        for kind in ("wrong_view", "duplicate"):
            target = dict(case["target"])
            if kind == "wrong_view":
                target["view_sha256"] = "0" * 64
            faulty = IntervenedPolicy(config, ranker, digest, target, "test-only", {"fires": int(kind == "duplicate")})
            try:
                await faulty.choose(trigger, budget)
            except ValueError:
                pass
            else:
                raise AssertionError("错误或重复窗口未拒绝")
    verify_inputs(plan)
    b.write(OUT / "checks.json", {"status": "PASS_SINGLE_INTERVENTION_BEHAVIOR", "checks": checks,
        "wrong_view_and_duplicate_rejected_per_case": True, "effect_tables": 0, "model_calls": 0})
    print("30 real requests, two targets: exact disabled plans, single enabled move, invalid/duplicate rejected", flush=True)


def verify_stage(raw, plans, contract, plan, case, original):
    """实际排序与原建议分别核验，且干预前每个原建议须与原轨迹逐项一致。"""
    checked = core.stage.verify_stage(raw, plans, contract, plan["rules_hash"], "candidate", plan["diagnostic_policy_id"])
    fired, prefix = 0, 0
    for table, before in zip(raw["tables"], original["tables"], strict=True):
        for i, row in enumerate(table["prototype_audit"]):
            p = row["proposal_audit"]
            assert all(row[k] == p[k] for k in ("decision_id", "trigger_seq", "status", "rule_calls", "elapsed_seconds", "base_first"))
            assert p["status"] in ("EVALUATED", "NOT_APPLICABLE")
            assert p["selected_first"] == (row["proposal_order"][0] if row["proposal_order"] else None)
            assert row["selected_first"] == (row["effective_order"][0] if row["effective_order"] else None)
            assert p["decision_id"] == row["decision_id"] and p["trigger_seq"] == row["trigger_seq"]
            if p["status"] == "EVALUATED":
                assert p["ranking_order"] == core.mathematics.expected_order(p["ranking_rows"], p["ranking_context"])
                assert row["proposal_order"][:len(p["ranking_order"])] == p["ranking_order"]
            if not fired:
                saved = before["prototype_audit"][i]
                clean = lambda x: {k: v for k, v in x.items() if k not in ("elapsed_seconds", "ranking_elapsed_seconds")}
                assert clean(p) == clean(saved)
                prefix += 1
            if row["intervention_applied"]:
                assert not fired
                target = case["target"]
                assert row["decision_id"] == target["decision_id"] and row["input_view_sha256"] == target["view_sha256"]
                assert row["proposal_order"][0] == target["from_action"] and target["to_action"] in row["legal_action_keys_at_intervention"]
                assert row["effective_order"] == [target["to_action"]] + [k for k in row["proposal_order"] if k != target["to_action"]]
                fired += 1
            else:
                assert row["effective_order"] == row["proposal_order"] and row["input_view_sha256"] is None
    assert fired == 1
    return {**checked, "interventions": fired, "prefix_original_decisions_reproduced_including_target": prefix}


def run():
    """两个完整阶段共4桌；旧候选轨迹只复用，不重新评价或修改原成绩。"""
    plan = b.read(OUT / "manifest.json")
    verify_inputs(plan)
    assert b.read(OUT / "checks.json")["status"] == "PASS_SINGLE_INTERVENTION_BEHAVIOR"
    process = b.read(OUT / "checks-process.json")
    assert process["returncode"] == 0 and not process["timed_out"] and not process["group_still_alive"]
    contract = b.read(b.Path(plan["contract"]))
    auth = b.read(OUT / "authorization.json")
    natural.require_authorization(auth)
    ledger = b.search.ActionValueLedger.load(OUT / "ledger.json", authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    ranker, digest = core.checks.load_ranker()
    samples = b.read(prior.OUT / "effect-samples.json")
    reports = []
    for case in plan["cases"]:
        verify_inputs(plan)
        sample = next(s for s in samples if s["opponent_mix"] == "M" and s["root_index"] == case["root_index"] and s["focal_anchor_seat"] == case["focal_anchor_seat"])
        original = sample["raw_arms"]["candidate"]
        plans = natural.build_seat_stage_plans(contract=contract, opponent="M", root_index=case["root_index"],
            focal_seat=case["focal_anchor_seat"], panel_seed=plan["panel_seed"])
        core.verify_result(original, plans, contract, b.read(prior.OUT / "evaluation-plan.json"), "candidate")
        counter = {"fires": 0}
        folder = OUT / "arms" / case["direction"]
        expected = {"step_id": case["direction"], "planned_tables": 2, "manifest_digest": diagnosis.parent._digest(plan),
            "plans_digest": diagnosis.parent._digest([p.to_json() for p in plans]), "diagnostic_policy_id": plan["diagnostic_policy_id"]}
        checked = diagnosis.parent.execute_arm(folder, expected=expected, ledger=ledger,
            runner=lambda: core.stage.run_stage(plans, "M", "candidate", contract,
                lambda config: IntervenedPolicy(config, ranker, digest, case["target"], plan["diagnostic_policy_id"], counter)),
            verifier=lambda raw: verify_stage(raw, plans, contract, plan, case, original))
        actual = b.read(folder / "result.json")["raw"]
        reports.append({"case": case, "verification": checked,
            "reference_u": {k: original[k] for k in ("u", "u_low", "u_high")},
            "intervened_u": {k: actual[k] for k in ("u", "u_low", "u_high")},
            "effect_delta_low": actual["u_low"] - original["u_high"], "effect_delta_high": actual["u_high"] - original["u_low"],
            "reference_stage_totals": original["stage_totals_by_participant"], "intervened_stage_totals": actual["stage_totals_by_participant"],
            "reference_place_points": original["stage_place_points_by_participant"], "intervened_place_points": actual["stage_place_points_by_participant"],
            "per_table": [{"table_id": a["table_id"], "reference_scores_by_seat": z["scores_by_seat"],
                "intervened_scores_by_seat": a["scores_by_seat"], "scores_changed": a["scores_by_seat"] != z["scores_by_seat"]}
                for a, z in zip(actual["tables"], original["tables"], strict=True)]})
        print(case["direction"], "complete", reports[-1]["reference_u"], "->", reports[-1]["intervened_u"], flush=True)
    verify_inputs(plan)
    assert ledger.spent("tables_full") == 4
    b.write(OUT / "summary.json", {"status": "COMPLETE_FIXED_STAGE_SINGLE_INTERVENTION", "reports": reports,
        "new_full_tables": 4, "reused_candidate_tables": 4, "spent": ledger.account_summary(),
        "model_calls": 0, "confirmation_roots": 0, "selection_eligible": False, "release_eligible": False,
        "limits": "固定seed的单次合法动作替换，不能推广一般因果效应；效用不变不表示轨迹无变化。至此停止逐窗检查，不扫描其他位置。"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check", "run"))
    args = parser.parse_args()
    if args.operation == "check":
        asyncio.run(check())
    else:
        {"prepare": prepare, "run": run}[args.operation]()
