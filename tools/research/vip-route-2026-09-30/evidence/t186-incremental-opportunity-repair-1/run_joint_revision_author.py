"""T186第二次且最后一次GLM作者调用：联合修订弃牌信用与等待增量。"""

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
import fcntl
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
    """先复核冻结反馈及费用，再单次调用；失败不自动重发，不启动牌桌。"""
    with (_project_file(_PROJECT_ROOT, HERE / ".joint-author-owner.lock")).open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        preparation = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-JOINT-REVISION-PREPARATION-v2.json")
        prepared = json.loads(preparation.read_text())
        assert prepared["complete"] and prepared["maximum_author_calls"] == 2
        assert prepared["actual_previous_model_calls"] == 1 and prepared["confirmation_pool_not_read"]
        assert all(pin(Path(p)) == h for p, h in prepared["files"].items())
        factpath = _project_file(_PROJECT_ROOT, HERE / "CURRENT-HU-ANCHOR-FACT-CHECK.json")
        fact = json.loads(factpath.read_text())
        assert fact["complete"] and fact["current_hu_has_baotou"] is False
        assert all(pin(Path(p)) == h for p, h in fact["files"].items())
        batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        parent = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
        parents = load_vip_parents([parent], batch)
        assert parents[0]["identity"] == prepared["formal_parent_identity"]
        feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-JOINT-REVISION-FEEDBACK-v2.txt")).read_text()
        packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
        assert packet.sha256 == prepared["prompt_sha256"]
        out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output")
        assert not out.exists()
        start = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-START.json")
        assert not start.exists()
        save(start, {"operator": "m1", "formal_parent_identity": parents[0]["identity"],
            "maximum_author_calls": 2, "actual_previous_calls": 1, "retry": False,
            "prompt_utf8_bytes_not_precise_tokens": len(packet.text.encode()),
            "files": {str(p): pin(p) for p in (Path(__file__), preparation, factpath,
                _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-JOINT-REVISION-FEEDBACK-v2.txt"), _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"))},
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
