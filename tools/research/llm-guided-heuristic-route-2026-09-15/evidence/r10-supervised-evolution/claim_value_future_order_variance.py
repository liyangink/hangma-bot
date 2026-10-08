"""AV1-TV1：同公开快照多未来可摸顺序的吃碰反事实方差审计。"""

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
import statistics
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_pilot as core  # noqa: E402
import claim_value_dataset as dataset  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import WindowKey, WindowPhase  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-future-order-01-20260921')
DATA_DIR = dataset.OUT
DATA_RESULT = DATA_DIR / "result.json"
MODEL_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-model-01-20260921/result.json')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R10-CLAIM-COUNTERFACTUAL-CLOSE-AND-VALUE-PIVOT-2026-09-21.md')
ROLLOUTS_PER_SNAPSHOT = 8
SNAPSHOTS_PER_SHARD = 4
SHARDS = tuple((seed, mix) for seed in dataset.PANEL_SEEDS for mix in dataset.MIXES)
SAMPLE_COUNT = len(SHARDS) * SNAPSHOTS_PER_SHARD
MAX_TABLES = SAMPLE_COUNT * ROLLOUTS_PER_SNAPSHOT * 2 * core.TABLES_PER_ARM


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_sources() -> list[dict]:
    """每分片按原 root_index 顺序取前四个有效机会，不读取标签。"""

    selected = []
    for seed, mix in SHARDS:
        hits = []
        for path in sorted((DATA_DIR / "shards").glob(f"s{seed}-{mix}-root*.json")):
            sample = batch.read(path)
            if sample.get("status") == "HIT_VALID":
                hits.append({
                    "panel_seed": seed,
                    "mix": mix,
                    "root_index": int(sample["root_index"]),
                    "path": str(path),
                    "sha256": digest(path),
                })
            if len(hits) >= SNAPSHOTS_PER_SHARD:
                break
        if len(hits) != SNAPSHOTS_PER_SHARD:
            raise ValueError(f"{seed}/{mix} 有效来源不足 {SNAPSHOTS_PER_SHARD}")
        selected.extend(hits)
    return selected


