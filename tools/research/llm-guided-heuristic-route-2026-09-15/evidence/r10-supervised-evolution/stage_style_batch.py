"""使用阶段积分对齐单一名次风格机制；冻结一份M1与固定开发评价。"""

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
import revalidate_v2_search_parent as parent_run
import diverse_proposal_batch as previous
import strong_seed_results as results
from compare_refinement_terminals import compare

OUT = b.HERE / 'stage-style-20260920'
NAME = 'stage-style-terra-max'


def prepare():
    """按真实分歧冻结一份M1、最多一次合同修复；不预先指定结果或追加模型档位。"""
    assert not OUT.exists()
    assert b.read(parent_run.OUT / 'summary.json')['status'] == 'COMPLETE_DEVELOPMENT_ONLY'
    assert b.read(parent_run.OUT / 'parent/feedback-consumption-check.json')['ok']
    parent = parent_run.OUT / 'parent/generation'
    diagnosis = b.HERE / 'stage-rank-preflight-20260920'
    evidence = b.read(diagnosis / 'audit.json')
    assert evidence['different_rank_with_discard'] > 0
    instruction = previous.COMMON + '''本次M1唯一父代为当前核心重新验收的V2相近种子。只修改“名次风格”这一机制的依据与触发，不改基础向听/有效牌、熟张基础项、公开副露邻近项、财神保留与弃财神代价、胡牌优先层、吃碰杠评分、未知锚定。不以升级模型或邻近阈值扫描代替新假设。
当前父代只读取visible_state.table_scores，以严格高于本座位的人数+1构造table_rank，并仅在discard上添加style_part：rank1且熟张+4；rank4且最小向听+2。目标却是完整阶段前二效用。competition.current_stage_scores是已完成桌账stage_scores加当前桌账table_scores，逐座位相加的当前阶段合计；不能再次加当前桌账。freshness_masks为stage_account:complete时可用；缺失/陈旧/无法映射不可猜0。请严格读取正式合同，缺账时保持原父代的本桌策略，不强行全局弃权或删除独立已知事实。
已保存112检查输入（64真实、24条件、24故障）中7个窗口本桌/阶段严格排名不同，5个含弃牌，其中4个有胡牌，因此这些计数不代表存在5次可盈利改选。真实例：座位1本桌(32,-29,-28,25)排名4，阶段合计(36,-19,-31,14)排名3；另一个开桌窗口本桌全0，阶段(-15,-14,-7,36)，座位1按本桌并列首位而阶段为第3。这是信息基准差异，不证明旧动作错或阶段名次能预测未来结果。
可证伪问题：如何用已知当前阶段位置定义一致的弃牌名次风格，使它服务前二目标，并谨慎对待并列？可以保留原触发含义仅换基准，也可选择更合适且可独立移除的单项名次风格机制；由你判断，不要求某个指定公式。保持奖励/惩罚在原风格项的小尺度内，不能借此重写整套评分或隐含增加条件结算奖励。缺少阶段账时精确保留父代行为。没有未来剩余桌数/阶段剩余手数/他家手牌，禁止臆造。
必须明确：当前积分名次不是最终晋级概率，第一名并列不一定安全，严排名2也可能多人同分争夺边界。不要通过任意tie-break当成权威顺序；若选择保守并列范围只依据已给积分，不伪造名次分/白板数。不能把提前保守等同一定晋级。
反馈：父代在当前256桌清单对V2 H/M均0。上一个单机制弃牌支持保护在首答有锚点数学错误，修复后H +0.15625/M -0.09375，因M负停止。此前路线简化第一清单正、第二清单负。以上均说明局部合理性不足以证明效果，本次不恢复失败机制。
请给完整可执行源码、目标/非目标边界、至少一个非零手算、一个并列例、一个缺账退化例，以及移除机制的方法。原常数如需调整必须仅属于style_part，解释单位与作用，不做多参数扫描。独立验收后才评测。'''
    assert len(instruction) <= 12000
    OUT.mkdir()
    sub = OUT / NAME
    sub.mkdir()
    sha = b.digest((parent / 'candidate.py').read_bytes())
    b.write(OUT / 'manifest.json', {'created_at_utc': b.search.utc_now(), 'parent': str(parent),
        'parent_sha256': sha, 'diagnostic_sha256': b.digest((diagnosis / 'audit.json').read_bytes()),
        'model': 'gpt-5.6-terra', 'effort': 'max', 'initial_authors': 1, 'max_author_calls': 2,
        'max_native_turn_seconds': 1800, 'core_tables': 256, 'conditional_full_cap': 4,
        'selection_rule': '完整H/M对V2均正且对冻结父代等权识别差下界正才签发第二已见清单；否则本提案停止追加',
        'scope': '单名次风格M1，缺阶段账精确保留父代；非调参扫描',
        'confirmation_roots': 0, 'release_eligible': False})
    panel = b.HERE / 'piao-opportunity-probe-20260920/panel.json'
    auth = b.unified_document(batch_label=NAME, authorization_id='r10-'+NAME,
        accounts={'tokens_input': 393216, 'tokens_output': 131072, 'tables_full': 300,
                  'tables_partial': 8, 'prefix_generation': 8},
        issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
        'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
        'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
        'requested_model': 'gpt-5.6-terra', 'requested_reasoning_effort': 'max',
        'autonomous_admission': False, 'supervisor_feedback': instruction,
        'issuance_basis': '用户持续推进和原生Terra作者授权；现有输入证明名次基准不一致，单份M1，不升级顶级模型',
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
        'v2-like-parent': {'dir': parent.parent, 'source_sha256': manifest['parent_sha256']}})
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    b.write(sub / 'parent-terminal-comparison.json', compare(SimpleNamespace(
        ROOT=OUT, NAME=NAME, PARENT=parent, ITER_DIR=state['iter_dir'])))
    closure = b.read(sub / 'batch-closure.json')
    paired = closure['versus_parents']['v2-like-parent']
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
