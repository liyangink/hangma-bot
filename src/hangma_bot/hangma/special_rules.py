"""财神特殊状态、抓打圈、爆头与动作链的纯规则判定。

本文件属于「财神与结算」子模块：提供财神（白板）动作限制、抓打圈
（Catch-play State）硬约束、爆头静态判定、有财必拷响（YouCaiBiKao）
与动作链延续性的纯函数。全部函数不访问网络、文件、时钟或随机源；
通用牌型分解由 hand_analysis 产出 `WinSplit` 后传入，本文件不实现
第二套分解；动作候选的生成见 action_families。

规则依据与证据级别：`RULES_EVIDENCE.md` §1/§5/§6/§7/§8
（官方指南 v9，2026-09-03 抓取；金例夹具 tests/fixtures/official/v9）。
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
    """确认仅表态、不会代替本人出牌的事件；未知 timeout 不能视为无副作用。

    官方 v15 归档的响应超时为 data.kind=response；kind=discard 是自动
    弃牌后的通知。缺 kind 或新增 kind 尚无法排除自动动作，必须保留未知。
    """
    return event.kind == "pass" or (
        event.kind == "timeout" and event.detail_kind == "response"
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
    - 本人出牌只能打刚摸到的牌 `drawn_tile`；
    - 本人仍可暗杠和自摸胡。

    边界约定：补杠（ADDED）不是暗杠，按「仅暗杠」原文一并禁止；
    `drawn_tile` 缺失时对 `Discard` 保守拒绝（无法核对=不能出），
    宁可少一个候选也不提交非法动作。抓打圈优先级高于任何策略偏好，
    由调用方用 `observation.rule_state.catch_play` 决定是否调用本函数。
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


def static_baotou(win: WinSplit) -> bool:
    """爆头静态判定（金例对拍与审计口径）。

    【官方】§5：爆头 ⟺ 摸牌前 13 张暗牌 + 任意一张牌都胡
    （`WinSplit.any_tile_tenpai`，由 hand_analysis 按指南 1.2 判定）
    ∧ 胡牌时手留白板数 ≠ 4（正好 4 张白板不视为爆头）。

    运行时结算优先使用 `observation.rule_state.baotou` 平台权威
    状态；本函数仅用于金例对拍、审计复核与 YouCaiBiKao 推断。

    【集成契约警示】hand_analysis.win_split 在 14 张口径下无法判定
    「摸牌前 13 张 + 任意一张」，返回的 `any_tile_tenpai` 恒为 False
    占位；对拍/审计调用方必须先用 `any_tile_win(摸牌前 13 张,
    meld_set_count)` 的结果 `dataclasses.replace` 覆盖该字段再传入——
    遗忘覆盖时本函数恒 False（YouCaiBiKao 走保守漏胡方向、审计番数
    漏记爆头 ×2，错误方向安全但不可 silently 当作已判定）。
    """

    return win.any_tile_tenpai and win.whites_held != 4


def you_cai_bi_kao_block(
    you_cai_bi_kao: bool, win: WinSplit, baotou: bool, gang_draw: bool
) -> Optional[str]:
    """有财必拷响（YouCaiBiKao）胡牌限制；None 表示允许胡，否则返回原因。

    【官方语义】指南 1.6：手上有财神时不允许平胡，必须爆头/杠开才能胡；
    fan-calc 工具不强制该规则（youcai-plain-hu-shape 金例 hu=true），
    合法性由本地按 `RuleConfig.you_cai_bi_kao` 判定。

    【假设】§7："平胡"按分支理解——开关开启 ∧ 手留白板 ≥ 1 时，
    胡候选仅当（爆头判定为真 ∨ 杠上摸牌）。七对分支是否豁免未确认，
    保守起见同样要求爆头/杠开（宁漏胡不 409）。被排除时调用方应记录
    RuleIssue，而非静默丢弃。

    参数：
      baotou：运行时传平台权威 `rule_state.baotou`，对拍可传
        `static_baotou(win)`；
      gang_draw：是否杠上摸牌（本人杠后紧跟本人摸牌），见
        `is_gang_draw`。
    """

    if not you_cai_bi_kao or win.whites_held == 0:
        return None
    if baotou or gang_draw:
        return None
    return (
        "有财必拷响：手留财神 {0} 张且分支 {1}，须爆头或杠上摸牌方可胡"
        "（七对分支按保守假设同样受限）".format(win.whites_held, win.branch)
    )


def is_gang_draw(public_history: Tuple[PublicEvent, ...], seat: int) -> bool:
    """按公共历史推断当前手牌是否为杠后补牌（杠上摸牌）。

    【假设】§7：杠上摸牌由公共历史最近事件推断——本人 `gang` 事件
    紧跟（seq 相邻，即 previous.seq == draw.seq - 1）本人 `tile_drawn`
    事件。取本人最近一次摸牌事件判定：若其紧前事件不是本人的杠、或
    序号存在缺口（中间丢失事件），则视为普通摸牌。未知事件夹在中间
    或序号不连续时一律判 False（保守；杠开豁免宁严勿宽，配合
    YouCaiBiKao 的宁漏胡不 409 方向）。

    该推断只用于合法性豁免与审计；不影响番数（链计数以平台为准）。
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
