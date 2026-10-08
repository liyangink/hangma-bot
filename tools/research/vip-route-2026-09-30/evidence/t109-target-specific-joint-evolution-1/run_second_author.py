"""执行T109最后一份已授权GLM联合提案，不自动重试或额外开作者。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1'

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
from prepare_second_author import pin

HERE = Path(__file__).resolve().parent


def main():
    """原失败和所有输入先核验；凭据只由既有API适配器读取。"""
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S02-AUTHOR-PREPARATION-CLOSED.json')).read_text())
    assert prep['complete'] and prep['actual_author_slots_already_used'] == 1
    assert all(pin(Path(p)) == h for p, h in prep['frozen_files'].items())
    parent = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'S02-API-BATCH.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-model-output'), operator='m1', backend='api', parent_paths=[parent],
        feedback=(_project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt')).read_text(),
        config=Path('/Users/liyang/hangma-bot/.private/vip-zai-api.json'),
        endpoint='zai-coding-cn', model='glm-5.3', tier='senior')
    print({k: result.get(k) for k in ('status', 'identity_stable', 'attempt_id', 'operator_actual')})
    if result['status'] != 'loaded_not_admitted' or not result['identity_stable']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
