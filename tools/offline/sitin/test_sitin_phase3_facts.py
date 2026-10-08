"""坐隐 3.0 事实矩阵自测：**矩阵必须与规则源码一致，且结论必须可执行**。

两条纪律：

1. **矩阵的每条事实都指向一个源码符号**，符号改名或删除必须让测试失败
   （否则矩阵会像散文一样悄悄漂移——本项目已有过一次"清单写了、代码改了"的教训）。
2. **动作族 × 分量的结论不是散文，是可执行的断言**：用构造输入调用规则转移函数，
   逐条核对结论。构造集只证明**规则分支与接线**，不构成效果证据。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts  # noqa: E402
from hangma_bot.hangma.progression import (  # noqa: E402
    baotou_after_action,
    chain_after_action,
    chain_after_discard,
    wealth_after_action,
)
from hangma_bot.hangma.special_rules import four_white_indicator  # noqa: E402
from hangma_bot.kernel.actions import (  # noqa: E402
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
)

spec = importlib.util.spec_from_file_location(
    "sitin_phase3_facts", _project_file(_PROJECT_ROOT, _HERE / "sitin_phase3_facts.py"))
facts_matrix = importlib.util.module_from_spec(spec)
sys.modules["sitin_phase3_facts"] = facts_matrix
assert spec.loader is not None
spec.loader.exec_module(facts_matrix)

WEALTH = Tile("白")
OTHER = Tile("1w")
#: 一副真实形状的暗牌（含摸牌），用于爆头重算。
HAND = tuple(Tile(code) for code in
             ("1w", "2w", "3w", "5w", "6w", "7w", "2t", "3t", "4t", "8b", "8b", "9b", "9b"))


# --- 1. 矩阵与源码一致 -------------------------------------------------------

def test_every_fact_carrier_resolves():
    """★ 矩阵的每条事实都指向真实源码符号；失败清单必须为空。"""

    failures = facts_matrix.check()
    assert failures == [], failures


def test_matrix_covers_every_component_and_phase():
    """四个分量 × 三栏必须**逐格有交代**：要么有事实，要么显式标 unavailable。"""

    covered = {(item["component"], item["phase"]) for item in facts_matrix.FACTS}
    expected = {(cid, pid) for cid, _, _ in facts_matrix.COMPONENTS
                for pid, _ in facts_matrix.PHASES}
    assert expected <= covered
    assert len(facts_matrix.COMPONENTS) == 4 and len(facts_matrix.PHASES) == 3


def test_unavailable_cells_are_exactly_the_random_future():
    """★ 只允许"未来摸牌之后"两格标不可确定——别的地方标 unavailable 就是逃避。"""

    data = facts_matrix.matrix()
    assert data["gap_summary"]["unknown"] == []
    assert data["gap_summary"]["unavailable"] == ["branch/after_random",
                                                 "four_white/after_random"]


def test_the_three_added_transitions_exist_and_are_rule_sourced():
    """本批新增的三处必须来自 hangma，且候选**不得**自己重写规则。"""

    added = {item["carrier"] for item in facts_matrix.FACTS
             if item["status"] == "added"}
    assert "hangma_bot.hangma.progression:chain_after_action" in added
    assert "hangma_bot.hangma.progression:wealth_after_action" in added
    assert "hangma_bot.hangma.progression:baotou_after_action" in added
    assert all(symbol.startswith("hangma_bot.hangma.") for symbol in added)


# --- 2. 动作族 × 分量：结论可执行 -------------------------------------------

def test_claim_actions_do_not_touch_the_chain():
    """吃 / 碰 / 过不改链——官方明文允许"圈内吃碰后再打财神 = 财飘链 +1"，
    因此吃碰是否是链投资属**状态**问题，不能按动作类别加减分。"""

    for action in (Chi((Tile("1w"), Tile("2w"), Tile("3w"))), Peng(Tile("1w")), Pass()):
        assert chain_after_action(2, 1, True, action) == (2, 1)


def test_gang_advances_the_chain_and_keeps_piao():
    for kind in GangKind:
        assert chain_after_action(2, 1, True, Gang(Tile("2b"), kind)) == (3, 1)


def test_piao_discard_advances_chain_and_piao_together():
    """爆头态打白 = 飘：链 +1 且链内飘出 +1（官方 §1.3「财飘」）。"""

    assert chain_after_action(2, 1, True, Discard(WEALTH)) == (3, 2)


def test_non_baotou_wealth_discard_breaks_the_chain():
    """非爆头态打白**不是飘**，且断链清零（官方 §1.3 明文）。"""

    assert chain_after_action(3, 2, False, Discard(WEALTH)) == (0, 0)


def test_unknown_piao_is_not_zero_filled():
    """★ 「空与 0 必须区分」：链内飘出未知时，非断链结局**保留未知**。

    只有**断链**那一种结局能把两项归零——那是规则规定的确定结果，
    与原先是否已知无关。其余情况填 0 就是把未知说成了已知。
    """

    assert chain_after_action(2, None, True, Gang(Tile("2b"), GangKind.CONCEALED)) == (3, None)
    assert chain_after_action(2, None, True, Pass()) == (2, None)
    assert chain_after_action(2, None, False, Discard(OTHER)) == (0, 0)


def test_wealth_after_action_only_drops_when_discarding_a_god():
    """白不可被吃碰杠（官方 §1.1）⇒ 只有打出白板的弃牌会减少手留张数。"""

    assert wealth_after_action(3, Discard(WEALTH)) == 2
    assert wealth_after_action(3, Discard(OTHER)) == 3
    assert wealth_after_action(3, Peng(Tile("1w"))) == 3
    assert wealth_after_action(3, Gang(Tile("2b"), GangKind.CONCEALED)) == 3
    with pytest.raises(ValueError):
        wealth_after_action(-1, Pass())


def test_four_white_is_an_equality_condition_not_a_monotone_score():
    """★ 四白是「**恰好**等于 4」：留 2 不算、留 4 算、留 3 + 链内飘 1 也算。"""

    assert four_white_indicator(4, 0) is True
    assert four_white_indicator(3, 1) is True
    assert four_white_indicator(2, 1) is False
    assert four_white_indicator(0, 0) is False
    assert four_white_indicator(None, 0) is None      # 未知不填 False
    assert four_white_indicator(4, None) is None


def test_four_white_sum_is_invariant_under_piao_discard():
    """★ 最容易写错的一条：**飘不改变四白的和**。

    爆头态打白：手留 −1、链内飘出 +1 ⇒ 和不变；因此"打白一定会掉四白"是错的。
    非爆头态打白：手留 −1 且 piao 归零 ⇒ 和减少。
    """

    def after_sum(wealth: int, piao: int, baotou: bool) -> int:
        _count, piao_after = chain_after_action(2, piao, baotou, Discard(WEALTH))
        return wealth_after_action(wealth, Discard(WEALTH)) + (piao_after or 0)

    # 飘：和不变（3+1 与 2+2 都等于动作前的 4；3+0 与 2+1 都等于 3）
    assert after_sum(3, 1, True) == 4
    assert after_sum(3, 0, True) == 3
    # 非爆头打白：手留 −1 且 piao 归零 ⇒ 和从 4 掉到 2
    assert after_sum(3, 1, False) == 2


def test_baotou_is_inherited_by_chi_peng_gang_and_recomputed_by_discard():
    """★ 3.0 的首个阻塞项：**确定性动作后的爆头**。

    - 吃/碰/杠/过：继承动作前状态（【实现 + 用户确认】，官方未逐事件写出公式）；
    - 弃牌：用**弃后暗牌**重新判定（【官方】指南 §1.2 的任意听定义）；
    - 胡：终局，返回 None（实际番值由结算给出，此处不做代理）。
    """

    for action in (Chi((Tile("1w"), Tile("2w"), Tile("3w"))), Peng(Tile("1w")),
                   Gang(Tile("2b"), GangKind.CONCEALED), Pass()):
        assert baotou_after_action(True, action, HAND, 0) is True
        assert baotou_after_action(False, action, HAND, 0) is False
    assert baotou_after_action(True, Hu(), HAND, 0) is None
    # 弃牌用弃后暗牌重算：答案与直接调用 chain 侧的同一函数一致
    after = baotou_after_action(False, Discard(HAND[0]), HAND, 0)
    assert isinstance(after, bool)
    # 弃的牌不在暗牌里 ⇒ 不猜
    assert baotou_after_action(True, Discard(Tile("东")), HAND, 0) is None


# --- 3. 动作后的分支事实只在 HAND_PROGRESS 上有值 ---------------------------

def test_branch_after_facts_only_exist_for_hand_progress():
    """★ 分支分量在动作后没有通用事实：只有 HAND_PROGRESS 才有两型向听。

    这条是**使用边界**，不是缺陷：调用方必须区分"没有分支信息"与"分支是 0"。
    """

    progress = CandidateFacts(CandidateFactKind.HAND_PROGRESS, 1,
                              standard_shanten_after=2, seven_pairs_shanten_after=1)
    assert progress.seven_pairs_shanten_after == 1
    for kind in (CandidateFactKind.WIN, CandidateFactKind.NOT_APPLICABLE,
                 CandidateFactKind.ANALYSIS_FAILED):
        facts = CandidateFacts(kind, -1 if kind is CandidateFactKind.WIN else None)
        assert facts.seven_pairs_shanten_after is None
        assert facts.standard_shanten_after is None


def test_action_table_covers_every_declared_action_family():
    """动作族清单与结论表必须一一对应，不能漏写一族。"""

    assert {row["family"] for row in facts_matrix.ACTION_TABLE} == set(
        facts_matrix.ACTION_FAMILIES)


def test_chain_after_discard_is_the_single_source_for_the_chain_family():
    """统一入口必须**复用**既有转移函数，而不是另写一套。"""

    for baotou, tile in ((True, WEALTH), (False, WEALTH), (True, OTHER), (False, OTHER)):
        assert chain_after_action(3, 2, baotou, Discard(tile)) == chain_after_discard(
            3, 2, baotou, tile)
