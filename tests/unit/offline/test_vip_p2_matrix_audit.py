"""P2 有限夹具诊断：根分母、双轴缺口与缺快照跳过。"""

import json
import importlib.util
from dataclasses import replace
from pathlib import Path

from hangma_bot.hangma.interface import RuleIssue
from hangma_bot.hangma.route_frontier import RouteGapKind

SCRIPT = Path(__file__).parents[3] / "scripts/vip_p2_matrix_audit.py"
SPEC = importlib.util.spec_from_file_location("vip_p2_matrix_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def test_current_official_fixture_matrix_is_reproducible():
    """按同次合法候选登记全部根；官方对拍仅指这九个已执行单步。"""

    result = audit_module.audit()
    assert result["target_config"] == {"BaseScore": 1, "YouCaiBiKao": False}
    assert (result["fixture_count"], result["snapshot_count"],
            result["legal_root_count"]) == (4, 9, 48)
    assert (result["official_pair_anchor_count"],
            result["official_pair_state_match_count"]) == (9, 9)
    assert sum(cell["legal_roots"] for cell in result["matrix"]) == 48
    assert sum(cell["mechanical_gap"] for cell in result["matrix"]) == 0
    assert sum(cell["legacy_mechanical_or_future_placeholder"]
               for cell in result["matrix"]) == 47
    assert sum(cell["root_projection_mechanical_gap"]
               for cell in result["matrix"]) == 0
    assert sum(cell["future_condition_open"] for cell in result["matrix"]) == 47
    assert sum(cell["input_evidence_gap"] for cell in result["matrix"]) == 0
    assert sum(cell["both_gaps"] for cell in result["matrix"]) == 0
    assert {row["config_provenance"] for row in result["rows"]} == {
        "v18_target_config_assumed",
        "v35_local_run_config_recorded_no_official_rules_response",
    }
    assert result["skipped"] == [{
        "fixture": "tests/fixtures/official/v35/vip-p2-natural/minggang-replenish-hu-1228-1231.json",
        "reason": "非本人可决策窗口", "seq": 1231,
    }]


def test_missing_full_snapshot_is_explicitly_skipped(tmp_path, monkeypatch):
    """动作后状态缺失时不可继续声称成对官方对拍。"""

    source = audit_module.REPO / audit_module.V18
    fixture = json.loads(source.read_text())
    fixture["snapshots"]["2269"] = {"seq": 2269, "gap": True}
    target = tmp_path / audit_module.V18
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(fixture, ensure_ascii=False))
    monkeypatch.setattr(audit_module, "REPO", Path(tmp_path))
    monkeypatch.setattr(audit_module, "TRACES", {
        audit_module.V18: audit_module.TRACES[audit_module.V18]})
    result = audit_module.audit()
    assert result["snapshot_count"] == 2
    assert result["official_pair_anchor_count"] == 1
    assert any(row["seq"] == 2269 and "gap=true" in row["reason"]
               for row in result["skipped"])
    assert any(row["seq"] == 2269 and "后继" in row["reason"]
               for row in result["skipped"])


def test_real_root_projection_failure_is_not_counted_as_future_unknown(monkeypatch):
    """故障注入：根动作投影失败须与仅待给定未来条件分开。"""

    original = audit_module.project_legal_roots
    injected = False

    def fail_one_root(*args, **kwargs):
        nonlocal injected
        roots = list(original(*args, **kwargs))
        if roots and not injected:
            roots[0] = replace(
            roots[0], branches=(), claim_state=None, proposal_state=None,
                pending_condition=None,
                gap_kind=RouteGapKind.MECHANICAL_GAP,
                gap_kinds=(RouteGapKind.MECHANICAL_GAP,),
                issues=(RuleIssue("route_transition.mechanical", "故障注入"),),
            )
            injected = True
        return tuple(roots)

    monkeypatch.setattr(audit_module, "project_legal_roots", fail_one_root)
    result = audit_module.audit()
    assert injected
    assert sum(cell["root_projection_mechanical_gap"]
               for cell in result["matrix"]) == 1
    assert sum(cell["future_condition_open"] for cell in result["matrix"]) == 46
