"""冻结旧批全部102个换弃牌首分歧，区分快速进张、备用并集和自然面子准备。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

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
import time
from dataclasses import asdict
from pathlib import Path

from common import HERE, ROOT, canonical, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import background_priority, postprocess_lock



def discard_metrics(view):
    """记录全部合法弃牌的原规则事实，不重算数学、不选支配动作。

    宽度沿用生产投影的公开相容定义；容量仅在相关码全部 exact 时相加，
    未知保持 None。自然面子目标不含将、不借白，不当成完整胡牌速度。
    """
    from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER
    nodes = {n.node_key: n for n in view.nodes}
    result = {}
    for action in view.actions:
        if action.action_type != "discard":
            continue
        todo, visited, waiting_nodes = [action.node_key], set(), {}
        while todo:
            key = todo.pop()
            if key in visited:
                continue
            visited.add(key)
            node = nodes[key]
            if node.waiting is not None:
                waiting_nodes[key] = node.waiting
            todo.extend(node.children)
        dev.require(len(waiting_nodes) == 1, "合法弃牌不是唯一真实等待态，不能合并其宽度")
        w = next(iter(waiting_nodes.values()))
        held = w.structure.natural_counts33 + (w.structure.whites_held,)
        def scope(codes):
            if codes is None:
                return None
            selected = set(codes)
            compatible = [i for i, code in enumerate(CANONICAL_TILE_ORDER)
                if code in selected and held[i] < 4 and (w.unseen_evidence[i] != "exact"
                    or w.unseen_capacities[i] is None or w.unseen_capacities[i] > 0)]
            exact = all(w.unseen_evidence[i] == "exact" and w.unseen_capacities[i] is not None for i in compatible)
            return {"codes": [CANONICAL_TILE_ORDER[i] for i in compatible], "compatible_width": len(compatible),
                "all_capacities_exact": exact,
                "exact_public_unseen_capacity_sum": sum(w.unseen_capacities[i] for i in compatible) if exact else None}
        union, natural = scope(w.useful_codes), scope(w.natural_preparation.natural_need_improvement_codes)
        dev.require(union["compatible_width"] == w.useful_code_width and
            natural["compatible_width"] == w.natural_preparation_code_width, "公开相容宽度不符生产定义")
        sh = w.structure
        result[action.action_key] = {"combined_shanten": min(sh.standard_shanten, sh.seven_pairs_shanten)
                if sh.seven_pairs_shanten is not None else sh.standard_shanten,
            "standard_shanten": sh.standard_shanten, "seven_pairs_shanten": sh.seven_pairs_shanten,
            "whites_held": sh.whites_held, "meld_set_count": sh.meld_set_count,
            "combined_improvement": scope(w.combined_useful_codes), "family_union_improvement": union,
            "standard_improvement": scope(w.standard_useful_codes), "seven_improvement": scope(w.seven_pairs_useful_codes),
            "natural_set_improvement": natural,
            "natural_set_draw_lower_bound": w.natural_preparation.natural_draw_lower_bound,
            "natural_set_discard_lower_bound": w.natural_preparation.natural_discard_lower_bound,
            "purpose_targets": [asdict(t) for t in sh.targets]}
    return result


def main():
    """开发诊断408评分；没有新世界/完整桌，不改变当前512桌原选择门或公式。"""
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    background_priority()
    with postprocess_lock("current_formulas_on_prior_closed_discard_diagnostics"):
        development, development_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
        dev.validate_plan(development)
        dev.frozen(development)
        old_directory = _project_file(_PROJECT_ROOT, HERE / "prior-joint-first-divergences")
        old, old_pin = dev.read(old_directory / "CLOSED.json")
        dev.require(old["complete"] is True and old["actual_paired_complete_tables_read"] == 128, "旧首分歧不完整")
        rows_path, raw_path = old_directory / "rows.jsonl", old_directory / "original-public-first-rows.jsonl.gz"
        dev.require(pin(rows_path) == old["rows_file_pin"] and pin(raw_path) == old["original_first_rows_pin"], "旧原行漂移")
        selected = [r for r in (dev.decode(line) for line in rows_path.read_bytes().splitlines()) if
            r["status"] == "first_divergence" and (r["parent_action"].startswith("discard:") and r["child_action"].startswith("discard:"))]
        dev.require(len(selected) == 102, "不是旧批全部102个换弃牌首分歧")
        old_rows = {}
        keys = {(r["root_id"], r["rotation"]) for r in selected}
        with gzip.open(raw_path, "rb") as stream:
            for line in stream:
                row = dev.decode(line)
                key = row["root_id"], row["rotation"]
                if key in keys:
                    dev.require(key not in old_rows, "原公开首分歧行重复")
                    old_rows[key] = row
        dev.require(set(old_rows) == keys, "102原公开首分歧行缺失")
        batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        arms = [development["parent"], *development["candidates"]]
        dev.require(len(arms) == 4, "当前诊断只覆盖原父+三冻结候选")
        sources = [Path(a["source_file"]).read_text() for a in arms]
        dev.require(all(batch.identity(s) == a["identity"] for a, s in zip(arms, sources)), "实际公式身份漂移")
        files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
            _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"), old_directory / "CLOSED.json", rows_path, raw_path,
            *[Path(a["source_file"]) for a in arms])}
        out = _project_file(_PROJECT_ROOT, HERE / "prior-discard-formula-probe")
        out.mkdir(exist_ok=False)
        # 此处尚未分析新候选分数或选择结果；额外已曝光来源不能进入确认分母。
        save(out / "PLAN.json", {"files": files, "source_manifest": development["source_manifest"],
            "development_plan_pin": development_pin, "old_first_divergence_closed_pin": old_pin,
            "selected_cases": [{k: r[k] for k in ("root_id", "rotation", "round_no", "trigger_seq", "parent_action", "child_action", "view_sha256")} for r in selected],
            "selection": "旧全批全部discard->discard首分歧；不按终分/胡型/当前候选表现删改",
            "arms": arms, "planned_score_attempts": 408, "capture_limits": {
                "max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 128},
            "post_selected_old_development_diagnostics_not_independent_strength": True,
            "frozen_current_selection_confirmation_sources_thresholds_unchanged": True})
        executors = [ActionValueExecutor(s, max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes) for s in sources]
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 128))
        results, attempts, failure, capture_result, started = [], 0, None, None, time.monotonic()
        try:
            with (out / "rows.jsonl").open("x") as stream:
                for selected_row in selected:
                    originals = old_rows[selected_row["root_id"], selected_row["rotation"]]
                    old_parent = originals["parent_original_row"]
                    obs, key = observation_from_json(old_parent["observation"]), window_key_from_json(old_parent["window_key"])
                    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    dev.require(analysis.completeness.value == "complete", "公开规则分析未完整")
                    request = DecisionRequest(obs, CompetitionContext("t185-prior-discard", None, None, None, None, (), 0),
                        analysis, old_parent["decision_id"], key.trigger_seq, key, ())
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    view_sha = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                    dev.require(view_sha == selected_row["view_sha256"], "新诊断图与旧实际完整公开图不等价")
                    legal = {c.action_key for c in analysis.legal_candidates}
                    metrics = discard_metrics(view)
                    outputs = []
                    for arm, executor in zip(arms, executors):
                        receipt = capture.store(view.candidate_view())
                        dev.require(receipt.saved_before_score, "真实评分前捕获失败")
                        attempts += 1
                        answer = executor.score_vip_route(view)
                        dev.require(answer.status == "SCORED", "当前公式未完成全评分")
                        entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)} for e in answer.entries], key=lambda e: e["action_key"])
                        dev.require(len(entries) == len(legal) and {e["action_key"] for e in entries} == legal and
                            hashlib.sha256(canonical(view.candidate_view())).hexdigest() == view_sha, "合法根或输入不变校验失败")
                        outputs.append({"candidate_id": arm["identity"]["candidate_id"], "label": arm["label"],
                            "entries": entries, "operation_count": executor.last_operation_count,
                            "first": sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"], "capture": asdict(receipt)})
                    expected = sorted([{"action_key": c["action_key"], "score": c["score"], "trace": c["trace"]["detail"]}
                        for c in old_parent["candidates"]], key=lambda e: e["action_key"])
                    dev.require(canonical(outputs[0]["entries"]) == canonical(expected) and
                        outputs[0]["operation_count"] == old_parent["candidate_operations"], "原S02全输出或计量重算不精确")
                    row = {"root_id": selected_row["root_id"], "rotation": selected_row["rotation"],
                        "round_no": selected_row["round_no"], "trigger_seq": selected_row["trigger_seq"],
                        "view_sha256": view_sha, "white_count": old_parent["white_count"],
                        "old_parent_first": old_parent["selected_action_key"],
                        "old_joint_first": originals["child_original_row"]["selected_action_key"], "outputs": outputs, "discard_metrics": metrics,
                        "metric_scope": "all legal discard facts; primary combined shanten vs family union vs natural sets are separate; public capacities are not wall probabilities",
                        "new_first_changes_are_not_strength_or_causal_proof": True}
                    results.append(row)
                    stream.write(canonical(row).decode() + "\n")
                    stream.flush()
            dev.require(attempts == 408 and len(results) == 102, "额外诊断评分分母不同")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "completed_cases": len(results), "actual_score_attempts": attempts}
        finally:
            try:
                capture_result = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
            stable = all(pin(Path(p)) == h for p, h in files.items()) and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in development["source_manifest"].items())
            complete = failure is None and len(results) == 102 and stable and capture_result is not None and capture_result["terminal"]["terminal_valid"]
            save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
                "files": files, "plan_pin": pin(out / "PLAN.json"), "actual_score_attempts": attempts,
                "actual_cases": len(results), "capture": capture_result, "rows": results,
                "elapsed_monotonic_seconds": time.monotonic() - started,
                "no_current_natural_table_scores_read": True,
                "frozen_current_selection_confirmation_sources_thresholds_unchanged": True,
                "new_worlds_tables_model_calls_HTTP": 0, "new_strength_or_deadline_admission": False})
        dev.require(complete, "旧缺口上的当前公式诊断未通过，原失败保留")
        print({"complete": complete, "actual_score_attempts": attempts, "cases": len(results)}, flush=True)


if __name__ == "__main__":
    main()
