"""六份受监督种子提案：冻结同题、原生作者交付及公共搜索门禁。"""

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
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / 'tools')))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / 'evidence/v4-impl/r9-gate2/run')))
import sitin_search as search
import sitin_real_behavior as behavior
from p12_authorization import unified_document

BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/strong-seeds-20260920')
CONFIGS = {
    'hard-sol-high': ('gpt-5.6-sol', 'high', 'hard'),
    'hard-terra-max': ('gpt-5.6-terra', 'max', 'hard'),
    'hard-sol-max': ('gpt-5.6-sol', 'max', 'hard'),
    'hard-astra-high': ('gpt-6-astra', 'high', 'hard'),
    'river-sol-high': ('gpt-5.6-sol', 'high', 'river'),
    'route-terra-max': ('gpt-5.6-terra', 'max', 'route'),
}
TASKS = {
    'hard': '探索吃碰后提速与七对/财神路线机会损失之间的取舍。使用现有公开直接牌效、逐弃牌分支及家族/路线证据，在相容条件内构造连贯评分；避免把互斥路线相加、把普通与分支牌效放在不同刻度而无意奖励副露。允许非线性和有明确作用关系的分项；不局限改一个权重。',
    'river': '探索杭麻自摸条件下弃牌熟张与公开副露邻近特征的合理作用。V2熟张+3和领先再+4的防点炮解释不足，但喂他家吃碰提速是独立机制。请提出一个可解释、可消融的弃牌排序机制；不能直接由无点炮推出所有公开对手信息无价值。',
    'route': '探索财神保留与普通型/七对/合法特殊路线的条件价值。优先使用已生产且相容的规则事实，显式区分可达、未分析和证实关闭；不凭未来牌墙或未校准概率许诺大牌收益。允许规则状态与牌效交互，避免无条件堆番或给所有未知路线加分。',
}


def digest(data):
    """计算冻结字节摘要。"""
    return hashlib.sha256(data).hexdigest()


def read(path):
    """读取当前实验的 JSON 证据。"""
    return json.loads(path.read_text())


def write(path, obj):
    """使用公共原子写入，不改写模型原答。"""
    search.av_atomic_write_json(path, obj)


def prepare():
    """预登记六份初答及同一开发清单；只生成题面，不调用作者。"""
    if BATCH.exists():
        raise SystemExit('批次已存在，禁止覆盖')
    parent = _project_file(_PROJECT_ROOT, HERE / 'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py')
    panel = _project_file(_PROJECT_ROOT, HERE / 'batch03-known-root-diagnostic/panel.json')
    source = parent.read_text()
    common = '''本次交付一个增强搜索种子，而不是复刻V2；允许改变动作排序，不要求V2差分等价。
目标是冻结开发赛制下完整阶段前二指标U，不能用改选数/胡牌数/大牌数代替效果。模型只作离线作者；唯一规则来源是投影中的合法动作与已生产规则事实，不重新判断合法性、向听或结算。
view在受限函数中已经是纯字典映射，直接get读取，不得调用view.candidate_view()；合同中的宿主类型签名不是候选代码模板，不给函数写类型注解。不得导入，遵守后附受限语法。完整交付一份源码及I1所需结构化字段。
杭麻依据：本项目冻结规则只允许自摸，不存在点炮/抢杠胡。喂牌对他家提速的影响不能等同点炮风险；财神、七对与副露、爆头/财飘/杠链、抓打圈分别按给定事实判断。不可猜测未投影的剩余赛程；代理分不是概率。使用路线时未知不当0，互斥路径不可叠加，吃碰后弃牌分支必须按真实字段读取。
下面给出经60个范围内差分、64个自然桌赛验证的V2相近工程起点：小样本H/M差值均0，不是已增强算法。你可以复用其接口组织，但不能假定参考源码全域无缺陷。主要已知例外是无过牌等待基线、全未知紧急选择和拒绝重试信息不可见。未知锚定及整批输出必须保持合同正确。
旧机制经验：统一刻度是必要检查；无条件非推进吃碰代价1.5在历史同根开发父代比较中退步，不能只换相邻常数重提；支持枚数截顶16会抹掉真实87/79差异，但更换映射未证实整体增强。这些是有限开发观察，不能泛化成任何局面禁吃碰。
交付说明写清规则依据、可见字段、作用路径、触发、预期变化、反例及如何移除该机制作消融。不需要预测提分。保留短而可核对的说明；没用阶段账就明确声明，勿为了展示数学而加入无关机制。源码不得硬编码开发样本、种子或评测身份。
本题方向：'''
    BATCH.mkdir()
    manifest = {'schema': 'strong-seed-batch/1', 'created_at_utc': search.utc_now(),
        'basis': '用户2026-09-20明确接受六份初答模型配置并要求继续推进',
        'configs': CONFIGS, 'initial_proposals': 6, 'max_author_turns': 12,
        'repair_policy': '每初答最多一次固定实际错误反馈修复；不更换机制，不隐式重试',
        'max_native_turn_seconds': 1800, 'native_usage': 'unknown; counts/wallclock enforced by supervisor; token reservations are accounting, not API-enforced caps',
        'parent_source': str(parent), 'parent_sha256': digest(parent.read_bytes()),
        'panel_seed': 2026092001, 'root_indices': list(range(1, 9)), 'opponents': ['H', 'M'],
        'seats': 4, 'tables_per_arm': 2, 'natural_tables_per_candidate': 256,
        'natural_tables_six_candidates_two_parents': 2048,
        'hard_prompt_sha256': None, 'confirmation_roots': 0,
        'release_eligible': False, 'prompt_policy': '完整正式机器合同保留；短监督目标与可信源码取代上批修复历史；同题提示字节严格一致'}
    write(_project_file(_PROJECT_ROOT, BATCH / 'manifest.json'), manifest)
    for name, (model, effort, task) in CONFIGS.items():
        sub = _project_file(_PROJECT_ROOT, BATCH / name)
        sub.mkdir()
        feedback = common + TASKS[task] + '\n参考工程种子（允许修改）：\n```python\n' + source + '\n```\n'
        if len(feedback) > 12000:
            raise ValueError('任务超过监督备注上界')
        auth = unified_document(batch_label=name, authorization_id='r10-strong-' + name,
            accounts={'tokens_input': 2*196608, 'tokens_output': 2*65536,
                      'tables_full': 300, 'tables_partial': 8, 'prefix_generation': 8},
            issued_by='lead', issued_at_utc=search.utc_now(), legacy_alias=False)
        auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
            'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
            'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
            'requested_model': model, 'requested_reasoning_effort': effort,
            'autonomous_admission': False, 'supervisor_feedback': feedback,
            'issuance_basis': manifest['basis'], 'scope': '监督开发种子，8根/层，共同核心面板，不确认不发布',
            'development_behavior_panel': {'path': str(panel), 'panel_digest': behavior.load_panel(panel)[0]}})
        write(sub / 'authorization.json', auth)
        state = search.av_start_iteration(sub/'run', operator='i1', generation_mode='delegate',
            predicate='branch_open', opponent='H', natural_roots=8, natural_seats=4,
            prefix_source='v2_behavior', panel_seed=2026092001, authorization=auth,
            archive_in={'source':'empty','path':None,'applied_operator':'i1',
                        'note':'工程种子知情的新机制初答；不继承历史效果成绩'})
        if state.get('stop_reason'):
            raise RuntimeError(state['stop_reason'])
        result = search.av_iteration_advance(search.av_latest_state_path(sub/'run'), sub/'run',
            authorization=auth, stop_after='BEHAVIOR_CHECKED')
        if not result.get('waiting_for_reply'):
            raise RuntimeError(str(result))
        state = search.av_state_load(search.av_latest_state_path(sub/'run'))
        prompt = Path(state['generation']['pending_dir'])/'prompt.txt'
        if task == 'hard':
            if manifest['hard_prompt_sha256'] is None:
                manifest['hard_prompt_sha256'] = digest(prompt.read_bytes())
            if digest(prompt.read_bytes()) != manifest['hard_prompt_sha256']:
                raise RuntimeError('同题提示字节不同')
        write(sub/'author-task.json', {'model': model, 'effort': effort, 'task':task,
            'prompt':str(prompt), 'prompt_sha256':digest(prompt.read_bytes()),
            'reply_path':str(sub/'author-reply.txt')})
        print(json.dumps({'name':name,'status':state['status'],'prompt_chars':len(prompt.read_text())}), flush=True)
    write(_project_file(_PROJECT_ROOT, BATCH/'manifest.json'),manifest)


