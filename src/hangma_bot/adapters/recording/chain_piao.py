"""记录层补全：把「链内飘出白板数」落成**可归因**的落盘事实（3.6d）。

为什么需要本模块（记录缺口的事实）
==================================
官方 ``god`` 只给 ``baotou`` / ``chain_count`` / ``catch_play`` / ``discarder_seat``，
**不提供 ``chain.piao``**（链内飘出白板数）；它只能由**本人动作史**推导。决策当时的
观察由 ``adapters/official`` 维护（含跨快照核对沿用），但**记录**里看不出归因：

- ``datasets/derived/auto-match-2026-09-06/decisions.jsonl``：3343 行 ``public_history``
  全为空、observation 里没有 ``chain_piao`` 键，于是链状态窗口 0 个可判定；唯一
  ``chain_count=1`` 的窗口被 ``hangma/engine.py`` 按"链历史不足"判 ``DEGRADED`` 排除；
- 2026-09-10 语料（3201 行）：3200 行与规则重推一致，**1 行** ``chain_count=1`` 记 0
  而规则重推为 ``None``（消费水位 1316、历史只到 1314）⇒ 记录里出现了**不可归因的值**。

职责与边界
==========
- 纯函数：不读时钟、不写文件、不访问网络、不持有状态；只消费记录里已有的事实。
- **只用于落盘**：在应用层已经完成决策之后运行，不参与决策、重试、退出或晋级判定。
- 落盘内容 = ``observation.chain_piao`` 归一到可归因推导值（未知写 ``None``）+ 同级
  ``chain_piao_attribution`` 归因块（live 原值、命中档位、命中事件序号、不变量）。
- **绝不填零**：每一档推导都给出规则依据；多档同时成立必须一致，冲突记 unknown。
  未知一律写 ``None``（未知 ≠ 零，见术语表与 ``PlayerObservation.chain_piao``）。
- 推导只经 ``hangma``（唯一规则来源）：``settlement.infer_piao_count`` 给值，
  ``progression`` / ``special_rules`` 给规则依据；本模块不另写一套链规则。

量纲
====
``chain_count`` 单位「次」（本人链动作计数，平台权威）；``chain_piao`` 单位「张/次」
（同一链内飘出的白板块数）。本模块不产生番值、倍率或积分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from hangma_bot.hangma.internal_types import is_wealth
from hangma_bot.hangma.settlement import infer_piao_count
from hangma_bot.kernel.observation import PlayerObservation
from hangma_bot.kernel.serialization import observation_from_json

#: 归因块在落盘 payload 中的键；与 observation 同级（不改 observation 结构）。
CHAIN_PIAO_ATTRIBUTION_KEY = "chain_piao_attribution"

#: 承载决策输入的 payload 键（``application.decision_loop`` 的 DECISION_INPUT 形态）。
DECISION_REQUEST_KEY = "request"

#: 归因块版本；字段含义变化时必须升级，便于离线按版本解释历史记录。
ATTRIBUTION_SCHEMA = "chain-piao-attribution-v1"

#: 六级规则档位名（落盘可读；每一档都必须有规则依据）。
RUNG_CHAIN_ZERO = "chain_count_zero"             # 无链 ⇒ 无飘
RUNG_RIVER_NO_WHITE = "own_river_without_white"  # 本人牌河无白 ⇒ 飘必为 0
RUNG_HELD_FOUR = "whites_held_four"              # 手留 4 张白 ⇒ 飘必为 0（白板共 4 张）
RUNG_GANG_DRAW_SINGLE = "gang_replenish_single"  # 杠上补牌且链长 1 ⇒ 该链动作即此杠
RUNG_NO_GANG_MELD = "own_melds_without_gang"     # 本局无杠组 ⇒ 链动作只能全是飘
RUNG_PUBLIC_HISTORY = "public_history_suffix"    # 连续历史后缀定位到链动作见证

#: 各档位的规则依据（写进归因块，供离线复核）。
RUNG_BASIS: Dict[str, str] = {
    RUNG_CHAIN_ZERO: "guide 1.3：链次数为 0 时链内飘出必为 0（settlement.infer_piao_count 首分支）",
    RUNG_RIVER_NO_WHITE: ("progression.chain_after_discard：飘 = 爆头态打出白板；白板不可被吃碰杠、"
                          "弃出后必留本人牌河 ⇒ 本人牌河无白则飘必为 0"),
    RUNG_HELD_FOUR: "settlement._validate_chain 同口径：白板共 4 张 ⇒ 手留 4 张时链内飘出必为 0",
    RUNG_GANG_DRAW_SINGLE: ("progression.chain_after_gang：杠使链 +1 且飘数不变；gang_draw=True 证明"
                            "上一次本人动作是杠 ⇒ 链次数 1 时飘必为 0"),
    RUNG_NO_GANG_MELD: ("progression.chain_after_discard / chain_after_gang：链每次只由飘或杠 +1；"
                        "本人副露里没有杠组 ⇒ 本局无杠 ⇒ 链次数即链内飘出张数"),
    RUNG_PUBLIC_HISTORY: "guide 1.3 生命周期：链内每次本人白板弃牌 +1 飘、杠 +0，连续后缀足以定位",
}

#: 副露种类前缀：杠（明/暗/补）都会以 gang* 形态留在公开副露里（见 observation_rules）。
_GANG_MELD_PREFIX = "gang"

#: 已实测的公开副露种类白名单（语料实测：chi 363k / peng 313k / gang_bu 8k / gang_ming 16k / gang_an 7k）。
#: 出现白名单外的种类时，"无杠组 ⇒ 无杠"这一档**不成立**（可能是不认识的杠形态）⇒ fail-closed 不归因。
_KNOWN_MELD_KINDS = frozenset({"chi", "peng", "gang", "gang_an", "gang_ming", "gang_bu"})


@dataclass(frozen=True)
class ChainPiaoDerivation:
    """一次落盘前的可归因推导结果（全部字段只读）。"""

    piao: Optional[int]  # 归因后的链内飘出张数；不可归因时为 None（未知，**不等于零**）
    chain_count: int  # 平台权威链次数（次）
    rungs: Tuple[str, ...]  # 命中的推导档位名；空元组表示无档位可用
    attributed_seqs: Tuple[int, ...]  # 归因命中的本人链动作官方事件序号（升序）
    own_river_whites: int  # 本人牌河白板数（张，单局口径）
    whites_held: int  # 手留白板数（张，含刚摸牌归一化）
    invariants: Tuple[Tuple[str, str, bool], ...]  # (不变量名, 依据, 是否成立)
    reason: Optional[str]  # 不可归因原因；可归因时为 None
    witnessed: bool = False  # 非零飘数是否由链动作事件逐条见证
    rule_accounted: bool = False  # 非零飘数是否由「本局无杠 ⇒ 链动作全是飘」档位排除其他可能

    @property
    def attributed(self) -> bool:
        """是否给出了可归因的值（False 表示落盘为未知）。"""

        return self.piao is not None and self.reason is None


def derive_chain_piao(observation: PlayerObservation) -> ChainPiaoDerivation:
    """由本人动作史与可见事实推导链内飘出张数；不可归因返回未知。

    各档规则证据独立取值，**同时成立时必须一致**；任一不变量不成立或档位冲突
    一律返回未知（``piao=None`` + ``reason``），不猜测、不填零。
    """

    chain_count = observation.rule_state.chain_count
    river_whites = _own_river_whites(observation)
    whites_held = _whites_held(observation)
    history_piao, history_seqs, history_reason = _history_witness(observation)
    if own_melds_contain_white(observation):
        return _verdict(None, chain_count, (), (), river_whites, whites_held,
                        reason="本人副露含白板，与「白板不可被吃碰杠」矛盾，本记录不作归因")

    candidates: List[Tuple[str, int]] = []
    if chain_count == 0:
        # 档位①：链次数为 0 ⇒ 飘必为 0（同一规则函数首分支；链为 0 时不看历史）。
        candidates.append((RUNG_CHAIN_ZERO, 0))
    elif history_piao is not None:
        candidates.append((RUNG_PUBLIC_HISTORY, history_piao))
    if river_whites == 0:
        # 档位②：本人牌河无白板 ⇒ 本局从未打出白板 ⇒ 飘必为 0。
        candidates.append((RUNG_RIVER_NO_WHITE, 0))
    if whites_held == 4:
        # 档位③：白板共 4 张，手留 4 张 ⇒ 链内飘出必为 0。
        candidates.append((RUNG_HELD_FOUR, 0))
    if chain_count == 1 and observation.gang_draw is True:
        # 档位④：这次摸牌是杠上补牌且链长 1 ⇒ 该链动作就是这次杠 ⇒ 飘 0。
        candidates.append((RUNG_GANG_DRAW_SINGLE, 0))
    if chain_count > 0 and own_melds_prove_no_gang(observation):
        # 档位⑥：本局公开副露里没有杠组（且种类全在已知白名单内）⇒ 链动作不可能是杠
        # ⇒ 链次数即飘数。与档位⑤（逐事件见证）互为交叉核对：两者同时成立必须一致。
        candidates.append((RUNG_NO_GANG_MELD, chain_count))

    if not candidates:
        reason = history_reason or "无可用归因档位：本人牌河有白板且历史不足以定位链动作"
        return _verdict(None, chain_count, (), (), river_whites, whites_held, reason=reason)
    values = {value for _, value in candidates}
    if len(values) != 1:
        detail = "、".join("{0}={1}".format(name, value) for name, value in candidates)
        return _verdict(None, chain_count, (), (), river_whites, whites_held,
                        reason="档位冲突，记录为未知：" + detail)
    piao = candidates[0][1]
    rungs = tuple(sorted(name for name, _ in candidates))
    witnessed = history_piao == piao and len(history_seqs) == chain_count
    rule_accounted = RUNG_NO_GANG_MELD in rungs and piao == chain_count
    if piao != 0 and history_piao is not None and history_piao != piao:
        return _verdict(None, chain_count, (), (), river_whites, whites_held,
                        reason="逐事件见证值 {0} 与档位值 {1} 不符，记录为未知".format(
                            history_piao, piao))
    if piao != 0 and not (witnessed or rule_accounted):
        return _verdict(None, chain_count, (), (), river_whites, whites_held,
                        reason="非零飘数既无逐事件见证、也无「本局无杠」档位支持，记录为未知")
    seqs = history_seqs if witnessed else ()
    return _verdict(piao, chain_count, rungs, seqs, river_whites, whites_held,
                    witnessed=witnessed, rule_accounted=rule_accounted)


def own_melds_contain_gang(observation: PlayerObservation) -> bool:
    """本人公开副露里是否有杠组（明/暗/补杠都以 gang* 形态留在副露里）。"""

    return any(meld.kind.startswith(_GANG_MELD_PREFIX)
               for meld in observation.melds[observation.seat])


def own_melds_prove_no_gang(observation: PlayerObservation) -> bool:
    """公开副露能否**证明**本局没有杠：有杠组则否；出现未知种类则不证明（fail-closed）。

    为什么加白名单：档位⑥ 的结论依赖"所有杠都会在副露里留下 gang* 形态"。
    若平台将来给出不认识的杠种类（例如改名），直接按"没有 gang 前缀 ⇒ 无杠"就会
    把杠链误判成飘链——宁可记未知，也不能在未知形态上编出一个值。
    """

    melds = observation.melds[observation.seat]
    for meld in melds:
        if meld.kind.startswith(_GANG_MELD_PREFIX):
            return False
        if meld.kind not in _KNOWN_MELD_KINDS:
            return False
    return True


def own_melds_contain_white(observation: PlayerObservation) -> bool:
    """本人副露是否含白板；含白即本记录不可作飘归因（白板不可被吃碰杠）。"""

    for meld in observation.melds[observation.seat]:
        if any(is_wealth(tile) for tile in meld.tiles):
            return True
    return False


def attribution_payload(derivation: ChainPiaoDerivation, *, live_value: Optional[int]) -> dict:
    """把推导结果转成落盘归因块（机读；字段名即证据名，单位随块声明）。"""

    return {
        "schema": ATTRIBUTION_SCHEMA,
        "status": "attributed" if derivation.attributed else "unknown",
        "piao": derivation.piao,  # 落盘值（张）；None = 未知，不等于零
        "chain_count": derivation.chain_count,  # 平台权威链次数（次）
        "rungs": list(derivation.rungs),
        "rung_basis": {name: RUNG_BASIS.get(name, "") for name in derivation.rungs},
        "attribution_basis": _basis_names(derivation),  # 归因方式（事件见证 / 规则档位 / 零值档位）
        "witness_seqs": list(derivation.attributed_seqs),  # 归因命中的本人链动作序号
        "own_river_whites": derivation.own_river_whites,  # 本人牌河白板数（张）
        "whites_held": derivation.whites_held,  # 手留白板数（张）
        "live_value": live_value,  # 归一化之前 observation 上的原值（可追溯）
        "changed": live_value != derivation.piao,  # 是否改写了 observation.chain_piao
        "invariants": {
            name: {"holds": bool(holds), "basis": basis}
            for name, basis, holds in derivation.invariants
        },
        "reason": derivation.reason,
        "units": {
            "chain_count": "次",
            "piao": "张（= 链内飘出次数）",
            "own_river_whites": "张",
            "whites_held": "张",
        },
    }


def normalize_decision_input_payload(payload: Mapping[str, object]) -> dict:
    """落盘前把决策输入补成可归因记录；返回新 payload，**不修改入参**。

    只改两处：``request.observation.chain_piao`` 与新增的 ``chain_piao_attribution``。
    任何解码/推导失败都原样返回（只加一条 ``status=error`` 归因块）——
    审计记录不因补全失败而丢失，也不因补全失败改变动作路径。
    """

    out = dict(payload)
    request = payload.get(DECISION_REQUEST_KEY)
    if not isinstance(request, Mapping):
        out[CHAIN_PIAO_ATTRIBUTION_KEY] = _failure_block(
            "not_applicable", "payload 不含 request 对象")
        return out
    raw_observation = request.get("observation")
    if not isinstance(raw_observation, Mapping):
        out[CHAIN_PIAO_ATTRIBUTION_KEY] = _failure_block(
            "not_applicable", "request 不含 observation 对象")
        return out
    try:
        observation = observation_from_json(raw_observation)
    except Exception as exc:  # noqa: BLE001 - 记录层不得因补全失败丢记录
        out[CHAIN_PIAO_ATTRIBUTION_KEY] = _failure_block(
            "error", "观察解码失败：{0}: {1}".format(type(exc).__name__, exc))
        return out
    try:
        derivation = derive_chain_piao(observation)
    except Exception as exc:  # noqa: BLE001 - 推导异常不改写 observation
        out[CHAIN_PIAO_ATTRIBUTION_KEY] = _failure_block(
            "error", "飘数推导失败：{0}: {1}".format(type(exc).__name__, exc))
        return out

    normalized_observation = dict(raw_observation)
    normalized_observation["chain_piao"] = derivation.piao
    normalized_request = dict(request)
    normalized_request["observation"] = normalized_observation
    out[DECISION_REQUEST_KEY] = normalized_request
    out[CHAIN_PIAO_ATTRIBUTION_KEY] = attribution_payload(
        derivation, live_value=observation.chain_piao)
    return out


def rule_value_for_cross_check(observation: PlayerObservation) -> Optional[int]:
    """规则单一来源给出的同一量（供审计/测试对拍；落盘路径同样只用它取值）。"""

    return infer_piao_count(
        observation.public_history, observation.seat,
        observation.rule_state.chain_count, observation.consumed_seq,
    )


def _basis_names(derivation: ChainPiaoDerivation) -> List[str]:
    """归因方式标签：事件见证、规则档位排除其他可能、或零值档位。"""

    names: List[str] = []
    if derivation.witnessed:
        names.append("event_witness")
    if derivation.rule_accounted:
        names.append("rule_rung_no_gang_meld")
    if derivation.piao == 0 and derivation.rungs:
        names.append("zero_by_rule_rung")
    return names


def _failure_block(status: str, reason: str) -> dict:
    """补全失败时的最小归因块；不声称任何值。"""

    return {"schema": ATTRIBUTION_SCHEMA, "status": status, "piao": None, "reason": reason}


def _verdict(
    piao: Optional[int], chain_count: int, rungs: Tuple[str, ...],
    attributed_seqs: Tuple[int, ...], own_river_whites: int, whites_held: int,
    *, reason: Optional[str] = None, witnessed: bool = False, rule_accounted: bool = False,
) -> ChainPiaoDerivation:
    """组装推导结果并计算不变量；任一不变量不成立即降级为未知。"""

    if piao == 0:
        attributed_ok = bool(rungs)
    else:
        attributed_ok = witnessed or rule_accounted
    invariants: List[Tuple[str, str, bool]] = [
        ("piao_le_chain_count", "settlement._validate_chain / PlayerObservation 构造",
         piao is None or piao <= chain_count),
        ("piao_le_own_river_whites",
         "progression.chain_after_discard：每次飘都打出白板并留在本人牌河",
         piao is None or piao <= own_river_whites),
        ("whites_total_le_four", "白板共 4 张（settlement._validate_chain 同口径）",
         piao is None or whites_held + piao <= 4),
        ("every_increment_attributed",
         "每个 +1 或由链动作事件见证（杠/白板弃牌）或由规则档位排除其他可能（本局无杠）",
         piao is None or attributed_ok),
    ]
    failed = [name for name, _, holds in invariants if not holds]
    if failed and reason is None:
        piao = None
        reason = "不变量不成立，记录为未知：" + "、".join(failed)
    return ChainPiaoDerivation(
        piao=piao, chain_count=chain_count, rungs=rungs,
        attributed_seqs=attributed_seqs, own_river_whites=own_river_whites,
        whites_held=whites_held, invariants=tuple(invariants), reason=reason,
        witnessed=witnessed and piao is not None, rule_accounted=rule_accounted and piao is not None,
    )


def _own_river_whites(observation: PlayerObservation) -> int:
    """本人牌河中的白板张数（张，单局口径；与本局链计数同局）。"""

    return sum(1 for tile in observation.discards[observation.seat] if is_wealth(tile))


def _concealed_codes(observation: PlayerObservation) -> Tuple[str, ...]:
    """本人暗牌牌码（含刚摸牌，摸牌置尾），按两种官方形态归一化计数。

    官方快照实测形态是 "my_hand 已含刚摸牌"（长度 14−3×副露），契约形态是
    "my_hand 不含摸牌"（长度 13−3×副露）；不归一化会把刚摸牌双计。
    与 ``policy.evaluation_v1._hand_codes_without_double_count`` 同口径
    （依据 ``doc/implementation/notes/rules-hu-gate-and-win-detection.md``）；
    只做计数整理，不做任何合法性判断。
    """

    codes = [tile.code for tile in observation.my_hand]
    drawn = observation.drawn_tile
    if drawn is None:
        return tuple(codes)
    expected = 14 - 3 * len(observation.melds[observation.seat])
    if len(codes) == expected:
        for index in range(len(codes) - 1, -1, -1):
            if codes[index] == drawn.code:
                del codes[index]
                break
    codes.append(drawn.code)
    return tuple(codes)


def _whites_held(observation: PlayerObservation) -> int:
    """手留财神（白板）张数（张）；机械计数，不推演向听或有效牌。"""

    return sum(1 for code in _concealed_codes(observation) if code == "白")


def _history_witness(
    observation: PlayerObservation,
) -> Tuple[Optional[int], Tuple[int, ...], Optional[str]]:
    """在连续历史后缀里定位链动作见证；口径与 ``settlement.infer_piao_count`` 相同。

    为什么另写一遍：规则函数只返回值，不返回"哪几个事件贡献了 +1"，而归因要求每个
    +1 都能指到具体事件序号。两处口径由等价性测试钉死（同输入必须同结果：规则函数
    返回 None 时这里也必须返回 None，返回值必须相等）——本函数只做**定位与核对**，
    不引入新的链语义；牌面分类统一用 ``hangma`` 的 ``is_wealth``。
    """

    chain_count = observation.rule_state.chain_count
    if chain_count == 0:
        return None, (), None
    history = observation.public_history
    expected = observation.consumed_seq
    if expected is None or not history:
        return None, (), "缺少消费水位或历史，无法定位链动作"
    found = piao = 0
    seqs: List[int] = []
    harmless = ("tile_drawn", "tile_discarded", "gang", "chi", "peng", "pass", "timeout")
    for event in reversed(history):
        if event.seq != expected:
            return None, (), "历史后缀不连续（序号缺口），无法定位链动作"
        expected -= 1
        if event.kind not in harmless:
            return None, (), "历史出现未知事件类型 {0}，无法定位链动作".format(event.kind)
        if event.seat != observation.seat:
            continue
        if event.kind == "gang":
            found += 1
            seqs.append(event.seq)
        elif event.kind == "tile_discarded":
            if len(event.tiles) != 1 or not is_wealth(event.tiles[0]):
                return None, (), "链动作之前出现本人普通弃牌，链已断，历史不足以定位"
            found += 1
            piao += 1
            seqs.append(event.seq)
        if found == chain_count:
            return piao, tuple(sorted(seqs)), None
    return None, (), "历史不足以覆盖 {0} 次链动作".format(chain_count)
