"""只重放已消费 M/root01、锚座位0的两臂，离线比较同一请求；最多4桌。"""
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

import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path

import collect_real_disagreements as base
import sitin_real_behavior as behavior

HERE = Path(__file__).resolve().parent
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/mechanism-batch-03')
ITERATION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/mechanism-batch-03/run/iterations/iter-02')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/batch03-known-root-diagnostic')


def main():
    """先登记预算，重放后复核原积分；诊断计数不是独立效果样本。"""
    if OUT.exists():
        raise SystemExit("输出已存在，不隐式重跑")
    OUT.mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "windows")).mkdir()
    natural, search = base.natural, base.search
    contract = json.loads((base.ROUTE / "contracts/group-dev-v1.json").read_text())
    sources = {"parent": base.SOURCES["parent"], "candidate": _project_file(_PROJECT_ROOT, ITERATION / "generation/candidate.py")}
    texts = {key: path.read_text() for key, path in sources.items()}
    scorers = {key: base.ActionValueScorer(key, text) for key, text in texts.items()}
    auth = base.unified_document(batch_label="r10-batch03-diagnostic",
        authorization_id="r10-batch03-diagnostic-4-tables", accounts={"tables_full": 4},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户授权root持续监督进化；已消费开发根诊断，4桌、0作者、0确认"
    natural.require_authorization(auth)
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    ledger = search.ActionValueLedger.load(_project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(auth))
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "purpose": "consumed_development_root_diagnostic", "panel_seed": 2026091911,
        "opponent": "M", "root_index": 1, "focal_anchor_seat": 0, "planned_tables": 4,
        "selection_eligible": False, "release_eligible": False,
        "sources": {k: {"path": str(sources[k]), "sha256": hashlib.sha256(v.encode()).hexdigest()}
                    for k, v in texts.items()},
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "selection": "首个M根首个锚座位；两臂全请求计数；每改选动作族前5窗、父子改分前50窗、每阶段动作族前2个对照",
        "limitations": "同根轨迹相关；观察不证明动作优劣；逻辑时钟不检验线上时限"})
    original = json.loads((_project_file(_PROJECT_ROOT, ITERATION / "natural-M/panel.json")).read_text())
    expected = next(s for s in original["samples"] if s["root_index"] == 1 and s["focal_anchor_seat"] == 0)
    plans = natural.build_seat_stage_plans(contract=contract, opponent="M", root_index=1,
        focal_seat=0, panel_seed=2026091911)
    rows, stages, entries, saved = [], [], [], set()
    counts, quotas = Counter(), Counter()
    for arm in ("baseline", "candidate"):
        requests = []
        def observe(request):
            if len(requests) >= 10000:
                raise ValueError("超过预定请求容量")
            requests.append(request)
        reservation = ledger.reserve(step_id="diagnostic:" + arm, account="tables_full", amount=2,
            note="已消费M根重放，不增加效果样本")
        try:
            result = natural.run_arm_stage(arm=arm, plans=plans, candidate_scorer=scorers["candidate"],
                opponent_policies=contract["panel"]["opponent_scenarios"]["M"]["opponent_policies"],
                versions_block=natural.stage.contract_versions_block(contract),
                step_limit=int(contract["stop"]["step_limit"]), value_limits=natural.ValueAnalysisLimits(),
                decision_observer=observe)
        finally:
            ledger.settle(reservation, usage_unknown=True, note="异常或中断按上界计费，成功后结算实际桌数")
        natural.write_json(_project_file(_PROJECT_ROOT, OUT / (arm + "-stage.json")), result)
        if result["status"] != "complete":
            raise ValueError("诊断阶段未完成")
        ledger.settle(reservation, actual=len(result["tables"]))
        if result["stage_totals_by_participant"] != expected["raw_arms"][arm]["stage_totals_by_participant"]:
            raise ValueError("原阶段积分未复现，停止使用本诊断")
        stages.append({"arm": arm, "original_totals_reproduced": True, "requests": len(requests)})
        # 模拟已经结束；逐请求走生产choose，避免在模拟事件循环中嵌套asyncio.run。
        for request in requests:
            view = behavior.build_scoring_view(request)
            name = behavior.digest(view.candidate_view())
            values = {key: behavior.evaluate_request(scorer, name, request) for key, scorer in scorers.items()}
            v2 = natural.stage.build_panel_policy(natural.BASELINE_FOCAL_POLICY, lambda: 0.0)
            plan = asyncio.run(v2.choose(request, behavior.DecisionBudget(1.0, 2.0, 3.0)))
            v2_key = plan.candidates[0].action_key if plan.candidates else None
            if any(row["status"] != "SCORED" or not row["action_key"] for row in values.values()) or not v2_key:
                raise ValueError("诊断评分或计划不可比较")
            parent, candidate = values["parent"], values["candidate"]
            changed = parent["scores"] != candidate["scores"]
            diff = v2_key != candidate["action_key"]
            counts[arm + ":views"] += 1
            counts[arm + ":parent_candidate_scores_changed"] += int(changed)
            counts[arm + ":parent_candidate_preferred_changed"] += int(parent["action_key"] != candidate["action_key"])
            counts[arm + ":v2_candidate_preferred_changed"] += int(diff)
            family = (v2_key.split(":")[0], candidate["action_key"].split(":")[0])
            if diff:
                counts["v2_to_candidate:" + "->".join(family)] += 1
            group = ("mechanism",) if changed else (("v2_disagreement",) + family if diff else
                    ("control", view.visible_state.phase, tuple(sorted({a.action_type for a in view.actions}))))
            limit = 50 if changed else 5 if diff else 2
            selected = name not in saved and quotas[group] < limit
            row = {"arm": arm, "window_id": name, "parent": parent, "candidate": candidate,
                   "v2_ordered_actions": [c.action_key for c in plan.candidates],
                   "parent_candidate_scores_changed": changed, "v2_candidate_preferred_changed": diff,
                   "selected": selected}
            rows.append(row)
            if selected:
                record = behavior.capture_request(request)
                file = "windows/" + name + ".json"
                natural.write_json(_project_file(_PROJECT_ROOT, OUT / file), record)
                entries.append({"file": file, "candidate_view_sha256": name,
                                "record_sha256": behavior.digest(record), "selection": list(group)})
                saved.add(name)
                quotas[group] += 1
        print(json.dumps(stages[-1]), flush=True)
    with (_project_file(_PROJECT_ROOT, OUT / "comparisons.jsonl")).open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "panel.json"), {"schema": "sitin-real-behavior-panel/1",
        "purpose": "development_behavior", "selection_eligible": False, "windows": entries,
        "source": "manifest.json", "limitations": "已消费单个M根两臂轨迹；配额采样只供诊断，不作自然频率或效果推断"})
    behavior.load_panel(_project_file(_PROJECT_ROOT, OUT / "panel.json"))
    summary = {"counts": dict(counts), "stages": stages, "saved_windows": len(saved),
        "spent": ledger.account_summary(), "selection_eligible": False, "release_eligible": False}
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
