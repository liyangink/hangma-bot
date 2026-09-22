"""财神特殊状态、抓打圈、爆头与动作链的纯规则判定。

本文件属于「财神与结算」子模块：提供财神（白板）动作限制、抓打圈
（Catch-play State）硬约束、爆头静态判定、有财必拷响（YouCaiBiKao）
与动作链延续性的纯函数。全部函数不访问网络、文件、时钟或随机源；
通用牌型分解由 hand_analysis 产出 `WinSplit` 后传入，本文件不实现
第二套分解；动作候选的生成见 action_families。

规则依据与证据级别：`RULES_EVIDENCE.md` §1/§5/§6/§7/§8
（官方指南 v9，2026-09-03 抓取；金例夹具 tests/fixtures/official/v9）；
有财必拷响另按 2026-09-07 用户确认及测试房拒胡事实修正规则解释。
四白爆头按官方指南 v23 §1.2 与 2026-09-08 fan-calc 实测修正；
旧版四白例外不再覆盖已经成立的爆头。
"""

from __future__ import annotations

from typing import Optional, Tuple

from hangma_bot.kernel.actions import (
    Action,
    Chi,
    Discard,
    Gang,
    GangKind,
    Peng,
    Tile,
)
from hangma_bot.kernel.observation import PublicEvent

from .internal_types import WinSplit, is_wealth

# 官方事件 type 原样透传值（doc/official-platform-api-v2.md §2.3）。
# 未知事件允许透传记录；以下常量只用于本模块的历史推断，不做枚举封闭。
EVENT_KIND_DRAWN = "tile_drawn"
EVENT_KIND_DISCARDED = "tile_discarded"
EVENT_KIND_GANG = "gang"


def is_passive_observation_event(event: PublicEvent) -> bool:
    """确认仅表态、不改变规则状态的事件；timeout 两类均为窗口生命周期记账。

    官方指南 v34（2026-09 抓取）§超时兜底：吃/碰窗口"固定走满"（防时间侧信道）；
    出牌思考超时由服务端"自动打出最右一张牌"，代打动作本身以紧邻的
    ``tile_discarded`` 事件进入公开流。2026-09-23 两房实测（a_55f18ee75775
    7 例、a_e2b2d94b31c1 17 例）：timeout(kind=discard) 全部与同座位紧邻
    ``tile_discarded`` 成对出现，含本人压线主动提交的同构场景，因此该事件
    不携带独立规则信息，与 response 类同为被动观察事件。
    缺 kind 或未来新增 kind 仍不能排除自动动作，必须保留未知。
    """
    return event.kind == "pass" or (
        event.kind == "timeout" and event.detail_kind in ("response", "discard")
    )


def wealth_action_restriction(action: Action) -> Optional[str]:
    """财神对单个动作的硬限制；返回 None 表示不受限，否则返回可审计原因。

    【官方】指南 1.1/1.6 与 §6：财神（白）本身不能被吃、碰、杠——
    - 吃：被吃牌与两张手牌组成 `Chi.tiles`，任一张为白即非法
      （财神不能被吃，且吃的两张手牌不得含白）；
    - 碰：`Peng.tile` 为白即非法；
    - 杠：白不参与任何杠（含暗杠与补杠），三类 `GangKind` 一视同仁；
    - 打出：财神可主动打出（飘的前提），`Discard` 恒不受本条限制；
    - 胡/过：不受本条限制（只能自摸胡，白作百搭正常参与胡牌）。

    本函数只判定财神限制，不判断窗口归属、牌张数等通用合法性，
    调用方（engine/action_families）须先满足各自的通用约束。
    """

    if isinstance(action, Chi):
        for tile in action.tiles:
            if is_wealth(tile):
                return "财神不能被吃：吃牌组合（含被吃牌与两张手牌）不得含白板"
    elif isinstance(action, Peng):
        if is_wealth(action.tile):
            return "财神不能被碰"
    elif isinstance(action, Gang):
        if is_wealth(action.tile):
            return "财神不参与任何杠（含暗杠与补杠）"
    return None


