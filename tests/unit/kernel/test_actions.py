"""kernel.actions 的单元测试：牌值域、动作参数、封闭联合与稳定动作键。"""

import unittest
from dataclasses import FrozenInstanceError
from typing import get_args

from hangma_bot.kernel.actions import (
    CANONICAL_TILE_CODES,
    SEAT_COUNT,
    Action,
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)


class TileTests(unittest.TestCase):
    """规范牌值的值域、不可变性与确定性。"""

    def test_accepts_exactly_the_official_tile_codes(self) -> None:
        """34 个官方牌码（万/筒/条 + 东南西北中发白）全部可构造。"""
        expected = (
            {"{0}w".format(number) for number in range(1, 10)}
            | {"{0}b".format(number) for number in range(1, 10)}
            | {"{0}t".format(number) for number in range(1, 10)}
            | {"东", "南", "西", "北", "中", "发", "白"}
        )
        self.assertEqual(CANONICAL_TILE_CODES, frozenset(expected))
        self.assertEqual(len(CANONICAL_TILE_CODES), 34)
        for code in expected:
            self.assertEqual(Tile(code).code, code)

    def test_rejects_unknown_or_malformed_codes(self) -> None:
        """未映射的官方字符串、空值和非字符串必须在构造时失败。"""
        for bad in ("x1", "1W", "", "0w", "10w", "白板", 1, None):
            with self.assertRaises(ValueError):
                Tile(bad)

    def test_tile_is_immutable_orderable_and_deterministic(self) -> None:
        """值对象不可变；排序与哈希为候选排序提供确定性。"""
        with self.assertRaises(FrozenInstanceError):
            Tile("1w").code = "2w"  # type: ignore[misc]
        self.assertLess(Tile("1w"), Tile("2w"))
        self.assertEqual(Tile("1w"), Tile("1w"))
        self.assertEqual(hash(Tile("1w")), hash(Tile("1w")))


class ActionParameterTests(unittest.TestCase):
    """动作参数的结构校验：只收规范 Tile 与枚举，防裸字符串混入。"""

    def test_rejects_raw_strings_in_place_of_tiles(self) -> None:
        """官方牌码字符串必须先映射为 Tile，不能直接塞进动作参数。"""
        constructors = (
            lambda: Discard("1w"),
            lambda: Peng("1w"),
            lambda: Gang("1w", GangKind.CONCEALED),
            lambda: Chi(("1w", "2w", "3w")),
        )
        for construct in constructors:
            with self.assertRaises(ValueError):
                construct()

    def test_chi_requires_exactly_three_tiles(self) -> None:
        """吃牌动作固定三张（含被吃牌）；张数错误立刻失败。"""
        valid = (Tile("1w"), Tile("2w"), Tile("3w"))
        self.assertEqual(Chi(valid).tiles, valid)
        for tiles in (valid[:2], valid + (Tile("4w"),)):
            with self.assertRaises(ValueError):
                Chi(tiles)

    def test_gang_requires_gang_kind_enum(self) -> None:
        """杠种必须是 GangKind 枚举；官方 an/ming/bu 由适配器映射。"""
        with self.assertRaises(ValueError):
            Gang(Tile("1w"), "concealed")
        self.assertEqual(Gang(Tile("1w"), GangKind.ADDED).kind, GangKind.ADDED)

    def test_actions_are_immutable(self) -> None:
        """封闭联合成员都是冻结值对象。"""
        action = Discard(Tile("1w"))
        with self.assertRaises(FrozenInstanceError):
            action.tile = Tile("2w")  # type: ignore[misc]


