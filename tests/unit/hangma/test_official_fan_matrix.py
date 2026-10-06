"""v23官方计算器全类型对拍，再叠加赛事有财必爆头资格（2026-09-08）。

计算器输入是静态13+1，不把合成链参数当成可达对局。原始副露反例和
已有官方连续动作轨迹另测。离线重放固定响应，不在测试或规则模块联网。
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.hand_analysis import any_tile_win, win_split
from hangma_bot.hangma.interface import RuleCompleteness, WinDescription
from hangma_bot.hangma.progression import baotou_after_draw
from hangma_bot.kernel.actions import Hu, Tile
from hangma_bot.kernel.config import RuleConfig
from tests.unit.hangma.test_youcai_integration import make_observation
from tests.unit.hangma.official_fan_tools import FIXTURE_DIR, request_key, current_response

FIXTURES=FIXTURE_DIR
ROWS=[json.loads(line) for line in (FIXTURES/'cases.jsonl').read_text().splitlines()]
VALID=[row for row in ROWS if row['http_status']==200]


def test_corpus_integrity_and_special_type_coverage():
    manifest=json.loads((FIXTURES/'manifest.json').read_text())
    assert manifest['cases']==len(ROWS)
    for name,digest in manifest['sha256'].items():
        assert hashlib.sha256((FIXTURES/name).read_bytes()).hexdigest()==digest
    assert manifest['guide_version'] == 23
    assert len({request_key(row['request']) for row in ROWS}) == len(ROWS)
    for row in ROWS:
        assert row['guide_version'] == 23
        assert json.loads(row['response_raw']) == row['response']
    details={s for row in VALID for s in (row['response'].get('detail') or [])}
    assert {'平胡','七对','豪华七对×1','豪华七对×2','豪华七对×3','杠开','爆头',
            '财飘','双财飘','三财飘','4个白板','连杠×2','连杠×3','杠飘链×3'}<=details
    assert any(row['response'].get('fan')==512 for row in VALID)
    assert any(not row['response']['hu'] for row in VALID)
    assert any(row['http_status']==400 for row in ROWS)


def test_previous_matrix_inputs_remain_covered():
    """旧版本原始响应保留，旧矩阵所有请求均有当前版本权威对照。"""
    old_dir = Path(__file__).resolve().parents[2] / 'fixtures/official/v18/fan-calc-youcai'
    manifest = json.loads((old_dir / 'manifest.json').read_text())
    assert hashlib.sha256((old_dir / 'cases.jsonl').read_bytes()).hexdigest() == manifest['sha256']['cases.jsonl']
    previous = [json.loads(line) for line in (old_dir / 'cases.jsonl').read_text().splitlines()]
    assert {request_key(row['request']) for row in previous} <= {request_key(row['request']) for row in ROWS}


@pytest.mark.parametrize('row',VALID,ids=[r['tags'][0] for r in VALID])
def test_shape_baotou_fan_details_scores_and_both_room_configs(row):
    q=row['request'];official=current_response(q);hand=tuple(Tile(t) for t in q['hand']);draw=Tile(q['draw'])
    split=win_split(hand+(draw,),0)
    assert (split is not None)==official['hu']
    baotou=baotou_after_draw(False,hand,0,draw,replacement=False)
    assert baotou==official['baotou']
    assert baotou==any_tile_win(hand,0)
    chain=q.get('chain',{'count':0,'piao':0})
    obs=make_observation(q['hand'],q['draw'],baotou=baotou,chain=chain['count'],piao=chain['piao'],gang=chain['count']>chain['piao'])
    for enabled in (False,True):
        rules=HangmaRules(RuleConfig('v23-fan-matrix',q.get('base',1),enabled))
        # 用户确认规则：有财必须爆头；明细含杠开不能替代baotou。
        allowed=official['hu'] and (not enabled or '白' not in q['hand']+[q['draw']] or official['baotou'])
        analysis=rules.analyze(obs)
        assert ('hu' in {c.action_key for c in analysis.legal_candidates})==allowed
        assert rules.validate(obs,Hu()).legal==allowed
        assert analysis.completeness is RuleCompleteness.COMPLETE
        assert analysis.emergency_candidate is not None
        if official['hu']:
            # score的输入契约是已确认胡牌事实，计算器倍率不叠加资格开关。
            for dealer in (0,1):
                settled=rules.score(WinDescription(replace(obs,dealer_seat=dealer),0))
                assert settled.fan==official['fan']
                assert list(settled.details)==official['detail']
                expected=official['scores']['dealer_hu' if dealer==0 else 'nondealer_hu']
                assert settled.score_delta[0]==expected['win']
                assert sorted(-v for v in settled.score_delta[1:])==sorted(expected['lose'])
                assert sum(settled.score_delta)==0
                if dealer==1:assert -settled.score_delta[1]==max(expected['lose'])
        else:
            settled=rules.score(WinDescription(obs,0))
            assert settled.fan==official['fan']==0
            assert settled.details==() and settled.score_delta==(0,0,0,0)


@pytest.mark.parametrize('row',[r for r in ROWS if r['http_status']==400],ids=lambda r:r['tags'][0])
def test_official_impossible_white_total_is_rejected_locally(row):
    """官方拒绝手留白板加链内飘白超过四张；本地不得产出有效结算。"""
    q=row['request']
    obs=make_observation(q['hand'],q['draw'],chain=q['chain']['count'],piao=q['chain']['piao'])
    rules=HangmaRules(RuleConfig('v23-invalid-white',1,False))
    with pytest.raises(ValueError,match='白板总数'):
        rules.score(WinDescription(obs,0))
