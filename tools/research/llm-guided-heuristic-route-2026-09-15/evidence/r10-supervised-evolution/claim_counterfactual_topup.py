"""CF2-B：只用未运行来源根补齐 CF2 的 H/M 行为样本配额。"""

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
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_pilot as core  # noqa: E402
import claim_counterfactual_variance as cf2  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-counterfactual-02b-20260921')
CF2_RESULT = cf2.OUT / "result.json"
ROOT_START = 33
ROOT_END = 64
TARGET_TOTAL_PER_MIX = 16
MAX_NEW_SAMPLES = 7
MAX_TABLES = MAX_NEW_SAMPLES * 2 * core.TABLES_PER_ARM


def digest(path: Path) -> str:
    """返回冻结文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths() -> list[Path]:
    """列出补额执行身份输入。"""

    return [Path(__file__), Path(core.__file__), Path(cf2.__file__), CF2_RESULT]


def prepare() -> None:
    """冻结补额数量和未运行根范围；不按标签选择根。"""

    if OUT.exists():
        raise SystemExit("CF2-B 目录已存在；拒绝覆盖")
    prior = batch.read(CF2_RESULT)
    if prior["status"] != "COMPLETE_CF2_MEASUREMENT":
        raise ValueError("CF2 未完成")
    prior_counts = dict(prior["summary"]["valid_hits_by_mix"])
    needed = {mix: TARGET_TOTAL_PER_MIX - int(prior_counts[mix]) for mix in cf2.MIXES}
    if needed != {"H": 5, "M": 2}:
        raise ValueError("CF2 缺额与冻结预期不符：" + repr(needed))
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-claim-counterfactual-cf2b",
        authorization_id="r10-claim-counterfactual-cf2b-20260921",
        accounts={"tables_full": MAX_TABLES, "prefix_generation": 64},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "CF2的25个命中全部机械有效且标签丰富度通过，但预登记32根/层不足以填满H/M各16；只补未运行根的行为配额",
        "scope": "沿用CF2 panel_seed；H/M分别从root33升序检查到64，只补H=5、M=2；根选择不读取标签；最多7个样本、28条桌记录",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-claim-counterfactual-cf2b/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "cf2_result": str(CF2_RESULT),
        "cf2_result_sha256": digest(CF2_RESULT),
        "panel_seed": cf2.PANEL_SEED,
        "root_range": [ROOT_START, ROOT_END],
        "prior_valid_by_mix": prior_counts,
        "needed_by_mix": needed,
        "selection": "每层从root33升序取行为命中，达到该层缺额即停；不读取主/辅助标签",
        "max_new_samples": MAX_NEW_SAMPLES,
        "max_tables": MAX_TABLES,
        "training": False,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_CF2B", "needed": needed}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对补额冻结输入。"""

    guard.verify(manifest["runtime"])
    if digest(Path(manifest["cf2_result"])) != manifest["cf2_result_sha256"]:
        raise ValueError("CF2 result 摘要漂移")


def signs(values: list[float]) -> dict[str, int]:
    """按正、零、负汇总。"""

    return {
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
    }


def run() -> None:
    """执行补额并生成 CF2 合并裁定。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("CF2-B 已执行；拒绝覆盖")
    prior = batch.read(CF2_RESULT)
    contract = batch.read(core.CONTRACT)
    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    attempts: list[dict] = []
    hits: list[dict] = []
    original_seed = core.PANEL_SEED
    core.PANEL_SEED = cf2.PANEL_SEED
    try:
        for mix in cf2.MIXES:
            needed = int(manifest["needed_by_mix"][mix])
            got = 0
            for root_index in range(ROOT_START, ROOT_END + 1):
                sample = core.one_sample(
                    manifest=manifest,
                    contract=contract,
                    mix=mix,
                    root_index=root_index,
                    rules=rules,
                    value_limits=value_limits,
                )
                attempts.append({
                    key: value
                    for key, value in sample.items()
                    if key not in {"snapshot", "double_arm", "witness"}
                })
                if sample["status"].startswith("HIT"):
                    hits.append(sample)
                    got += 1
                if got >= needed:
                    break
    finally:
        core.PANEL_SEED = original_seed

    combined_hits = list(prior["hits"]) + hits
    valid_by_mix = {
        mix: sum(
            item["mix"] == mix and item["status"] == "HIT_VALID"
            for item in combined_hits
        )
        for mix in cf2.MIXES
    }
    primary = [float(item["label"]["u_low_delta"]) for item in combined_hits]
    auxiliary = [float(item["label"]["focal_stage_score_delta"]) for item in combined_hits]
    families = Counter(
        str(item["witness"]["claim_action_key"]).split(":", 1)[0]
        for item in combined_hits
    )
    mechanics_ok = (
        valid_by_mix == {"H": TARGET_TOTAL_PER_MIX, "M": TARGET_TOTAL_PER_MIX}
        and len(combined_hits) == 32
        and all(item["mechanical_ok"] for item in combined_hits)
    )
    primary_signs = signs(primary)
    auxiliary_signs = signs(auxiliary)
    primary_ready = (
        primary_signs["positive"] > 0
        and primary_signs["negative"] > 0
        and primary_signs["positive"] + primary_signs["negative"] >= 4
    )
    auxiliary_ready = (
        auxiliary_signs["positive"] > 0
        and auxiliary_signs["negative"] > 0
        and auxiliary_signs["positive"] + auxiliary_signs["negative"] >= 8
    )
    disposition = (
        "PROCEED_OBSERVABLE_AUXILIARY_GATE_WITH_PRIMARY_STAGE_VALIDATION"
        if mechanics_ok and families["chi"] >= 2 and families["peng"] >= 2
        and auxiliary_ready
        else "REVIEW_MEASUREMENT_AND_LITERATURE_BEFORE_GATE_SEARCH"
    )
    combined_summary = {
        "samples": len(combined_hits),
        "valid_hits_by_mix": valid_by_mix,
        "action_families": dict(sorted(families.items())),
        "primary_u_low_delta_signs": primary_signs,
        "auxiliary_stage_score_delta_signs": auxiliary_signs,
        "auxiliary_mean": statistics.fmean(auxiliary),
        "auxiliary_median": statistics.median(auxiliary),
        "direct_primary_training_ready": primary_ready,
        "auxiliary_training_ready": auxiliary_ready,
        "mechanics_ok": mechanics_ok,
        "disposition": disposition,
        "strength_claim": False,
    }
    result = {
        "schema": "r10-claim-counterfactual-cf2b-result/1",
        "status": "COMPLETE_CF2B_TOPUP",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "attempts": attempts,
        "hits": hits,
        "combined_summary": combined_summary,
        "combined_sources": [str(CF2_RESULT), str(result_path)],
        "literature_review": {
            "Suphx": "全局奖励过粗会损害信用分配；动作类型分解与前瞻事实可借，但杭麻对手行为和财神语义必须保留",
            "Mxplainer_Tjong": "目标/动作分解与可校准小模型可借；动作预测或代理分不能替代完整赛事指标",
            "EoH_ReEvo": "评估成本远高于论文小实例，必须硬预算和逐样本记账；未运行来源根补额不构成按结果挑样本",
        },
    }
    batch.write(result_path, result)
    verify_inputs(manifest)
    print(json.dumps(combined_summary | {"new_attempts": len(attempts), "new_hits": len(hits)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
