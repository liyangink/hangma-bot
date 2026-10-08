"""在实际编码装配下运行录制器公开契约；fixture不调用真实研究业务。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t120-s02-bounded-native-capture-1'

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
import sys
import pytest

HERE = Path(__file__).resolve().parent
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME/'src'))]
from codec_overlay import installed


def main():
    """返回实际pytest状态，退出后检查编码绑定恢复，保留原测试收据。"""
    with installed() as (identity, stats):
        code = pytest.main(['-q', '-p', 'no:cacheprovider',
            'tests/unit/offline/test_scoring_input_capture.py'])
    with (_project_file(_PROJECT_ROOT, HERE/'CAPTURE-CONTRACT-RESULT.json')).open('x') as stream:
        json.dump({'schema':'t120-capture-contract/1','pytest_exit_code':int(code),
            'native_identity':identity,'codec_stats':stats,
            'actual_rule_choose_score_world_table_calls':0},stream,
            ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    return int(code)


if __name__ == '__main__':
    raise SystemExit(main())