def advance(name, evaluate=False):
    """摄入作者原答并运行公共门禁；效果评价须先有监督源码裁定。"""
    sub=_project_file(_PROJECT_ROOT, BATCH/name); root=sub/'run'
    if (sub/'batch-closure.json').exists():
        raise SystemExit('提案已关闭')
    path=search.av_latest_state_path(root); state=search.av_state_load(path)
    ok, why, _=search.av_verify_run_identity(state)
    if not ok:
        raise SystemExit(why)
    task=read(sub/'author-task.json')
    envelope=Path(state['iter_dir'])/'reply-envelope.json'
    if not evaluate and not envelope.exists():
        done=read(sub/task.get('completion_file','author-completion.json'))
        dispatch=read(sub/task.get('dispatch_file','author-dispatch.json'))
        reply=Path(task['reply_path']).read_text()
        if done['reply_sha256']!=digest(reply.encode()) or done['agent_task']!=dispatch['agent_task']:
            raise SystemExit('交付证据不符')
        if task['prompt_sha256']!=state['generation']['prompt_sha256']:
            raise SystemExit('题面身份不符')
        write(envelope, {'schema':'sitin-generation-reply/1','origin':'delegated_model_reply',
            'prompt_sha256':task['prompt_sha256'],'reply':reply,'provider':'codex-native',
            'model':task['model'],'captured_at_utc':search.utc_now(),
            'delegator':'root supervised native author','usage':None,
            'usage_source':'unavailable_native_subagent','evidence':str(sub/task.get('dispatch_file','author-dispatch.json')),
            'info_boundary':'instruction-only read frozen prompt/write reply; tools not capability-disabled'})
    if evaluate:
        verdict=read(sub/'source-review.json')
        source=Path(state['iter_dir'])/'generation/candidate.py'
        if verdict.get('allow_development_evaluation') is not True or verdict['source_sha256']!=digest(source.read_bytes()):
            raise SystemExit('缺少匹配源码的监督裁定')
    auth_path=sub/'authorization-repair.json'
    if not auth_path.exists():
        auth_path=sub/'authorization.json'
    result=search.av_iteration_advance(path,root,authorization=read(auth_path),
        stop_after=None if evaluate else 'BEHAVIOR_CHECKED')
    print(json.dumps({k:result.get(k) for k in ('status','advanced','terminal','refused','waiting_for_reply')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','ingest','evaluate'])
    p.add_argument('--name',choices=list(CONFIGS))
    args=p.parse_args()
    if args.action=='prepare': prepare()
    elif args.name: advance(args.name,args.action=='evaluate')
    else: p.error('指定提案名')
