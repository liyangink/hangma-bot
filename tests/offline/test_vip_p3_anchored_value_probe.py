"""支付锚定探针必须与同源规则结算一致，并拒绝教师篡改。"""

import gzip
import json
from pathlib import Path

import pytest

from hangma_bot.kernel.serialization import observation_from_json
from scripts.vip_p3_anchored_value_probe import _roots, predict_observation


_TEACHER = Path("review/vip-route-2026-09-30/evidence/"
                "p3-competing-terminal-20260930/new-shape-teacher.json.gz")
_SCAN = Path("review/vip-route-2026-09-30/evidence/"
             "p3-highfan-payoff-20260930/scan-r18-3701-3800.json")
_MODEL = Path("review/vip-route-2026-09-30/evidence/"
              "p3-anchored-payoff-20260930/train-model.json")


def _one_direct_hu_root():
    with gzip.open(_TEACHER, "rt", encoding="utf-8") as stream:
        report = json.load(stream)
    row = next(row for row in report["rows"] if any(
        item["first_event"]["kind"] == "self_normal_draw"
        and item["first_event"]["immediate_hu"] is not None
        for key, arm in row["outcomes_by_action"].items() if key.startswith("discard:")
        for item in arm
    ))
    report["rows"] = [row]
    return report


def test_opened_teacher_next_draw_matches_rule_payoff_and_rejects_tamper(tmp_path):
    """未来仅作标签；逐码资格、番数、四座支付须与行动前规则见证一致。"""

    report = _one_direct_hu_root()
    path = tmp_path / "one-root.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    roots, counters = _roots((path,))
    assert len(roots) == 1
    assert counters["matched_draw_payoffs"] > 0

    event = next(item["first_event"] for key, arm in report["rows"][0][
        "outcomes_by_action"
    ].items() if key.startswith("discard:") for item in arm
                 if item["first_event"]["kind"] == "self_normal_draw"
                 and item["first_event"]["immediate_hu"] is not None)
    event["immediate_hu"]["fan"] += 1
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="逐码规则支付"):
        _roots((path,))


def test_existing_highfan_positive_control_is_recognized_without_future_input():
    """已开正控只测行动前模型是否看见高番等待，不当独立强度确认。"""

    scan = json.loads(_SCAN.read_text(encoding="utf-8"))
    row = next(item for item in scan["selected_roots"] if item["seed"] == 3704)
    model = json.loads(_MODEL.read_text(encoding="utf-8"))
    scores = predict_observation(observation_from_json(row["observation"]), model)
    assert scores[0]["action_key"].startswith("discard:")
    assert scores[0]["predicted_own_net"] > next(
        item["predicted_own_net"] for item in scores if item["action_key"] == "hu"
    )
    assert scores[0]["first_normal_draw_direct_payoff"] > 0
