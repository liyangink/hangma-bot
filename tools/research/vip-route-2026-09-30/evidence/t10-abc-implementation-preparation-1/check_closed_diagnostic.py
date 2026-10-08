"""纯读关闭的120臂诊断，核对来源、实际输入、动作及积分；不重执行业务。"""
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
import gzip
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    """用于内容身份的严格JSON字节；概率、时间和积分单位沿用源字段。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read(path):
    """只读取已保存原件；缺件直接失败，不生成替代结果。"""
    return json.loads(path.read_bytes())


def digest(path):
    """原文件SHA256，不依赖源码运行或规则计算。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(directory):
    """关闭批核验；所有断言均须成立才写 accepted_engineering_only。"""
    plan, start, result = (read(directory / name) for name in ("PREPARED.json", "ROOT-START.json", "COSTS-AND-RESULT.json"))
    assert start["prepared_sha256"] == digest(directory / "PREPARED.json")
    assert result["status"] == "diagnostic_batch_closed_not_strength_confirmation"
    assert result["completed_arms"] == result["dispatched_arms"] == 120
    assert result["missing_or_failed_arms"] == 0 and not result["cleanup_errors"]
    for mapping in (plan["files"], plan["runtime_files"]):
        for filename, identity in mapping.items():
            path = Path(filename)
            assert path.stat().st_size == identity["bytes"] and digest(path) == identity["sha256"], filename
    assert digest(Path(plan["tool_file"])) == plan["tool_sha256"]
    views = {}
    with gzip.open(directory / "views.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            raw = canonical(row["view"])
            assert len(raw) == row["json_bytes"] and hashlib.sha256(raw).hexdigest() == row["view_sha256"]
            assert row["view_sha256"] not in views
            views[row["view_sha256"]] = row["view"]
    assert len(views) == result["input_capture"]["terminal"]["verified_unique_views"] == 1635
    counts = Counter()
    calls, paths, max_ops = {}, defaultdict(list), Counter()
    with (directory / "calls-and-choices.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            counts[row["event"]] += 1
            key = (row["root_id"], row.get("variant"), row.get("arm"))
            if row["event"] == "score_call":
                assert row["status"] == row["scores"]["status"] == "SCORED"
                capture = row["input_capture"]
                assert capture["saved_before_score"] and capture["error"] is None
                assert capture["view_sha256"] in views
                assert 0 <= row["operations"] <= row["operation_limit"]
                max_ops[row["kind"]] = max(max_ops[row["kind"]], row["operations"])
                entries = row["scores"]["entries"]
                keys = [entry["action_key"] for entry in entries]
                assert len(keys) == len(set(keys)) and set(keys) == set(row["legal_action_keys"])
                assert set(a["action_key"] for a in views[capture["view_sha256"]]["actions"]) == set(keys)
                assert all(math.isfinite(entry["score"]) for entry in entries)
                assert row["policy_call_no"] not in calls
                calls[row["policy_call_no"]] = row
                counts[row["kind"] + ":score_calls"] += 1
            elif row["event"] == "policy_choose":
                assert row["status"] == "chosen" and row["selected_action_key"] in row["legal_action_keys"]
                assert set(row["ordered_action_keys"]) == set(row["legal_action_keys"])
                if row["arm"] in ("Sol-C", "S02-C") and row["seat"] == row["window_key"]["seat"] and row["policy_id"].startswith("vip:"):
                    assert row["scored_by_self"] and row["policy_call_no"] in calls
                    assert not row["degraded_reasons"]
            elif row["event"] == "advance" and row["status"] == "advanced":
                paths[key].append(row["choices"])
    assert counts["policy_choose"] == result["actual_calls"]["policy_choose_calls"] == 6618
    assert counts["score_call"] == result["actual_calls"]["C:score_calls"] + result["actual_calls"]["R18:score_calls"] == 3551
    assert counts["C:score_calls"] == 717 and counts["R18:score_calls"] == 2834
    planned = {(r["root_id"], v, a) for r in plan["roots"] for v in plan["variant_order"] for a in plan["arm_order"]}
    assert {(r["root_id"], r["variant"], r["arm"]) for r in result["arms"]} == planned
    same_first_verified = 0
    for ordinal, root in enumerate(plan["roots"], 1):
        root_dir = directory / ("root-" + str(ordinal).zfill(2))
        assert read(root_dir / "ROOT-RESULT.json")["status"] == "complete"
        starts = [read(root_dir / v / "COMMON-START.json") for v in plan["variant_order"]]
        assert starts[0]["focal_observation"] == starts[1]["focal_observation"]
        for variant in plan["variant_order"]:
            outcomes = {arm: read(root_dir / variant / (arm + "-outcome.json")) for arm in plan["arm_order"]}
            world_result = read(root_dir / variant / "WORLD-RESULT.json")
            assert world_result["root_id"] == root["root_id"] and world_result["variant"] == variant
            for arm, row in outcomes.items():
                s, outcome = row["settlement"], row["outcome"]
                assert row["status"] == outcome["status"] == "complete" and outcome["completed_hands"] == 1
                assert not outcome["blocked_reason"] and not outcome["error_reason"]
                assert not any(outcome["runtime_counts"].values())
                assert sum(s["score_delta"]) == 0
                assert [a+b for a,b in zip(s["scores_before"],s["score_delta"])] == s["scores_after"] == outcome["final_scores"]
                assert row["focal_net_score"] == s["score_delta"][root["permutation"][0]]
            for name in ("Sol", "S02"):
                b = outcomes[name + "-B"]
                assert b["force_count"] == 1
                a_score, b_score, c_score = (outcomes[k]["focal_net_score"] for k in ("A", name+"-B", name+"-C"))
                assert world_result["deltas"][name] == {"B_minus_A": b_score-a_score, "C_minus_A": c_score-a_score, "C_minus_B": c_score-b_score}
                if b["first_action_key"] == outcomes["A"]["first_action_key"]:
                    assert paths[(root["root_id"],variant,name+"-B")] == paths[(root["root_id"],variant,"A")]
                    assert b["settlement"] == outcomes["A"]["settlement"]
                    same_first_verified += 1
    assert result["elapsed_monotonic_seconds"] < plan["budgets"]["wall_clock_seconds"]
    assert result["output_bytes_before_terminal"] < plan["budgets"]["max_output_bytes"]
    return {"schema":"t10-abc-diagnostic-root-pure-read-check/1", "status":"accepted_engineering_only",
        "source_result_sha256":digest(directory/"COSTS-AND-RESULT.json"),
        "mother_roots":12, "worlds":24, "complete_single_hand_continuations":120,
        "policy_calls":counts["policy_choose"], "C_score_calls":counts["C:score_calls"],
        "R18_score_calls":counts["R18:score_calls"], "unique_actual_full_inputs":len(views),
        "max_operations_by_kind":dict(max_ops), "same_first_B_A_paths_verified":same_first_verified,
        "source_identity_rechecked":True, "settlements_conserve_and_match_final_scores":True,
        "all_scores_legal_finite_and_input_hash_bound":True, "normal_C_r18_fallbacks":0,
        "opponent_near_completion_scope":"original_only; hidden variant not teacher-requalified",
        "business_calls":0, "model_api_calls":0, "strength_claim":False, "confirmation":False}


def main():
    """只消费原件，独占创建核验收据；任何失败保留原件并退出。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.directory)
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
