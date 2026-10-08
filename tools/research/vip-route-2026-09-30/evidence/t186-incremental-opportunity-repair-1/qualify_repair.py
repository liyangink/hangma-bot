"""T186公开状态机械和行为筛选；缓存父分，重复子评分，不重跑牌局。"""

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
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, canonical, pin, save
from t185_prepare_confirmation import background_priority
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def require(condition, message):
    """输入、完整输出和确定性任一不符即拒绝；费用和失败原样保存。"""
    if not condition:
        raise ValueError(message)


def main():
    """221公开图双次全评分；只授机械资格，不授收益或动作时限。"""
    background_priority()
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
    derivation = json.loads((package / "DERIVATION.json").read_text())
    require(derivation["complete"] and derivation["executable_source_unchanged"] and
            not derivation["is_entire_reply_raw_model_output"] and
            derivation["derived_generation_pin"] == pin(package / "generation.json") and
            derivation["original_generation_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-model-output/generation.json")),
            "派生元数据修复未绑定原失败或算法源码")
    proposal = load_vip_parents([package], batch)[0]
    cases = json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"]
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    require(all(pin(Path(p)) == h for p, h in preparation["files"].items()), "准备材料漂移")
    old_gate_file = _project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-incremental-model-output-qualification/CLOSURE.json")
    old_gate = json.loads(old_gate_file.read_text())
    require(old_gate["complete"] and old_gate["mechanical_passed"] and
            old_gate["identity"] == preparation["formal_parent"], "原正式父代资格不同")
    parents = {r["label"]: {"first": r["candidate_first"], "view_sha256": r["view_sha256"]}
               for r in old_gate["rows"]}
    source_pins = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "CASES.json"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), old_gate_file, package / "generation.json", package / "candidate.py",
        package / "DERIVATION.json", _project_file(_PROJECT_ROOT, HERE / "REPLY-METADATA-REPAIR.json"))}
    for slot in range(4):
        path = _project_file(_PROJECT_ROOT, HERE / f"confirmation-paths/worker-{slot}/public-first-rows.jsonl.gz")
        source_pins[str(path)] = pin(path)
        with gzip.open(path, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                child = row["child_original_row"]
                parents[f"closed-confirmation:{row['ordinal']:03d}"] = {
                    "first": child["selected_action_key"],
                    "view_sha256": child["scoring_calls"][0]["input_capture"]["view_sha256"]}
    executor = ActionValueExecutor(proposal["source"], max_operations=batch.max_operations,
                                  max_local_collection_size=batch.projection_limits.max_nodes)
    out = _project_file(_PROJECT_ROOT, HERE / "qualification")
    out.mkdir(exist_ok=False)
    save(out / "START.json", {"identity": proposal["identity"], "files": source_pins,
        "planned_public_views": len(cases), "planned_score_attempts": len(cases) * 2,
        "no_strength_or_deadline_admission": True})
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 1073741824, 512))
    rows, attempts, failure, terminal = [], 0, None, None
    started = time.monotonic()
    try:
        with (out / "rows.jsonl").open("x") as stream:
            for case in cases:
                observation = observation_from_json(case["observation"])
                key = window_key_from_json(case["window_key"])
                analysis = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
                require(analysis.completeness.value == "complete", "公开规则分析不完整")
                request = DecisionRequest(observation, CompetitionContext("t186-qualification", None, None, None,
                    None, (), 0), analysis, case["label"], key.trigger_seq, key, ())
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                require(digest == parents[case["label"]]["view_sha256"], "重构图与公开原件不同")
                legal = {a.action_key for a in view.actions}
                outputs, operations, durations = [], [], []
                for repeat in range(2):
                    receipt = capture.store(view.candidate_view())
                    require(receipt.saved_before_score, "评分前记录失败")
                    attempts += 1
                    clock = time.monotonic()
                    answer = executor.score_vip_route(view)
                    durations.append(time.monotonic() - clock)
                    require(answer.status == "SCORED", "候选未完整评分")
                    entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                                     for e in answer.entries], key=lambda e: e["action_key"])
                    require(len(entries) == len(legal) and {e["action_key"] for e in entries} == legal and
                            all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries),
                            "完整合法根缺失或非有限分")
                    require(hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest, "候选改变输入")
                    outputs.append(entries)
                    operations.append(executor.last_operation_count)
                require(canonical(outputs[0]) == canonical(outputs[1]) and operations[0] == operations[1], "候选不确定")
                first = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                row = {"label": case["label"], "root_id": case["root_id"], "classes": case["classes"],
                    "view_sha256": digest, "entries": entries, "operation_counts": operations,
                    "score_monotonic_seconds": durations, "parent_first": parents[case["label"]]["first"],
                    "candidate_first": first, "first_changed": first != parents[case["label"]]["first"]}
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error), "actual_views": len(rows)}
    finally:
        try:
            terminal = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
    stable = all(pin(Path(p)) == h for p, h in source_pins.items())
    complete = failure is None and stable and len(rows) == len(cases) and terminal["terminal"]["terminal_valid"]
    changed = [r for r in rows if r["first_changed"]]
    save(out / "CLOSED.json", {"complete": complete, "mechanical_passed": complete,
        "failure": failure, "source_stable": stable, "identity": proposal["identity"], "files": source_pins,
        "actual_completed_views": len(rows), "actual_score_attempts": attempts,
        "changed_windows": len(changed), "changed_sources": sorted({r["root_id"] for r in changed}),
        "changes_by_class": dict(Counter(c for r in changed for c in r["classes"])),
        "rows_pin": pin(out / "rows.jsonl"), "capture": terminal,
        "elapsed_monotonic_seconds": time.monotonic() - started,
        "actual_max_score_monotonic_seconds": max((d for r in rows for d in r["score_monotonic_seconds"]), default=None),
        "maximum_operations": max((max(r["operation_counts"]) for r in rows), default=None),
        "new_worlds_tables_models_HTTP": 0, "strength_or_original_deadline_admission": False})
    require(complete, "资格未通过，失败保留，不自动重试")
    print(json.dumps({"complete": True, "views": len(rows), "score_attempts": attempts,
        "changed_windows": len(changed)}), flush=True)


if __name__ == "__main__":
    main()
