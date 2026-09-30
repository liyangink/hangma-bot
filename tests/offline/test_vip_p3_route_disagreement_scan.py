"""P3 结果盲高番条件前沿分歧扫描回归。"""

from scripts.vip_p3_route_disagreement_scan import scan


def test_scan_keeps_one_result_blind_high_fan_disagreement_per_seed():
    """只读行动前规则与冻结父代分数，容量不冒充牌墙概率。"""

    report = scan(start_seed=608, seeds=1, max_own_draw_index=15)
    assert report["counts"] == {
        "eligible_windows": 3,
        "no_high_fan_capacity_advantage": 9,
        "scanned_own_draw_windows": 12,
    }
    assert len(report["selected_roots"]) == 1
    root = report["selected_roots"][0]
    assert root["own_draw_index"] == 7
    assert root["r18_top_action"] == "discard:6w"
    assert root["route_alternative"] == "discard:7t"
    assert root["capacity_gap"] == 1
