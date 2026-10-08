"""发起一槽已授权GLM 5.3提案；复用EoH额度账、隔离和凭据脱敏。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

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
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import run_vip_eoh_generate
from glm_max_transport import make_factory
from common import HERE, ROOT, pin, save


def main(mechanism):
    """只读取已冻结公开材料；失败原样保留并计槽，禁止自动重发。"""
    assert mechanism in ("speed", "incremental")
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert all(pin(Path(p)) == h for p, h in preparation["files"].items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in preparation["source_manifest"].items())
    out = _project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-model-output")
    assert not out.exists()
    feedback = (_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-FEEDBACK.txt")).read_text()
    save(_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-START.json"), {"mechanism": mechanism, "operator": "i1", "parent_paths": [],
        "model": "glm-5.3", "endpoint": "zai-coding-cn", "authorization": "human standing project-source and feedback API authorization",
        "preparation_pin": pin(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")), "runner_pin": pin(Path(__file__)),
        "reasoning_transport_pin": pin(_project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py")),
        "api_request_started_at_start_file": False, "retry": False})
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out,
        operator="i1", backend="api", parent_paths=[], feedback=feedback,
        config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"), endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"))
    print({k: result.get(k) for k in ("status", "identity_stable", "attempt_id", "operator_actual", "error")}, flush=True)
    if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mechanism", choices=("speed", "incremental"), required=True)
    main(parser.parse_args().mechanism)
