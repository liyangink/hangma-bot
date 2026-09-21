"""六动作族候选生成：出牌、吃、碰、杠（暗/明/补）、胡、过。

本文件属于「动作族」子模块：按 `WindowContext`（engine 从
`PlayerObservation` 提取的机械事实）生成当前动作窗口内的全部合法候选。
采用「族生成器 + 组合器」结构——每个动作族一个独立纯函数，
`generate_candidates` 按固定族顺序聚合并逐族隔离异常（§9：任一分支
抛错只形成该族 RuleIssue，不得让整体分析崩溃）。

职责边界（避免第二套规则源）：

- 手牌数学不在此复制：胡牌族只消费注入的 `HandSummary.is_win`
  （hand_analysis 的产物，由 engine 调用后传入）。以参数注入而非
  import：两子模块并行开发时互不阻塞，且手牌分析失败（hand=None）
  时胡牌族保守降级，不影响其余五族候选。
- 财神限制与抓打圈约束在生成侧直接应用（§1/§6），与 special_rules
  的单动作校验器同源同据（RULES_EVIDENCE.md）；engine 可再用
  special_rules 做提交前复核，本模块不 import 它以保持并行边界。
- YouCaiBiKao（§7）需要 RuleConfig 与爆头/杠上摸牌状态，由
  special_rules/engine 在候选产出后过滤，本模块不判断。
- 飘/杠链与结算语义见 special_rules / settlement；向听排序属 policy。

输入契约（2026-09-08 圈主修订）：`WindowContext.catch_play` 是本座是否
受限，由 engine 调用唯一圈主解析产生；不是官方 god.catch_play 全局值。
非圈主和归属未知者仅摸切、暗杠、自摸胡。已证明圈主不受摸切限制，
响应动作仍须实际 phase、responding_seats、触发弃牌与手牌条件齐全。
v26已明确圈主可吃碰明杠补杠（2026-09-09抓取v27全文）；不再附加待确认
降级标记，仍不得把本地候选等同官方已开放的响应成员。

全部函数为纯函数：不访问网络、文件、时钟或随机源；最差手牌（17 张）
下每族都是 O(34) 计数遍历，毫秒级完成，满足 1 秒动作窗口预算。

规则依据与证据级别：`RULES_EVIDENCE.md` §1/§2/§6/§7/§9
（官方指南 v9，2026-09-03 抓取）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from hangma_bot.kernel.actions import (
    Action,
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowPhase,
    action_key,
)

from .interface import RuleCandidate, RuleIssue
from .internal_types import (
    TILE_INDEX,
    TILE_ORDER,
    WEALTH_CODE,
    HandSummary,
    WindowContext,
    counts_from_tiles,
    is_wealth,
)

_DRAW = WindowPhase.DRAW.value
_RESPONSE_PENG = WindowPhase.RESPONSE_PENG.value
_RESPONSE_CHI = WindowPhase.RESPONSE_CHI.value

WALL_RESERVE_TILES = 20
"""牌墙保留不摸的张数（最后 10 墩）；剩余 ≤ 该值时禁止任何杠（§6）。

边界口径（【假设】需测试房间验证）：`remaining_tile_count` 按"含保留
区的墙余"理解——剩余恰好 20 即已进入保留区，杠的补牌无从摸取，禁止；
> 20 才允许杠。
"""

MAX_CHI_MELDS = 2
"""吃副露上限（"吃最多 2 摊"，§6）；碰/杠次数不限。"""

FAMILY_ORDER: Tuple[str, ...] = ("discard", "chi", "peng", "gang", "hu", "pass")
"""组合器聚合的固定族顺序：出牌 → 吃 → 碰 → 杠 → 胡 → 过。

