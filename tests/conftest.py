"""共享夹具与本机整批历史复算的测试边界。"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("HANGMA_OFFLINE_TEST_FIXTURES", "1")
collect_ignore_glob = ["fixtures/research/**"]

# 已封存实验和旧 S02/R18 包绑定原始来源链及冻结运行根。
_ARCHIVE_MODULES = (
    'tests/offline/test_vip_p3_afterstate_contract.py',
    'tests/offline/test_vip_p3_anchored_value_probe.py',
    'tests/offline/test_vip_p3_competing_holdout_eval.py',
    'tests/offline/test_vip_p3_competing_predict.py',
    'tests/offline/test_vip_p3_conditional_branch_audit.py',
    'tests/offline/test_vip_p3_event_teacher.py',
    'tests/offline/test_vip_p3_highfan_payoff_scan.py',
    'tests/offline/test_vip_p3_highfan_probe_teacher.py',
    'tests/offline/test_vip_p3_hu_wait_holdout_eval.py',
    'tests/offline/test_vip_p3_hu_wait_predict.py',
    'tests/offline/test_vip_p3_hu_wait_root_scan.py',
    'tests/offline/test_vip_p3_multi_opportunity_analysis.py',
    'tests/offline/test_vip_p3_multi_opportunity_freeze.py',
    'tests/offline/test_vip_p3_payoff_frontier.py',
    'tests/offline/test_vip_p3_poststate_value_probe.py',
    'tests/offline/test_vip_p3_width_pair_diagnostic.py',
    'tests/unit/application/test_r18_current_testroom_wiring.py',
    'tests/unit/application/test_vip_free_end_to_end_public.py',
    'tests/unit/application/test_vip_free_assembly.py',
    'tests/unit/application/test_vip_testroom_assembly.py',
)


def pytest_collection_modifyitems(items):
    """本机归档缺失时明确跳过整批复算，不改写来源摘要或模型结果。"""
    root = Path(__file__).resolve().parents[1]
    if (root / "review/vip-route-2026-09-30/evidence").is_dir():
        return
    archived = pytest.mark.skip(reason="归档复算需要本机原始来源链及对应旧冻结运行根")
    for item in items:
        if item.path.relative_to(root).as_posix() in _ARCHIVE_MODULES:
            item.add_marker(archived)
