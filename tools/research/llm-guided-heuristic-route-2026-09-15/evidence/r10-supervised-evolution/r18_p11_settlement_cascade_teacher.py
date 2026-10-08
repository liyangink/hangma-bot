"""R18 P11：截取局结算与后续局级联分解教师。"""

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
import r18_p10_survival_trace_teacher as p10  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p11-settlement-cascade-teacher-01-20260922')


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SettlementCaptureEngine:
    """透明代理模拟器，仅在非历史一致续打中保存新完成的局记录。"""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.records: list[Any] = []
        self.rules_hash = getattr(inner, "rules_hash", None)
        self.fixture_mode = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def advance(self, world: Any, revision: int, choices: Any) -> Any:
        before = len(world.round_records)
        result = self.inner.advance(world, revision, choices)
        if not world.history_consistent and len(result.round_records) > before:
            self.records.extend(result.round_records[before:])
        return result


def p10_rows() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((p10.OUT / "rollouts").glob("*.json"))
    ]


def selected_pairs() -> list[dict[str, Any]]:
    """冻结所有终止类型改变或完整剩余桌分差非零的机制配对。"""

    rows = []
    for row in p10_rows():
        if (
            row["reference"]["terminal"] != row["intervention"]["terminal"]
            or row["score"]["delta"] != 0
        ):
            rows.append({
                "target_id": row["target_id"],
                "rollout_index": row["rollout_index"],
                "sample_key": row["sample_key"],
                "p10_score_delta": row["score"]["delta"],
                "p10_reference_terminal": row["reference"]["terminal"],
                "p10_intervention_terminal": row["intervention"]["terminal"],
            })
    return rows


def record_json(record: Any) -> dict[str, Any]:
    return {
        "round_no": record.round_no,
        "dealer_seat": record.dealer_seat,
        "winner_seat": record.winner_seat,
        "is_draw": record.is_draw,
        "fan": record.fan,
        "details": list(record.details),
        "score_delta": list(record.score_delta),
        "scores_before": list(record.scores_before),
        "scores_after": list(record.scores_after),
    }


def record_terminal(record: Any, focal: int) -> str:
    if record.is_draw or record.winner_seat is None:
        return "wall_draw_or_non_hu_end"
    return "focal_hu" if record.winner_seat == focal else "opponent_hu"


def execute(pair: Mapping[str, Any]) -> dict[str, Any]:
    target = next(row for row in p9.targets() if row["target_id"] == pair["target_id"])
    snapshot = json.loads(p9.snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(p9.CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(p9.core.rule_config_from_contract(contract))
    base_runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    capture = SettlementCaptureEngine(base_runtime["engine"])
    runtime = dict(base_runtime)
    runtime["engine"] = capture
    reference_policies, reference_force = p9._policies_for_arm(
        target=target, snapshot=snapshot, action_key=str(target["reference_action"]),
        label="p11-reference-{0}-{1:02d}".format(pair["target_id"], pair["rollout_index"]),
    )
    intervention_policies, intervention_force = p9._policies_for_arm(
        target=target, snapshot=snapshot, action_key=str(target["intervention_action"]),
        label="p11-intervention-{0}-{1:02d}".format(pair["target_id"], pair["rollout_index"]),
    )
    double = opportunities.run_double_arm(
        rules=rules, snapshot=snapshot,
        baseline_policies_by_seat=reference_policies,
        candidate_policies_by_seat=intervention_policies,
        config=opportunities._driver_config(), value_limits=p9.LIMITS, runtime=runtime,
        current_world_transform=lambda world: capture.resample_public_consistent_hidden_world(
            world, focal_seat=int(target["focal_physical_seat"]),
            sample_key=str(pair["sample_key"]),
        ),
    )
    cut_round = int(target["features"]["round_no"])
    cut_records = [record for record in capture.records if record.round_no == cut_round]
    if len(cut_records) != 2:
        raise RuntimeError("截取局必须按参考臂、干预臂各捕获一次，实际 {0}".format(len(cut_records)))
    reference, intervention = cut_records
    focal = int(target["focal_physical_seat"])
    reference_score = double["arms"]["baseline"].get("focal_stage_score")
    intervention_score = double["arms"]["candidate"].get("focal_stage_score")
    full_delta = int(intervention_score) - int(reference_score)
    direct_delta = int(intervention.score_delta[focal]) - int(reference.score_delta[focal])
    mechanical = bool(
        double.get("valid") and reference_force.force_count == 1
        and intervention_force.force_count == 1
        and full_delta == pair["p10_score_delta"]
        and record_terminal(reference, focal) == pair["p10_reference_terminal"]
        and record_terminal(intervention, focal) == pair["p10_intervention_terminal"]
    )
    return {
        "schema": "r18-p11-settlement-cascade/1",
        **dict(pair),
        "mechanical_ok": mechanical,
        "reference": record_json(reference),
        "intervention": record_json(intervention),
        "focal_current_round_settlement_delta": direct_delta,
        "focal_remaining_table_delta": full_delta,
        "downstream_round_cascade_delta": full_delta - direct_delta,
    }


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("P11 目录已存在；拒绝覆盖")
    pairs = selected_pairs()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rows")).mkdir()
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {"schema": "r18-p11-targets/1", "pairs": pairs})
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p11-manifest/1",
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(p9.__file__), Path(p10.__file__),
            Path(opportunities.__file__), p9.P5, p9.P7, p9.CONTRACT,
            p10.OUT / "manifest.json", p10.OUT / "result.json", _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "p10_result_sha256": digest(p10.OUT / "result.json"),
        "pairs": len(pairs), "planned_tables": len(pairs) * 2, "workers": 8,
        "selection": "P10中当前局终止类型改变或完整剩余桌分差非零的全部配对",
        "label_only": "RoundRecord仅作离线教师标签，不进入策略请求",
        "development_only": True, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "pairs": len(pairs)}, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    guard.verify(manifest["runtime"])
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["pairs"]
    return manifest, targets


