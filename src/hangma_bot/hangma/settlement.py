"""财神链推断、番数公式与四家结算（审计与对拍路径）。

实现指南 1.3/1.4 的计分语义：

- 总番 = 分支因子 × 2^动作链次数 ×（白板总数=4 ? ×2）×（爆头 ? ×2）；
- 得分 = 底分 × 总番 ×（庄家 ×8 / 闲家 ×1），庄家倍率恒 ×8（直上
  三连庄，无 ×2/×4 递增），四家支付总分守恒。

通用牌型分解（分支与豪华组数）由 hand_analysis 产出 `WinSplit` 后
传入，本文件不实现第二套分解。全部函数为纯函数：不访问网络、文件、
时钟或随机源；历史推断仅遍历调用方传入的 `public_history`。

规则依据与证据级别：`RULES_EVIDENCE.md` §3/§4/§8（官方指南 v9，
2026-09-03 抓取；61 例成胡金例 + 反例与 400 校验全部复核）。
四白与爆头叠加按官方指南 v23 §1.2 与 2026-09-08 fan-calc 实测修正。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from hangma_bot.kernel.actions import SEAT_COUNT
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent, ScoreVector

from .interface import Settlement
from .internal_types import WinSplit, is_wealth
from .special_rules import four_white_indicator, is_passive_observation_event

_BRANCH_PLAIN = "平胡"
_BRANCH_CHIITOI = "七对"
_WHITE_TOTAL_DETAIL = "4个白板"
_BAOTOU_DETAIL = "爆头"


@dataclass(frozen=True)
class FanResult:
    """一次番数计算的确定结果；`details` 与官方 fan-calc 明细逐字一致。"""

    fan: int  # 总番；流局不经本路径，调用方直接以番 0 结算
    details: Tuple[str, ...]  # 明细顺序固定：分支 → 动作链 → 4 白板 → 爆头


def infer_piao_count(
    public_history: Tuple[PublicEvent, ...], seat: int, chain_count: int,
    consumed_seq: Optional[int] = None,
) -> Optional[int]:
    """用权威链次数约束连续历史后缀，精确求链内飘次数；缺证据返回 None。

    官方指南 v18（2026-09-06）§1.3：飘/杠各累计一次，普通弃牌断链。
    按 RULES_EVIDENCE.md 的 v18 生命周期修订，吃碰保持已有链，不增加
    次数；反查必须跨过它们，不能把合法吃碰误当断链或历史缺失。
    从当前已消费水位反向找最近 chain_count 次本人白弃/杠；官方非零链
    计数约束其中白弃属于飘。收齐前遇断点不能借旧链补数。
    """
    if chain_count == 0:
        return 0
    if consumed_seq is None or not public_history:
        return None
    expected = consumed_seq
    found = piao = 0
    harmless = {"tile_drawn", "tile_discarded", "gang", "chi", "peng", "pass", "timeout"}
    for event in reversed(public_history):
        if event.seq != expected or event.kind not in harmless:
            return None
        expected -= 1
        if event.kind == "timeout" and not is_passive_observation_event(event):
            return None
        if event.seat != seat:
            continue
        if event.kind == "gang":
            found += 1
        elif event.kind == "tile_discarded":
            if len(event.tiles) != 1 or not is_wealth(event.tiles[0]):
                return None
            found += 1
            piao += 1
        if found == chain_count:
            return piao
    return None


def _validate_chain(chain_count: int, piao: int, whites_held: int) -> None:
    """链参数的廉价结构校验；非法输入立即失败，不产出臆造番数。"""

    for name, value in (("chain_count", chain_count), ("piao", piao)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("{0} 必须是非负整数，得到 {1!r}".format(name, value))
    if piao > chain_count:
        raise ValueError(
            "chain.piao（{0}）不能超过 chain.count（{1}）".format(piao, chain_count)
        )
    # 与官方 fan-calc 400 校验同口径：白板总数（手留 + 链内飘出）≤ 4。
    if whites_held + piao > 4:
        raise ValueError(
            "白板总数（手留 + 链内飘出）不能超过 4（136 张中白板共 4 张）"
        )


def _chain_detail(count: int, piao: int) -> str:
    """动作链明细命名（与官方 detail 逐字一致，金例核对）。

    命名表【官方】§3 + 金例 chain-4-4：count=1,piao=0 → 杠开；count≥2,piao=0 →
    连杠×N；piao=1/2/3 且 piao=count → 财飘/双财飘/三财飘；piao=count≥4 →
    连飘×N；count>piao≥1 → 杠飘链×N（N=count）。
    """

    if piao == 0:
        if count == 1:
            return "杠开"
        return "连杠×{0}".format(count)
    if piao == count:
        if piao == 1:
            return "财飘"
        if piao == 2:
            return "双财飘"
        if piao == 3:
            return "三财飘"
        return "连飘×{0}".format(count)
    return "杠飘链×{0}".format(count)


def compute_fan(
    win: WinSplit, chain_count: int, piao: int, baotou: bool
) -> FanResult:
    """按指南 1.3 番数公式计算总番与明细命名。

    参数：
      win：hand_analysis 产出的胡牌分解元数据（分支/豪华组数/手留白板）；
      chain_count：链动作数（飘/杠各计 1）；运行时取
        `rule_state.chain_count`；
      piao：链内飘出白板数；运行时取观察中已确认的链内飘次数，缺失不得估计；
      baotou：爆头标志。运行时传平台权威 `rule_state.baotou`，
        对拍/审计可传 `special_rules.static_baotou(win)`（注意先覆盖
        win_split 的 any_tile_tenpai=False 占位，警示见该函数）；
        它用于全局资格，不等同于七对分支支付资格。七对且旗为真时，
        win.seven_pairs_baotou 必须已由准确摸前13张确认，否则抛 ValueError。
        官方 v35、2026-10-06 fan-calc 同14张不同draw对照确认此区别。
        四白与成立的分支爆头分别 ×2，不按四白数量清除全局旗。

    校验失败抛 ValueError（含官方 400 同口径的白板总数校验）；
    未胡牌不进入本路径，由调用方以流局（番 0）处理。
    """

    if win.branch not in (_BRANCH_PLAIN, _BRANCH_CHIITOI):
        raise ValueError("未知胡牌分支 {0!r}；合法取值：平胡/七对".format(win.branch))
    if isinstance(win.luxury_pairs, bool) or not 0 <= win.luxury_pairs <= 3:
        raise ValueError("豪华七对组数必须在 0-3，得到 {0!r}".format(win.luxury_pairs))
    if win.branch == _BRANCH_PLAIN and win.luxury_pairs > 0:
        raise ValueError("平胡分支不携带豪华七对组")
    if isinstance(win.whites_held, bool) or not 0 <= win.whites_held <= 4:
        raise ValueError("手留白板数必须在 0-4，得到 {0!r}".format(win.whites_held))
    _validate_chain(chain_count, piao, win.whites_held)
    if win.seven_pairs_baotou is not None and type(win.seven_pairs_baotou) is not bool:
        raise ValueError("七对爆头支付资格必须是 bool 或 None")
    paid_baotou = baotou
    if baotou and win.branch == _BRANCH_CHIITOI:
        if win.seven_pairs_baotou is None:
            raise ValueError("七对爆头支付资格未知，需要准确摸前13张上下文")
        paid_baotou = win.seven_pairs_baotou

    details: list = []
    if win.branch == _BRANCH_PLAIN:
        branch_factor = 1
        details.append(_BRANCH_PLAIN)
    else:
        # 七对 ×2；豪华 N 组在七对之上再 ×2^N（N=1,2,3 → ×4/×8/×16）。
        branch_factor = 2 * (1 << win.luxury_pairs)
        if win.luxury_pairs == 0:
            details.append(_BRANCH_CHIITOI)
        else:
            details.append("豪华七对×{0}".format(win.luxury_pairs))

    if chain_count > 0:
        details.append(_chain_detail(chain_count, piao))

    # 单一规则来源：等值条件「手留白 + 链内飘出 == 4」由 special_rules 判定。
    four_white = four_white_indicator(win.whites_held, piao) is True
    if four_white:
        details.append(_WHITE_TOTAL_DETAIL)

    if paid_baotou:
        details.append(_BAOTOU_DETAIL)

    fan = branch_factor
    fan <<= chain_count
    if four_white:
        fan <<= 1
    if paid_baotou:
        fan <<= 1
    return FanResult(fan=fan, details=tuple(details))


def _validate_seat(value: object, field_name: str) -> None:
    """座位下标必须位于 0—3；越界只可能是上游装配错误，立即失败。"""

    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < SEAT_COUNT:
        raise ValueError(
            "{0} 必须是 0-{1} 的座位下标，得到 {2!r}".format(
                field_name, SEAT_COUNT - 1, value
            )
        )


def settle_scores(
    fan: int, base_score: int, winner_seat: int, dealer_seat: int
) -> ScoreVector:
    """四家结算（指南 1.4）；返回按座位 0—3 排列的积分增量向量。

    【官方】§4：得分 = 底分 × 总番 ×（庄家 ×8 / 闲家 ×1），庄家倍率
    恒 ×8（直上三连庄，无递增）——
    - 庄家胡：三个闲家各付 底分×番×8（庄家 +24×番×底）；
    - 闲家胡：庄家付 底分×番×8，另两闲家各付 底分×番×1（胡家
      +10×番×底）；
    - 流局：番 0，无支付（全零向量）。

    总分守恒（性质测试覆盖）：四家增量之和恒为 0。
    """

    if isinstance(fan, bool) or not isinstance(fan, int) or fan < 0:
        raise ValueError("fan 必须是非负整数，得到 {0!r}".format(fan))
    if isinstance(base_score, bool) or not isinstance(base_score, int) or base_score <= 0:
        raise ValueError("base_score 必须是正整数，得到 {0!r}".format(base_score))
    _validate_seat(winner_seat, "winner_seat")
    _validate_seat(dealer_seat, "dealer_seat")

    deltas = [0] * SEAT_COUNT
    if fan == 0:
        return tuple(deltas)

    dealer_amount = base_score * fan * 8  # 庄家侧单价（无论胡家是谁）
    common_amount = base_score * fan  # 闲家对闲家单价
    if winner_seat == dealer_seat:
        deltas[winner_seat] = 3 * dealer_amount
        for seat in range(SEAT_COUNT):
            if seat != winner_seat:
                deltas[seat] = -dealer_amount
    else:
        deltas[winner_seat] = dealer_amount + 2 * common_amount
        deltas[dealer_seat] = -dealer_amount
        for seat in range(SEAT_COUNT):
            if seat != winner_seat and seat != dealer_seat:
                deltas[seat] = -common_amount
    return tuple(deltas)


def settle_win(
    win: WinSplit,
    chain_count: int,
    piao: int,
    baotou: bool,
    base_score: int,
    winner_seat: int,
    dealer_seat: int,
    *,
    pre_draw_hand: Optional[Tuple[Tile, ...]] = None,
    meld_set_count: int = 0,
) -> Settlement:
    """一次胡牌的完整结算便捷入口；供 engine.score 组装公开结果。

    pre_draw_hand 是本人准确摸前暗牌，不含摸牌、他家手牌或未来牌墙；
    meld_set_count 是当时副露面子数。七对且全局爆头为真时必须提供
    该上下文或已核的 WinSplit 支付资格，缺失明确失败，不猜测倍率。
    14张分解缓存不保存13张资格，本入口每次据真实前驱补充元数据。
    流局（番0）不经本路径。函数不访问网络、文件或时钟。
    """

    if baotou and win.branch == _BRANCH_CHIITOI and pre_draw_hand is not None:
        from .hand_analysis import qualify_seven_pairs_baotou

        win = qualify_seven_pairs_baotou(win, pre_draw_hand, meld_set_count)
    result = compute_fan(win, chain_count, piao, baotou)
    return Settlement(
        score_delta=settle_scores(result.fan, base_score, winner_seat, dealer_seat),
        fan=result.fan,
        details=result.details,
    )
