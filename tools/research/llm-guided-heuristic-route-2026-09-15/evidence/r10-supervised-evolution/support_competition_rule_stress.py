"""用唯一规则引擎构造高候选数/重叠结构压力输入；不虚构向听和有效牌事实。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import replace
import argparse
import time
import strong_seed_batch as b
import support_competition_batch as task
import sitin_natural_panel as natural
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits

PATH=task.OUT/'rule-generated-stress.json'
HANDS={
    'fourteen_distinct':('1w','2w','3w','4w','5w','6w','7w','8w','9w','1b','3b','5b','7b','9b'),
    'dense_recombination':('1w','1w','2w','2w','3w','3w','4w','4w','5w','5w','6w','6w','7w','8w'),
    'cross_suit_overlap_wealth':('1w','1w','2w','2w','3w','4w','5b','5b','6b','7b','3t','4t','5t','白'),
    'honor_pairs_and_sequence':('东','东','南','南','西','西','北','北','中','发','1w','2w','3w','4w'),
    'four_copies_and_neighbors':('3w','3w','3w','3w','4w','5w','6w','7w','8w','1b','2b','4b','5b','6b'),
}


def freeze():
    """公开观察人工构造，规则事实全部由生产analyze生成；不是历史可达证明。"""
    assert not PATH.exists()
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json');versions=natural.stage.contract_versions_block(contract)
    config=RuleConfig(ruleset_version=str(versions['ruleset_version']),base_score=int(versions['base_score']),you_cai_bi_kao=bool(versions['you_cai_bi_kao']))
    rules=HangmaRules(config)
    original=b.read(task.OUT/'diagnostic-panel.json')['rows'][0]['record']['request']
    template=b.behavior.decision_request_from_json(original);rows=[]
    for name,hand in HANDS.items():
        assert len(hand)==14 and max(hand.count(c) for c in hand)<=4
        obs=PlayerObservation(game_id='competition-stress-'+name,seat=0,round_no=1,snapshot_seq=10,consumed_seq=10,
            phase='draw',dealer_seat=0,turn_seat=0,responding_seats=(),my_hand=tuple(Tile(c) for c in hand[:-1]),drawn_tile=Tile(hand[-1]),
            discards=((),(),(),()),melds=((),(),(),()),hand_counts=(14,13,13,13),last_discard=None,remaining_tile_count=60,
            scores=(0,0,0,0),rule_state=RulePublicState(Tile('白'),False,0,False),public_history=(),chain_piao=0)
        start=time.perf_counter();analysis=rules.analyze(obs,value_limits=ValueAnalysisLimits());ms=(time.perf_counter()-start)*1000
        request=replace(template,observation=obs,rules=analysis,decision_id='stress-'+name,trigger_seq=10)
        record=b.behavior.capture_request(request)
        rows.append({'name':name,'record':record,'analysis_ms':ms,'legal_candidates':len(analysis.legal_candidates),
                     'completeness':str(analysis.completeness),'issues':[str(i) for i in analysis.issues]})
    assert max(r['legal_candidates'] for r in rows)>=14
    b.write(PATH,{'created_at_utc':b.search.utc_now(),'deps_digest':b.search.av_gates().av_deps_digest(),
        'builder_sha256':b.digest(b.Path(__file__).read_bytes()),'versions':versions,'rows':rows,
        'scope':'5个构造观察，经唯一规则引擎生成事实；不宣称历史可达或已覆盖最坏时间，零桌赛/模型调用'})
    print([{'name':r['name'],'actions':r['legal_candidates'],'completeness':r['completeness'],'issues':len(r['issues'])} for r in rows],flush=True)

if __name__=='__main__':freeze()
