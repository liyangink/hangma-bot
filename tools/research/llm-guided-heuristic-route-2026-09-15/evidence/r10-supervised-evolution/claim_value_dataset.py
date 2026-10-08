"""AV1-1：采集完整玩家可见状态的自然吃碰动作价值训练池。"""

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
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_nullable as nullable  # noqa: E402
import claim_counterfactual_pilot as core  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.offline.claim_value_features import (  # noqa: E402
    SCHEMA as FEATURE_SCHEMA,
    encode_claim_value_features,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-dataset-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R10-CLAIM-COUNTERFACTUAL-CLOSE-AND-VALUE-PIVOT-2026-09-21.md')
PANEL_SEEDS = (2026092310, 2026092311)
MIXES = ("H", "M")
TARGET_HITS_PER_SHARD = 32
MAX_ROOTS_PER_SHARD = 128
TABLES_PER_SAMPLE = 2 * core.TABLES_PER_ARM
MAX_SAMPLES = len(PANEL_SEEDS) * len(MIXES) * TARGET_HITS_PER_SHARD
MAX_TABLES = MAX_SAMPLES * TABLES_PER_SAMPLE
MAX_PREFIX_ROOTS = len(PANEL_SEEDS) * len(MIXES) * MAX_ROOTS_PER_SHARD


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


class AV1RouteChangeCapture(core.RouteChangeCapture):
    """沿用冻结自然机会定义，并替换为 AV1 完整公开状态编码。"""

    def __call__(self, request: Any) -> dict | None:
        witness = super().__call__(request)
        if witness is None:
            return None
        witness["observable_features"] = encode_claim_value_features(
            request, str(witness["claim_action_key"])
        )
        return witness


def one_av1_sample(**kwargs: Any) -> dict:
    """在单进程内临时安装 AV1 截取器并复用已验收双臂执行链。"""

    previous = core.RouteChangeCapture
    core.RouteChangeCapture = AV1RouteChangeCapture
    try:
        return nullable.one_sample_nullable(**kwargs)
    finally:
        core.RouteChangeCapture = previous


def source_paths() -> list[Path]:
    """列出本批执行身份输入。"""

    import hangma_bot.offline.claim_value_features as features
    import hangma_bot.offline.forced_action as forced_action

    return [
        Path(__file__),
        Path(core.__file__),
        Path(nullable.__file__),
        Path(core.opportunities.__file__),
        Path(core.specialist.__file__),
        Path(features.__file__),
        Path(forced_action.__file__),
        PLAN,
        core.CONTRACT,
        core.ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结来源、顺序取样、信息边界、配额和停止条件。"""

    if OUT.exists():
        raise SystemExit("AV1-1 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "shards")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / ".gitignore")).write_text("/shards/\n", encoding="utf-8")
    authorization = batch.unified_document(
        batch_label="r10-av1-action-value-dataset",
        authorization_id="r10-av1-action-value-dataset-20260921",
        accounts={"tables_full": MAX_TABLES, "prefix_generation": MAX_PREFIX_ROOTS},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "固定奖励与单特征门控均在全新来源失败；按文献复盘转入完整玩家可见状态的动作价值建模",
        "scope": "两个全新panel_seed；每个seed×H/M按root_index升序最多128根，取前32个机械有效自然机会；不按标签补样",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-av1-action-value-dataset/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(core.CONTRACT),
        "contract_sha256": digest(core.CONTRACT),
        "route_source": str(core.ROUTE_SOURCE),
        "route_source_sha256": digest(core.ROUTE_SOURCE),
        "feature_schema": FEATURE_SCHEMA,
        "panel_seeds": list(PANEL_SEEDS),
        "mixes": list(MIXES),
        "target_hits_per_shard": TARGET_HITS_PER_SHARD,
        "max_roots_per_shard": MAX_ROOTS_PER_SHARD,
        "selection": "每个seed×mix按root_index升序取前32个V2首选pass且冻结路线父代首选合法chi/peng并通过双臂机械验收的机会；不读取标签",
        "seat_schedule": "seat=(root_index-1)%4",
        "student_information": "仅DecisionRequest中的PlayerObservation、CompetitionContext和HangmaRules事实；相对座位编码；无场次、来源根、对手实现、绝对身份、未来信息或终局派生特征",
        "primary_label": "具体鸣牌臂减过牌臂的完整剩余阶段group_advance_v1识别区间",
        "auxiliary_label": "同终点焦点参与者阶段总积分差；只作稳健回归/排序教师，不替代完整阶段指标",
        "max_samples": MAX_SAMPLES,
        "max_tables": MAX_TABLES,
        "max_prefix_roots": MAX_PREFIX_ROOTS,
        "parallel_shards": len(PANEL_SEEDS) * len(MIXES),
        "training": False,
        "selection_effect_claim": False,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_AV1_1",
        "target_samples": MAX_SAMPLES,
        "max_tables": MAX_TABLES,
        "max_prefix_roots": MAX_PREFIX_ROOTS,
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对代码、规则合同、路线来源和计划均未漂移。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def _root_path(panel_seed: int, mix: str, root_index: int) -> Path:
    """为每个来源根返回独立原子检查点路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "shards" / f"s{panel_seed}-{mix}-root{root_index:03d}.json")


def _existing_shard(panel_seed: int, mix: str) -> list[dict]:
    """按根序读取已完成的原子检查点。"""

    rows = []
    for root_index in range(1, MAX_ROOTS_PER_SHARD + 1):
        path = _root_path(panel_seed, mix, root_index)
        if not path.exists():
            break
        rows.append(batch.read(path))
    return rows


def _worker(panel_seed: int, mix: str, manifest: dict, contract: dict) -> dict:
    """顺序完成一个 seed×mix 分片；四个分片之间才允许并行。"""

    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    existing = _existing_shard(panel_seed, mix)
    valid_hits = sum(item.get("status") == "HIT_VALID" for item in existing)
    next_root = len(existing) + 1
    previous_seed = core.PANEL_SEED
    core.PANEL_SEED = panel_seed
    try:
        for root_index in range(next_root, MAX_ROOTS_PER_SHARD + 1):
            if valid_hits >= TARGET_HITS_PER_SHARD:
                break
            sample = one_av1_sample(
                manifest=manifest,
                contract=contract,
                mix=mix,
                root_index=root_index,
                rules=rules,
                value_limits=value_limits,
            )
            batch.write(_root_path(panel_seed, mix, root_index), sample)
            if sample.get("status") == "HIT_VALID":
                valid_hits += 1
    finally:
        core.PANEL_SEED = previous_seed
    rows = _existing_shard(panel_seed, mix)
    return {
        "panel_seed": panel_seed,
        "mix": mix,
        "attempts": len(rows),
        "valid_hits": sum(item.get("status") == "HIT_VALID" for item in rows),
        "invalid_hits": sum(item.get("status") == "HIT_INVALID" for item in rows),
        "complete": sum(item.get("status") == "HIT_VALID" for item in rows)
        >= TARGET_HITS_PER_SHARD,
    }


def _compact_row(sample: dict, panel_seed: int) -> dict:
    """分离玩家可见输入与离线标签，生成建模数据行。"""

    witness = sample["witness"]
    features = witness["observable_features"]
    if features.get("schema") != FEATURE_SCHEMA:
        raise ValueError("样本特征不是冻结 AV1 schema")
    return {
        "row_id": f"s{panel_seed}:{sample['mix']}:{sample['source_root_id']}",
        "group": {
            "panel_seed": panel_seed,
            "mix": sample["mix"],
            "source_root_id": sample["source_root_id"],
            "root_index": sample["root_index"],
        },
        "claim_action_key": witness["claim_action_key"],
        "features": features,
        "labels": {
            "u_delta": sample["label"].get("u_delta"),
            "u_low_delta": sample["label"]["u_low_delta"],
            "u_high_delta": sample["label"]["u_high_delta"],
            "focal_stage_score_delta": sample["label"]["focal_stage_score_delta"],
        },
    }


def _signs(values: list[float]) -> dict[str, int]:
    """稳定汇总正、零、负标签数。"""

    return {
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
    }


def run() -> None:
    """并行采集四个独立分片，并在完成后生成紧凑训练池。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("AV1-1 已形成结果；拒绝覆盖")
    contract = batch.read(core.CONTRACT)
    shards = [(seed, mix) for seed in PANEL_SEEDS for mix in MIXES]
    summaries: list[dict] = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=len(shards)) as executor:
            futures = {
                executor.submit(_worker, seed, mix, manifest, contract): (seed, mix)
                for seed, mix in shards
            }
            for future in concurrent.futures.as_completed(futures):
                summaries.append(future.result())
    except Exception as exc:
        batch.write(_project_file(_PROJECT_ROOT, OUT / "failure.json"), {
            "schema": "r10-av1-action-value-dataset-failure/1",
            "status": "INTERRUPTED_RESUMABLE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "completed_shards": sorted(
                summaries, key=lambda item: (item["panel_seed"], item["mix"])
            ),
        })
        raise

    summaries.sort(key=lambda item: (item["panel_seed"], item["mix"]))
    all_samples: list[tuple[int, dict]] = []
    raw_index: list[dict] = []
    for seed, mix in shards:
        for root_index, sample in enumerate(_existing_shard(seed, mix), start=1):
            path = _root_path(seed, mix, root_index)
            raw_index.append({
                "panel_seed": seed,
                "mix": mix,
                "root_index": root_index,
                "path": str(path.relative_to(OUT)),
                "sha256": digest(path),
                "status": sample.get("status"),
            })
            if sample.get("status") == "HIT_VALID":
                all_samples.append((seed, sample))
    rows = [_compact_row(sample, seed) for seed, sample in all_samples]
    batch.write(_project_file(_PROJECT_ROOT, OUT / "raw-index.json"), {
        "schema": "r10-av1-action-value-raw-index/1",
        "records": raw_index,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r10-av1-action-value-dataset-rows/1",
        "feature_schema": FEATURE_SCHEMA,
        "rows": rows,
    })
    actions = Counter(row["claim_action_key"].split(":", 1)[0] for row in rows)
    primary = [float(row["labels"]["u_low_delta"]) for row in rows]
    auxiliary = [float(row["labels"]["focal_stage_score_delta"]) for row in rows]
    mechanics_ok = (
        len(rows) == MAX_SAMPLES
        and all(item["complete"] and item["invalid_hits"] == 0 for item in summaries)
    )
    coverage_ok = actions["chi"] >= 16 and actions["peng"] >= 16
    status = (
        "PASS_AV1_1_DATASET_FOR_GROUPED_MODELING"
        if mechanics_ok and coverage_ok
        else "STOP_AV1_1_AND_REVIEW_SAMPLING"
    )
    result = {
        "schema": "r10-av1-action-value-dataset-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "raw_index_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "raw-index.json")),
        "summary": {
            "shards": summaries,
            "rows": len(rows),
            "action_families": dict(sorted(actions.items())),
            "primary_u_low_delta_signs": _signs(primary),
            "auxiliary_stage_score_delta_signs": _signs(auxiliary),
            "auxiliary_mean": statistics.fmean(auxiliary) if auxiliary else None,
            "auxiliary_median": statistics.median(auxiliary) if auxiliary else None,
            "mechanics_ok": mechanics_ok,
            "coverage_ok": coverage_ok,
            "full_or_partial_tables": len(rows) * TABLES_PER_SAMPLE,
            "strength_claim": False,
        },
        "next": (
            "按SourceRoot和panel_seed分组交叉验证低容量动作条件价值模型；训练池不得兼作冻结动作验证"
            if status.startswith("PASS")
            else "先复盘自然机会命中、机械缺陷或动作族覆盖；不得降低配额或按标签补样"
        ),
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps({"status": status, **result["summary"]}, ensure_ascii=False, indent=2))


def status() -> None:
    """只读显示四个可恢复分片的当前进度。"""

    if not (_project_file(_PROJECT_ROOT, OUT / "manifest.json")).exists():
        raise SystemExit("AV1-1 尚未 prepare")
    rows = []
    for seed in PANEL_SEEDS:
        for mix in MIXES:
            values = _existing_shard(seed, mix)
            rows.append({
                "panel_seed": seed,
                "mix": mix,
                "attempts": len(values),
                "valid_hits": sum(item.get("status") == "HIT_VALID" for item in values),
                "invalid_hits": sum(item.get("status") == "HIT_INVALID" for item in values),
            })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "status"))
    args = parser.parse_args()
    globals()[args.operation]()
