"""T129 单次投影内复用纯事实；不改变规则、图展开或等待资格缓存。

冻结源码只读。等待态校验仅将一个生成器内的重复集合构造移到辅助
函数；原生等待方法仍执行原来的资格判断、节点生成及工作量计数。
计数与相容码缓存强持有不可变输入，数量各不超过本投影 max_nodes。
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

import ast
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap

from hangma_bot.hangma.route_transition import ConditionalRouteState
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile


FROZEN_SHA256 = {
    "route_vip_heuristic.py": "1948b15d063bbd7194b83077d2f6284406e2bd8387aa95d6231767387f3cfdce",
    "route_heuristic_view.py": "82555e304073755ff9f2758de0c470e3595e96ceeb2497897a7b846d75f121d1",
    "_counts_from_visible_tiles": "eea87075ee25cb6bb4c1f400a8fd6a98c258fb37260a0d54075f8e080da9a05e",
    "RouteWaitingView.__post_init__": "63130f38db9659e45177ac2d19d3b7833ce191c999aca91b7a6a965f21b7611c",
}
_ACTIVE_PROJECTION = ContextVar("t129_graph_active_projection", default=None)
_TILE_CODES = frozenset(CANONICAL_TILE_ORDER)
_REPEATED_EXPRESSION = (
    "tuple(code for code in CANONICAL_TILE_ORDER if code in set(codes))"
)


def sha256(value: bytes) -> str:
    """计算实现或冻结源字节的审计摘要，不访问运行秘密。"""
    return hashlib.sha256(value).hexdigest()


def _cacheable_tiles(tiles) -> bool:
    # 不接受可变容器、Tile 子类或自定义牌码，避免缓存吞掉其属性副作用。
    return type(tiles) is tuple and all(
        type(tile) is Tile and type(tile.code) is str and tile.code in _TILE_CODES
        for tile in tiles
    )


def _cacheable_capacity(state) -> bool:
    return (
        type(state) is ConditionalRouteState
        and type(state.unseen_capacities) is tuple
        and type(state.unseen_evidence) is tuple
        and len(state.unseen_capacities) == len(state.unseen_evidence) == 34
        and all(value is None or type(value) is int and 0 <= value <= 4
                for value in state.unseen_capacities)
        and all(type(kind) is str and kind in ("exact", "conservative", "unknown")
                for kind in state.unseen_evidence)
        and _cacheable_tiles(state.concealed)
    )


def make_projection(base, count_function, stats):
    """在最终装配类上包一层；仅复用计数/相容码，父类等待完整键不变。

    输入为已验签的父类和原计数函数。返回类只在其 own self 中存缓存；
    stats 只保存整数，不强持有投影或图。原路径异常会原样向外传播。
    """
    class GraphBatchProjection(base):
        """保留原图搜索，只减少同一不可变状态的重复纯事实包装。"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._t129_counts_cache = {}
            self._t129_compatible_cache = {}
            self._t129_scope_stats = {
                "count_calls": 0, "count_hits": 0, "count_entries": 0,
                "compatible_calls": 0, "compatible_hits": 0,
                "compatible_entries": 0, "width_calls": 0,
                "waiting_calls": 0, "max_entries": self.limits.max_nodes,
            }
            stats["projection_scopes"].append(self._t129_scope_stats)

        def _t129_counts(self, tiles):
            row = self._t129_scope_stats
            row["count_calls"] += 1
            previous = self._t129_counts_cache.get(id(tiles))
            if previous is not None and previous[0] is tiles:
                row["count_hits"] += 1
                return previous[1]
            # 先执行原函数，非法输入的异常和次序不得被缓存检查改写。
            result = count_function(tiles)
            if (len(self._t129_counts_cache) < self.limits.max_nodes
                    and _cacheable_tiles(tiles)):
                self._t129_counts_cache[id(tiles)] = (tiles, result)
                row["count_entries"] = len(self._t129_counts_cache)
            return result

        def _t129_compatible_facts(self, state):
            row = self._t129_scope_stats
            row["compatible_calls"] += 1
            previous = self._t129_compatible_cache.get(id(state))
            if previous is not None and previous[0] is state:
                row["compatible_hits"] += 1
                return previous[1], previous[2]
            if state.unseen_capacities is None or state.unseen_evidence is None:
                # 缺证据仍由原入口发出原类别和原文，不缓存失败。
                codes = super().compatible_codes(state)
            else:
                held = self._t129_counts(state.concealed)
                codes = tuple(code for index, code in enumerate(CANONICAL_TILE_ORDER)
                              if held[index] < 4 and (
                                  state.unseen_evidence[index] != "exact"
                                  or state.unseen_capacities[index] is None
                                  or state.unseen_capacities[index] > 0))
            possible = frozenset(codes)
            if (len(self._t129_compatible_cache) < self.limits.max_nodes
                    and _cacheable_capacity(state)):
                self._t129_compatible_cache[id(state)] = (state, codes, possible)
                row["compatible_entries"] = len(self._t129_compatible_cache)
            return codes, possible

        def compatible_codes(self, state):
            """复用当前完整公开容量状态的相容码，保留规范牌序。"""
            return self._t129_compatible_facts(state)[0]

        def code_width(self, codes, state):
            """沿用原集合交集数学；两入口同时覆盖原生类的静态引用。"""
            self._t129_scope_stats["width_calls"] += 1
            possible = self._t129_compatible_facts(state)[1]
            return len(set(codes) & possible)

        def waiting(self, state, *, qualification=True):
            """原等待方法完整运行，仅给其计数入口关联本次投影。"""
            self._t129_scope_stats["waiting_calls"] += 1
            token = _ACTIVE_PROJECTION.set(self)
            try:
                return super().waiting(state, qualification=qualification)
            finally:
                _ACTIVE_PROJECTION.reset(token)

    return GraphBatchProjection


