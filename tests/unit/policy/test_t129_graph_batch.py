"""T129 纯事实复用的输入语义、公开隔离及上下文恢复；不运行 choose。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/unit/policy'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import importlib.util
import inspect
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from hangma_bot.hangma.route_transition import ConditionalPhase, ConditionalRouteState
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy import route_heuristic_view as view
from hangma_bot.policy import route_vip_heuristic as vip


PATH = (_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[3] / "review/vip-route-2026-09-30/"
        "evidence/t129-s02-grouped-optimization-1/graph_batch.py"))
spec = importlib.util.spec_from_file_location("t129_graph_batch_test", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CONFIG = RuleConfig("t129-graph-input-test", 1, False)
pytestmark = pytest.mark.skipif(
    module.sha256(Path(inspect.getfile(vip)).read_bytes())
    != module.FROZEN_SHA256["route_vip_heuristic.py"],
    reason="T129 研究装配只接受冻结源码；使用 t54 冻结目录的 PYTHONPATH 运行",
)


def state(**changes):
    """仅构造本人可见的条件等待输入，不含他家暗牌或未来牌墙。"""
    base = ConditionalRouteState(
        concealed=tuple(Tile(code) for code in (
            "1w", "2w", "4w", "6w", "8w", "1t", "3t", "5t", "7t",
            "1b", "4b", "东", "南")),
        meld_count=0, phase=ConditionalPhase.NORMAL_DRAW, baotou=False,
        chain_count=0, chain_piao=0, wall_remaining=20,
        unseen_capacities=(4,) * 34, unseen_evidence=("exact",) * 34,
    )
    return replace(base, **changes)


def projection(kind=None, *, max_nodes=4096):
    return (kind or vip._Projection)(
        None, CONFIG, vip.VipRouteProjectionLimits(max_nodes=max_nodes))


def error_for(waiting, changes):
    try:
        replace(waiting, **changes)
    except Exception as error:
        return type(error), str(error)
    raise AssertionError("本测试输入应被原完整校验拒绝")


@pytest.mark.parametrize("changes", (
    {"unseen_capacities": (True,) + (4,) * 33},
    {"baotou": 1}, {"chain_count": True}, {"useful_code_width": True},
    {"natural_preparation_code_width": False},
    {"qualification_unknown_codes": ("2w", "1w")},
    {"qualification_unknown_codes": ("1w", "1w")},
    {"qualification_unknown_codes": ["1w"]},
    {"qualification_unknown_codes": (True,)},
    {"qualification_unknown_codes": ("invalid",)},
    {"restricted_hu_draw_codes": ("2w", "1w")},
    {"unrestricted_hu_draw_codes": ("1w", "1w")},
    {"qualification_math_closed_codes": (False,)},
))
def test_waiting_constructor_keeps_type_order_and_duplicate_errors(changes):
    waiting = projection().waiting(state())
    expected = error_for(waiting, changes)
    with module.installed() as (identity, stats):
        assert error_for(waiting, changes) == expected
        assert identity["waiting_validator"]["replacement_count"] == 1
    assert stats["bindings_restored"]


def test_public_capacity_and_evidence_are_separate_and_keep_canonical_order():
    original = vip._Projection
    first = state(concealed=(Tile("1w"),) * 4 + state().concealed[4:])
    empty_exact = replace(first, unseen_capacities=(0,) * 34)
    empty_conservative = replace(empty_exact, unseen_evidence=("conservative",) * 34)
    empty_unknown = replace(empty_exact, unseen_evidence=("unknown",) * 34)
    values = (first, empty_exact, empty_conservative, empty_unknown)
    reference = projection(original)
    expected = [(reference.compatible_codes(item), reference.code_width(
        ("2w", "2w", "白", "1w"), item)) for item in values]
    with module.installed() as (_, stats):
        optimized = projection()
        for _ in range(3):
            actual = [(optimized.compatible_codes(item), optimized.code_width(
                ("2w", "2w", "白", "1w"), item)) for item in values]
            assert actual == expected
        assert actual[1] == ((), 0)
        assert actual[2][0] == tuple(code for code in CANONICAL_TILE_ORDER if code != "1w")
        assert stats["projection_scopes"][0]["compatible_hits"] > 0
        assert stats["projection_scopes"][0]["compatible_entries"] == 4


def test_waiting_full_qualification_key_and_workcounts_are_unchanged():
    initial = state()
    changed = replace(initial, unseen_capacities=(0,) + initial.unseen_capacities[1:])
    reference = projection()
    expected = [reference.waiting(initial, qualification=True),
                reference.waiting(initial, qualification=False),
                reference.waiting(changed, qualification=False)]
    with module.installed() as (_, stats):
        optimized = projection()
        actual = [optimized.waiting(initial, qualification=True),
                  optimized.waiting(initial, qualification=False),
                  optimized.waiting(changed, qualification=False)]
        assert actual == expected
        assert actual[0].legal_hu_draw_codes == ()
        assert actual[1].legal_hu_draw_codes is None
        assert "1w" in actual[1].qualification_unknown_codes
        assert "1w" not in actual[2].qualification_unknown_codes
        # 原等待完整键命中返回同一冻结值，资格 True/False 不能串用。
        assert optimized.waiting(initial, qualification=True) is actual[0]
        assert optimized.waiting(initial, qualification=False) is actual[1]
        for name in ("branch_count", "witness_count", "target_distance_count"):
            assert getattr(optimized, name) == getattr(reference, name)
        row = stats["projection_scopes"][0]
        assert row["count_hits"] > 0 and row["compatible_hits"] > 0


def test_count_reuse_keeps_unordered_duplicate_tiles_and_original_exception():
    stats = {"projection_scopes": []}
    kind = module.make_projection(vip._Projection, vip._counts_from_visible_tiles, stats)
    optimized = projection(kind)
    held = state(concealed=(Tile("白"), Tile("2w"), Tile("1w"), Tile("2w")))
    assert optimized.compatible_codes(held) == projection().compatible_codes(held)
    assert optimized.code_width(("2w", "1w", "2w"), held) == 2
    invalid = replace(held, concealed=(SimpleNamespace(code="invalid"),))
    with pytest.raises(KeyError) as original:
        projection().compatible_codes(invalid)
    with pytest.raises(KeyError) as changed:
        optimized.compatible_codes(invalid)
    assert changed.value.args == original.value.args


def test_mutable_capacity_bypasses_cache_and_observes_changes():
    stats = {"projection_scopes": []}
    kind = module.make_projection(vip._Projection, vip._counts_from_visible_tiles, stats)
    optimized = projection(kind)
    # 原入口支持鸭子类型；只读缓存不得将其可变列表当作冻结输入。
    mutable = SimpleNamespace(concealed=(Tile("2w"),),
                              unseen_capacities=[4] * 34,
                              unseen_evidence=["exact"] * 34)
    assert "1w" in optimized.compatible_codes(mutable)
    mutable.unseen_capacities[0] = 0
    assert "1w" not in optimized.compatible_codes(mutable)
    assert stats["projection_scopes"][0]["compatible_entries"] == 0


def test_scopes_and_cache_bounds_do_not_share_or_retain_projection_objects():
    import weakref
    stats = {"projection_scopes": []}
    kind = module.make_projection(vip._Projection, vip._counts_from_visible_tiles, stats)
    first, second = projection(kind, max_nodes=1), projection(kind, max_nodes=1)
    initial = state()
    for item in (initial, replace(initial), state()):
        first.compatible_codes(item)
    second.compatible_codes(initial)
    assert len(stats["projection_scopes"]) == 2
    assert all(row["count_entries"] <= 1 and row["compatible_entries"] <= 1
               for row in stats["projection_scopes"])
    assert stats["projection_scopes"][1]["compatible_hits"] == 0
    pointer = weakref.ref(first)
    del first
    assert pointer() is None


def test_exception_restore_releases_active_scope_and_all_bindings():
    previous = (vip._Projection, vip._counts_from_visible_tiles,
                view.RouteWaitingView.__post_init__)
    with pytest.raises(RuntimeError, match="上下文失败"):
        with module.installed() as (_, stats):
            optimized = projection()
            missing = state(unseen_capacities=None)
            with pytest.raises(vip.RouteHeuristicResearchError):
                optimized.waiting(missing)
            calls = stats["projection_scopes"][0]["count_calls"]
            vip._counts_from_visible_tiles(state().concealed)
            assert stats["projection_scopes"][0]["count_calls"] == calls
            raise RuntimeError("上下文失败")
    assert (vip._Projection, vip._counts_from_visible_tiles,
            view.RouteWaitingView.__post_init__) == previous
    assert stats["bindings_restored"]


def test_other_thread_does_not_use_waiting_scope_count_cache():
    # ContextVar 不跨线程传递；即使在等待入口内启动工作线程也不能串投影。
    class ThreadBoundary(vip._Projection):
        def waiting(self, current, *, qualification=True):
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(vip._counts_from_visible_tiles, current.concealed).result()

    original = vip._Projection
    vip._Projection = ThreadBoundary
    try:
        with module.installed() as (_, stats):
            result = projection().waiting(state())
            assert result == vip._counts_from_visible_tiles(state().concealed)
            assert stats["projection_scopes"][0]["count_calls"] == 0
    finally:
        vip._Projection = original


def test_native_waiting_alias_and_final_replacement_subclass_restore():
    """实际原生 MRO 验证；二进制缺失环境不把纯 Python 结果冒充原生门。"""
    import sys
    evidence = PATH.parent.parent
    native_dir = evidence / "t88-native-execution-prototype-1"
    if not any(native_dir.glob("build/lib/_t88_projection*.so")):
        pytest.skip("该环境未提供 T88 已验签原生制品")

    def load(name, path):
        binding = importlib.util.spec_from_file_location(name, path)
        result = importlib.util.module_from_spec(binding)
        binding.loader.exec_module(result)
        return result

    native = load("t129_unit_native", native_dir / "native_overlay.py")
    choices = load("t129_unit_choices", evidence / "t116-s02-completed-choice-cache-1/choice_cache.py")
    replacements = load("t129_unit_replacements", evidence / "t122-s02-completed-replacement-cache-1/replacement_cache.py")
    previous = vip._Projection
    with native.installed(native_candidate=False):
        native_projection = vip._Projection
        vip._Projection = replacements.make_projection(choices.make_projection(native_projection))
        try:
            initial = state(phase=ConditionalPhase.PUBLIC_WAIT)
            reference = projection()
            expected = [reference.waiting(initial, qualification=True),
                        reference.waiting(initial, qualification=False)]
            original_count = sys.modules["_t88_projection"]._counts_from_visible_tiles
            with module.installed() as (identity, stats):
                actual = projection()
                assert [actual.waiting(initial, qualification=True),
                        actual.waiting(initial, qualification=False)] == expected
                assert actual.code_width(("1w", "1w", "白"), initial) == 2
                assert identity["count_alias_modules"] == [
                    "hangma_bot.policy.route_vip_heuristic", "_t88_projection"]
            assert stats["bindings_restored"]
            assert stats["projection_scopes"][0]["count_hits"] > 0
            assert sys.modules["_t88_projection"]._counts_from_visible_tiles is original_count
        finally:
            vip._Projection = native_projection
    assert vip._Projection is previous