def source_paths() -> list[Path]:
    """列出方差审计代码与冻结输入。"""

    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__),
        Path(core.__file__),
        Path(opportunities.__file__),
        Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__),
        DATA_RESULT,
        MODEL_RESULT,
        PLAN,
        core.CONTRACT,
        core.ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结 16 个快照、8 个未来顺序、方差判读与预算。"""

    if OUT.exists():
        raise SystemExit("AV1-TV1 目录已存在；拒绝覆盖")
    data_result = batch.read(DATA_RESULT)
    model_result = batch.read(MODEL_RESULT)
    if data_result["status"] != "PASS_AV1_1_DATASET_FOR_GROUPED_MODELING":
        raise ValueError("AV1-1 数据集未通过")
    if model_result["status"] != "CLOSE_AV1_2_AND_REVIEW_VALUE_TEACHER":
        raise ValueError("只有 AV1-2 关闭后才允许方差审计")
    sources = selected_sources()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "raw")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / ".gitignore")).write_text("/raw/\n", encoding="utf-8")
    authorization = batch.unified_document(
        batch_label="r10-av1-future-order-variance",
        authorization_id="r10-av1-future-order-variance-20260921",
        accounts={"tables_full": MAX_TABLES, "source_snapshots": SAMPLE_COUNT},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "AV1-2的8个低容量模型均无法使M层非负；按Suphx奖励预测与rollout信息集边界先分解未来顺序方差",
        "scope": "AV1-1每个panel_seed×H/M分片按root_index取前4个有效快照；每快照8个预编号未来可摸区重排；过牌/具体鸣牌同一重排配对",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-av1-future-order-variance/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "data_result": str(DATA_RESULT),
        "data_result_sha256": digest(DATA_RESULT),
        "model_result": str(MODEL_RESULT),
        "model_result_sha256": digest(MODEL_RESULT),
        "sources": sources,
        "rollouts_per_snapshot": ROLLOUTS_PER_SNAPSHOT,
        "sample_keys": [f"future-order-{index:02d}" for index in range(1, ROLLOUTS_PER_SNAPSHOT + 1)],
        "resampling_scope": "只重排当前局wall[wall_front:wall_back]；保持已消费前缀、四家当前暗手、公开状态、牌张多重集、保留区与后续桌种子不变",
        "interpretation": "估计给定当前真实隐藏分配时的未来可摸顺序条件方差；不是隐藏手牌后验、不是精确Q、不是候选效果验证",
        "readout": {
            "substantial_order_noise": "至少25%快照的8次标签同时出现正负非零符号，或快照内辅助标签标准差中位数>=8分",
            "averaged_route_robust": "H/M两层的快照均值再平均均>=0，且主晋级下界均值均>=0",
            "next_if_noise_and_robust": "建立多未来顺序平均教师并重新采集独立训练池",
            "next_if_noise_but_not_robust": "未来顺序平均不足以消除M负效应；评估一致隐藏世界采样可行性，不生成门控候选",
            "next_if_low_noise": "单轨迹噪声不是主因；关闭当前路线动作教师，转回对手稳健的其他动作族/机制",
        },
        "max_tables": MAX_TABLES,
        "llm_calls": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_AV1_TV1", "snapshots": SAMPLE_COUNT, "max_tables": MAX_TABLES}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对代码、来源快照与上游结果未漂移。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("data_result", "data_result_sha256"),
        ("model_result", "model_result_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    for source in manifest["sources"]:
        if digest(Path(source["path"])) != source["sha256"]:
            raise ValueError("来源快照摘要漂移：" + source["path"])


def _window(snapshot: dict) -> WindowKey:
    """从冻结快照恢复精确强制动作窗口键。"""

    cut = snapshot["cut_window"]
    return WindowKey(
        game_id=str(snapshot["match_spec"]["match_id"]),
        round_no=int(cut["round_no"]),
        trigger_seq=int(cut["trigger_seq"]),
        phase=WindowPhase(str(cut["phase"])),
        seat=int(cut["seat"]),
    )


def _run_source(source: dict, manifest: dict, contract: dict) -> dict:
    """顺序完成一个公开快照的八个确定性未来顺序。"""

    sample = batch.read(Path(source["path"]))
    snapshot = sample["snapshot"]
    witness = sample["witness"]
    focal_seat = int(sample["focal_seat"])
    opponent_names = opportunities.opponent_policy_names(contract, str(source["mix"]))
    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    rows = []
    for index, key in enumerate(manifest["sample_keys"], start=1):
        checkpoint = _project_file(_PROJECT_ROOT, OUT / "raw" / (
            f"s{source['panel_seed']}-{source['mix']}-root{source['root_index']:03d}-r{index:02d}.json"
        ))
        if checkpoint.exists():
            rows.append(batch.read(checkpoint))
            continue
        baseline_policies, pass_policy = core.policies_for_arm(
            opponent_names=opponent_names,
            focal_seat=focal_seat,
            forced_action_key=str(witness["baseline_action_key"]),
            target_window=_window(snapshot),
            arm_name=f"pass-r{index:02d}",
        )
        candidate_policies, claim_policy = core.policies_for_arm(
            opponent_names=opponent_names,
            focal_seat=focal_seat,
            forced_action_key=str(witness["claim_action_key"]),
            target_window=_window(snapshot),
            arm_name=f"claim-r{index:02d}",
        )
        double_arm = opportunities.run_double_arm(
            rules=rules,
            snapshot=snapshot,
            baseline_policies_by_seat=baseline_policies,
            candidate_policies_by_seat=candidate_policies,
            config=opportunities._driver_config(),
            value_limits=value_limits,
            runtime=runtime,
            current_world_transform=lambda world, sample_key=key: runtime["engine"].resample_future_drawable_wall(
                world, sample_key=sample_key
            ),
        )
        actual = {
            arm: (((double_arm.get("window_actions") or {}).get("arms") or {}).get(arm) or {}).get("action_key")
            for arm in ("baseline", "candidate")
        }
        baseline = double_arm["arms"]["baseline"]
        candidate = double_arm["arms"]["candidate"]
        mechanical_ok = bool(
            double_arm.get("valid")
            and pass_policy.force_count == 1
            and claim_policy.force_count == 1
            and actual["baseline"] == witness["baseline_action_key"]
            and actual["candidate"] == witness["claim_action_key"]
        )
        row = {
            "schema": "r10-av1-future-order-rollout/1",
            "panel_seed": source["panel_seed"],
            "mix": source["mix"],
            "root_index": source["root_index"],
            "source_root_id": sample["source_root_id"],
            "sample_key": key,
            "actual_cut_actions": actual,
            "force_count": {"baseline": pass_policy.force_count, "candidate": claim_policy.force_count},
            "label": {
                "u_low_delta": float(candidate["u_low"]) - float(baseline["u_low"]),
                "u_high_delta": float(candidate["u_high"]) - float(baseline["u_high"]),
                "focal_stage_score_delta": int(candidate["focal_stage_score"]) - int(baseline["focal_stage_score"]),
            },
            "mechanical_ok": mechanical_ok,
            "tables_executed": double_arm["tables_executed"],
        }
        batch.write(checkpoint, row)
        rows.append(row)
    return {"source": source, "rollouts": rows}


def _worker(seed: int, mix: str, manifest: dict, contract: dict) -> list[dict]:
    """处理同一 seed×mix 下的四个快照。"""

    return [
        _run_source(source, manifest, contract)
        for source in manifest["sources"]
        if source["panel_seed"] == seed and source["mix"] == mix
    ]


def run() -> None:
    """执行四个分片并判读未来顺序方差是否足以改变路线。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("AV1-TV1 已执行；拒绝覆盖")
    contract = batch.read(core.CONTRACT)
    groups = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=len(SHARDS)) as executor:
        futures = [
            executor.submit(_worker, seed, mix, manifest, contract)
            for seed, mix in SHARDS
        ]
        for future in concurrent.futures.as_completed(futures):
            groups.extend(future.result())
    groups.sort(key=lambda item: (
        item["source"]["panel_seed"], item["source"]["mix"], item["source"]["root_index"]
    ))
    snapshot_rows = []
    all_mechanical = True
    for item in groups:
        auxiliary = [float(row["label"]["focal_stage_score_delta"]) for row in item["rollouts"]]
        primary_low = [float(row["label"]["u_low_delta"]) for row in item["rollouts"]]
        positive = any(value > 0 for value in auxiliary)
        negative = any(value < 0 for value in auxiliary)
        all_mechanical = all_mechanical and all(row["mechanical_ok"] for row in item["rollouts"])
        snapshot_rows.append({
            **item["source"],
            "rollouts": len(item["rollouts"]),
            "auxiliary_values": auxiliary,
            "auxiliary_mean": statistics.fmean(auxiliary),
            "auxiliary_stdev": statistics.stdev(auxiliary) if len(auxiliary) > 1 else 0.0,
            "primary_low_values": primary_low,
            "primary_low_mean": statistics.fmean(primary_low),
            "both_nonzero_signs": positive and negative,
            "mechanics_ok": all(row["mechanical_ok"] for row in item["rollouts"]),
        })
    median_stdev = statistics.median(row["auxiliary_stdev"] for row in snapshot_rows)
    sign_disagreement = sum(row["both_nonzero_signs"] for row in snapshot_rows)
    by_mix = {}
    for mix in dataset.MIXES:
        selected = [row for row in snapshot_rows if row["mix"] == mix]
        by_mix[mix] = {
            "snapshots": len(selected),
            "auxiliary_mean_of_snapshot_means": statistics.fmean(row["auxiliary_mean"] for row in selected),
            "primary_low_mean_of_snapshot_means": statistics.fmean(row["primary_low_mean"] for row in selected),
            "both_nonzero_signs": sum(row["both_nonzero_signs"] for row in selected),
        }
    substantial_noise = bool(
        sign_disagreement >= SAMPLE_COUNT * 0.25 or median_stdev >= 8.0
    )
    averaged_robust = bool(
        all(by_mix[mix]["auxiliary_mean_of_snapshot_means"] >= 0 for mix in dataset.MIXES)
        and all(by_mix[mix]["primary_low_mean_of_snapshot_means"] >= 0 for mix in dataset.MIXES)
    )
    if not all_mechanical:
        status = "STOP_AV1_TV1_MECHANICAL_FAILURE"
        next_step = "修复未来顺序执行接缝；当前方差读数不得使用"
    elif substantial_noise and averaged_robust:
        status = "PASS_AV1_TV1_FOR_AVERAGED_TEACHER"
        next_step = "另用全新来源建立多未来顺序平均教师；当前16个快照只作方差开发证据"
    elif substantial_noise:
        status = "REVIEW_CONSISTENT_HIDDEN_WORLD_TEACHER"
        next_step = "未来顺序噪声显著但平均后仍有对手层负效应；先审查历史一致隐藏世界采样可行性，不生成门控候选"
    else:
        status = "CLOSE_ROUTE_ACTION_TEACHER_LOW_ORDER_NOISE"
        next_step = "单轨迹未来顺序不是主因；关闭当前路线吃碰教师，转向对手稳健的其他动作族/机制"
    result = {
        "schema": "r10-av1-future-order-variance-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "snapshots": snapshot_rows,
        "summary": {
            "snapshot_count": len(snapshot_rows),
            "rollouts": sum(row["rollouts"] for row in snapshot_rows),
            "full_or_partial_tables": MAX_TABLES,
            "mechanics_ok": all_mechanical,
            "both_nonzero_sign_snapshots": sign_disagreement,
            "median_within_snapshot_auxiliary_stdev": median_stdev,
            "substantial_future_order_noise": substantial_noise,
            "averaged_route_robust": averaged_robust,
            "by_mix": by_mix,
            "strength_claim": False,
        },
        "next": next_step,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps({"status": status, **result["summary"], "next": next_step}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
