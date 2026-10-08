"""修复后的零调用重判：读取原始回复，报告只写新目录，不改历史证据。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import contextlib
import io
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
DEV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
sys.path.insert(0, str(DEV))
import criterion as c

def main():
    """按同一新版判分器重判两个原始数据集；不作模型排名或新准入。"""
    rows = {}
    for name in ('slim', 'glm'):
        c.PACKAGE = _project_file(_PROJECT_ROOT, DEV / name / 'package')
        target = _project_file(_PROJECT_ROOT, HERE / (name + '-regrade.json'))
        sys.argv = ['criterion.py', '--replies', str(_project_file(_PROJECT_ROOT, DEV / name / 'replies/first')),
                    '--round-label', 'takeover-regrade-' + name, '--out', str(target)]
        with contextlib.redirect_stdout(io.StringIO()):
            c.main()
        grade = json.loads(target.with_suffix('.grade.json').read_text())
        rows[name] = [{k: r.get(k) for k in ('task_id', 'first_pass', 'repair_pass', 'pass',
                      'repair_gate', 'attempt_change')} for r in grade['tasks']]
    (_project_file(_PROJECT_ROOT, HERE / 'regrade-summary.json')).write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({name: {'first': sum(bool(r['first_pass']) for r in rs),
                                  'final': sum(bool(r['pass']) for r in rs),
                                  'rows': [[r['task_id'],r['first_pass'],r['pass']] for r in rs]}
                      for name,rs in rows.items()}, ensure_ascii=False))
if __name__ == '__main__':
    main()
