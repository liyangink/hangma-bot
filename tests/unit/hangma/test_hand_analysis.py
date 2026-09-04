"""hand_analysis 单元测试：金例重放 + 正反例 + 性质。

金例夹具：tests/fixtures/official/v9/fan-calc/cases*.jsonl
（61 例 hu=true + 37 例 hu=false + 1 例 400 输入校验；含 59 例随机偏置
对拍 cases-random-crossval.jsonl，2026-09-03 官方 fan-calc 实测 0 差异）。
"""

import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.hangma.hand_analysis import (
    analyse_hand,
    any_tile_win,
    win_split,
)
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.kernel.actions import Tile

FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "fixtures" / "official" / "v9" / "fan-calc"
)
CASE_FILES = (
    "cases.jsonl",
    "cases-baotou.jsonl",
    "cases-baotou2.jsonl",
    "cases-chain4.jsonl",
    "cases-random-crossval.jsonl",
)


def _load_cases():
    """加载金例并归一化两种行格式（request/response 与 顶层 hand/resp）。"""

    cases = []
    for name in CASE_FILES:
        for line in (FIXTURE_DIR / name).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if "http_status" in obj:
                continue  # 400 输入校验例：白板总数超 4，不进入牌型对拍
            request = obj.get("request", obj)
            response = obj.get("response") or obj["resp"]
            cases.append(
                pytest.param(
                    tuple(Tile(code) for code in request["hand"] + [request["draw"]]),
                    response,
                    id=obj["tag"],
                )
            )
    return cases


GOLDEN_CASES = _load_cases()


def tiles(*codes):
    return tuple(Tile(code) for code in codes)


# ---------------------------------------------------------------------------
# 金例参数化重放
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hand14,response", GOLDEN_CASES)
def test_golden_win_split_matches_hu(hand14, response):
    """38 例 hu=true 全部非 None；唯一 hu=false 例必须 None。"""

    split = win_split(hand14, 0)
    assert (split is not None) == response["hu"]


@pytest.mark.parametrize("hand14,response", GOLDEN_CASES)
def test_golden_branch_and_luxury_match_detail(hand14, response):
    """分支与豪华组数与官方 detail[0]（平胡/七对/豪华七对×N）交叉验证。"""

    if not response["hu"]:
        return
    split = win_split(hand14, 0)
    head = response["detail"][0]
    if head == "平胡":
        assert split.branch == "平胡" and split.luxury_pairs == 0
    elif head == "七对":
        assert split.branch == "七对" and split.luxury_pairs == 0
    else:
        luxury = int(head.split("×")[1])
        assert split.branch == "七对" and split.luxury_pairs == luxury


@pytest.mark.parametrize("hand14,response", GOLDEN_CASES)
def test_golden_baotou_equivalence(hand14, response):
    """爆头 ⟺ any_tile_win(摸前 13 张) ∧ (hand+draw).count(白) != 4。"""

    hand13 = hand14[:-1]
    whites14 = sum(1 for tile in hand14 if tile.code == "白")
    predicted = any_tile_win(hand13, 0) and whites14 != 4
    assert predicted == response["baotou"]


# ---------------------------------------------------------------------------
# 胡牌判定正反例（白板语义锚点，RULES_EVIDENCE §2/§5）
# ---------------------------------------------------------------------------


def test_win_basic_plain():
    hand = tiles("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东")
    split = win_split(hand, 0)
    assert split is not None and split.branch == "平胡"


def test_not_win_thirteen_orphans_style():
    hand = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b", "5b")
    assert win_split(hand, 0) is None


def test_white_pads_run_start_position():
    # 白 + 8w + 9w = 789w：白垫顺子起始位（最易错点）。
    hand = tiles("白", "8w", "9w", "1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b", "东", "东")
    split = win_split(hand, 0)
    assert split is not None and split.whites_held == 1


def test_white_triplet_and_white_pair():
    # 白白白可自刻（占 1 组面子）；白白可自将对。
    assert win_split(tiles("白", "白", "白", "东", "东"), 3) is not None
    assert win_split(tiles("白", "白"), 4) is not None  # 0 组面子 + 将


def test_four_whites_in_hand_can_win():
    # 4 白在手可胡（金例 four-white-kept 同型变体）。
    hand = tiles("白", "白", "白", "白", "1w", "2w", "3w", "4w", "5w", "6w", "东", "东", "9w", "9w")
    split = win_split(hand, 0)
    assert split is not None and split.whites_held == 4


