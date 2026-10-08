"""飘/杠的本人合法动作前缀；复用生产推进，不声称模拟了他家抢胡与摸切。"""

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
from collections import Counter
from dataclasses import replace
import json

from lab import GOLD, HERE, RULESET, HangmaRules, Tile, RuleConfig, observation
from hangma_bot.hangma import progression as p
from hangma_bot.hangma.interface import WinDescription
from hangma_bot.kernel.actions import Discard, Gang, GangKind
from hangma_bot.kernel.observation import PublicMeld, RulePublicState


def start(pre, draw):
    """仅承载本人推进；空他家不是完整牌山，不能交给赛事效果评估。"""
    seats = tuple(p.SeatProgression(tuple(Tile(c) for c in pre) if i == 0 else (),
                  (), (), None, False, 0, 0, False) for i in range(4))
    state = p.ProgressionState(1, 1, 1, seats, (0, 0, 0, 0), 60, 80, 1,
                              'pending_draw', 0, (), 1, None,
                              p.DrawRequest(0, False, None, False, False), None)
    return p.attach_draw(state, Tile(draw)).state


def view(state, replacement=False):
    """推进事实机械映射为本人观察，不填入他家暗牌或未来进张。"""
    s = state.seats[0]
    # 基础观察的门清占位手随后完整替换，不用占位的规则事实。
    obs = observation(('1w',)*3 + ('2w',)*3 + ('3b',)*3 + ('4t',)*3 + ('白','东'), case_id='chain-prefix')
    return replace(obs, my_hand=s.hand, drawn_tile=s.drawn, discards=(s.discards, (), (), ()),
        melds=(tuple(PublicMeld(0, m.kind, m.tiles, m.from_seat) for m in s.melds), (), (), ()),
        hand_counts=(len(s.hand)+bool(s.drawn), 13, 13, 13),
        rule_state=RulePublicState(Tile('白'), s.baotou, s.chain_count, s.catch_play,
                                   0 if s.catch_play else None), chain_piao=s.chain_piao,
        gang_draw=replacement, snapshot_seq=state.seq, consumed_seq=state.seq)


def advance(state, action, draw, rules, replacement=False):
    """先经公开规则确认动作，再由生产推进应用；下一摸的类型显式给定。"""
    obs = view(state, replacement)
    legal = rules.analyze(obs).legal_candidates
    assert any(c.action == action for c in legal), (action, legal, obs)
    changed = p.resolve(state, ((0, action),))
    assert changed.blocked is None
    pending = replace(changed.state, window='pending_draw', responding=(), turn_seat=0,
                      pending_draw=p.DrawRequest(0, isinstance(action, Gang), None, False, False))
    return p.attach_draw(pending, Tile(draw)).state


def inventory(state):
    """核对本人暗牌、副露与已弃牌没有使用第五张牌。"""
    s = state.seats[0]
    codes = [t.code for t in s.hand + s.discards + ((s.drawn,) if s.drawn else ())]
    codes += [t.code for m in s.melds for t in m.tiles]
    assert max(Counter(codes).values()) <= 4


def run():
    """官方纯飘计番锚必须有可执行白板前缀；另覆盖一至四次真实杠补。"""
    rows = [json.loads(line) for line in GOLD.read_text().splitlines()]
    selected = {}
    for line, row in enumerate(rows):
        req, res = row['request'], row['response']
        chain = req.get('chain', {})
        count = chain.get('count', 0)
        if row['http_status'] != 200 or not res.get('hu') or not 1 <= count <= 3 or chain.get('piao') != count:
            continue
        if req['hand'].count('白') + count + (req['draw'] == '白') > 4:
            continue
        if not p.recompute_baotou(tuple(Tile(c) for c in req['hand']), 0, req['hand'].count('白')):
            continue
        selected.setdefault(tuple(res['detail']), (line, row))
    output = []
    for details, (line, row) in selected.items():
        for enabled in (False,):
            req = row['request']
            count = req['chain']['count']
            rules = HangmaRules(RuleConfig(RULESET, req.get('base', 1), enabled))
            state = start(req['hand'], '白')
            trace = []
            for step in range(count):
                inventory(state)
                obs = view(state)
                trace.append(dict(hand=[t.code for t in obs.my_hand], drawn=obs.drawn_tile.code,
                                  action='discard:白', chain=obs.rule_state.chain_count,
                                  baotou=obs.rule_state.baotou))
                draw = req['draw'] if step == count-1 else '白'
                state = advance(state, Discard(Tile('白')), draw, rules)
            inventory(state)
            obs = view(state)
            assert any(c.action_key == 'hu' for c in rules.analyze(obs).legal_candidates)
            result = rules.score(WinDescription(obs, 0))
            assert result.fan == row['response']['fan']
            assert result.details == details
            output.append(dict(kind='piao', anchor_line=line, enabled=enabled, trace=trace,
                               fan=result.fan, details=result.details))
    for count in range(1, 5):
        for enabled in (False,):
            rules = HangmaRules(RuleConfig(RULESET, 1, enabled))
            state = start(['1w']*4 + ['2w']*4 + ['3w']*4 + ['4w'], '4w')
            trace = []
            for step in range(count):
                inventory(state)
                code = str(step+1) + 'w'
                draw = ('白' if count < 4 or step == 2 else '东') if step == count-1 or step == 2 else '4w'
                action = Gang(Tile(code), GangKind.CONCEALED)
                trace.append(dict(action='gang:concealed:' + code, replacement=draw))
                state = advance(state, action, draw, rules, replacement=step > 0)
            inventory(state)
            obs = view(state, True)
            allowed = any(c.action_key == 'hu' for c in rules.analyze(obs).legal_candidates)
            # 白板杠补若未爆头，有财必拷仍不可胡；第四杠后留白单将成立爆头。
            assert allowed == (not enabled or obs.rule_state.baotou)
            result = rules.score(WinDescription(obs, 0)) if allowed else None
            if result:
                assert not any('七对' in d for d in result.details)
            output.append(dict(kind='gang', gang_count=count, enabled=enabled, allowed=allowed,
                               trace=trace, fan=None if result is None else result.fan,
                               details=[] if result is None else result.details))
    path = _project_file(_PROJECT_ROOT, HERE / 'chain-report.json')
    path.write_text(json.dumps(dict(scope='本人合法前缀，不计他家先胡概率', cases=output), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(piao_families=len(selected), cases=len(output)), ensure_ascii=False))


if __name__ == '__main__':
    run()
