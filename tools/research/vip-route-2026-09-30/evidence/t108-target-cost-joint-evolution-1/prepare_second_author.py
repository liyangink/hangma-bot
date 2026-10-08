"""以闭合正反证据冻结本批第二作者；缩短输入但不删机械合同。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import run_vip_eoh_generate

HERE = Path(__file__).resolve().parent


def canonical(value):
    """精确公共事实编码；未知与空值保持原样。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """流式绑定公开输入字节，绝不读取凭据。"""
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
            size += len(b)
    return {'bytes': size, 'sha256': h.hexdigest()}


def save(path, value):
    """准备只新建；原S01包、面板和读回不修改。"""
    with path.open('xb') as f:
        f.write(canonical(value) + b'\n')


def main():
    """第二作者只收到本座公开事实；32源已转开发，128确认源未启。"""
    campaign = _project_file(_PROJECT_ROOT, HERE / 'S01-natural-development-1')
    result = json.loads((campaign / 'CAMPAIGN-CLOSURE.json').read_text())
    assert result['whole_batch_valid'] and not result['predeclared_confirmation_start_screen_passed']
    panel = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json')).read_text())
    assert len(panel['cases']) == 98
    selected, inputs = [], []
    for case in ('root003-loss', 'root030-gain'):
        path = _project_file(_PROJECT_ROOT, HERE / ('S01-fresh-' + case))
        readback = json.loads((path / 'ROOT-READBACK.json').read_text())
        terminal = json.loads((path / 'ACTUAL-READBACK-TERMINAL.json').read_text())
        assert readback['complete'] and readback['P_and_C_original_whole_tail_exact']
        assert terminal['exit_code'] == 0
        public = json.loads((path / 'PUBLIC-TARGETS.json').read_text())['targets']
        p, c = (next(r for r in public if r['arm'] == a) for a in ('P', 'C'))
        with gzip.open(path / 'PUBLIC-VIEWS.jsonl.gz', 'rt') as stream:
            views = {r['view_sha256']: r['view'] for r in map(json.loads, stream)}
        selected.append({'label': case, 'complete_public_view': views[p['view_sha256']],
            'P_first': p['original_first'], 'S01_first': c['original_first'],
            'P_scores': p['original_full_scores'], 'S01_scores': c['original_full_scores'],
            'current_hand_observed': {a: {
                'executed_first': r['executed_first'], 'focal_net_score': r['focal_net_score'],
                'fan': r['settlement']['fan'], 'winner_seat': r['settlement']['winner_seat']}
                for a, r in readback['results'][0]['results'].items()},
            'not_optimal_action_gold': True})
        panel['cases'].append({'label': 'T108:' + case, 'observation': p['observation'],
            'window_key': p['window_key'], 'parent_first': p['original_first'],
            'parent_scores': [{'action_key': r['action_key'], 'score': r['score'], 'trace': r['trace']}
                              for r in p['original_full_scores']], 'view_sha256': p['view_sha256']})
        inputs.extend([path / n for n in ('PUBLIC-TARGETS.json', 'PUBLIC-VIEWS.jsonl.gz',
                                         'ROOT-READBACK.json', 'ACTUAL-READBACK-TERMINAL.json')])
    panel['scope'] = '100 exposed public development windows; no optimal-action gold labels'
    save(_project_file(_PROJECT_ROOT, HERE / 'S02-PUBLIC-PANEL.json'), panel)
    # 旧大图只给原观察、实际父评分及现有等待事实，不复制整棵条件图。
    prior = json.loads((_project_file(_PROJECT_ROOT, HERE / 'SELECTED-PUBLIC-FEEDBACK.json')).read_text())['cases']
    controls = []
    for label in ('T105:954', 'T94:1757', 'T96:1815'):
        r = next(x for x in prior if x['label'] == label)
        v = r['complete_public_view']
        controls.append({'label': label, 'observation': r['observation'], 'T101_first': r['T101_first'],
            'T101_scores': r['T101_scores'], 'actions': v['actions'],
            'waiting_facts': [dict(node_key=n['node_key'], kind=n['kind'], waiting=n['waiting'])
                              for n in v['nodes'] if n['waiting'] is not None],
            'scope': 'public waiting leaves only; conditional edges deliberately omitted from this feedback summary'})
    prefix = '''这是本批第二且最后一份m1完整联合公式提案。正式父是T101；S01只是已验证的修改反例。
保持速度、有效码多样性、自然成型、保白高番和当前胡/等的联合权衡，不新增规则、隐藏信息或长期精确期望分前置。
S01仅删掉中间保白目标对最终自然准备负担的比例继承。新32开发源512实际桌全核齐：
S01相对父每桌-0.75（30源终分持平、1负1正）；相对R18-4.3046875。相对父普通胡-100、高番+40、支付-36，总-96。
高番新增仅一源，不能推广。父在这32源相对R18-3.5546875；更早128源确认+5.2754且区间跨零、高番-240。
两个新共同起点已实际整段续打，各父/子/R18三臂，并复现两版原轨迹与分值：
正例二白、三副露：父/R18立即两番20，S01继续后四番40。负例三白、零副露：父/R18两番20，S01继续后下一家先胡，本人-8。
不能把一次未知他家胡解释成当时必然该胡；这些是开发正反例，不是动作金标，也不要写“两白等、三白胡”的案例分支。
两手都保持很宽的普通听牌，但自然准备分别还需1和2张；目标自身下界与最后自然成型成本需要一致定价，既避免重复负担，也避免便宜中间目标掩盖后续代价。
优先研究连续的目标完成代价/升级收益/备用普通出口组织；可用实际下一摸合法支付、自然进张宽度、剩余牌山、公开副露与庄家事实。
允许一定普通效率损失，条件是跨来源实际高番收益覆盖；不要简单抬所有等待、保白、闭门或七对的分值。
仍须能优化早期弃牌的自然发展和进张范围，不仅改单个当前Hu阈值；已有早期正例、当前胡负控、自然准备正控必须作为反思材料。
不得硬编码本例牌码、来源、序号、结局或使用他家暗牌/未来牌墙。保持全部合法根、条件分支和未知状态；按只读合同交付完整可执行源码与真实m1机制说明。
第一版赛事压力只记录，不加入排名奖金策略。既有预算、官方支付和规则模块不改。对结果应克制，不宣称精确概率或已增强。
以下仅依法可见完整DTO及实际开发成绩，不包含恢复轨迹、其他座位暗牌、牌墙或未曝光确认种子。
'''
    feedback = prefix + canonical({'new_public_cases': selected, 'older_public_controls': controls}).decode()
    (_project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt')).write_text(feedback)
    parent = _project_file(_PROJECT_ROOT, HERE.parent / 't101-joint-breadth-recovery-author-1/S02-model-output')
    emission = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission'), operator='m1', parent_paths=[parent], feedback=feedback)
    assert emission['status'] == 'prompt_emitted' and emission['identity_stable']
    for old_name, new_name in [('probe.py', 'S02-probe.py'), ('read_probe.py', 'S02-read-probe.py')]:
        text = (_project_file(_PROJECT_ROOT, HERE / old_name)).read_text().replace('98', '100')
        text = text.replace('AUTHOR-PREPARATION-CLOSED.json', 'S02-AUTHOR-PREPARATION-CLOSED.json')
        text = text.replace('PUBLIC-PANEL.json', 'S02-PUBLIC-PANEL.json')
        ast.parse(text)
        (_project_file(_PROJECT_ROOT, HERE / new_name)).write_text(text)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'), _project_file(_PROJECT_ROOT, HERE / 'EVOLUTION-PLAN.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S02-PUBLIC-PANEL.json'), _project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt'), _project_file(_PROJECT_ROOT, HERE / 'S02-probe.py'),
        _project_file(_PROJECT_ROOT, HERE / 'S02-read-probe.py'), _project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json'),
        campaign / 'CAMPAIGN-CLOSURE.json', campaign / 'ACTUAL-READBACK-TERMINAL.json',
        parent / 'candidate.py', parent / 'generation.json'] + inputs
    save(_project_file(_PROJECT_ROOT, HERE / 'S02-AUTHOR-PREPARATION-CLOSED.json'), {'complete': True,
        'stage': 'before_real_model_call', 'new_models_rules_scores_worlds_tables': 0,
        'frozen_files': {str(p): pin(p) for p in files}, 'prompt_sha256': emission['prompt_sha256'],
        'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt')).stat().st_size,
        'public_windows': 100, 'only_author_slot_remaining': 'S02', 'confirmation_started': False,
        'development_sources_reused_explicitly': True, 'model': 'glm-5.3',
        'reasoning_effort': 'not sent by existing API backend; provider default'})
    print({'prepared': True, 'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt')).stat().st_size,
           'public_windows': 100, 'real_model_calls': 0})


if __name__ == '__main__':
    main()
