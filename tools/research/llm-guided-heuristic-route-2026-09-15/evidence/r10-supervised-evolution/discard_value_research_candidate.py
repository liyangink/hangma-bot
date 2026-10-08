"""R11-DV1-2R：冻结未过原门但值得独立确认的弃牌研究候选。"""

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
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import discard_value_grouped_model as grouped  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-research-candidate-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R11-DISCARD-ACTION-VALUE-EVOLUTION-PLAN-2026-09-21.md')
MODEL_RESULT = grouped.OUT / "result.json"
SELECTED_MODEL_ID = "gam:features=16:passes=3:shrinkage=0.15"
FEATURE_LIMIT = 16
PASSES = 3
SHRINKAGE = 0.15


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_reading(result: dict) -> dict:
    """读取逐字匹配的开发留出读数。"""

    return next(
        item for item in result["comparisons"]
        if item["model_id"] == SELECTED_MODEL_ID
    )


def prepare() -> None:
    """冻结事后选择身份、模型规格、输入数据和多重性声明。"""

    if OUT.exists():
        raise SystemExit("DV1-2R 候选目录已存在；拒绝覆盖")
    result = batch.read(MODEL_RESULT)
    if result.get("status") != "CLOSE_DV1_2_GROUPED_MODELS_NO_GENERALIZATION":
        raise SystemExit("原四折批没有按失败关闭")
    reading = selected_reading(result)
    if reading.get("passes_continue_gate") is not False:
        raise SystemExit("研究候选身份必须来自未过原门的规格")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r11-dv1-research-candidate-v1",
        authorization_id="r11-dv1-research-candidate-v1-20260921",
        accounts={},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "原四折门不追认；按文献复盘把总体正向但单小面板未分辨的GAM-16保留为唯一探索候选，后续必须全新来源独立确认",
        "scope": "只用既有128快照重拟合逐字同一GAM规格并冻结训练内阈值；零LLM、零桌赛",
        "max_model_calls": 0,
        "max_model_fits": 1,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r11-dv1-research-candidate/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(grouped.__file__), PLAN, _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        ]),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "data": str(grouped.DATA),
        "data_sha256": digest(grouped.DATA),
        "model_result": str(MODEL_RESULT),
        "model_result_sha256": digest(MODEL_RESULT),
        "selected_model_id": SELECTED_MODEL_ID,
        "selection_origin": "post_hoc_research_retention_from_11_preregistered_models",
        "original_gate_passed": False,
        "development_reading": reading,
        "multiple_models_screened": len(result["comparisons"]),
        "independent_confirmation_required": True,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_DV1_2R_RESEARCH_CANDIDATE",
        "selected_model_id": SELECTED_MODEL_ID,
        "original_gate_passed": False,
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对模型代码、计划、教师数据和原关闭结果。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("data", "data_sha256"),
        ("model_result", "model_result_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def run() -> None:
    """用全部开发数据重拟合唯一研究候选并冻结阈值。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("DV1-2R 候选已经冻结；拒绝覆盖")
    rows = list(batch.read(grouped.DATA)["rows"])
    training = grouped.examples(rows)
    model = grouped.fit_gam(training, FEATURE_LIMIT, PASSES, SHRINKAGE)
    threshold, calibration = grouped.calibrate_threshold(model, rows)
    decision_artifact = {
        "schema": "r11-dv1-discard-decision-artifact/1",
        "decision_threshold": threshold,
        "threshold_calibration": calibration,
        "model": model.artifact(),
    }
    reconstructed, reconstructed_threshold = grouped.decision_from_artifact(decision_artifact)
    if reconstructed_threshold != threshold:
        raise ValueError("冻结阈值无法往返")
    sample = training[0]["features"]
    if reconstructed.predict(sample) != model.predict(sample):
        raise ValueError("冻结模型无法逐值往返")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "candidate.json"), decision_artifact)
    result = {
        "schema": "r11-dv1-research-candidate-result/1",
        "status": "FROZEN_RESEARCH_CANDIDATE_FOR_INDEPENDENT_ACTION_VALIDATION",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "candidate.json")),
        "selected_model_id": SELECTED_MODEL_ID,
        "snapshots": len(rows),
        "training_examples": len(training),
        "decision_threshold": threshold,
        "original_gate_passed": False,
        "selection_origin": manifest["selection_origin"],
        "multiple_models_screened": manifest["multiple_models_screened"],
        "next": "用四个全新面板种子执行唯一一次128快照、16共同未来顺序的独立动作确认",
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
