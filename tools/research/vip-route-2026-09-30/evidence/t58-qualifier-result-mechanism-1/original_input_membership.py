"""只读证明16份重建实际DTO也存在于原T52完整输入捕获，不再评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ORIGINAL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t52-fixed-qualifier-unexposed-long-1')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):
            digest.update(block)
    return digest.hexdigest()


def save(name,value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('xb') as stream:
        stream.write(canonical(value)+b'\n')


def main():
    replay_path=_project_file(_PROJECT_ROOT, HERE/'PARENT-REPLAY-CLOSURE.json')
    replay=json.loads(replay_path.read_text())
    assert replay['complete'] and replay['actual_score_calls']==16
    wanted={row['actual_input_sha256']:row['label'] for row in replay['rows']}
    assert len(wanted)==16
    paths=[_project_file(_PROJECT_ROOT, ORIGINAL/f'block-{i:02}/views.jsonl.gz') for i in range(1,5)]
    frozen={str(p):sha(p) for p in [Path(__file__),replay_path,*paths]}
    save('INPUT-MEMBERSHIP-PLAN.json',{'schema':'t58-original-input-membership/1',
        'wanted_sha256_to_label':wanted,'frozen_files':frozen,'new_score_model_world_table_calls':0})
    pattern=re.compile(r'"view_sha256"\s*:\s*"([0-9a-f]{64})"')
    found={}
    read_rows=0
    for path in paths:
        with gzip.open(path,'rt',encoding='utf-8') as stream:
            for line in stream:
                read_rows+=1
                # 原捕获器将摘要写在view前，固定元信息不超过300字符。
                match=pattern.search(line[:300])
                assert match is not None, '原捕获头布局改变，不能静默略过'
                digest=match.group(1)
                if digest not in wanted or digest in found:
                    continue
                row=json.loads(line)
                assert row['schema']=='vip-scoring-input-view/1'
                assert hashlib.sha256(canonical(row['view'])).hexdigest()==row['view_sha256']==digest
                found[digest]={'label':wanted[digest],'original_capture_file':str(path)}
                if set(found)==set(wanted):
                    break
        print({'block':path.parent.name,'matched_full_inputs':len(found)},flush=True)
        if set(found)==set(wanted):
            break
    stable=all(sha(Path(p))==digest for p,digest in frozen.items())
    assert stable and set(found)==set(wanted)
    save('INPUT-MEMBERSHIP-CLOSURE.json',{'schema':'t58-original-input-membership-result/1',
        'complete':True,'source_stable':stable,'full_original_inputs_matched':16,
        'original_capture_rows_scanned':read_rows,'matches':found,
        'new_score_model_world_table_calls':0,'strength_or_online_admission':False})
    print({'complete':True,'matched_original_full_inputs':16,'new_scores':0},flush=True)


if __name__=='__main__':
    main()
