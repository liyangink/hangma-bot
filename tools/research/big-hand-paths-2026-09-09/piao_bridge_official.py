"""从真实条件续打审计提取首飘/终点，对拍无状态官方工具并保存原文。"""

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
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import ssl
import time
import urllib.request

from lab import ROOT
from piao_bridge_probe import DIRECTORY, cases

BASE = 'https://10.240.169.190:18080'


def inputs():
    """每个计番阶段/最终明细各取首个实际世界；不把未实现的路径伪造为终点。"""
    result = []
    for case in cases():
        original = case['initial_hand']
        result.append(dict(tag=case['case_id']+'-root', request=dict(hand=original[:-1], draw=original[-1],
            base=1, chain=dict(count=0, piao=0)), expected=case['expected']))
        seen = set()
        for row in map(json.loads, gzip.open(DIRECTORY/(case['case_id']+'.jsonl.gz'), 'rt')):
            arm = row['arms']['bridge']
            piao = 1
            choices = {h['seq']:h for h in arm['hu_choices']}
            for trace in arm['trace']:
                assert trace['action'] in ('discard:白', 'hu', 'pass')
                if trace['seq'] in choices:
                    h = choices[trace['seq']]
                    kind = (piao, tuple(h['details']))
                    if kind not in seen:
                        seen.add(kind)
                        result.append(dict(tag=f'{case["case_id"]}-piao-{piao}-{len(seen)}',
                            source_seed=row['seed'], source_seq=trace['seq'],
                            request=dict(hand=h['hand'], draw=h['draw'], base=1, chain=dict(count=piao,piao=piao)),
                            expected=dict(hu=True, baotou=True, fan=h['immediate_score']//24,
                                          detail=h['details'])))
                if trace['action']=='discard:白':
                    piao += 1
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """TLS 例外仅作用于已配置固定内网主机，禁止跟随到其他地址。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('官方无状态工具发生重定向，停止')


def capture():
    """无需 Token，起始请求间隔至少一秒；异常停止，保留每条原始响应。"""
    directory = DIRECTORY/'official'
    directory.mkdir(exist_ok=False)
    selected = inputs()
    (directory/'inputs.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=context))
    previous = time.monotonic()
    with opener.open(BASE+'/portal/api/guide?format=text', timeout=12) as response:
        guide = response.read()
    (directory/'guide.json').write_bytes(guide)
    version = json.loads(guide)['version']
    mismatches = []
    with (directory/'responses.jsonl').open('x') as output:
        for item in selected:
            time.sleep(max(0, 1-(time.monotonic()-previous)))
            previous = time.monotonic()
            request = urllib.request.Request(BASE+'/portal/api/tools/fan-calc',
                data=json.dumps(item['request'],ensure_ascii=False).encode(), headers={'Content-Type':'application/json'})
            with opener.open(request, timeout=12) as response:
                raw = response.read().decode()
                status = response.status
            parsed = json.loads(raw)
            mismatch = {k:dict(expected=v,actual=parsed.get(k)) for k,v in item['expected'].items()
                        if k in ('hu','baotou','fan','detail') and parsed.get(k)!=v}
            record = dict(item,http_status=status,response=parsed,response_raw=raw,guide_version=version,
                          captured_at_utc=datetime.now(timezone.utc).isoformat(),mismatch=mismatch)
            output.write(json.dumps(record,ensure_ascii=False)+'\n')
            output.flush()
            if mismatch:
                mismatches.append(dict(tag=item['tag'],mismatch=mismatch))
    manifest = dict(endpoint=BASE+'/portal/api/tools/fan-calc',guide_version=version,cases=len(selected),
        mismatches=mismatches, sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in directory.iterdir() if p.is_file()})
    (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False))
    assert not mismatches


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true')
    if parser.parse_args().capture:
        capture()
    else:
        print(json.dumps(inputs(),ensure_ascii=False,indent=2))
