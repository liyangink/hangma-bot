"""在batch04已消费的相同开发来源根评价父代，分离本次映射变异与换根影响。"""
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
from pathlib import Path

import collect_real_disagreements as base
from verify_natural_evidence import verify_panel

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/batch04-parent-ablation')


def main():
    """冻结四根全换座、64桌预算并复核共同V2臂；不新增确认数据。"""
    if OUT.exists():
        raise SystemExit("目录已存在，禁止隐式重跑")
    natural, search = base.natural, base.search
    OUT.mkdir()
    contract = json.loads((base.ROUTE / "contracts/group-dev-v1.json").read_text())
    parent_path = _project_file(_PROJECT_ROOT, HERE / "mechanism-batch-03/run/iterations/iter-02/generation/candidate.py")
    source = parent_path.read_text()
    auth = base.unified_document(batch_label="r10-batch04-parent-ablation",
        authorization_id="r10-batch04-parent-ablation-64-tables", accounts={"tables_full": 64},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False)
    auth["issuance_basis"] = "用户授权监督持续进化；已消费batch04四根的同根父代消融，64桌、零作者、零确认"
    natural.require_authorization(auth)
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {"purpose": "same_development_roots_parent_ablation",
        "created_at_utc": search.utc_now(), "panel_seed": 2026091912, "opponents": ["H", "M"],
        "root_indices": [1, 2], "seats_per_root": 4, "planned_tables": 64,
        "parent_source": str(parent_path), "parent_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "selection_eligible": False, "release_eligible": False,
        "limitations": "看到子代结果后开展的开发消融；没有独立确认资格；不回填选留成绩"})
    rows, reconciliation = [], []
    for mix in ("H", "M"):
        natural.run_natural_panel(candidate_source=source, opponent=mix, roots=2, seats_per_root=4,
            contract=contract, out_dir=_project_file(_PROJECT_ROOT, OUT / ("natural-" + mix)), authorization=auth,
            panel_seed=2026091912, ledger_path=_project_file(_PROJECT_ROOT, OUT / "ledger.json"),
            ledger_authorized_budgets=search.av_ledger_budgets_from_authorization(auth), min_roots=1)
        parent = json.loads((_project_file(_PROJECT_ROOT, OUT / ("natural-" + mix) / "panel.json")).read_text())
        child = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanism-batch-04/run/iterations/iter-01" / ("natural-" + mix) / "panel.json")).read_text())
        reconciliation.append(verify_panel(parent, contract, expected_identity=parent["identity"], expected_root_indices=[1, 2]))
        for index in (1, 2):
            deltas = []
            for seat in range(4):
                p = next(s for s in parent["samples"] if s["root_index"] == index and s["focal_anchor_seat"] == seat)
                c = next(s for s in child["samples"] if s["root_index"] == index and s["focal_anchor_seat"] == seat)
                assert p["root_content_digest"] == c["root_content_digest"]
                for key in ("stage_totals_by_participant", "stage_place_points_by_participant", "u_low", "u_high"):
                    assert p["raw_arms"]["baseline"][key] == c["raw_arms"]["baseline"][key]
                a, b = c["arms"]["candidate"], p["arms"]["candidate"]
                deltas.append({"low": a["u_low"] - b["u_high"], "high": a["u_high"] - b["u_low"]})
            rows.append({"opponent": mix, "root_index": index,
                "root_content_digest": p["root_content_digest"],
                "delta_low": sum(d["low"] for d in deltas) / 4,
                "delta_high": sum(d["high"] for d in deltas) / 4})
        print(json.dumps({"opponent": mix, "baseline_reproduced": True}), flush=True)
    ledger = search.ActionValueLedger.load(_project_file(_PROJECT_ROOT, OUT / "ledger.json"))
    result = {"purpose": "development_child_minus_parent", "roots": rows,
        "equal_mix_low": sum(r["delta_low"] for r in rows) / 4,
        "equal_mix_high": sum(r["delta_high"] for r in rows) / 4,
        "all_common_baseline_totals_reproduced": True, "spent": ledger.account_summary(),
        "selection_eligible": False, "release_eligible": False}
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "reconciliation.json"), reconciliation)
    natural.write_json(_project_file(_PROJECT_ROOT, OUT / "summary.json"), result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
