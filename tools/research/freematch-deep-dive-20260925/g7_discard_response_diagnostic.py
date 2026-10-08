#!/usr/bin/env python3
"""赛后诊断 G7 首弃立即给他家制造的合法响应机会，不作线上特征。"""

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

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g7_new_root_paired_teacher as batch  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-discard-response-diagnostic-20260927')


def _response_facts(target, snapshot, action_key, rules, runtime):
    """仅使用赛后重建的同一隐藏世界，审查弃牌后各家的合法响应。"""

    p84 = batch.teacher.p84
    engine, world = p84.opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=p84.p83.LIMITS,
        runtime=runtime,
    )
    frame = engine.frame(world)
    cut = [decision for decision in frame.decisions
           if decision.window_key == p84.window_key_from_json(target["window_key"])]
    if len(cut) != 1 or len(frame.decisions) != 1:
        raise ValueError("目标摸牌弃牌窗口不唯一")
    analysis = rules.analyze(cut[0].observation, value_limits=p84.p83.LIMITS)
    selected = [candidate.action for candidate in analysis.legal_candidates
                if candidate.action_key == action_key]
    if len(selected) != 1:
        raise ValueError("首动作不再合法")
    world = engine.advance(world, frame.revision,
                           (runtime["choice_factory"](cut[0].window_key, selected[0]),))
    response = engine.frame(world)
    by_seat = {}
    for decision in response.decisions:
        if decision.window_key.seat == target["focal_physical_seat"]:
            raise ValueError("弃牌后仍由焦点座决策")
        legal = rules.analyze(decision.observation,
                              value_limits=p84.p83.LIMITS).legal_candidates
        by_seat[str(decision.window_key.seat)] = sorted(
            candidate.action_key for candidate in legal
            if candidate.action_key != "pass"
        )
    return {"by_seat": by_seat,
            "nonpass_seats": sum(bool(actions) for actions in by_seat.values()),
            "nonpass_actions": sum(len(actions) for actions in by_seat.values())}


def main() -> None:
    if OUT.exists():
        raise SystemExit("赛后响应诊断结果已存在，拒绝覆盖")
    manifest, targets = batch.teacher._verify()
    result = batch.teacher._read(batch.OUT / "result.json")
    if result["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("教师批次未完整")
    score_by_target = {row["target_id"]: row for row in result["rows"]}
    p84 = batch.teacher.p84
    contract = batch.teacher._read(batch.teacher.g1.CONTRACT)
    rules = p84.HangmaRules(p84.core.rule_config_from_contract(contract))
    rows = []
    for target in targets:
        snapshot = batch.teacher._read(p84.snapshot_path(target))
        runtime = p84.opportunities.build_real_runtime(
            rules_config=rules.config,
            rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
            seed=int(snapshot["match_spec"]["seed"]),
            scenario_id=str(snapshot["match_spec"]["scenario_id"]),
        )
        a = _response_facts(target, snapshot, target["reference_action"],
                            rules, runtime)
        b = _response_facts(target, snapshot, target["intervention_action"],
                            rules, runtime)
        score = score_by_target[target["target_id"]]
        rows.append({"target_id": target["target_id"],
                     "source_root_id": target["source"]["source_root_id"],
                     "mix": score["mix"], "proxy_class": score["proxy_class"],
                     "a": a, "b": b,
                     "extra_b_response_action": b["nonpass_actions"] > a["nonpass_actions"],
                     "table_delta_mean": score["table_delta_mean"],
                     "target_round_delta_mean": score["target_round_delta_mean"]})
    grouped = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        count = grouped[row["mix"]][row["proxy_class"]]
        count["targets"] += 1
        count["b_extra_response_actions"] += int(row["extra_b_response_action"])
        count["a_response_targets"] += int(row["a"]["nonpass_actions"] > 0)
        count["b_response_targets"] += int(row["b"]["nonpass_actions"] > 0)
        count["b_extra_and_round_loss"] += int(
            row["extra_b_response_action"] and row["target_round_delta_mean"] < 0)
    output = {"schema": "g7-discard-response-diagnostic/1",
              "teacher_manifest_sha256": batch.teacher._sha(batch.OUT / "manifest.json"),
              "teacher_result_sha256": batch.teacher._sha(batch.OUT / "result.json"),
              "rows": rows,
              "grouped": {mix: {category: dict(counts)
                                for category, counts in values.items()}
                          for mix, values in grouped.items()},
              "information_boundary": "赛后同隐藏世界真实他家暗手，只用于解释；线上不可读取"}
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output["grouped"], ensure_ascii=False))


if __name__ == "__main__":
    main()
