"""T191三组条件评估的薄装配；复用旧恢复与单局端点，不创建通用框架。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/evaluation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1')
ROOT = _PROJECT_ROOT
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(PRIOR))
from common import OLD, canonical, pin, save
from evaluation_sharding import resource_slot_paths
from reuse_causal_helpers import EndpointEngine
from t185_prepare_confirmation import background_priority

spec = importlib.util.spec_from_file_location("t191_reused_t188_condition", _project_file(_PROJECT_ROOT, EVIDENCE / "t188-joint-score-mechanism-1/run_condition.py"))
t188 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t188)
recover = t188.recover


def require(ok, message):
    """不符即保留失败并停止，不替换输入、不重抽暗牌。"""
    if not ok:
        raise ValueError(message)


def sha(value):
    """完整公开JSON的规范SHA；不读取WorldState。"""
    return hashlib.sha256(canonical(value)).hexdigest()


def unchanged(plan):
    """检查本批全部冻结文件与当前运行源码闭包，不借旧成绩验收新身份。"""
    return all(pin(Path(p)) == expected for p, expected in plan["files"].items()) and all(
        pin(_project_file(_PROJECT_ROOT, ROOT / p)) == expected for p, expected in plan["source_manifest"].items())


def read(path):
    """只读严格JSON；相对证据路径按仓库根解析。"""
    path = Path(path)
    return json.loads((path if path.is_absolute() else _project_file(_PROJECT_ROOT, ROOT / path)).read_text())


def normalize_target(target, *, historical):
    """保留可恢复的原公开窗口，丢弃旧候选首选和旧分数，不改变其信息。"""
    case = target["case"]
    keys = ("label", "root_id", "window_key", "observation", "legal_action_keys", "view_sha256", "classes")
    require(all(k in case for k in keys), "缺目标公开信息或原图摘要")
    require(case["window_key"]["seat"] == target["focal_seat"] == case["observation"]["seat"], "目标座位不同")
    require(len(case["legal_action_keys"]) == len(set(case["legal_action_keys"])), "合法根重复")
    closure = Path(target["source_closure"])
    if not closure.is_absolute():
        closure = _project_file(_PROJECT_ROOT, ROOT / closure)
    result = {"case": {k: case[k] for k in keys}, "focal_seat": target["focal_seat"],
        "composition": target["composition"], "source_closure": str(closure),
        "selection": target["selection"], "historical_control": historical,
        "source_scope": "existing_exposed_simulation_development_reuse_not_independent_confirmation"}
    for key in ("selection_public_facts", "source_public_rows", "source_public_views"):
        if key in target:
            result[key] = target[key]
    return result


def reused_files():
    """冻结真实导入的旧工具，避免相邻导入变化静默改变恢复行为。"""
    return [_project_file(_PROJECT_ROOT, EVIDENCE / "t188-joint-score-mechanism-1/run_condition.py"), _project_file(_PROJECT_ROOT, PRIOR / "common.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "reuse_causal_helpers.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "t185_prepare_confirmation.py"), _project_file(_PROJECT_ROOT, PRIOR / "t185_close_development.py"),
        OLD / "run_causal.py", OLD / "prepare_diagnostics.py", OLD / "run_diagnostic_sources.py"]


__all__ = ["HERE", "STAGE", "ROOT", "EVIDENCE", "OLD", "canonical", "pin", "save", "sha", "read",
    "require", "unchanged", "normalize_target", "reused_files", "recover", "EndpointEngine",
    "resource_slot_paths", "background_priority"]
