"""R18 P10：七对多步生存轨迹探针。

本试验复用 P9 已冻结的 29 个自然基础状态和公开状态一致隐藏分配，只在
正式 ``BotPolicy.choose`` 接缝外包一层只读记录器。记录器只读取当时的
``DecisionRequest``、规则候选和策略返回计划，不读取 ``WorldState``、他家
暗牌或未来牌墙。它回答分差变化来自本人先胡、他家先胡还是流局，并检查
普通型/七对向听的多步轨迹能否稳定采集，为 P10 新表示定字段。

本批仍是既有开发状态上的机制探针，不具备候选选择、隐藏确认或发布资格。
"""

from __future__ import annotations

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
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p9_midgame_hidden_world_teacher as p9  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p10-survival-trace-01-20260922')
SAMPLES_PER_STATE = 32


def write_json(path: Path, value: Any) -> None:
    """写入规范 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TracePolicy:
    """在正式策略外记录当时可见的动作与分牌型规则事实。"""

    def __init__(self, delegate: Any, *, seat: int,
                 journal: list[dict[str, Any]]) -> None:
        self.delegate = delegate
        self.seat = seat
        self.policy_id = "trace:" + str(getattr(delegate, "policy_id", type(delegate).__name__))
        self.journal = journal

    async def choose(self, request: Any, budget: Any) -> Any:
        plan = await self.delegate.choose(request, budget)
        chosen = plan.candidates[0] if plan.candidates else None
        chosen_key = None if chosen is None else chosen.action_key
        fact = next(
            (
                candidate.facts
                for candidate in request.rules.legal_candidates
                if candidate.action_key == chosen_key
            ),
            None,
        )
        self.journal.append({
            "round_no": request.observation.round_no,
            "trigger_seq": request.window_key.trigger_seq,
            "snapshot_seq": request.observation.snapshot_seq,
            "phase": request.window_key.phase.value,
            "seat": request.window_key.seat,
            "remaining_tile_count": request.observation.remaining_tile_count,
            "chosen_action": chosen_key,
            "legal_hu": any(
                candidate.action_key.startswith("hu")
                for candidate in request.rules.legal_candidates
            ),
            "standard_shanten_after": (
                None if fact is None else fact.standard_shanten_after
            ),
            "seven_pairs_shanten_after": (
                None if fact is None else fact.seven_pairs_shanten_after
            ),
            "standard_support_remaining": (
                None
                if fact is None or fact.standard_useful_tiles is None
                else sum(item.remaining_estimate for item in fact.standard_useful_tiles)
            ),
            "seven_pairs_support_remaining": (
                None
                if fact is None or fact.seven_pairs_useful_tiles is None
                else sum(item.remaining_estimate for item in fact.seven_pairs_useful_tiles)
            ),
        })
        return plan


def trace_summary(journal: list[dict[str, Any]], focal_seat: int,
                  cut_round_no: int) -> dict[str, Any]:
    """只把截取窗口所在当前局压成终止与路线进展标签。"""

    records = sorted(journal, key=lambda row: (
        int(row["round_no"]), int(row["trigger_seq"]), int(row["seat"]),
    ))
    current = [row for row in records if row["round_no"] == cut_round_no]
    hu = [record for record in current if str(record["chosen_action"]).startswith("hu")]
    if hu:
        terminal = "focal_hu" if hu[0]["seat"] == focal_seat else "opponent_hu"
        terminal_seat = int(hu[0]["seat"])
    else:
        terminal = "wall_draw_or_non_hu_end"
        terminal_seat = None
    focal_draws = [
        row for row in current
        if row["seat"] == focal_seat and row["phase"] == "draw"
    ]
    standard = [
        int(row["standard_shanten_after"])
        for row in focal_draws
        if row["standard_shanten_after"] is not None
    ]
    seven = [
        int(row["seven_pairs_shanten_after"])
        for row in focal_draws
        if row["seven_pairs_shanten_after"] is not None
    ]
    return {
        "terminal": terminal,
        "terminal_seat": terminal_seat,
        "policy_decisions": len(records),
        "current_round_policy_decisions": len(current),
        "later_round_policy_decisions": sum(row["round_no"] > cut_round_no for row in records),
        "focal_draw_decisions": len(focal_draws),
        "focal_legal_hu_windows": sum(bool(row["legal_hu"]) for row in focal_draws),
        "minimum_selected_standard_shanten": min(standard) if standard else None,
        "minimum_selected_seven_pairs_shanten": min(seven) if seven else None,
        "selected_standard_tenpai_windows": sum(value == 0 for value in standard),
        "selected_seven_pairs_tenpai_windows": sum(value == 0 for value in seven),
        "focal_draw_trace": focal_draws,
    }


def wrapped_arm(target: Mapping[str, Any], snapshot: Mapping[str, Any], action: str,
                label: str) -> tuple[list[Any], Any, list[dict[str, Any]]]:
    policies, forced = p9._policies_for_arm(
        target=target, snapshot=snapshot, action_key=action, label=label,
    )
    journal: list[dict[str, Any]] = []
    wrappers = [
        TracePolicy(policy, seat=seat, journal=journal)
        for seat, policy in enumerate(policies)
    ]
    return wrappers, forced, journal


def rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    snapshot = json.loads(p9.snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(p9.CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(p9.core.rule_config_from_contract(contract))
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    baseline, baseline_force, baseline_trace = wrapped_arm(
        target, snapshot, str(target["reference_action"]),
        "p10-reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    candidate, candidate_force, candidate_trace = wrapped_arm(
        target, snapshot, str(target["intervention_action"]),
        "p10-candidate-{0}-{1:02d}".format(target["target_id"], index),
    )
    double = opportunities.run_double_arm(
        rules=rules,
        snapshot=snapshot,
        baseline_policies_by_seat=baseline,
        candidate_policies_by_seat=candidate,
        config=opportunities._driver_config(),
        value_limits=p9.LIMITS,
        runtime=runtime,
        current_world_transform=lambda world: runtime["engine"].resample_public_consistent_hidden_world(
            world,
            focal_seat=int(target["focal_physical_seat"]),
            sample_key=sample_key,
        ),
    )
    focal = int(target["focal_physical_seat"])
    baseline_score = double["arms"]["baseline"].get("focal_stage_score")
    candidate_score = double["arms"]["candidate"].get("focal_stage_score")
    actions = {
        arm: (((double.get("window_actions") or {}).get("arms") or {}).get(arm) or {}).get("action_key")
        for arm in ("baseline", "candidate")
    }
    mechanical = bool(
        double.get("valid")
        and baseline_force.force_count == 1
        and candidate_force.force_count == 1
        and actions["baseline"] == target["reference_action"]
        and actions["candidate"] == target["intervention_action"]
        and baseline_score is not None
        and candidate_score is not None
    )
    return {
        "schema": "r18-p10-survival-trace-rollout/2",
        "target_id": target["target_id"],
        "rollout_index": index,
        "sample_key": sample_key,
        "mechanical_ok": mechanical,
        "score": {
            "reference": baseline_score,
            "intervention": candidate_score,
            "delta": None if not mechanical else int(candidate_score) - int(baseline_score),
        },
        "reference": trace_summary(
            baseline_trace, focal, int(target["features"]["round_no"]),
        ),
        "intervention": trace_summary(
            candidate_trace, focal, int(target["features"]["round_no"]),
        ),
    }


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("P10 轨迹试验目录已存在；拒绝覆盖")
    p9.verify_manifest()
    targets = p9.targets()
    keys = ["r18-p9-hidden-world-{0:02d}".format(i) for i in range(1, SAMPLES_PER_STATE + 1)]
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), {
        "schema": "r18-p10-survival-trace-authorization/2",
        "scope": "P9既有29状态×32个共同隐藏分配×P5/P7两臂；只读公开策略轨迹",
        "planned_tables": len(targets) * len(keys) * 2,
        "max_model_calls": 0,
        "development_only": True,
        "selection_eligible": False,
        "release_eligible": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p10-survival-trace-manifest/2",
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(p9.__file__), Path(opportunities.__file__),
            p9.P5, p9.P7, p9.CONTRACT, p9.OUT / "manifest.json",
        ]),
        "p9_result_sha256": digest(p9.OUT / "result.json"),
        "targets": len(targets),
        "sample_keys": keys,
        "planned_tables": len(targets) * len(keys) * 2,
        "workers": 8,
        "independent_unit": "自然基础状态；32个隐藏世界只用于估计各状态的机制标签，不冒充独立状态",
        "trace_scope": "只统计截取窗口所在round_no；后续局仅计数，不参与当前局终止分类",
        "predeclared_outcomes": ["focal_hu", "opponent_hu", "wall_draw_or_non_hu_end"],
        "development_only": True,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "tables": len(targets) * len(keys) * 2}, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    guard.verify(manifest["runtime"])
    if digest(p9.OUT / "result.json") != manifest["p9_result_sha256"]:
        raise ValueError("P9 结果哈希变化")
    return manifest, p9.targets()


def run() -> None:
    manifest, targets = verify()
    jobs = [
        (target, index, key)
        for target in targets
        for index, key in enumerate(manifest["sample_keys"], 1)
    ]
    failures = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
        futures = {pool.submit(rollout, *job): job for job in jobs}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            target, index, _ = futures[future]
            try:
                row = future.result()
                if not row["mechanical_ok"]:
                    raise RuntimeError("轨迹配对机械失败")
                write_json(_project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-{1:02d}.json".format(target["target_id"], index)), row)
            except Exception as exc:  # noqa: BLE001
                failures.append({"target_id": target["target_id"], "index": index,
                                 "error": type(exc).__name__ + ": " + str(exc)})
            if completed % 29 == 0:
                print(json.dumps({"completed_pairs": completed, "planned_pairs": len(jobs)}, ensure_ascii=False), flush=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "pairs": len(jobs) - len(failures), "planned_pairs": len(jobs), "failures": failures,
    })
    if failures:
        raise RuntimeError("P10 轨迹采集存在失败")


def analyze() -> None:
    manifest, targets = verify()
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))]
    expected = len(targets) * len(manifest["sample_keys"])
    if len(rows) != expected or not all(row["mechanical_ok"] for row in rows):
        raise ValueError("P10 轨迹不完整")
    counts = {}
    for arm in ("reference", "intervention"):
        counts[arm] = {
            kind: sum(row[arm]["terminal"] == kind for row in rows)
            for kind in manifest["predeclared_outcomes"]
        }
    state_rows = []
    for target in targets:
        selected = [row for row in rows if row["target_id"] == target["target_id"]]
        state_rows.append({
            "target_id": target["target_id"],
            "score_delta_mean": statistics.fmean(row["score"]["delta"] for row in selected),
            "focal_hu_rate_delta": statistics.fmean(
                (row["intervention"]["terminal"] == "focal_hu")
                - (row["reference"]["terminal"] == "focal_hu")
                for row in selected
            ),
            "opponent_hu_rate_delta": statistics.fmean(
                (row["intervention"]["terminal"] == "opponent_hu")
                - (row["reference"]["terminal"] == "opponent_hu")
                for row in selected
            ),
        })
    score = [row["score_delta_mean"] for row in state_rows]
    arrival = [row["focal_hu_rate_delta"] for row in state_rows]
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p10-survival-trace-result/2",
        "status": "COMPLETE_P10_CURRENT_ROUND_SURVIVAL_TRACE",
        "mechanical_ok": True,
        "base_states": len(state_rows),
        "paired_hidden_worlds": len(rows),
        "tables": len(rows) * 2,
        "terminal_counts": counts,
        "mean_of_state_score_delta_means": statistics.fmean(score),
        "mean_of_state_focal_hu_rate_deltas": statistics.fmean(arrival),
        "states": state_rows,
        "next_gate": "若三类终止标签全程闭合，扩到32世界并在新自然来源冻结多步表示；本批不得拟合阈值",
        "development_only": True,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8")), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
