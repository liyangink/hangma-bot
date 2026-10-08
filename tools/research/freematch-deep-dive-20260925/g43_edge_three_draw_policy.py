"""G43 离线策略：G30 改选仅在三摸条件容量严格增大时生效。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
from pathlib import Path
import time

import g7_three_self_draw_probe as g7
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import Tile


ROOT = _PROJECT_ROOT
G30_RELATIVE = 'tests/fixtures/research/freematch-deep-dive-20260925/candidates/G30-EDGE-TIE-ONEWHITE-V1.py'
G30_SHA = "bdfaf823e5b52718f3eefef5ac9972ee455dc9742dfda560c1b53f4e238ae7b2"


def _capacity(request, action_key: str, unseen: tuple[int, ...]) -> int:
    """只删去当前合法弃牌，后继仍调用生产牌形数学。"""
    hand = list(_build_context(request.observation).full_hand())
    hand.remove(Tile(action_key.split(":", 1)[1]))
    melds = len(request.observation.melds[request.observation.seat])
    return g7.favorable(counts_from_tiles(tuple(hand)), unseen, melds, 3)


class ThreeDrawFilterPolicy:
    """每个动作窗重新计算；无跨桌状态，异常保留冻结父代动作。"""

    policy_id = "g43-edge-three-draw-filter-v1"

    def __init__(self, baseline, edge, metrics: list[dict]):
        self.baseline = baseline
        self.edge = edge
        self.metrics = metrics

    async def choose(self, request, budget):
        """非持白摸打窗沿用 R18；G30 提议后才付三摸计算开销。"""
        baseline = await self.baseline.choose(request, budget)
        if request.window_key.phase.value != "draw":
            return baseline
        edge = await self.edge.choose(request, budget)
        if not baseline.candidates or not edge.candidates:
            self.metrics.append({"status": "failure", "reason": "empty_plan"})
            return baseline
        parent_key = baseline.candidates[0].action_key
        edge_key = edge.candidates[0].action_key
        if parent_key == edge_key:
            return baseline
        identity = {"decision_id": request.decision_id,
                    "round_no": request.window_key.round_no,
                    "trigger_seq": request.window_key.trigger_seq,
                    "parent_action": parent_key, "edge_action": edge_key}
        if not parent_key.startswith("discard:") or not edge_key.startswith("discard:"):
            self.metrics.append(dict(identity, status="failure", reason="non_discard_change"))
            return baseline
        legal = {candidate.action_key for candidate in request.rules.legal_candidates}
        if parent_key not in legal or edge_key not in legal:
            self.metrics.append(dict(identity, status="failure", reason="illegal_proposal"))
            return baseline
        started = time.perf_counter()
        try:
            unseen = count_unseen_tiles(request.observation)
            if any(type(value) is not int or value < 0 for value in unseen):
                raise ValueError("公开未见容量缺失")
            pool = tuple(unseen)
            parent_value = _capacity(request, parent_key, pool)
            edge_value = _capacity(request, edge_key, pool)
        except Exception as exc:
            self.metrics.append(dict(identity, status="failure", reason=type(exc).__name__,
                                     elapsed_ms=round((time.perf_counter() - started) * 1000, 3)))
            return baseline
        elapsed = (time.perf_counter() - started) * 1000
        delta = edge_value - parent_value
        self.metrics.append(dict(
            identity, status="adopted" if delta > 0 else "rejected",
            delta=delta, elapsed_ms=round(elapsed, 3),
            white_count=sum(tile.code == "白" for tile in
                            _build_context(request.observation).full_hand())))
        if len(self.metrics) % 16 == 0:
            g7.favorable.cache_clear()
            g7.summary.cache_clear()
        return edge if delta > 0 else baseline


def policy_factory(metrics: list[dict]):
    """验证 G30 源码摘要，再用与父代相同的面板时钟装配两套评分器。"""
    import paired_study

    source = _project_file(_PROJECT_ROOT, ROOT / G30_RELATIVE)
    if hashlib.sha256(source.read_bytes()).hexdigest() != G30_SHA:
        raise ValueError("G30 冻结候选源码漂移")
    baseline_factory = paired_study.policy_factory("r18_v2")
    edge_factory = paired_study.policy_factory("candidate@" + G30_RELATIVE)

    def build(monotonic):
        return ThreeDrawFilterPolicy(baseline_factory(monotonic),
                                     edge_factory(monotonic), metrics)

    return build
