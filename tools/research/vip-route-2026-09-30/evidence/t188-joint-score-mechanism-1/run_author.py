"""T188按已验证机制发出一次真实GLM作者；不自动重发，不启动牌桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

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
    """复核两个真实父与冻结反馈，调用已授权API一次，保留失败和用量。"""
    with (_project_file(_PROJECT_ROOT, HERE / ".author-owner.lock")).open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prep_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")
        prep = json.loads(prep_path.read_text())
        assert prep["complete"] and prep["confirmation_pool_not_read"]
        assert all(pin(Path(p)) == h for p, h in prep["files"].items())
        batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        paths = [Path(p) for p in prep["formal_parent_paths"]]
        parents = load_vip_parents(paths, batch)
        assert [p["identity"] for p in parents] == prep["formal_parent_identities"]
        feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-FEEDBACK.txt")).read_text()
        prompt, _ = build_vip_eoh_prompt(batch, "e2", parents, feedback)
        assert prompt.sha256 == prep["prompt_sha256"]
        out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-model-output")
        assert not out.exists()
        save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-START.json"), {
            "operator": "e2", "retry": False, "model": "glm-5.3", "endpoint": "zai-coding-cn",
            "requested_reasoning_effort": "max", "prompt_sha256": prompt.sha256,
            "parent_identities": prep["formal_parent_identities"],
            "files": {str(p): pin(p) for p in (
                Path(__file__), prep_path, _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-FEEDBACK.txt"),
                _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"),
            )}, "new_worlds_tables_or_official_HTTP": 0,
        })
        result = run_vip_eoh_generate(
            batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out, operator="e2", backend="api",
            parent_paths=paths, feedback=feedback, config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"),
            endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
            backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"),
        )
        print(json.dumps({k: result.get(k) for k in (
            "status", "identity_stable", "attempt_id", "operator_actual", "error",
        )}), flush=True)
        if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
