"""CF3-C：冻结单桩门控器的全新来源动作级验证。"""

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
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_pilot as core  # noqa: E402
import claim_gate_stump_calibration as stump  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-new-source-01-20260921')
STUMP_RESULT = stump.OUT / "result.json"
PANEL_SEED = 2026092303
MIXES = ("H", "M")
TARGET_HITS_PER_MIX = 8
MAX_ROOTS_PER_MIX = 32
MAX_SAMPLES = 16
MAX_TABLES = MAX_SAMPLES * 2 * core.TABLES_PER_ARM


def digest(path: Path) -> str:
    """返回冻结文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> None:
    """冻结门控器、全新来源、顺序取样和验证门槛。"""

    if OUT.exists():
        raise SystemExit("CF3-C 目录已存在；拒绝覆盖")
    result = batch.read(STUMP_RESULT)
    if result["status"] != "PASS_CF3B_STUMP_FOR_NEW_SOURCE_VALIDATION":
        raise ValueError("CF3-B 未授权新来源验证")
    model = result["selected"]["final_model"]
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-claim-gate-new-source-cf3c",
        authorization_id="r10-claim-gate-new-source-cf3c-20260921",
        accounts={"tables_full": MAX_TABLES, "prefix_generation": 64},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "CF3-B仅有route_raw单桩通过32开发根留一条件；必须在全新panel_seed验证",
        "scope": "H/M各按root_index升序最多检查32根并取前8个行为命中；每个机会过牌/具体鸣牌双臂续打两桌；门控器冻结不调参",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=[
        Path(__file__), Path(core.__file__), Path(stump.__file__), STUMP_RESULT,
        core.CONTRACT, core.ROUTE_SOURCE, _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
    ])
    manifest = {
        "schema": "r10-claim-gate-new-source-cf3c/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "stump_result": str(STUMP_RESULT),
        "stump_result_sha256": digest(STUMP_RESULT),
        "model": model,
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "target_hits_per_mix": TARGET_HITS_PER_MIX,
        "max_roots_per_mix": MAX_ROOTS_PER_MIX,
        "selection": "每层按root_index升序取前8个V2首选pass且路线父代首选合法chi/peng的机会；不读取标签",
        "validation_gate": {
            "mechanics": "H/M各8个有效命中；两臂完整且首动作匹配",
            "label_coverage": "辅助正类和非正类均至少1个",
            "behavior": "冻结门控器claim_count在2..14",
            "effect": "门控辅助积分均值>0且>=always-claim；门控主晋级差均值>=0",
            "meaning": "通过只允许实现离线候选并进入全新完整阶段开发；不是强度或发布证据",
        },
        "max_samples": MAX_SAMPLES,
        "max_tables": MAX_TABLES,
        "llm_calls": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_CF3C", "model": model}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对门控器与全新来源冻结输入。"""

    guard.verify(manifest["runtime"])
    if digest(Path(manifest["stump_result"])) != manifest["stump_result_sha256"]:
        raise ValueError("CF3-B 结果摘要漂移")
    if batch.read(Path(manifest["stump_result"]))["selected"]["final_model"] != manifest["model"]:
        raise ValueError("冻结门控器漂移")


def run() -> None:
    """采集全新反事实标签并一次性验收冻结门控器。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("CF3-C 已执行；拒绝覆盖")
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

    rows = [stump.extract_row(hit) for hit in hits]
    decisions = [stump.decide(manifest["model"], row) for row in rows]
    validation = stump.metrics(rows, decisions) if rows else None
    valid_by_mix = {
        mix: sum(
            hit["mix"] == mix and hit["status"] == "HIT_VALID"
            for hit in hits
        )
        for mix in MIXES
    }
    mechanics_ok = (
        len(hits) == MAX_SAMPLES
        and valid_by_mix == {"H": TARGET_HITS_PER_MIX, "M": TARGET_HITS_PER_MIX}
        and all(hit["mechanical_ok"] for hit in hits)
    )
    positive_rows = sum(row["labels"]["auxiliary_positive"] for row in rows)
    label_coverage = bool(rows) and 0 < positive_rows < len(rows)
    always_claim_aux = (
        statistics.fmean(row["labels"]["auxiliary_stage_score_delta"] for row in rows)
        if rows else None
    )
    gate_pass = bool(
        mechanics_ok
        and label_coverage
        and validation is not None
        and 2 <= validation["claim_count"] <= 14
        and validation["auxiliary_gate_mean"] > 0
        and validation["auxiliary_gate_mean"] >= always_claim_aux
        and validation["primary_gate_mean"] >= 0
    )
    result = {
        "schema": "r10-claim-gate-new-source-cf3c-result/1",
        "status": "PASS_CF3C_GATE_FOR_FULL_STAGE_IMPLEMENTATION" if gate_pass
        else "CLOSE_CF3C_GATE_AND_REVIEW_LITERATURE",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "attempts": attempts,
        "hits": hits,
        "validation_rows": rows,
        "decisions": ["claim" if decision else "pass" for decision in decisions],
        "summary": {
            "attempts": len(attempts),
            "hits": len(hits),
            "valid_hits_by_mix": valid_by_mix,
            "mechanics_ok": mechanics_ok,
            "positive_rows": positive_rows,
            "nonpositive_rows": len(rows) - positive_rows,
            "label_coverage": label_coverage,
            "validation": validation,
            "always_claim_auxiliary_mean": always_claim_aux,
            "gate_pass": gate_pass,
            "full_or_partial_tables": sum(
                sum(int(value) for value in hit["double_arm"]["tables_executed"].values())
                for hit in hits
            ),
            "strength_claim": False,
        },
        "next": (
            "实现只在V2过、路线父代建议吃碰且route_raw满足冻结阈值时采用鸣牌的离线候选；进入全新完整阶段开发"
            if gate_pass
            else "不得实现或调阈值；回顾Suphx信用分配、Mxplainer目标特征和杭麻规则，重构标签或特征"
        ),
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(result_path, result)
    verify_inputs(manifest)
    print(json.dumps({"status": result["status"], **result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
