"""大牌路线案例实验：可见决策与离线指定进张分离，所有牌型委托生产规则。

生成的是本人动作前缀，在他家不终局且不鸣牌的条件下可执行；不把指定
进张当成概率，不冒充完整牌墙模拟。当前批次只接受零链门清计番锚。
"""
from __future__ import annotations

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
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(_project_file(_PROJECT_ROOT, ROOT / 'src')), str(ROOT)]

from hangma_bot.application.audit_codec import decision_request_to_json
from hangma_bot.hangma import HangmaRules, hand_analysis, progression
from hangma_bot.hangma.interface import ValueAnalysisLimits, WinDescription
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile, Discard, WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState, CompetitionContext
from hangma_bot.policy.interface import DecisionRequest, DecisionBudget
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.value_one_draw import OneDrawValuePolicy
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN

RULESET = 'hangma-mvp-v10-public-counts'
GOLD = _project_file(_PROJECT_ROOT, ROOT / 'tests/fixtures/official/v23/fan-calc/cases.jsonl')
# 原始零起始行号，只用当前物理可达的零链门清终点；链类另建动作前缀。
ANCHORS = (0, 1, 96, 240, 275, 277, 283, 320, 330, 408, 409, 604, 619, 639, 649)


@dataclass(frozen=True)
class Case:
    """可复现本人前缀；future_draws 只属于离线教师，不进入观察或请求。"""
    case_id: str
    anchor_line: int  # 官方归档零起始行号，报告另存文件哈希
    initial_hand: tuple[str, ...]  # 十四张，最后一张为当前摸牌
    discards: tuple[str, ...]  # 指定每次等待前的弃牌，含当前决策
    future_draws: tuple[str, ...]  # 按本人摸牌次数排序，末次摸后胡


def generate():
    """从官方终点反向替换一至四张，保证所有手牌、未来牌、弃牌总计不超四张。"""
    rows = [json.loads(line) for line in GOLD.read_text().splitlines()]
    cases = []
    for index in ANCHORS:
        row = rows[index]
        req = row['request']
        assert row['http_status'] == 200 and row['response']['hu']
        assert not req.get('chain', {}).get('count', 0)
        terminal = req['hand'] + [req['draw']]
        assert len(terminal) == 14 and max(Counter(terminal).values()) <= 4
        junk = [c for c in ('北', '南', '中', '发', '9b', '9t', '9w', '8b') if c not in terminal][:4]
        assert len(junk) == 4
        for draws in range(1, 5):
            for variant in range(2 if draws > 1 else 1):
                pre = list(req['hand'])
                removed = []
                for step in range(draws - 1):
                    removed.append(pre.pop(0 if variant == 0 else -1))
                hand = tuple(pre + junk[:draws])
                cuts = tuple(reversed(junk[:draws]))
                future = tuple(removed + [req['draw']])
                assert len(hand) == 14
                assert max(Counter(hand + future).values()) <= 4
                cases.append(Case(f'gold-{index}-draws-{draws}-variant-{variant}', index, hand, cuts, future))
    return rows, tuple(cases)


def observation(hand, *, case_id, wall=80, dealer=1, river=(), seq=1, reserve=()):
    """构造不含未来信息的门清摸牌观察；公开计数完整、零链、无抓打圈。"""
    tiles = tuple(Tile(c) for c in hand)
    before, draw = tiles[:-1], tiles[-1]
    baotou = progression.baotou_after_draw(False, before, 0, draw)
    # 补齐当前公开牌库存，避免把长墙空牌河原封不动配成短墙快照。
    # 指定进张只用于构造物理有效的案例，不传给策略；完整历史仍不作声称。
    rivers = [list(river), [], [], []]
    used = Counter(tuple(hand) + tuple(river) + tuple(reserve))
    missing = 83 - wall - len(river)
    assert missing >= 0
    for code in CANONICAL_TILE_ORDER:
        if code == '白':
            continue  # 避免为补库存制造未定义的抓打圈历史。
        for _ in range(4 - used[code]):
            if not missing:
                break
            rivers[missing % 4].append(code)
            missing -= 1
        if not missing:
            break
    assert missing == 0
    return PlayerObservation(
        game_id=case_id, seat=0, round_no=1, snapshot_seq=seq, consumed_seq=seq,
        phase='draw', dealer_seat=dealer, turn_seat=0, responding_seats=(),
        my_hand=before, drawn_tile=draw, discards=tuple(tuple(Tile(c) for c in r) for r in rivers),
        melds=((), (), (), ()), hand_counts=(14, 13, 13, 13), last_discard=None,
        remaining_tile_count=wall, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile('白'), baotou, 0, False),
        public_history=(), history_complete=False, chain_piao=0, gang_draw=False,
    )


def request_for(obs, rules):
    """仅向策略交付可见观察和生产规则事实，不携带目标牌型或指定进张。"""
    return DecisionRequest(
        observation=obs,
        competition=CompetitionContext('constructed-case', None, None, None, None, (), 0),
        rules=rules, decision_id=obs.game_id, trigger_seq=obs.snapshot_seq,
        window_key=WindowKey(obs.game_id, obs.round_no, obs.snapshot_seq, WindowPhase.DRAW, obs.seat),
        rejected_attempts=(),
    )


