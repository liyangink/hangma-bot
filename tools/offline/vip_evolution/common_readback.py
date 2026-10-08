"""共同来源完整诊断的薄读回；全批自然闭合后才分析，禁止把条件积分当自然适应度。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t200-eoh-fast-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import gzip
import hashlib
import json
import math
import time
from pathlib import Path


def read(path: Path):
    """只读取受体积限制的完整JSON，不执行其中的字段。"""
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("闭件超过8MiB，不扩大读取")
    return json.loads(path.read_bytes())


def pin(path: Path):
    """为原件计算字节摘要，路径和数据不包含运行凭据。"""
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            sha.update(block)
    return {"bytes": size, "sha256": sha.hexdigest()}


def canonical(value):
    """只比较公开业务输入，浮点和列表次序不作隐式修正。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def bins(rows, seat):
    """按结算归类；支付为正支出，净分＝普通收入＋四番及以上收入－支付。"""
    ordinary = high = payments = net = 0
    for row in rows:
        value = row["score_delta"][seat]
        net += value
        if row["is_draw"]:
            if value != 0:
                raise ValueError("流局分值非零")
        elif row["winner_seat"] == seat:
            if type(row["fan"]) is not int or value <= 0:
                raise ValueError("胡牌收入或番值缺失")
            if row["fan"] >= 4:
                high += value
            else:
                ordinary += value
        else:
            if value > 0:
                raise ValueError("他家胡牌却收到收入")
            payments -= value
    if net != ordinary + high - payments:
        raise ValueError("结算分账不闭")
    return {"ordinary_hu_income_lt4": ordinary, "high_fan_hu_income_ge4": high,
            "payments": payments, "net": net, "completed_remaining_hands": len(rows)}


def key(row):
    """按本次观察已消费序号排序，再对齐同期座位。

    碰响应与吃响应可以共用最初弃牌的trigger_seq，但后者已经消费前者
    的过牌事件。不能按phase字母序把吃响应排在更早的碰响应之前。
    同期多座choose的返回次序也不是动作差异。
    """
    window = row["window_key"]
    seq = row["observation"]["consumed_seq"]
    if type(seq) is not int or seq < window["trigger_seq"]:
        raise ValueError("观察消费序号缺失或早于触发事件")
    return window["round_no"], seq, window["phase"], row["seat"]


def decisions(path, cap, arms=("parent", "candidate")):
    """流式读取固定封口的原决策；上限是解压字节，不是压缩文件大小。"""
    groups = {(sample, arm): [] for sample in (1, 2) for arm in arms}
    size = 0
    with gzip.open(path, "rb") as stream:
        for line in stream:
            size += len(line)
            if size > cap:
                raise ValueError("决策解压字节预算耗尽，不扩大读取")
            envelope = json.loads(line)
            if envelope["record_kind"] != "delegate_actual_choose":
                raise ValueError("未知决策记录类型")
            groups[(envelope["sample"], envelope["arm"])].append(envelope["row"])
    for rows in groups.values():
        rows.sort(key=key)
        if len({key(row) for row in rows}) != len(rows):
            raise ValueError("同期座位窗口重复，不能伪造唯一序列")
    return groups, size


def divergence(parent, child, focal):
    """首个动作分歧前须同观察、合法根及本家typed输入；只留第一次分歧的薄定位。"""
    input_fields = ("seat", "window_key", "observation", "legal_action_keys")
    first = None
    prefix = 0
    for a, b in zip(parent, child):
        if any(canonical(a[field]) != canonical(b[field]) for field in input_fields):
            raise ValueError("首个改选前出现不同业务输入；不归为算法效果")
        if a["seat"] == focal:
            ca, cb = a["scoring_calls"], b["scoring_calls"]
            if len(ca) != 1 or len(cb) != 1 or ca[0]["input_capture"]["view_sha256"] != cb[0]["input_capture"]["view_sha256"]:
                raise ValueError("首个改选前本家typed输入不同")
        if a["selected_action_key"] != b["selected_action_key"]:
            if a["seat"] != focal:
                raise ValueError("首个动作差异来自对手，未证明共同对局")
            first = {"aligned_index": prefix, "window_key": a["window_key"],
                     "parent": a["selected_action_key"], "candidate": b["selected_action_key"],
                     "white_count": a["white_count"], "current_opportunity": a["current_opportunity"],
                     "observation": a["observation"], "parent_candidates": a["candidates"],
                     "candidate_candidates": b["candidates"], "same_all_inputs_before_divergence": True}
            break
        prefix += 1
    if first is None and len(parent) != len(child):
        raise ValueError("没有改选却序列长度不同，资料未闭")
    return {"full_core_trajectory_same": first is None, "prefix_same_decisions": prefix,
            "first_divergence": first}


