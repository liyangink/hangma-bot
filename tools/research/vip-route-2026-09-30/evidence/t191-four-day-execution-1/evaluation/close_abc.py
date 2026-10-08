"""三组全批自然闭合后验证缓存、实际评分、forcing和结算，统一分账，不重评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/evaluation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import fcntl
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from abc_support import *
from run_abc import valid_score_row


def account(result, seat):
    """按模拟规则公开结算分账；向量物理座位0—3，大牌为四番及以上。"""
    settlement = result["settlement"]
    delta = settlement["score_delta"]
    require(len(delta) == 4 and all(type(v) is int for v in delta) and sum(delta) == 0, "积分向量不同")
    values = {"net": delta[seat], "ordinary_hu_income": 0, "large_hu_income": 0,
        "payments": 0, "own_hu": 0, "other_hu": 0, "draws": 0}
    if settlement["is_draw"]:
        require(delta == [0, 0, 0, 0], "流局有支付")
        values["draws"] = 1
    elif settlement["winner_seat"] == seat:
        require(delta[seat] > 0, "本人Hu无正支付")
        values["own_hu"] = 1
        values["large_hu_income" if settlement["fan"] >= 4 else "ordinary_hu_income"] = delta[seat]
    else:
        require(delta[seat] <= 0, "他家Hu本人收到正支付")
        values["other_hu"] = 1
        values["payments"] = delta[seat]
    require(values["net"] == result["focal_net_score"] == values["ordinary_hu_income"] + values["large_hu_income"] + values["payments"], "净积分分账未闭合")
    return values


def verify_scores(directory, closed, plan, *, verify_settlement=True):
    """逐字节读回完整公开图及实际评分；forced行独立核对，不授其完整评分标签。"""
    views, records, forces = {}, defaultdict(list), defaultdict(list)
    with gzip.open(directory / "views.jsonl.gz", "rt") as stream:
        for line in stream:
            saved = json.loads(line)
            require(sha(saved["view"]) == saved["view_sha256"] and len(canonical(saved["view"])) == saved["json_bytes"], "实际缓存摘要不同")
            require(saved["view_sha256"] not in views, "去重缓存重复")
            views[saved["view_sha256"]] = saved["view"]
    rows, calls, forced_count = 0, 0, 0
    with gzip.open(directory / "decisions.jsonl.gz", "rt") as stream:
        for line in stream:
            item = json.loads(line)
            row, arm, sample = item["row"], item["arm"], item["sample"]
            if row["record_kind"] == "forced_first_action":
                require(arm == "B" and row["c_self_scored"] is False and row["actual_formula_full_scored"] is False
                    and row["scoring_calls"] == [] and row["force_count"] == 1, "forcing冒充完整评分")
                forces[sample, arm].append(row)
                forced_count += 1
                continue
            require(row["record_kind"] == "formula_score" and valid_score_row(row), "存在缺失完整评分")
            require(row["c_self_scored"] is (arm == "C"), "非C自行选择冒充c_self_scored")
            source_name = "child" if arm in ("selector", "C") else "parent"
            require(row["score_source_name"] == source_name and row["policy_id"] == "vip:" + plan["arms_sources"][source_name]["identity"]["candidate_id"], "实际评分公式身份不同")
            call = row["scoring_calls"][0]
            require(type(call["candidate_operations"]) is int and 0 <= call["candidate_operations"] <= 4800000, "评分操作超限")
            view = views[call["input_capture"]["view_sha256"]]
            roots, entries = [a["action_key"] for a in view["actions"]], row["candidates"]
            require(len(roots) == len(set(roots)) and sorted(roots) == sorted(row["legal_action_keys"])
                == sorted(call["scored_action_keys"]) == sorted(e["action_key"] for e in entries), "完整合法根或评分根不同")
            require(all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries), "非有限评分")
            require(row["selected_action_key"] == entries[0]["action_key"], "实际公式首选不同")
            records[sample, arm].append(row)
            rows += 1
            calls += call["actual_score_calls"]
    require(rows == closed["counts"]["scored_decisions"] and calls == closed["counts"]["actual_score_calls"]
        == closed["capture"]["store_calls"] and len(views) == closed["capture"]["unique_views_saved"], "评分或缓存费用分母不同")
    require(closed["capture"]["terminal"]["terminal_valid"] and forced_count == closed["counts"]["forced_first_actions"], "缓存终态或强制分母不同")
    selector = records[None, "selector"]
    require(len(selector) == closed["counts"]["selector_score_calls"] == 1, "公共首手候选评分不唯一")
    selector = selector[0]
    target_window = closed["target"]["case"]["window_key"]
    for result in closed["results"]:
        sample, arm = result["sample"], result["arm"]
        local = records[sample, arm]
        require(len(local) == result["focal_score_calls"] > 0, "单组实际评分分母不同")
        outcome = read(directory / f"sample-{sample}-{arm}-OUTCOME.json")
        require(outcome["status"] == "complete" and outcome["completed_hands"] == target_window["round_no"]
            and all(type(v) is int and v == 0 for v in outcome["runtime_counts"].values()), "原结果未完整或故障")
        own = [d for d in outcome["decisions"] if d["seat"] == closed["target"]["focal_seat"]]
        require(len(own) == len(local), "实际动作和公式评分数量不同")
        for actual, row in zip(own, local):
            require(actual["window_key"] == row["window_key"] and actual["legal"] is True and actual["fallback_reason"] is None, "实际动作窗口/合法性不同")
            is_forced = arm == "B" and row["window_key"] == target_window
            require(actual["action_key"] == (selector["selected_action_key"] if is_forced else row["selected_action_key"]), "实际后续动作不是委托首选")
            require(list(actual["degraded_reasons"]) == (["offline_counterfactual_force_first:" + selector["selected_action_key"]] if is_forced else []), "存在未声明降级")
        first = next(r for r in local if r["window_key"] == target_window)
        require(first["observation"] == closed["target"]["case"]["observation"] and
            first["scoring_calls"][0]["input_capture"]["view_sha256"] == closed["target"]["case"]["view_sha256"], "公共首手输入不同")
        if arm == "C":
            require(first["candidates"] == selector["candidates"], "候选同公开首手评分不同")
        if arm == "B":
            require(len(forces[sample, arm]) == result["forced_count"] == 1
                and forces[sample, arm][0]["window_key"] == target_window
                and forces[sample, arm][0]["selected_action_key"] == result["first_actual"], "B并非仅干预首手")
            reference = next(r for r in records[sample, "A"] if r["window_key"] == target_window)
            require(first["candidates"] == reference["candidates"], "A/B委托S02首手原分不同")
        else:
            require(not forces[sample, arm] and result["forced_count"] == 0, "A/C出现forcing")
        if verify_settlement:
            require(outcome["final_scores"] == result["settlement"]["scores_after"], "单局端点积分与规则结算不同")
    return {"complete": True, "actual_score_calls": calls, "full_score_rows": rows,
        "forced_rows_separately_verified": forced_count, "unique_views": len(views), "rescoring_calls": 0}


def summarize(pairs):
    """按公开母来源保留相关性，汇总三项对照；不给自然总体频率或强度区间。"""
    groups, totals = defaultdict(list), {name: Counter() for name in ("B_minus_A", "C_minus_A", "C_minus_B")}
    for row in pairs:
        groups[row["root_id"]].append(row)
        for name in totals:
            totals[name].update(row[name])
    return {"public_start_pairs": len(pairs), "mother_source_groups": len(groups),
        "sum_deltas": {k: dict(v) for k, v in totals.items()},
        "source_groups": [{"root_id": root, "public_start_pairs": len(rows),
            "sum_deltas": {name: {metric: sum(row[name][metric] for row in rows) for metric in rows[0][name]}
                for name in totals}} for root, rows in sorted(groups.items())],
        "natural_population_estimate_or_independent_strength_admission": False}


def main(args):
    """要求真实进程终态和资源释放，再统一读分；缺失或失败不重抽、不启动下一阶段。"""
    background_priority()
    plan_path, output, dispatch_path = Path(args.plan).resolve(), Path(args.output).resolve(), Path(args.dispatch_closed).resolve()
    plan, dispatch = read(plan_path), read(dispatch_path)
    require(unchanged(plan) and dispatch["complete"] and dispatch["worker_returncodes"] == [0] * 4
        and dispatch["all_processes_naturally_waited"] and dispatch["plan_pin"] == pin(plan_path), "全批真实进程尚未闭合")
    for path in resource_slot_paths(OLD, 4):
        with path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for slot in range(4):
        start, closed = (read(output / f"worker-{slot}" / name) for name in ("START.json", "CLOSE.json"))
        lane = list(range(slot + 1, len(plan["targets"]) + 1, 4))
        require(closed["complete"] and closed["failure"] is None and start["targets"] == closed["attempted"] == closed["completed"] == lane
            and start["pid"] == closed["pid"] == dispatch["children"][slot] and start["plan_pin"] == pin(plan_path), "worker分片或真实身份不同")
    counts, pairs, audits, files = Counter(), [], [], {str(dispatch_path): pin(dispatch_path)}
    for index, target in enumerate(plan["targets"], 1):
        directory = output / f"target-{index:03d}"
        start, closed = read(directory / "START.json"), read(directory / "CLOSURE.json")
        require(start["plan_pin"] == pin(plan_path) and start["target"] == closed["target"] == target and
            closed["complete"] and closed["failure"] is None and closed["source_stable"], "目标未自然有效闭合")
        expected_samples = [1, 2]
        if target["historical_control"] and plan["historical_original_world_for_first_14"]:
            expected_samples = [0, 1, 2]
        require(closed["counts"]["single_hand_dispatched"] == closed["counts"]["single_hand_completed"] == len(expected_samples) * 3
            and closed["counts"]["hidden_samples"] == 2 and closed["counts"]["failed_or_missing_full_scores"] == 0,
            "目标费用或样本分母不同")
        audits.append({"target": index, **verify_scores(directory, closed, plan)})
        counts.update(closed["counts"])
        for sample in expected_samples:
            results = [r for r in closed["results"] if r["sample"] == sample]
            require(len(results) == 3 and {r["arm"] for r in results} == {"A", "B", "C"}
                and len({r["sample_key"] for r in results}) == 1, "三组共同世界键不一致")
            accounts = {r["arm"]: account(r, target["focal_seat"]) for r in results}
            row = {"target": index, "root_id": target["composition"]["root_id"], "label": target["case"]["label"],
                "classes": target["case"]["classes"], "sample": sample,
                "world_kind": "historical_exposed" if sample == 0 else "public_compatible_uniform", "accounts": accounts}
            for left, right in (("B", "A"), ("C", "A"), ("C", "B")):
                row[left + "_minus_" + right] = {k: accounts[left][k] - accounts[right][k] for k in accounts[left]}
            pairs.append(row)
        for path in directory.iterdir():
            if path.is_file():
                files[str(path)] = pin(path)
    require(counts["single_hand_dispatched"] == plan["planned_single_hand_instances"] and unchanged(plan), "全批费用或冻结不同")
    save(Path(args.closed_output).resolve(), {"schema": "t191-fixed-abc-closed/1", "complete": True,
        "plan_pin": pin(plan_path), "source_stable": True, "counts": dict(counts), "audits": audits,
        "candidate_identity": plan["arms_sources"]["child"]["identity"],
        "historical_exposed": summarize([p for p in pairs if p["sample"] == 0]),
        "public_compatible_uniform": summarize([p for p in pairs if p["sample"] > 0]),
        "pairs": pairs, "files": files, "historical_and_compatible_not_pooled": True,
        "forcing_is_c_self_scored": False, "multiple_windows_rotations_samples_are_correlated": True,
        "resources_released": True, "actual_new_business_calls_at_readback": 0,
        "strength_deadline_or_release_admission": False, "automatic_next_stage_dispatch": False})
    print(json.dumps({"complete": True, "single_hand_instances": counts["single_hand_dispatched"],
        "actual_score_calls": counts["actual_score_calls"], "rescoring_calls": 0}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--dispatch-closed", required=True)
    p.add_argument("--closed-output", required=True)
    main(p.parse_args())
