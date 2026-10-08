"""完整桌赛证据核对与改选类型审计；不把累计积分当作单局收益。"""

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
import asyncio
from collections import Counter,defaultdict
import gzip
import hashlib
import json

from lab import HERE,ROOT,DecisionBudget
from hangma_bot.application.audit_codec import decision_request_from_json
from upgrade_persistent import upgrade_policy


async def verify(phase):
    directory=_project_file(_PROJECT_ROOT, HERE/f'dual-route-{phase}')
    freeze=json.loads((directory/'freeze.json').read_text())
    metadata=json.loads((directory/'completion.json').read_text())
    for name,expected in freeze['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/name)).read_bytes()).hexdigest()==expected,name
    rows=[json.loads(x) for x in (directory/'results.jsonl').read_text().splitlines()]
    hands=[json.loads(x) for x in gzip.open(directory/'hands.jsonl.gz','rt')]
    changes=[json.loads(x) for x in gzip.open(directory/'changes.jsonl.gz','rt')]
    assert len(rows)==metadata['tables']==freeze['roots']*8
    assert len(hands)==metadata['hands']==len(rows)*freeze['hands_per_table']
    assert len(changes)==metadata['changes'] and not metadata['excluded']
    assert all(value==0 for value in metadata['runtime_totals'].values())
    grouped=defaultdict(list);pairs=Counter();roots=Counter()
    for hand in hands:
        assert len(hand['score_delta'])==4 and sum(hand['score_delta'])==0
        grouped[hand['game_id']].append(hand)
    for row in rows:
        assert row['status']=='complete' and not row['invalid_reasons']
        assert row['completed_hands']==row['expected_hands']==row['config']['rounds_per_game']==freeze['hands_per_table']
        game=row['game_key']['game_id'];h=grouped.pop(game)
        assert sorted(x['round_no'] for x in h)==list(range(1,freeze['hands_per_table']+1))
        actual=[sum(x['score_delta'][seat] for x in h) for seat in range(4)]
        assert actual==[a-b for a,b in zip(row['scores_after'],row['scores_before'])]
        pairs[row['pair_id']]+=1;roots[row['scenario_id']]+=1
    assert not grouped and all(n==2 for n in pairs.values()) and all(n==8 for n in roots.values())
    by_action=Counter();examples={};policy=upgrade_policy()
    for change in changes:
        request=decision_request_from_json(change['request'])
        old=(await policy.choose(request,DecisionBudget(10,11,12))).candidates[0].action_key
        new=change['action'];assert old!=new
        kind=old.split(':')[0]+'→'+new.split(':')[0];by_action[kind]+=1
        if kind not in examples:
            obs=request.observation;facts={c.action_key:c.facts for c in request.rules.legal_candidates}
            def describe(key):
                f=facts.get(key)
                return None if f is None else dict(shanten=f.shanten_after,standard=f.standard_shanten_after,
                    seven=f.seven_pairs_shanten_after,unseen=sum(t.remaining_estimate for t in f.useful_tiles),
                    replacement_draw_unknown=f.replacement_draw_unknown)
            examples[kind]=dict(game_id=obs.game_id,round_no=obs.round_no,seat=obs.seat,seq=request.trigger_seq,
                hand=[t.code for t in obs.my_hand],draw=None if obs.drawn_tile is None else obs.drawn_tile.code,
                old_action=old,new_action=new,old_facts=describe(old),new_facts=describe(new),wall=obs.remaining_tile_count)
    report=dict(schema='dual-route-table-verification/1',source_hashes_verified=True,complete_pairing=True,
        hand_deltas_match_table_deltas=True,tables=len(rows),hands=len(hands),roots=len(roots),
        changes=len(changes),changed_action_families=by_action,examples=examples,
        scope='逻辑时钟下完整8单局桌赛和单项改选审计；不代表真实平台限时/正式赛全阶段验证')
    (directory/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['smoke','development','confirmation'],required=True)
    asyncio.run(verify(parser.parse_args().phase))
