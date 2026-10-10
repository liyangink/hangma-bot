"""等待形状去重、未知与无摸跟打边界，防止速度统计虚增。"""
import importlib.util
from pathlib import Path
import pytest

FILE=Path(__file__).resolve().parents[3]/'tools/research/astra-evolution-2026-10-10/tempo160.py'
spec=importlib.util.spec_from_file_location('astra_stage_tempo',FILE)
tempo=importlib.util.module_from_spec(spec);spec.loader.exec_module(tempo)


def row(routes=(),coverage='complete',selected='discard:1w'):
    return {'round_no':1,'seq':4,'seat':0,'selected':selected,'current_white':1,'acquired_white':1,
            'selected_rule_facts':{'completeness':'complete','shanten_after':0},
            'selected_value_facts':{'coverage':coverage,'issues':[],'routes':list(routes)}}


def route(capacity=2,followup=None,kind='normal'):
    return {'followup_discard':followup,'conditions':{'draw_kind':kind},
            'useful_tiles':[{'code':'3w','remaining_estimate':capacity}],
            'conditional_settlement':{'score_delta':[10,-8,-1,-1]}}


def test_same_code_does_not_double_count_different_conditions():
    shape=tempo.waiting_shape(row([route(),route()]))
    assert shape['code_width']==1 and shape['capacity']==2


def test_inconsistent_capacity_is_rejected():
    with pytest.raises(ValueError):tempo.waiting_shape(row([route(1),route(2)]))


def test_unknown_coverage_is_not_known_zero():
    assert tempo.waiting_shape(row(coverage='partial'))['capacity'] is None
    assert tempo.waiting_shape(row())['status']=='known_empty'


def test_claim_best_followup_is_not_actual_waiting_shape():
    assert tempo.waiting_shape(row([route()],selected='peng:3w'))['status']=='not_waiting'
    assert tempo.waiting_shape(row([route(followup='1w'),route(kind='replacement')]))['status']=='known_empty'


def test_claim_followup_without_draw_does_not_add_draw_ordinal():
    h={'round_no':1,'initial':{'drawn_seat':1,'dealer_seat':1,'hands':[[],[],[],[]]},'events':[],
       'winner_seat':None,'score_delta':[0,0,0,0],'fan':0}
    record=tempo.hand_tempo(h,[row([route()])],0)
    assert record['first_known_normal_hu_waiting_witness']['own_draw_ordinal']==0


def test_unknown_and_no_witness_hands_keep_denominator():
    h={'round_no':1,'initial':{'drawn_seat':1,'dealer_seat':1,'hands':[[],[],[],[]]},'events':[],
       'winner_seat':None,'score_delta':[0,0,0,0],'fan':0}
    unknown=row(coverage='partial');unknown['selected_rule_facts']=None
    record=tempo.hand_tempo(h,[unknown],0)
    facts=tempo.aggregate([record])
    assert facts['hands']==1 and facts['no_observed_waiting_witness_hands']==1
    assert facts['waiting_coverage_unknown_windows']==1 and facts['mean_own_draw_ordinal_to_waiting_witness'] is None


def test_dealer_initial_white_and_later_white_are_not_double_counted():
    h={'round_no':1,'initial':{'drawn_seat':0,'dealer_seat':0,'hands':[['白'],[],[],[]]},
       'events':[{'type':'tile_drawn','seat':0,'seq':3,'tile':'白'}],
       'winner_seat':None,'score_delta':[0,0,0,0],'fan':0}
    record=tempo.hand_tempo(h,[],0)
    assert record['initial_white']==1 and record['final_acquired_white']==2
