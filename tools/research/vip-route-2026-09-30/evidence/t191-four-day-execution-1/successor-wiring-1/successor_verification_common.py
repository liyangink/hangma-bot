"""复用原39请求解码和真实服务探针，额外绑定183来源的公开S03工厂。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
WORK = _project_file(_PROJECT_ROOT, '.private/t191-successor-wiring/workspace')
PRIOR_PREPARATION = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1')
sys.path[:0] = [str(_project_file(_PROJECT_ROOT, WORK / "src")), str(WORK)]
from hangma_bot import bootstrap  # 先装入隔离包，旧工具增加搜索路径不能改其模块来源。
assert Path(bootstrap.__file__).resolve().is_relative_to(WORK)
sys.path.insert(0, str(PRIOR_PREPARATION))
from verification_common import (canonical, pin, save, check_files, digest, original_cases,
    resource_zero, planned_scores, research_slots)


def validated_assembly():
    """只用真实8包验装、原638等价及183来源；没有新候选或二次效果确认。"""
    packages = json.loads((_project_file(_PROJECT_ROOT, HERE / "PACKAGES-CLOSED.json")).read_text())
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / "ASSEMBLY-VALIDATION-CLOSED.json")).read_text())
    assert packages["complete"] and closed["complete"] and closed["source_stable"]
    assert len(closed["actual_checks"]) == 80 and closed["actual_functional_score_calls"] == 10
    assert packages["source_manifest"] == closed["source_manifest"] == bootstrap._vip_runtime_sources()
    row = next(r for r in packages["rows"] if r["strategy"] == bootstrap.VIP_S03_FREE_STRATEGY)
    package = bootstrap._load_vip_manifest(row["strategy"], row["package_id"])
    compiled = bootstrap._verify_vip_s03_runtime(package["compiled_runtime"]["manifest_sha256"])[0]
    assert pin(_project_file(_PROJECT_ROOT, WORK / row["package_path"])) == row["package_pin"]
    source = _project_file(_PROJECT_ROOT, HERE.parent / "wait-reassessment-1/candidate/source.py")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == package["source_sha256"]
    arm = {"identity": package["candidate_identity"], "source_file": str(source)}
    runtime = SimpleNamespace(execution_id=row["package_id"],
        original_execution_id=compiled["manifest"]["original_execution_id"])
    files = {str(_project_file(_PROJECT_ROOT, HERE / name)): pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in
        ("PACKAGES-CLOSED.json", "ASSEMBLY-VALIDATION-CLOSED.json", "successor_verification_common.py",
         "probe_successor_deadlines.py")}
    files.update({str(_project_file(_PROJECT_ROOT, WORK / path)): {"bytes": (_project_file(_PROJECT_ROOT, WORK / path)).stat().st_size, "sha256": sha}
        for path, sha in packages["source_manifest"].items()})
    files.update({str(_project_file(_PROJECT_ROOT, WORK / row["package_path"])): row["package_pin"]})
    directory = _project_file(_PROJECT_ROOT, WORK / compiled["directory"])
    files.update({str(directory / name): expected for name, expected in compiled["manifest"]["files"].items()})
    files[str(directory / "manifest.json")] = pin(directory / "manifest.json")
    files.update({str(_project_file(_PROJECT_ROOT, WORK / name)): {"bytes": (_project_file(_PROJECT_ROOT, WORK / name)).stat().st_size, "sha256": sha}
        for name, sha in package["evidence_sha256"].items()})
    check_files(files)
    return None, arm, runtime, files