def test_chiitoi_win_with_white_substitution():
    hand = tiles("1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w", "5w", "6w", "6w", "白", "白")
    split = win_split(hand, 0)
    assert split is not None and split.branch == "七对" and split.luxury_pairs == 0


def test_meld_set_count_reduces_required_sets():
    # 1 副露：11 张暗牌 = 3 面子 + 将。
    hand = tiles("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w")
    assert win_split(hand, 1) is not None
    assert win_split(hand, 0) is None  # 门清口径差一组面子


def test_chiitoi_forbidden_with_melds():
    # 七对牌型 + 1 副露：七对分支不可用；此牌无顺/刻结构（仅 1 白）不成标准型。
    hand = tiles("1w", "1w", "3w", "3w", "5w", "5w", "7w", "7w", "9w", "9w", "白")
    summary = analyse_hand(hand, 1)
    assert summary.chiitoi_shanten is None
    assert not summary.is_win


# ---------------------------------------------------------------------------
# 向听与有效牌
# ---------------------------------------------------------------------------


def test_shanten_tenpai_and_useful_tiles():
    # 123w 456w 789w 123b + 4b：听 1b（1b1b 将 + 234b）/4b（单骑）/白。
    hand13 = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b")
    summary = analyse_hand(hand13, 0)
    assert summary.shanten == 0
    codes = [entry.code for entry in summary.useful_tiles]
    assert codes == ["1b", "4b", "白"]
    assert all(entry.shanten_after == -1 for entry in summary.useful_tiles)


def test_shanten_two_away_and_progression():
    # 3 面子 + 12b 搭 + 4b 单：一向听；摸 3b 后听牌。
    hand13 = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "4b", "东")
    summary = analyse_hand(hand13, 0)
    assert summary.shanten == 1
    improved = analyse_hand(hand13 + (Tile("3b"),), 0)
    assert improved.shanten == 0


def test_chiitoi_shanten_value():
    # 5 对 + 3 单张（14 张）：七对向听 1。
    hand = tiles("1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w", "5w", "6w", "7w", "8w", "9w")
    summary = analyse_hand(hand, 0)
    assert summary.chiitoi_shanten == 1


def test_shanten_respects_four_copy_cap():
    # 评审回归例（d5 前轮）：123w456w789w + 东×4——第 5 张东不存在，
    # "东东将 + 东东虚刻"不可行，真实向听为 1（弃东改听单骑任一非东）。
    hand13 = tiles(
        "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "东"
    )
    summary = analyse_hand(hand13, 0)
    assert summary.shanten == 1
    codes = [entry.code for entry in summary.useful_tiles]
    assert "东" not in codes  # 不可能摸到的第 5 张东不是有效牌
    assert "白" in codes and len(codes) == 33  # 其余种类皆可作单骑将眼


def test_shanten_four_copy_cap_quad_natural():
    # 1w×4 在手：第 5 张 1w 摸不到，不进有效牌；其余种类均可推进
    #（[111],[456],[789],[东东东] + 虚牌将 = need 2 → 向听 1）。
    hand13 = tiles(
        "1w", "1w", "1w", "1w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东"
    )
    summary = analyse_hand(hand13, 0)
    assert summary.shanten == 1
    codes = [entry.code for entry in summary.useful_tiles]
    assert "1w" not in codes  # 第 5 张 1w 不存在
    assert "东" not in codes  # 摸第 4 张东后其将眼虚牌被上限堵死，不推进
    assert "白" in codes and len(codes) == 32


def test_useful_tiles_sorted_and_white_always_useful():
    hand13 = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "2b", "3b")
    summary = analyse_hand(hand13, 0)
    codes = [entry.code for entry in summary.useful_tiles]
    assert codes == sorted(set(codes), key=TILE_ORDER.index)
    assert "白" in codes


def test_win_summary_has_no_useful_tiles():
    hand = tiles("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东")
    summary = analyse_hand(hand, 0)
    assert summary.is_win and summary.shanten == -1
    assert summary.useful_tiles == ()


