"""kernel.serialization 的单元测试：往返相等、schema version 与格式校验。"""

import copy
import json
import unittest

from hangma_bot.kernel.actions import Gang, GangKind, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RankingEntry,
    RulePublicState,
)
from hangma_bot.kernel.serialization import (
    KERNEL_VALUE_SCHEMA_VERSION,
    action_from_json,
    action_to_json,
    competition_from_json,
    competition_to_json,
    observation_from_json,
    observation_to_json,
    tournament_config_from_json,
    tournament_config_to_json,
    window_key_from_json,
    window_key_to_json,
)


def _window_key() -> WindowKey:
    return WindowKey(
        game_id="g1",
        round_no=1,
        trigger_seq=12,
        phase=WindowPhase.DRAW,
        seat=0,
    )


def _observation() -> PlayerObservation:
    return PlayerObservation(
        game_id="g1",
        seat=0,
        round_no=1,
        snapshot_seq=5,
        phase="response_chi",
        dealer_seat=3,
        turn_seat=2,
        responding_seats=(0,),
        my_hand=(Tile("8w"), Tile("1w"), Tile("3w"), Tile("白")),
        drawn_tile=None,
        discards=(
            (Tile("2b"),),
            (),
            (Tile("东"), Tile("中")),
            (),
        ),
        melds=(
            (),
            (PublicMeld(seat=1, kind="chi", tiles=(Tile("4t"), Tile("5t"), Tile("6t")), from_seat=2),),
            (),
            (),
        ),
        hand_counts=(10, 9, 13, 13),
        last_discard=PublicDiscard(seat=2, tile=Tile("中"), seq=11),
        remaining_tile_count=None,
        scores=(24, -8, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile("白"), baotou=False, chain_count=1, catch_play=False
        ),
        public_history=(
            PublicEvent(seq=11, kind="tile_discarded", seat=2, tiles=(Tile("中"),), occurred_at_unix_sec=1756771200),
            PublicEvent(seq=12, kind="future_event", seat=None),
        ),
    )


def _competition() -> CompetitionContext:
    return CompetitionContext(
        tournament_id="t1",
        stage_no=1,
        stage_role="finalist",
        stage_total=4,
        participant_rank=None,
        ranking=(
            RankingEntry(participant_id="p1", total_score=120, place_points=9, god_count=2, games_played=8, rank=1),
            RankingEntry(participant_id="p2", total_score=-30, place_points=-3, god_count=0, games_played=8, rank=2),
        ),
        observed_at_unix_ms=1756771200000,
    )


def _config() -> TournamentConfig:
    return TournamentConfig(
        max_games=2,
        rounds_per_game=4,
        rules=RuleConfig(ruleset_version="hangma-v1", base_score=8, you_cai_bi_kao=True),
        timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0, discard_timeout_sec=3.0),
    )


class ActionSerializationTests(unittest.TestCase):
    """动作序列化：往返相等、判别键与格式校验。"""

    def test_round_trip_through_stdlib_json_for_all_kinds(self) -> None:
        """全部动作种类经 stdlib json 编解码后保持相等。"""
        from hangma_bot.kernel.actions import Chi, Discard, Hu, Pass, Peng

        samples = [
            Discard(Tile("1w")),
            Chi((Tile("1w"), Tile("2w"), Tile("3w"))),
            Peng(Tile("2w")),
            Gang(Tile("3w"), GangKind.CONCEALED),
            Gang(Tile("3w"), GangKind.EXPOSED),
            Gang(Tile("3w"), GangKind.ADDED),
            Hu(),
            Pass(),
        ]
        for action in samples:
            payload = action_to_json(action)
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            restored = action_from_json(json.loads(text))
            self.assertEqual(restored, action)
            self.assertEqual(action_from_json(action_to_json(action)), action)

    def test_payload_shape_is_explicit_and_versioned(self) -> None:
        """负载带 schema_version；杠用 gang_kind 区分，键名显式稳定。"""
        payload = action_to_json(Gang(Tile("3w"), GangKind.ADDED))
        self.assertEqual(
            payload,
            {
                "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
                "kind": "gang",
                "gang_kind": "added",
                "tile": "3w",
            },
        )

    def test_rejects_unknown_kind_missing_key_and_version_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            action_from_json({"schema_version": KERNEL_VALUE_SCHEMA_VERSION, "kind": "bugi"})
        with self.assertRaises(ValueError):
            action_from_json(
                {"schema_version": KERNEL_VALUE_SCHEMA_VERSION, "kind": "discard"}
            )
        with self.assertRaises(ValueError):
            action_from_json(
                {
                    "schema_version": KERNEL_VALUE_SCHEMA_VERSION + 1,
                    "kind": "hu",
                }
            )
        with self.assertRaises(ValueError):
            action_from_json(["not", "a", "mapping"])
        with self.assertRaises(ValueError):
            action_from_json(
                {
                    "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
                    "kind": "gang",
                    "gang_kind": "wrong",
                    "tile": "3w",
                }
            )


