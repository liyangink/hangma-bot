"""赛后摘要一致性：取自 2026-09-06 测试房 2307 事件下载的最小片段。

来源：runs/adapter-live-d69073e76b58/official/download-20260906/batch-0/events.json。
原文 SHA-256：a93e36161d84579b08e0182a595944c86ce196235ec6315c2f1c18d910f8d4a2。
采用终局 seq=323/719 与错配的 rounds[0]/[1]；其他用例从该片段做明确变异。
只保留公开终局结果，不含 Token/四家手牌；测试不依赖 runs 目录存在。
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from hangma_bot.adapters.official.replay import parse_room_document, round_data


def document():
    return {
        "room_id": "t_d69073e76b58", "game_id": "t_d69073e76b58_r1_b0_t0",
        "batch": 0, "status": "finished", "seats": [],
        "blocks": [{
            "round_no": 1, "seq_start": 323, "seq_end": 323, "dealer": 0,
            "truncated": False, "start_hands": None,
            "events": [{"seq": 323, "type": "round_ended", "seat": 0, "tile": "",
                        "data": {"detail": ["平胡", "爆头"], "draw": False, "fan": 2, "scores": [48, -16, -16, -16]},
                        "ts": 1788694601}],
        }],
        "rounds": [{"round_no": 1, "dealer": 0, "is_draw": 0, "winner": 0,
                    "multiplier": 2, "scores": [48, -16, -16, -16]}],
    }


def read_round(doc, round_no=1):
    return round_data(parse_room_document(doc), round_no, file_sha256="ab"*32, json_pointer="#")


def test_actual_download_wrong_first_summary_is_rejected_without_repairing_source():
    doc = document()
    # 原下载 rounds[0] 实际属于第 7 单局，却被标 round_no=1。
    doc["rounds"][0] = {"dealer": 0, "is_draw": 0, "multiplier": 2, "round_no": 1,
                        "scores": [-2, -2, 20, -16], "winner": 2}
    before = deepcopy(doc)
    with pytest.raises(ValueError, match="official_result_conflict:round_no=1:winner"):
        read_round(doc)
    assert doc == before


def test_actual_download_wrong_second_summary_is_rejected():
    doc = document()
    doc["blocks"][0].update(round_no=2, seq_start=719, seq_end=719)
    doc["blocks"][0]["events"] = [{"seq":719,"type":"round_ended","seat":-1,"tile":"",
                                   "data":{"draw":True,"scores":[0,0,0,0]},"ts":1788694735}]
    doc["rounds"] = [{"dealer":2,"is_draw":0,"multiplier":4,"round_no":2,
                      "scores":[-32,-32,96,-32],"winner":2}]
    with pytest.raises(ValueError, match="official_result_conflict:round_no=2:dealer"):
        read_round(doc, 2)


@pytest.mark.parametrize("field,value,error", [
    ("winner", 1, "winner"), ("is_draw", True, "is_draw"),
    ("scores", [0, 0, 0, 0], "scores"), ("multiplier", 4, "fan"),
    ("dealer", 3, "dealer"),
])
def test_each_provided_summary_fact_is_checked(field, value, error):
    doc = document()
    doc["rounds"][0][field] = value
    with pytest.raises(ValueError, match="official_result_conflict:round_no=1:"+error):
        read_round(doc)


def test_consistent_summary_exposes_all_checked_fields():
    result = read_round(document())
    assert result["result_consistency"] == {
        "status": "passed", "checks": {"dealer":"passed", "winner":"passed", "is_draw":"passed", "scores":"passed", "fan":"passed"},
    }
    assert result["winner_seat"] == 0
    assert result["scores_after"] == [48, -16, -16, -16]


@pytest.mark.parametrize("field,check", [("winner","winner"),("is_draw","is_draw"),("scores","scores"),("multiplier","fan"),("dealer","dealer")])
def test_missing_summary_field_remains_explicitly_unchecked(field, check):
    doc = document()
    del doc["rounds"][0][field]
    result = read_round(doc)
    assert result["result_consistency"]["status"] == "not_checked"
    assert result["result_consistency"]["checks"][check] == "not_checked"
    assert "result_consistency:not_checked:"+check in result["missing_fields"]
    # 不拿终局事件自动填补缺失的摘要结果，保留来源区别。
    if field == "scores":
        assert result["scores_after"] is None


def test_missing_terminal_event_is_readable_but_not_checked():
    doc = document()
    doc["blocks"][0]["events"] = []
    result = read_round(doc)
    assert result["result_consistency"]["status"] == "not_checked"
    assert result["result_consistency"]["checks"]["scores"] == "not_checked"


def test_missing_terminal_field_does_not_count_as_a_passed_comparison():
    doc = document()
    del doc["blocks"][0]["events"][0]["data"]["scores"]
    result = read_round(doc)
    assert result["result_consistency"]["checks"]["scores"] == "not_checked"
    assert result["result_consistency"]["checks"]["fan"] == "passed"


def test_duplicate_round_summary_cannot_silently_select_first():
    doc = document()
    doc["rounds"].append(deepcopy(doc["rounds"][0]))
    with pytest.raises(ValueError, match="duplicate_summary"):
        read_round(doc)


def test_block_dealers_must_agree_within_same_round():
    doc = document()
    block = deepcopy(doc["blocks"][0]);block.update(seq_start=324,seq_end=324,dealer=1)
    block["events"]=[{"seq":324,"type":"game_ended"}]
    doc["blocks"].append(block)
    with pytest.raises(ValueError, match="block.dealer"):
        read_round(doc)


def test_multiple_terminal_events_are_ambiguous_and_rejected():
    doc = document()
    second=deepcopy(doc["blocks"][0]["events"][0]);second["seq"]=324
    doc["blocks"][0]["events"].append(second);doc["blocks"][0]["seq_end"]=324
    with pytest.raises(ValueError, match="multiple_round_ended"):
        read_round(doc)


def test_draw_with_explicit_no_winner_is_consistent_without_invented_fan():
    doc = document()
    doc["rounds"][0].update(is_draw=1,winner=-1,scores=[0,0,0,0]);del doc["rounds"][0]["multiplier"]
    terminal=doc["blocks"][0]["events"][0];terminal.update(seat=-1,data={"draw":True,"scores":[0,0,0,0]})
    result=read_round(doc)
    assert result["winner_seat"] is None and result["is_draw"] is True
    assert result["result_consistency"]["checks"]["winner"] == "passed"
    assert result["result_consistency"]["checks"]["fan"] == "not_checked"


def test_conflicting_duplicate_terminal_cannot_hide_behind_first_copy():
    doc = document()
    second = deepcopy(doc["blocks"][0]["events"][0])
    second["data"]["scores"] = [0, 0, 0, 0]
    doc["blocks"][0]["events"].append(second)
    with pytest.raises(ValueError, match="conflicting_round_ended_copy"):
        read_round(doc)


def test_explicit_fan_alias_is_checked_and_disagreement_with_multiplier_rejected():
    doc = document()
    doc["rounds"][0]["fan"] = 2
    assert read_round(doc)["result_consistency"]["checks"]["fan"] == "passed"
    doc["rounds"][0]["fan"] = 4
    with pytest.raises(ValueError, match="summary.multiplier_fan"):
        read_round(doc)


@pytest.mark.parametrize("field,value", [("winner",4),("dealer",-1),("multiplier",True)])
def test_malformed_supplied_summary_value_is_rejected(field, value):
    doc = document()
    doc["rounds"][0][field] = value
    with pytest.raises(ValueError):
        read_round(doc)
