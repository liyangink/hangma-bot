"""四个真实进程全终态后，纯读核验完整输入、1024桌和真实积分分账。

终态文件必须由工具实际返回填写，不能凭summary/锁文件推定进程已结束。
本工具不重评分、不读取或创建WorldState，不准入或发布候选。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t112-fixed-t110-s02-fresh-confirmation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import gzip
import hashlib
import json
import math
import random
import statistics

from hangma_bot.offline.evaluation_results import read_results_jsonl, check_complete_consistency
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_evaluation import FrozenRoot, audit_vip_batch

HERE = Path(__file__).resolve().parent
PERMUTATIONS = ((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2))
BANDS = ('own_lt4','own_4_to7','own_8_to15','own_ge16','opponent_hu','draw')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    """流式文件摘要，不覆盖大原件或把纯读计入评分费用。"""
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    """完整压缩日志逐条解码；不允许截断日志冒充完整输入。"""
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def audit_actual_inputs(out, summary, plan):
    """核验真实调用收据和已保存DTO；单位为实际调用/动作分值，不是独立牌山。"""
    candidate_id = 'vip:'+plan['candidate_identity']['candidate_id']
    archive = {}
    for row in rows(out/'views.jsonl.gz'):
        raw = canonical(row['view'])
        digest = row['view_sha256']
        assert hashlib.sha256(raw).hexdigest() == digest and len(raw) == row['json_bytes']
        assert digest not in archive
        keys = [a['action_key'] for a in row['view']['actions']]
        assert keys and len(keys) == len(set(keys))
        archive[digest] = (len(raw), set(keys))
    calls, used, selected, whites = set(), set(), Counter(), Counter()
    decisions = C_decisions = action_scores = max_operations = 0
    phase_ms = defaultdict(list)
    for row in rows(out/'decisions.jsonl.gz'):
        decisions += 1
        assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
        if row['policy_id'] != candidate_id:
            continue
        C_decisions += 1
        assert row['c_self_scored'] and row['scoring_cumulative_failed_calls'] == 0
        assert not row['degraded_reasons']
        selected[row['selected_action_key'].split(':',1)[0]] += 1
        whites[row['white_count']] += 1
        phase_ms[row['phase']].append(row['policy_compute_ms_observed'])
        keys = [c['action_key'] for c in row['candidates']]
        assert len(keys) == len(set(keys)) and set(keys) == set(row['legal_action_keys'])
        assert row['candidates'][0]['action_key'] == row['selected_action_key']
        assert all(type(c['score']) in (int,float) and math.isfinite(c['score']) for c in row['candidates'])
        action_scores += len(keys)
        assert row['scoring_calls']
        for call in row['scoring_calls']:
            receipt = call['input_capture']
            assert call['status'] == 'SCORED' and call['score_completed'] and call['full_legal_keys']
            assert call['actual_score_calls'] == 1 and call['cumulative_failed_calls'] == 0
            assert receipt['saved_before_score'] and receipt['error'] is None
            seq, digest = receipt['store_call_no'], receipt['view_sha256']
            assert seq not in calls and digest in archive
            calls.add(seq); used.add(digest)
            assert archive[digest][0] == receipt['json_bytes']
            assert archive[digest][1] == set(call['scored_action_keys']) == set(keys)
            ops = call['candidate_operations']
            assert type(ops) is int and 0 <= ops <= plan['offline_max_operations']
            max_operations = max(max_operations, ops)
    capture = summary['scoring_input_capture']
    terminal = capture['terminal']
    assert terminal['terminal_valid'] and terminal['closed'] and terminal['verified']
    assert sha(out/'views.jsonl.gz') == terminal['compressed_sha256']
    assert len(archive) == terminal['verified_unique_views'] and used == set(archive)
    assert calls == set(range(1,capture['store_calls']+1))
    assert decisions == summary['decision_windows']
    distributions = {}
    for phase, values in phase_ms.items():
        values.sort()
        distributions[phase] = {'n':len(values),'p50_ms':values[(len(values)-1)//2],
            'p95_ms':values[math.ceil(len(values)*.95)-1], 'max_ms':values[-1]}
    return {'all_seat_decisions':decisions,'candidate_decisions':C_decisions,'actual_score_calls':len(calls),
        'finite_legal_action_score_outputs':action_scores,'unique_complete_views':len(archive),
        'max_candidate_operations':max_operations,'white_counts_at_C_decisions':dict(whites),
        'selected_action_counts':dict(selected),'choose_with_capture_ms_by_phase':distributions,
        'timing_scope':'offline choose plus capture; excludes rules/worker/network/SSE; not online deadline credit'}


def bootstrap(root_means, confidence):
    """母牌山成组抽样：每次保留组内四座，返回预登记95%经验分位。"""
    rng = random.Random(confidence['seed'])
    n = len(root_means)
    values = sorted(statistics.mean(rng.choices(root_means,k=n)) for _ in range(confidence['resamples']))
    tail = (1-confidence['interval'])/2
    # 延续T77的经验顺序统计量：20000次95%区间取索引500和19499。
    lo = round(len(values)*tail)
    hi = len(values)-lo-1
    return [values[lo],values[hi]]


def main():
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')).read_text())
    handles = json.loads((_project_file(_PROJECT_ROOT, HERE/'PROCESS-HANDLES.json')).read_text())['processes']
    terminal_paths = [_project_file(_PROJECT_ROOT, HERE/f'BLOCK-{i:02d}-TERMINAL.json') for i in range(1,5)]
    if not all(p.exists() for p in terminal_paths):
        print({'status':'pending_tool_terminal_records','outcomes_read':False})
        raise SystemExit(2)
    terminals = [json.loads(p.read_text()) for p in terminal_paths]
    for terminal, handle in zip(terminals,handles):
        assert terminal['block'] == handle['block'] and terminal['session_id'] == handle['session_id']
        assert type(terminal['exit_code']) is int and terminal['verified_tool_terminal'] is True
    # 先逐块记实际成本。失败批不能因最早的断言而把已尝试费用写成0。
    costs = []
    for i in range(1,5):
        path = _project_file(_PROJECT_ROOT, HERE/f'block-{i:02d}/costs.json')
        value = json.loads(path.read_text()) if path.exists() else None
        entries = value['entries'] if value else []
        costs.append({'block':i,'cost_record_present':value is not None,
            'charged_instances_known':sum(e['charged_table_instances'] for e in entries),
            'actual_started_known_subtotal':sum(e['actual_started_table_instances'] or 0 for e in entries),
            'actual_started_unknown_entries':sum(e['actual_started_table_instances'] is None for e in entries),
            'completed_pairs':sum(e['status']=='settled' for e in entries),
            'failed_pairs':sum(e['status']=='failed_cost_retained' for e in entries)})
    issues, pairs, seen_hands = [], defaultdict(dict), set()
    table_sums, hand_totals = defaultdict(int), defaultdict(int)
    realized = {a:{k:{'hands':0,'score':0} for k in BANDS} for a in ('A','C')}
    root_highfan, source_inputs = {a:set() for a in ('A','C')}, []
    candidate_id = 'vip:'+plan['candidate_identity']['candidate_id']
    mean = interval = root_means = None
    try:
        assert all(t['exit_code'] == 0 for t in terminals), 'nonzero process exit'
        assert not (_project_file(_PROJECT_ROOT, HERE/'GLOBAL-ENGINEERING-FAILURE.json')).exists(), 'global engineering failure'
        for name,digest in plan['prerequisite_sha256'].items():
            assert sha(Path(name)) == digest, name
        for i in range(1,5):
            out = _project_file(_PROJECT_ROOT, HERE/f'block-{i:02d}')
            summary = json.loads((out/'summary.json').read_text())
            block_plan = json.loads((_project_file(_PROJECT_ROOT, HERE/f'BLOCK-{i:02d}-PLAN.json')).read_text())
            assert summary['block_complete'] and summary['identity_stable'] and not summary['issues']
            assert summary['candidate_identity'] == plan['candidate_identity']
            assert summary['observed_result_rows'] == summary['actual_started_table_instances'] == 256
            assert summary['charged_table_instances'] == 256 and summary['completed_hands'] == 2048
            freeze = json.loads((out/'end-freeze.json').read_text())
            assert freeze['source_stable']
            for path,digest in freeze['frozen_files'].items():
                assert sha(Path(path)) == digest, path
            for relative,digest in freeze['source_manifest'].items():
                actual, copied = _project_file(_PROJECT_ROOT, REPO_ROOT/relative), out/'code_snapshot'/relative
                assert actual.stat().st_size == copied.stat().st_size == digest['bytes']
                assert sha(actual) == sha(copied) == digest['sha256'], relative
            assert sha(out/'RUNNER.py') == sha(_project_file(_PROJECT_ROOT, HERE/'run_block.py'))
            source_inputs.append(dict(block=i,**audit_actual_inputs(out,summary,plan)))
            results = read_results_jsonl(out/'results.jsonl')
            assert len(results) == 256 and all(not check_complete_consistency(r) for r in results)
            by_id = {r.game_key.game_id:r for r in results}
            assert len(by_id) == 256
            for result in results:
                assert result.scenario_id in block_plan['root_ids']
                assert result.status == 'complete' and result.expected_hands == result.completed_hands == 8
                assert all(getattr(result.runtime_counts,k) == 0 for k in
                    ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing'))
                seat = result.seat_permutation[0]
                arm = 'C' if result.policy_ids_by_seat[seat] == candidate_id else 'A'
                assert arm == 'C' or result.policy_ids_by_seat[seat].startswith('research-r18-v2:')
                key = (result.scenario_id,result.seat_permutation)
                assert arm not in pairs[key]
                pairs[key][arm] = result.scores_after[seat]-result.scores_before[seat]
                table_sums[arm] += pairs[key][arm]
            audits = []
            for root_id in block_plan['root_ids']:
                subset = [r for r in results if r.scenario_id == root_id]
                baselines = {r.policy_ids_by_seat[r.seat_permutation[0]] for r in subset
                    if r.policy_ids_by_seat[r.seat_permutation[0]] != candidate_id}
                assert len(baselines) == 1
                audit = audit_vip_batch([FrozenRoot(root_id,PERMUTATIONS,('all_natural',)*4,(0.,)*4)],
                    {'all_natural':1.},subset,baseline_policy_id=next(iter(baselines)),challenger_policy_id=candidate_id)
                assert audit.confirmable
                audits.append(asdict(audit))
            assert canonical(audits) == canonical(summary['root_audits'])
            for row in rows(out/'settlements.jsonl.gz'):
                result = by_id[row['match_id']]
                key = (row['match_id'],row['round_no'])
                assert key not in seen_hands
                seen_hands.add(key)
                seat = result.seat_permutation[0]
                arm = 'C' if result.policy_ids_by_seat[seat] == candidate_id else 'A'
                s = row['settlement']
                assert row['evidence'] == 'public_export_hand_settlement' and row['focal_physical_seat'] == seat
                delta = s['score_delta']
                assert sum(delta) == 0 and [b+d for b,d in zip(s['scores_before'],delta)] == s['scores_after']
                if s['is_draw']:
                    kind = 'draw'
                elif s['winner_seat'] != seat:
                    kind = 'opponent_hu'
                else:
                    fan = s['fan']
                    assert type(fan) is int and fan > 0
                    kind = 'own_lt4' if fan<4 else 'own_4_to7' if fan<8 else 'own_8_to15' if fan<16 else 'own_ge16'
                    if fan>=4:
                        root_highfan[arm].add(row['root_id'])
                realized[arm][kind]['hands'] += 1
                realized[arm][kind]['score'] += delta[seat]
                hand_totals[row['match_id']] += delta[seat]
            assert all(hand_totals[r.game_key.game_id] == r.scores_after[r.seat_permutation[0]]-r.scores_before[r.seat_permutation[0]]
                for r in results)
        assert all(c['cost_record_present'] and c['actual_started_unknown_entries'] == 0 for c in costs)
        assert sum(c['actual_started_known_subtotal'] for c in costs) == sum(c['charged_instances_known'] for c in costs) == 1024
        assert len(seen_hands) == plan['planned_hands'] == 8192
        assert len(pairs) == plan['paired_tables'] == 512 and all(set(v)=={'A','C'} for v in pairs.values())
        root_means = [statistics.mean(pairs[(root,p)]['C']-pairs[(root,p)]['A'] for p in PERMUTATIONS)
                      for root in plan['root_ids']]
        assert len(root_means) == 128
        for arm in ('A','C'):
            assert sum(v['hands'] for v in realized[arm].values()) == 4096
            assert sum(v['score'] for v in realized[arm].values()) == table_sums[arm]
        mean = statistics.mean(root_means)
        assert mean == (table_sums['C']-table_sums['A'])/512
        interval = bootstrap(root_means,plan['confidence'])
    except Exception as exc:
        issues.append(type(exc).__name__+': '+str(exc))
        mean = interval = root_means = None
    result = {'schema':'t112-whole-fresh-natural-confirmation-result/1','whole_batch_valid':not issues,'issues':issues,
        'planned_actual_tables':1024,'planned_hands':8192,'planned_independent_roots':128,
        'actual_costs_by_block':costs,'observed_hands_in_this_readback':len(seen_hands),
        'candidate_identity':plan['candidate_identity'],'root_mean_deltas':root_means,
        'net_score_delta_per_table':mean,'root_cluster_percentile_95':interval,
        'source_input_audits':source_inputs,'realized_net_by_arm':dict(table_sums),
        'realized_mutually_exclusive_bands':realized,
        'highfan_root_clusters':{a:sorted(v) for a,v in root_highfan.items()},
        'net_positive_interval':not issues and interval[0]>0,
        'scope':'current fixed execution identity, fresh128-root qualifier scenario; no automatic admission/top3/deadline/publication',
        'confirmation_claim':False,'published':False,'new_models_scores_worlds_tables_in_readback':0}
    with (_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-CLOSURE.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
    print({k:result[k] for k in ('whole_batch_valid','issues','net_score_delta_per_table','root_cluster_percentile_95')})
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
