"""纯读已关闭的同起点诊断；不导入策略、规则、世界或模型。

按母根/来源/原与隐藏世界分账；提取 C/B 首次实际动作分歧供开发反馈。
条件续打不能冒充自然完整桌，描述性差额不能冒充强度确认。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def read(path):
    """读取原件；不填补缺字段或失败终态。"""
    return json.loads(path.read_bytes())


def canonical(value):
    """标准JSON身份；拒绝非有限浮点，单位随原字段保留。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def analyse(directory):
    """返回开发总结；只接受关闭终态，按原120槽保留失效或未启动项。"""
    plan, result = read(directory / "PREPARED.json"), read(directory / "COSTS-AND-RESULT.json")
    if result["status"] != "diagnostic_batch_closed_not_strength_confirmation":
        raise ValueError("诊断未完整关闭；先解决工具失败，不抽成功子集计算效果")
    planned = {(r["root_id"], v, a) for r in plan["roots"] for v in plan["variant_order"] for a in plan["arm_order"]}
    observed = {(r["root_id"], r["variant"], r["arm"]) for r in result["arms"]}
    if len(result["arms"]) != 120 or observed != planned:
        raise ValueError("120槽身份或分母不完整")
    definitions = {r["root_id"]: r for r in plan["roots"]}
    policy_rows, advances, score_rows = defaultdict(dict), defaultdict(list), {}
    with (directory / "calls-and-choices.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if "variant" not in row or "arm" not in row:
                continue
            key = (row["root_id"], row["variant"], row["arm"])
            if row["event"] == "policy_choose":
                policy_rows[key][canonical(row["window_key"])] = row
            elif row["event"] == "score_call":
                score_rows[row["policy_call_no"]] = row
            elif row["event"] == "advance" and row["status"] == "advanced":
                advances[key].append(row["choices"])
    worlds, grouped = [], defaultdict(list)
    for ordinal, root in enumerate(plan["roots"], 1):
        root_id = root["root_id"]
        focal = root["permutation"][0]
        for variant in plan["variant_order"]:
            slots = [r for r in result["arms"] if r["root_id"] == root_id and r["variant"] == variant]
            if not all(r["status"] == "complete" for r in slots):
                worlds.append({"root_id": root_id, "source_kind": root["source_kind"], "variant": variant,
                               "status": "invalid_original_slots_retained", "slots": slots})
                continue
            parent = directory / ("root-" + str(ordinal).zfill(2)) / variant
            arm_rows = {a: read(parent / (a + "-outcome.json")) for a in plan["arm_order"]}
            target = read(parent / "COMMON-START.json")["target_window"]
            a_first = policy_rows[(root_id, variant, "A")][canonical(target)]
            current_hu = "hu" in a_first["legal_action_keys"]
            row = {"root_id": root_id, "source_kind": root["source_kind"], "profile": root["profile"],
                   "variant": variant, "status": "valid", "focal_physical_seat": focal,
                   "current_legal_hu": current_hu, "arms": {}, "deltas": {}, "first_C_B_divergences": {}}
            for arm, arm_row in arm_rows.items():
                settlement = arm_row["settlement"]
                if sum(settlement["score_delta"]) != 0 or arm_row["outcome"]["completed_hands"] != 1:
                    raise ValueError("单局端点或积分不守恒")
                row["arms"][arm] = {"first_action": arm_row["first_action_key"],
                    "focal_net_score": settlement["score_delta"][focal], "focal_won": settlement["winner_seat"] == focal,
                    "other_won": settlement["winner_seat"] is not None and settlement["winner_seat"] != focal,
                    "draw": settlement["is_draw"], "fan": settlement["fan"], "details": settlement["details"]}
            for name in ("Sol", "S02"):
                a, b, c = (row["arms"][k]["focal_net_score"] for k in ("A", name + "-B", name + "-C"))
                row["deltas"][name] = {"B_minus_A": b-a, "C_minus_A": c-a, "C_minus_B": c-b}
                grouped[(root["source_kind"], variant, name)].append(row)
                c_path, b_path = (advances[(root_id, variant, name + suffix)] for suffix in ("-C", "-B"))
                for index, (c_frame, b_frame) in enumerate(zip(c_path, b_path)):
                    if c_frame == b_frame:
                        continue
                    divergence = {"advance_index_after_start": index + 1, "C_choices": c_frame, "B_choices": b_frame,
                                  "scope": "首个实际帧分歧；整段积分差不归因成这一动作的通用真值"}
                    for role, frame, suffix in (("C", c_frame, "-C"), ("B", b_frame, "-B")):
                        candidates = [r for r in frame if r["window_key"]["seat"] == focal]
                        if len(candidates) != 1:
                            continue
                        decision = policy_rows[(root_id, variant, name + suffix)][canonical(candidates[0]["window_key"])]
                        score = score_rows.get(decision["policy_call_no"])
                        divergence[role + "_decision"] = {"window_key": decision["window_key"],
                            "observation": decision["observation"], "selected_action_key": decision["selected_action_key"],
                            "full_input_sha256": None if score is None else score["input_capture"]["view_sha256"],
                            "scores": None if score is None else score["scores"]}
                    if "C_decision" in divergence and "B_decision" in divergence:
                        divergence["same_focal_observation"] = divergence["C_decision"]["observation"] == divergence["B_decision"]["observation"]
                    row["first_C_B_divergences"][name] = divergence
                    break
            worlds.append(row)
    summaries = []
    for (kind, variant, name), rows in sorted(grouped.items()):
        n = len(rows)
        summary = {"source_kind": kind, "variant": variant, "candidate": name, "mother_roots_in_this_stratum": n,
            "mean_deltas": {key: sum(r["deltas"][name][key] for r in rows)/n for key in ("B_minus_A", "C_minus_A", "C_minus_B")},
            "C_A_sign_counts": dict(Counter("positive" if r["deltas"][name]["C_minus_A"] > 0 else
                                             "negative" if r["deltas"][name]["C_minus_A"] < 0 else "zero" for r in rows)),
            "A_outcomes": dict(Counter("own_hu" if r["arms"]["A"]["focal_won"] else "other_hu" if r["arms"]["A"]["other_won"] else "draw" for r in rows)),
            "C_outcomes": dict(Counter("own_hu" if r["arms"][name+"-C"]["focal_won"] else "other_hu" if r["arms"][name+"-C"]["other_won"] else "draw" for r in rows)),
            "own_fan_ge4_A_C": [sum(r["arms"][arm]["focal_won"] and r["arms"][arm]["fan"] >= 4 for r in rows) for arm in ("A", name+"-C")],
            "current_hu_continued_then_other_won_C": sum(r["current_legal_hu"] and r["arms"][name+"-C"]["first_action"] != "hu" and r["arms"][name+"-C"]["other_won"] for r in rows)}
        summaries.append(summary)
    return {"schema": "t10-abc-credit-development-analysis/1", "status": "descriptive_only",
        "source_result_sha256": hashlib.sha256((directory/"COSTS-AND-RESULT.json").read_bytes()).hexdigest(),
        "planned_mother_roots": 12, "completed_mother_roots": sum(r["status"] == "complete" for r in result["roots"]),
        "planned_worlds": 24, "valid_worlds": sum(r["status"] == "valid" for r in worlds),
        "planned_single_hand_continuations": 120, "completed_single_hand_continuations": result["completed_arms"],
        "source_variant_summaries": summaries, "worlds": worlds,
        "opponent_near_completion_scope": "教师向听0仅固定原世界；隐藏重采样的他家近完成资格未知，不把两个世界计成已验证近完成对照",
        "clustering_unit": "mother_root; variants and arms not independent roots",
        "strength_claim": False, "confirmation": False, "natural_complete_table_credit": False, "business_calls": 0}


def main():
    """CLI只消费关闭原件，独占写总结，不修改源文件或算法。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyse(args.directory)
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    print(canonical({k: result[k] for k in ("status", "completed_mother_roots", "valid_worlds", "completed_single_hand_continuations", "source_variant_summaries")}).decode())


if __name__ == "__main__":
    main()