class WindowKeySerializationTests(unittest.TestCase):
    """窗口键序列化：往返相等与枚举值校验。"""

    def test_round_trip_through_stdlib_json(self) -> None:
        payload = window_key_to_json(_window_key())
        restored = window_key_from_json(json.loads(json.dumps(payload)))
        self.assertEqual(restored, _window_key())

    def test_rejects_unknown_phase_and_bad_shapes(self) -> None:
        with self.assertRaises(ValueError):
            window_key_from_json(
                {
                    "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
                    "game_id": "g1",
                    "round_no": 1,
                    "trigger_seq": 12,
                    "phase": "response_hu",
                    "seat": 0,
                }
            )
        with self.assertRaises(ValueError):
            window_key_from_json(
                {
                    "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
                    "game_id": "g1",
                    "round_no": 1,
                    "trigger_seq": 12,
                    "phase": "draw",
                    "seat": "0",
                }
            )


class ObservationSerializationTests(unittest.TestCase):
    """玩家观察序列化：往返相等、手牌顺序与信息权限。"""

    def test_round_trip_through_stdlib_json(self) -> None:
        observation = _observation()
        payload = observation_to_json(observation)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        restored = observation_from_json(json.loads(text))
        self.assertEqual(restored, observation)

    def test_hand_order_survives_serialization(self) -> None:
        """序列化不得排序或去重官方手牌顺序。"""
        payload = observation_to_json(_observation())
        self.assertEqual(payload["my_hand"], ["8w", "1w", "3w", "白"])
        self.assertEqual(observation_from_json(payload).my_hand[-1], Tile("白"))

    def test_payload_keys_are_exactly_the_visible_fields(self) -> None:
        """序列化键集合与可见字段一一对应，隐藏信息没有输出通道。

        输出键是字段白名单的序列化镜像：未来扩大信息权限或改变线格式
        都必须显式更新本测试。
        """
        expected_keys = {
            "schema_version",
            "game_id",
            "seat",
            "round_no",
            "snapshot_seq",
            "phase",
            "dealer_seat",
            "turn_seat",
            "responding_seats",
            "my_hand",
            "drawn_tile",
            "discards",
            "melds",
            "hand_counts",
            "last_discard",
            "remaining_tile_count",
            "scores",
            "rule_state",
            "public_history",
            "consumed_seq", "history_complete", "chain_piao", "gang_draw", "observation_issues",
        }
        self.assertEqual(set(observation_to_json(_observation())), expected_keys)

    def test_deterministic_output_for_equal_inputs(self) -> None:
        """同输入的输出逐字节稳定（排序键后可复现）。"""
        first = observation_to_json(_observation())
        second = observation_to_json(_observation())
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )

    def test_rejects_missing_key_and_semantically_invalid_values(self) -> None:
        """格式错误与越界值（座位、张数）都必须失败。"""
        payload = observation_to_json(_observation())
        del payload["rule_state"]
        with self.assertRaises(ValueError):
            observation_from_json(payload)
        broken = observation_to_json(_observation())
        broken["seat"] = 9
        with self.assertRaises(ValueError):
            observation_from_json(broken)
        broken = observation_to_json(_observation())
        broken["hand_counts"] = [1, 2, 3]
        with self.assertRaises(ValueError):
            observation_from_json(broken)

    def test_malformed_nested_rows_raise_value_error(self) -> None:
        """反例回归：melds 行形状错误必须抛 ValueError 而非 TypeError。"""
        broken = observation_to_json(_observation())
        broken["melds"] = [[], [], [], 5]
        with self.assertRaises(ValueError):
            observation_from_json(broken)
        broken = observation_to_json(_observation())
        broken["melds"] = [[], [], [], [7]]
        with self.assertRaises(ValueError):
            observation_from_json(broken)

    def test_json_value_alias_covers_list_output(self) -> None:
        """反例回归：JSONValue 别名必须覆盖实际输出的 list 类型。"""
        from typing import get_args, get_origin

        from hangma_bot.kernel.serialization import JSONValue

        self.assertTrue(
            any(get_origin(member) is list for member in get_args(JSONValue)),
            "JSONValue 必须包含 List 成员以匹配 *_to_json 的 list 输出",
        )


class CompetitionAndConfigSerializationTests(unittest.TestCase):
    """赛事上下文与运行配置的序列化往返。"""

    def test_competition_round_trip(self) -> None:
        context = _competition()
        payload = competition_to_json(context)
        restored = competition_from_json(json.loads(json.dumps(payload, ensure_ascii=False)))
        self.assertEqual(restored, context)
        self.assertEqual(
            payload["schema_version"], KERNEL_VALUE_SCHEMA_VERSION
        )

    def test_tournament_config_round_trip(self) -> None:
        config = _config()
        payload = tournament_config_to_json(config)
        restored = tournament_config_from_json(json.loads(json.dumps(payload)))
        self.assertEqual(restored, config)
        self.assertEqual(restored.timing, config.timing)

    def test_forward_compatible_extra_keys_are_ignored(self) -> None:
        """新增可选键不算破坏性变更：解码器必须忽略未知键。"""
        payload = tournament_config_to_json(_config())
        payload["future_optional_key"] = {"nested": True}
        self.assertEqual(tournament_config_from_json(payload), _config())
        action_payload = action_to_json(Gang(Tile("3w"), GangKind.EXPOSED))
        action_payload["future_note"] = "x"
        self.assertEqual(
            action_from_json(action_payload), Gang(Tile("3w"), GangKind.EXPOSED)
        )


class DeepCopyCompatibilityTests(unittest.TestCase):
    """值对象可被标准库 copy 稳定复制（回放/测试场景依赖）。"""

    def test_deep_copy_preserves_equality(self) -> None:
        observation = _observation()
        self.assertEqual(copy.deepcopy(observation), observation)


if __name__ == "__main__":
    unittest.main()
