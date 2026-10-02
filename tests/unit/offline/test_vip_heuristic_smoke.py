"""严格桌赛失败分母、当前源码身份与证据覆盖保护。"""

import asyncio
import gzip
import json

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline import vip_heuristic_smoke as smoke
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE, VipRouteProjectionLimits,
)


def test_identity_includes_new_framework_and_native_source():
    identity = smoke.freeze_vip_identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    paths = set(identity["source_manifest"])
    assert {
        "src/hangma_bot/policy/route_heuristic_view.py",
        "src/hangma_bot/policy/route_vip_heuristic.py",
        "src/hangma_bot/hangma/route_structure.py",
        "src/hangma_bot/hangma/natural_preparation.py",
        "src/hangma_bot/hangma/route_transition.py",
        "src/hangma_bot/hangma/_grouped_native.c",
    } <= paths
    assert identity["params"]["max_local_collection_size"] == 4096
    changed_budget = smoke.freeze_vip_identity(
        VIP_ROUTE_HEURISTIC_SEED_SOURCE,
        projection_limits=VipRouteProjectionLimits(max_nodes=2048),
    )
    assert changed_budget["candidate_id"] != identity["candidate_id"]
    assert changed_budget["params"]["max_local_collection_size"] == 2048
    changed_rules = smoke.freeze_vip_identity(
        VIP_ROUTE_HEURISTIC_SEED_SOURCE,
        rule_config=RuleConfig("another-rules-instance", 1, False),
    )
    changed_analysis = smoke.freeze_vip_identity(
        VIP_ROUTE_HEURISTIC_SEED_SOURCE,
        route_limits=ValueAnalysisLimits(max_expansions=4096),
    )
    assert changed_rules["candidate_id"] != identity["candidate_id"]
    assert changed_analysis["candidate_id"] != identity["candidate_id"]


def test_dependency_body_change_invalidates_identity(monkeypatch):
    original = smoke.freeze_vip_identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    actual_manifest = smoke.source_manifest

    def changed_manifest(roots):
        manifest = actual_manifest(roots)
        path = "src/hangma_bot/hangma/route_structure.py"
        manifest[path] = {**manifest[path], "sha256": "b" * 64}
        return manifest

    monkeypatch.setattr(smoke, "source_manifest", changed_manifest)
    changed = smoke.freeze_vip_identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    assert changed["candidate_id"] != original["candidate_id"]
    assert changed["source_sha256"] == original["source_sha256"]


def test_abstention_stops_real_driver_and_keeps_failed_table(tmp_path):
    source = '''
def score_actions(view):
    return {"status": "ABSTAIN", "entries": [], "reason": "故障注入"}
'''
    out = tmp_path / "abstention"
    result = asyncio.run(smoke.run_vip_smoke(
        out, start_seed=1, seeds=1, rounds=8, source=source,
    ))
    assert result["status"] == "failed"
    assert (result["requested_tables"], result["complete_tables"]) == (1, 0)
    row = result["rows"][0]
    assert row["completed_hands"] == 0
    assert row["status"] == "error"
    assert "ABSTAIN" in row["error_reason"]
    with gzip.open(out / "decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    assert records and all(record["status"] == "failed" for record in records)
    assert all("selected_action_key" not in record for record in records)
    assert all(record["legal_action_keys"] for record in records)
    assert result["strength_or_release_claim"] is False
    with pytest.raises(FileExistsError):
        asyncio.run(smoke.run_vip_smoke(
            out, start_seed=1, seeds=1, rounds=8, source=source,
        ))
