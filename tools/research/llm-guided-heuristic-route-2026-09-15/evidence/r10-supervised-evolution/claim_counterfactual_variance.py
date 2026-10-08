"""CF2：扩大自然吃碰反事实样本，测量主/辅助标签分布与成本。"""

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
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-counterfactual-02-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-counterfactual-plan-20260921.json')
CF1_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-counterfactual-01-20260921/result.json')
PANEL_SEED = 2026092302
MIXES = ("H", "M")
TARGET_HITS_PER_MIX = 16
MAX_ROOTS_PER_MIX = 32
MAX_SAMPLES = 32
MAX_TABLES = MAX_SAMPLES * 2 * core.TABLES_PER_ARM


def digest(path: Path) -> str:
    """返回冻结文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths() -> list[Path]:
    """列出 CF2 执行身份输入。"""

    return [
        Path(__file__),
        Path(core.__file__),
        Path(core.opportunities.__file__),
        Path(core.specialist.__file__),
        PLAN,
        CF1_RESULT,
        core.CONTRACT,
        core.ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结 CF2 新来源、顺序取样和标签可用性判据。"""

    if OUT.exists():
        raise SystemExit("CF2 目录已存在；拒绝覆盖")
    cf1 = batch.read(CF1_RESULT)
    if cf1["status"] != "PASS_CF1_MECHANICS":
        raise ValueError("CF1 机械验收未通过")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-claim-counterfactual-cf2",
        authorization_id="r10-claim-counterfactual-cf2-20260921",
        accounts={"tables_full": MAX_TABLES, "prefix_generation": 64},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "CF1通过机械验收；CF2仅测量标签分布、动作族覆盖与成本，不训练、不选优",
        "scope": "全新panel_seed；H/M各按root_index升序最多检查32根并取前16个行为命中；每样本过牌/具体鸣牌两臂，各续打两桌",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-claim-counterfactual-cf2/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "cf1_result": str(CF1_RESULT),
        "cf1_result_sha256": digest(CF1_RESULT),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(core.CONTRACT),
        "contract_sha256": digest(core.CONTRACT),
        "route_source": str(core.ROUTE_SOURCE),
        "route_source_sha256": digest(core.ROUTE_SOURCE),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "max_roots_per_mix": MAX_ROOTS_PER_MIX,
        "target_hits_per_mix": TARGET_HITS_PER_MIX,
        "selection": "每层按root_index升序取前16个V2首选pass且路线父代首选合法chi/peng的窗口；不读取续打标签",
        "seat_schedule": "seat=(root_index-1)%4",
        "primary_label": "同快照具体鸣牌臂减过牌臂的完整剩余阶段group_advance_v1效用差",
        "auxiliary_label": "同终点焦点参与者阶段总积分差；仅作动作信用和训练辅助，不替代晋级目标或发布证据",
        "label_readiness": {
            "mechanics": "32个样本全部双臂完整、首动作匹配、force_count=1、执行审核全绿",
            "coverage": "H/M各16个有效样本；全批chi和peng均至少2个",
            "direct_primary_training": "主标签至少4个非零且同时有正负；否则不得直接拟合晋级标签",
            "auxiliary_training": "阶段积分差至少8个非零且同时有正负；满足时只允许作为辅助教师",
            "meaning": "标签丰富度与成本验收，不是候选效果判据",
        },
        "tables_per_arm": core.TABLES_PER_ARM,
        "max_samples": MAX_SAMPLES,
        "max_tables": MAX_TABLES,
        "training": False,
        "selection_effect_claim": False,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_CF2", "max_tables": MAX_TABLES}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对 CF2 冻结输入。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("cf1_result", "cf1_result_sha256"),
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def sign_counts(values: list[float]) -> dict[str, int]:
    """按正、零、负稳定汇总标签。"""

    return {
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
    }


def run() -> None:
    """执行 CF2 新来源并只读汇总标签丰富度。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("CF2 已执行；拒绝覆盖")
    contract = batch.read(core.CONTRACT)
    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    attempts: list[dict] = []
    hits: list[dict] = []
    original_seed = core.PANEL_SEED
    core.PANEL_SEED = PANEL_SEED
    try:
        for mix in MIXES:
            mix_hits = 0
            for root_index in range(1, MAX_ROOTS_PER_MIX + 1):
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
                    mix_hits += 1
                if mix_hits >= TARGET_HITS_PER_MIX:
                    break
    finally:
        core.PANEL_SEED = original_seed

    primary = [float(item["label"]["u_low_delta"]) for item in hits]
    auxiliary = [float(item["label"]["focal_stage_score_delta"]) for item in hits]
    families = Counter(
        str(item["witness"]["claim_action_key"]).split(":", 1)[0]
        for item in hits
    )
    valid_by_mix = {
        mix: sum(
            item["mix"] == mix and item["status"] == "HIT_VALID"
            for item in hits
        )
        for mix in MIXES
    }
    mechanics_ok = (
        len(hits) == MAX_SAMPLES
        and valid_by_mix == {"H": TARGET_HITS_PER_MIX, "M": TARGET_HITS_PER_MIX}
        and all(item["mechanical_ok"] for item in hits)
    )
    coverage_ok = families["chi"] >= 2 and families["peng"] >= 2
    primary_signs = sign_counts(primary)
    auxiliary_signs = sign_counts(auxiliary)
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
    if not mechanics_ok or not coverage_ok:
        disposition = "STOP_AND_FIX_CF2_MEASUREMENT"
    elif auxiliary_ready:
        disposition = "PROCEED_OBSERVABLE_AUXILIARY_GATE_WITH_PRIMARY_STAGE_VALIDATION"
    else:
        disposition = "REVIEW_LABEL_ENDPOINT_AND_LITERATURE_BEFORE_GATE_SEARCH"
    summary = {
        "attempts": len(attempts),
        "hits": len(hits),
        "valid_hits_by_mix": valid_by_mix,
        "action_families": dict(sorted(families.items())),
        "primary_u_low_delta_signs": primary_signs,
        "auxiliary_stage_score_delta_signs": auxiliary_signs,
        "auxiliary_mean": statistics.fmean(auxiliary) if auxiliary else None,
        "auxiliary_median": statistics.median(auxiliary) if auxiliary else None,
        "direct_primary_training_ready": primary_ready,
        "auxiliary_training_ready": auxiliary_ready,
        "mechanics_ok": mechanics_ok,
        "coverage_ok": coverage_ok,
        "full_or_partial_tables": sum(
            sum(int(value) for value in item["double_arm"]["tables_executed"].values())
            for item in hits
        ),
        "disposition": disposition,
        "strength_claim": False,
    }
    result = {
        "schema": "r10-claim-counterfactual-cf2-result/1",
        "status": "COMPLETE_CF2_MEASUREMENT",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "attempts": attempts,
        "hits": hits,
        "summary": summary,
        "interpretation": {
            "primary": "group_advance_v1是最终研究目标；稀疏时不得用少量标签直接训练或宣称提升",
            "auxiliary": "阶段积分差来自同快照、同对手、同终点的首动作干预，只作动作信用；不得替代完整阶段晋级评价",
            "next": "只有机械、覆盖与辅助丰富度通过，才冻结来源根级训练/验证切分并拟合玩家可见轻量门控器",
        },
    }
    batch.write(result_path, result)
    verify_inputs(manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