def test_whites_held_conservation():
    hand = tiles("白", "白", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东")
    summary = analyse_hand(hand, 0)
    assert summary.whites_held == 2


# ---------------------------------------------------------------------------
# 任意听（爆头静态判定核心）
# ---------------------------------------------------------------------------


def test_any_tile_win_true_classic():
    # 双白 + 三顺 + 将：任意牌都胡（金例 std-2white-literal-pair 同型）。
    hand13 = tiles("白", "白", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "2b", "3b")
    assert any_tile_win(hand13, 0) is True


def test_any_tile_win_false_single_white_in_run():
    # 单白进顺/刻非任意听（§5 反例锚点）。
    hand13 = tiles("白", "1w", "2w", "4w", "5w", "7w", "8w", "1b", "2b", "4b", "5b", "7b", "8b")
    assert any_tile_win(hand13, 0) is False


def test_any_tile_win_false_tenpai_only():
    # 普通听牌（仅听特定牌）不是任意听（金例 not-hu 的 13 张口径）。
    hand13 = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b")
    assert any_tile_win(hand13, 0) is False


def test_any_tile_win_with_meld_folding():
    # 副露折算：1 副露后 10 张暗牌 + 任意一张都胡。
    hand10 = tiles("白", "白", "1w", "2w", "3w", "4w", "5w", "6w", "东", "东")
    assert any_tile_win(hand10, 1) is True


def test_win_split_any_tile_tenpai_placeholder():
    hand = tiles("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东")
    split = win_split(hand, 0)
    assert split.any_tile_tenpai is False  # 占位：调用方用 replace 覆盖
    patched = replace(split, any_tile_tenpai=True)
    assert patched.any_tile_tenpai is True


# ---------------------------------------------------------------------------
# 性质：确定性 / 边界校验 / 性能
# ---------------------------------------------------------------------------


def test_determinism_same_input_same_output():
    hand13 = tiles("白", "1w", "2w", "4w", "5w", "7w", "8w", "1b", "2b", "4b", "5b", "7b", "8b")
    first = analyse_hand(hand13, 0)
    second = analyse_hand(hand13, 0)
    assert first == second
    hand14 = tiles("1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w", "5w", "6w", "6w", "7w", "白")
    assert win_split(hand14, 0) == win_split(hand14, 0)


def test_input_order_independence():
    # 输入顺序不影响结果（确定性按 TILE_ORDER 归一）。
    straight = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "东", "1w", "1w")
    shuffled = tuple(reversed(straight))
    assert analyse_hand(straight, 0) == analyse_hand(shuffled, 0)


@pytest.mark.parametrize("bad", [-1, 5, "1", 1.0, True])
def test_invalid_meld_set_count_raises(bad):
    hand = tiles("1w", "2w", "3w")
    with pytest.raises(ValueError):
        analyse_hand(hand, bad)
    with pytest.raises(ValueError):
        win_split(hand, bad)
    with pytest.raises(ValueError):
        any_tile_win(hand, bad)


def test_any_tile_win_performance():
    # 34 次成胡判定应毫秒级（记忆化递归）；上限远宽于性能预算。
    hand13 = tiles("白", "白", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "2b", "3b")
    start = time.perf_counter()
    for _ in range(100):
        any_tile_win(hand13, 0)
    assert time.perf_counter() - start < 5.0


def test_analyse_hand_worst_case_latency():
    """最差手牌单次分析耗时上限（评审 d8-f4dadf info 4）。

    含跨手牌缓存命中场景：紧凑预算键使不同手牌共享记忆化状态，
    连续分析 20 个随机手牌也必须远低于 3 秒窗口预算。
    """

    import random as _random

    rng = _random.Random(20260903)
    pool = [f"{n}{s}" for s in "wbt" for n in range(1, 10)] + list("东南西北中发白")
    worst = tiles("1w", "2w", "4w", "5w", "8w", "9w", "1b", "2b", "5b", "6b", "1t", "4t", "7t", "3w")
    start = time.perf_counter()
    analyse_hand(worst, 0)
    single = time.perf_counter() - start
    assert single < 0.5, "单次最差手牌分析超 500ms：{0}ms".format(single * 1000)
    for _ in range(20):
        hand = tiles(*[rng.choice(pool) for _ in range(14)])
        analyse_hand(hand, 0)
    assert time.perf_counter() - start < 5.0, "20 个随机手牌总耗时超限"

def test_four_whites_held_excludes_fifth_white_from_useful():
    """评审 d12-6cec77 遗留 info：4 白在手且未成胡时，useful 不含白。

    第 5 张白板物理不可得（白板共 4 张）；防御性 append 已由
    whites < 4 守卫约束（评审 d8-f4dadf risk 1），本用例 pin 住口径。
    """

    hand = tiles(
        "白", "白", "白", "白",
        "东", "南", "西", "北", "中", "发", "1w", "9w", "1b", "9b",
    )
    summary = analyse_hand(hand, 0)
    assert summary.is_win is False
    codes = [tile.code for tile in summary.useful_tiles]
    assert "白" not in codes
    assert summary.whites_held == 4
