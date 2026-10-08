"""从未晋升凝聚度父代研究共享支撑竞争；固定单机制和开发对照。"""

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
from types import SimpleNamespace

import strong_seed_batch as b
import diverse_proposal_batch as previous
import strong_seed_results as results
from compare_refinement_terminals import compare

OUT = b.HERE / 'support-competition-20260920'
NAME = 'support-competition-terra-max'


def prepare():
    """按真实分歧冻结一份M1、最多一次合同修复；不预先指定结果或追加模型档位。"""
    assert not OUT.exists()
    parent = b.HERE / 'comparable-shape-20260920/comparable-shape-terra-max/run/iterations/iter-01/generation'
    binding = b.search.av_generate().av_parent_binding(parent)
    _, verdict = b.search._av_m1_feedback({'plan': {'parent_dir': str(parent), 'parent_candidate_id': binding['candidate_id']}})
    assert verdict['ok'], verdict
    old_decision = b.read(b.HERE / 'comparable-shape-second-dev-20260920/summary.json')
    assert old_decision['continue_new_development'] is False
    diagnosis = b.HERE / 'comparable-shape-second-diagnostic-20260920'
    evidence = b.read(diagnosis / 'audit.json')
    assert evidence['status'] == 'COMPLETE_DIAGNOSTIC_ONLY'
    instruction = previous.COMMON + '本次M1从未晋升的统一残余结构研究父代提出一个新机制：共享支撑牌竞争。父代首清单256桌H +0.21875/M +0.03125，等权+0.125；第二张已见清单父子共512桌，父代本身对V2 H +0.125/M -0.03125，等权+0.046875。虽然超过其自己的父代，但按H/M均正的预先条件停止扩评，不进入未见验证或确认。请不要把第一清单的正反馈当已晋升；后附标准M1反馈来自首清单，第二清单失败以本段为完整补充。源码身份一直不变。\n已按确定规则重放第二清单M最早严格负案例与H最早严格正案例，双臂8桌终局全部复现。2945请求，候选对V2首选变化21次，保存17个改选记录中16个是V2平分，1个跨激活边界。双臂共享窗口不能当独立样本；局部动作没有正负真值，H/M不同牌山不能因果归于对手类型。\nM负例首次V2分歧：弃6b/9b同为-317，综合/普通/七对向听均4；弃6b后连接8孤张5获+0.6，弃9b后连接9孤张4获+1.0，改选9b。两边都激活且未截顶。本窗口含5b、5b、6b：两张5b被记为对子连接，而6b又依赖5b被记为邻接连接。每个牌位只归一个类别不等于其支撑牌没有被其他机会重复使用。这是启发特征局限，不是已证实规则错误或该负终局的原因。\nH正例首次V2分歧：弃2w/7t同为-246，综合/普通/七对向听均3；弃2w后连接11孤张2得+1.8，弃7t后连接13孤张0截顶+2.0，改选7t。正负例均普通型和七对向听相同，不能为消除负例就机械禁用全部两路线并列。上一父代129固定输入中187个激活条目60个达到截顶；本次不扫0.2/10或激活阈值，不用截顶统计伪装新机制。\n新机制任务：给出一种计算有界、可解释的残余结构机会代价或保留价值，显式处理多个连接机会争用同一自然牌的问题，同时允许结构重组。可以否定监督者解释并提出同范围更合理的量，但只能交付一份实质新候选。55+6呈现竞争，44556却可以重组成456和45，所以不能简单“先抽尽对子，再把邻牌视为孤张”；已成顺子、刻子、对子及重叠搭子也不能任意因遍历顺序得到不同分数。牌形是结构示例，不是让你硬编码它们或自行实现杭麻裁定。\n只整体替换父代 residual_v2 计算块及一次加分/trace，不叠加旧shape或别的机制；默认保留当前可信直接hand_progress、普通型最优且当前最佳向听的作用边界。解释普通/七对同向听时该代理如何偏好、何时会错，不能把两路线互斥收益相加。结构量只作依法可见手牌特征，不能导入生产模块、重新计算向听/胡牌/合法性/结算，不能在受限评分器内另造完整规则引擎。若需要合同没有的精确两步规则事实，应明确指出，不能虚构字段或将近似称为规则真值。不用无界递归、指数枚举完整分解或在线搜索；说明最坏手牌长度/动作数下的循环上界与退化路径。\n其他基础评分保持父代：胡排序层、财神保留/弃财神代价、熟张与喂牌分项、名次风格、吃碰杠/过牌策略和最终未知锚定不改。胡数值随已知最大分变化允许，但胡首选不变。新结构要对数牌/普通字牌使用同一可比口径，白/财神不是普通字牌，不把财神当自然连接支撑。原规则事实裁定七对/副露资格。公开有效牌枚数不是摸牌概率，启发结构量不是额外可兑现面子或期望番数。\n完整手牌语义：my_hand不包含独立drawn_tile。本人副露组数m=melds[seat]组数。drawn_tile非None时my_hand应13-3m张，追加摸牌恰好一次，即便该码已在手里；drawn_tile=None时应14-3m张，直接复制。逐张保留重复，从完整手牌恰减候选弃牌一次。缺支持事实、形状异常、候选不在手中时，新结构项为0，退回不含新旧结构项的V2相近基础评分；不能把独立已知牌效抹成未知。followup_branches仅吃碰后弃牌，不提供普通弃牌下一摸再弃的分析；无hand_codes字段。\n交付：完整受限Python源码和正式四字段。说明相较父代的实质变化、数学单位/上下界、负修正后的未知锚定、循环上界、规则依据与反例；至少手算一组共享支撑竞争、一组可重组结构、一组已成结构、一组字牌/数牌比较、一组重复摸牌/副露/财神边界及缺证据退化。不预报涨分或声称已测试。移除整个新机制应机械回到无结构的V2相近基础，恢复原residual_v2即是父代消融，不靠保留不同旧项造成混杂。监督者会先独立算术与生产选择核验，再固定H/M核心；负效果不会获得调参修复。不得识别案例组合、余牌数、root、来源身份或终局标签。'
    assert len(instruction) <= 12000
    OUT.mkdir()
    b.write(OUT / 'parent-feedback-consumption-check.json', verdict)
    sub = OUT / NAME
    sub.mkdir()
    sha = b.digest((parent / 'candidate.py').read_bytes())
    b.write(OUT / 'manifest.json', {'created_at_utc': b.search.utc_now(), 'parent': str(parent),
        'parent_sha256': sha, 'diagnostic_sha256': b.digest((diagnosis / 'audit.json').read_bytes()),
        'model': 'gpt-5.6-terra', 'effort': 'max', 'initial_authors': 1, 'max_author_calls': 2,
        'max_native_turn_seconds': 1800, 'core_tables': 256, 'conditional_full_cap': 4,
        'selection_rule': '完整H/M对V2均正且对冻结父代等权识别差下界正才签发第二已见清单；否则本提案停止追加',
        'scope': '共享支撑竞争的新结构机制；未晋升研究父代，不扫旧常数，不重建规则引擎',
        'author_feedback_mode': 'compact_prefix_v1',
        'confirmation_roots': 0, 'release_eligible': False})
    panel = diagnosis / 'panel.json'
    auth = b.unified_document(batch_label=NAME, authorization_id='r10-'+NAME,
        accounts={'tokens_input': 393216, 'tokens_output': 131072, 'tables_full': 300,
                  'tables_partial': 8, 'prefix_generation': 8},
        issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
        'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
        'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
        'requested_model': 'gpt-5.6-terra', 'requested_reasoning_effort': 'max',
        'autonomous_admission': False, 'author_feedback_mode': 'compact_prefix_v1', 'supervisor_feedback': instruction,
        'issuance_basis': '用户持续推进和原生Terra作者授权；已完成第二清单正负诊断，一份共享支撑竞争M1；最多一次合同修复，负效果不修复',
        'scope': '源码、独立算术与生产触发验收后才评测；负效果不触发修复',
        'development_behavior_panel': {'path': str(panel), 'panel_digest': b.behavior.load_panel(panel)[0]}})
    b.write(sub / 'authorization.json', auth)
    state = b.search.av_start_iteration(sub / 'run', operator='m1', parent_dir=parent,
        generation_mode='delegate', predicate='branch_open', opponent='H', natural_roots=8,
        natural_seats=4, prefix_source='v2_behavior', panel_seed=2026092001, authorization=auth,
        archive_in={'source': 'empty', 'path': None, 'applied_operator': 'm1',
                    'note': '监督按诊断显式选择父代，非自动档案选父'})
    assert not state.get('stop_reason'), state.get('stop_reason')
    result = b.search.av_iteration_advance(b.search.av_latest_state_path(sub / 'run'), sub / 'run',
        authorization=auth, stop_after='BEHAVIOR_CHECKED')
    assert result.get('waiting_for_reply'), result
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    prompt = b.Path(state['generation']['pending_dir']) / 'prompt.txt'
    b.write(sub / 'author-task.json', {'model': 'gpt-5.6-terra', 'effort': 'max', 'task': 'm1',
        'prompt': str(prompt), 'prompt_sha256': b.digest(prompt.read_bytes()), 'reply_path': str(sub / 'author-reply.txt')})
    print('prepared', len(prompt.read_text()), flush=True)


def close():
    """开发评价完整结束后同根核对，不合并新旧核心成绩。"""
    manifest = b.read(OUT / 'manifest.json')
    parent = b.Path(manifest['parent'])
    sub = OUT / NAME
    results.summarize(NAME, candidate_dir=sub, parent_specs={
        'unpromoted-cohesion-parent': {'dir': parent.parent, 'source_sha256': manifest['parent_sha256']}})
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    b.write(sub / 'parent-terminal-comparison.json', compare(SimpleNamespace(
        ROOT=OUT, NAME=NAME, PARENT=parent, ITER_DIR=state['iter_dir'])))
    closure = b.read(sub / 'batch-closure.json')
    paired = closure['versus_parents']['unpromoted-cohesion-parent']
    keep = paired['equal_mix_low'] > 0 and all(s['mean_delta'] > 0 for s in closure['versus_v2'].values())
    b.write(sub / 'development-decision.json', {'continue_second_seen_panel': keep,
        'interval_kind': '平分识别区间，非置信区间', 'release_eligible': False})
    print('continue_second_seen_panel', keep)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'ingest', 'evaluate', 'close'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'close':
        close()
    else:
        b.BATCH = OUT
        b.advance(NAME, args.action == 'evaluate')
