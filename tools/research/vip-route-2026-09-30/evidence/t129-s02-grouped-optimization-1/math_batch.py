"""T129 同状态、同标准目标的纯数学批量复用研究装配。

仍调用冻结的 ``_standard.need``，不改自然实体配额、将或财神分配。
同一自然计数及剩余面子数下，只有 ``(用白数, 是否需要将)`` 完全相同
的目标才共享距离；不同目标只共享一次自然进张计数构造。七对沿用原
闭式公式，以计数奇偶更新对子及单张数，四张同码仍按两对计。

结果的 ``target_distance_evaluation_count`` 保持合同中的距离请求量，
不是实际后端执行次数（v3自然准备合同第53行）。另记实际need入口次数
与已响应的标准距离请求量，不能把入口减少量写成C搜索节点或耗时收益。
本文件只显式替换当前进程绑定，退出反序恢复，不改冻结源码或线上装配。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from contextlib import contextmanager
from functools import lru_cache
import sys


MAX_BATCH_STATES = 2048


class _NaturalBatch:
    """只含本人自然计数的有界复用单元；进张元组不在缓存中长期保存。"""

    __slots__ = ("natural", "sets_left", "pairs", "singles", "eligible", "goals", "need", "stats")

    def __init__(self, natural, sets_left, need, stats, codes):
        self.natural = natural
        self.sets_left = sets_left
        self.pairs = sum(value // 2 for value in natural)
        self.singles = sum(value % 2 for value in natural)
        self.eligible = tuple(
            (index, held, codes[index])
            for index, held in enumerate(natural) if held < 4
        )
        # 键为用白数及将要求；值为基础缺张、规范自然牌顺序下的补张距离。
        # 补张距离为None时仅计算了基础缺张，不能冒充已完成进张计算。
        self.goals = {}
        self.need = need
        self.stats = stats

    def base(self, goal):
        """获取固定目标的基础距离，缓存只回答完全相同的数学请求。"""
        saved = self.goals.get(goal)
        if saved is None:
            self.stats["backend_need_calls"] += 1
            missing = self.need(self.natural, goal[0], self.sets_left, goal[1])
            saved = (missing, None)
            self.goals[goal] = saved
        return saved[0]

    def ensure_draws(self, goals):
        """每个自然补张计数只构造一次，再求本批所有尚缺的固定目标。"""
        pending = tuple(dict.fromkeys(goal for goal in goals if self.goals.get(goal, (None, None))[1] is None))
        if not pending:
            return
        bases = tuple(self.base(goal) for goal in pending)
        after = [[] for _ in pending]
        natural = self.natural
        for index, held, _ in self.eligible:
            drawn = natural[:index] + (held + 1,) + natural[index + 1:]
            self.stats["natural_draw_tuple_constructions"] += 1
            for position, goal in enumerate(pending):
                self.stats["backend_need_calls"] += 1
                after[position].append(self.need(drawn, goal[0], self.sets_left, goal[1]))
        for position, goal in enumerate(pending):
            self.goals[goal] = (bases[position], tuple(after[position]))

    def improvement(self, goal):
        """返回同目标自然改善码；不加入白板、公开容量或胡资格判断。"""
        before, after = self.goals[goal]
        return tuple(code for (_, _, code), missing in zip(self.eligible, after) if missing < before)


def _replace_aliases(before, after, changes):
    """按对象身份替换已装载第一方别名，包含T88编译模块的全局字典。"""
    seen = set()
    for module in tuple(sys.modules.values()):
        name = "" if module is None else getattr(module, "__name__", "")
        if not name.startswith(("hangma_bot.", "_t88_", "_t120_")):
            continue
        namespace = vars(module)
        # Cython函数使用编译模块的全局字典；同一模块有多个sys别名也只改一次。
        if id(namespace) in seen:
            continue
        seen.add(id(namespace))
        for alias, value in tuple(namespace.items()):
            if value is before:
                changes.append((module, alias, before))
                setattr(module, alias, after)


@contextmanager
def installed():
    """装配同数学批次；yield身份及可变计数，异常退出也恢复所有绑定。

    在T123原生装配后进入。缓存均局限本次显式装配，路线和自然结果缓存
    各保持2048条上限。额外数学批次也最多2048个自然状态，不含完整世界。
    统计只覆盖本装配调用的纯数学入口；不授端到端时限或发布资格。
    """
    from hangma_bot.hangma import hand_analysis as hand
    from hangma_bot.hangma import natural_preparation as natural
    from hangma_bot.hangma import route_structure as route
    from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER

    need = hand._need_std
    if route._standard_need is not need or natural._standard_need is not need:
        raise RuntimeError("三种手牌事实必须绑定同一权威标准型数学后端")
    original_math = hand._analyse_counts_progress_math
    original_route = route.analyze_route_structure
    original_natural = natural.analyze_natural_set_preparation
    stats = {
        "backend_need_calls": 0,
        "standard_distance_requests": 0,
        "target_distance_requests": 0,
        "natural_draw_tuple_constructions": 0,
        "hand_math_fallback_calls": 0,
        "bindings_restored": False,
    }

    @lru_cache(maxsize=MAX_BATCH_STATES)
    def batch_for(natural_counts, sets_left):
        return _NaturalBatch(natural_counts, sets_left, need, stats, CANONICAL_TILE_ORDER)

    def analyze_counts_math(counts34, meld_set_count, *, collect_pattern_useful):
        """保持原手牌摘要全部字段，标准自然进张复用同目标的完整距离。"""
        hand._validate_melds(meld_set_count)
        if len(counts34) != 34:
            raise ValueError("counts34 必须包含 34 个规范牌值计数")
        # 原入口不是严格等待态接口。未落入规范实体域时回原函数，保留原错。
        if (type(counts34) is not tuple
                or any(type(value) is not int or not 0 <= value <= 4 for value in counts34)):
            stats["hand_math_fallback_calls"] += 1
            return original_math(counts34, meld_set_count, collect_pattern_useful=collect_pattern_useful)
        whites = counts34[33]
        batch = batch_for(counts34[:33], 4 - meld_set_count)
        goal = (whites, True)
        stats["standard_distance_requests"] += 1
        standard_shanten = batch.base(goal) - 1
        chiitoi_shanten = None
        if meld_set_count == 0:
            paired = min(whites, batch.singles)
            chiitoi_shanten = 6 - min(7, batch.pairs + paired + (whites - paired) // 2)
        shanten = standard_shanten if chiitoi_shanten is None else min(standard_shanten, chiitoi_shanten)
        is_win = shanten == -1
        entries = []
        standard_entries = [] if collect_pattern_useful else None
        seven_entries = [] if collect_pattern_useful else None
        if not is_win:
            stats["standard_distance_requests"] += len(batch.eligible)
            batch.ensure_draws((goal,))
            after_standard_values = batch.goals[goal][1]
            # 保留34码顺序；白进张改变真实白库存，不与自然进张混用。
            rows = [
                (index, held, code, whites, missing - 1)
                for (index, held, code), missing in zip(batch.eligible, after_standard_values)
            ]
            if whites < 4:
                stats["standard_distance_requests"] += 1
                rows.append((33, whites, CANONICAL_TILE_ORDER[33], whites + 1, batch.base((whites + 1, True)) - 1))
            for index, held, code, drawn_whites, after_standard in rows:
                after = after_standard
                if standard_entries is not None and after_standard < standard_shanten:
                    standard_entries.append((code, after_standard))
                if meld_set_count == 0:
                    drawn_pairs = batch.pairs + (held % 2 if index < 33 else 0)
                    drawn_singles = batch.singles + ((1 if held % 2 == 0 else -1) if index < 33 else 0)
                    paired = min(drawn_whites, drawn_singles)
                    after_seven = 6 - min(7, drawn_pairs + paired + (drawn_whites - paired) // 2)
                    after = min(after, after_seven)
                    if seven_entries is not None and after_seven < chiitoi_shanten:
                        seven_entries.append((code, after_seven))
                if after < shanten:
                    entries.append((code, after))
            if whites < 4 and not any(code == hand._WHITE_CODE for code, _ in entries):
                entries.append((hand._WHITE_CODE, shanten - 1))
        return (standard_shanten, chiitoi_shanten, shanten, is_win, whites,
                tuple(entries), None if standard_entries is None else tuple(standard_entries),
                None if seven_entries is None else tuple(seven_entries))

    @lru_cache(maxsize=2048)
    def route_cached(counts34, meld_set_count):
        """保留原路线目标顺序及请求计量；仅共用固定目标距离和进张构造。"""
        whites = counts34[33]
        sets_left = 4 - meld_set_count
        batch = batch_for(counts34[:33], sets_left)
        goals = tuple((whites - retained, retained == 0) for retained in range(whites + 1))
        per_target = 1 + len(batch.eligible)
        stats["standard_distance_requests"] += 1 + len(goals) * per_target
        batch.ensure_draws(goals)
        standard_shanten = batch.base((whites, True)) - 1
        seven_shanten = 6 - hand._chiitoi_pairs(batch.natural, whites) if meld_set_count == 0 else None
        families = ("standard", "seven_pairs") if meld_set_count == 0 else ("standard",)
        targets = []
        for family in families:
            for retained in range(whites + 1):
                used = whites - retained
                predecessor = retained > 0
                slots = (3 * sets_left + (0 if predecessor else 2)
                         if family == "standard" else (12 if predecessor else 14))
                if family == "standard":
                    goal = (used, not predecessor)
                    missing = batch.base(goal)
                    improving = batch.improvement(goal)
                else:
                    pairs = 6 if predecessor else 7
                    remaining = max(0, pairs - batch.pairs)
                    missing = max(0, 2 * remaining - min(batch.singles, remaining) - used)
                    improving_codes = []
                    for _, held, code in batch.eligible:
                        drawn_pairs = batch.pairs + held % 2
                        drawn_singles = batch.singles + (1 if held % 2 == 0 else -1)
                        drawn_remaining = max(0, pairs - drawn_pairs)
                        after_missing = max(0, 2 * drawn_remaining - min(drawn_singles, drawn_remaining) - used)
                        if after_missing < missing:
                            improving_codes.append(code)
                    improving = tuple(improving_codes)
                discards = missing - (retained - 1) if predecessor else missing - 1
                if used > slots or discards < 0:
                    raise RuntimeError("用途结构距离违反等待态数量守恒")
                targets.append(route.RouteStructureTarget(
                    family=family, retained_whites=retained, white_used=used,
                    target_stage="waiting_predecessor" if predecessor else "complete_structure",
                    target_natural_size=slots - used, natural_need=missing,
                    target_natural_draw_lower_bound=missing,
                    target_natural_discard_lower_bound=discards,
                    target_white_discard_lower_bound=retained - 1 if predecessor else 0,
                    requires_terminal_draw=predecessor,
                    conditional_need_improvement_codes=improving))
        evaluations = len(targets) * per_target
        stats["target_distance_requests"] += evaluations
        return route.RouteStructureFacts(
            natural_counts33=batch.natural, whites_held=whites, meld_set_count=meld_set_count,
            standard_shanten=standard_shanten, seven_pairs_shanten=seven_shanten,
            natural_pair_count=batch.pairs,
            natural_quad_codes=tuple(CANONICAL_TILE_ORDER[index] for index, held in enumerate(batch.natural) if held == 4),
            targets=tuple(targets), target_distance_evaluation_count=evaluations)

    def analyze_route(counts34, meld_set_count):
        """先执行冻结的严格等待态校验，bool/int缓存相等也不能绕过边界。"""
        route._validate_waiting_counts(counts34, meld_set_count)
        return route_cached(counts34, meld_set_count)

    @lru_cache(maxsize=2048)
    def natural_cached(counts34, meld_set_count):
        """自然目标不借白、不含将；可复用全保白路线的完全相同目标。"""
        batch = batch_for(counts34[:33], 4 - meld_set_count)
        goal = (0, False)
        evaluations = 1 + len(batch.eligible)
        stats["standard_distance_requests"] += evaluations
        stats["target_distance_requests"] += evaluations
        batch.ensure_draws((goal,))
        missing = batch.base(goal)
        size = 3 * batch.sets_left
        discards = sum(batch.natural) + missing - size
        if discards < 0:
            raise RuntimeError("自然面子准备距离违反目标实体数量守恒")
        return natural.NaturalSetPreparationFacts(
            natural_counts33=batch.natural, whites_held=counts34[33], meld_set_count=meld_set_count,
            sets_left=batch.sets_left, target_natural_size=size,
            natural_draw_lower_bound=missing, natural_discard_lower_bound=discards,
            natural_need_improvement_codes=batch.improvement(goal),
            target_distance_evaluation_count=evaluations)

    def analyze_natural(counts34, meld_set_count):
        """沿用冻结入口的全部校验及错误文案，随后进入共享数学缓存。"""
        return original_natural(counts34, meld_set_count)

    changes = []
    identity = {
        "schema": "t129-shared-standard-target-math/1",
        "max_batch_states": MAX_BATCH_STATES,
        "target_count_semantics": "distance requests required by result, including answers from shared cache",
        "shared_goal_key": ["natural_counts33", "sets_left", "white_used", "pair_needed"],
        "new_formula": False, "production_changes": 0, "admission": False,
    }
    try:
        _replace_aliases(original_math, analyze_counts_math, changes)
        _replace_aliases(original_route, analyze_route, changes)
        # 保留原自然入口的完整校验及错误文案，只换其校验后的缓存核心。
        _replace_aliases(natural._analyze_validated_counts, natural_cached, changes)
        # 若已有第一方别名持有入口，仍按对象身份显式重绑，覆盖编译模块路径。
        _replace_aliases(original_natural, analyze_natural, changes)
        stats["replaced_bindings"] = len(changes)
        yield identity, stats
    finally:
        for module, alias, before in reversed(changes):
            setattr(module, alias, before)
        stats["bindings_restored"] = all(getattr(module, alias) is before for module, alias, before in changes)
        stats["standard_need_calls_avoided"] = stats["standard_distance_requests"] - stats["backend_need_calls"]
        stats["batch_cache"] = batch_for.cache_info()._asdict()
        stats["route_result_cache"] = route_cached.cache_info()._asdict()
        stats["natural_result_cache"] = natural_cached.cache_info()._asdict()
        batch_for.cache_clear()
        route_cached.cache_clear()
        natural_cached.cache_clear()
