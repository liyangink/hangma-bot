"""自摸竞速提案的预冻结输入、生产行为、合同边界与跨执行器核验。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import asyncio
from dataclasses import replace
import json
import sys

import selfdraw_tempo_batch as batch
import check_candidate_python_semantics as semantics
from check_discard_arithmetic import action, view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import DecisionBudget
from sitin_process import run_supervised

b = batch.b
PANEL = batch.OUT / "diagnostic-panel.json"
BOUNDARIES = batch.OUT / "boundary-inputs.json"


def cases():
    """评分合同形状检查；不声称合成支持数对应某条完整合法牌谱。"""
    a = action("4b", 12, 1)
    c = action("8t", 4, 0)
    base = view((a, c), familiar=())
    return [
        ("ready_vs_one_away", base, "scored"),
        ("one_vs_two_away", view((a, action("8t", 20, 2)), familiar=()), "scored"),
        ("same_distance_different_support", view((a, action("8t", 8, 1)), familiar=()), "scored"),
        ("zero_visible_support", view((action("4b", 0, 0), c), familiar=()), "scored"),
        ("same_scale_call_wait", view((action("4b", 12, 1, "peng"), action("", 12, 1, "pass")), familiar=()), "scored"),
        ("unknown_action_below_known", replace(base, actions=tuple(sorted(base.actions + (action("", kind="pass"),), key=lambda x:x.action_key))), "unknown_floor"),
        ("hu_above_known", replace(base, actions=tuple(sorted(base.actions + (action("", kind="hu"),), key=lambda x:x.action_key))), "hu_first"),
        ("all_unknown", view((action("4b"), action("8t")), familiar=()), "abstain"),
        ("missing_wall_keeps_known", replace(base, visible_state=replace(base.visible_state, remaining_tile_count=None)), "scored"),
        ("hand_permutation", replace(base, visible_state=replace(base.visible_state, my_hand=tuple(reversed(base.visible_state.my_hand)))), "same_ready_scores"),
    ]


def freeze():
    """复用既有公开请求，核对编码/投影相同后登记当前执行依赖，不修改旧证据。"""
    if PANEL.exists() or BOUNDARIES.exists():
        raise ValueError("检查输入已冻结")
    old = b.HERE / "stage-rank-preflight-20260920/panel.json"
    rows = b.read(old)["rows"]
    for row in rows:
        record = row["record"]
        if b.behavior.digest(record["request"]) != record["request_sha256"]:
            raise ValueError("旧输入摘要不符")
        request = b.behavior.decision_request_from_json(record["request"])
        if b.behavior.capture_request(request) != record:
            raise ValueError("旧输入往返或当前投影已改变")
    b.write(PANEL, {"created_at_utc": b.search.utc_now(), "rows": rows,
        "deps_digest": b.search.av_gates().av_deps_digest(),
        "source": {"path": str(old), "sha256": b.digest(old.read_bytes())},
        "scope": "112份已曝光真实/规则条件/故障输入，只检查当前执行，不继承历史效果", "selection_eligible": False})
    b.write(BOUNDARIES, {"created_at_utc": b.search.utc_now(),
        "rows": [{"name": name, "view": sample.candidate_view(), "invariant": invariant}
                 for name, sample, invariant in cases()],
        "scope": "交付前固定合同边界；具体公式手算在作者交付后独立推导"})
    print("frozen", len(rows), "inputs and", len(cases()), "boundaries", flush=True)


def source_path():
    """读取当前候选并核对迭代冻结身份，不猜首答或修复位置。"""
    sub = batch.OUT / batch.NAME
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / "run"))
    ok, why, _ = b.search.av_verify_run_identity(state)
    if not ok: raise ValueError(why)
    return b.Path(state["iter_dir"]) / "generation/candidate.py"


def boundary():
    """不指定新算法最优动作；核对已知/未知、胡层和输入表示不变量。"""
    source = source_path()
    scorer = ActionValueScorer("tempo-boundary", source.read_text())
    frozen = b.read(BOUNDARIES)
    rows = []
    base_scores = None
    for (name, sample, invariant), old in zip(cases(), frozen["rows"], strict=True):
        if b.behavior.digest(sample.candidate_view()) != b.behavior.digest(old["view"]):
            raise ValueError("冻结边界发生漂移")
        result = scorer.score(sample)
        scores = {e.action_key:e.score for e in result.entries}
        errors = []
        if result.status != ("ABSTAIN" if invariant == "abstain" else "SCORED"): errors.append("status")
        if result.status == "SCORED" and set(scores) != {a.action_key for a in sample.actions}: errors.append("coverage")
        if invariant == "unknown_floor" and not scores["pass"] < min(v for k,v in scores.items() if k != "pass"): errors.append("unknown_floor")
        if invariant == "hu_first" and not scores["hu"] > max(v for k,v in scores.items() if k != "hu"): errors.append("hu_first")
        if name == "ready_vs_one_away": base_scores = scores
        if invariant == "same_ready_scores" and scores != base_scores: errors.append("hand_permutation")
        rows.append({"name": name, "status": result.status, "scores": scores,
            "trace": {e.action_key:dict(e.trace) for e in result.entries},
            "operations": scorer.last_operation_count, "errors": errors})
    report = {"status": "PASS" if all(not r["errors"] for r in rows) else "FAIL", "rows": rows,
        "source_sha256": b.digest(source.read_bytes()), "input_sha256": b.digest(BOUNDARIES.read_bytes())}
    b.write(batch.OUT / batch.NAME / "boundary-check.json", report)
    print(report["status"], [(r["name"],r["errors"]) for r in rows if r["errors"]], flush=True)


def behavior():
    """通过正式choose对比稳定V2，记录全分数/trace及实际计数；不是效果样本。"""
    source = source_path()
    panel = b.read(PANEL)
    if panel["deps_digest"] != b.search.av_gates().av_deps_digest(): raise ValueError("依赖漂移")
    scorer = ActionValueScorer("selfdraw-tempo", source.read_text())
    v2 = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    rows = []
    for row in panel["rows"]:
        request = b.behavior.decision_request_from_json(row["record"]["request"])
        chosen = b.behavior.evaluate_request(scorer, row["name"], request)
        plan = asyncio.run(v2.choose(request, DecisionBudget(1.0, 2.0, 3.0)))
        v2_order = [entry.action_key for entry in plan.candidates]
        scored = scorer.score(b.behavior.build_scoring_view(request))
        rows.append({"origin": row["origin"], "name": row["name"], "candidate": chosen,
            "v2_order": v2_order, "first_changed": chosen["ordered_actions"][:1] != v2_order[:1],
            "operations": scorer.last_operation_count,
            "trace": {entry.action_key:dict(entry.trace) for entry in scored.entries}})
    summary = {"inputs": len(rows), "scored": sum(r["candidate"]["status"] == "SCORED" for r in rows),
        "first_changed": sum(r["first_changed"] for r in rows), "max_operations": max(r["operations"] for r in rows)}
    b.write(batch.OUT / batch.NAME / "diagnostic-comparison.json", {"summary": summary, "rows": rows,
        "source_sha256": b.digest(source.read_bytes()), "panel_sha256": b.digest(PANEL.read_bytes()),
        "selection_eligible": False, "release_eligible": False})
    print(summary, flush=True)


def reference(worker=False):
    """静态与监督源码检查后，仅在30秒隔离进程中做标准Python差分。"""
    semantics.experiment.OUT = batch.OUT
    semantics.checks.PANEL = PANEL
    if worker:
        semantics.worker(batch.NAME, source_path())
        return
    process = run_supervised([sys.executable, __file__, "reference", "--worker"],
        cwd=b.ROUTE.parents[1], timeout_sec=30, max_output_chars=200000)
    b.write(batch.OUT / batch.NAME / "reference-process.json", process.to_json())
    if process.returncode != 0 or process.timed_out or process.group_still_alive or process.output_truncated:
        raise ValueError("参考检查进程失败")
    result = json.loads(process.stdout)
    result["scope"] = str(result["cases"]) + "固定输入的跨执行器语义差分；不证明全域等价，不作为评分替代通道或强度样本"
    b.write(batch.OUT / batch.NAME / "python-semantics-check.json", result)
    print(result["status"], result["cases"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "boundary", "behavior", "reference"))
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.operation == "reference": reference(args.worker)
    else: {"freeze": freeze, "boundary": boundary, "behavior": behavior}[args.operation]()