def run() -> None:
    manifest, pairs = verify()
    failures = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
        futures = {pool.submit(execute, pair): pair for pair in pairs}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            pair = futures[future]
            try:
                row = future.result()
                if not row["mechanical_ok"]:
                    raise RuntimeError("P10/RoundRecord 对账失败")
                write_json(_project_file(_PROJECT_ROOT, OUT / "rows" / "{0}-{1:02d}.json".format(
                    pair["target_id"], pair["rollout_index"])), row)
            except Exception as exc:  # noqa: BLE001
                failures.append({"target_id": pair["target_id"],
                                 "rollout_index": pair["rollout_index"],
                                 "error": type(exc).__name__ + ": " + str(exc)})
            if completed % 32 == 0:
                print(json.dumps({"completed": completed, "planned": len(pairs)}, ensure_ascii=False), flush=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {"completed": len(pairs) - len(failures),
                                           "planned": len(pairs), "failures": failures})
    if failures:
        raise RuntimeError("P11 存在失败")


def analyze() -> None:
    manifest, pairs = verify()
    rows = [json.loads(path.read_text()) for path in sorted((_project_file(_PROJECT_ROOT, OUT / "rows")).glob("*.json"))]
    if len(rows) != len(pairs) or not all(row["mechanical_ok"] for row in rows):
        raise ValueError("P11 记录不完整")
    direct = [row["focal_current_round_settlement_delta"] for row in rows]
    cascade = [row["downstream_round_cascade_delta"] for row in rows]
    full = [row["focal_remaining_table_delta"] for row in rows]
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p11-result/1", "status": "COMPLETE_P11_SETTLEMENT_CASCADE",
        "mechanical_ok": True, "pairs": len(rows), "tables": len(rows) * 2,
        "sum_current_round_settlement_delta": sum(direct),
        "sum_downstream_round_cascade_delta": sum(cascade),
        "sum_remaining_table_delta": sum(full),
        "mean_current_round_settlement_delta": statistics.fmean(direct),
        "mean_downstream_round_cascade_delta": statistics.fmean(cascade),
        "mean_remaining_table_delta": statistics.fmean(full),
        "nonzero_current_round": sum(value != 0 for value in direct),
        "nonzero_downstream_cascade": sum(value != 0 for value in cascade),
        "development_only": True, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text()), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare": prepare()
    elif command == "run": run()
    else: analyze()


if __name__ == "__main__":
    main()
