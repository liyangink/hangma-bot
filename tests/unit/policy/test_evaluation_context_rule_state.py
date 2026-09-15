"""S1c 事实接线：EvaluationContext 的三个规则状态字段（2026-09-15）。

背景：官方总番 = 1 x 分支因子 x 2^动作链次数 x（4 白板 x2）x（爆头 x2）
（doc/references/official-guide-v34-content.txt 第 29 行）。链与爆头都直接乘 2 的幂，
是"状态势"必须包含的状态量；漏掉它们，potential-based 塑形（Ng 1999 Thm 1）的
充分条件失效。因此把 chain_count / baotou / wealth_count 接进评分上下文。

本文件守住三件事：
  A 接线证明：rule_state 的值确实到达评分上下文（不是"寄存器上写了但没接线"）；
  B 口径唯一：wealth_count 与 combined_codes x wealth_code 的机械计数同式，
    包含官方形态（my_hand 已含刚摸牌）去重后的口径，不存在第二套语义；
  C 行为中性：三个字段改回默认值后，V1 与 V2 的评分结果逐字节不变
    （守住"新增字段不改变旧策略实现"这一冻结契约的实质）。
"""

import asyncio
from dataclasses import replace

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import RulePublicState
from hangma_bot.policy.evaluation_v1 import build_context
from hangma_bot.policy.evaluation_v1 import score_candidates as score_v1
from hangma_bot.policy.evaluation_v2 import score_candidates as score_v2
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

from .support import WEALTH_CODE, make_observation, rules_from_engine

NUMBERS = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w"]

# 13 张：9 张序数牌 + 东东南白；配一张摸牌即 14 张。
HAND = NUMBERS + ["东", "东", "南", "白"]


async def _no_deadline() -> None:
    """评分只需一个可等待的截止检查；本测试不模拟超时。"""

    return None


def _obs(hand, *, drawn=None, baotou=False, chain_count=0, catch_play=False,
         chain_piao=None):
    """构造观察；规则状态显式给值，其余沿用 support 的安全默认。"""

    return make_observation(
        my_hand=tuple(Tile(code) for code in hand),
        drawn_tile=Tile(drawn) if drawn else None,
        chain_piao=chain_piao,
        rule_state=RulePublicState(
            wealth_god=Tile(WEALTH_CODE),
            baotou=baotou,
            chain_count=chain_count,
            catch_play=catch_play,
        ),
    )


# --- A 接线证明 ---------------------------------------------------------

def test_rule_state_reaches_scoring_context() -> None:
    """chain_count / baotou 必须原样到达上下文（此前二者在 policy 内零出现）。"""

    ctx = build_context(_obs(HAND, drawn=WEALTH_CODE, baotou=True, chain_count=3))
    assert ctx.chain_count == 3
    assert ctx.baotou is True


def test_chain_piao_is_passed_through_including_unknown() -> None:
    """chain.piao 原样透传；**依据不足时为空，不等于零**（术语表口径）。"""

    unknown = build_context(_obs(HAND, drawn=WEALTH_CODE, chain_count=3))
    assert unknown.chain_piao is None

    known = build_context(_obs(HAND, drawn=WEALTH_CODE, chain_count=3, chain_piao=2))
    assert known.chain_piao == 2


def test_default_rule_state_yields_neutral_values() -> None:
    """规则状态为默认时，三个新字段必须是中性值，而不是未初始化。"""

    ctx = build_context(_obs(HAND, drawn=WEALTH_CODE))
    assert ctx.chain_count == 0
    assert ctx.baotou is False
    assert ctx.wealth_count == 2  # 手牌 1 张白 + 刚摸 1 张白


# --- B 口径唯一 ---------------------------------------------------------

def test_wealth_count_is_mechanical_count_of_combined_codes() -> None:
    """wealth_count 必须等于 combined_codes 中财神码的计数（与 _wealth_after 同式）。"""

    ctx = build_context(_obs(NUMBERS + ["东", "东", WEALTH_CODE, WEALTH_CODE]))
    assert ctx.wealth_count == 2
    assert ctx.wealth_count == sum(
        1 for code in ctx.combined_codes if code == ctx.wealth_code)


def test_wealth_count_counts_drawn_wealth_once_in_official_form() -> None:
    """官方形态（my_hand 已含刚摸牌）与契约形态给出同一个 wealth_count。"""

    contract = build_context(_obs(HAND, drawn=WEALTH_CODE))
    official = build_context(_obs(HAND + [WEALTH_CODE], drawn=WEALTH_CODE))
    assert contract.wealth_count == official.wealth_count == 2  # 手牌 1 + 摸 1，无幻影
    assert official.combined_codes == contract.combined_codes


# --- C 行为中性 ---------------------------------------------------------

def _neutral(ctx):
    """把三个新字段强制改回默认值，其余字段原样保留。"""

    return replace(ctx, chain_count=0, baotou=False, wealth_count=0, chain_piao=None)


def test_neutral_context_differs_only_in_the_new_fields() -> None:
    """先证明这条中性化确实改变了新字段，C 组测试才有意义。"""

    ctx = build_context(_obs(HAND, drawn=WEALTH_CODE, baotou=True, chain_count=3))
    neutral = _neutral(ctx)
    assert ctx != neutral
    assert (ctx.combined_codes, ctx.wealth_code, ctx.safe_codes, ctx.my_seat) == (
        neutral.combined_codes, neutral.wealth_code, neutral.safe_codes, neutral.my_seat)


def test_v1_scoring_ignores_the_new_fields() -> None:
    """V1 评分不读新字段：中性化上下文后，分项与总分逐字节不变。"""

    obs = _obs(HAND, drawn=WEALTH_CODE, baotou=True, chain_count=3)
    candidates = rules_from_engine(obs).legal_candidates
    assert candidates  # 真实规则必须给出候选，否则本测试无意义

    ctx = build_context(obs)
    real = asyncio.run(score_v1(candidates, ctx, DEFAULT_WEIGHTS_V1, _no_deadline))
    neutral = asyncio.run(
        score_v1(candidates, _neutral(ctx), DEFAULT_WEIGHTS_V1, _no_deadline))
    assert real == neutral
    assert [item.parts for item in real] == [item.parts for item in neutral]


def test_v2_scoring_ignores_the_new_fields() -> None:
    """V2（含过牌等待分项）同样不读新字段。"""

    obs = _obs(HAND, drawn=WEALTH_CODE, baotou=True, chain_count=3)
    candidates = rules_from_engine(obs).legal_candidates

    ctx = build_context(obs)
    real = asyncio.run(score_v2(candidates, ctx, DEFAULT_WEIGHTS_V1, _no_deadline))
    neutral = asyncio.run(
        score_v2(candidates, _neutral(ctx), DEFAULT_WEIGHTS_V1, _no_deadline))
    assert real == neutral
