"""价值族④：**期望实际积分**（概率代理 × 番值 × 庄闲结算）—— 3.6c 规则感知评分器。

## 这是什么（与既有三族的关系）

前三族是**结构势差**：四分量基线（four_component_path_value）把官方番型公式的四个
乘子在 log2 下写成可加状态势，按 Φ(s′) − Φ(s) 计分。本模块是**第四个独立候选**，
按 PHASE3-RULE-AWARE-EVALUATION §2.1 明确允许的第三种形态实现：
**明确声明的直接动作评分**，而不是势差。

原文（§2.1）：「单一同权势差保留作基线，允许非线性势、分量交互或**明确声明的直接动作评分**；
各自验证幅度、适用域和运行成本，不能强迫所有候选满足不适用的可加性合同。」

**聚合口径（本候选的声明）**：把「四族各自加概率×倍率」改成**单一路径的期望值**
Q(a) = Σ_o P(o | I, a, π) × ΔScore(o) 的一个**下界代理**：

    收益侧  P_self(a) × Fan_lb(a) × gain_per_fan(我的支付角色)        单位：积分
    代价侧  P_opp(a)  × opp_fan_proxy × pay_per_fan(对手的支付角色)    单位：积分
    Φ(a)    = points_per_score ×（收益侧 − 代价侧）                    单位：评分点

**为什么不是把四族「概率 × 倍率」直接相加**：四族在规则上**重叠**（同一手牌可以同时
是七对 / 有链 / 四白 / 爆头），相加会把同一份总番算多次。本候选改为**乘性**：
总番 = 分支因子 × 2^链 × 四白 × 爆头，因此取各因子的**期望**再相乘，不做跨族相加。
两个指示量乘子用恒等式 E[2^I] = 1 + P(I)（Bernoulli 精确，不是近似）线性化；
分支与链是**已成立的状态事实**（不是未来事件），按其确定值进入。

## 量纲纪律（总番 / 实际积分 / 评分点分开声明）

| 量 | 单位 | 来源 |
| --- | --- | --- |
| 分支因子、2^链、四白、爆头 | **倍率**（无量纲，相对 1 番基数） | 【官方】指南 v34 §1.2—1.4（doc/references/official-guide-v34-content.txt） |
| Fan_lb(a) | **倍率**（= 期望总番代理，且是**下界**，见下） | 本模块由上面四个因子相乘 |
| gain_per_fan / pay_per_fan | **积分 / 倍率**（每 1 番的总积分增量） | hangma.settlement:settle_scores（**唯一规则来源**，本模块不重写结算） |
| P_self / P_opp | **概率代理**（无量纲 0—1，**不是**已校准概率） | 本模块的确定性代理，见「代理声明」 |
| Φ(a) | **评分点** | points_per_score（评分点/积分）× 上面的积分期望 |

**禁止把本候选的输出写成"真实期望积分"**：P 是未校准代理，Fan_lb 是下界。
它们只叫**评分点**（PLAN-REVISION §1.1、README §17.2 口径 2）。

## 四个分量补齐了什么（3.6c 要求）

| 缺口（PHASE3 §2 表格） | 本模块的补齐 | 三态 |
| --- | --- | --- |
| 「尚未形成但值得保留」的路径进展 | 七对距离、四白所需进张、链的升级入口都进 Fan_lb 的**期望**，不是只按当前真假 | 已证不可达 / 可达但兑现未知 / 尚未分析，逐项报告 |
| 同张牌竞争、开门排除七对、财飘/杠/爆头联动 | 乘性结构 + meld_count_of 判定七对关闭（【官方】：七对禁副露）；四白按「手留白 + 链内飘出 == 4」的**等值条件**（不写成"白越多越好"） | 关闭为**规则已证**，不是未知 |
| 「一次摸牌范围内完整」当成"全部路线完整" | 用**剩余巡数**（牌墙余量/4）+ 向听距离折算兑现机会，不是只看下一摸 | 墙余量未知 ⇒ **不评分**（不填零、不假设） |
| 只看"自己胡了能拿多少" | 显式**代价项**：P_opp × opp_fan_proxy × pay_per_fan 表示「等待/喂牌造成他家先胡时的支付」；P_self 的差额即**少胡机会** | 对手成胡份额用声明先验，见「代理声明」 |
| 「局面 → 用哪个分量」没有选择规则 | SCENARIO_CLASS_BINDINGS + activated_classes()：按 3.6a 的**规则状态谓词**决定哪些分量参与本窗口 | 每个类给「适用 / 不适用 / 不可判定」，见 Appraisal.activated |
| 庄闲 / 支付倍率不进评分层 | settlement_factors() 直接调 settle_scores；**庄闲生效性门禁**见下 | 支付角色两类**互斥且穷尽** |

## 庄闲生效性门禁（结构性空操作教训）

历史事实（evidence/3.0-scenario-classes/README.md §已知缺口 3）：
V1/V2 权重 11 项**没有庄闲字段**，全仓唯一庄闲建模在 hu_upgrade.py，
且「庄闲分离定价差分 **0 / 10,769 窗口**」被判定为**结构性空操作**——因为上游
_next_draw_value 的「能证明弃牌后任意下一摸必翻倍」先过滤掉了几乎所有窗口
（见 policy/hu_upgrade_calibration.py 的保留结论）。**顺序反了：风险表只在
可证明性之后的比较式里起作用，调表永远是空操作。**

因此本候选的庄闲因子**不放在"可证明性"之后**，而是与其它候选直接相加比较：

- use_dealer_parity=1（默认）：settle_scores 的真实系数（本人庄 24 / 本人闲 10；
  付方：庄家胡 8、闲家胡 1（本人非庄）或 8（本人庄））。
- use_dealer_parity=0：**对照变体**，把两张系数表都替换成 1/1（与庄闲无关的中立口径）。
  两者**只差这一个参数**（同权重、同其它参数），因此两者在冻结面板上首选动作的差异
  **只能**来自庄闲依赖本身。

**门禁判据**（实跑见 evidence/3.6c-scorer/probe_dealer_effectiveness.py）：
① use_dealer_parity=1 与 =0 在冻结面板上的**首选动作差异数 > 0**；
② **负例**：把庄闲因子换成**与庄闲无关的常量**的变体，同一实验必须得到 **差异数 = 0**
   （即门禁必须对它 FAIL）。① 通过而 ② 不成立 ⇒ 测的不是庄闲依赖。
不得靠改 loss_absolute/基础权重制造差异：探针**强制断言**两个变体的
weights_effective 完全相同，只有 adj.use_dealer_parity 不同。

## 势差合同的重新声明（PLAN-REVISION §1.2）

**本候选不是势差，也不声明势差合同。** 原合同（Φ(s)=Σg_i(s)φ_i(s)、完整差值、
域内可加性与环判据、bound ≥ Φ_max − Φ_min）**只在四分量基线上成立**，本模块不引用它，
也不借用它的"结构检查通过"结论。本候选声明的替代合同：

1. **声明域**：Fan_lb ∈ [1, fan_cap]、P ∈ [0,1]、墙余量与牌效事实齐备、
   动作类别在 scope 内。任一条不满足 ⇒ **该动作不评分**（返回 0 并记录原因），
   不夹取、不用 0 或 False 冒充缺失事实。
2. **幅度界**：bound = points_per_score × (fan_cap × gain_max + opp_fan_cap × pay_max)，
   由声明域**推导**（不是手写常量）；改任一参数，bound 自动跟随，并进候选身份。
   gain_max = 24、pay_max = 8 来自 settle_scores（庄 24 / 闲 10；庄家胡付 8 / 闲家胡付 1）。
3. **动作标签无关性**：取值只依赖「动作后的规则事实 + 窗口上下文」，不按动作类别分档；
   吃/碰是通过"永久关闭七对路径（规则已证）"间接影响取值，不是标签加分。
4. **不覆盖立即胡优先级**：合法胡恒为 priority = 0（evaluation_v1._priority），
   评分不参与其排序；bound 只用于适配器的越界审计，**没有任何路径能把胡降层**
   （回归 test_hu_priority_is_independent_of_weights_and_facts）。
5. **可加性/环判据不适用**：直接动作评分不做 F(A,B)+F(B,C)=F(A,C) 的断言；
   本模块**不声称**最优策略不变，也不声称安全提升。

## 代理声明（全部是【工程假设】，不是校准概率）

- P_self = [1 − (1 − p)^n] × decay^d，其中
  p = min(1, U / wall)（U = 规则事实给出的有效牌剩余估计之和，wall = 牌墙余量），
  n = max(1, wall // 4)（**剩余巡数**代理），d = 规则给出的动作后向听距离，
  decay = 每多一步向听的额外折减。**它不是概率**：真实 P(o|I,a,π) 依赖他家策略与隐藏牌墙。
- P_four_white = 1（已成立）/ 0（需要的白板多于可得）/ 否则 [1−(1−p)^n]/k
  （k = 还需白板张数，p = 可达白板数 / wall）。链内飘出不可归因时取**保守下界**
  （需要的张数取下界口径 ⇒ 概率偏小），并单独计数，**不用 0 冒充未知**。
- P_opp = 1 − (1 − q)^n，q = opp_draw_rate × (1 + exposure(a))；
  exposure(a) = 本动作落入**已知副露对手**邻域的加权计数，
  权重取 pay_per_fan（庄家倍率 8 / 闲家 1，来自 settle_scores）。
  对手成胡份额用**声明先验**（未被喂到的部分按 0 计，属**下界**口径，单独标记）。
- opp_fan_proxy：他家成胡番值的声明代理（默认 2 番），因为决策面板看不到未来成胡。

## 三态与「未知不填零」

每个分量在**每个状态**上取三态之一：REACHED（规则已确认成立）、IMPOSSIBLE
（规则已证不可达：七对被副露永久关闭、需要张数 > 物理可得）、UNKNOWN（尚未分析：
未来摸牌、未来成胡、他家手牌）。UNKNOWN 的处理：

- **不进"零值"**：不写 False、不写 0；
- 乘性结构里以**下界因子 1** 出现（E[2^I] = 1 + P ≥ 1），故 Fan_lb 是期望总番的
  **下界**，不是点估计；被略去的因子在 Appraisal.unappraised 里逐条登记；
- 影响**兑现机会**的未知（墙余量缺失、牌效事实缺失、规则门控使成胡条件未建模）
  直接让该动作**不评分**并记录原因。

## 纯度

纯函数：只读 EvaluationContext、规则给出的候选与不可变参数；不读时间、随机、
文件、网络，不做搜索、不重算向听（只消费 CandidateFacts）。规则一律调用 hangma
（settlement / progression / special_rules），**policy 不复制规则**。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from hangma_bot.hangma.interface import CandidateFactKind, RuleCandidate
from hangma_bot.hangma.progression import chain_after_action, wealth_after_action
from hangma_bot.hangma.settlement import settle_scores
from hangma_bot.kernel.actions import Discard, Hu

from ..evaluation_v1 import EvaluationContext, _near_meld
from ..heuristic_adapter import AdjustmentSpec, HeuristicAdjustment, action_kind
from .four_component_path_value import (
    BRANCH_LOG2_CHIITOI,
    MAX_CHAIN_COUNT,
    WEALTH_TOTAL,
    action_state,
    context_state,
    known_piao,
    locked_luxury_groups,
    meld_count_of,
)

EXPECTED_SCORE_VERSION = "expected-score-path-value-v1"

# --- 单位锚点（全部进候选身份；都是工程初始选择，未做参数搜索）-----------------

#: 评分点 / 积分。取 2.0 使典型窗口的 |Δ| 与 V1 的 feed_risk=6 / safe_tile_bonus=3 同量级。
DEFAULT_POINTS_PER_SCORE = 2.0
#: 声明域上界（倍率）：Fan_lb > fan_cap 的动作按**域外**处理（不评分 + 记录原因）。
DEFAULT_FAN_CAP = 64.0
#: 他家成胡番值的声明代理（番），面板看不到未来成胡。
DEFAULT_OPP_FAN_PROXY = 2
#: 单个对手每巡成胡率的声明基准（概率代理，无量纲）。
DEFAULT_OPP_DRAW_RATE = 0.06
#: 向听每多一步对兑现机会的额外折减（无量纲，0—1）。
DEFAULT_DECAY_PER_SHANTEN = 0.35
#: 结算单位：底分。settle_scores 要求正整数；本项只声明**单位**，整体线性缩放不改变排序。
SETTLEMENT_BASE_SCORE = 1

#: 牌墙余量 → 剩余巡数 的换算（4 人各摸一次为一巡）。**工程假设**。
TILES_PER_ROUND = 4

#: 作用面：全部动作类别；是否真的取值由「动作后事实 + 声明域」决定，不按标签分档。
ALL_KINDS: Tuple[str, ...] = ("chi", "peng", "gang", "discard", "pass", "hu")

#: 三态（术语表：空与 0 必须区分）。
REACHED = "reached"
IMPOSSIBLE = "impossible"
UNKNOWN = "unknown"


# --- 3.6a 场景类绑定：这一版"局面 → 分量"的机器可判映射 -----------------------


@dataclass(frozen=True)
class ClassBinding:
    """一个 3.6a 场景类 → 本候选的某个分量/因子的绑定。

    class_id / predicate_text 逐字对应 3.6a 清单（evidence/3.0-scenario-classes/CLASSES.md），
    因此"声明覆盖了哪些类"可以被 sitin_scenario_classes.py 的记号扫描复核。
    component：本候选内部的分量名（进证据与审计）。
    """

    class_id: str
    predicate_text: str
    component: str


SCENARIO_CLASS_BINDINGS: Tuple[ClassBinding, ...] = (
    ClassBinding("payrole.self_dealer", "ctx.my_seat == ctx.dealer_seat", "pay_multiplier"),
    ClassBinding("payrole.self_nondealer", "ctx.my_seat != ctx.dealer_seat", "pay_multiplier"),
    ClassBinding("branch.chiitoi_live", "meld_count_of(combined_codes)==0", "branch_path"),
    ClassBinding("branch.luxury_locked",
                 "meld_count_of(...)==0 且 locked_luxury_groups(combined_codes, wealth_code)>=1",
                 "branch_path"),
    ClassBinding("chain.open", "ctx.chain_count >= 1", "chain_multiplier"),
    ClassBinding("chain.gang_step", "窗口内存在 gang 候选（暗杠/明杠/补杠）", "chain_multiplier"),
    ClassBinding("chain.break_discard",
                 "ctx.chain_count >= 1 且 存在「非飘」discard 候选", "chain_multiplier"),
    ClassBinding("chain.piao_discard",
                 "ctx.baotou 为真 且 窗口存在「打出财神」discard 候选", "chain_multiplier"),
    ClassBinding("four_white.at_four",
                 "four_white_indicator(wealth_count, known_piao(...)) is True",
                 "four_white_multiplier"),
    ClassBinding("four_white.unknown_piao",
                 "known_piao(wealth_count, ctx.chain_piao, ctx.chain_count) is None",
                 "four_white_multiplier"),
    ClassBinding("baotou.active", "ctx.baotou 为真", "baotou_multiplier"),
    ClassBinding("baotou.discard_recheck",
                 "ctx.baotou 为真 且 存在 discard 候选", "baotou_multiplier"),
    ClassBinding("meld.waiting_facts_available",
                 "natural_draw_value(candidates) is not None", "realisation_chance"),
    ClassBinding("gate.wall_end_gang_ban",
                 "已接线可判定：ctx.remaining_tile_count <= WALL_RESERVE_TILES；未知/未接线→None",
                 "realisation_chance"),
    ClassBinding("gate.you_cai_bi_kao",
                 "已接线可判定：ctx.you_cai_bi_kao is True；未接线→None", "realisation_chance"),
    ClassBinding("gate.catch_play_owner",
                 "已接线可判定：不在圈内→False；在圈内 ctx.catch_play_owner_seat == ctx.my_seat；未知→None",
                 "realisation_chance"),
)


@dataclass(frozen=True)
class ExpectedScoreParams:
    """不可变参数实例；**全部字段进候选身份**（含推导出的 bound）。

    points_per_score：单位 **评分点 / 积分**（把积分期望换算成评分尺度）。
    fan_cap：声明域上界（倍率）；Fan_lb > fan_cap 的动作不评分。
    opp_fan_proxy：他家成胡番值代理（番，整数，进 settle_scores）。
    opp_draw_rate：单个对手每巡成胡率代理（无量纲）。
    decay_per_shanten：向听每多一步对兑现机会的**额外**折减（无量纲，0—1）。
    use_dealer_parity：1 = 用 settle_scores 的真实庄闲系数；0 = **对照变体**，
        两张系数表都替换成 1/1（见模块 docstring 的生效性门禁）。
    use_opp_cost / use_path_progress：消融开关（0/1），各自是独立候选身份。
    bound：**推导属性**，见 derived_bound。
    """

    points_per_score: float = DEFAULT_POINTS_PER_SCORE
    fan_cap: float = DEFAULT_FAN_CAP
    opp_fan_proxy: int = DEFAULT_OPP_FAN_PROXY
    opp_draw_rate: float = DEFAULT_OPP_DRAW_RATE
    decay_per_shanten: float = DEFAULT_DECAY_PER_SHANTEN
    use_dealer_parity: float = 1.0
    use_opp_cost: float = 1.0
    use_path_progress: float = 1.0
    scope: Tuple[str, ...] = ALL_KINDS

    def __post_init__(self) -> None:
        for field_name in ("points_per_score", "fan_cap", "opp_draw_rate",
                           "decay_per_shanten", "use_dealer_parity",
                           "use_opp_cost", "use_path_progress"):
            value = getattr(self, field_name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(
                    "ExpectedScoreParams.{0} 必须是有限数值".format(field_name))
        if type(self.opp_fan_proxy) is not int:
            raise ValueError("ExpectedScoreParams.opp_fan_proxy 必须是整数（结算口径）")
        if self.points_per_score < 0:
            raise ValueError("ExpectedScoreParams.points_per_score 必须非负")
        if self.fan_cap <= 0:
            raise ValueError("ExpectedScoreParams.fan_cap 必须为正")
        if self.opp_fan_proxy <= 0:
            raise ValueError("ExpectedScoreParams.opp_fan_proxy 必须为正整数")
        if not 0.0 <= self.opp_draw_rate <= 1.0:
            raise ValueError("ExpectedScoreParams.opp_draw_rate 必须落在 [0,1]")
        if not 0.0 <= self.decay_per_shanten <= 1.0:
            raise ValueError("ExpectedScoreParams.decay_per_shanten 必须落在 [0,1]")
        for field_name in ("use_dealer_parity", "use_opp_cost", "use_path_progress"):
            if getattr(self, field_name) not in (0.0, 1.0):
                raise ValueError(
                    "ExpectedScoreParams.{0} 只能是 0 或 1".format(field_name))

    @property
    def gain_per_fan_max(self) -> float:
        """声明域上「每番的总积分增量」上界（本人胡）：庄家 24 = 3 × 8。"""

        return float(max(settle_scores(1, SETTLEMENT_BASE_SCORE, seat, seat)[seat]
                         for seat in range(4)))

    @property
    def pay_per_fan_max(self) -> float:
        """声明域上「每番的支付」上界（他家胡，本人付）：付方倍率 8。"""

        return float(max(-settle_scores(1, SETTLEMENT_BASE_SCORE, winner_seat, dealer_seat)[payer]
                         for winner_seat in range(4)
                         for dealer_seat in range(4)
                         for payer in range(4)
                         if payer != winner_seat))

    @property
    def derived_bound(self) -> float:
        """幅度界 = pps × (fan_cap × 收益上界 + opp_fan_proxy × 支付上界)。"""

        return self.points_per_score * (
            self.fan_cap * self.gain_per_fan_max
            + float(self.opp_fan_proxy) * self.pay_per_fan_max)

    def to_json(self) -> str:
        """稳定序列化；**进候选身份**，使产物可复现到具体参数与推导出的 bound。"""

        return (
            "pps={0},fan_cap={1},opp_fan={2},opp_rate={3},decay={4},"
            "parity={5},opp_cost={6},path_progress={7},bound={8},scope={9}".format(
                self.points_per_score, self.fan_cap, self.opp_fan_proxy,
                self.opp_draw_rate, self.decay_per_shanten,
                int(self.use_dealer_parity), int(self.use_opp_cost),
                int(self.use_path_progress), self.derived_bound,
                "+".join(self.scope)))


# --- 结算系数：**唯一规则来源**是 settle_scores -------------------------------


def blind_settlement_factors() -> Tuple[float, float]:
    """门禁对照臂用的**与庄闲无关的常量** (gain_per_fan, pay_per_fan)。

    在"庄闲/胡家均匀先验"下对 settle_scores 取整体平均：保留真实结算的**量级**、
    去掉**座位依赖**。全仓唯一的庄闲语义仍在 settle_scores；本函数只做平均，
    不引入第二套规则口径（结算规则变化时常量会自动跟随）。
    """

    seats = range(4)
    gain = sum(settle_scores(1, SETTLEMENT_BASE_SCORE, me, dealer)[me]
               for me in seats for dealer in seats) / float(len(seats) ** 2)
    pairs = [(winner, dealer, payer) for winner in seats for dealer in seats
             for payer in seats if payer != winner]
    pay = sum(-settle_scores(1, SETTLEMENT_BASE_SCORE, winner, dealer)[payer]
              for winner, dealer, payer in pairs) / float(len(pairs))
    return float(gain), float(pay)


def settlement_factors(ctx: EvaluationContext, params: ExpectedScoreParams
                       ) -> Tuple[float, Tuple[float, ...]]:
    """返回 (gain_per_fan, pay_per_fan[对手座位])，单位 **积分 / 倍率**。

    gain_per_fan：本人以 1 番自摸胡时的**本人**积分增量（庄 24 / 闲 10）。
    pay_per_fan[j]：对手 j 以 1 番自摸胡时**本人**支付的绝对值
    （本人闲：庄家胡付 8、闲家胡付 1；本人庄：任意闲家胡各付 8）。
    两者都直接来自 hangma.settlement.settle_scores（唯一规则来源），本模块不重写结算。

    use_dealer_parity=0 时把两张表都替换成**与庄闲无关的常量**（blind_settlement_factors）：
    这是**生效性门禁的对照臂**，不是另一套规则口径。常量由 settle_scores 在
    "庄闲均匀先验"下的**整体平均幅度**导出，因此对照臂保留本项的**量级**、
    只去掉**座位依赖**——否则"差异 > 0"可能来自"加了一项这么大的分"而不是庄闲。
    """

    if params.use_dealer_parity == 0.0:
        gain_const, pay_const = blind_settlement_factors()
        return gain_const, tuple(0.0 if seat == ctx.my_seat else pay_const
                                 for seat in range(4))
    gain = float(settle_scores(
        1, SETTLEMENT_BASE_SCORE, ctx.my_seat, ctx.dealer_seat)[ctx.my_seat])
    pay = tuple(
        float(-settle_scores(
            1, SETTLEMENT_BASE_SCORE, seat, ctx.dealer_seat)[ctx.my_seat])
        if seat != ctx.my_seat else 0.0
        for seat in range(4))
    return gain, pay


# --- 动作后规则状态（复用规则单一来源，不复制转移函数）------------------------


@dataclass(frozen=True)
class ActionState:
    """动作后的**已知**规则状态 + 三态路径取值。

    branch_state / chiitoi_alive 是**规则已证**的路径状态（不是估计）：
    有副露 ⇒ 七对路径被官方永久关闭（IMPOSSIBLE），不是"未知"。
    """

    branch_log2: Optional[float]
    chiitoi_alive: Optional[bool]
    locked_groups: Optional[int]
    chain_count: Optional[int]
    wealth_after: Optional[int]
    piao_after: Optional[int]
    four_white: Optional[bool]
    baotou: Optional[bool]


def _four_white_state(ctx: EvaluationContext, action, chain_after: Optional[int],
                      piao_before: Optional[int]
                      ) -> Tuple[Optional[int], Optional[int], Optional[bool]]:
    """动作后 (手留财神, 链内飘出, 四白指示)；飘出不可归因时返回 None（未知不填零）。"""

    wealth_after = wealth_after_action(ctx.wealth_count, action)
    _, piao_raw = chain_after_action(
        ctx.chain_count, piao_before, ctx.baotou, action)
    piao_after = known_piao(
        wealth_after, piao_raw, chain_after if chain_after is not None else 0)
    if piao_after is None:
        return wealth_after, None, None
    if wealth_after + piao_after == WEALTH_TOTAL:
        return wealth_after, piao_after, True
    return wealth_after, piao_after, False


def action_state_after(candidate: RuleCandidate, ctx: EvaluationContext
                       ) -> Optional[ActionState]:
    """动作后的已知规则状态；无法构造时返回 None（不猜）。

    复用 four_component_path_value.context_state / action_state 的**同一套规则调用**
    （progression.chain_after_action / wealth_after_action / baotou_after_action），
    保证与结构基线不会出现第二套规则转移。
    """

    action = candidate.action
    if isinstance(action, Hu):
        return None                        # 终局：与基线同口径，不参与评分
    before = context_state(ctx)
    after = action_state(candidate, ctx, before)
    if after is None:
        return None
    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None                        # 分支路径不可判定：不猜（D4 同口径）
    piao_before = known_piao(ctx.wealth_count, ctx.chain_piao, ctx.chain_count)
    wealth_after, piao_after, four_white = _four_white_state(
        ctx, action, after.chain_count, piao_before)
    if melds == 0:
        groups = locked_luxury_groups(ctx.combined_codes, ctx.wealth_code)
        if isinstance(action, Discard) and ctx.combined_codes.count(action.tile.code) == WEALTH_TOTAL \
                and action.tile.code != ctx.wealth_code:
            groups -= 1                    # 打掉手里恰好 4 张的自然牌 ⇒ 少一个已锁定豪华组
        chiitoi_alive, locked = True, max(0, groups)
    else:
        chiitoi_alive, locked = False, 0
    return ActionState(
        branch_log2=after.branch_log2,
        chiitoi_alive=chiitoi_alive,
        locked_groups=locked,
        chain_count=after.chain_count,
        wealth_after=wealth_after,
        piao_after=piao_after,
        four_white=four_white,
        baotou=after.baotou,
    )


# --- 兑现机会与路径可达代理（全部是声明代理，不是概率）------------------------


def remaining_rounds(wall: Optional[int]) -> Optional[int]:
    """剩余巡数代理 = max(1, wall // 4)；墙余量未知返回 None（不假设）。"""

    if wall is None or wall < 0:
        return None
    return max(1, wall // TILES_PER_ROUND)


def hit_once(rate: float, rounds: int) -> float:
    """1 − (1 − rate)^rounds：rounds 次机会里至少命中一次的概率代理。"""

    if rate <= 0.0:
        return 0.0
    if rate >= 1.0:
        return 1.0
    return 1.0 - (1.0 - rate) ** rounds


def path_reach(rate: float, rounds: int, steps: int) -> float:
    """路径兑现代理：至少命中一次的概率按**步数**摊分（steps ≥ 1）。

    语义：「每次摸牌以 rate 命中下一步所需牌；走到成胡还要 steps 步」。
    **不是概率**（他家策略与隐藏牌墙未建模），只用于同窗口内候选之间的比较。
    """

    return hit_once(rate, rounds) / float(max(1, steps))


def facts_useful_count(facts) -> Tuple[Optional[int], Optional[int]]:
    """返回 (综合有效牌剩余估计之和, 标准型向听)；缺字段或事实非 COMPLETE 返回 (None, None)。"""

    if facts is None or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS:
        return None, None
    if facts.completeness.name != "COMPLETE":
        return None, None
    total = sum(item.remaining_estimate for item in facts.useful_tiles)
    shanten = facts.standard_shanten_after
    if shanten is None:
        shanten = facts.shanten_after
    return total, shanten


def realisation_chance(facts, wall: Optional[int], params: ExpectedScoreParams
                       ) -> Tuple[Optional[float], str]:
    """P_self：动作后「还能成胡」的兑现机会代理；不可判定时返回 (None, 原因)。

    未知一律**不评分**（返回 None），不假设、不填零：
    牌效事实缺失/未完成、牌墙余量未知都属此列。
    """

    total, shanten = facts_useful_count(facts)
    if total is None or shanten is None:
        return None, "牌效事实缺失或未完成：按未知处理，不推断向听或有效牌"
    rounds = remaining_rounds(wall)
    if rounds is None or wall is None or wall <= 0:
        return None, "牌墙余量未知：不假设巡数、不评分"
    rate = min(1.0, float(total) / float(wall))
    value = hit_once(rate, rounds) * (params.decay_per_shanten ** max(0, int(shanten)))
    return value, ""


def four_white_reach(state: ActionState, wall: Optional[int], ctx: EvaluationContext
                     ) -> Tuple[float, Optional[str]]:
    """P_four_white：手留白 + 链内飘出 == 4 的兑现代理（等值条件，不是"越多越好"）。

    返回 (概率代理, 保守口径说明)。四条分支：

    1. 已成立 ⇒ 1.0（规则已证）；
    2. 需要的白板数 > 物理可得 ⇒ 0.0（**规则已证不可达**，不是未知）；
    3. 链内飘出不可归因 ⇒ 需要的张数取下界口径（概率偏小）⇒ **保守下界**，并返回说明；
    4. 其余 ⇒ 至少命中一次的概率按还需张数摊分。
    """

    if state.four_white is True:
        return 1.0, None
    if state.wealth_after is None:
        return 1.0, "手留财神未知：四白期望因子按下界 1（不参与估值）"
    rounds = remaining_rounds(wall)
    if rounds is None or wall is None or wall <= 0:
        return 1.0, "牌墙余量未知：四白期望因子按下界 1（不参与估值）"
    held = state.wealth_after
    if state.four_white is None:
        # 飘出不可归因：需要的张数取下界口径（飘出按最大可能取值）⇒ 概率偏小 ⇒ 保守。
        chain_count = ctx.chain_count if ctx.chain_count is not None else 0
        piao_upper = max(0, min(chain_count, WEALTH_TOTAL - held)) if held < WEALTH_TOTAL else 0
        need = max(1, WEALTH_TOTAL - held - piao_upper)
        note = "链内飘出不可归因：四白可达概率按保守下界口径（需要张数取下界）"
    else:
        if state.piao_after is None:
            return 1.0, "链内飘出不可归因：四白期望因子按下界 1（不参与估值）"
        need = WEALTH_TOTAL - held - state.piao_after
        note = None
    if need <= 0:
        return 1.0, note                # 已成立（与 four_white is True 同义）
    available = max(0, WEALTH_TOTAL - held)   # 本人手上之外还能被摸到的白板上限
    if need > available:
        return 0.0, note                # 规则已证不可达：物理上不可能再凑够
    rate = min(1.0, float(need) / float(wall))
    return path_reach(rate, rounds, need), note


def chiitoi_reach(state: ActionState, facts, wall: Optional[int]
                  ) -> Tuple[float, str]:
    """P_chiitoi：七对（含豪华）路径的兑现代理，附三态标签。

    七对路径被副露**永久关闭**是【官方】事实 ⇒ 返回 0.0 + IMPOSSIBLE
    （**规则已证不可达**，不是未知）；事实不足 ⇒ 0.0 + UNKNOWN（尚未分析）。
    """

    if state.chiitoi_alive is False:
        return 0.0, IMPOSSIBLE
    rounds = remaining_rounds(wall)
    if rounds is None or wall is None or wall <= 0:
        return 0.0, UNKNOWN
    shanten = getattr(facts, "seven_pairs_shanten_after", None) if facts is not None else None
    tiles = getattr(facts, "seven_pairs_useful_tiles", None) if facts is not None else None
    if tiles is None:
        tiles = getattr(facts, "useful_tiles", ()) if facts is not None else ()
    if shanten is None:
        return 0.0, UNKNOWN
    total = sum(item.remaining_estimate for item in tiles)
    rate = min(1.0, float(total) / float(wall))
    return path_reach(rate, rounds, max(1, int(shanten) + 1)), REACHED


# --- 对手代价：支付他家自摸 ------------------------------------------------


@dataclass(frozen=True)
class Exposure:
    """本动作对**已知副露对手**的喂牌暴露（加权计数）与不可观测部分标记。"""

    units: float
    observed_seats: Tuple[int, ...]
    unknown_seats: Tuple[int, ...]
    note: Optional[str]


def exposure_units(candidate: RuleCandidate, ctx: EvaluationContext,
                   pay_per_fan: Tuple[float, ...]) -> Exposure:
    """弃牌落入已知副露对手邻域的加权计数；权重 = 该对手胡时**本人的每番支付**。

    EvaluationContext 只带**下家**与**庄家**的副露牌码（既有事实面），因此其余对手的
    邻域**不可观测**——它们进 unknown_seats 并单独标记，**不填零**。
    """

    action = candidate.action
    observed: Tuple[int, ...] = ()
    unknown: Tuple[int, ...] = ()
    units = 0.0
    note = None
    if isinstance(action, Discard):
        code = action.tile.code
        by_seat = {ctx.next_seat: ctx.next_seat_meld_codes,
                   ctx.dealer_seat: ctx.dealer_meld_codes}
        for seat in range(4):
            if seat == ctx.my_seat:
                continue
            codes = by_seat.get(seat)
            if codes is None:
                unknown += (seat,)
                continue
            observed += (seat,)
            if codes and _near_meld(codes, code):
                units += pay_per_fan[seat]
        if unknown:
            note = ("座位 {0} 的副露牌码不在评分上下文（只带下家与庄家）："
                    "该部分暴露未计入，属**下界**口径".format(list(unknown)))
    else:
        # 非弃牌动作不喂牌；但他家可能自行成胡，代价项仍按基准率计入。
        observed = tuple(seat for seat in range(4) if seat != ctx.my_seat)
    return Exposure(units, observed, unknown, note)


def opponent_cost(candidate: RuleCandidate, ctx: EvaluationContext, wall: Optional[int],
                  pay_per_fan: Tuple[float, ...], params: ExpectedScoreParams
                  ) -> Tuple[Optional[float], Optional[Exposure], str]:
    """代价项（积分）：P_opp × opp_fan_proxy × 平均每番支付；不可判定时返回原因。"""

    rounds = remaining_rounds(wall)
    if rounds is None:
        return None, None, "牌墙余量未知：不假设巡数、不评分"
    exposure = exposure_units(candidate, ctx, pay_per_fan)
    observed = [seat for seat in range(4) if seat != ctx.my_seat]
    if not observed:
        return None, exposure, "无对手座位：代价项不适用"
    average_pay = sum(pay_per_fan[seat] for seat in observed) / float(len(observed))
    q = params.opp_draw_rate * (1.0 + exposure.units)
    p_opp = hit_once(min(1.0, q), rounds)
    return p_opp * float(params.opp_fan_proxy) * average_pay, exposure, ""


# --- 汇总：一个动作的期望实际积分 --------------------------------------------


@dataclass(frozen=True)
class Appraisal:
    """一个动作的**期望实际积分**评比分解（全部字段都是代理量，见模块 docstring）。

    fan_lower_bound：期望总番的**下界**（倍率）。
    p_self：兑现机会代理（无量纲）。
    gain / cost / net：单位 **积分**。
    activated：本窗口激活的 3.6a 场景类（"局面 → 分量"选择规则的可审计输出）。
    unappraised：未参与估值的因子（"未知不填零"的登记处）。
    """

    fan_lower_bound: float
    p_self: float
    gain: float
    cost: Optional[float]
    net: float
    points: float
    activated: Tuple[str, ...]
    unappraised: Tuple[str, ...]
    notes: Tuple[str, ...]


def activated_classes(ctx: EvaluationContext, candidate: RuleCandidate,
                      state: ActionState, facts) -> Tuple[str, ...]:
    """"局面 → 分量"选择规则：按 3.6a 的规则状态谓词返回**本窗口激活的类**。

    谓词与 SCENARIO_CLASS_BINDINGS 一一对应，本函数是它的机器可判实现；
    没有激活的类不进任何分项——这就是"什么时候用哪个分量"的显式声明。
    """

    ids = ["payrole.self_dealer" if ctx.my_seat == ctx.dealer_seat
           else "payrole.self_nondealer"]
    if state.chiitoi_alive:
        ids.append("branch.chiitoi_live")
        if (state.locked_groups or 0) >= 1:
            ids.append("branch.luxury_locked")
    if ctx.chain_count >= 1:
        ids.append("chain.open")
        if action_kind(candidate.action_key) == "discard":
            if ctx.baotou and candidate.action.tile.code == ctx.wealth_code:
                ids.append("chain.piao_discard")
            else:
                ids.append("chain.break_discard")
    if action_kind(candidate.action_key) == "gang":
        ids.append("chain.gang_step")
    if state.four_white is True:
        ids.append("four_white.at_four")
    elif state.four_white is None:
        ids.append("four_white.unknown_piao")
    if ctx.baotou:
        ids.append("baotou.active")
        if action_kind(candidate.action_key) == "discard":
            ids.append("baotou.discard_recheck")
    if facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS:
        ids.append("meld.waiting_facts_available")
    if ctx.remaining_tile_count is not None:
        ids.append("gate.wall_end_gang_ban")
    if ctx.you_cai_bi_kao is not None:
        ids.append("gate.you_cai_bi_kao")
    if ctx.catch_play_owner_seat is not None or not ctx.catch_play:
        ids.append("gate.catch_play_owner")
    return tuple(ids)


def appraise(candidate: RuleCandidate, ctx: EvaluationContext,
             params: ExpectedScoreParams) -> Optional[Appraisal]:
    """对一个动作做期望实际积分评比；不在声明域内时返回 None。

    返回 None 的情形（**都是声明的"不评分"，不是零值**）：
    终局胡（本项不参与其排序）、动作后规则状态不可构造、牌效事实缺失、牌墙余量未知、
    链次数越出官方声明域、期望总番越出 fan_cap。
    """

    facts = candidate.facts
    state = action_state_after(candidate, ctx)
    if state is None:
        return None
    p_self, _ = realisation_chance(facts, ctx.remaining_tile_count, params)
    if p_self is None:
        return None

    unappraised = []
    notes = []
    # 1) 分支（七对 / 豪华）因子的期望：E[f] = 1 + (f_chiitoi − 1) × P_chiitoi
    chiitoi_factor = 1.0
    if params.use_path_progress and state.chiitoi_alive:
        p_chiitoi, chiitoi_state = chiitoi_reach(state, facts, ctx.remaining_tile_count)
        f_chiitoi = 2.0 ** (BRANCH_LOG2_CHIITOI + float(state.locked_groups or 0))
        chiitoi_factor = 1.0 + (f_chiitoi - 1.0) * p_chiitoi
        if chiitoi_state == UNKNOWN:
            unappraised.append("branch.chiitoi_reach=尚未分析（缺七对向听/进张事实）")
    # 2) 链：已成立的状态事实（不是未来事件）。
    # **两个端点都要在声明域内**（与基线 D1 同口径）：动作前的链次数与动作后的链次数
    # 任一越出官方 0—6 域 ⇒ 该动作不评分（不夹取、不惩罚）。
    if not 0 <= ctx.chain_count <= MAX_CHAIN_COUNT:
        return None
    if state.chain_count is None or not 0 <= state.chain_count <= MAX_CHAIN_COUNT:
        return None
    chain_factor = 2.0 ** state.chain_count
    # 3) 四白乘子：E[2^I] = 1 + P
    white_factor = 1.0
    if params.use_path_progress:
        p_white, white_note = four_white_reach(state, ctx.remaining_tile_count, ctx)
        white_factor = 1.0 + p_white
        if white_note:
            unappraised.append("four_white=" + white_note)
            notes.append(white_note)
    # 4) 爆头乘子：已成立 ⇒ ×2；未成立时未来可达**尚未分析**，按乘性下界 1 计并登记
    baotou_factor = 2.0 if state.baotou else 1.0
    if not state.baotou:
        unappraised.append("baotou=尚未分析（未来是否进入爆头无规则事实）")

    fan_lb = chiitoi_factor * chain_factor * white_factor * baotou_factor
    if not math.isfinite(fan_lb) or fan_lb > params.fan_cap:
        return None

    gain_per_fan, pay_per_fan = settlement_factors(ctx, params)
    gain = p_self * fan_lb * gain_per_fan
    cost: Optional[float] = None
    if params.use_opp_cost:
        cost, exposure, _ = opponent_cost(
            candidate, ctx, ctx.remaining_tile_count, pay_per_fan, params)
        if cost is None:
            return None
        if exposure is not None and exposure.note:
            notes.append(exposure.note)
    net = gain - (cost if cost is not None else 0.0)
    return Appraisal(
        fan_lower_bound=fan_lb,
        p_self=p_self,
        gain=gain,
        cost=cost,
        net=net,
        points=params.points_per_score * net,
        activated=activated_classes(ctx, candidate, state, facts),
        unappraised=tuple(unappraised),
        notes=tuple(notes),
    )


def expected_points(candidate: RuleCandidate, ctx: EvaluationContext,
                    params: ExpectedScoreParams) -> float:
    """动作的期望实际积分（**评分点**）；不在声明域内时返回 0.0。"""

    appraisal = appraise(candidate, ctx, params)
    if appraisal is None:
        return 0.0
    return round(appraisal.points, 6)


# --- 接缝：构造可直接交给适配器的候选 ---------------------------------------


def build_adjustment(
    params: ExpectedScoreParams = ExpectedScoreParams(),
    *,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustment:
    """构造可直接交给适配器的候选调整。

    candidates 参数不消费：本项是**逐动作的直接评分**，不需要跨候选的量
    （四族重叠的相加问题由「乘性期望」解决，而不是靠窗口内归一分摊）。
    """

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidates
        return expected_points(candidate, ctx, params)

    spec = AdjustmentSpec(
        name="价值族④-期望实际积分",
        version=EXPECTED_SCORE_VERSION,
        thought=(
            "把四个价值族从「各自的即时标量相加」改成**单一路径的期望值**："
            "总番在官方口径下是四个因子的**乘积**，故取各因子的期望再相乘"
            "（指示量乘子用 E[2^I]=1+P 的精确线性化）。兑现机会用规则给出的"
            "向听距离 + 有效牌剩余 + 牌墙余量（剩余巡数）折算成代理概率；"
            "代价项显式计入「等待/喂牌造成他家先胡时的支付」；"
            "庄闲与支付倍率直接调 settlement.settle_scores（唯一规则来源）"
            "⇒ 本人庄 24 / 本人闲 10，付方庄家 ×8 / 闲家 ×1。"
            "尚未形成但值得保留的路径（七对距离、四白所需进张）进**期望因子**，"
            "因此「离大牌更近」与「已有大牌」都能得到正分。这是结构 + 兑现的代理，"
            "不是已校准期望，也不是已证明的强化。"),
        trigger=(
            "本项按**动作后的规则事实**取值，不按动作标签分档："
            "弃牌改变向听/有效牌/链/四白/爆头；吃碰永久关闭七对路径（规则已证）；"
            "杠使链 +1；过牌保持原状态（与等待基线同值）。"
            "取值要求牌效事实（HAND_PROGRESS）与牌墙余量齐备，"
            "期望总番不得越出声明的 fan_cap；任一条件不满足时该动作**不评分**"
            "（返回 0 并记录原因），不用 0 或 False 冒充未知。"
            "合法胡恒为 priority=0，本项不参与其排序。"),
        scope=params.scope,
        bound=params.derived_bound,
    )
    return HeuristicAdjustment(
        spec, delta,
        source_fingerprint_value=source_fingerprint_value,
        params_json=params.to_json(),
    )


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """从声明参数构造候选；未知键直接报错，避免写错却静默用默认值。"""

    known = {"points_per_score", "fan_cap", "opp_fan_proxy", "opp_draw_rate",
             "decay_per_shanten", "use_dealer_parity", "use_opp_cost",
             "use_path_progress"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("价值族④参数含未知键：{0}；可识别：{1}".format(
            sorted(unknown), sorted(known)))
    kwargs = {key: float(params[key]) for key in known
              if key in params and key != "opp_fan_proxy"}
    if "opp_fan_proxy" in params:
        kwargs["opp_fan_proxy"] = int(params["opp_fan_proxy"])
    return build_adjustment(
        ExpectedScoreParams(**kwargs),
        source_fingerprint_value=source_fingerprint_value)


__all__ = [
    "ALL_KINDS",
    "ActionState",
    "Appraisal",
    "DEFAULT_DECAY_PER_SHANTEN",
    "DEFAULT_FAN_CAP",
    "DEFAULT_OPP_DRAW_RATE",
    "DEFAULT_OPP_FAN_PROXY",
    "DEFAULT_POINTS_PER_SCORE",
    "EXPECTED_SCORE_VERSION",
    "ExpectedScoreParams",
    "Exposure",
    "IMPOSSIBLE",
    "REACHED",
    "SCENARIO_CLASS_BINDINGS",
    "SETTLEMENT_BASE_SCORE",
    "UNKNOWN",
    "action_state_after",
    "activated_classes",
    "appraise",
    "build_adjustment",
    "build_adjustment_from_params",
    "chiitoi_reach",
    "expected_points",
    "exposure_units",
    "facts_useful_count",
    "four_white_reach",
    "hit_once",
    "opponent_cost",
    "path_reach",
    "realisation_chance",
    "remaining_rounds",
    "settlement_factors",
]

