"""只探索普通型与七对的后续选择余地；紧凑反馈M1与固定开发评价。"""

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

OUT = b.HERE / 'pattern-option-20260920'
NAME = 'pattern-option-terra-max'


def prepare():
    """按真实分歧冻结一份M1、最多一次合同修复；不预先指定结果或追加模型档位。"""
    assert not OUT.exists()
    assert b.read(parent_run.OUT / 'summary.json')['status'] == 'COMPLETE_DEVELOPMENT_ONLY'
    assert b.read(parent_run.OUT / 'parent/feedback-consumption-check.json')['ok']
    parent = parent_run.OUT / 'parent/generation'
    diagnosis = b.HERE / 'pattern-option-preflight-20260920'
    evidence = b.read(diagnosis / 'audit.json')
    assert evidence['near_seven_without_hu'] > 0
    instruction = previous.COMMON + """本次M1唯一父代是当前核心验收的V2相近种子。只探索普通型与七对在弃牌后的后续选择余地，不修改吃碰杠、胡牌优先层、财神保留/弃财神代价、公开熟张/邻近/名次分项和未知锚定，不恢复旧路线父代。机制仅影响直接已知hand_progress弃牌；新分牌型事实缺失或不可信时原父代该动作评分精确退化，不把独立已知直接牌效抹成未知。
可证伪问题：父代的综合最小向听与综合有效牌有时掩盖第二种牌型的不同距离；当两弃牌综合牌效相近，而普通型/七对的距离、有效牌支持不同，是否有一个简单、可独立移除的机制保留有价值的后续选择？由你决定方向和公式，也可以否定七对普遍应受奖励。不得把七对向听无条件减常数，不把所有family_progress_entries的advance直接加分，不为了命中十个例子写样本识别。允许保持牌效优先并细化；请解释何时应该完全不奖励。
覆盖观察：已有64个真实观察、372个弃牌动作，0个直接已知有效牌总量为0，因此本批不投入死等牌机制；10个无合法Hu窗口存在七对向听<=普通向听+1的弃牌。这个+1仅是诊断计数定义，不是指定算法阈值。例：两种弃牌综合向听均2、支持均24，一者普通2/七对5，另一者普通2/七对4；还有开局普通4/七对4、综合支持79与普通5/七对4、支持33的区别。后者父代已明显区分，不能重复计算并声称新增信息。观察不证明哪一动作更好。对方手牌和未来牌墙未知。
已生产字段：动作级standard_shanten_after、seven_pairs_shanten_after、standard_useful_tiles、seven_pairs_useful_tiles，后两者为逐牌{code,remaining_estimate}；None是未知或七对不适用，空集合是已知空。具体参见正式合同。可使用这些事实及visible_state，不重算规则/向听/牌型，不依赖兼容但未生产的hand_codes。普通型和七对的有效牌可能重叠，不能重复算张数；最优向听相同的综合有效牌已经并集，不再次给同一事实两份奖励。次优牌型的有效牌未必推进综合向听。支持是公开未见枚数，不是摸到概率，也不证明将来能形成七对。
规则依据：冻结官方指南v34（2026-09-15本地快照）和唯一HangmaRules，七对要求无副露（含暗杠），财神可补对；七对的条件翻倍不等于当前晋级概率或期望积分，豪华和四白规则不能自行补结算。YouCaiBiKao按给定事实；规则引擎合法动作不改。
父代在当前256桌开发清单H/M均0。此前公开弃牌偏好取舍M1为H +0.15625/M -0.09375；阶段名次风格为H +0.03125/M 0，两者均停止。旧全局路线简化第一清单正而第二清单负。它们不证明本机制有效，也不能为重开原阈值扫描辩护。本任务是不同事实的单机制探索，保留父代其余丰富行为，不接受只改trace来源名称。
交付完整源码、一个非零手算、一个相同综合牌效但第二牌型不同的边界例、一个分牌型信息缺失时严格退化例，并说明移除新机制如何恢复父代。新分数的单位是启发偏好而非番数或真实收益，不应破坏主向听尺度；若新增常数，只给一个固定方案和理由，不列参数网格。不要为了减少提示把正式合同省掉。本次原始长动作前缀已用可核验摘要替代，原轨迹未随正文送达，不需要读取其路径。
"""
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
        'scope': '普通/七对后续选择单机制；compact_prefix_v1首次作者使用，非压缩效果对照',
        'author_feedback_mode': 'compact_prefix_v1',
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
        'autonomous_admission': False, 'author_feedback_mode': 'compact_prefix_v1', 'supervisor_feedback': instruction,
        'issuance_basis': '用户持续推进和原生Terra作者授权；现有输入证明分牌型后续距离不同，单份M1，不升级顶级模型',
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
