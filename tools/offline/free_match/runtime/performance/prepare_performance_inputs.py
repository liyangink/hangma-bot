"""T199原39窗口＋P0正反例＋18重型公开输入；只解码/冻结，不评分或开计算服务。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/performance'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import copy
import json
from pathlib import Path

from performance_common import ROOT, P0, HERE, OUT, digest, package, pin, read, save


def main():
    """原输入字节及数字完整时才重用原预算；其他案例只标名义窗口。"""
    from hangma_bot.application.audit_codec import decision_request_from_json
    from hangma_bot.kernel.serialization import observation_from_json
    import math
    OUT.mkdir(exist_ok=False)
    rows, files = [], {}
    prior = _project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
    deadlines = ('enhancement_deadline_monotonic','fallback_deadline_monotonic','latest_send_at_monotonic')

    def add(record, origin, group, position):
        if record.get('kind') != 'decision_input':
            return
        request = decision_request_from_json(record['payload']['request'])
        stamp = record['monotonic_ns']
        raw = record['payload']['budget']
        if type(stamp) is not int or stamp < 0 or any(type(raw[k]) not in (int,float) or not math.isfinite(raw[k]) for k in deadlines):
            raise ValueError('原记录时间／预算无效')
        spans = [raw[k] - stamp / 1e9 for k in deadlines]
        if not (0 < spans[0] <= spans[1] <= spans[2]):
            raise ValueError('原余量非正或逆序，不扩窗')
        rows.append({'label':'original:'+request.decision_id,'decision_id':request.decision_id,
            'observation':record['payload']['request']['observation'], 'window_key':record['payload']['request']['window_key'],
            'original_request':record['payload']['request'],'original_budget':raw,'original_monotonic_ns':stamp,
            'original_remaining_seconds':spans,'nominal_seconds':3.0 if request.observation.phase=='draw' else 1.0,
            'group':group,'origin':str(origin),'origin_position':position,'record_sha256':digest(record),
            'official_original_budget':True})

    ref = read(_project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t173-joint-exact-equivalence-1/joint-actual-001/JOINT-RESULT.json'))
    refs = {r['decision_id']:r for r in ref['rows'] if r['variant']=='baseline' and r['repeat']==0}
    for path in sorted((_project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t169-closed-state-pressure-1')).glob('dec-*.json')):
        files[str(path)] = pin(path)
        document = read(path)
        position, record = next((i,r['record']) for i,r in enumerate(document['records']) if r['record']['kind']=='decision_input')
        add(record,path,'original-pressure',position)
        if files[str(path)]['sha256'] != refs[rows[-1]['decision_id']]['original_input_sha256']:
            raise ValueError('七压力原输入SHA漂移')
        if [v*1000 for v in rows[-1]['original_remaining_seconds']] != refs[rows[-1]['decision_id']]['original_remaining_ms']:
            raise ValueError('七压力原余量未核同')
    sources = [_project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t183-baotou-wait-case-a40864715552-1/WINDOW-AUDIT.jsonl'),
               _project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t184-white-strata-and-strong-gap-1/OPENING-ORIGINAL-AUDIT.jsonl'),
               prior / 'SUPPLEMENT-ORIGINAL-AUDIT.jsonl']
    expected = read(prior / 'LIVE-DEADLINE-SUPPLEMENT.json')['files']
    expected.update(read(prior / 'SUPPLEMENT-PLAN.json')['files'])
    for source in sources:
        files[str(source)] = pin(source)
        if files[str(source)] != expected[str(source)]:
            raise ValueError('十二片段或二十首摸原字节漂移')
        for position, line in enumerate(source.read_bytes().splitlines()):
            record = json.loads(line)
            if record.get('kind') != 'decision_input':
                continue
            group = 'original-live' if source!=sources[-1] else 'supplement-'+record['payload']['request']['window_key']['game_id'].split('_r1_')[0]
            add(record,source,group,position)
    if len(rows)!=39 or len({r['decision_id'] for r in rows})!=39 or len({r['window_key']['game_id'] for r in rows})!=27:
        raise ValueError('原39请求／27桌未完整解码，不重造19替代')
    original_count = len(rows)
    heavy_path = _project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1/development-heavy-inputs/CASES.json')
    files[str(heavy_path)] = pin(heavy_path)
    for index, case in enumerate(read(heavy_path)['cases']):
        raw=case['original_public_decision']
        obs=observation_from_json(raw['observation'])
        rows.append({'label':'heavy:%02d'%index,'decision_id':raw['decision_id'],'observation':raw['observation'],
            'window_key':raw['window_key'],'original_remaining_seconds':None,'nominal_seconds':3.0 if obs.phase=='draw' else 1.0,
            'group':'nominal-heavy','origin':str(heavy_path),'origin_position':index,'official_original_budget':False})
    fixture_path = _project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t197-strong-behavior-code-audit-1/FAN-FIXTURE.json')
    gold_path = _project_file(_PROJECT_ROOT, ROOT / '.private/t199-four-step-execution/p0-workspace/tests/fixtures/official/v35/fan-calc-branch-baotou/cases.jsonl')
    files[str(fixture_path)],files[str(gold_path)] = pin(fixture_path),pin(gold_path)
    base=read(fixture_path)['minimal_observation']
    for index,line in enumerate(gold_path.read_bytes().splitlines()):
        row=json.loads(line);q=row['request'];obs=copy.deepcopy(base);gid='t199-p0-gold-'+row['tag']
        obs.update(game_id=gid,my_hand=q['hand'],drawn_tile=q['draw'],gang_draw=q['chain']['count']>q['chain']['piao'],chain_piao=q['chain']['piao'])
        obs['rule_state'].update(baotou=row['response']['baotou'],chain_count=q['chain']['count'])
        observation_from_json(obs)
        key={'schema_version':1,'game_id':gid,'round_no':obs['round_no'],'trigger_seq':obs['snapshot_seq'],'phase':'draw','seat':obs['seat']}
        rows.append({'label':'gold:'+row['tag'],'decision_id':'t199-p0-'+row['tag'],'observation':obs,'window_key':key,
            'original_remaining_seconds':None,'nominal_seconds':3.0,'group':'nominal-gold','origin':str(gold_path),
            'origin_position':index,'official_original_budget':False,'trajectory_reachability':row['trajectory_reachability']})
    payload=package()
    frozen=read(_project_file(_PROJECT_ROOT, ROOT / '.private/t199-four-step-execution/runtime-workspace/P0-RUNTIME-ROOT-FINAL.json'))
    if any(pin(P0 / relative)!=expected for relative,expected in frozen['files'].items()):
        raise ValueError('冻结P0根实际字节漂移')
    save(OUT / 'INPUTS.json',{'complete':True,'rows':rows,'input_files':files,'original_requests':original_count,
        'nominal_heavy':18,'nominal_gold':len(rows)-57,'P0_root_manifest_pin':pin(_project_file(_PROJECT_ROOT, ROOT / '.private/t199-four-step-execution/runtime-workspace/P0-RUNTIME-ROOT-FINAL.json')),
        'package_id':payload['release_package_id'],'candidate_identity':payload['candidate_identity'],
        'rules_source_hash':payload['rules_source_hash'],'scores_compute_workers_HTTP_Token':0})
    print({'original_requests':original_count,'total_cases':len(rows),'scores':0,'compute_workers':0},flush=True)


if __name__=='__main__':
    main()