class ClosedActionUnionTests(unittest.TestCase):
    """封闭动作联合与 action_key 的覆盖性、确定性与唯一性。"""

    def test_union_covers_exactly_the_six_action_types(self) -> None:
        """封闭联合回归：增删动作种类必须显式更新契约与文档。"""
        self.assertEqual(
            {member.__name__ for member in get_args(Action)},
            {"Discard", "Chi", "Peng", "Gang", "Hu", "Pass"},
        )

    def test_action_key_covers_all_kinds_deterministically(self) -> None:
        """每个动作种类的键确定、可重复，且不同动作不共享键。"""
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
        keys = [action_key(action) for action in samples]
        self.assertEqual(len(set(keys)), len(keys))
        for action, key in zip(samples, keys):
            self.assertIsInstance(key, str)
            self.assertTrue(key)
            self.assertEqual(action_key(action), key)
        self.assertEqual(keys[0], "discard:1w")
        self.assertEqual(keys[1], "chi:1w,2w,3w")
        self.assertEqual(keys[3], "gang:concealed:3w")

    def test_action_key_contains_no_nondeterministic_parts(self) -> None:
        """键只由动作种类与牌值决定，不含内存地址等不稳定成分。"""
        self.assertEqual(action_key(Discard(Tile("5t"))), action_key(Discard(Tile("5t"))))
        self.assertNotIn("0x", action_key(Hu()))

    def test_unknown_action_type_raises_type_error(self) -> None:
        """联合之外的类型必须抛 `TypeError`——跨模块故障隔离契约。

        `hangma` 验证与 `policy` 候选过滤依赖 `except TypeError` 隔离
        未知动作对象；改为 `ValueError` 会让异常穿透它们的故障隔离
        （终裁第 3 轮以 hangma/engine.py、policy/weighted_heuristic.py
        的现网捕获为证推翻了统一提案）。
        """
        with self.assertRaises(TypeError):
            action_key(object())


class WindowKeyTests(unittest.TestCase):
    """动作窗口键的结构校验与窗口区分。"""

    def _key(self, **overrides: object) -> WindowKey:
        base = {
            "game_id": "g1",
            "round_no": 1,
            "trigger_seq": 12,
            "phase": WindowPhase.DRAW,
            "seat": 0,
        }
        base.update(overrides)
        return WindowKey(**base)  # type: ignore[arg-type]

    def test_rejects_seat_out_of_range(self) -> None:
        """座位必须位于 0—3；bool 与字符串都不是座位下标。"""
        for seat in (-1, SEAT_COUNT, SEAT_COUNT + 1, True, "0", None):
            with self.assertRaises(ValueError):
                self._key(seat=seat)
        self.assertEqual(self._key(seat=3).seat, 3)

    def test_rejects_empty_game_id_and_raw_phase_string(self) -> None:
        """场次标识非空且非纯空白；阶段必须使用规范枚举而不是裸字符串。"""
        with self.assertRaises(ValueError):
            self._key(game_id="")
        with self.assertRaises(ValueError):
            self._key(game_id="   ")
        with self.assertRaises(ValueError):
            self._key(phase="draw")

    def test_phase_values_match_official_snapshot_phases(self) -> None:
        """枚举值与官方快照 phase 的行动子集一致；官方值变化必须更新。"""
        self.assertEqual(
            {phase.value for phase in WindowPhase},
            {"draw", "response_peng", "response_chi"},
        )

    def test_peng_and_chi_are_distinct_windows(self) -> None:
        """同一弃牌的碰与吃是两个窗口（与契约测试同一语义）。"""
        self.assertNotEqual(
            self._key(phase=WindowPhase.RESPONSE_PENG),
            self._key(phase=WindowPhase.RESPONSE_CHI),
        )

    def test_rejects_mutable_container_input(self) -> None:
        """反例回归：可变 list 不得进入冻结值对象。

        若接受 list，构造后原位改写会使 `action_key` 漂移、对象不可哈希，
        破坏已拒绝动作排除与审计关联（终裁 IMP/RS-4：拒绝式修复）。
        """
        with self.assertRaises(ValueError):
            Chi([Tile("1w"), Tile("2w"), Tile("3w")])
        # tuple 构造的身份稳定：动作键与哈希在构造后不可被外界改变。
        chi = Chi((Tile("1w"), Tile("2w"), Tile("3w")))
        self.assertEqual(action_key(chi), "chi:1w,2w,3w")
        self.assertEqual(hash(chi), hash(Chi((Tile("1w"), Tile("2w"), Tile("3w")))))

    def test_rejects_bad_round_no_and_trigger_seq(self) -> None:
        """反例回归：窗口序号必须是纯非负 int（bool/str/float/负数拒绝）。

        `trigger_seq=0` 必须放行：官方协议用 seq=0 请求全量快照（API §2.3）。
        """
        for field_name in ("round_no", "trigger_seq"):
            for bad in (-1, -5, True, "1", None, 1.5):
                with self.assertRaises(ValueError):
                    self._key(**{field_name: bad})
        self.assertEqual(self._key(round_no=0, trigger_seq=0).trigger_seq, 0)


if __name__ == "__main__":
    unittest.main()