def witness(case, rows, enabled):
    """逐步复核本人弃牌与最终胡；提前可胡不冒充不可胡，记录为合法主动延后路径。"""
    rules = HangmaRules(RuleConfig(RULESET, 1, enabled))
    hand, river, early_hu = list(case.initial_hand), [], []
    trace = []
    for step, (cut, draw) in enumerate(zip(case.discards, case.future_draws)):
        obs = observation(hand, case_id=case.case_id, river=river, seq=step + 1,
                          wall=80-4*step, reserve=case.future_draws[step:])
        analysis = rules.analyze(obs)
        keys = {c.action_key for c in analysis.legal_candidates}
        assert 'discard:' + cut in keys, (case.case_id, step, keys)
        if 'hu' in keys:
            early_hu.append(step)
        assert progression.chain_after_discard(0, 0, obs.rule_state.baotou, Tile(cut)) == (0, 0)
        trace.append(dict(hand=list(hand), discard=cut, draw_next=draw, could_hu='hu' in keys))
        hand.remove(cut)
        river.append(cut)
        hand.append(draw)
        assert max(Counter(hand + river).values()) <= 4
    obs = observation(hand, case_id=case.case_id, river=river, seq=len(trace) + 1,
                      wall=80-4*len(trace))
    legal = any(c.action_key == 'hu' for c in rules.analyze(obs).legal_candidates)
    expected = rows[case.anchor_line]['response']
    allowed = not enabled or '白' not in hand or expected['baotou']
    assert legal == allowed, (case.case_id, enabled, expected, obs)
    result = rules.score(WinDescription(obs, 0)) if legal else None
    if result:
        assert result.fan == expected['fan'], (case.case_id, result, expected)
        assert result.details == tuple(expected['detail']), (case.case_id, result, expected)
    return dict(allowed=legal, fan=None if result is None else result.fan,
                details=[] if result is None else result.details, early_hu_steps=early_hu, trace=trace)


def describe(candidate, obs):
    """诊断只读取生产牌效/条件结算；对子距离同样委托规则模块。"""
    f, v = candidate.facts, candidate.value_facts
    result = dict(action=candidate.action_key, shanten=None if f is None else f.shanten_after,
                  unseen=None if f is None else sum(t.remaining_estimate for t in f.useful_tiles),
                  value_coverage=None if v is None else v.coverage.value)
    if isinstance(candidate.action, Discard):
        hand = list(obs.my_hand) + [obs.drawn_tile]
        hand.remove(candidate.action.tile)
        summary = hand_analysis.analyse_hand(tuple(hand), 0)
        result.update(standard=summary.standard_shanten, seven=summary.chiitoi_shanten)
    routes = [] if v is None else v.routes
    result['score_mass'] = sum(t.remaining_estimate * r.conditional_settlement.score_delta[obs.seat]
                               for r in routes for t in r.useful_tiles)
    result['routes'] = [dict(fan=r.conditional_settlement.fan, details=r.conditional_settlement.details,
                            tiles=[[t.code, t.remaining_estimate] for t in r.useful_tiles]) for r in routes]
    return result


async def run(output, limit=None):
    """生成并验证案例，比较冻结策略；结果仅为条件诊断而非完整桌赛期望。"""
    rows, cases = generate()
    if limit is not None:
        cases = cases[:limit]
    policies = dict(v2=ComparableHeuristicPolicyV2(monotonic=lambda: 0),
                    one_draw_reference=OneDrawValuePolicy(monotonic=lambda: 0),
                    hu_upgrade=V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=RISK_CELLS,
                                                risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN))
    results, proofs, counts = [], [], Counter()
    started = time.monotonic()
    for enabled in (False,):
        rules = HangmaRules(RuleConfig(RULESET, 1, enabled))
        for case in cases:
            proof = witness(case, rows, enabled)
            proofs.append(dict(case_id=case.case_id, enabled=enabled, **proof))
            for wall in (24, 48, 80):
                for dealer in (0, 1):
                    obs = observation(case.initial_hand, case_id=case.case_id, wall=wall, dealer=dealer,
                                      reserve=case.future_draws)
                    # 与线上配置保护一致：等胡未校准配置完整退回 V2。
                    analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits(2048, 128))
                    request = request_for(obs, analysis)
                    plans = {}
                    for name, policy in policies.items():
                        effective = request
                        if name == 'hu_upgrade' and enabled:
                            effective = replace(request, rules=rules.analyze(obs))
                        plan = await policy.choose(effective, DecisionBudget(10, 11, 12))
                        plans[name] = dict(first=plan.candidates[0].action_key,
                                           degraded=list(plan.degraded_reasons))
                    descriptions = [describe(c, obs) for c in analysis.legal_candidates]
                    counts['decisions'] += 1
                    counts['immediate_hu' if any(c.action_key == 'hu' for c in analysis.legal_candidates) else 'not_hu'] += 1
                    for name in ('hu_upgrade', 'one_draw_reference'):
                        counts[name + '_changes'] += plans[name]['first'] != plans['v2']['first']
                    results.append(dict(case_id=case.case_id, anchor_line=case.anchor_line,
                        enabled=enabled, wall=wall, dealer=dealer, specified_draw_count=len(case.future_draws),
                        specified_path_fits_wall=wall-20 >= 4*len(case.future_draws),
                        witness_target_allowed=proof['allowed'], witness_cut=case.discards[0],
                        hand=list(case.initial_hand), plans=plans, candidates=descriptions))
    payload = dict(schema='big-hand-case-report/1', scope='本人条件前缀与可见策略诊断，非完整桌赛效果',
                   gold_sha256=hashlib.sha256(GOLD.read_bytes()).hexdigest(), ruleset=RULESET,
                   counts=counts, elapsed_seconds=time.monotonic()-started,
                   witnesses=proofs, decisions=results)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(counts=counts, witnesses=len(proofs), elapsed_seconds=payload['elapsed_seconds']), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=_project_file(_PROJECT_ROOT, HERE / 'case-report.json'))
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    asyncio.run(run(args.output, args.limit))
