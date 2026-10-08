"""人工不可变状态的缓存键负控；不生成规则分析、胡牌或牌局标签。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t122-s02-completed-replacement-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
RUNTIME=Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0]=[str(RUNTIME),str(_project_file(_PROJECT_ROOT, RUNTIME/'src'))]
from hangma_bot.hangma import public_tile_counts as public
from hangma_bot.hangma.route_transition import ConditionalIdentity,ConditionalPhase,ConditionalRouteState
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER,Tile
from hangma_bot.kernel.observation import PublicMeld
from replacement_cache import make_projection


class KeyOnlyBase:
    """没有replacement实现；本测试只检查键，不偷跑伪规则或图。"""
    def __init__(self):
        self.input_guard=public._PublicInputGuard()


def main():
    Projection=make_projection(KeyOnlyBase)
    projection=Projection()
    hand=tuple(Tile(code) for code in CANONICAL_TILE_ORDER[:10])
    meld=PublicMeld('gang_an',(Tile('东'),)*4,0,None)
    view=public.PublicTileView(((),)*4,((meld,),(),(),()),(10,13,13,13),83)
    identity=ConditionalIdentity('fixture-only',1,'gang:fixture',('first-path',),'fixture-rules')
    state=ConditionalRouteState(hand,1,ConditionalPhase.REPLACEMENT_DRAW,False,1,0,83,
        root_public_view=view,public_view=view,identity=identity,seat=0,dealer_seat=0,
        unseen_capacities=(4,)*34,unseen_evidence=('exact',)*34)
    first=projection.replacement_key(state)
    assert first is not None
    assert projection.replacement_key(replace(state,concealed=tuple(reversed(hand))))==first
    assert projection.replacement_key(replace(state,identity=replace(identity,path=('different-path',))))==first
    changes=[{'dealer_seat':1},{'seat':1},{'baotou':True},{'baotou':1},
        {'chain_count':2},{'chain_count':True},{'chain_piao':1},{'wall_remaining':82},
        {'catch_restricted':True},{'last_draw_replacement':True},{'local_witness_only':True},
        {'claim_awarded':True},{'unseen_capacities':(3,)+(4,)*33},
        {'unseen_evidence':('unknown',)+('exact',)*33},
        {'identity':replace(identity,root_action_key='another-root')},
        {'identity':replace(identity,ruleset_version='another-rules')},
        {'public_view':replace(view,consumed_seq=1)},
        {'public_view':replace(view,discards=((Tile('1w'),),(),(),()))},
        {'root_public_view':replace(view)}]
    for change in changes:
        assert projection.replacement_key(replace(state,**change))!=first,change
    bypasses=[{'structural_only':True},{'wall_remaining':20},{'phase':ConditionalPhase.PUBLIC_WAIT},
        {'identity':None},{'public_view':None},{'concealed':hand[:-1]},
        {'seat':True},{'meld_count':True}]
    for change in bypasses:
        assert projection.replacement_key(replace(state,**change)) is None,change
    result={'schema':'t122-replacement-key-controls/1','synthetic_only':True,
        'equivalent_controls':2,'distinct_controls':len(changes),'bypass_controls':len(bypasses),
        'all_passed':True,'actual_rule_choose_score_world_table_calls':0}
    with (_project_file(_PROJECT_ROOT, HERE/'KEY-CONTROL-RESULT.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
