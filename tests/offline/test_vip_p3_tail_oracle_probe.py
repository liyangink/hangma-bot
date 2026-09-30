"""未来首次事件上界不能被误当成当前可部署策略。"""

from scripts.vip_p3_tail_oracle_probe import _Event, _EventRoot, _evaluate


def test_oracle_future_hu_can_choose_wait_without_any_fitted_feature():
    """下一摸已知高分会造成研究上界，即使价值模型全为零。"""

    empty = (0.0,) * 27
    root = _EventRoot(
        seed=1, root_id="visible-root", keys=("hu", "discard:1w"),
        shape_key="hu", arms=(
            (_Event(empty, 10.0, 10.0),),
            (_Event(empty, 20.0, 20.0),),
        ),
    )
    result = _evaluate((root,), (0.0,) * 6, 6)
    assert result["mean_paired_net_delta"] == 10.0
    assert result["deferred_current_hu_roots"] == 1
    assert result["mean_absolute_terminal_error"] == 0.0
