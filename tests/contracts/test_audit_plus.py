"""parallel-v1 共同验收向量的审计线消费测试（契约 §9）。

向量来源：doc/implementation/contracts/contract-vectors.json（contract_id=
parallel-v1）。本文件锁定：身份哈希算法、非法输入拒绝、四进程加重启
视角合并、三个真实分块样本的转换评级、预算平移与未知主版本拒绝。
行为向量 audit-crosses-send-deadline / codec-fails-before-emit 的完整
决策循环用例在 tests/unit/application/test_decision_loop_audit_plus.py
与 tests/unit/application/test_audit_trail_plus.py（同一工作线测试目录）。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from hangma_bot.adapters.official.replay import parse_room_document, round_data
from hangma_bot.adapters.recording.bundle import create_bundle, pack_bundle
from hangma_bot.application.audit_codec import translate_monotonic_deadlines
from hangma_bot.offline.replay import (
    build_dataset,
    hand_id,
    load_hand_rows,
    split_group_id,
)

ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = ROOT / "doc" / "implementation" / "contracts" / "contract-vectors.json"
FIXTURES = ROOT / "tests" / "fixtures" / "hangma" / "archived-rooms"


def _vectors():
    with VECTORS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_identity_algorithm_matches_vector_encoding():
    """身份编码口径：ensure_ascii=False / separators=(comma,colon) /
    allow_nan=False 的 UTF-8 JSON 数组 → SHA-256 全长十六进制。"""

    fields = ["hangma-official", "t_6c121bfda7e8", "t_6c121bfda7e8_r4_b0_t0", 1]
    encoded = json.dumps(fields, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert _sha256_text(encoded) == "769903c4f23a976a785f84c8d473d55096ae2c0d81b2d83bc4b4d7688cbaac5f"


def test_identity_cases_match_frozen_vectors():
    vectors = _vectors()
    for case in vectors["identity_cases"]:
        namespace, tournament, game, round_no = case["key"]
        assert hand_id(namespace, tournament, game, round_no) == case["hand_id"]
        assert split_group_id(namespace, tournament) == case["official_split_group_id"]


def test_invalid_identity_cases_raise_value_error():
    vectors = _vectors()
    for case in vectors["invalid_identity_cases"]:
        with pytest.raises(ValueError):
            hand_id(*case["key"])


def test_identity_components_not_stripped_or_case_folded():
    # 契约：前三项不做 strip/大小写改写，不同字符串必须是不同身份。
    assert hand_id("ns", "room", "game", 1) != hand_id("ns ", "room", "game", 1)
    assert hand_id("ns", "Room", "game", 1) != hand_id("ns", "room", "game", 1)


def test_budget_translation_vector():
    vectors = _vectors()
    spec = vectors["budget_translation"]
    translated = translate_monotonic_deadlines(
        spec["old_origin"], spec["old_deadlines"], spec["new_origin"]
    )
    assert list(translated) == spec["new_deadlines"]


def _write_run_decisions(root: Path, run_id: str, participant_id: str, attempt: str) -> None:
    """写入一条携带完整场次身份与决策输入的记录（单局身份合并的视角来源）。"""

    from hangma_bot.application.audit_codec import (
        decision_budget_to_json,
        decision_request_to_json,
    )
    from hangma_bot.hangma.interface import RuleAnalysis, RuleCompleteness
    from hangma_bot.kernel.actions import Discard, Tile, WindowKey, WindowPhase, action_key
    from hangma_bot.kernel.observation import (
        CompetitionContext,
        PlayerObservation,
        RulePublicState,
    )
    from hangma_bot.policy.interface import DecisionBudget, DecisionRequest

    observation = PlayerObservation(
        game_id="t_6c121bfda7e8_r4_b0_t0", seat=0, round_no=1, snapshot_seq=10,
        phase="draw", dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=(Tile("1w"), Tile("2w"), Tile("3w")), drawn_tile=None,
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13), last_discard=None, remaining_tile_count=None,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=False),
        public_history=(),
    )
    window_key = WindowKey(
        game_id="t_6c121bfda7e8_r4_b0_t0", round_no=1, trigger_seq=10,
        phase=WindowPhase.DRAW, seat=0,
    )
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="t_6c121bfda7e8", stage_no=None, stage_role=None,
            stage_total=None, participant_rank=None, ranking=(),
            observed_at_unix_ms=1,
        ),
        rules=RuleAnalysis(
            legal_candidates=(
                _candidate(Discard(Tile("1w"))),
            ),
            emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="v1",
            issues=(),
        ),
        decision_id="dec-" + run_id,
        trigger_seq=10,
        window_key=window_key,
        rejected_attempts=(),
    )
    budget = DecisionBudget(100.5, 100.7, 100.85)
    run_dir = root / "runs" / run_id / "participants" / participant_id
    run_dir.mkdir(parents=True)
    payload = {
        "plan_revision": 1,
        "budget_origin_monotonic": 100.0,
        "rule_elapsed_ms": 1.0,
        "request": decision_request_to_json(request),
        "budget": decision_budget_to_json(budget),
        "window": {"game_id": "t_6c121bfda7e8_r4_b0_t0", "round_no": 1, "trigger_seq": 10, "phase": "draw", "seat": 0},
        "capture_profile": "audit-plus-v1",
        "audit_producer": "application",
    }
    context = {
        "run_id": run_id,
        "tournament_id": "t_6c121bfda7e8",
        "participant_id": participant_id,
        "stage_attempt_id": attempt,
        "game_id": "t_6c121bfda7e8_r4_b0_t0",
        "round_no": 1,
        "trigger_seq": 10,
        "decision_id": "dec-" + run_id,
    }
    line_input = json.dumps(
        {"schema_version": 1, "kind": "decision_input", "context": context,
         "wall_time_unix_ms": 1, "monotonic_ns": 1, "payload": payload},
        ensure_ascii=False,
    )
    line_ended = json.dumps(
        {"schema_version": 1, "kind": "decision_ended", "context": context,
         "wall_time_unix_ms": 2, "monotonic_ns": 2,
         "payload": {"plan_revision": 1, "end_reason": "exhausted",
                     "attempt_count": 0, "sent_attempts": 0}},
        ensure_ascii=False,
    )
    (run_dir / "decisions.jsonl").write_text(
        line_input + chr(10) + line_ended + chr(10), encoding="utf-8"
    )
    (root / "runs" / run_id / "summary.json").write_text("{}", encoding="utf-8")


def _candidate(action):
    from hangma_bot.hangma.interface import RuleCandidate
    from hangma_bot.kernel.actions import action_key

    return RuleCandidate(action=action, action_key=action_key(action), evidence=("v",))


def test_multi_process_merge_vector():
    """四进程不同 attempt + 重启第五视角 → 一个 hand_id、五个 view、
    一个 split_group_id；无权威结束证据时 attempt_status=unknown。"""

    vectors = _vectors()
    spec = vectors["multi_process_merge"]
    namespace, tournament, game, round_no = spec["key"]
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        run_ids = []
        for view in spec["views"]:
            run_ids.append(view["run_id"])
            _write_run_decisions(
                root, view["run_id"], view["participant_id"], view["local_stage_attempt_id"]
            )
        manifest = create_bundle(root, run_ids=run_ids, out_dir=root / "bundles-root")
        bundle_dir = root / "bundles-root" / "bundles" / manifest.bundle_id
        report = build_dataset(
            bundle_dir, root / "datasets", source_namespace=namespace
        )
        dataset_dir = Path(report["dataset_dir"])
        index_rows = [
            json.loads(line)
            for line in (dataset_dir / "index.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(index_rows) == spec["expected_hand_count"]
        index = index_rows[0]
        assert index["hand_id"] == hand_id(namespace, tournament, game, round_no)
        assert index["split_group_id"] == split_group_id(namespace, tournament)
        assert len(index["views"]) == spec["expected_view_count"]
        assert len({index["split_group_id"]}) == spec["expected_split_group_count"]
        assert index["attempt_status"] == spec["status_without_authoritative_end"]
        assert report["validation"]["file_integrity"]["status"] == "passed"
        assert report["validation"]["decision_completeness"]["status"] == "passed"


def test_archived_room_cases_match_vectors():
    """三个真实分块样本：块数、seq 范围、事件数、起手张数、后续块空起点、
    无牌墙评级 full_history、世界导入不允许——全部按向量值验收。"""

    vectors = _vectors()
    for case in vectors["archived_room_cases"]:
        fixture = FIXTURES / Path(case["path"]).name
        document = json.loads(fixture.read_text(encoding="utf-8"))
        file_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
        assert file_sha == case["sha256"], "夹具哈希漂移: {}".format(case["path"])
        parsed = parse_room_document(document)
        assert parsed.room_id == case["room_id"]
        assert parsed.game_id == case["game_id"]
        assert parsed.batch == case["batch"]
        for hand in case["hands"]:
            data = round_data(
                parsed, hand["round_no"], file_sha256=file_sha, json_pointer="#"
            )
            assert hand_id(
                "hangma-official", case["room_id"], case["game_id"], hand["round_no"]
            ) == hand["hand_id"]
            assert split_group_id(
                "hangma-official", case["room_id"]
            ) == hand["split_group_id"]
            assert data["block_count"] == hand["block_count"]
            assert data["seq_ranges"] == hand["seq_ranges"]
            assert len(data["events"]) == hand["event_count"]
            assert data["initial"]["start_hand_lengths"] == hand["first_hand_lengths"]
            assert data["initial"]["later_start_hands_are_null"] == hand["later_start_hands_are_null"]
            assert data["coverage"] == hand["max_coverage_without_extra_evidence"]
            assert data["initial"]["wall"] is None
            assert data["initial"]["draw_identity_known"] is False
            # full_history 不等于可导入完整世界：无牌墙时世界导入不允许。
            assert data["initial"]["world_payload"] is None
            assert data["initial"]["wall"] is None  # world_import_allowed 恒 False 的依据


def test_unknown_replay_major_rejected():
    """未知主版本拒绝读取且保留原文件（行为向量 unknown-replay-major）。"""

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "hands.jsonl"
        path.write_text(
            json.dumps({"replay_schema_version": 99, "hand_id": "hand-x"}) + chr(10),
            encoding="utf-8",
        )
        original = path.read_bytes()
        with pytest.raises(ValueError):
            load_hand_rows(path)
        assert path.read_bytes() == original  # 拒绝读取时不改动原文件


def test_split_group_id_official_fields_are_namespace_and_tournament():
    vectors = _vectors()
    first = vectors["identity_cases"][0]
    namespace, tournament = first["key"][0], first["key"][1]
    # 划分键只含 namespace+tournament：同一赛事的两个单局共享同一划分键。
    assert split_group_id(namespace, tournament) == first["official_split_group_id"]
    case2 = vectors["identity_cases"][1]
    assert case2["official_split_group_id"] == first["official_split_group_id"]
