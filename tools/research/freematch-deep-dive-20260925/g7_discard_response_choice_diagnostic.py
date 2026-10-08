#!/usr/bin/env python3
"""赛后核对新增碰机会是否被冻结对手策略实际选择。"""

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

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g7_discard_response_diagnostic as diagnostic  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402

OUT = diagnostic.OUT / "policy-choices.json"


def main() -> None:
    if OUT.exists():
        raise SystemExit("赛后对手响应选择已存在，拒绝覆盖")
    prior = json.loads((diagnostic.OUT / "result.json").read_text(encoding="utf-8"))
    batch = diagnostic.batch
    p84 = batch.teacher.p84
    manifest, targets = batch.teacher._verify()
    target_by_id = {target["target_id"]: target for target in targets}
    contract = batch.teacher._read(batch.teacher.g1.CONTRACT)
    rules = p84.HangmaRules(p84.core.rule_config_from_contract(contract))
    rows = []
    for row in prior["rows"]:
        if not row["extra_b_response_action"]:
            continue
        target = target_by_id[row["target_id"]]
        snapshot = batch.teacher._read(p84.snapshot_path(target))
        source = target["source"]
        plans = p84.natural.build_seat_stage_plans(
            contract=contract, opponent=source["mix"],
            root_index=source["root_index"], focal_seat=source["focal_seat"],
            panel_seed=source["panel_seed"],
        )
        plan = plans[source["table_no"]-1]
        situation = p84.stage_projection(
            target, plan, int(snapshot["match_spec"]["rounds_per_game"]),
        )
        config = replace(p84.opportunities._driver_config(),
                         competition_tournament_id=str(plan.scenario_id))
        runtime = p84.opportunities.build_real_runtime(
            rules_config=rules.config,
            rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
            seed=int(snapshot["match_spec"]["seed"]),
            scenario_id=str(snapshot["match_spec"]["scenario_id"]),
        )
        engine, world = p84.opportunities.rebuild_world(
            rules=rules, snapshot=snapshot, value_limits=p84.p83.LIMITS,
            runtime=runtime,
        )
        frame = engine.frame(world)
        cut = [decision for decision in frame.decisions
               if decision.window_key == p84.window_key_from_json(target["window_key"])]
        if len(cut) != 1 or len(frame.decisions) != 1:
            raise ValueError("目标弃牌窗口不是唯一")
        analysis = rules.analyze(cut[0].observation, value_limits=p84.p83.LIMITS)
        actions = [candidate.action for candidate in analysis.legal_candidates
                   if candidate.action_key == target["intervention_action"]]
        if len(actions) != 1:
            raise ValueError("B 不再合法")
        world = engine.advance(world, frame.revision,
                               (runtime["choice_factory"](cut[0].window_key,
                                                          actions[0]),))
        response = engine.frame(world)
        policies, _ = p84.policies_for_arm(
            target=target, snapshot=snapshot,
            forced_action_key=target["intervention_action"],
            label="g7-response-choice-" + target["target_id"],
        )
        actual = {}
        for decision in response.decisions:
            rules_analysis = rules.analyze(decision.observation,
                                           value_limits=p84.p83.LIMITS)
            request = p84.opportunities.real_window_request(
                decision=decision, analysis=rules_analysis,
                match_id=str(plan.match_id), config=config,
                now_monotonic=lambda: 800.0, stage_situation=situation,
            )
            chosen = asyncio.run(policies[decision.window_key.seat].choose(
                request,
                config.budget_policy.build(800.0, decision.timeout_seconds),
            ))
            if not chosen.candidates:
                raise ValueError("对手响应策略未返回候选")
            key = action_key(chosen.candidates[0].action)
            if key not in {item.action_key for item in rules_analysis.legal_candidates}:
                raise ValueError("对手首选响应不合法")
            actual[str(decision.window_key.seat)] = key
        rows.append({"target_id": target["target_id"], "mix": row["mix"],
                     "proxy_class": row["proxy_class"],
                     "source_root_id": row["source_root_id"],
                     "b_legal": row["b"]["by_seat"],
                     "b_chosen": actual,
                     "any_nonpass_chosen": any(key != "pass" for key in actual.values()),
                     "target_round_delta_mean": row["target_round_delta_mean"],
                     "table_delta_mean": row["table_delta_mean"]})
    output = {"schema": "g7-discard-response-choice-diagnostic/1",
              "teacher_manifest_sha256": batch.teacher._sha(batch.OUT / "manifest.json"),
              "prior_response_sha256": batch.teacher._sha(diagnostic.OUT / "result.json"),
              "rows": rows,
              "nonpass_chosen": sum(row["any_nonpass_chosen"] for row in rows),
              "note": "赛后同隐藏世界核查；不是线上可见特征"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"targets": len(rows),
                      "nonpass_chosen": output["nonpass_chosen"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
