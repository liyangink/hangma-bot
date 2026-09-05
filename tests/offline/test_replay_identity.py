"""统一牌谱身份算法测试（契约 §4.1 + contract-vectors 消费）。"""

from __future__ import annotations

import hashlib
import json

import pytest

from hangma_bot.offline.replay import hand_id, split_group_id


def _digest(fields) -> str:
    text = json.dumps(fields, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_hand_id_frozen_vector():
    assert (
        hand_id("hangma-official", "t_6c121bfda7e8", "t_6c121bfda7e8_r4_b0_t0", 1)
        == "hand-" + _digest(["hangma-official", "t_6c121bfda7e8", "t_6c121bfda7e8_r4_b0_t0", 1])
    )


def test_split_group_id_frozen_vector():
    assert (
        split_group_id("hangma-official", "t_6c121bfda7e8")
        == "split-" + _digest(["hangma-official", "t_6c121bfda7e8"])
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ("", "room", "game", 1),
        ("ns", "", "game", 1),
        ("ns", "room", "", 1),
        ("ns", "room", "game", 0),
        ("ns", "room", "game", -1),
        ("ns", "room", "game", True),
        ("ns", "room", "game", 1.0),
    ],
)
def test_hand_id_rejects_invalid_inputs(arguments):
    with pytest.raises(ValueError):
        hand_id(*arguments)


def test_hand_id_is_stable_and_distinct():
    base = hand_id("ns", "room", "game", 1)
    assert base == hand_id("ns", "room", "game", 1)
    assert base != hand_id("ns", "room", "game", 2)
    assert base != hand_id("ns", "room", "other-game", 1)
    assert base != hand_id("other-ns", "room", "game", 1)


def test_round_no_positive_int_required():
    with pytest.raises(ValueError):
        hand_id("ns", "room", "game", "1")
    with pytest.raises(ValueError):
        hand_id("ns", "room", "game", 1.5)
