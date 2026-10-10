"""验证实际取白、三类支付与独立根区间，防止把决策数当样本数。"""
import importlib.util
from pathlib import Path
import pytest

FILE=Path(__file__).resolve().parents[3]/'tools/research/astra-evolution-2026-10-10/summarize160.py'
spec=importlib.util.spec_from_file_location('astra_stage160_summary',FILE)
summary=importlib.util.module_from_spec(spec);spec.loader.exec_module(summary)


def hand(*,winner=1,dealer=0,fan=1,delta=(-8,10,-1,-1)):
    return {'initial':{'dealer_seat':dealer,'drawn_seat':dealer,'hands':[['白'],[],[],[]]},
            'events':[{'type':'tile_drawn','seat':0,'tile':'白'},
                      {'type':'tile_discarded','seat':0,'tile':'白'}],
            'winner_seat':winner,'score_delta':list(delta),'fan':fan,'is_draw':winner is None}


@pytest.mark.parametrize('focal,dealer,winner,delta,key,amount',[
    (0,0,1,(-8,10,-1,-1),'dealer_to_idle_payment',8),
    (2,0,0,(24,-8,-8,-8),'idle_to_dealer_payment',8),
    (2,0,1,(-8,10,-1,-1),'idle_to_idle_payment',1)])
def test_payments_are_separated(focal,dealer,winner,delta,key,amount):
    facts=summary.hand_facts(hand(dealer=dealer,winner=winner,delta=delta),focal)
    assert facts[key]==amount
    assert sum(facts[k] for k in ('dealer_to_idle_payment','idle_to_dealer_payment','idle_to_idle_payment'))==amount


def test_acquired_white_keeps_discarded_white_and_counts_dealer_draw_once():
    facts=summary.hand_facts(hand(),0)
    assert facts['white_bin']=='2' and facts['white_by_seat'][0]==2
    assert facts['draws_by_seat'][0]==2


def test_highfan_and_multiwhite_income_protection():
    facts=summary.hand_facts(hand(winner=0,fan=4,delta=(96,-32,-32,-32)),0)
    assert facts['highfan_income']==facts['multiwhite_income']==96
    assert facts['ordinary_income']==0 and facts['dealer_hu']==1


def test_draw_is_not_a_hu_or_payment():
    facts=summary.hand_facts(hand(winner=None,delta=(0,0,0,0)),0)
    assert facts['draw_hand']==1 and facts['own_hu']==0
    assert facts['dealer_to_idle_payment']==0


def test_single_root_never_creates_strength_interval():
    assert summary.root_statistics([10])['root_bootstrap_95_percent_interval'] is None


def test_zero_activity_roots_are_retained():
    facts=summary.root_statistics([0,0,10,0],resamples=1000)
    assert facts['independent_roots']==4 and facts['mean']==2.5 and facts['zero_roots']==3
    assert facts['root_bootstrap_95_percent_interval'][0]==0


def test_three_key_ties_remain_intervals():
    ledger=[{'total_score':10,'place_points':3,'god_count':2},
            {'total_score':10,'place_points':3,'god_count':2},
            {'total_score':10,'place_points':3,'god_count':1},
            {'total_score':20,'place_points':-3,'god_count':0}]
    assert summary.rank_intervals(ledger)==[[2,3],[2,3],[4,4],[1,1]]


def test_short_table_is_rejected_before_aggregation():
    task={'focal_seat':0};closed={'task':task,'status':'complete','completed_hands':15}
    with pytest.raises(ValueError,match='不完整'):
        summary.analyze_table(task,closed,[{}]*15,[],[],None)
