"""重放已消费 H/root1 父代阶段，采集可往返请求；最多两桌，零模型调用。"""
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

import json
from collections import Counter
from pathlib import Path

import collect_real_disagreements as original
import sitin_real_behavior as behavior


def main() -> None:
    """差异窗口全部保留，另按阶段与合法动作族预定配额采未改选对照。"""
    natural, search = original.natural, original.search
    out = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / "real-behavior-panel-v1")
    if out.exists():
        raise SystemExit("目录已存在，保留冻结证据")
    out.mkdir()
    (out / "windows").mkdir()
    contract = json.loads((original.ROUTE / "contracts/group-dev-v1.json").read_text())
    history = original.HERE / "known-root-diagnostic/comparisons.jsonl"
    targets = {r["view_sha256"] for line in history.read_text().splitlines()
               if (r := json.loads(line))["preferred_changed"]
               and r["context"]["active"] == "parent" and r["context"]["opponent"] == "H"}
    auth = original.unified_document(batch_label="r10-capture-behavior-panel",
           authorization_id="r10-capture-2-tables", accounts={"tables_full": 2},
           issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户授权监督进化；已消费开发根请求采集，最多2桌，0模型，0确认"
    natural.require_authorization(auth)
    natural.write_json(out / "authorization.json", auth)
    ledger = search.ActionValueLedger.load(out / "ledger.json",
              authorized_budgets=search.av_ledger_budgets_from_authorization(auth))
    saved, controls, seen_targets = {}, Counter(), set()

    def observe(request):
        view = behavior.build_scoring_view(request)
        key = behavior.digest(view.candidate_view())
        stratum = (request.observation.phase, tuple(sorted({a.action_type for a in view.actions})))
        target = key in targets
        if target:
            seen_targets.add(key)
        if key in saved or (not target and controls[stratum] >= 2):
            return
        if len(saved) >= 100:
            raise ValueError("超过冻结的100观察采集上界")
        record = behavior.capture_request(request)
        assert record["candidate_view_sha256"] == key
        natural.write_json(out / "windows" / (key + ".json"), record)
        saved[key] = {"file": "windows/" + key + ".json", "candidate_view_sha256": key,
                      "record_sha256": behavior.digest(record),
                      "selection": "known_disagreement" if target else "first_two_per_phase_action_family"}
        if not target:
            controls[stratum] += 1

    plans = natural.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
                focal_seat=0, panel_seed=2026091901)
    source = original.SOURCES["parent"].read_text()
    reservation = ledger.reserve(step_id="capture:H:parent", account="tables_full", amount=2,
                                 note="已消费开发根请求采集，不新增效果样本")
    try:
        result = natural.run_arm_stage(arm="candidate", plans=plans,
            candidate_scorer=original.ActionValueScorer("parent", source),
            opponent_policies=contract["panel"]["opponent_scenarios"]["H"]["opponent_policies"],
            versions_block=natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]), value_limits=natural.ValueAnalysisLimits(),
            decision_observer=observe)
    finally:
        ledger.settle(reservation, usage_unknown=True, note="失败或中断保守计费，完成后结算实际桌数")
    natural.write_json(out / "stage-result.json", result)
    if result["status"] != "complete":
        raise SystemExit("采集阶段失败：保留证据，不冻结面板")
    ledger.settle(reservation, actual=len(result["tables"]))
    expected = json.loads((original.HERE / "known-root-diagnostic/stages.json").read_text())[0]["result"]
    assert result["stage_totals_by_participant"] == expected["stage_totals_by_participant"]
    assert seen_targets == targets
    manifest = {"schema": "sitin-real-behavior-panel/1", "purpose": "development_behavior",
                "selection_eligible": False, "windows": [saved[k] for k in sorted(saved)],
                "source": {"opponent": "H", "root_index": 1, "panel_seed": 2026091901,
                           "focal_anchor_seat": 0, "policy_source_sha256": original.hashlib.sha256(source.encode()).hexdigest()},
                "collection": {"known_disagreements": len(targets), "control_count": sum(controls.values()),
                               "control_quota": "first 2 per phase and legal action-family set",
                               "original_totals_reproduced": True, "spent": ledger.account_summary()},
                "limitations": "已消费H来源根、一个锚座位、父代轨迹；不代表全部规则族或自然分布，非确认数据"}
    natural.write_json(out / "panel.json", manifest)
    behavior.load_panel(out / "panel.json")
    print(json.dumps(manifest["collection"], ensure_ascii=False))


if __name__ == "__main__":
    main()
