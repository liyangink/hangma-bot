"""执行第一份已冻结紧凑GLM提案；第二份须等实际反馈再单独准备。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import run_vip_eoh_generate
from prepare import pin

HERE = Path(__file__).resolve().parent


def main():
    """凭据只交既有API边界；原失败、预算、公开范围和源码不得漂移。"""
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    assert prep['complete'] and prep['before_actual_API_call']
    assert all(pin(Path(name)) == expected for name, expected in prep['frozen_files'].items())
    parent = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-model-output'), operator='m1', backend='api', parent_paths=[parent],
        feedback=(_project_file(_PROJECT_ROOT, HERE / prep['actual_feedback_file'])).read_text(),
        config=Path('/Users/liyang/hangma-bot/.private/vip-zai-api.json'),
        endpoint='zai-coding-cn', model='glm-5.3', tier='senior')
    print({key: result.get(key) for key in ('status', 'identity_stable', 'attempt_id', 'operator_actual')}, flush=True)
    if result['status'] != 'loaded_not_admitted' or not result['identity_stable']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
