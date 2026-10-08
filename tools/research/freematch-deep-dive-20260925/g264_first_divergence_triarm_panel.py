#!/usr/bin/env python3
"""G264：冻结 G49 首次改弃、持续改弃与当前规则父代的离线同墙三臂面板。

每个池×根×焦点座位运行 A/B/C，各阶段两张完整八局桌。B 的一次改弃
在每张桌开始时重置；C 仍逐窗调用未修改的 G49 选择器。不得用于线上装配。
"""

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

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import random
from typing import Any

import g14_accounted_paired_panel as panel
import g49_natural_route_policy as frozen_g49
import g261_current_rules_panel as current
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
ARMS = (current.RESEARCH_PARENT_ARM, "g49_first_discard_then_r18",
        "g49_continuous")
CONTRASTS = (("B-A", ARMS[1], ARMS[0]),
             ("C-B", ARMS[2], ARMS[1]),
             ("C-A", ARMS[2], ARMS[0]))
INPUTS = (
    "review/freematch-deep-dive-20260925/G263-FIRST-DIVERGENCE-ROUTE-VALUE-DESIGN-2026-09-29.md",
    'tools/research/freematch-deep-dive-20260925/g264_first_divergence_triarm_panel.py',
    'tools/research/freematch-deep-dive-20260925/g261_current_rules_panel.py',
    'tools/research/freematch-deep-dive-20260925/g193_early_shape_policy.py',
    'tools/research/freematch-deep-dive-20260925/g49_natural_route_policy.py',
    'tools/research/freematch-deep-dive-20260925/g40_official_natural_gap_reach.py',
)


def digest(path: Path) -> str:
    """返回源码字节的 SHA-256；清单重跑时据此拒绝执行身份漂移。"""

    return sha256(path.read_bytes()).hexdigest()


class _FixedParentPlan:
    """向冻结 G49 包装器提供本窗已计算的 R18 合法保底计划。"""

    def __init__(self, plan: Any) -> None:
        self.plan = plan

    async def choose(self, _request: Any, _budget: Any) -> Any:
        """返回当前窗 R18 计划；无副作用，不重复评分。"""

        return self.plan


class FirstDivergencePolicy:
    """离线逐桌包装器；B 改弃一次后回父代，C 每窗重用冻结 G49 行为。"""

    def __init__(self, *, arm: str, baseline: Any, table_id: str) -> None:
        if arm not in ARMS[1:]:
            raise ValueError("G264 包装器只接受 B/C 臂")
        self.arm = arm
        self.baseline = baseline
        self.table_id = table_id
        self.policy_id = "action_value_v1:research:g264:" + arm
        self.max_operations = getattr(baseline, "max_operations", None)
        self.events: list[dict[str, Any]] = []
        self.changed_count = 0
        self.first_divergence: dict[str, Any] | None = None

    async def choose(self, request: Any, budget: Any) -> Any:
        """先建合法 R18 计划；G49 缺事实或异常沿其冻结回退逻辑返回父代。"""

        parent = await self.baseline.choose(request, budget)
        if self.arm == ARMS[1] and self.changed_count:
            return parent
        events: list[dict[str, Any]] = []
        route = frozen_g49.NaturalRoutePolicy(_FixedParentPlan(parent), events)
        selected = await route.choose(request, budget)
        for event in events:
            status = event.get("status")
            if status not in ("adopted", "fallback"):
                raise ValueError("G49 返回未知指标状态")
            recorded = {"table_id": self.table_id, **event}
            if status == "adopted":
                if not parent.candidates or not selected.candidates:
                    raise ValueError("G49 改弃缺少候选计划")
                parent_key = parent.candidates[0].action_key
                chosen_key = selected.candidates[0].action_key
                if (chosen_key == parent_key or chosen_key != event.get("action")
                        or chosen_key not in {item.action_key for item in
                                              request.rules.legal_candidates}):
                    raise ValueError("G49 改弃身份或合法性不符")
                recorded.update(parent_action=parent_key,
                                action=chosen_key,
                                game_id=request.window_key.game_id,
                                round_no=request.window_key.round_no,
                                trigger_seq=request.trigger_seq)
                self.changed_count += 1
                if self.first_divergence is None:
                    self.first_divergence = {
                        name: recorded[name] for name in
                        ("table_id", "decision_id", "game_id", "round_no",
                         "trigger_seq", "parent_action", "action")}
            self.events.append(recorded)
        return selected

    def summary(self) -> dict[str, Any]:
        """保留逐桌首次实际分歧和全部实际改选／异常回退事件。"""

        return {"table_id": self.table_id,
                "first_divergence": self.first_divergence,
                "changed_count": self.changed_count,
                "events": self.events}


