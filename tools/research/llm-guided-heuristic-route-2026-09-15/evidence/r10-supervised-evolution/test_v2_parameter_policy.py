"""联合参数研究包装的身份、输入和真实排序回归。"""

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
import json
from dataclasses import asdict
from pathlib import Path

import pytest

import v2_parameter_policy as subject
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1


HERE = Path(__file__).resolve().parent


def test_complete_record_and_identity_are_deterministic():
    record = asdict(DEFAULT_WEIGHTS_V1)
    first = subject.weights_from_record(record)
    second = subject.weights_from_record(dict(reversed(list(record.items()))))
    assert first == second == DEFAULT_WEIGHTS_V1
    assert subject.weights_digest(first) == subject.weights_digest(second)
    with pytest.raises(ValueError):
        subject.weights_from_record({key: value for key, value in record.items()
                                     if key != "effective_tile"})
    with pytest.raises(ValueError):
        subject.weights_from_record({**record, "unknown": 1})


def test_default_matches_v2_and_selected_configuration_changes_existing_requests():
    design = json.loads((_project_file(_PROJECT_ROOT, HERE / "parameter-search-design-20260920.json")).read_text())
    audit = json.loads((_project_file(_PROJECT_ROOT, HERE / "parameter-surface-audit-20260920.json")).read_text())
    selected = next(row for row in design["selected"] if row["config_id"] == "v2_joint_18")
    default = subject.ResearchWeightedV2(DEFAULT_WEIGHTS_V1, monotonic=lambda: 0.0)
    probe = subject.ResearchWeightedV2(subject.weights_from_record(selected["weights"]),
                                       monotonic=lambda: 0.0)
    from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
    stable = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    budget = DecisionBudget(1.0, 2.0, 3.0)
    changed = 0
    for path_text in audit["inputs"]:
        request = decision_request_from_json(json.loads(Path(path_text).read_text())["request"])
        stable_plan = asyncio.run(stable.choose(request, budget))
        default_plan = asyncio.run(default.choose(request, budget))
        probe_plan = asyncio.run(probe.choose(request, budget))
        stable_order = [row.action_key for row in stable_plan.candidates]
        default_order = [row.action_key for row in default_plan.candidates]
        probe_order = [row.action_key for row in probe_plan.candidates]
        assert default_order == stable_order
        assert sorted(probe_order) == sorted(stable_order)
        changed += probe_order != stable_order
    assert changed == selected["full_order_changes"]
    assert default.policy_id != probe.policy_id
