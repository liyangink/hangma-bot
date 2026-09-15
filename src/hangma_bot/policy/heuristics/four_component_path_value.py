"""价值族（Value-Path Family）第三个实例：**四分量完整结构基线**。

## 这是什么

官方《1.3 番型倍率》原文（`doc/references/official-guide-v34-content.txt`
第 29 行，2026-09-14 抓取、2026-09-15 复核）：

    总番 = 1 × 分支因子 × 2^动作链次数 ×（4 白板 ×2）×（爆头 ×2）；
    计算顺序：分支 → 动作链 → 4 白板 → 爆头（**最后统一加**）

"最后统一加"即**在指数上相加**，所以取 log2 后总番是**四个加数**：

    log2(总番) = 分支 + 链次数 + 四白指示 + 爆头指示

本候选把这四个加数各做成一个**状态势分量**，用同一个尺度换算成评分点：

    Φ(s) = scale · Σ_i g_i(s) · φ_i(s)
    term(a) = Φ(s′) − Φ(s)

它**不是**"给吃加 X、给碰加 Y"这类动作标签加分：φ_i 只依赖**状态**
（暗牌、链次数、链内飘出、爆头），不依赖动作是吃还是碰。同一状态内所有不改状态
的动作因此得到**同一个平移**，相对次序在结构上不可能改变（这正是
`review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates/TRIGGER-SET-FINDINGS.md`
§4.1 那条推论的来源）。

**本项是结构基线，不是效果结论**：四个分量的"未兑现路径代理"是【工程假设】，
是否更优由完整桌赛与阶段目标实测回答（PLAN-REVISION §1.1、§2）。

## 四个分量、声明域与来源

| 分量 | φ_i(s) | 域 | 依据 |
| --- | --- | --- | --- |
| 分支 branch | 七对路径存活时 `1 + 已锁定豪华组数`；有副露（平胡分支）时 0 | [0,4] | 【官方】番型表：平胡 ×1（log2 0）、七对 ×2（1）、豪华 N 组 2×2^N（1+N，N=0—3） |
| 链 chain | 本人动作链次数 | [0,6] | 【官方】fan-calc 请求字段 `chain.count 0-6`（快照第 106 行） |
| 四白 four_white | 等值条件成立 1，否则 0 | [0,1] | 【官方】"手留白 + 链内飘出 = 4（正好 4 张；普通打出的、杠出的不算）" |
| 爆头 baotou | 爆头 1，否则 0 | [0,1] | 【官方】1.2 判定；运行时取 `rule_state.baotou` |

**"已锁定豪华组数"是确定性代理【工程假设，不是官方口径】**：暗牌里**恰好 4 张**的
**自然牌**码各计 1 组。它与结算分解同源（`hand_analysis.win_split` 的
`sum(1 for value in counts if value == 4)`），但结算还有一条
"`whites == 4 and not singles` 时 4 张真白板算 1 组"——那依赖"白板是否已被用于补落单"，
是**成胡时才能判定**的事实（PLAN-REVISION §1.3 的"待随机事件后"栏），本项**不猜**。
因此本项只会**少算**、不会多算豪华组数。

**平胡分支为什么是 0**：平胡的分支因子是 1 ⇒ log2 0。有副露时七对路径被**官方明文
永久关闭**（"七对子：禁止吃碰明杠暗杠"），此时分支分量取平胡的 0。

## 门控放在势函数内部，且**只依赖单个状态**（PLAN-REVISION §1.2）

"无法确定"的分量不能拿 0 或 False 冒充（§1.3：未知后态不得填零）。本模块按规划给出的
形式实现门控——**门控是状态的性质，不是"这一对状态"的性质**：

    Φ(s) = Σ_i g_i(s) · φ_i(s)        g_i(s) ∈ {0,1} 只依赖**单个状态 s**
    term(s → s′) = Φ(s′) − Φ(s)       声明域内取**完整差值**

`g_i(s) = 1` 当且仅当 φ_i(s) 在状态 s 上**可判定且落在上表的声明域内**。
"用某一侧的已知值替另一侧填数"是被禁止的（未知不填零）。

### 适用域条件（不是门控值）：域外转移整段返回 0

下面每一条都使**该转移**判为**域外（out-of-domain）**并返回 0——此时
`Φ(s′) − Φ(s)` 不再是一个可解释的价值差（会把"门控开关"本身算成价值变化）。
四条逐条枚举、逐条测试：

| # | 域外条件 | 为什么这样声明 |
| --- | --- | --- |
| **D1** | 任一端点有分量的值**越出声明域**（链次数 ∉ [0,6]；分支 ∉ [0,4]；指示量非 0/1） | 端点已不在 Φ 的声明域上，差值没有定义；不夹取、不惩罚 |
| **D2** | 某分量在两端点的**可判定性模式不同**（一端 `g=1`、另一端 `g=0`） | 差值里会混进"门控开关"，而不是价值变化 |
| **D3** | 终局（胡）——**声明的终局例外**，不是域外 | 合法胡恒为 `priority = 0`，评分不参与它的排序，见下 |
| **D4** | 无法构造 `s′`（未知动作类型；副露数不能由暗牌张数反推） | 不猜 |

**D2 是"势差形状"的必要条件，不是可选的洁癖**：域外转移返回 0 是**声明的降级**，
与"该转移真的没有价值变化"在语义上不同，因此两者必须能被分开报告
（见下面的作用域声明与结构证据）。

### 可加性与环判据的**作用域**（必须与结论一起引用）

`term = Φ(s′) − Φ(s)` 在**声明域内、且可判定性模式恒定**的转移集上是单态势差，
因此**在该子集上**可加性（`F(A,B) + F(B,C) = F(A,C)`）与环判据（闭环求和为 0）成立。

**这不是全域结论**：域外转移返回的是声明的降级值 0，不是势差；把它混进加法就会得到
"看起来违反可加性"的算式。最小反例（四白分量在三点上从"可判定"掉到"不可判定"）：

    A: 四白 = False（φ=0）      B: 四白 = True（φ=1）      C: 四白 不可判定（g=0）
    F(A,B) = +scale = +40        F(B,C) = 0（D2 域外）        F(A,C) = 0（D2 域外）
    F(A,B) + F(B,C) = 40  ≠  0 = F(A,C)

这**不**说明势差算错：B→C 与 A→C 根本不在声明域内，它们是**声明过的降级**，
不是被静默算错的差值。结构证据（`evidence/3.0-baseline`）把域内/域外**分别计数**
并在 JSON 的 `scope` 字段里写明，`tests/.../test_gated_counterexample_*` 把这条反例
固定成回归——"可加性违规 0"**只**指域内子集。

**`potential` 与 `state_term` 同源**：域内转移的 `term` 直接由
`potential(s′) − potential(s)` 取差，保证"声明的 Φ"与"实现的增量"不可能各说各话；
域外转移走的是声明过的降级路径，不参与该等式。

三种"不可判定"的来源与处置：

| 情形 | 处置 | 依据 |
| --- | --- | --- |
| `chain_piao` 为空（观察编码器不落盘该字段） | 四白分量不计入；**除非**手留财神 4 张——此时链内飘出必为 0（4 张白板全在手上），可判定 | 【实现 + 官方同口径】白板共 4 张、`settlement._validate_chain` 的 `手留白 + 链内飘出 ≤ 4` |
| 暗牌张数不是 13/14 − 3×副露 的合法形态（对 3 取余为 0） | 依附于副露数的分支分量与"弃牌后爆头"不计入 | 【实现】`evaluation_v1._hand_codes_without_double_count` 的归一化不变量 |
| 弃的牌不在暗牌里 | 爆头分量不计入（`baotou_after_action` 返回 None） | 【实现】`progression.baotou_after_action` 明确"不猜" |
| 四白输入越出 0—4（上游装配错误） | 四白分量不计入；**不夹取、不抛错** | 本模块的边界决定，见下 |

**关于最后一行**：规则模块 `four_white_indicator` 对越界输入**抛 ValueError**
（"只可能是上游装配错误，立即失败"）。本候选选择**不下沉该异常**：越界时把该分量
判为不适用，其余三个分量仍可用，评分器不会因为一个越界字段整体失效。越界本身仍应
由上游装配测试捕获——本模块既**不静默夹取**（那会把错误数据算成一个合法的 0/1），
也**不替上游做合法性判断**。

## bound 的推导（PLAN-REVISION §1.2 实施答疑）

先由势函数本身推导范围，取 `bound ≥ Φ_max − Φ_min`：

    Φ_min = 0                        （四个分量同时取 0：平胡分支 0 + 链 0 + 四白 0 + 爆头 0）
    Φ_max = scale × (4 + 6 + 1 + 1)  = 40 × 12 = 480
    bound = Φ_max − Φ_min            = 480

四个上界分别有依据：分支 4 = 1 + 豪华组数上限 3（`settlement.compute_fan` 校验
`0 <= luxury_pairs <= 3`）；链 6 = 官方 `chain.count 0-6`；四白与爆头各 1（指示量）。
**480 是声明域上的保守范围上界，不是已证明可达的单步差值**：单步
`|Φ(s′) − Φ(s)|` 还受"一个动作能同时改变几个分量"约束，实际更小。门控不扩大声明域，
故 `|term| ≤ 480` 在声明域内恒成立。

`bound` 由参数**推导**（`scale × Σ 各分量的声明上界`）而不是手写常量：改尺度或
关掉分量时上界自动跟着变，不会出现"常量写着 480、实际域已变"的漂移。
`bound` 与全部结构参数一起进 `params_json`，因此**进候选身份**——改 bound 就是换候选。

**本模块不做任何裁剪**：唯一的强制点是 `heuristic_adapter.HeuristicAdjustment.apply`
的钳制与越界审计（G-1 把"适配器发生钳制"列为失败）。候选内部先裁剪、再让适配器计数
为 0，会被读成"没有越界"，那正是 PLAN-REVISION §1.2 明确禁止的写法。

## 一处**有意**的偏离：终局（胡）

按严格势差，胡是吸收态，应为 `Φ(吸收态) − Φ(s)`。本项对胡返回 0.0，理由与价值族②
相同：合法胡恒为 `priority = 0`（`evaluation_v1._priority`），评分不参与它的排序，
"0 还是 −Φ(s)"**不可能改变任何计划**；写一个大负数只会误导人工复核。
差异只落在 win 动作上，同状态内其余动作仍共享同一势差。

## 分量开关（消融用，都是**独立候选身份**）

`use_branch / use_chain / use_four_white / use_baotou` 取 0 或 1，用于"单项、组合、
去掉一项、全零"消融。它们进 `params_json` ⇒ 进候选身份，因此每个消融变体都必须
**单独准入**，不能拿完整版本的准入结论代用（PLAN-REVISION §3.0）。

## 证据级别（根 AGENTS.md §3）

- 【官方】四个加数、四个乘子的倍率、`chain.count 0-6`、四白等值条件、七对禁副露；
- 【实现】副露数由暗牌张数反推、弃后爆头重算、吃碰杠继承爆头、豪华组数代理的口径；
- 【工程假设】四个分量作为**非终局价值代理**本身（路径存活不等于必然兑现，
  未来分支 0—4 不能冒充已知事实）；
- 【推导】`bound = 480` 与"手留 4 张 ⇒ 链内飘出为 0"。

## 纯度

纯函数：只读 `EvaluationContext`、规则给的候选与不可变参数；不读时间、随机、文件、
网络，不做搜索，不改候选集合。规则一律调用 `hangma`（`progression` /
`special_rules`），**policy 不复制规则**。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.hangma.progression import (
    baotou_after_action,
    chain_after_action,
    wealth_after_action,
)
from hangma_bot.hangma.special_rules import four_white_indicator
from hangma_bot.kernel.actions import Chi, Discard, Gang, Hu, Pass, Peng, Tile

from ..evaluation_v1 import EvaluationContext
from ..heuristic_adapter import AdjustmentSpec, HeuristicAdjustment

FOUR_COMPONENT_VERSION = "four-component-path-value-v1"

# --- 声明域（每一项都在模块 docstring 里给出依据） ---------------------------

#: 平胡分支因子 1 ⇒ log2 0。**规则常量，不是调参结果。**
BRANCH_LOG2_PLAIN = 0.0
#: 七对 ×2 ⇒ log2 1。**规则常量。**
BRANCH_LOG2_CHIITOI = 1.0
#: 豪华七对只到 3 组（`settlement.compute_fan` 校验 0—3）。
MAX_LUXURY_GROUPS = 3
#: 分支分量上界 = 七对 1 + 最多 3 组豪华。
BRANCH_LOG2_CAP = BRANCH_LOG2_CHIITOI + MAX_LUXURY_GROUPS
#: 官方 fan-calc 请求字段 `chain.count 0-6`（快照第 106 行）。
MAX_CHAIN_COUNT = 6
#: 四白是等值指示（官方：手留白 + 链内飘出 == 4），贡献 1 个 log2 番。
FOUR_WHITE_LOG2_CAP = 1.0
#: 爆头 ×2 ⇒ 1 个 log2 番。
BAOTOU_LOG2_CAP = 1.0
#: 尺度锚点同价值族②：V1 权重里 `gang_bonus = 40.0` 已是"一次杠（×2 = log2 +1）"的分值。
DEFAULT_SCALE = 40.0

#: 白板总数（官方 400 校验口径：手留白 + 链内飘出 ≤ 4；136 张中白板共 4 张）。
WEALTH_TOTAL = 4
#: 无副露时暗牌张数（不含刚摸牌）。
CONCEALED_TILES_NO_MELD = 13
#: 含刚摸牌时的满手张数。
CONCEALED_TILES_WITH_DRAW = 14
#: 每次副露使暗牌少 3 张。
MELD_TILE_STEP = 3

#: 作用面：**全部动作类别**。理由同价值族①②——分档依据是状态变化，
#: 而状态变化可以发生在任何动作上；用动作类别去卡就退化成动作标签加分。
ALL_KINDS: Tuple[str, ...] = ("chi", "peng", "gang", "discard", "pass", "hu")

#: 分量名（顺序固定；产物与证据按此顺序报告逐分量覆盖）。
COMPONENT_NAMES: Tuple[str, ...] = ("branch", "chain", "four_white", "baotou")


@dataclass(frozen=True)
class PathState:
    """一个决策状态在四个分量上的取值。

    **`None` 表示"该分量在此状态不可判定"，不是 0**（术语表：空与 0 必须区分）。
    四个字段都是 log2 口径的"该分量为总番贡献了几个 ×2"，不是评分点。
    """

    branch_log2: Optional[float]
    chain_count: Optional[int]
    four_white: Optional[bool]
    baotou: Optional[bool]


@dataclass(frozen=True)
class FourComponentPathParams:
    """不可变参数实例；**全部字段进候选身份**。

    scale：单位 **评分点 / log2 番**，四个分量共用同一个尺度（PLAN-REVISION §1.1
        "初始可用单一尺度"）。
    branch_cap / chain_cap：两个分量的声明上界，进 `bound` 推导。
    use_*：分量开关（0 或 1），供消融变体使用。
    bound：**推导属性**，见模块 docstring；不手写常量。
    """

    scale: float = DEFAULT_SCALE
    branch_cap: float = BRANCH_LOG2_CAP
    chain_cap: int = MAX_CHAIN_COUNT
    use_branch: float = 1.0
    use_chain: float = 1.0
    use_four_white: float = 1.0
    use_baotou: float = 1.0
    scope: Tuple[str, ...] = ALL_KINDS

    def __post_init__(self) -> None:
        for field_name in ("scale", "branch_cap", "use_branch", "use_chain",
                           "use_four_white", "use_baotou"):
            value = getattr(self, field_name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(
                    "FourComponentPathParams.{0} 必须是有限数值".format(field_name))
        if type(self.chain_cap) is not int:
            raise ValueError("FourComponentPathParams.chain_cap 必须是整数")
        if self.scale < 0:
            raise ValueError("FourComponentPathParams.scale 必须非负")
        if self.branch_cap <= 0 or self.chain_cap <= 0:
            raise ValueError("分支与链的声明上界必须为正")
        for field_name in ("use_branch", "use_chain", "use_four_white", "use_baotou"):
            if getattr(self, field_name) not in (0.0, 1.0):
                raise ValueError(
                    "FourComponentPathParams.{0} 只能是 0 或 1".format(field_name))

    @property
    def bound(self) -> float:
        """幅度上限 = `scale × Σ (声明上界 × 开关)`；见模块 docstring 的推导。"""

        total = (
            self.use_branch * self.branch_cap
            + self.use_chain * float(self.chain_cap)
            + self.use_four_white * FOUR_WHITE_LOG2_CAP
            + self.use_baotou * BAOTOU_LOG2_CAP
        )
        return self.scale * total

    def to_json(self) -> str:
        """稳定序列化；**进候选身份**，使产物可复现到具体参数与推导出的 bound。"""

        return (
            "scale={0},branch_cap={1},chain_cap={2},bound={3},"
            "use=branch{4}+chain{5}+four_white{6}+baotou{7},scope={8}".format(
                self.scale, self.branch_cap, self.chain_cap, self.bound,
                int(self.use_branch), int(self.use_chain),
                int(self.use_four_white), int(self.use_baotou),
                "+".join(self.scope)))


# --- 状态事实：全部来自规则模块或评分上下文的机械计数 ------------------------


def meld_count_of(combined_codes: Tuple[str, ...]) -> Optional[int]:
    """由暗牌张数反推**本人副露数**；形态不合法时返回 `None`（不猜）。

    依据 `evaluation_v1._hand_codes_without_double_count` 的归一化不变量：
    有刚摸牌时长度 = `14 − 3×副露数`，无刚摸牌（响应窗口）时长度 = `13 − 3×副露数`。
    两种形态对 3 取余分别是 2 与 1，**互不混淆**，因此余数唯一确定分支：

        余 2 ⇒ 副露数 = (14 − 长度) / 3
        余 1 ⇒ 副露数 = (13 − 长度) / 3
        余 0 ⇒ 不是任何一种合法形态 ⇒ None

    为什么需要它：七对路径是否存活（有无副露）与"弃牌后爆头"都要用到副露数，而
    `EvaluationContext` 只带**他家**副露（`next_seat_meld_codes` /
    `dealer_meld_codes`），本人暗牌张数是上下文里唯一可用的等价信息。
    本函数只做计数，不做任何规则判断。
    """

    length = len(combined_codes)
    residue = length % MELD_TILE_STEP
    if residue == 2:
        melds = (CONCEALED_TILES_WITH_DRAW - length) // MELD_TILE_STEP
    elif residue == 1:
        melds = (CONCEALED_TILES_NO_MELD - length) // MELD_TILE_STEP
    else:
        return None
    return melds if melds >= 0 else None


def locked_luxury_groups(concealed_codes: Tuple[str, ...], wealth_code: str) -> int:
    """暗牌里**恰好 4 张**的自然牌码数（豪华七对已锁定的组数代理）。

    【工程假设】与结算同源但更保守：结算在成胡时按 `sum(value == 4)` 计入豪华组，
    本项现在就把"手里已经有 4 张同牌"计为 1 组；白板（财神）不计——结算里
    "4 张真白板算 1 组"还要求"其余牌全为自然对、未用于补落单"，那是未来成胡时的事实。
    """

    counts: dict = {}
    for code in concealed_codes:
        counts[code] = counts.get(code, 0) + 1
    return sum(1 for code, count in counts.items()
               if count == WEALTH_TOTAL and code != wealth_code)


def known_piao(wealth_count: int, chain_piao: Optional[int],
               chain_count: int) -> Optional[int]:
    """链内飘出白板数；只在**可以确定**时给出数值，否则 `None`。

    `chain_piao` 已知时原样返回。为空时有两种情形可以**推导**（都是规则直接给出的）：

    1. **链次数为 0 ⇒ 飘出必为 0**：官方 fan-calc 字段说明写的是 `piao ≤ count`
       （实现侧 `settlement._validate_chain` 同口径校验），链次数 0 时不可能有飘出；
    2. **手留财神恰好 4 张 ⇒ 飘出必为 0**：4 张白板全在手上，
       白板不可被吃碰杠胡（指南 §1.1），飘出的白板不会回到手上。

    其余情形保持 **None**：把未知写成 0，会让"四白"这个**等值条件**凭空成立或不成立。

    **为什么这两条推导很重要**：观察编码器不落盘 `chain_piao` 时，若不做推导，
    `s` 的四白不可判定而 `s′`（断链后飘出确定为 0）却可判定，转移就会因为
    "可判定性模式不同"（D2）整段落在声明域外——那会把绝大多数弃牌窗口排除掉，
    而这原因与候选机制无关。
    """

    if chain_piao is not None:
        return chain_piao
    if chain_count == 0:
        return 0
    if wealth_count == WEALTH_TOTAL:
        return 0
    return None


def four_white_state(whites_held: int, piao: Optional[int]) -> Optional[bool]:
    """四白等值条件的**单一规则来源**是 `special_rules.four_white_indicator`。

    任一输入未知 ⇒ None（该分量不适用）。数值越出规则域（只可能是上游装配错误）
    ⇒ 同样返回 None：本模块既不夹取、也不替上游做合法性判断，见模块 docstring。
    """

    try:
        return four_white_indicator(whites_held, piao)
    except ValueError:
        return None


def concealed_tiles(ctx: EvaluationContext) -> Tuple[Tile, ...]:
    """评分上下文里的本人暗牌（含刚摸牌）→ 规则模块需要的 `Tile` 元组。"""

    return tuple(Tile(code) for code in ctx.combined_codes)


def context_state(ctx: EvaluationContext) -> PathState:
    """动作前状态 `s` 的四分量取值；不可判定的分量记为 `None`。"""

    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        branch: Optional[float] = None
    elif melds == 0:
        branch = BRANCH_LOG2_CHIITOI + locked_luxury_groups(
            ctx.combined_codes, ctx.wealth_code)
    else:
        branch = BRANCH_LOG2_PLAIN
    piao = known_piao(ctx.wealth_count, ctx.chain_piao, ctx.chain_count)
    return PathState(
        branch_log2=branch,
        chain_count=ctx.chain_count,
        four_white=four_white_state(ctx.wealth_count, piao),
        baotou=ctx.baotou,
    )


def action_state(candidate: RuleCandidate, ctx: EvaluationContext,
                 before: PathState) -> Optional[PathState]:
    """已知动作后状态 `s′` 的四分量取值；**终局（胡）返回 None**。

    - 吃 / 碰 / 杠：七对路径**永久关闭**（【官方】"七对子：禁止吃碰明杠暗杠"）
      ⇒ 分支取平胡的 0；爆头按【实现 + 用户确认】**继承**动作前状态
      （官方指南未逐事件写出赋值公式）。
    - 过牌：规则状态与手牌都不变 ⇒ `s′` 与 `s` 是**同一个状态**，直接返回 `before`。
    - 弃牌：分支按"弃后暗牌还剩几个 4 张组"算（只有被弃的那个牌码会变，
      不需要重排手牌）；爆头调用 `baotou_after_action`（用**弃后暗牌**重新判定；
      弃的牌不在暗牌里时它返回 None ⇒ 本分量不适用）。
    - 链 / 四白：一律走 `progression.chain_after_action` / `wealth_after_action`，
      本模块不重算规则。
    """

    action = candidate.action
    if isinstance(action, Hu):
        return None                       # 终局：见模块 docstring 的偏离说明
    if isinstance(action, Pass):
        return before

    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None                       # 依附副露数的分量都无法判定：不猜
    # 用**推导后**的 piao 参与转移：断链与杠都会把它带到 s′，
    # 于是 s′ 的可判定性与 s 一致（否则会因为"模式不同"整段落入域外）。
    piao_before = known_piao(ctx.wealth_count, ctx.chain_piao, ctx.chain_count)
    chain_after, piao_raw = chain_after_action(
        ctx.chain_count, piao_before, ctx.baotou, action)
    wealth_after = wealth_after_action(ctx.wealth_count, action)
    piao_after = known_piao(wealth_after, piao_raw, chain_after)

    if isinstance(action, Discard):
        if before.branch_log2 is None:
            branch: Optional[float] = None
        elif melds > 0:
            branch = BRANCH_LOG2_PLAIN
        else:
            # 弃掉"恰好 4 张"的**自然牌**那张 ⇒ 该豪华组不再锁定；其余情况组数不变。
            # 财神必须排除：locked_luxury_groups 只数自然四张（"4 张真白板算 1 组"
            # 要成胡时才判定），打折一张财神并没有打掉任何已锁定的豪华组。
            natural_four = (
                ctx.combined_codes.count(action.tile.code) == WEALTH_TOTAL
                and action.tile.code != ctx.wealth_code)
            branch = before.branch_log2 - (1.0 if natural_four else 0.0)
        baotou: Optional[bool] = baotou_after_action(
            ctx.baotou, action, concealed_tiles(ctx), melds)
    elif isinstance(action, (Chi, Peng, Gang)):
        branch = BRANCH_LOG2_PLAIN
        baotou = ctx.baotou               # 继承（无需副露数）
    else:                                 # 未知动作类型：不猜
        return None

    return PathState(
        branch_log2=branch,
        chain_count=chain_after,
        four_white=four_white_state(wealth_after, piao_after),
        baotou=baotou,
    )


# --- 势函数、完整差值与逐分量分解 -------------------------------------------


def _as_log2(value: Optional[bool]) -> Optional[float]:
    """指示量 → log2 口径；`None` 原样传下去（不可判定 ≠ 0）。"""

    return None if value is None else (1.0 if value else 0.0)


def _component_pairs(before: PathState, after: PathState,
                     params: FourComponentPathParams):
    """(分量名, 动作前值, 动作后值, 声明上界, 开关) —— 五项一组，顺序固定。"""

    return (
        ("branch", before.branch_log2, after.branch_log2,
         params.branch_cap, params.use_branch),
        ("chain",
         None if before.chain_count is None else float(before.chain_count),
         None if after.chain_count is None else float(after.chain_count),
         float(params.chain_cap), params.use_chain),
        ("four_white", _as_log2(before.four_white), _as_log2(after.four_white),
         FOUR_WHITE_LOG2_CAP, params.use_four_white),
        ("baotou", _as_log2(before.baotou), _as_log2(after.baotou),
         BAOTOU_LOG2_CAP, params.use_baotou),
    )


def _gate(value: Optional[float], cap: float) -> bool:
    """单态门控 `g_i(s)`：该分量在**这个状态**上可判定且落在声明域内时为 1。"""

    return value is not None and 0.0 <= value <= cap


def _fmt(value: float) -> str:
    """域外原因的稳定文本（`7.0` → `7`），便于产物比对。"""

    return "{0:g}".format(value)


def domain_status(before: PathState, after: PathState,
                  params: FourComponentPathParams) -> Tuple[bool, Tuple[str, ...]]:
    """这个转移是否落在**声明域**内；不在域内时逐条给出原因（D1 / D2）。

    - `(True, ())`：两个端点的四个分量都在声明域内，且各分量的可判定性模式一致
      ⇒ 可以取 `Φ(s′) − Φ(s)` 的完整差值；
    - `(False, reasons)`：命中 **D1**（端点越出声明域）或 **D2**（可判定性模式不同）
      ⇒ 该转移按声明返回 0，`reasons` 逐条列出分量与原因。

    终局（D3）与"无法构造 `s′`"（D4）不在这里：它们连"两个状态"都没有，
    由 `path_term` 直接返回 0。四条域外条件见模块 docstring。
    """

    reasons: List[str] = []
    for name, left, right, cap, use in _component_pairs(before, after, params):
        del use                      # 开关只影响取值，不影响可判定性与域
        if left is not None and not 0.0 <= left <= cap:
            reasons.append("{0}:动作前越出声明域({1})".format(name, _fmt(left)))
        if right is not None and not 0.0 <= right <= cap:
            reasons.append("{0}:动作后越出声明域({1})".format(name, _fmt(right)))
        if _gate(left, cap) != _gate(right, cap):
            reasons.append("{0}:可判定性模式不同".format(name))
    return (not reasons, tuple(reasons))


def component_deltas(before: PathState, after: PathState,
                     params: FourComponentPathParams) -> Tuple[Tuple[str, float], ...]:
    """**逐分量**的势差分解（只在**声明域内**的转移上有定义）。

    域外转移（D1/D2）返回**空元组**：那不是"四个分量都为 0"，而是"这个转移不参与
    势差"。两者必须能被分开读，所以这里不返回四个 0.0。
    域内转移返回每个可判定分量的 `scale × use × (φ′ − φ)`——**含恰好为 0 的分量**，
    它们仍是"该分量可判定"的证据，供逐分量覆盖报告使用。

    返回顺序与 `COMPONENT_NAMES` 一致；值为**评分点**（已乘 scale）。
    """

    in_domain, _ = domain_status(before, after, params)
    if not in_domain:
        return ()
    parts = []
    for name, left, right, cap, use in _component_pairs(before, after, params):
        if use == 0.0:
            continue
        if left is None or right is None:        # 域内不会发生；防御性跳过
            continue
        parts.append((name, params.scale * use * (right - left)))
    return tuple(parts)


def potential(state: PathState, params: FourComponentPathParams) -> float:
    """`Φ(s) = scale · Σ_i g_i(s) · φ_i(s)`：**门控只看单个状态**。

    越出声明域的值在**本状态**上 `g=0`（门控只收窄、不扩大声明范围）；
    但含这种端点的**转移**会被 `domain_status` 判为域外（D1），
    不会用这个 Φ 去取差。
    """

    total = 0.0
    for _, value, _, cap, use in _component_pairs(state, state, params):
        if use == 0.0 or not _gate(value, cap):
            continue
        total += value
    return params.scale * total


def state_term(before: PathState, after: PathState,
               params: FourComponentPathParams) -> float:
    """`Φ(s′) − Φ(s)`：**与 `potential` 同源**，域外转移按声明返回 0。

    域内：直接取两个单态势之差，取**完整差值**、不做任何提前返回——R8-2 的教训是
    "前后都存活就返回 0"会把同一条路径内部的更近/更远变化整个吞掉；
    域外（D1/D2）：返回 0，原因见 `domain_status`；可加性与环判据只在域内子集上成立
    （见模块 docstring 的作用域声明与最小反例）。
    """

    in_domain, _ = domain_status(before, after, params)
    if not in_domain:
        return 0.0
    return round(potential(after, params) - potential(before, params), 6)


def path_term(candidate: RuleCandidate, ctx: EvaluationContext,
              params: FourComponentPathParams) -> float:
    """从"动作 + 上下文"直接算 `Φ(s′) − Φ(s)`。

    终局（D3）或无法构造 `s′`（D4）时返回 0.0；域外（D1/D2）由 `state_term` 返回 0。
    """

    before = context_state(ctx)
    after = action_state(candidate, ctx, before)
    if after is None:
        return 0.0
    return state_term(before, after, params)


# --- 接缝：构造可直接交给适配器的候选 ---------------------------------------


def build_adjustment(
    params: FourComponentPathParams = FourComponentPathParams(),
    *,
    source_fingerprint_value: str = "",
) -> HeuristicAdjustment:
    """构造可直接交给适配器的候选调整。"""

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidates        # 本项是纯状态势，不需要跨候选的量
        return path_term(candidate, ctx, params)

    spec = AdjustmentSpec(
        name="价值族③-四分量路径价值",
        version=FOUR_COMPONENT_VERSION,
        thought=(
            "按官方番型公式的四个乘子（分支 / 动作链 / 四白 / 爆头）组织评分："
            "总番在 log2 下正是这四个加数之和，因此取 Φ(s) = scale × 四加数之和，"
            "按 Φ(s′)−Φ(s) 计分。四个分量都只依赖状态（暗牌、链、链内飘出、爆头），"
            "不依赖动作标签：吃碰不改链与四白、只关闭七对路径（官方明文禁止副露）；"
            "弃牌可能断链、失去爆头或打掉四白。门控只依赖单个状态（g_i(s)），"
            "增量取 Φ(s′)−Φ(s)；分量在端点不可判定、或端点越出声明域时，"
            "该转移整段判为域外并返回 0，不用 0 或 False 冒充未知。"
            "这是结构基线，不是已证明的强化。"),
        trigger=(
            "动作改变了四个分量中的至少一个：弃牌（链断/飘、爆头进出、手留白减少、"
            "打掉已锁定的 4 张组）、杠（链 +1）、吃碰（七对路径关闭）、过牌不改变任何分量；"
            "其中四白需要链内飘出可判定（已知，或手留 4 张时推导为 0），"
            "分支与弃牌后爆头需要暗牌张数能反推副露数；"
            "分量在端点不可判定或越出声明域时该转移整段返回 0（域外）；"
            "胡为终局，本项返回 0"),
        scope=params.scope,
        bound=params.bound,
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

    known = {"scale", "branch_cap", "chain_cap",
             "use_branch", "use_chain", "use_four_white", "use_baotou"}
    unknown = set(params) - known
    if unknown:
        raise ValueError("价值族③参数含未知键：{0}；可识别：{1}".format(
            sorted(unknown), sorted(known)))
    kwargs = {key: float(params[key]) for key in known
              if key in params and key != "chain_cap"}
    if "chain_cap" in params:
        kwargs["chain_cap"] = int(params["chain_cap"])
    return build_adjustment(
        FourComponentPathParams(**kwargs),
        source_fingerprint_value=source_fingerprint_value)


__all__ = [
    "ALL_KINDS",
    "BAOTOU_LOG2_CAP",
    "BRANCH_LOG2_CAP",
    "BRANCH_LOG2_CHIITOI",
    "BRANCH_LOG2_PLAIN",
    "COMPONENT_NAMES",
    "DEFAULT_SCALE",
    "FOUR_COMPONENT_VERSION",
    "FOUR_WHITE_LOG2_CAP",
    "FourComponentPathParams",
    "MAX_CHAIN_COUNT",
    "MAX_LUXURY_GROUPS",
    "PathState",
    "WEALTH_TOTAL",
    "action_state",
    "build_adjustment",
    "build_adjustment_from_params",
    "component_deltas",
    "concealed_tiles",
    "context_state",
    "domain_status",
    "four_white_state",
    "known_piao",
    "locked_luxury_groups",
    "meld_count_of",
    "path_term",
    "potential",
    "state_term",
]
