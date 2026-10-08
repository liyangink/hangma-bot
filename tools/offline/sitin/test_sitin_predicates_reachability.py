# -*- coding: utf-8 -*-
"""可达性 + 选择性回归测试（P9/P9b/P9c，Lead 要求 4 与 P9c 要求 3/4）。

背景（三次同类缺陷，病根都是"冻结阈值/量在真实帧上不可达或不可分辨"）：
  - P9：wall_left 被投影成含保留区的公开余量 ⇒ 代价侧 ≤8 结构不可达、机会侧 ≥16 恒真；
  - P9b：gap 实测域只有 {−2,−1,0,1} ⇒ 原阈值对（≤1/≥2）恒真/恒假；
  - P9c：改用 Δsupp = support_remaining(b,f) − support_remaining(c,f)（域 [−71,+31]），
    并加"决策相关性"门槛（b 的动作后向听 ≤ PAIR_SHANTEN_MAX）——它是两侧**位置选择性**的来源。

本测试把"阈值可达 + 两侧互补 + 位置选择性"变成**机器断言**，数据源是真实帧样本
（probes/reachability-sample.json：只存**输入事实**，判定由当前生产谓词在测试时重算）：
  ① 每个分量 TRUE/FALSE 都非空（退化即红）；
  ② 新量阈值落在实测域**内部**、两侧互补（−16/−17、15/16）；
  ③ 两侧帧级命中率在声明带内（绝对带 0.1%–50%）；
  ④ **位置选择性**：侧逐根首命中帧的"首帧占比 < 50% 且中位数 > 1"；
  ⑤ **已登记退化清单**必须与实测一致（新增退化红；修好却没更新清单也红）；
  ⑥ 阈值冻结守卫 + 分量接线守卫 + 检查器自检 + 投影单位守卫。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import pathlib
import statistics
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_opportunities as opportunities  # noqa: E402
import sitin_predicates_v4 as P  # noqa: E402

REPO_ROOT = _HERE.parents[2]
SAMPLE_PATH = (_project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
               "/evidence/v4-impl/r9-fixes/P9-famcost/probes/reachability-sample.json"))

#: 声明区间（真实帧实测一次性选定；Lead 要求的绝对带 (0.1%, 50%) 另行硬断言）。
DECLARED_BANDS = {
    "side_open_rate": (0.02, 0.30),
    "side_cost_rate": (0.02, 0.30),
    "component_wall_open_rate": (0.85, 0.9995),
    "component_wall_cost_rate": (0.0005, 0.15),
    "pair_delta_open_rate": (0.20, 0.80),
    "pair_delta_cost_rate": (0.20, 0.80),
}
#: 已登记退化清单（P9c 换量后应为空；新增退化 ⇒ 红，修好却没清空 ⇒ 也红）。
DECLARED_DEGENERATE: dict = {}
ABSOLUTE_SIDE_BAND = (0.001, 0.50)
#: 位置选择性硬判据：首帧占比 < 50% 且首命中中位数 > 1。
POSITIONAL_FIRST_FRAME_SHARE_MAX = 0.50
POSITIONAL_MEDIAN_MIN = 1.0


def load_sample():
    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    families = payload["families"]
    codes = payload["codes"]
    state_of = {v: k for k, v in codes["shanten_state"].items()}
    route_of = {v: k for k, v in codes["route_status"].items()}
    progress_of = {v: k for k, v in codes["progress"].items()}
    frames = []
    for index, frame in enumerate(payload["frames"]):
        branches = []
        for position, row in enumerate(frame["b"]):
            progress = dict(zip(families,
                                [progress_of[v] for v in row[3:3 + len(families)]]))
            support = dict(zip(families, row[3 + len(families):]))
            branches.append({
                "action_key": "a{0}".format(position),
                "combined_shanten": row[0],
                "shanten_state": state_of[row[1]],
                "route_status": route_of[row[2]],
                "family_progress": progress,
                "support_remaining": support,
            })
        frames.append({"frame": index, "wall_left": frame["w"], "branches": branches})
    return payload, frames


def facts_of(frame):
    return {"wall_left": frame["wall_left"],
            "branches": [dict(branch) for branch in frame["branches"]]}


def _comparable(branch):
    state = branch.get("shanten_state")
    if not state:
        state = "known" if branch.get("combined_shanten") is not None else "unknown"
    return state == "known"


def pair_rows(branches, family="branch"):
    """结构合格对 → [(eligible, delta, b_shanten)]（P9c：Δsupp + 决策相关性门槛）。"""

    rows = []
    for b in branches:
        if b["route_status"] not in P._B_ROUTE_STATUSES or not _comparable(b):
            continue
        b_shanten = b.get("combined_shanten")
        for c in branches:
            if c["action_key"] == b["action_key"] or not _comparable(c):
                continue
            if not P._strict_pair(b["family_progress"][family],
                                  c["family_progress"][family]):
                continue
            eligible = b_shanten is not None and b_shanten <= P.PAIR_SHANTEN_MAX
            b_support = b["support_remaining"][family]
            c_support = c["support_remaining"][family]
            delta = (None if b_support is None or c_support is None
                     else int(b_support) - int(c_support))
            rows.append((eligible, delta, b_shanten))
    return rows


def _first_hit(first_open, first_cost, root_spans):
    """逐根首命中帧（样本按根顺序拼接，root_spans 给出每根帧数）。"""

    def _summary(first):
        starts = []
        cursor = 0
        for span in root_spans:
            starts.append((cursor, cursor + span))
            cursor += span
        values = []
        for start, end in starts:
            hit = next((first[i] for i in range(start, end) if i in first), None)
            # 样本按根顺序拼接，这里换算成**根内**帧号（与生产前缀行走的 frame 口径一致）。
            values.append(None if hit is None else hit - start + 1)
        hits = [v for v in values if v is not None]
        return {"roots": len(values), "hit_roots": len(hits),
                "frame1_share": (sum(1 for v in hits if v == 1) / len(hits)
                                 if hits else None),
                "median_first_frame": statistics.median(hits) if hits else None,
                "distribution": {str(k): hits.count(k) for k in sorted(set(hits))}}
    return {"open": _summary(first_open), "cost": _summary(first_cost)}


def check_reachability(frames, *, thresholds, root_spans=None, family="branch"):
    """在真实帧上检查阈值可达性、互补性与位置选择性；返回读数与退化清单。"""

    saved = (P.WALL_OPEN_MIN, P.WALL_COST_MAX, P.PAIR_SHANTEN_MAX,
             P.SUPPORT_DELTA_OPEN_MIN, P.SUPPORT_DELTA_COST_MAX)
    P.WALL_OPEN_MIN = thresholds["WALL_OPEN_MIN"]
    P.WALL_COST_MAX = thresholds["WALL_COST_MAX"]
    P.PAIR_SHANTEN_MAX = thresholds["PAIR_SHANTEN_MAX"]
    P.SUPPORT_DELTA_OPEN_MIN = thresholds["SUPPORT_DELTA_OPEN_MIN"]
    P.SUPPORT_DELTA_COST_MAX = thresholds["SUPPORT_DELTA_COST_MAX"]
    try:
        counts = {key: {"true": 0, "false": 0, "unknown": 0}
                  for key in ("open", "cost", "wall_open", "wall_cost", "gate")}
        pair = {key: {"true": 0, "false": 0} for key in (
            "delta_open", "delta_cost", "gate")}
        pair["domain"] = set()
        first_open = {}
        first_cost = {}
        for index, frame in enumerate(frames):
            results = P.evaluate_predicates(facts_of(frame))
            for key, predicate in (("open", "branch_open"), ("cost", "branch_cost")):
                value = results[predicate]["value"].lower()
                counts[key][value if value in counts[key] else "unknown"] += 1
                if value == "true":
                    if key == "open":
                        first_open.setdefault(index, frame["frame"])
                    else:
                        first_cost.setdefault(index, frame["frame"])
            wall = frame["wall_left"]
            if isinstance(wall, int):
                counts["wall_open"][
                    "true" if wall >= thresholds["WALL_OPEN_MIN"] else "false"] += 1
                counts["wall_cost"][
                    "true" if wall <= thresholds["WALL_COST_MAX"] else "false"] += 1
            rows = pair_rows(frame["branches"], family)
            counts["gate"]["true" if any(e for e, _d, _s in rows) else "false"] += 1
            for eligible, delta, _shanten in rows:
                # 决策相关性门槛在**对级**的可分辨性：合格对与"结构合格但被门槛排除"
                # 的对都必须非空（cap 过松 ⇒ 排除侧为 0 ⇒ 退化）。
                pair["gate"]["true" if eligible else "false"] += 1
                if not eligible or delta is None:
                    continue
                pair["domain"].add(delta)
                pair["delta_open"][
                    "true" if delta >= thresholds["SUPPORT_DELTA_OPEN_MIN"] else "false"] += 1
                pair["delta_cost"][
                    "true" if delta <= thresholds["SUPPORT_DELTA_COST_MAX"] else "false"] += 1
        readings = {
            "frames": len(frames),
            "side_open_rate": counts["open"]["true"] / max(1, len(frames)),
            "side_cost_rate": counts["cost"]["true"] / max(1, len(frames)),
            "component_wall_open_rate": counts["wall_open"]["true"] / max(1, len(frames)),
            "component_wall_cost_rate": counts["wall_cost"]["true"] / max(1, len(frames)),
            "pair_delta_open_rate": (pair["delta_open"]["true"]
                                     / max(1, pair["delta_open"]["true"]
                                           + pair["delta_open"]["false"])),
            "pair_delta_cost_rate": (pair["delta_cost"]["true"]
                                     / max(1, pair["delta_cost"]["true"]
                                           + pair["delta_cost"]["false"])),
            "counts": counts, "pair": pair,
        }
        readings["degenerate"] = {
            "side_open": counts["open"]["true"] == 0 or counts["open"]["false"] == 0,
            "side_cost": counts["cost"]["true"] == 0 or counts["cost"]["false"] == 0,
            "component_wall_open": (counts["wall_open"]["true"] == 0
                                    or counts["wall_open"]["false"] == 0),
            "component_wall_cost": (counts["wall_cost"]["true"] == 0
                                    or counts["wall_cost"]["false"] == 0),
            "pair_delta_open": (pair["delta_open"]["true"] == 0
                                or pair["delta_open"]["false"] == 0),
            "pair_delta_cost": (pair["delta_cost"]["true"] == 0
                                or pair["delta_cost"]["false"] == 0),
            "gate_decision_relevance": (pair["gate"]["true"] == 0
                                        or pair["gate"]["false"] == 0),
        }
        if root_spans:
            readings["first_hit"] = _first_hit(first_open, first_cost, root_spans)
    finally:
        (P.WALL_OPEN_MIN, P.WALL_COST_MAX, P.PAIR_SHANTEN_MAX,
         P.SUPPORT_DELTA_OPEN_MIN, P.SUPPORT_DELTA_COST_MAX) = saved
    return readings


@pytest.fixture(scope="module")
def sample():
    payload, frames = load_sample()
    spans = [int(root["frames"]) for root in payload["roots"]]
    thresholds = {"WALL_OPEN_MIN": P.WALL_OPEN_MIN, "WALL_COST_MAX": P.WALL_COST_MAX,
                  "PAIR_SHANTEN_MAX": P.PAIR_SHANTEN_MAX,
                  "SUPPORT_DELTA_OPEN_MIN": P.SUPPORT_DELTA_OPEN_MIN,
                  "SUPPORT_DELTA_COST_MAX": P.SUPPORT_DELTA_COST_MAX}
    readings = check_reachability(frames, thresholds=thresholds, root_spans=spans)
    return payload, frames, spans, readings


def test_side_rates_are_selective(sample):
    _payload, _frames, _spans, readings = sample
    for key in ("side_open_rate", "side_cost_rate"):
        low, high = DECLARED_BANDS[key]
        value = readings[key]
        assert low <= value <= high, (key, value)
        assert ABSOLUTE_SIDE_BAND[0] <= value <= ABSOLUTE_SIDE_BAND[1], (key, value)


def test_every_component_has_both_true_and_false(sample):
    _payload, _frames, _spans, readings = sample
    discovered = {key for key, value in readings["degenerate"].items() if value}
    assert discovered == set(DECLARED_DEGENERATE), (
        "退化分量集合与登记不一致：实测 {0} / 登记 {1}".format(
            sorted(discovered), sorted(DECLARED_DEGENERATE)))


def test_new_quantity_thresholds_inside_domain_and_complementary(sample):
    _payload, _frames, _spans, readings = sample
    domain = readings["pair"]["domain"]
    assert domain, "样本里没有任何合格对（无法判定可达性）"
    low, high = min(domain), max(domain)
    assert low <= P.SUPPORT_DELTA_OPEN_MIN <= high, (low, high)
    assert low <= P.SUPPORT_DELTA_COST_MAX <= high, (low, high)
    assert P.SUPPORT_DELTA_COST_MAX == P.SUPPORT_DELTA_OPEN_MIN - 1
    assert P.WALL_COST_MAX == P.WALL_OPEN_MIN - 1
    assert readings["pair_delta_open_rate"] + readings["pair_delta_cost_rate"] == 1.0
    for key in ("pair_delta_open_rate", "pair_delta_cost_rate",
                "component_wall_open_rate", "component_wall_cost_rate"):
        low_band, high_band = DECLARED_BANDS[key]
        assert low_band <= readings[key] <= high_band, (key, readings[key])


def test_positional_selectivity_is_hard_criterion(sample):
    """两侧都不得"首帧即命中"：首帧占比 < 50% 且首命中帧中位数 > 1。"""

    _payload, _frames, _spans, readings = sample
    first = readings["first_hit"]
    for side in ("open", "cost"):
        summary = first[side]
        assert summary["hit_roots"] == summary["roots"] >= 6, summary
        assert summary["frame1_share"] < POSITIONAL_FIRST_FRAME_SHARE_MAX, summary
        assert summary["median_first_frame"] > POSITIONAL_MEDIAN_MIN, summary


def test_thresholds_are_frozen_to_the_captured_sample(sample):
    payload, _frames, _spans, _readings = sample
    assert payload["thresholds_at_capture"] == {
        "WALL_OPEN_MIN": P.WALL_OPEN_MIN, "WALL_COST_MAX": P.WALL_COST_MAX,
        "PAIR_SHANTEN_MAX": P.PAIR_SHANTEN_MAX,
        "SUPPORT_DELTA_OPEN_MIN": P.SUPPORT_DELTA_OPEN_MIN,
        "SUPPORT_DELTA_COST_MAX": P.SUPPORT_DELTA_COST_MAX}


def test_checker_detects_degenerate_configs(sample):
    """检查器自检：喂退化配置必须报告退化（把断言摘掉即红）。"""

    _payload, frames, spans, _readings = sample
    base = {"WALL_OPEN_MIN": P.WALL_OPEN_MIN, "WALL_COST_MAX": P.WALL_COST_MAX,
            "PAIR_SHANTEN_MAX": P.PAIR_SHANTEN_MAX,
            "SUPPORT_DELTA_OPEN_MIN": P.SUPPORT_DELTA_OPEN_MIN,
            "SUPPORT_DELTA_COST_MAX": P.SUPPORT_DELTA_COST_MAX}
    for label, override, expected in (
            ("Δ 阈值越域上侧（open 恒假）",
             {"SUPPORT_DELTA_OPEN_MIN": 999, "SUPPORT_DELTA_COST_MAX": 1000},
             "pair_delta_open"),
            ("Δ 阈值越域下侧（cost 恒假）",
             {"SUPPORT_DELTA_OPEN_MIN": -999, "SUPPORT_DELTA_COST_MAX": -998},
             "pair_delta_cost"),
            ("墙阈越域（cost 墙 ≤ −1）", {"WALL_COST_MAX": -1},
             "component_wall_cost"),
            ("决策相关性门槛越域（cap=99）", {"PAIR_SHANTEN_MAX": 99},
             "gate_decision_relevance")):
        thresholds = dict(base, **override)
        readings = check_reachability(frames, thresholds=thresholds, root_spans=spans)
        assert readings["degenerate"][expected], (label, readings["degenerate"])


def test_positional_checker_can_see_a_non_selective_config(sample):
    """位置选择性自检：把决策相关性门槛摘掉后，检查器必须**看得见**首帧即命中回归。

    这条把"位置选择性断言"变成有分辨力的度量：门槛一旦被摘掉（或断言被改成恒真），
    本用例即红。
    """

    _payload, frames, spans, readings = sample
    assert readings["first_hit"]["open"]["frame1_share"] == 0.0
    broken = check_reachability(
        frames, root_spans=spans,
        thresholds={"WALL_OPEN_MIN": P.WALL_OPEN_MIN, "WALL_COST_MAX": P.WALL_COST_MAX,
                    "PAIR_SHANTEN_MAX": 99,
                    "SUPPORT_DELTA_OPEN_MIN": P.SUPPORT_DELTA_OPEN_MIN,
                    "SUPPORT_DELTA_COST_MAX": P.SUPPORT_DELTA_COST_MAX})
    assert broken["degenerate"]["gate_decision_relevance"] is True
    assert broken["first_hit"]["open"]["frame1_share"] >= POSITIONAL_FIRST_FRAME_SHARE_MAX


def test_new_quantity_is_wired_into_both_sides():
    """分量接线守卫：两帧只差 Δsupp / 墙 / 决策相关性时必须按冻结边界翻转。"""

    def facts(*, wall=20, b_shanten=1, b_support=4, c_support=None):
        c_support = b_support if c_support is None else c_support
        progress = {family: "SAME" for family in P.FAMILIES}
        retreat = {family: "RETREAT" for family in P.FAMILIES}

        def branch(key, shanten, value, support):
            return {"action_key": key, "combined_shanten": shanten,
                    "shanten_state": "known", "route_status": "WITNESSED",
                    "family_progress": value,
                    "support_remaining": {family: support for family in P.FAMILIES}}

        return {"wall_left": wall,
                "branches": [branch("b", b_shanten, progress, b_support),
                             branch("c", b_shanten + 1, retreat, c_support)]}

    balanced = P.evaluate_predicates(facts())                      # Δsupp = 0
    assert balanced["branch_open"]["value"] == "TRUE"
    assert balanced["branch_cost"]["value"] == "FALSE"
    starved = P.evaluate_predicates(facts(b_support=4, c_support=21))   # Δsupp = −17
    assert starved["branch_open"]["value"] == "FALSE"
    assert starved["branch_cost"]["value"] == "TRUE"
    at_edge = P.evaluate_predicates(facts(b_support=4, c_support=20))   # Δsupp = −16
    assert at_edge["branch_open"]["value"] == "TRUE"
    assert at_edge["branch_cost"]["value"] == "FALSE"
    assert P.evaluate_predicates(
        facts(wall=P.WALL_COST_MAX))["branch_cost"]["value"] == "TRUE"
    assert P.evaluate_predicates(
        facts(wall=P.WALL_OPEN_MIN))["branch_cost"]["value"] == "FALSE"
    outside = P.evaluate_predicates(facts(b_shanten=P.PAIR_SHANTEN_MAX + 1,
                                          b_support=4, c_support=21))
    assert outside["branch_open"]["value"] == "FALSE"
    assert outside["branch_cost"]["value"] == "FALSE"
    assert outside["branch_cost"]["missing"] is None


def test_projection_unit_is_pinned(sample):
    """投影单位守卫：wall_left 必须仍是「可摸牌墙余量」（P9 缺陷不得回归）。"""

    payload, frames, _spans, _readings = sample
    reserve = payload["projection"]["reserve_tiles"]
    assert reserve == opportunities.wall_reserve_tiles() == 20
    assert opportunities.wall_left_drawable(83) == 63
    assert opportunities.wall_left_drawable(20) == 0
    assert opportunities.wall_left_drawable(15) == 0
    assert opportunities.wall_left_drawable(None) is None
    assert payload["projection"]["wall_left"] == (
        "max(0, observation.remaining_tile_count - 20)")
    walls = [frame["wall_left"] for frame in frames]
    assert min(walls) >= 0 and max(walls) <= 63
