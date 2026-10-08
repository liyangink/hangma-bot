"""分析文件与原始压缩记录必须隔离，重复写报告也不能覆盖原始证据。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

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
import shutil

import pytest

from lab import HERE
from conditional_analysis import analyze


def test_report_output_never_reuses_the_last_rows_filename(tmp_path):
    cid='mutation-1-82';filename=f'persistent-{cid}.jsonl.gz'
    directories=[]
    for name,source in [('new','dual-route'),('old','progress-guard')]:
        dest=tmp_path/name;dest.mkdir();directories.append(dest)
        original=_project_file(_PROJECT_ROOT, HERE/source)
        manifest=json.loads((original/'persistent-freeze.json').read_text())
        manifest['cases']=[r for r in manifest['cases'] if r['case']['case_id']==cid]
        summary=json.loads((original/'persistent-summary.json').read_text())
        summary['cases']=[r for r in summary['cases'] if r['case_id']==cid]
        (dest/'persistent-freeze.json').write_text(json.dumps(manifest))
        (dest/'persistent-summary.json').write_text(json.dumps(summary))
        shutil.copyfile(original/filename,dest/filename)
    new,old=directories
    before=hashlib.sha256((new/filename).read_bytes()).hexdigest()
    comparisons={'fixed_root_increment':('seven_dual','seven_guard')}
    a=analyze(new,old,comparisons,1)
    b=analyze(new,old,comparisons,1,output_filename='second-report.json')
    assert a==b
    assert (new/'analysis.json').is_file() and (new/'second-report.json').is_file()
    assert hashlib.sha256((new/filename).read_bytes()).hexdigest()==before
    with pytest.raises(ValueError):analyze(new,old,comparisons,1,output_filename=filename)
    assert hashlib.sha256((new/filename).read_bytes()).hexdigest()==before
