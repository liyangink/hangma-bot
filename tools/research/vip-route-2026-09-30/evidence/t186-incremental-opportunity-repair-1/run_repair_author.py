"""T186首个m1：针对已持白释放增量，不改规则、框架和线上策略。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, pin, save
from glm_max_transport import make_factory
from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, load_vip_parents, run_vip_eoh_generate,
)


def main():
    """只调用一次已授权GLM5.3 max；失败保留，不自动再发。"""
    prepared = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert prepared["complete"] and prepared["maximum_author_calls"] == 2
    assert all(pin(Path(p)) == h for p, h in prepared["files"].items())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent = _project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-incremental-model-output")
    parents = load_vip_parents([parent], batch)
    assert parents[0]["identity"] == prepared["formal_parent"]
    feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-REPAIR-FEEDBACK.txt")).read_text()
    packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
    out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-model-output")
    assert not out.exists()
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-START.json"), {"operator": "m1",
        "formal_parent_identity": parents[0]["identity"], "maximum_author_calls": 2,
        "actual_previous_calls": 0, "retry": False,
        "prompt_utf8_bytes_not_precise_tokens": len(packet.text.encode()),
        "files": {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-REPAIR-FEEDBACK.txt"), _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"))},
        "new_worlds_tables_or_official_HTTP": 0})
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out,
        operator="m1", backend="api", parent_paths=[parent], feedback=feedback,
        config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"), endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"))
    print(json.dumps({k: result.get(k) for k in ("status", "identity_stable", "attempt_id", "operator_actual", "error")}), flush=True)
    if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