def run_unit(unit: tuple[str, int, int, str, int]) -> dict[str, Any]:
    """复用 G14 八局结算执行器；每桌策略实例和首次标志均独立。"""

    mix, root, seat, arm, panel_seed = unit
    if arm not in ARMS:
        raise ValueError("G264 未知臂")
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)
    policies: list[FirstDivergencePolicy] = []

    def factory(monotonic: Any) -> Any:
        """自然面板按桌顺序调用一次；超额装配立即失败，避免指标错桌。"""

        if len(policies) >= len(plans):
            raise ValueError("G264 策略实例数超过桌计划")
        policy = FirstDivergencePolicy(
            arm=arm, baseline=current.research_parent_factory(monotonic),
            table_id=plans[len(policies)].table_id)
        policies.append(policy)
        return policy

    stage = panel.accounted.run_accounted_stage(
        plans=plans,
        candidate_policy_factory=(current.research_parent_factory
                                  if arm == ARMS[0] else factory),
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    stage["route_tables"] = (
        [{"table_id": plan.table_id, "first_divergence": None,
          "changed_count": 0, "events": []} for plan in plans]
        if arm == ARMS[0] else [policy.summary() for policy in policies])
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest(args: argparse.Namespace) -> dict[str, Any]:
    """冻结当前规则、R18/G49 源码、入口及牌山身份，不继承旧发布资格。"""

    if sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest() != (
            R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("G264 冻结 R18 v2 评分源码摘要漂移")
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    frozen = panel._manifest(
        args=args, arms=ARMS,
        tables_per_stage=int(contract["group"]["tables_per_group"]))
    frozen.update({
        "schema": "g264-first-divergence-triarm-manifest/1",
        "r18_v2_release_id": None,
        "parent_binding": "research_current_rules_not_release_package",
        "parent_algorithm_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "g49_selector_sha256": digest(_project_file(_PROJECT_ROOT, HERE / "g49_natural_route_policy.py")),
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "smoke_roots": [1, 2], "development_roots": [3, 34],
        "confirmation_roots": [35, 66],
        "boundary": "纯离线研究；冒烟根不作效果判定；旧发布守卫及线上策略不变。",
    })
    frozen["input_identity"].update({path: digest(_project_file(_PROJECT_ROOT, ROOT / path)) for path in INPUTS})
    return frozen


def verify_unit(row: dict[str, Any], *, unit: tuple[str, int, int, str, int],
                tables_per_stage: int) -> None:
    """核八局拆账、合法动作、逐桌指标及 B 的单次改弃上限。"""

    panel.verify_unit(row, unit=unit, tables_per_stage=tables_per_stage)
    stage = row["stage"]
    metrics = stage.get("route_tables")
    if not isinstance(metrics, list) or len(metrics) != tables_per_stage:
        raise ValueError("G264 逐桌指标缺失")
    for table, route in zip(stage["tables"], metrics):
        account = table["hand_account"]
        if account.get("complete_hands") != 8 or len(table["hand_records"]) != 8:
            raise ValueError("G264 必须完成完整八局")
        recalculated = panel.accounted.summarize_hands(
            table["hand_records"], focal_seat=account["focal_seat"],
            initial_scores=(0, 0, 0, 0), final_scores=table["scores_by_seat"],
            expected_hands=8)
        if recalculated != account:
            raise ValueError("G264 逐局零和／完整桌拆账复核失败")
        events = route.get("events")
        if route.get("table_id") != table["table_id"] or not isinstance(events, list):
            raise ValueError("G264 指标与桌身份不符")
        adopted = [event for event in events if event.get("status") == "adopted"]
        if any(event.get("table_id") != table["table_id"]
               or event.get("status") not in ("adopted", "fallback")
               for event in events):
            raise ValueError("G264 改选／回退事件身份异常")
        if route.get("changed_count") != len(adopted):
            raise ValueError("G264 改选计数与逐决策事件不符")
        first = route.get("first_divergence")
        if bool(adopted) != (first is not None):
            raise ValueError("G264 首次分歧缺失")
        if first is not None and any(first.get(name) != adopted[0].get(name)
                                     for name in first):
            raise ValueError("G264 首次分歧与实际首改选不符")
        if unit[3] == ARMS[0] and (events or first or route["changed_count"]):
            raise ValueError("G264 A 臂不应有 G49 改选")
        if unit[3] == ARMS[1] and route["changed_count"] > 1:
            raise ValueError("G264 B 臂整桌最多改弃一次")
        runtime = table["result"]["runtime_counts"]
        for field in ("illegal_choices", "fallbacks", "timeouts", "auto_actions"):
            if type(runtime.get(field)) is not int or runtime[field] != 0:
                raise ValueError("G264 实际执行偏离计划或存在非法行动：" + field)


def verify_triplet(rows: dict[str, dict[str, Any]],
                   routes: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """核同墙三臂首次动作一致；无首次分歧必须有相同完整八局结算。"""

    if set(rows) != set(ARMS) or set(routes) != set(ARMS):
        raise ValueError("G264 三臂完整桌不齐")
    ids = {row["table_id"] for row in rows.values()}
    seeds = {row["seed"] for row in rows.values()}
    game_keys = {json.dumps(row["result"]["game_key"], sort_keys=True)
                 for row in rows.values()}
    rule_hashes = {row["result"]["versions"]["rules_hash"] for row in rows.values()}
    if len(ids) != 1 or len(seeds) != 1 or len(game_keys) != 1 or len(rule_hashes) != 1:
        raise ValueError("G264 三臂牌山／规则身份不一致")
    first_b = routes[ARMS[1]]["first_divergence"]
    first_c = routes[ARMS[2]]["first_divergence"]
    stable_first_fields = ("table_id", "game_id", "round_no", "trigger_seq",
                           "parent_action", "action")
    if ((first_b is None) != (first_c is None)
            or (first_b is not None and any(first_b.get(key) != first_c.get(key)
                                            for key in stable_first_fields))):
        raise ValueError("G264 B/C 首次改弃身份或动作不同")
    if first_b is None:
        if any(rows[arm]["scores_by_seat"] != rows[ARMS[0]]["scores_by_seat"]
               or rows[arm]["hand_records"] != rows[ARMS[0]]["hand_records"]
               for arm in ARMS[1:]):
            raise ValueError("G264 未触发桌三臂结算不同")
    return first_b


def _table_delta(rows: dict[str, dict[str, Any]], name: str) -> float:
    _, high, low = next(item for item in CONTRASTS if item[0] == name)
    return (rows[high]["hand_account"]["focal_table_delta"]
            - rows[low]["hand_account"]["focal_table_delta"])


def _root_interval(values_by_mix: dict[str, list[float]], seed: int) -> list[float] | None:
    """按 H/M 各自牌山根重采样；冒烟仅一根时不输出伪区间。"""

    if any(len(values_by_mix[mix]) < 2 for mix in panel.MIXES):
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(2000):
        drawn = [rng.choice(values_by_mix[mix]) for mix in panel.MIXES
                 for _ in values_by_mix[mix]]
        estimates.append(sum(drawn) / len(drawn))
    estimates.sort()
    return [estimates[49], estimates[1949]]


def result(*, args: argparse.Namespace,
           units: list[tuple[str, int, int, str, int]], out: Path,
           tables_per_stage: int) -> dict[str, Any]:
    """先核三臂逐桌首次分歧，再按 H/M×牌山根聚合全部自然桌。"""

    base = panel._result(args=args, arms=ARMS, units=units,
                         out=out, tables_per_stage=tables_per_stage)
    grouped: dict[tuple[str, int, int], dict[str, dict[str, Any]]] = {}
    for unit in units:
        row = json.loads(panel.paired.unit_path(out, unit).read_text(encoding="utf-8"))
        verify_unit(row, unit=unit, tables_per_stage=tables_per_stage)
        grouped.setdefault(unit[:3], {})[unit[3]] = row
    tables = []
    root_values: dict[tuple[str, int, str], list[float]] = {}
    for (mix, root, seat), arms in sorted(grouped.items()):
        if set(arms) != set(ARMS):
            raise ValueError("G264 三臂阶段不齐")
        for index in range(tables_per_stage):
            rows = {arm: arms[arm]["stage"]["tables"][index] for arm in ARMS}
            routes = {arm: arms[arm]["stage"]["route_tables"][index] for arm in ARMS}
            first_b = verify_triplet(rows, routes)
            deltas = {name: _table_delta(rows, name) for name, _, _ in CONTRASTS}
            if any(deltas[name] != 0 for name in deltas) and first_b is None:
                raise ValueError("G264 未触发桌出现积分效应")
            for name, value in deltas.items():
                root_values.setdefault((mix, root, name), []).append(value)
            tables.append({
                "mix": mix, "root_index": root, "focal_seat": seat,
                "table_index": index + 1, "table_id": rows[ARMS[0]]["table_id"],
                "seed": rows[ARMS[0]]["seed"], "first_divergence": first_b,
                "changed_count_by_arm": {arm: routes[arm]["changed_count"] for arm in ARMS},
                "fallback_count_by_arm": {arm: sum(event["status"] == "fallback"
                                                   for event in routes[arm]["events"])
                                          for arm in ARMS},
                "hand_account_by_arm": {arm: rows[arm]["hand_account"] for arm in ARMS},
                "runtime_counts_by_arm": {arm: rows[arm]["result"]["runtime_counts"]
                                          for arm in ARMS},
                "score_delta": deltas,
            })
    if len(tables) != len(panel.MIXES) * args.roots_per_mix * len(panel.SEATS) * tables_per_stage:
        raise ValueError("G264 三臂完整桌配对数不足")
    root_rows = []
    for root in base["root_clusters"]:
        mix, number = root["mix"], root["root_index"]
        values = {name: root_values[(mix, number, name)] for name, _, _ in CONTRASTS}
        if any(len(item) != len(panel.SEATS) * tables_per_stage
               for item in values.values()):
            raise ValueError("G264 根内换座或阶段桌不齐")
        root_rows.append({"mix": mix, "root_index": number,
                          "mean_delta_per_table": {
                              name: sum(item) / len(item) for name, item in values.items()},
                          "component_mean_by_arm": root["component_mean_by_arm"],
                          "table_score_mean_by_arm": root["table_score_mean_by_arm"]})
    by_mix = {mix: {name: [row["mean_delta_per_table"][name]
                           for row in root_rows if row["mix"] == mix]
                    for name, _, _ in CONTRASTS} for mix in panel.MIXES}
    contrasts = {}
    for offset, (name, high, low) in enumerate(CONTRASTS):
        values = [table["score_delta"][name] for table in tables]
        affected = [table["score_delta"][name] for table in tables
                    if table["first_divergence"] is not None]
        root_means = {mix: by_mix[mix][name] for mix in panel.MIXES}
        mean = sum(values) / len(values)
        frequency = len(affected) / len(values)
        conditional = None if not affected else sum(affected) / len(affected)
        if abs(mean - frequency * (conditional or 0.0)) > 1e-9:
            raise ValueError("G264 首次分歧频率拆解不守恒")
        contrasts[name] = {
            "high_arm": high, "low_arm": low,
            "all_table_mean": mean,
            "root_mean": sum(sum(group) for group in root_means.values()) /
                         sum(len(group) for group in root_means.values()),
            "root_bootstrap_95_interval": _root_interval(root_means, args.panel_seed + offset),
            "tail": {"positive_tables": sum(value > 0 for value in values),
                     "negative_tables": sum(value < 0 for value in values),
                     "zero_tables": sum(value == 0 for value in values),
                     "min": min(values), "max": max(values)},
            "first_divergence_rate": frequency,
            "mean_given_first_divergence": conditional,
            "rate_times_conditional_mean": frequency * (conditional or 0.0),
            "component_mean_delta": {
                component: sum(root["component_mean_by_arm"][high][component]
                               - root["component_mean_by_arm"][low][component]
                               for root in root_rows) / len(root_rows)
                for component in panel.COMPONENTS},
        }
        if abs(sum(contrasts[name]["component_mean_delta"].values()) - mean) > 1e-9:
            raise ValueError("G264 三臂收益分量差不守恒")
    base.update({"schema": "g264-first-divergence-triarm-result/1",
                 "table_pairs": tables, "root_clusters": root_rows,
                 "contrasts": contrasts,
                 "triggered_tables": sum(table["first_divergence"] is not None for table in tables),
                 "c_additional_changes_after_first": sum(
                     max(0, table["changed_count_by_arm"][ARMS[2]] - 1)
                     for table in tables),
                 "boundary": "冒烟根只验装配与守恒；根级区间仅供开发描述，发布另需独立确认。"})
    return base


def main() -> None:
    """冻结清单后串行或低并发运行；失败阶段留痕但不进入效果汇总。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--panel-seed", type=int, required=True)
    parser.add_argument("--root-start", type=int, required=True)
    parser.add_argument("--roots-per-mix", type=int, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if (args.panel_seed != 2026122964 or args.root_start < 1
            or args.roots_per_mix < 1
            or args.root_start + args.roots_per_mix - 1 > 66
            or not 1 <= args.workers <= 2 or args.max_new_units < 0):
        parser.error("G264 种子固定 2026122964；根限 1..66；workers 限 1..2")
    frozen = manifest(args)
    panel._write_new(args.out / "manifest.json", frozen)
    units = [(mix, root, seat, arm, args.panel_seed)
             for mix in panel.MIXES
             for root in range(args.root_start, args.root_start + args.roots_per_mix)
             for seat in panel.SEATS for arm in ARMS]
    pending = []
    for unit in units:
        path = panel.paired.unit_path(args.out, unit)
        if path.exists():
            verify_unit(json.loads(path.read_text(encoding="utf-8")), unit=unit,
                        tables_per_stage=frozen["tables_per_stage"])
        else:
            pending.append(unit)
    if args.max_new_units:
        pending = pending[:args.max_new_units]
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for future in as_completed(futures):
                unit = futures[future]
                row = None
                try:
                    row = future.result()
                    verify_unit(row, unit=unit,
                                tables_per_stage=frozen["tables_per_stage"])
                except Exception as exc:
                    diagnostic = {"schema": "g264-unit-error/1",
                                  "unit": list(unit),
                                  "error": f"{type(exc).__name__}: {exc}",
                                  "partial_row": row}
                    encoded = json.dumps(diagnostic, ensure_ascii=False, sort_keys=True)
                    error_path = panel.paired.unit_path(args.out, unit)
                    target = args.out / "errors" / (
                        error_path.stem + "-" + sha256(encoded.encode()).hexdigest()[:16]
                        + ".json")
                    panel._write_new(target, diagnostic)
                    raise
                panel._write_new(panel.paired.unit_path(args.out, unit), row)
                print(json.dumps({"completed_unit": list(unit[:4])}), flush=True)
    if any(not panel.paired.unit_path(args.out, unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "units_complete": len(units) -
                          sum(not panel.paired.unit_path(args.out, unit).exists()
                              for unit in units)}), flush=True)
        return
    summary = result(args=args, units=units, out=args.out,
                     tables_per_stage=frozen["tables_per_stage"])
    summary["manifest_sha256"] = digest(args.out / "manifest.json")
    panel._write_new(args.out / "result.json", summary)
    print(json.dumps({"complete_tables": summary["complete_tables"],
                      "independent_root_clusters": summary["independent_root_clusters"],
                      "triggered_tables": summary["triggered_tables"],
                      "contrasts": {name: row["all_table_mean"]
                                    for name, row in summary["contrasts"].items()}},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
