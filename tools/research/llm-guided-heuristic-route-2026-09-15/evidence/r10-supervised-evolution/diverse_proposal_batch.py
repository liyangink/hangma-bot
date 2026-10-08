"""恢复结案后冻结两种搜索方向：单父代简化M1与无父代结构探索I1。"""

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
import argparse

import strong_seed_batch as b
import route_executor_recovery as recovery

OUT = b.HERE / 'diverse-proposals-20260920'
CONFIGS = {'simplify-terra-max': ('gpt-5.6-terra', 'max', 'm1'),
           'structure-sol-high': ('gpt-5.6-sol', 'high', 'i1')}
COMMON = '''你只作离线算法作者。目标为完整阶段前二效用；改选数、胡牌数、大牌次数与自报分数不替代它。
唯一规则来源是给定合法动作与HangmaRules已生产事实。冻结杭麻规则：只自摸，无点炮/抢杠胡；财神不参与吃碰杠；七对和副露互斥。爆头、财飘、杠链及抓打圈按已给事实，不能照搬其他麻将规则。公开喂牌对他家提速的影响须与点炮风险分开。LLM不进入线上动作闭环。
输入view是纯字典，直接get，不调用.candidate_view，不导入。只读合法可见输入，不重算向听、合法性或结算，不虚构未来牌墙、剩余赛程、真实概率。来源支持枚数及条件结算是启发代理，未知不等于0。
生产分支followup_branches条目有followup_key/followup_discard/combined_shanten/standard_shanten_after/seven_pairs_shanten_after/useful_tiles/support_remaining；可空字段可省略。这里useful_tiles是牌码元组，support_remaining是总枚数。没有hand_codes/progress/route_state。动作级family_progress_entries不是每个分支独立家族事实。routes的useful_tiles才是逐牌{code,remaining_estimate}，conditions用于隔离不同后继，不把互斥收益拼接兑现。followup_branches缺失与routes已知可并存，两路生产隔离；不能抹掉独立已知证据。
用正式未知锚定：布尔不冒充数、无事实动作不越过已知负分动作；全未知按合同弃权。完整输出所有合法动作，每个有限分数及可审计trace。代码短而可核对，说明触发与失败边界，不增加与机制无关的复杂度。
给出一项可手算的非零例、一项退化例及可独立移除的消融说明；例子是合成合同说明，不冒充真实牌局或已测效果。只按正式输出格式交付机制说明、JSON四字段和唯一完整Python源码；不要自称已测试、预计提分或已达发布门禁。
'''


