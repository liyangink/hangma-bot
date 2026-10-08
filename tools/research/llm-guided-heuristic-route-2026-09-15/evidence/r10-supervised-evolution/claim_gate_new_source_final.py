"""CF3-C3：可空类型兼容修复后的全新来源门控器验证。"""

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
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_nullable as nullable  # noqa: E402
import claim_counterfactual_pilot as core  # noqa: E402
import claim_gate_new_source_nullable as runner  # noqa: E402
import claim_gate_stump_calibration as stump  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-new-source-03-20260921')
STUMP_RESULT = stump.OUT / "result.json"
FAILED_BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-new-source-02-20260921/failure.json')
PANEL_SEED = 2026092305


def prepare() -> None:
    """冻结第二次兼容修复、全新来源和不变的门控器/验证条件。"""

    if OUT.exists():
        raise SystemExit("CF3-C3 目录已存在；拒绝覆盖")
    failed = batch.read(FAILED_BATCH)
    if failed["status"] != "CLOSED_COMPATIBILITY_DEFECT_NO_VALIDATION_RESULT":
        raise ValueError("CF3-C2 失败没有正确关闭")
    stump_result = batch.read(STUMP_RESULT)
    if stump_result["status"] != "PASS_CF3B_STUMP_FOR_NEW_SOURCE_VALIDATION":
        raise ValueError("CF3-B 未授权新来源验证")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-claim-gate-new-source-cf3c3",
        authorization_id="r10-claim-gate-new-source-cf3c3-20260921",
        accounts={"tables_full": runner.MAX_TABLES, "prefix_generation": 64},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "CF3-C2在首个机会截取前因兼容层覆盖float类型失败；改为float子类后，门控器与判据保持不变",
        "scope": "全新panel_seed；H/M各按root_index升序最多检查32根并取前8个行为命中；每机会双臂两桌；门控器冻结不调参",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=[
        Path(__file__), Path(runner.__file__), Path(nullable.__file__), Path(core.__file__),
        Path(stump.__file__), STUMP_RESULT, FAILED_BATCH, core.CONTRACT,
        core.ROUTE_SOURCE, _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
    ])
    model = stump_result["selected"]["final_model"]
    manifest = {
        "schema": "r10-claim-gate-new-source-cf3c3/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "stump_result": str(STUMP_RESULT),
        "stump_result_sha256": runner.digest(STUMP_RESULT),
        "failed_batch": str(FAILED_BATCH),
        "failed_batch_sha256": runner.digest(FAILED_BATCH),
        "nullable_adapter": str(Path(nullable.__file__)),
        "nullable_adapter_sha256": runner.digest(Path(nullable.__file__)),
        "model": model,
        "panel_seed": PANEL_SEED,
        "mixes": list(runner.MIXES),
        "target_hits_per_mix": runner.TARGET_HITS_PER_MIX,
        "max_roots_per_mix": runner.MAX_ROOTS_PER_MIX,
        "selection": "每层按root_index升序取前8个行为命中；不读取标签",
        "validation_gate": {
            "mechanics": "H/M各8个有效命中；两臂完整且首动作匹配",
            "label_coverage": "辅助正类和非正类均至少1个",
            "behavior": "冻结门控器claim_count在2..14",
            "effect": "门控辅助积分均值>0且>=always-claim；门控主晋级保守差均值>=0",
            "meaning": "通过只允许实现离线候选并进入全新完整阶段开发；不是强度或发布证据",
        },
        "max_samples": runner.MAX_SAMPLES,
        "max_tables": runner.MAX_TABLES,
        "llm_calls": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_CF3C3", "model": model}, ensure_ascii=False))


def run() -> None:
    """复用冻结的 C2 执行与验收逻辑，仅替换输出目录和全新来源。"""

    runner.OUT = OUT
    runner.PANEL_SEED = PANEL_SEED
    runner.FAILED_BATCH = FAILED_BATCH
    runner.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
