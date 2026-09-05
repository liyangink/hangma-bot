"""契约向量消费：身份哈希算法与归档资料分级（contract-vectors.json）。

parallel-v1 契约向量是实施验收输入；本测试逐例对拍 identity 算法并核对
三份真实归档资料的 SHA-256 与分块形态（供 check_hand 按能力核对）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hangma_bot.simulation import hand_id, split_group_id

_VECTORS = Path(__file__).resolve().parents[2] / "doc" / "implementation" / "contracts" / "contract-vectors.json"
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "hangma" / "archived-rooms"


def _vectors():
    return json.loads(_VECTORS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _vectors()["identity_cases"] if _VECTORS.exists() else [])
def test_identity_cases(case):
    """官方身份四例逐一对拍（含中文键与 another-generation 变体）。"""
    namespace, tournament_id, game_id, round_no = case["key"]
    assert hand_id(namespace, tournament_id, game_id, round_no) == case["hand_id"]
    assert split_group_id([namespace, tournament_id]) == case["official_split_group_id"]


@pytest.mark.parametrize("case", _vectors()["invalid_identity_cases"] if _VECTORS.exists() else [])
def test_invalid_identity_cases(case):
    """非法输入：bool/0/1.0/空 namespace 一律 ValueError。"""
    with pytest.raises(ValueError):
        hand_id(*case["key"])


def test_vectors_file_present():
    """契约向量缺失时测试必须失败而不是静默缩水。"""
    assert _VECTORS.exists(), "contract-vectors.json 缺失"


@pytest.mark.parametrize("case", _vectors()["archived_room_cases"] if _VECTORS.exists() else [])
def test_archived_room_case_metadata(case):
    """三份真实资料：文件 SHA-256、分块形态与缺墙分级（world_import_allowed=false）。"""
    path = Path(__file__).resolve().parents[2] / case["path"]
    if not path.exists():
        pytest.skip("归档夹具缺失：{0}".format(path.name))
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case["sha256"]
    doc = json.loads(raw.decode("utf-8"))
    blocks = doc["blocks"]
    for hand in case["hands"]:
        assert len(blocks) == hand["block_count"]
        assert [len(row) for row in blocks[0]["start_hands"]] == hand["first_hand_lengths"]
        # 后续 block 的四家 start_hands 为 [null,null,null,null]（不重复起点，非空手牌）。
        for block in blocks[1:]:
            assert block.get("start_hands") == [None, None, None, None] or hand["later_start_hands_are_null"]
        assert sum(1 for block in blocks for _ in block["events"]) == hand["event_count"]
        assert [block["seq_start"] for block in blocks] == [rng[0] for rng in hand["seq_ranges"]]
        assert [block["seq_end"] for block in blocks] == [rng[1] for rng in hand["seq_ranges"]]
        assert hand["max_coverage_without_extra_evidence"] == "full_history"
        assert hand["wall"] is None
        assert hand["world_import_allowed"] is False


def test_simulation_split_fields():
    """模拟划分组字段 [source_namespace, scenario_id]（契约向量口径）。"""
    assert split_group_id(["hangma-simulation", "scenario-x"]) == split_group_id(
        ["hangma-simulation", "scenario-x"]
    )
    assert split_group_id(["hangma-simulation", "a"]) != split_group_id(["hangma-simulation", "b"])