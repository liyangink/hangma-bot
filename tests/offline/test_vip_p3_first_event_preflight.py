"""P3 竞争事件预检：过牌专用响应不是一个新的决策终点。"""

from scripts.vip_p3_first_event_preflight import audit


def test_first_event_accounting_uses_actionable_windows_and_tile_keys():
    """固定新根与相关世界中，每个动作世界恰分配一个有牌码的事件。"""

    report = audit(start_seed=301, seeds=5, worlds_per_root=4, own_draw_index=6)
    assert report["reached_roots"] == 5
    assert report["skipped_roots"] == []
    assert report["action_worlds"] == 60
    assert report["event_counts"] == {"self_normal_draw": 60}
    assert sum(report["event_key_counts"].values()) == 60
    assert all(key.startswith("self_normal_draw:")
               for key in report["event_key_counts"])
    assert sum(report["paired_event_changes"].values()) == 40


def test_same_first_draw_can_have_different_hu_qualification_by_discard():
    """相关世界摸同一事件牌，弃牌后手牌不同仍会改变立即胡资格。"""

    report = audit(start_seed=443, seeds=1, worlds_per_root=8, own_draw_index=14)
    assert report["action_worlds"] == 24
    assert report["event_counts"] == {"self_normal_draw": 24}
    assert report["immediate_hu_action_worlds"] == 3
    assert report["paired_immediate_hu"]["no_hu->hu"] == 3
    assert report["root_groups"][0]["immediate_hu_fan_counts_by_arm"] == {
        "discard:6t": {}, "discard:中": {"2": 1}, "discard:发": {"2": 2},
    }
    assert report["root_groups"][0]["immediate_hu_net_points_by_arm"] == {
        "discard:6t": 0, "discard:中": 48, "discard:发": 96,
    }


def test_paired_immediate_hu_is_checked_against_complete_hand_settlement():
    """局部可胡提升不能直接当整局收益；完整续打单独结算。"""

    report = audit(start_seed=443, seeds=1, worlds_per_root=8,
                   own_draw_index=14, full_tail=True)
    assert report["paired_full_hand_delta_sign"] == {"positive": 4, "zero": 12}
    assert report["root_groups"][0]["full_hand_net_points_by_arm"] == {
        "discard:6t": 0, "discard:中": 48, "discard:发": 144,
    }


def test_shape_reference_is_independent_and_completes_same_world_arms():
    """规则牌效基础续打者在新种子上完成相关世界各动作臂。"""

    report = audit(start_seed=501, seeds=1, worlds_per_root=2,
                   own_draw_index=9, full_tail=True, reference="shape")
    assert report["reference"] == "shape"
    assert report["reached_roots"] == 1
    assert report["action_worlds"] == 6
    assert report["paired_full_hand_delta_sign"] == {"zero": 4}