def run_three(plan_path, run_dir, output, cap):
    """同两世界的两个子代分别对同一父代分账；必须六条轨迹全部闭合。

    两个隐藏世界归属同一完整task.root_id，不把不同子代或换世界增加为
    独立母来源。起点单局与后来新发手牌的收入和支付分别记录。
    """
    started = time.monotonic()
    plan = read(plan_path)
    children = plan["candidate_identities"]
    arms = tuple(plan["arms"])
    if len(children) != 2 or arms != ("P0", *children) or len(set(arms)) != 3:
        raise ValueError("三臂布局不唯一或不是同父两子")
    identities = {"P0": plan["parent_identity"], **children}
    if len({i["candidate_id"] for i in identities.values()}) != 3:
        raise ValueError("三臂候选身份重复")
    points = plan["points"]
    if not points:
        raise ValueError("没有母来源，不能报告完整诊断")
    paths = [run_dir / f"point-{i:03d}" / "CLOSED.json" for i in range(1, len(points) + 1)]
    if not all(path.is_file() for path in paths):
        raise ValueError("全批尚未自然闭合；0效果读回")
    plan_pin = pin(plan_path)
    closed = [read(path) for path in paths]
    for index, c in enumerate(closed, 1):
        if (c["complete"] is not True or c["failure"] is not None or c["point"] != index
                or c["plan_pin"] != plan_pin or c["candidate_identities"] != children
                or c["source_stable"] is not True or c["forced_first_rows"]
                or c["counts"]["remaining_table_continuations_complete"] != 6
                or c["capture"]["terminal"]["terminal_valid"] is not True):
            raise ValueError("三臂存在未闭来源、身份漂移、强制首选或评分缺口")
    fields = ("net_delta", "ordinary_income_delta", "high_fan_income_delta", "payment_delta")
    totals = {arm: {"candidate_id": children[arm]["candidate_id"],
                    **{field: 0 for field in fields}, "same_full_trajectory_pairs": 0,
                    "actual_policy_divergence_pairs": 0} for arm in children}
    report = {"schema": "common-three-arm-full-policy-readback/1", "complete": False,
              "plan_pin": plan_pin, "source_mothers": len(points),
              "shared_compatible_worlds": 2 * len(points),
              "whole_policy_trajectories": 6 * len(points), "per_candidate": totals,
              "fitness_natural": None, "strength_admitted": False, "sources": [],
              "counts": {}, "raw_decompressed_bytes": 0,
              "all_closed_before_any_effect_read": True,
              "terminal_pins": {str(path): pin(path) for path in paths}}
    mothers = set()
    for index, (point, c) in enumerate(zip(points, closed), 1):
        directory = run_dir / f"point-{index:03d}"
        for name, expected in c["raw_files"].items():
            if pin(directory / name) != expected:
                raise ValueError("三臂原件摘要不同")
        mother = point["task"]["root_id"]
        if mother in mothers:
            raise ValueError("完整母来源重复，不扩大独立来源数")
        mothers.add(mother)
        seat = point["task"]["focal_physical_seat"]
        results = {(r["sample"], r["arm"]): r for r in c["results"]}
        if len(c["results"]) != 6 or set(results) != {(s, a) for s in (1, 2) for a in arms}:
            raise ValueError("三臂两世界缺失或重复")
        for (sample, arm), result in results.items():
            if result["focal_identity"] != identities[arm] or result["force_count"] != 0:
                raise ValueError("三臂实际身份或首动作强制不同")
            if (result["actual_remaining_hands"] != 9 - point["window_key"]["round_no"]
                    or bins(result["settlements"], seat) != result["bins"]
                    or result["bins"]["net"] != result["final_scores_seat_order_0_1_2_3"][seat]
                    - point["observation"]["scores"][seat]):
                raise ValueError("三臂剩余完整桌结算或当前积分不闭")
        groups, size = decisions(directory / "decisions.jsonl.gz", cap, arms)
        if sum(map(len, groups.values())) != c["counts"]["all_seat_decision_windows"]:
            raise ValueError("三臂逐手分母与终态不一致")
        source = {"label": point["label"], "source_root_id": mother, "candidates": {}}
        for arm in children:
            entry = {"pairs": [], **{field: 0 for field in fields}}
            for sample in (1, 2):
                a, b = results[(sample, "P0")], results[(sample, arm)]
                if a["sample_key"] != b["sample_key"]:
                    raise ValueError("三臂相容世界标识不同")
                pair = {"sample": sample}
                for field, name in zip(fields, ("net", "ordinary_hu_income_lt4", "high_fan_hu_income_ge4", "payments")):
                    pair[field] = b["bins"][name] - a["bins"][name]
                for label, segment in (("starting_hand", slice(0, 1)), ("later_hands", slice(1, None))):
                    ba, bb = bins(a["settlements"][segment], seat), bins(b["settlements"][segment], seat)
                    pair[label] = {name: bb[name] - ba[name] for name in
                                   ("net", "ordinary_hu_income_lt4", "high_fan_hu_income_ge4", "payments")}
                if pair["starting_hand"]["net"] + pair["later_hands"]["net"] != pair["net_delta"]:
                    raise ValueError("三臂起点单局与后发单局分账不闭")
                pair.update(divergence(groups[(sample, "P0")], groups[(sample, arm)], seat))
                same = pair["full_core_trajectory_same"]
                if same and canonical(a["settlements"]) != canonical(b["settlements"]):
                    raise ValueError("三臂同轨迹但结算不同")
                totals[arm]["same_full_trajectory_pairs" if same else "actual_policy_divergence_pairs"] += 1
                entry["pairs"].append(pair)
                for field in fields:
                    entry[field] += pair[field]
                    totals[arm][field] += pair[field]
            source["candidates"][arm] = entry
        for name, value in c["counts"].items():
            report["counts"][name] = report["counts"].get(name, 0) + value
        report["raw_decompressed_bytes"] += size
        report["sources"].append(source)
    for total in totals.values():
        if total["net_delta"] != total["ordinary_income_delta"] + total["high_fan_income_delta"] - total["payment_delta"]:
            raise ValueError("三臂候选总分账不闭")
    for path, expected in report["terminal_pins"].items():
        if pin(Path(path)) != expected:
            raise ValueError("三臂读回过程终态漂移")
    report.update(complete=True, elapsed_monotonic_seconds=time.monotonic() - started)
    with output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def run(plan_path, run_dir, output, cap):
    """全部来源闭合、身份和原件稳定后一次读效；输出排他创建，没有续样或重试。"""
    started = time.monotonic()
    plan = read(plan_path)
    if "candidate_identities" in plan:
        return run_three(plan_path, run_dir, output, cap)
    points = plan["points"]
    if not points:
        raise ValueError("没有母来源，不能报告完整诊断")
    closed_paths = [run_dir / f"point-{i:03d}" / "CLOSED.json" for i in range(1, len(points) + 1)]
    if not all(path.is_file() for path in closed_paths):
        raise ValueError("全批尚未自然闭合；0效果读回")
    plan_pin = pin(plan_path)
    closed = [read(path) for path in closed_paths]
    for i, c in enumerate(closed, 1):
        if (not c["complete"] or c["failure"] is not None or c["point"] != i or
                c["plan_pin"] != plan_pin or c["candidate_identity"] != plan["candidate_identity"] or
                not c["source_stable"] or c["forced_first_rows"] or
                c["counts"]["remaining_table_continuations_complete"] != 4 or
                not c["capture"]["terminal"]["terminal_valid"]):
            raise ValueError("存在未闭来源、身份漂移、强制首选或完整评分缺口")
    report = {"schema": "common-full-policy-readback/1", "complete": False, "plan_pin": plan_pin,
              "candidate_id": plan["candidate_identity"]["candidate_id"], "source_mothers": len(points),
              "paired_worlds": 2 * len(points), "whole_policy_trajectories": 4 * len(points),
              "fitness_natural": None, "strength_admitted": False, "sources": [], "counts": {},
              "net_delta": 0, "ordinary_income_delta": 0, "high_fan_income_delta": 0, "payment_delta": 0,
              "raw_decompressed_bytes": 0, "all_closed_before_any_effect_read": True,
              "same_full_trajectory_pairs": 0, "actual_policy_divergence_pairs": 0,
              "terminal_pins": {str(p): pin(p) for p in closed_paths}}
    mothers = set()
    for index, (point, c) in enumerate(zip(points, closed), 1):
        directory = run_dir / f"point-{index:03d}"
        for name, expected in c["raw_files"].items():
            if pin(directory / name) != expected:
                raise ValueError("原件摘要不同")
        mothers.add(c["source_mother"])
        seat = point["task"]["focal_physical_seat"]
        by_arm = {(r["sample"], r["arm"]): r for r in c["results"]}
        if set(by_arm) != {(s, a) for s in (1, 2) for a in ("parent", "candidate")} or len(c["results"]) != 4:
            raise ValueError("父子两世界不完整或重复")
        for (sample, arm), result in by_arm.items():
            expected_identity = plan["parent_identity"] if arm == "parent" else plan["candidate_identity"]
            if result["focal_identity"] != expected_identity or result["force_count"] != 0:
                raise ValueError("实际臂身份或强制动作不同")
            if (result["actual_remaining_hands"] != 9 - point["window_key"]["round_no"] or
                    bins(result["settlements"], seat) != result["bins"] or
                    result["bins"]["net"] != result["final_scores_seat_order_0_1_2_3"][seat] - point["observation"]["scores"][seat]):
                raise ValueError("剩余完整桌结算或当前积分不闭")
        groups, byte_count = decisions(directory / "decisions.jsonl.gz", cap)
        if sum(map(len, groups.values())) != c["counts"]["all_seat_decision_windows"]:
            raise ValueError("逐手记录分母与闭件不一致")
        source = {"label": point["label"], "source_mother": c["source_mother"], "pairs": [],
                  "net_delta": 0, "ordinary_income_delta": 0, "high_fan_income_delta": 0, "payment_delta": 0}
        for sample in (1, 2):
            a, b = by_arm[(sample, "parent")], by_arm[(sample, "candidate")]
            if a["sample_key"] != b["sample_key"]:
                raise ValueError("父子相容世界不同")
            pair = {"sample": sample, "net_delta": b["bins"]["net"] - a["bins"]["net"],
                    "ordinary_income_delta": b["bins"]["ordinary_hu_income_lt4"] - a["bins"]["ordinary_hu_income_lt4"],
                    "high_fan_income_delta": b["bins"]["high_fan_hu_income_ge4"] - a["bins"]["high_fan_hu_income_ge4"],
                    "payment_delta": b["bins"]["payments"] - a["bins"]["payments"]}
            # 起点所在单局与后来新发手牌分别记账；来源标签不能替代实际作用白数。
            start_a, start_b = bins(a["settlements"][:1], seat), bins(b["settlements"][:1], seat)
            later_a, later_b = bins(a["settlements"][1:], seat), bins(b["settlements"][1:], seat)
            pair["starting_hand_net_delta"] = start_b["net"] - start_a["net"]
            pair["later_hands_net_delta"] = later_b["net"] - later_a["net"]
            if pair["starting_hand_net_delta"] + pair["later_hands_net_delta"] != pair["net_delta"]:
                raise ValueError("起点所在单局与后续新手分账不闭")
            pair.update(divergence(groups[(sample, "parent")], groups[(sample, "candidate")], seat))
            if pair["full_core_trajectory_same"]:
                if canonical(a["settlements"]) != canonical(b["settlements"]):
                    raise ValueError("同策略轨迹却结算不同")
                report["same_full_trajectory_pairs"] += 1
            else:
                report["actual_policy_divergence_pairs"] += 1
            source["pairs"].append(pair)
            for field in ("net_delta", "ordinary_income_delta", "high_fan_income_delta", "payment_delta"):
                source[field] += pair[field]
                report[field] += pair[field]
        for name, value in c["counts"].items():
            report["counts"][name] = report["counts"].get(name, 0) + value
        report["raw_decompressed_bytes"] += byte_count
        report["sources"].append(source)
    if len(mothers) != len(points):
        raise ValueError("来源标识重复，独立母数不能扩大")
    if report["net_delta"] != report["ordinary_income_delta"] + report["high_fan_income_delta"] - report["payment_delta"]:
        raise ValueError("总净分分账不闭")
    for path, expected in report["terminal_pins"].items():
        if pin(Path(path)) != expected:
            raise ValueError("读回过程终态漂移")
    report.update(complete=True, elapsed_monotonic_seconds=time.monotonic() - started)
    with output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-decisions-bytes-per-point", default=128 * 1024 * 1024, type=int)
    args = parser.parse_args()
    result = run(args.plan, args.run, args.output, args.max_decisions_bytes_per_point)
    print(json.dumps({k: v for k, v in result.items() if k not in ("sources", "terminal_pins")}, ensure_ascii=False))
