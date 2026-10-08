"""按真实结算重读大牌增益来源；只读已闭证据，不评分、不推进世界。"""

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
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import gzip
from pathlib import Path

HERE = Path(__file__).resolve().parent
BANDS = ('draw', 'opponent_hu', 'own_lt4', 'own_4_to7', 'own_8_to15', 'own_ge16')


def main():
    """用完整桌的焦点策略身份划分两臂，逐来源计算真实大牌收入净差。"""
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-CLOSURE.json')).read_text())
    terminal = json.loads((_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-READBACK-TERMINAL.json')).read_text())
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-PLAN.json')).read_text())
    assert terminal['verified_tool_terminal'] and terminal['exit_code'] == 0
    assert closed['whole_batch_valid'] and not closed['issues']
    candidate_id = 'vip:' + closed['candidate_identity']['candidate_id']
    roots = {root: {'A': Counter(), 'C': Counter()} for root in plan['root_ids']}
    seen, tables, baseline_ids = set(), {}, set()
    for block in range(1, 5):
        out = _project_file(_PROJECT_ROOT, HERE / f'block-{block:02d}')
        for line in (out / 'results.jsonl').read_text().splitlines():
            result = json.loads(line)
            seat = result['seat_permutation'][0]
            policy_id = result['policy_ids_by_seat'][seat]
            arm = 'C' if policy_id == candidate_id else 'A'
            if arm == 'A':
                assert policy_id.startswith('research-r18-v2:')
                baseline_ids.add(policy_id)
            match_id = result['game_key']['game_id']
            assert match_id not in tables
            tables[match_id] = (arm, seat, result['game_key']['tournament_id'])
        with gzip.open(out / 'settlements.jsonl.gz', 'rt') as stream:
            for line in stream:
                row = json.loads(line)
                arm, seat, root = tables[row['match_id']]
                key = (row['match_id'], row['round_no'])
                assert key not in seen and root == row['root_id'] and root in roots
                assert seat == row['focal_physical_seat']
                seen.add(key)
                settlement = row['settlement']
                if settlement['is_draw']:
                    band = 'draw'
                elif settlement['winner_seat'] != seat:
                    band = 'opponent_hu'
                else:
                    fan = settlement['fan']
                    assert type(fan) is int and fan > 0
                    band = 'own_lt4' if fan < 4 else 'own_4_to7' if fan < 8 else 'own_8_to15' if fan < 16 else 'own_ge16'
                roots[root][arm][band] += settlement['score_delta'][seat]
    assert len(tables) == 1024 and len(seen) == 8192 and len(baseline_ids) == 1
    actual = closed['realized_mutually_exclusive_bands']
    for arm in ('A', 'C'):
        for band in BANDS:
            assert sum(v[arm][band] for v in roots.values()) == actual[arm][band]['score']
    deltas = {root: sum(v['C'][band] - v['A'][band] for band in BANDS[3:]) for root, v in roots.items()}
    net = sum(deltas.values())
    signs = {'positive': sum(x > 0 for x in deltas.values()),
             'negative': sum(x < 0 for x in deltas.values()), 'tie': sum(x == 0 for x in deltas.values())}
    components = {band: actual['C'][band]['score'] - actual['A'][band]['score'] for band in BANDS}
    assert sum(components.values()) == closed['net_score_delta_per_table'] * 512
    audits = closed['source_input_audits']
    accepted = closed['net_positive_interval'] and net > 0 and signs['positive'] >= 2
    result = {'schema': 't112-actual-highfan-source-readback/1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'candidate_identity': closed['candidate_identity'],
        'actual_tables': len(tables), 'actual_hands': len(seen), 'independent_roots': len(roots),
        'baseline_policy_id': next(iter(baseline_ids)), 'root_actual_highfan_score_deltas': deltas,
        'highfan_net_gain': net, 'highfan_increment_root_signs': signs, 'mutually_exclusive_net_components': components,
        'actual_candidate_score_calls': sum(a['actual_score_calls'] for a in audits),
        'actual_finite_legal_score_outputs': sum(a['finite_legal_action_score_outputs'] for a in audits),
        'max_candidate_operations': max(a['max_candidate_operations'] for a in audits),
        'normal_R18_fallbacks': 0, 'normal_fallback_evidence': 'closed reader checks every C decision degraded_reasons and all table runtime counts',
        'independent_strength_signal_passed': bool(accepted), 'timing_eligible': bool(accepted),
        'online_admission': False, 'published': False, 'new_models_scores_worlds_tables': 0,
        'reader_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'fixed S02, 128 independent sources, frozen 60 percent weak-opponent setting; no top3 or official deadline claim'}
    with (_project_file(_PROJECT_ROOT, HERE / 'ROOT-HIGHFAN-READBACK.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({key: result[key] for key in ('highfan_net_gain', 'highfan_increment_root_signs',
        'actual_candidate_score_calls', 'actual_finite_legal_score_outputs', 'timing_eligible')})


if __name__ == '__main__':
    main()