def prepare():
    """全部旧评测终态后签发；不把旧核心成绩或父代登记替换成新证据。"""
    plan = b.read(recovery.OUT / 'manifest.json')
    recovery.verify(plan)
    summary = b.read(recovery.OUT / 'summary.json')
    assert summary['full_tables_verified'] == 512
    for name in recovery.NAMES:
        assert b.read(recovery.OUT / name / 'feedback-consumption-check.json')['ok']
    assert not OUT.exists()
    stats = summary['statistics']
    use_child = (all(stats['candidate'][mix]['mean_delta'] >= stats['parent'][mix]['mean_delta'] for mix in ('H', 'M'))
                 and summary['parent_difference_low'] > 0)
    parent_name = 'candidate' if use_child else 'parent'
    parent = recovery.OUT / parent_name / 'generation'
    parent_sha = b.digest((parent / 'candidate.py').read_bytes())
    feedback = COMMON + '''本次M1只选一个机制做简化，尽量保持不相关行为。允许否定监督者解释，不要求执行某个指定公式或删除某项。问题：父代哪些代理项、最大值选择或重复奖励最可能放大局部偏差？选择一项简化，并说明什么观测会否定你的解释。
不得顺带强制Hu最高、加入统一财神-65项、改未知锚定或重写规则。不同尺度可作为诊断，但本次不是多参数扫描。配对比较反馈仅帮助思考，不是第二父代或交叉任务。
旧核心背景观察（不作当前执行身份的成绩）：route父代两张已见开发清单H/M分别(+0.125,+0.125)、(+0.0625,-0.234375)；hard-terra分别(+0.125,+0.09375)、(+0.03125,-0.046875)。每层8个相关来源根，不代表全局模型排名或显著提升。强制立即Hu消融未改善核心、在第二清单更差；分支来源改名曾完全不改评分；财神代价与家族项混改曾变差，不能单项归因。
本次路线归并暴露执行器普通下标误复制嵌套列表，聚合项意外丢失。缺陷已修复且非零算术通过。旧故障版本的较高开发均值仅提示简化假设，不能继承错误执行器或称原机制有效。当前核心下原父子完整对照如下（均对V2的开发均值）：
'''
    for name in recovery.NAMES:
        feedback += '{}：H {:+.6f}，M {:+.6f}。\n'.format(name, stats[name]['H']['mean_delta'], stats[name]['M']['mean_delta'])
    feedback += '本次绑定父代为{}；它只是探索父代，没有发布资格。\n'.format(parent_name)
    initial = COMMON + '''本次I1无父代源码、无实验成绩。请提出一种连贯且与普通固定权重相加有实质区别的完整动作评分结构。可以考虑分层比较、同一窗口相对刻度或你认为更合理的结构；这些是可选方向，不是指定答案。
重点回答：牌效与条件结算如何比较、相互排斥的后继如何择优、立即收益与条件机会如何区分、缺失事实如何保持保守而不过度抹掉独立已知信息。无需把所有事实都塞入评分，但必须覆盖所有动作并说明未使用的主要信息。说明哪些可见变化会实际改变首选，而不是只换trace名称。不要引入在线搜索、模型服务或新规则计算。
'''
    assert len(feedback) <= 12000 and len(initial) <= 12000
    OUT.mkdir()
    b.write(OUT / 'manifest.json', {'created_at_utc': b.search.utc_now(), 'configs': CONFIGS,
        'parent': str(parent), 'parent_sha256': parent_sha, 'parent_selected_from': parent_name,
        'recovery_summary_sha256': b.digest((recovery.OUT / 'summary.json').read_bytes()),
        'initial_authors': 2, 'max_author_calls': 4, 'max_native_turn_seconds': 1800,
        'native_tokens': 'unknown; reservation charges are not actual usage',
        'third_proposal': '不自动签发；仅在两张已见清单有信号且单参数诊断明确后另冻结',
        'core_tables_per_proposal': 256, 'confirmation_roots': 0, 'release_eligible': False,
        'selection_rule': '先验收独立算术/未知退化/真实改选，再完整评测；H/M对V2均正且对冻结父代等权识别差下界正才投入第二清单。无信号不追加新根或昂贵模型。',
        'archive_note': '显式人工探索父代，尚非自动档案选择'})
    panel = b.HERE / 'batch03-known-root-diagnostic/panel.json'
    for name, (model, effort, operator) in CONFIGS.items():
        sub = OUT / name
        sub.mkdir()
        auth = b.unified_document(batch_label=name, authorization_id='r10-diverse-' + name,
            accounts={'tokens_input': 393216, 'tokens_output': 131072,
                      'tables_full': 300, 'tables_partial': 8, 'prefix_generation': 8},
            issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
        auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
            'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
            'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
            'requested_model': model, 'requested_reasoning_effort': effort,
            'autonomous_admission': False, 'supervisor_feedback': feedback if operator == 'm1' else initial,
            'issuance_basis': '用户持续推进与Terra/Sol作者授权；有界比较简化及结构探索，不增加顶级档位',
            'scope': '开发提案；独立算术与行为检查后才准自然评测；不确认不发布',
            'development_behavior_panel': {'path': str(panel), 'panel_digest': b.behavior.load_panel(panel)[0]}})
        b.write(sub / 'authorization.json', auth)
        state = b.search.av_start_iteration(sub / 'run', operator=operator,
            parent_dir=parent if operator == 'm1' else None, generation_mode='delegate',
            predicate='branch_open', opponent='H', natural_roots=8, natural_seats=4,
            prefix_source='v2_behavior', panel_seed=2026092001, authorization=auth,
            archive_in={'source': 'empty', 'path': None, 'applied_operator': operator,
                        'note': '监督显式选父代/方向，不冒充自动档案选择或群体重组'})
        assert not state.get('stop_reason'), state.get('stop_reason')
        result = b.search.av_iteration_advance(b.search.av_latest_state_path(sub / 'run'), sub / 'run',
            authorization=auth, stop_after='BEHAVIOR_CHECKED')
        assert result.get('waiting_for_reply'), result
        state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
        prompt = b.Path(state['generation']['pending_dir']) / 'prompt.txt'
        b.write(sub / 'author-task.json', {'model': model, 'effort': effort, 'task': operator,
            'prompt': str(prompt), 'prompt_sha256': b.digest(prompt.read_bytes()),
            'reply_path': str(sub / 'author-reply.txt')})
        print(name, len(prompt.read_text()), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'ingest', 'evaluate'])
    parser.add_argument('--name', choices=CONFIGS)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.name:
        b.BATCH = OUT
        b.advance(args.name, args.action == 'evaluate')
    else:
        parser.error('请指定name')