def _canonical_codes_once(codes):
    selected = set(codes)
    return tuple(code for code in CANONICAL_TILE_ORDER if code in selected)


def _waiting_validator(original):
    """只替换已冻结校验中的一个表达式，保留其余 AST 和短路次序。"""
    source = inspect.getsource(original)
    if sha256(source.encode()) != FROZEN_SHA256["RouteWaitingView.__post_init__"]:
        raise ValueError("T129 等待态校验源摘要不匹配")
    tree = ast.parse(textwrap.dedent(source))
    expected = ast.dump(ast.parse(_REPEATED_EXPRESSION, mode="eval").body,
                        include_attributes=False)
    before = ast.dump(tree, include_attributes=False)

    class ReplaceRepeatedSet(ast.NodeTransformer):
        count = 0

        def visit_Call(self, node):
            if ast.dump(node, include_attributes=False) == expected:
                self.count += 1
                return ast.copy_location(ast.parse(
                    "_t129_canonical_codes_once(codes)", mode="eval").body, node)
            return self.generic_visit(node)

    transform = ReplaceRepeatedSet()
    changed = transform.visit(tree)
    if transform.count != 1:
        raise ValueError("T129 重复集合表达式数量必须严格为一")
    ast.fix_missing_locations(changed)
    namespace = dict(original.__globals__)
    namespace["_t129_canonical_codes_once"] = _canonical_codes_once
    exec(compile(changed, "<t129-waiting-validator>", "exec"), namespace)
    result = namespace[original.__name__]
    result.__module__, result.__qualname__ = original.__module__, original.__qualname__
    audit = {
        "original_method_sha256": sha256(source.encode()),
        "original_ast_sha256": sha256(before.encode()),
        "optimized_ast_sha256": sha256(ast.dump(changed, include_attributes=False).encode()),
        "replacement_count": transform.count,
        "replacement": "one set(codes) per validated tuple; unchanged short circuit",
    }
    return result, audit


@contextmanager
def installed():
    """研究上下文返回 (identity, stats)，退出时恢复类与原生计数别名。

    装配应位于 T123 最终 _Projection 之后。这里不保存输出文件、不运行
    choose，也不调整节点/分支/资格见证额度。stats 在退出后仍可保存。
    """
    from hangma_bot.policy import route_heuristic_view as view
    from hangma_bot.policy import route_vip_heuristic as vip

    for module in (vip, view):
        path = Path(inspect.getfile(module))
        if sha256(path.read_bytes()) != FROZEN_SHA256[path.name]:
            raise ValueError("T129 冻结模块源摘要不匹配: " + path.name)
    original_counts = vip._counts_from_visible_tiles
    if sha256(inspect.getsource(original_counts).encode()) != FROZEN_SHA256["_counts_from_visible_tiles"]:
        raise ValueError("T129 原计数函数源摘要不匹配")
    original_validator = view.RouteWaitingView.__post_init__
    validator, audit = _waiting_validator(original_validator)
    original_projection = vip._Projection
    stats = {"projection_scopes": [], "bindings_restored": False}
    projection = make_projection(original_projection, original_counts, stats)

    def scoped_counts(tiles):
        active = _ACTIVE_PROJECTION.get()
        return (active._t129_counts(tiles) if active is not None
                else original_counts(tiles))

    # Cython 等待函数读取其定义模块 globals，不能只改 vip 的 Python 别名。
    count_modules = [vip]
    for kind in original_projection.__mro__:
        method = vars(kind).get("waiting")
        waiting_module = sys.modules.get(getattr(method, "__module__", ""))
        if (waiting_module is not None and waiting_module not in count_modules
                and hasattr(waiting_module, "_counts_from_visible_tiles")):
            count_modules.append(waiting_module)
    for module in count_modules:
        if getattr(module, "_counts_from_visible_tiles", None) is not original_counts:
            raise ValueError("T129 等待方法计数别名不是冻结原件")

    identity = {
        "schema": "t129-scoped-graph-facts/1",
        "implementation_sha256": sha256(Path(__file__).read_bytes()),
        "frozen_source_sha256": dict(FROZEN_SHA256),
        "waiting_validator": audit,
        "parent_projection_mro": [kind.__module__ + "." + kind.__qualname__
                                  for kind in original_projection.__mro__],
        "count_alias_modules": [module.__name__ for module in count_modules],
        "cache_scope": "projection self; strong immutable input identity",
        "cache_bound": "each cache <= limits.max_nodes",
        "waiting_full_key_unchanged": True,
        "node_branch_witness_workcounts_unchanged": True,
        "qualification_result_cache_added": False,
        "production_changes": 0, "admission": False,
    }
    identity["research_execution_id"] = sha256(json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode())
    try:
        for module in count_modules:
            module._counts_from_visible_tiles = scoped_counts
        view.RouteWaitingView.__post_init__ = validator
        vip._Projection = projection
        yield identity, stats
    finally:
        vip._Projection = original_projection
        view.RouteWaitingView.__post_init__ = original_validator
        for module in reversed(count_modules):
            module._counts_from_visible_tiles = original_counts
        stats["bindings_restored"] = True