def catch_play_restriction(
    action: Action, drawn_tile: Optional[Tile]
) -> Optional[str]:
    """抓打圈（Catch-play State）内单个动作的硬约束；None 表示不受限。

    【官方】指南 1.1 与 API §5.4：打出财神触发的抓打圈中——
    - 其余玩家不能吃、碰、明杠（仅暗杠与自摸胡）；
    - 受限座位出牌只能打刚摸到的牌 `drawn_tile`；
    - 受限座位仍可暗杠和自摸胡；当前圈主不直接套用这些限制。

    边界约定：补杠（ADDED）不是暗杠，按「仅暗杠」原文一并禁止；
    `drawn_tile` 缺失时对 `Discard` 保守拒绝（无法核对=不能出），
    宁可少一个候选也不提交非法动作。抓打圈优先级高于任何策略偏好，
    调用方须先经 catch_play.analyze_catch_play 结合圈主判定本座是否受限，
    不能直接用 observation.rule_state.catch_play 全局标记调用本函数。
    """

    if isinstance(action, Discard):
        if drawn_tile is None:
            return "抓打圈出牌只能打刚摸到的牌，但本窗口缺少摸牌信息"
        if action.tile.code != drawn_tile.code:
            return "抓打圈出牌只能打刚摸到的牌"
        return None
    if isinstance(action, (Chi, Peng)):
        return "抓打圈期间不能吃、碰（其余玩家仅暗杠与自摸胡）"
    if isinstance(action, Gang):
        if action.kind is GangKind.CONCEALED:
            return None
        return "抓打圈期间仅允许暗杠（明杠、补杠均禁止）"
    return None  # 自摸胡与过不受抓打圈额外限制


def is_piao_discard(tile: Tile, baotou: bool) -> bool:
    """判断一次弃牌是否构成飘（爆头状态下打出财神）。

    【官方】§8：飘 = 爆头状态下打出财神，继续听任意牌；连续打出
    财神累积财飘。非爆头态打出白板不是飘（且会断链）。
    `baotou` 运行时取 `observation.rule_state.baotou`（平台权威）。
    """

    return baotou and is_wealth(tile)


def chain_breaks_on_discard(tile: Tile, baotou: bool) -> bool:
    """判断一次弃牌是否打断动作链（God Chain）；杠不断链。

    【官方】指南 1.3：打出非飘非杠的牌 → 链断重新计数；非爆头态
    打出白板同样属于「非飘非杠」的普通弃牌，链断清零。杠（任意种类）
    每次使链计数 +1，不经过本函数；运行时链计数以
    `observation.rule_state.chain_count` 为权威，本函数用于审计与
    模拟器推进。
    """

    return not is_piao_discard(tile, baotou)


def four_white_indicator(whites_held: Optional[int],
                         chain_piao: Optional[int]) -> Optional[bool]:
    """官方「4 个白板」指示：**手留白 + 链内飘出恰好等于 4**。

    【官方】指南 v34 §1.3（2026-09-14 抓取）：「胡牌时手牌留存 + 链内飘出的白板 = 4
    （**正好 4 张**；普通打出的、杠出的不算）」→ ×2。

    **这是等值条件，不是单调量**：留 2 张不算、留 4 张算、留 3 张 + 链内飘 1 张也算。
    把它写成"白板越多越好"是错的（README §14.1 M-2 的反例同源）。

    任一输入未知时返回 None——**空与 0 必须区分，未知不填 False**；
    数值越界只可能是上游装配错误，立即失败而不是静默夹取。
    """

    if whites_held is None or chain_piao is None:
        return None
    for name, value in (("whites_held", whites_held), ("chain_piao", chain_piao)):
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError(
                "four_white_indicator.{0} 必须是 0-4 的整数，得到 {1!r}".format(
                    name, value))
    return whites_held + chain_piao == 4


