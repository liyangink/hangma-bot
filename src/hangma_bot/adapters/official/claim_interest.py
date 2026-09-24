"""鸣牌兴趣预过滤：只决定"是否值得拉一次权威快照"，不判断合法性。

2026-09-17 测试赛复盘（review/test-tournament-20260917/REPORT.md §8.2/§9.3）：
每用户 16 次/秒的 state 配额中约 34.5% 被"每次弃牌/每个窗口边界必刷一次
全量快照"消耗，而其中绝大多数响应窗与我校无关——零动作窗可鸣率 4.07%，
已规划响应窗可鸣率 6.04%。本模块用"我方暗牌保守超集 + 弃牌公开事实"
做兴趣判定，让无关弃牌周期完全走增量事件：

- 假阳性（判有兴趣而实际没有）只多花一次 GET，方向安全；
- 假阴性为零的关键是手牌口径只增不减：本人弃牌/副露让真实暗牌变少，
  超集自动偏保守；本人新摸牌必须并入（见 sync_state._own_hand_superset），
  摸牌身份未知时整体退回"有兴趣"。

合法动作判定唯一属于 hangma（模块 AGENTS：适配器不得实现第二套合法性
判断）；本模块的输出只用于"是否多拉一次快照"，任何候选、提交与紧急
路径都不经过它。

规则口径来源与漂移义务：财神不可被吃/碰/杠来自 hangma/RULES_EVIDENCE.md
§1；吃仅来自上家、碰需持对来自接口协议 §6 的吃碰语义。上述口径若随
官方指南修订变化，必须同步修改本文件与 test_claim_interest.py——本
模块是口径的保守超集镜像，不是规则真值。
"""

from typing import Optional, Sequence

WEALTH_GOD_CODE = "白"
"""财神牌码：不能被吃/碰/杠（RULES_EVIDENCE §1），直接排除。"""

_SUIT_SUFFIXES = ("w", "b", "t")


def _rank(tile_code: str) -> Optional[tuple]:
    """数牌返回 (花色后缀, 点数 1-9)；字牌/畸形牌码返回 None。"""

    if len(tile_code) != 2:
        return None
    suit, digit = tile_code[1], tile_code[0]
    if suit not in _SUIT_SUFFIXES or digit not in "123456789":
        return None
    return (suit, int(digit))


def chi_shape_superset(tile_code: str, hand_codes: Sequence[str]) -> bool:
    """在暗牌保守超集里查完整吃搭；不把它当作合法动作判定。

    真实暗牌始终包含于传入的 hand_codes；若真实暗牌有两张成搭，超集
    中也必有这两张。因此要求两张齐全仍无假阴性，并可排除只有一张邻牌
    的假兴趣。财神、抓打圈及未知暗牌由调用方另行保守处理。
    """

    target = _rank(tile_code)
    if target is None:
        return False  # 字牌不能组成顺子
    suit, digit = target
    held = set(hand_codes)
    return any(
        1 <= left <= 9 and 1 <= right <= 9
        and f"{left}{suit}" in held and f"{right}{suit}" in held
        for left, right in ((digit - 2, digit - 1), (digit - 1, digit + 1),
                            (digit + 1, digit + 2))
    )


def discard_interesting(
    *,
    my_seat: Optional[int],
    discarder_seat: Optional[int],
    tile_code: str,
    hand_codes: Optional[Sequence[str]],
) -> bool:
    """一次他家弃牌是否可能给我开碰/明杠/吃响应窗（保守超集）。

    my_seat 或手牌超集不可知（快照缺失、本人摸牌身份未知、抓打圈激活）
    时返回 True：信息不足永远选"拉快照"这一安全侧。
    """

    if my_seat is None or discarder_seat is None or hand_codes is None:
        return True
    if not isinstance(my_seat, int) or not isinstance(discarder_seat, int):
        return True
    if not tile_code:
        return True
    if tile_code == WEALTH_GOD_CODE:
        return False  # 财神不能被吃/碰/杠，弃财神不可能给我开响应窗
    if list(hand_codes).count(tile_code) >= 2:
        return True  # 碰（≥2 张）；明杠（≥3 张）被同一超集覆盖
    if discarder_seat == (my_seat - 1) % 4 and chi_shape_superset(tile_code, hand_codes):
        return True  # 只有上家弃牌可能被吃
    return False
