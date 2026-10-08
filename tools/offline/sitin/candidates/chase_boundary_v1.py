"""chase_boundary_v1：按「追 vs 收」的精确判据排序（受限子集：白名单内建 + 只读方法 + 字面量常量）。

机制四字段
- trigger：窗口内同时存在「合法胡」与「飘」（爆头态弃财神）两个动作。
- changed_branches：E(追) > fan(收) 时把飘排到胡之前；否则维持胡优先。
- expected_direction：剩余巡数大、飘后等待面仍宽时倾向追；否则倾向收。
- counterexample：不建模他家自摸；等待宽度只用可见剩余估计，边界（≈50%）附近可能判错。

判据：收 = fan(现胡)（确定）；追 = P(k 巡内再胡) × fan(现胡) × 2（链 +1 翻倍）。
P 用闭式 1 − Π(1 − w/(n−j))；w = 飘后动作的等待枚数估计，n = 公开墙余量。
未知字段动作按「已知分最小值 − 1」锚定（与 seeds 同口径）。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools/candidates'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
K_TURNS = 12
CHAIN_FACTOR = 2.0
BAOTOU_FACTOR = 2.0  # 爆头 ×2；飘之后爆头按「弃后暗牌」重算（RULES_EVIDENCE §8），本候选保守假设其丢失
SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
PIAO_KEY = "discard:白"


def settlement_fan(settlement):
    if settlement is None:
        return None
    fan = settlement.get("fan")
    if fan is None or fan is True or fan is False:
        return None
    if fan <= 0:
        return None
    return float(fan)


def numeric(value):
    if value is None or value is True or value is False:
        return None
    return value


def wait_width(action):
    """等待宽度：只有已经听牌（动作后向听 = 0）时，useful_tiles 才是成胡牌；
    否则它只是推进牌，不能用来算"下一巡再胡"的概率（本候选据此返回 None）。"""
    shanten = numeric(action.get("shanten_after"))
    if shanten is None or shanten != 0:
        return None
    tiles = action.get("useful_tiles")
    if tiles is None:
        return None
    total = 0.0
    for tile in tiles:
        remaining = numeric(tile.get("remaining_estimate"))
        if remaining is None:
            return None
        total = total + remaining
    return total


def hit_probability(width, wall, turns):
    if width is None or wall is None:
        return 0.0
    if wall <= 0 or width <= 0:
        return 0.0
    miss = 1.0
    for step in range(turns):
        room = wall - step
        if room <= 0:
            break
        chance = width / room
        if chance > 1.0:
            chance = 1.0
        miss = miss * (1.0 - chance)
    return 1.0 - miss


def efficiency_score(action):
    shanten = numeric(action.get("shanten_after"))
    if shanten is None or shanten < -1:
        return None
    support = wait_width(action)
    if support is None:
        support = 0.0
    return 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support


def score_actions(view):
    actions = view["actions"]
    visible = view.get("visible_state")
    rule_state = None
    wall = None
    if visible is not None:
        rule_state = visible.get("rule_state")
        wall = numeric(visible.get("remaining_tile_count"))
    baotou = None
    if rule_state is not None:
        baotou = rule_state.get("baotou")
    fan_take = None
    hu_key = None
    piao_key = None
    piao_width = None
    piao_baotou_after = None
    for action in actions:
        kind = action.get("action_type")
        key = action.get("action_key")
        if kind == "hu":
            fan = settlement_fan(action.get("immediate_settlement"))
            if fan is not None and (fan_take is None or fan > fan_take):
                fan_take = fan
                hu_key = key
        elif kind == "discard" and key == PIAO_KEY and baotou is True:
            piao_key = key
            piao_width = wait_width(action)
            piao_baotou_after = action.get("baotou_after")
    chase = None
    if fan_take is not None and piao_key is not None:
        # 飘的链动作数 +1（番值 ×2）；爆头是否保住要看**弃后暗牌**（视图事实 baotou_after）：
        #   仍任意听 ⇒ 下一巡必胡（概率 1）且爆头 ×2 保住，与链 ×2 兼得 ⇒ 净 ×2；
        #   爆头退出 ⇒ 净番值不变，还要求重新听牌 ⇒ 通常应当收；
        #   未知 ⇒ 保守（按退出处理）。
        if piao_baotou_after is True:
            probability = 1.0
            net_factor = CHAIN_FACTOR
        else:
            probability = hit_probability(piao_width, wall, K_TURNS)
            net_factor = CHAIN_FACTOR / BAOTOU_FACTOR
        chase = probability * fan_take * net_factor
    # 受限子集禁止下标赋值 ⇒ 两遍循环：先定锚点，再统一构造条目
    unknown_keys = []
    known_min = None
    for action in actions:
        key = action.get("action_key")
        score = None
        if key == hu_key and fan_take is not None:
            score = 1000.0 + fan_take
        elif key == piao_key and chase is not None:
            score = 1000.0 + chase
        else:
            score = efficiency_score(action)
        if score is None:
            unknown_keys.append(key)
        elif known_min is None or score < known_min:
            known_min = score
    anchor = known_min - 1.0 if known_min is not None else 0.0
    entries = []
    for action in actions:
        key = action.get("action_key")
        width = wait_width(action)
        role = "efficiency"
        score = efficiency_score(action)
        if key == hu_key and fan_take is not None:
            role = "take_win"
            score = 1000.0 + fan_take
        elif key == piao_key and chase is not None:
            role = "piao_candidate"
            score = 1000.0 + chase
        if score is None:
            role = "unknown_fields"
            score = anchor
        trace = {"basis": "chase_boundary", "k_turns": K_TURNS, "wall": wall,
                 "wait_width": width, "baotou": baotou, "role": role,
                 "fan_take": fan_take, "chase_expectation": chase}
        entries.append({"action_key": key, "score": score, "trace": trace})
    if len(entries) == 0:
        return {"status": "ABSTAIN", "entries": [], "reason": "no actions"}
    return {"status": "SCORED", "entries": entries, "reason": None}