def static_baotou(win: WinSplit) -> bool:
    """爆头静态判定（金例对拍与审计口径）。

    【官方 v23，2026-09-08 对拍】爆头 ⟺ 摸牌前暗牌 + 任意一张
    物理可得的牌都胡（`WinSplit.any_tile_tenpai`，由 hand_analysis
    按指南 1.2 判定）。手留四白同样按任意听判断，四白本身不保证爆头；
    指南旧计番表仍有“四白除外”字样，以 v23 fan-calc 实测为准。

    运行时结算优先使用 `observation.rule_state.baotou` 平台权威
    状态；本函数仅用于金例对拍、审计复核与 YouCaiBiKao 推断。

    【集成契约警示】hand_analysis.win_split 在 14 张口径下无法判定
    「摸牌前 13 张 + 任意一张」，返回的 `any_tile_tenpai` 恒为 False
    占位；对拍/审计调用方必须先用 `any_tile_win(摸牌前 13 张,
    meld_set_count)` 的结果 `dataclasses.replace` 覆盖该字段再传入——
    遗忘覆盖时本函数恒 False（YouCaiBiKao 走保守漏胡方向、审计番数
    漏记爆头 ×2，错误方向安全但不可 silently 当作已判定）。
    """

    return win.any_tile_tenpai


def you_cai_bi_kao_block(
    you_cai_bi_kao: bool, win: WinSplit, baotou: bool
) -> Optional[str]:
    """成牌后叠加赛局的有财必拷响限制；None 表示本条不拦截。

    【用户确认，2026-09-07】开关开启且手留财神时必须爆头，普通杠开
    不豁免；七对和豪华七对同样适用。测试房两次有财、非爆头的杠补
    成牌被官方拒绝，与此口径一致。fan-calc 只判成牌、爆头与番数，
    因此其 hu=true 必须再叠加实际 `RuleConfig.you_cai_bi_kao`。

    【官方 v23，2026-09-08 对拍】手留四白也可以爆头；本函数消费
    已确认的爆头事实，不因白板数量重新否定。四白非爆头仍受开关限制。
    开关关闭或手中无财神时，此规则不限制已由调用方确认的成牌。

    参数：
      baotou：运行时传平台权威 `rule_state.baotou`，对拍可传
        `static_baotou(win)`；
      you_cai_bi_kao：当前赛局配置，不得因历史房间开启而写死为 True。

    本函数不重做通用成牌判断，也不计算番数；无副作用。
    被排除时调用方保留可审计原因。
    """

    if not you_cai_bi_kao or win.whites_held == 0:
        return None
    if baotou:
        return None
    return (
        "有财必拷响：手留财神 {0} 张且分支 {1}，必须爆头才能胡；"
        "杠补不豁免".format(win.whites_held, win.branch)
    )


def is_gang_draw(public_history: Tuple[PublicEvent, ...], seat: int) -> bool:
    """按公共历史推断最近一次本人摸牌是否为杠后补牌，供历史审计使用。

    【假设】§7：杠上摸牌由公共历史最近事件推断——本人 `gang` 事件
    紧跟（seq 相邻，即 previous.seq == draw.seq - 1）本人 `tile_drawn`
    事件。取本人最近一次摸牌事件判定：若其紧前事件不是本人的杠、或
    序号存在缺口（中间丢失事件），则视为普通摸牌。未知事件夹在中间
    或序号不连续时一律判 False（仅表示无法从历史确认杠补来源）。

    该结果不是胡牌资格豁免，也不代表当前窗口仍是摸牌窗口；运行时
    当前摸牌来源优先使用官方事件事实，番数使用平台链计数。
    """

    last_draw_index = -1
    for index in range(len(public_history) - 1, -1, -1):
        event = public_history[index]
        if event.seat == seat and event.kind == EVENT_KIND_DRAWN:
            last_draw_index = index
            break
    if last_draw_index <= 0:
        return False
    draw_event = public_history[last_draw_index]
    previous = public_history[last_draw_index - 1]
    return (
        previous.kind == EVENT_KIND_GANG
        and previous.seat == seat
        and previous.seq == draw_event.seq - 1
    )