顺序确定且与窗口语义一致（响应窗口候选以过收尾，摸牌窗口必须行动），
结果可逐字节回归对比（确定性性质测试的基础）。
"""


@dataclass(frozen=True)
class FamilyOutcome:
    """一个（或全部）动作族的候选与降级说明。

    `candidates` 按族内规范顺序（TILE_ORDER 升序 / 动作种类固定序）
    去重排列；`issues` 为空表示该族完整分析，非空表示保守降级或观察
    自相矛盾（可审计，不静默吞掉）。规则性无候选（如财神不可被吃）
    不产生 Issue——那是规则本身而非降级。
    """

    candidates: Tuple[RuleCandidate, ...]
    issues: Tuple[RuleIssue, ...]


_EMPTY: FamilyOutcome = FamilyOutcome((), ())


def _area(family: str) -> str:
    """族名 → 稳定 RuleIssue.area；engine 聚合时以此区分来源模块。"""

    return "action_families.{0}".format(family)


def _candidate(action: Action, evidence: Tuple[str, ...]) -> RuleCandidate:
    """构造候选；action_key 复用 kernel 单一实现，不二次推导键规则。"""

    return RuleCandidate(
        action=action, action_key=action_key(action), evidence=evidence
    )


def _own_draw(context: WindowContext) -> bool:
    """是否处于本人摸牌窗口（draw ∧ turn=me，§6 阶段判定下限）。"""

    return context.phase == _DRAW and context.turn_seat == context.seat


def _responding(context: WindowContext, phase: str) -> bool:
    """本人是否处于指定响应窗口（阶段匹配 ∧ 本人 ∈ 响应座位，§6）。"""

    return context.phase == phase and context.seat in context.responding_seats


def _number_of_code(code: str) -> Optional[int]:
    """数牌（万/筒/条）牌值 → 1-9 点数；字牌返回 None（无顺子概念）。"""

    if len(code) == 2 and code[1] in ("w", "b", "t") and code[0] in "123456789":
        return int(code[0])
    return None


def _wall_allows_gang(context: WindowContext) -> Tuple[bool, Tuple[RuleIssue, ...]]:
    """最后 10 墩（20 张）内禁杠的公共门禁（§6）。

    牌墙剩余未知时无法验证禁杠边界——按 §7 保守方向（宁漏候选不 409）
    返回 False 并附 Issue；已知剩余 > 20 才放行。仅在确有杠牌形状时
    调用本门禁，避免对无杠手牌产生降级噪声。
    """

    if context.remaining_tile_count is None:
        return False, (
            RuleIssue(
                _area("gang"),
                "牌墙剩余张数未知，无法验证最后 20 张禁杠边界，保守不生成杠候选（§6/§7）",
            ),
        )
    if context.remaining_tile_count <= WALL_RESERVE_TILES:
        return False, ()
    return True, ()


def discard_tile_codes(
    context: WindowContext,
) -> Tuple[Tuple[str, ...], Tuple[RuleIssue, ...]]:
    """出牌族的规范合法牌码；供完整候选和批量后继共同消费。

    本函数拥有抓打圈与摸牌窗口的出牌合法性，返回牌码而不分配动作、
    证据或候选对象。调用方不得再实现一套出牌合法性。
    """

    if not _own_draw(context):
        return (), ()
    if context.catch_play:
        if context.drawn_tile is None:
            return (), (
                RuleIssue(
                    _area("discard"),
                    "抓打圈但刚摸牌缺失，无法确定唯一可出的刚摸牌（§6）",
                ),
            )
        return (context.drawn_tile.code,), ()
    full_hand = context.full_hand()
    if not full_hand:
        return (), ()
    counts = counts_from_tiles(full_hand)
    return tuple(
        TILE_ORDER[index] for index, count in enumerate(counts) if count > 0
    ), ()


def discard_candidates(context: WindowContext) -> FamilyOutcome:
    """出牌族：本人摸牌窗口的全部合法弃牌候选（§6）。

    【官方】§6：抓打圈内受限座位只能打刚摸到的牌（刚摸牌缺失时无法
    确定唯一合法牌，保守降级并交由紧急路径兜底）；其余情况任意暗牌
    均可打——含刚摸牌与财神（财神可主动打出，§1；是否构成飘由
    special_rules 按爆头状态判定，§8）。候选按 TILE_ORDER 升序、
    每牌值一个，天然去重且确定。
    """

    codes, issues = discard_tile_codes(context)
    if issues or not codes:
        return FamilyOutcome((), issues)
    candidates = []
    for code in codes:
        evidence = [
            "出牌:抓打圈仅可打刚摸的牌 {0}（§6）".format(code)
            if context.catch_play
            else "出牌:摸牌窗口本人回合，暗牌均可打（§6）"
        ]
        if code == WEALTH_CODE:
            evidence.append(
                "出牌:财神可主动打出（§1）；是否构成飘由 special_rules 按爆头状态判定（§8）"
            )
        candidates.append(_candidate(Discard(Tile(code)), tuple(evidence)))
    return FamilyOutcome(tuple(candidates), ())


def chi_candidates(context: WindowContext) -> FamilyOutcome:
    """吃族：吃窗口内用两张手牌与触发弃牌组成顺子的全部候选（§6）。

    【官方】§1/§6：财神不能被吃，且吃的两张手牌不得含白——按精确
    牌值组顺天然排除白（白不作顺子替身）；吃最多 2 摊（按本人吃副露
    计数）；碰（含明杠）窗口先于吃窗口，response_peng 阶段不产生吃
    候选；抓打圈内其余玩家不能吃。数牌才可能组顺，字牌无候选。
    候选按顺子起始牌升序（等价 TILE_ORDER 序），同形状多副本只出一个。
    """

    if not _responding(context, _RESPONSE_CHI):
        return _EMPTY
    if context.catch_play:
        # 本座为非圈主或归属未知时禁吃碰明杠；已知圈主不走本分支。
        return _EMPTY
    last = context.last_discard
    if last is None:
        return FamilyOutcome(
            (),
            (RuleIssue(_area("chi"), "吃窗口缺少触发弃牌，观察不完整（§6）"),),
        )
    if last.seat == context.seat:
        return FamilyOutcome(
            (),
            (RuleIssue(_area("chi"), "触发弃牌来自本人，与响应窗口语义矛盾"),),
        )
    discarded = last.tile
    if is_wealth(discarded):
        return _EMPTY  # 财神不能被吃（§1）。
    if context.my_chi_count >= MAX_CHI_MELDS:
        return _EMPTY  # 吃最多 2 摊（§6）。
    number = _number_of_code(discarded.code)
    if number is None:
        return _EMPTY  # 字牌不能组顺子（§1 牌系统）。
    suit = discarded.code[1]
    hand_counts = counts_from_tiles(context.full_hand())
    candidates = []
    for low in (number - 2, number - 1, number):
        if low < 1 or low + 2 > 9:
            continue
        run_codes = (
            "{0}{1}".format(low, suit),
            "{0}{1}".format(low + 1, suit),
            "{0}{1}".format(low + 2, suit),
        )
        partners = [code for code in run_codes if code != discarded.code]
        if any(hand_counts[TILE_INDEX[code]] < 1 for code in partners):
            continue
        evidence = (
            "吃:{0} 顺子含被吃 {1}；本人吃摊 {2}/{3}（§6）".format(
                "".join(run_codes), discarded.code, context.my_chi_count, MAX_CHI_MELDS
            ),
        )
        candidates.append(
            _candidate(
                Chi((Tile(run_codes[0]), Tile(run_codes[1]), Tile(run_codes[2]))),
                evidence,
            )
        )
    return FamilyOutcome(tuple(candidates), ())


def peng_candidates(context: WindowContext) -> FamilyOutcome:
    """碰族：碰窗口内暗牌持有至少两张同牌值的碰候选（§6）。

    【官方】§1/§6：财神不能被碰（白不作碰替身，按精确牌值计数）；
    碰（含明杠）窗口先于吃窗口，response_chi 阶段不再产生碰候选；
    抓打圈内其余玩家不能碰。响应座位不含本人时无窗口。
    """

    if not _responding(context, _RESPONSE_PENG):
        return _EMPTY
    if context.catch_play:
        return _EMPTY  # 抓打圈：圈内不能吃/碰/明杠（§6）。
    last = context.last_discard
    if last is None:
        return FamilyOutcome(
            (),
            (RuleIssue(_area("peng"), "碰窗口缺少触发弃牌，观察不完整（§6）"),),
        )
    if last.seat == context.seat:
        return FamilyOutcome(
            (),
            (RuleIssue(_area("peng"), "触发弃牌来自本人，与响应窗口语义矛盾"),),
        )
    discarded = last.tile
    if is_wealth(discarded):
        return _EMPTY  # 财神不能被碰（§1）。
    hand_counts = counts_from_tiles(context.full_hand())
    held = hand_counts[TILE_INDEX[discarded.code]]
    if held < 2:
        return _EMPTY
    evidence = ("碰:暗牌持有 {0} ×{1}（§6）".format(discarded.code, held),)
    return FamilyOutcome((_candidate(Peng(discarded), evidence),), ())


def gang_candidates(context: WindowContext) -> FamilyOutcome:
    """杠族：暗杠 / 明杠 / 补杠三类候选（§6）。

    【官方】§1/§6：

    - 暗杠（concealed）：本人摸牌窗口、暗牌 4 张同一自然牌；抓打圈内
      仍允许（"仅暗杠与自摸胡"）；白不参与任何杠。
    - 明杠（exposed）：碰响应窗口、暗牌 3 张 + 被弃牌；抓打圈内禁止。
    - 补杠（added）：本人摸牌窗口、已有碰副露牌值 + 暗牌持有第 4 张；
      不是暗杠，按"仅暗杠"原文在抓打圈内一并禁止。
    - 公共约束：最后 10 墩（20 张）内禁止杠牌；牌墙剩余未知时按 §7
      保守方向不生成并记 Issue（仅在实际存在杠形状时，避免噪声）。
    """

    if _own_draw(context):
        counts = counts_from_tiles(context.full_hand())
        concealed = []
        for index, count in enumerate(counts):
            code = TILE_ORDER[index]
            if count == 4 and code != WEALTH_CODE:
                evidence = ("杠:暗杠自然四张 {0}（§6；白不参与任何杠，§1）".format(code),)
                concealed.append(
                    _candidate(Gang(Tile(code), GangKind.CONCEALED), evidence)
                )
        added = []
        if not context.catch_play:
            for code in dict.fromkeys(context.my_peng_codes):
                if code == WEALTH_CODE:
                    # 防御：财神不可能被碰，出现即上游数据污染，跳过该值。
                    continue
                if counts[TILE_INDEX[code]] >= 1:
                    evidence = (
                        "杠:补杠已有 {0} 碰副露且暗牌持有第 4 张（§6；抓打圈内禁止，§6）".format(
                            code
                        ),
                    )
                    added.append(_candidate(Gang(Tile(code), GangKind.ADDED), evidence))
        shapes = concealed + added
        if not shapes:
            return _EMPTY
        allowed, issues = _wall_allows_gang(context)
        if not allowed:
            return FamilyOutcome((), issues)
        return FamilyOutcome(tuple(shapes), ())
    if _responding(context, _RESPONSE_PENG):
        if context.catch_play:
            return _EMPTY  # 抓打圈：圈内不能明杠（§6）。
        last = context.last_discard
        if last is None:
            return FamilyOutcome(
                (),
                (RuleIssue(_area("gang"), "碰窗口缺少触发弃牌，明杠无法判定（§6）"),),
            )
        if last.seat == context.seat:
            return FamilyOutcome(
                (),
                (RuleIssue(_area("gang"), "触发弃牌来自本人，与响应窗口语义矛盾"),),
            )
        discarded = last.tile
        if is_wealth(discarded):
            return _EMPTY  # 财神不能被杠（§1）。
        hand_counts = counts_from_tiles(context.full_hand())
        if hand_counts[TILE_INDEX[discarded.code]] < 3:
            return _EMPTY
        allowed, issues = _wall_allows_gang(context)
        if not allowed:
            return FamilyOutcome((), issues)
        evidence = (
            "杠:明杠响应窗口暗牌 3 张 {0} + 被弃牌（§6；碰窗口先于吃窗口）".format(
                discarded.code
            ),
        )
        return FamilyOutcome(
            (_candidate(Gang(discarded, GangKind.EXPOSED), evidence),), ()
        )
    return _EMPTY


def hu_candidates(
    context: WindowContext, hand: Optional[HandSummary] = None
) -> FamilyOutcome:
    """胡族：本人摸牌窗口、刚摸牌存在且完整手牌成胡时的自摸胡候选（§2/§6）。

    【官方】§2/§6：只能自摸、不允许点炮、禁止抢杠胡——响应窗口永不
    产生胡候选；抓打圈内仍可自摸胡。胡牌形判定复用手牌数学
    （`HandSummary.is_win`，摸牌含在内），本模块不复制分解算法。

    【官方】「刚摸牌」门禁（指南变更日志 v1，2026-09-02「碰后禁止胡牌」；
    API 记录 §2.4「碰、吃、杠后，在下一次摸牌之前提交 hu 会返回 409」）：
    - 碰/吃/杠之后、下次摸牌之前，官方拒绝提交 hu（409 INVALID_ACTION）。
      该窗口在快照上仍是 draw ∧ turn=me（出牌窗口），但 drawn_tile 为空——
      阶段判定无法区分，必须显式建模：drawn_tile is None 时本族不产生
      胡候选（规则性关闭而非降级，不记 Issue）。
    - 杠后补牌（杠上摸）属于「已摸牌」：杠的补牌以 tile_drawn 事件与
      非空 drawn_tile 呈现（杠开场景），门禁应正确放行。
    - 庄家首局「发牌直抽」的第 14 张同样以 drawn_tile 呈现
      （2026-09-04 实测，b6_t40 r1 首窗口审计），不受本门禁影响。

    YouCaiBiKao（§7）不在本族判断：需要 RuleConfig、爆头状态与杠上
    摸牌推断，由 special_rules/engine 在候选产出后过滤。hand 缺失
    （手牌分析未就绪或上游降级）时保守降级并记 Issue，不伪造胡候选。
    """

    if not _own_draw(context):
        return _EMPTY
    if context.drawn_tile is None:
        # 「刚摸牌」门禁（指南变更日志 v1）：碰/吃/杠后、摸牌前提交
        # hu 官方返回 409 INVALID_ACTION；drawn_tile 为空即本窗口
        # 未发生摸牌，胡候选按规则性关闭（详见函数 docstring）。
        # 注意：门禁早退先于下方 hand is None 的降级簿记（有意为之——
        # 本窗口本就无胡候选，无需 hu 族降级噪声；手牌分析异常另有
        # engine.hand_analysis Issue 覆盖）。勿调整两分支顺序。
        return _EMPTY
    if hand is None:
        return FamilyOutcome(
            (),
            (
                RuleIssue(
                    _area("hu"),
                    "缺少手牌分析 HandSummary，胡牌族保守降级（§9 故障隔离）",
                ),
            ),
        )
    if not hand.is_win:
        return _EMPTY
    evidence = (
        "胡:自摸胡成胡，判定来自手牌数学 is_win（§2/§6；只能自摸、无点炮）",
    ) + hand.evidence
    return FamilyOutcome((_candidate(Hu(), evidence),), ())


def pass_candidates(context: WindowContext) -> FamilyOutcome:
    """过族：两个响应窗口内的放弃候选（§6）；摸牌窗口必须行动，无过。"""

    if _responding(context, _RESPONSE_PENG) or _responding(context, _RESPONSE_CHI):
        evidence = ("过:响应窗口放弃当前响应机会（§6）",)
        return FamilyOutcome((_candidate(Pass(), evidence),), ())
    return _EMPTY


_FAMILY_GENERATORS: Dict[str, Callable[[WindowContext], FamilyOutcome]] = {
    "discard": discard_candidates,
    "chi": chi_candidates,
    "peng": peng_candidates,
    "gang": gang_candidates,
    "pass": pass_candidates,
}
"""无额外输入的五个族生成器；胡族需要 HandSummary，由组合器单独传参。"""


def generate_candidates(
    context: WindowContext, hand: Optional[HandSummary] = None
) -> FamilyOutcome:
    """组合器：按 FAMILY_ORDER 聚合六族候选，逐族异常隔离（§9）。

    单族抛出的任何异常收敛为该族 RuleIssue（异常类型与消息写入
    reason，不吞异常），其余族照常产出——engine 只需把结果映射进
    RuleAnalysis 并对 issues 非空标记 DEGRADED。结果顺序与内容对
    相同输入逐字节一致（确定性性质测试覆盖）。
    """

    candidates = []
    issues = []
    for family in FAMILY_ORDER:
        try:
            if family == "hu":
                outcome = hu_candidates(context, hand)
            else:
                outcome = _FAMILY_GENERATORS[family](context)
        except Exception as exc:  # 故障边界：见模块 docstring 与 §9。
            issues.append(
                RuleIssue(
                    _area(family),
                    "动作族 {0} 分析异常: {1}: {2}".format(
                        family, type(exc).__name__, exc
                    ),
                )
            )
            continue
        candidates.extend(outcome.candidates)
        issues.extend(outcome.issues)
    return FamilyOutcome(tuple(candidates), tuple(issues))
