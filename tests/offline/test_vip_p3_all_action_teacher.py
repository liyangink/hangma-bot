"""P3 全动作教师的同窗、同世界与积分守恒合同。"""

from scripts.vip_p3_all_action_teacher import audit


def test_all_legal_arms_keep_one_outcome_per_world_and_claim_followup_is_distinct():
    """吃后跟打不冒充普通摸牌；每一合法动作都保留自身结局。"""

    report = audit(start_seed=1001, seeds=1, worlds_per_root=2)
    assert report["root_count"] == 3
    assert report["action_worlds"] == 50
    assert report["tag_counts"] == {
        "draw_1": 1, "draw_5": 1, "response_chi_actionable": 1,
    }
    for row in report["rows"]:
        assert set(row["outcomes_by_action"]) == set(row["legal_action_keys"])
        assert len(row["legal_action_keys"]) == len(set(row["legal_action_keys"]))
        assert all(len(outcomes) == row["sample_count"]
                   for outcomes in row["outcomes_by_action"].values())
        for outcomes in row["outcomes_by_action"].values():
            assert [item["sample"] for item in outcomes] == list(range(row["sample_count"]))
            assert all(sum(item["terminal"]["score_delta"]) == 0 for item in outcomes)
            assert all("next_observation" in item["first_event"]
                       for item in outcomes if item["first_event"]["kind"] not in
                       ("self_win", "other_win", "draw"))
    first = next(row for row in report["rows"] if "draw_1" in row["tags"])
    baseline, alternate = (first["outcomes_by_action"][key][0]
                           for key in first["legal_action_keys"][:2])
    assert baseline["first_event_key"] == alternate["first_event_key"]
    assert baseline["first_event"]["next_observation"] != (
        alternate["first_event"]["next_observation"])
    claim = next(row for row in report["rows"] if row["phase"] == "response_chi")
    assert claim["sampling_mode"] == "resampled_same_observation"
    assert claim["sample_count"] == 2
    assert {item["first_event_key"] for item in
            claim["outcomes_by_action"]["chi:3b,4b,5b"]} == {"self_claim_followup"}
    assert all(item["first_event_key"].startswith("self_normal_draw:")
               for item in claim["outcomes_by_action"]["pass"])
