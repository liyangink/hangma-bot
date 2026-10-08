"""八个实际进程全部终态后，纯读核256桌、双基线和真实积分分账。

复用T93完整输入读取器，不调用规则、评分、世界或模型。不把重复R18
当新来源；T101相对T97的差额必须在重复A全动作/终局一致后才给出。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t102-joint-breadth-fresh-pilot-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import defaultdict
from dataclasses import asdict
import gzip
import importlib.util
import json
from pathlib import Path
import statistics

from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.evaluation_results import read_results_jsonl, check_complete_consistency
from hangma_bot.offline.vip_evaluation import FrozenRoot, audit_vip_batch

HERE=Path(__file__).resolve().parent
OLD=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py')
PERMUTATIONS=((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2))
BANDS=('own_lt4','own_4_to7','own_8_to15','own_ge16','opponent_hu','draw')


def save(name,value):
    """终态只创建，失败读回和费用不可覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def main():
    """核八块完整结果后按16母根计算三种差额，置信区间仅开发描述。"""
    spec=importlib.util.spec_from_file_location('t93_closed_input_reader',OLD)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    plan=json.loads((_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')).read_text())
    handles=json.loads((_project_file(_PROJECT_ROOT, HERE/'ALL-PROCESS-HANDLES.json')).read_text())['processes']
    assert len(handles)==8 and {h['block'] for h in handles}==set(range(1,9))
    terminal_paths=[_project_file(_PROJECT_ROOT, HERE/f'BLOCK-{i:02d}-TERMINAL.json') for i in range(1,9)]
    if not all(p.exists() for p in terminal_paths):
        print({'status':'await_all_actual_tool_terminals','outcomes_read':False});raise SystemExit(2)
    terminals=[json.loads(p.read_text()) for p in terminal_paths]
    by_block={h['block']:h for h in handles}
    for t in terminals:
        assert t['session_id']==by_block[t['block']]['session_id'] and t['verified_tool_terminal']
    # 先读取实际费用。任一验证失败也保留已经消耗的桌实例。
    costs=[]
    for i in range(1,9):
        path=_project_file(_PROJECT_ROOT, HERE/f'block-{i:02d}/costs.json')
        value=json.loads(path.read_text()) if path.exists() else None
        es=value['entries'] if value else []
        costs.append({'block':i,'cost_record_present':value is not None,
            'actual_started_known_subtotal':sum(e['actual_started_table_instances'] or 0 for e in es),
            'actual_started_unknown_entries':sum(e['actual_started_table_instances'] is None for e in es),
            'charged_instances':sum(e['charged_table_instances'] for e in es),
            'settled_pairs':sum(e['status']=='settled' for e in es),
            'failed_pairs':sum(e['status']=='failed_cost_retained' for e in es)})
    issues=[];input_audits=[];pairs={v:defaultdict(dict) for v in ['T101','T97']}
    table_sums={v:defaultdict(int) for v in ['T101','T97']}
    realized={v:{a:{k:{'hands':0,'score':0} for k in BANDS} for a in ['A','C']} for v in ['T101','T97']}
    root_highfan={v:{a:defaultdict(int) for a in ['A','C']} for v in ['T101','T97']}
    outcomes={v:{} for v in ['T101','T97']};settlements_by_match={v:defaultdict(list) for v in ['T101','T97']}
    seen_hands=set();baseline_ids=set();descriptive=None;duplicate_tables=0
    try:
        assert all(t['exit_code']==0 for t in terminals)
        assert not (_project_file(_PROJECT_ROOT, HERE/'GLOBAL-ENGINEERING-FAILURE.json')).exists()
        for n,expected in plan['prerequisite_sha256'].items():assert helper.sha(Path(n))==expected
        reader_freeze=json.loads((_project_file(_PROJECT_ROOT, HERE/'OUTCOME-READER-FREEZE.json')).read_text())
        for n,expected in reader_freeze['files'].items():assert helper.sha(Path(n))==expected
        for i in range(1,9):
            out=_project_file(_PROJECT_ROOT, HERE/f'block-{i:02d}');bp=json.loads((_project_file(_PROJECT_ROOT, HERE/f'BLOCK-{i:02d}-PLAN.json')).read_text())
            v=bp['variant'];cid='vip:'+bp['candidate_identity']['candidate_id']
            summary=json.loads((out/'summary.json').read_text())
            assert summary['block_complete'] and summary['identity_stable'] and not summary['issues']
            assert summary['candidate_identity']==plan['formulas'][v] and summary['variant']==v
            assert summary['observed_result_rows']==summary['actual_started_table_instances']==summary['charged_table_instances']==32
            assert summary['completed_hands']==256
            freeze=json.loads((out/'end-freeze.json').read_text());assert freeze['source_stable']
            for n,d in freeze['frozen_files'].items():assert helper.sha(Path(n))==d
            for n,d in freeze['source_manifest'].items():
                actual,copied=_project_file(_PROJECT_ROOT, REPO_ROOT/n),out/'code_snapshot'/n
                assert actual.stat().st_size==copied.stat().st_size==d['bytes']
                assert helper.sha(actual)==helper.sha(copied)==d['sha256']
            assert helper.sha(out/'RUNNER.py')==helper.sha(_project_file(_PROJECT_ROOT, HERE/'run_block.py'))
            input_audits.append(dict(block=i,variant=v,**helper.audit_actual_inputs(out,summary,bp)))
            rs=read_results_jsonl(out/'results.jsonl')
            assert len(rs)==32 and all(not check_complete_consistency(r) for r in rs)
            by_id={r.game_key.game_id:r for r in rs};assert len(by_id)==32
            for r in rs:
                assert r.scenario_id in bp['root_ids'] and r.status=='complete' and r.expected_hands==r.completed_hands==8
                assert all(getattr(r.runtime_counts,k)==0 for k in ['timeouts','illegal_choices','fallbacks','auto_actions','audit_missing'])
                seat=r.seat_permutation[0];a='C' if r.policy_ids_by_seat[seat]==cid else 'A'
                if a=='A':
                    assert r.policy_ids_by_seat[seat].startswith('research-r18-v2:');baseline_ids.add(r.policy_ids_by_seat[seat])
                key=(r.scenario_id,r.seat_permutation);assert a not in pairs[v][key]
                pairs[v][key][a]=r.scores_after[seat]-r.scores_before[seat]
                table_sums[v][a]+=pairs[v][key][a]
            audits=[]
            for root_id in bp['root_ids']:
                subset=[r for r in rs if r.scenario_id==root_id]
                baseline=next(r.policy_ids_by_seat[r.seat_permutation[0]] for r in subset if r.policy_ids_by_seat[r.seat_permutation[0]]!=cid)
                audit=audit_vip_batch([FrozenRoot(root_id,PERMUTATIONS,('all_natural',)*4,(0.,)*4)],
                    {'all_natural':1.},subset,baseline_policy_id=baseline,challenger_policy_id=cid)
                assert audit.confirmable;audits.append(asdict(audit))
            assert helper.canonical(audits)==helper.canonical(summary['root_audits'])
            totals=defaultdict(int)
            for row in helper.rows(out/'settlements.jsonl.gz'):
                r=by_id[row['match_id']];s=row['settlement'];seat=r.seat_permutation[0]
                key=(v,row['match_id'],row['round_no']);assert key not in seen_hands;seen_hands.add(key)
                assert row['evidence']=='public_export_hand_settlement' and row['focal_physical_seat']==seat
                assert sum(s['score_delta'])==0 and [b+d for b,d in zip(s['scores_before'],s['score_delta'])]==s['scores_after']
                a='C' if r.policy_ids_by_seat[seat]==cid else 'A'
                if s['is_draw']:k='draw'
                elif s['winner_seat']!=seat:k='opponent_hu'
                else:
                    fan=s['fan'];assert type(fan) is int and fan>0
                    k='own_lt4' if fan<4 else 'own_4_to7' if fan<8 else 'own_8_to15' if fan<16 else 'own_ge16'
                    if fan>=4:root_highfan[v][a][r.scenario_id]+=s['score_delta'][seat]
                realized[v][a][k]['hands']+=1;realized[v][a][k]['score']+=s['score_delta'][seat]
                totals[row['match_id']]+=s['score_delta'][seat]
                settlements_by_match[v][row['match_id']].append(row)
            assert all(totals[r.game_key.game_id]==r.scores_after[r.seat_permutation[0]]-r.scores_before[r.seat_permutation[0]] for r in rs)
            for path in out.glob('group-*.json.gz'):
                with gzip.open(path,'rt') as f:g=json.load(f)
                assert len(g['match_records'])==2
                for record in g['match_records']:
                    mid=record['match_id'];assert mid in by_id and mid not in outcomes[v]
                    o=record['outcome'];assert o['status']=='complete' and o['completed_hands']==8
                    assert o['final_scores']==list(by_id[mid].scores_after)
                    outcomes[v][mid]=o
        assert len(baseline_ids)==1
        baseline_id=next(iter(baseline_ids))
        for mid,o in outcomes['T101'].items():
            if mid.endswith(':'+baseline_id):
                # logical模式原始Outcome不含实测compute时长；完整对象必须精确一致。
                assert helper.canonical(o)==helper.canonical(outcomes['T97'][mid])
                assert helper.canonical(settlements_by_match['T101'][mid])==helper.canonical(settlements_by_match['T97'][mid])
                duplicate_tables+=1
        assert duplicate_tables==64 and len(outcomes['T101'])==len(outcomes['T97'])==128
        assert len(seen_hands)==2048
        assert all(c['cost_record_present'] and c['actual_started_unknown_entries']==0 for c in costs)
        assert sum(c['actual_started_known_subtotal'] for c in costs)==sum(c['charged_instances'] for c in costs)==256
        assert all(len(pairs[v])==64 and all(set(x)=={'A','C'} for x in pairs[v].values()) for v in pairs)
        for v in ['T101','T97']:
            for a in ['A','C']:
                assert sum(x['hands'] for x in realized[v][a].values())==512
                assert sum(x['score'] for x in realized[v][a].values())==table_sums[v][a]
        deltas={}
        for v in ['T101','T97']:
            deltas[v+'_minus_R18']=[statistics.mean(pairs[v][(root,p)]['C']-pairs[v][(root,p)]['A'] for p in PERMUTATIONS) for root in plan['root_ids']]
        deltas['T101_minus_T97']=[statistics.mean(pairs['T101'][(root,p)]['C']-pairs['T97'][(root,p)]['C'] for p in PERMUTATIONS) for root in plan['root_ids']]
        descriptive={k:{'root_mean_deltas':vals,'net_per_table':statistics.mean(vals),
            'mother_root_cluster_95':helper.bootstrap(vals,plan['confidence']),
            'positive_roots':sum(x>0 for x in vals),'negative_roots':sum(x<0 for x in vals),'tied_roots':sum(x==0 for x in vals)} for k,vals in deltas.items()}
        assert descriptive['T101_minus_T97']['net_per_table']==descriptive['T101_minus_R18']['net_per_table']-descriptive['T97_minus_R18']['net_per_table']
    except Exception as exc:
        issues.append(type(exc).__name__+': '+str(exc));descriptive=None
    highfan_deltas={}
    if not issues:
        for label,v,a in [('T101_minus_R18','T101','A'),('T101_minus_T97','T97','C')]:
            ds={root:root_highfan['T101']['C'][root]-root_highfan[v][a][root] for root in plan['root_ids']}
            highfan_deltas[label]={'root_actual_highfan_score_deltas':ds,'total_delta':sum(ds.values()),'positive_roots':sum(x>0 for x in ds.values())}
    screen=not issues and all(descriptive[k]['net_per_table']>0 and highfan_deltas[k]['total_delta']>0 and highfan_deltas[k]['positive_roots']>=2 for k in ['T101_minus_R18','T101_minus_T97'])
    result={'schema':'t102-whole-three-formula-pilot-result/1','whole_batch_valid':not issues,'issues':issues,
        'planned_actual_tables':256,'observed_actual_tables':sum(c['actual_started_known_subtotal'] for c in costs),
        'observed_hands_in_readback':len(seen_hands),'independent_roots':16,'duplicate_R18_tables_verified':duplicate_tables,
        'actual_costs_by_block':costs,'source_input_audits':input_audits,'descriptive_comparisons':descriptive,
        'realized_mutually_exclusive_bands':realized,'realized_table_net_totals':{v:dict(x) for v,x in table_sums.items()},
        'highfan_deltas':highfan_deltas,'predeclared_confirmation_start_screen_passed':screen,
        'confirmation_claim':False,'published':False,'normal_R18_fallbacks':0 if not issues else None,
        'new_models_scores_rules_worlds_tables_in_readback':0,
        'scope':'sixteen new development roots; no confidence-based admission/top3/deadline claim; confirmation roots still reserved'}
    save('CAMPAIGN-CLOSURE.json',result)
    print({k:result[k] for k in ['whole_batch_valid','issues','descriptive_comparisons','predeclared_confirmation_start_screen_passed']},flush=True)
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
