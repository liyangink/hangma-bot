"""T165 已闭合实战的只读分账；不重新评分、不发 HTTP、不启动新房。

完整桌赛为统计单位，四视角先去重。四番以上/普通胡/他家胡支付互斥；
工程缺陷保留原记录与受影响桌号。官方隐藏初始牌只作赛后诊断，绝不进入策略。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t165-live-watchdog-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter, defaultdict
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
HELPER = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t163-received-fix-fast-four-seat-testroom-1/summarize_closed.py')


def load(path):
    """读取本批指定 JSON 原文。"""
    return json.loads(path.read_text())


def save(path, value, *, replace=False):
    """原始批次摘要独占写；累计摘要可原子替换。"""
    if replace:
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        temporary.replace(path)
    else:
        with path.open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')


def official_tables(session):
    """按 game_id 去重官方成功下载并验原文字节；冲突不能任选一份。"""
    tables, hashes = {}, {}
    for path in sorted(session.glob('official/dl-*/events.json')):
        if not (path.parent / 'source.json').is_file() or (path.parent / 'download-error.json').exists():
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        source, doc = load(path.parent / 'source.json'), json.loads(raw)
        assert source['original_sha256'] == digest
        assert doc['status'] == 'finished' and source['game_id'] == doc['game_id']
        game = doc['game_id']
        if game in tables:
            assert hashes[game] == digest, '同桌官方原文冲突'
            continue
        tables[game], hashes[game] = doc, digest
    assert len(tables) == 10
    return tables, hashes


def complete_rounds(doc, endings_by_round):
    """以官方结束事件计完整单局；汇总省略流局时明确来源，不补造倍率。

    官方自由赛的 rounds 可以只列胡成单局，blocks 仍保留流局结束事件。
    非流局缺少汇总、重复编号或汇总与事件不一致均拒绝统计。
    """
    assert set(endings_by_round) == set(range(1, 9)), '必须有编号1..8的八个官方结束事件'
    summaries = {row['round_no']: row for row in doc['rounds']}
    assert len(summaries) == len(doc['rounds']), '官方单局汇总编号重复'
    assert set(summaries) <= set(endings_by_round)
    complete = []
    for number in range(1, 9):
        ended = endings_by_round[number]
        data = ended['data']
        draw = data['draw']
        assert type(draw) is bool
        # 流局没有番数，保留 None；不能将缺失倍率杜撰成平胡或零番。
        row = {'round_no': number, 'dealer': data['dealer'], 'winner': ended['seat'],
               'is_draw': draw, 'scores': data['scores'], 'multiplier': data.get('fan'),
               'source': 'official_round_ended', 'round_ended_seq': ended['seq'],
               'summary_array_status': 'present' if number in summaries else 'omitted_draw'}
        assert len(row['scores']) == 4 and sum(row['scores']) == 0
        if number in summaries:
            summary = summaries[number]
            for key in ('round_no', 'dealer', 'winner', 'is_draw', 'scores'):
                assert summary[key] == row[key], '官方汇总与结束事件不一致：' + key
            if not draw:
                assert summary['multiplier'] == row['multiplier']
        else:
            assert draw, '非流局缺官方单局汇总，不能仅凭事件补造'
        if not draw:
            assert type(row['multiplier']) is int and row['multiplier'] > 0
        complete.append(row)
    return complete


def end_records(logfile, lane):
    """读取现有运行器打印的真实终态；非原始 RESULT 的格式标清来源。"""
    import re
    lines, terminal = [], None
    for line in logfile.read_text().splitlines():
        if lane == 'free' and line.startswith('RESULT '):
            lines.append(json.loads(line[len('RESULT '):]))
        if lane == 'mixed':
            match = re.match(r'\[([^]]+)\] (\w+) \| 终态: ([^|]+)\| .*exit=(-?\d+)$', line)
            if match:
                terminal = {'slot': match[1], 'outcome': match[2], 'terminal_reason': match[3].strip(),
                            'exit_code': int(match[4]), 'origin': 'run_test_room报告转换，不是原始RESULT报文'}
                lines.append(terminal)
            elif terminal is not None and line.strip().startswith('run_id:'):
                terminal['run_id'] = line.split(':', 1)[1].strip()
            elif terminal is not None and '计算服务退出:' in line:
                terminal['decision_compute'] = json.loads(line[line.index('{'):])
    assert len(lines) == (1 if lane == 'free' else 4)
    return lines


def analyze_lane(cycle, plan, lane):
    """验关闭审计及官方结算，再作座位归因、互斥分账和污染标记。"""
    assert load(cycle / (lane.upper() + '-CHILD-TERMINAL.json'))['actual_exit_code'] == 0
    assert load(cycle / (lane.upper() + '-POSTGAME-TERMINAL.json'))['actual_exit_code'] == 0
    session = _project_file(_PROJECT_ROOT, ROOT / plan[lane + '_session'])
    spec = importlib.util.spec_from_file_location('t165_readonly_audit', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = session
    runs = sorted(session.glob('audit/runs/*')) if lane == 'free' else sorted(session.glob('audit/slot-*/runs/*'))
    assert len(runs) == (1 if lane == 'free' else 4)
    sources = {}
    audit = [module.audit_run(run, sources) for run in runs]
    terminals = end_records(cycle / (lane.upper() + '-STDOUT-STDERR.log'), lane)
    assert {r.name for r in runs} == {t['run_id'] for t in terminals}
    tables, hashes = official_tables(session)
    if lane == 'free':
        owners = [p.name for p in (runs[0] / 'participants').glob('u_*') if p.is_dir()]
        assert len(owners) == 1
        mapping = {owners[0]: {'arm': 'T110', 'slot': 'free'}}
    else:
        mapping = plan['owner_map'] if 'owner_map' in plan else load(cycle / 'OWNER-MAP.json')
        assert Counter(row['arm'] for row in mapping.values()) == {'T110': 2, 'R18': 2}
    contaminated = defaultdict(list)
    warnings = defaultdict(list)
    for result in audit:
        for failed in result['failed_plans']:
            game = failed['context']['game_id']
            row = {'kind': 'missing_full_score', 'run_id': result['run_id'], 'detail': failed}
            if failed['input']['legal'] == ['pass']:
                warnings[game].append(row)
            else:
                contaminated[game].append(row)
        for failure in result['policy_errors']:
            contaminated[failure['context']['game_id']].append({'kind': 'policy_exception', 'detail': failure})
    # 零规划无精确当时输入，因此不以最近快照冒充完整候选；先单列待复查。
    zeros = []
    for run in runs:
        for path in run.glob('participants/*/games/*.jsonl'):
            for no, line in enumerate(path.open(), 1):
                rec = json.loads(line)
                if (rec['kind'] == 'http_request' and rec['payload'].get('phase') == 'finished'
                        and rec['payload'].get('http_status') == 429
                        and '/api/games/' in rec['payload'].get('endpoint', '')):
                    contaminated[rec['context']['game_id']].append({'kind': 'game_http_429',
                        'source': str(path.relative_to(session)), 'line': no, 'payload': rec['payload']})
                if rec['kind'] == 'protocol_recovered' and any('零动作尝试' in x for x in rec['payload'].get('reasons', [])):
                    row = {'kind': 'zero_attempt_window_unclassified', 'source': str(path.relative_to(session)),
                           'line': no, 'context': rec['context'], 'payload': rec['payload']}
                    zeros.append(row)
                    warnings[rec['context']['game_id']].append(row)
    scores, wins, ranks, dealer, opportunity = (defaultdict(Counter) for _ in range(5))
    totals, hands, unique_events = [], [], Counter()
    round_summary_coverage = {}
    game_429 = sum(a['http_categories'].get(category, {}).get('429', 0) for a in audit for category in ('state', 'action'))
    for gid, doc in sorted(tables.items()):
        seat_rows = {i: mapping[p['user_id']] for i, p in enumerate(doc['seats']) if p['user_id'] in mapping}
        events = {}
        for block in doc['blocks']:
            for event in block['events']:
                if event['seq'] in events:
                    assert events[event['seq']] == event
                events[event['seq']] = event
        endings = [e for e in events.values() if e['type'] == 'round_ended']
        endings_by_round = {e['data']['round_no']: e for e in endings}
        assert len(endings_by_round) == len(endings), '结束事件存在重复单局编号'
        round_rows = complete_rounds(doc, endings_by_round)
        round_summary_coverage[gid] = {'official_endings': len(round_rows),
            'summary_array_entries': len(doc['rounds']),
            'omitted_draw_rounds': [r['round_no'] for r in round_rows if r['summary_array_status'] == 'omitted_draw']}
        finals = [e['data']['final_scores'] for e in events.values() if e['type'] == 'game_ended']
        assert len(finals) == 1
        actual = [sum(e['data']['scores'][seat] for e in endings) for seat in range(4)]
        assert actual == finals[0] and sum(actual) == 0
        for event in events.values():
            unique_events[event['type']] += 1
            if event['type'] == 'timeout' and event.get('data', {}).get('kind') == 'discard' and event['seat'] in seat_rows:
                contaminated[gid].append({'kind': 'official_discard_timeout', 'event': event})
        arm_table = Counter()
        for seat, owner in seat_rows.items():
            arm = owner['arm']
            rank = 1 + sum(n > actual[seat] for n in actual)
            ranks[arm][str(rank)] += 1
            arm_table[arm] += actual[seat]
        total = {'game_id': gid, 'seat_arm_map': seat_rows, 'scores_seat_order_0_3': actual,
                 'arm_team_scores': dict(arm_table)}
        if lane == 'mixed':
            total['T110_minus_R18_score_per_seat'] = (arm_table['T110'] - arm_table['R18']) / 2
        totals.append(total)
        for summary in round_rows:
            number = summary['round_no']
            ended = endings_by_round[number]
            assert ended['data']['scores'] == summary['scores']
            blocks = [b for b in doc['blocks'] if b['round_no'] == number]
            assert blocks
            block = blocks[0]
            detail = ended['data'].get('detail', [])
            for seat, owner in seat_rows.items():
                arm, value = owner['arm'], summary['scores'][seat]
                won = not summary['is_draw'] and summary['winner'] == seat
                # 三项覆盖全部整数积分；抽牌不擅自假定0，放到显式残余。
                account = ('high_fan_hu_income' if won and summary['multiplier'] >= 4 else
                           'ordinary_hu_income' if won else 'payment_when_other_hu' if not summary['is_draw'] else 'draw_residual')
                scores[arm][account] += value
                scores[arm]['total_score'] += value
                scores[arm]['seat_hand_observations'] += 1
                if won:
                    wins[arm][str(summary['multiplier'])] += 1
                role = 'dealer' if summary['dealer'] == seat else 'non_dealer'
                dealer[arm][role + '_score'] += value
                dealer[arm][role + '_seat_hands'] += 1
                initial = block.get('start_hands', [])
                white = initial[seat].count('白') if len(initial) == 4 else None
                if white is not None and white >= 2:
                    opportunity[arm]['initial_two_or_more_white_seat_hands'] += 1
                    opportunity[arm]['wins'] += int(won)
                    opportunity[arm]['high_fan_wins'] += int(won and summary['multiplier'] >= 4)
                    opportunity[arm]['score'] += value
                hands.append({'game_id': gid, 'round_no': number, 'seat': seat, 'arm': arm,
                    'dealer': summary['dealer'], 'winner': summary['winner'], 'draw': bool(summary['is_draw']),
                    'official_multiplier': summary['multiplier'], 'our_score': value, 'account': account,
                    'initial_white_count_retrospective_only': white, 'official_detail': detail,
                    'settlement_source': summary['source'], 'round_ended_seq': summary['round_ended_seq'],
                    'summary_array_status': summary['summary_array_status'],
                    'source_sha256': hashes[gid]})
    for arm, account in scores.items():
        assert sum(account[k] for k in ('high_fan_hu_income', 'ordinary_hu_income', 'payment_when_other_hu', 'draw_residual')) == account['total_score']
    latest = load(session / 'latest-postgame.json')
    report = load(session / latest['job'] / 'report.json')
    assert report['official_documents'] == 10
    assert report['audit_complete'] is True and report['bundle_verified'] is True, '赛后封存未完整核验，不授闭合'
    checks = report['official_rule_checks']
    assert {c['game_id']: c['source_sha256'] for c in checks} == hashes
    # postgame 已验证整个封存包；额外精确核对本次统计使用的官方事件在包中同字节。
    job = session / latest['job']
    bundle = job / report['bundle']
    bundle_manifest = load(bundle / 'bundle.json')
    bundle_files = {row['path']: row for row in bundle_manifest['files']}
    bundle_official_sources = {}
    for gid, digest in hashes.items():
        relative = 'official/' + digest + '/events.json'
        entry = bundle_files[relative]
        raw = (bundle / relative).read_bytes()
        assert entry['sha256'] == digest == hashlib.sha256(raw).hexdigest()
        assert entry['bytes'] == len(raw)
        bundle_official_sources[gid] = {'path': relative, 'sha256': digest, 'bytes': len(raw)}
    conflicts = [x for check in checks for x in check.get('origin_conflicts', [])]
    assert not conflicts and all(c.get('final_scores_match') is True for c in checks)
    computed = [t['decision_compute'] for t in terminals if 'decision_compute' in t]
    result = {'lane': lane, 'room_ids': sorted({d['room_id'] for d in tables.values()}), 'unique_tables': 10, 'unique_hands': 80,
        'seat_hand_observations': len(hands), 'tables': totals, 'hands': hands,
        'mutually_exclusive_accounts': dict(scores), 'wins_by_multiplier': dict(wins), 'ranks_ties_shared': dict(ranks),
        'dealer_strata': dict(dealer), 'initial_white_opportunity_strata': dict(opportunity),
        'audit': audit, 'terminals': terminals, 'zero_attempt_windows_unclassified': zeros,
        'engineering_contaminated_tables': dict(contaminated), 'engineering_warning_tables': dict(warnings),
        'game_request_429': game_429, 'compute_faults': sum(c['faults'] for c in computed),
        'compute_restarts': sum(c['restarts'] for c in computed),
        'rule_statuses': dict(Counter(r['status'] for c in checks for r in c.get('rounds', []))),
        'rule_summary_comparison_statuses': dict(Counter(r['status'] for c in checks for r in c.get('summary_comparisons', []))),
        'rule_issue_codes': dict(Counter(i['code'] for c in checks for r in c.get('rounds', []) for i in r.get('issues', []))),
        'dataset_validation_original': report['dataset_summary']['validation'],
        'round_summary_coverage': round_summary_coverage,
        'postgame_bundle_manifest_sha256': hashlib.sha256((bundle / 'bundle.json').read_bytes()).hexdigest(),
        'postgame_official_sources_verified': bundle_official_sources,
        'postgame_audit_complete': report['audit_complete'], 'postgame_bundle_verified': report['bundle_verified'],
        'official_unique_events': dict(unique_events), 'official_source_sha256': hashes, 'audit_source_sha256': sources,
        'audit_counter_helper_sha256': hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        'interpretation': '两臂同桌有交互且牌山没有反事实换座；结果是实战诊断。初始白板为赛后事实，不输入策略。零规划先保留未知，不补造候选。',
        'strength_admission': False, 'formal_release': False}
    return result


def aggregate():
    """从已分析完整批次去重累加；不把一房四席视角变成四倍样本。"""
    seen, lanes, cycles = set(), defaultdict(lambda: {'tables': 0, 'hands': 0, 'scores': Counter(),
        'accounts': defaultdict(Counter), 'wins': defaultdict(Counter), 'ranks': defaultdict(Counter),
        'engineering_contaminated_tables': 0, 'engineering_warning_tables': 0,
        'game_request_429': 0, 'compute_faults': 0, 'compute_restarts': 0}), []
    for path in sorted(HERE.glob('cycle-*/SUMMARY.json')):
        summary = load(path)
        cycles.append(summary['cycle'])
        for lane, row in summary['lanes'].items():
            ids = {t['game_id'] for t in row['tables']}
            assert not ids & seen, '累计发现重复桌赛，拒绝双计'
            seen.update(ids)
            lanes[lane]['tables'] += row['unique_tables']
            lanes[lane]['hands'] += row['unique_hands']
            for arm, account in row['mutually_exclusive_accounts'].items():
                lanes[lane]['scores'][arm] += account['total_score']
                lanes[lane]['accounts'][arm].update(account)
            for arm, wins in row['wins_by_multiplier'].items():
                lanes[lane]['wins'][arm].update(wins)
            for arm, ranks in row['ranks_ties_shared'].items():
                lanes[lane]['ranks'][arm].update(ranks)
            for category in ('game_request_429', 'compute_faults', 'compute_restarts'):
                lanes[lane][category] += row[category]
            for category in ('engineering_contaminated_tables', 'engineering_warning_tables'):
                lanes[lane][category] += len(row[category])
    return {'completed_cycles': cycles, 'lanes': dict(lanes), 'checkpoints': [5, 10, 20],
            'strength_admission': False, 'formal_release': False,
            'interpretation': '累计规模是唯一完整桌与单局；实时查看不是重复独立检验，不追加到显著。'}


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--cycle', type=Path, required=True)
    cycle = args.parse_args().cycle.resolve()
    assert cycle.parent == HERE
    plan = load(cycle / 'PLAN.json')
    result = {'cycle': plan['cycle'], 'identity': plan['identity'], 'lanes': {}, 'strength_admission': False, 'formal_release': False}
    for lane in ('free', 'mixed'):
        result['lanes'][lane] = analyze_lane(cycle, plan, lane)
    save(cycle / 'SUMMARY.json', result)
    save(_project_file(_PROJECT_ROOT, HERE / 'CUMULATIVE.json'), aggregate(), replace=True)
    print(json.dumps({k: v for k, v in aggregate().items() if k != 'interpretation'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
