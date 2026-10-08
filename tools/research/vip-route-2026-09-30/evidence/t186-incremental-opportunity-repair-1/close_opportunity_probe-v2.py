"""四条件worker自然结束后核原评分流和物理座位分账；不重跑或授强度。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, OLD, canonical, pin, save
from evaluation_sharding import resource_slot_paths
from t185_prepare_confirmation import background_priority, postprocess_lock
from reuse_causal_helpers import unchanged


def account(result, seat):
    """原模拟结算分账；向量物理座位0—3，大牌按四番及以上，不另算杭麻番型。"""
    s = result["settlement"]
    delta = s["score_delta"]
    assert len(delta) == 4 and all(type(v) is int for v in delta) and sum(delta) == 0
    a = {"net": delta[seat], "ordinary_hu_income": 0, "large_hu_income": 0,
         "payments": 0, "own_hu": 0, "other_hu": 0, "draws": 0}
    if s["is_draw"]:
        assert delta == [0, 0, 0, 0]
        a["draws"] = 1
    elif s["winner_seat"] == seat:
        assert delta[seat] > 0
        a["own_hu"] = 1
        a["large_hu_income" if s["fan"] >= 4 else "ordinary_hu_income"] = delta[seat]
    else:
        assert delta[seat] <= 0
        a["other_hu"] = 1
        a["payments"] = delta[seat]
    assert a["net"] == result["focal_net_score"] == a["ordinary_hu_income"] + a["large_hu_income"] + a["payments"]
    return a


def verify_scores(directory, closure, plan):
    """原输入逐字节摘要与合法根、完整分数和实际调用相互核对，不重新评分。"""
    views = {}
    with gzip.open(directory / "views.jsonl.gz", "rt") as stream:
        for line in stream:
            v = json.loads(line)
            raw = canonical(v["view"])
            assert hashlib.sha256(raw).hexdigest() == v["view_sha256"] and len(raw) == v["json_bytes"]
            assert v["view_sha256"] not in views
            views[v["view_sha256"]] = v["view"]
    rows, calls, groups = 0, 0, Counter()
    with gzip.open(directory / "decisions.jsonl.gz", "rt") as stream:
        for line in stream:
            x = json.loads(line)
            row = x["row"]
            assert row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"]
            assert len(row["scoring_calls"]) == 1
            c = row["scoring_calls"][0]
            receipt = c["input_capture"]
            assert c["actual_score_calls"] == 1 and c["score_completed"] and c["full_legal_keys"] and receipt["saved_before_score"]
            assert type(c["candidate_operations"]) is int and 0 <= c["candidate_operations"] <= 4800000
            view = views[receipt["view_sha256"]]
            roots = [a["action_key"] for a in view["actions"]]
            entries = row["candidates"]
            assert sorted(roots) == sorted(c["scored_action_keys"]) == sorted(e["action_key"] for e in entries)
            assert len(roots) == len(set(roots)) and all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
            assert row["selected_action_key"] == entries[0]["action_key"]
            rows += 1
            calls += c["actual_score_calls"]
            groups[(x["sample"], x["arm"])] += 1
    assert rows == closure["counts"]["scored_decisions"] and calls == closure["counts"]["actual_score_calls"]
    assert calls == closure["capture"]["store_calls"] and len(views) == closure["capture"]["unique_views_saved"]
    assert closure["capture"]["terminal"]["terminal_valid"]
    for r in closure["results"]:
        assert groups[(r["sample"], r["arm"])] == r["focal_score_calls"] > 0
    return {"actual_score_calls": calls, "unique_views": len(views), "complete": True}


def main():
    """仅全批统一读回，冻结母源相关性与条件等权边界；不给总体置信区间。"""
    background_priority()
    plan_path = _project_file(_PROJECT_ROOT, HERE / "OPPORTUNITY-PROBE-PLAN-v2.json")
    plan = json.loads(plan_path.read_text())
    out = _project_file(_PROJECT_ROOT, HERE / "opportunity-probe-v2")
    dispatch = json.loads((out / "DISPATCH-CLOSED.json").read_text())
    assert dispatch["complete"] and dispatch["worker_returncodes"] == [0] * 4 and dispatch["all_processes_naturally_waited"]
    assert dispatch["plan_pin"] == pin(plan_path) and unchanged(plan)
    # 同一共用槽必须已释放，不能仅凭终态文件推定没有真实计算持有者。
    import fcntl
    for p in resource_slot_paths(OLD, 4):
        with p.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    counts, comparisons, files, target_summaries = Counter(), [], {}, []
    for slot in range(4):
        w = out / f"worker-{slot}"
        start, close = (json.loads((w / n).read_text()) for n in ["START.json", "CLOSE.json"])
        assert close["complete"] and close["failure"] is None and close["completed"] == start["targets"] == list(range(slot + 1, 10, 4))
        assert start["pid"] == close["pid"] == dispatch["children"][slot] and start["plan_pin"] == pin(plan_path)
        for n in ["START.json", "CLOSE.json"]:
            files[str(w / n)] = pin(w / n)
    for index, target in enumerate(plan["targets"], 1):
        d = out / f"target-{index:03d}"
        start, c = (json.loads((d / n).read_text()) for n in ["START.json", "CLOSURE.json"])
        assert start["plan_pin"] == pin(plan_path) and start["target"] == c["target"] == target
        assert c["complete"] and c["source_stable"] and c["failure"] is None
        assert c["counts"]["new_origin_worlds"] == 1 and c["counts"]["hidden_samples"] == 4 and c["counts"]["single_hand_dispatched"] == 12
        audit = verify_scores(d, c, plan)
        counts.update(c["counts"])
        deltas, outcomes = Counter(), Counter()
        for sample in range(1, 5):
            results = {r["arm"]: r for r in c["results"] if r["sample"] == sample}
            assert set(results) == {"A", "B", "C"} and len(set(r["sample_key"] for r in results.values())) == 1
            accounts = {arm: account(r, target["focal_seat"]) for arm, r in results.items()}
            pair = {"target": index, "root_id": target["case"]["root_id"], "label": target["case"]["label"],
                "classes": target["case"]["classes"], "sample": sample, "accounts": accounts,
                "actual_fans": {a: r["settlement"]["fan"] if r["settlement"]["winner_seat"] == target["focal_seat"] else None for a, r in results.items()}}
            for left, right in [("B", "A"), ("C", "A"), ("C", "B")]:
                key = left + "_minus_" + right
                pair[key] = {k: accounts[left][k] - accounts[right][k] for k in accounts[left]}
            comparisons.append(pair)
            deltas.update(pair["C_minus_A"])
            outcomes["C_vs_A_positive" if pair["C_minus_A"]["net"] > 0 else "C_vs_A_negative" if pair["C_minus_A"]["net"] < 0 else "C_vs_A_equal"] += 1
        target_summaries.append({"target": index, "label": target["case"]["label"], "classes": target["case"]["classes"],
            "focal_seat": target["focal_seat"], "four_conditional_C_minus_A": dict(deltas), "outcomes": dict(outcomes), "audit": audit})
        for p in d.iterdir():
            if p.is_file():
                files[str(p)] = pin(p)
    assert counts["single_hand_dispatched"] == plan["planned_single_hand_continuations"] == 108 and unchanged(plan)
    save(_project_file(_PROJECT_ROOT, HERE / "OPPORTUNITY-PROBE-CLOSED-v2.json"), {"schema": "t186-opportunity-probe-closed/1", "complete": True,
        "plan_pin": pin(plan_path), "counts": dict(counts), "target_summaries": target_summaries, "comparisons": comparisons,
        "files": files, "source_stable": True, "actual_cpu_workers": 4, "resources_released": True,
        "sampler_interpretation": plan["sampler_interpretation"], "official_deadline_or_natural_strength_admission": False,
        "new_scores_worlds_tables_models_HTTP_at_readback": 0})
    print(json.dumps({"complete": True, "counts": dict(counts), "targets": target_summaries}, ensure_ascii=False))


if __name__ == "__main__":
    with postprocess_lock("T186-condition-readback"):
        main()
