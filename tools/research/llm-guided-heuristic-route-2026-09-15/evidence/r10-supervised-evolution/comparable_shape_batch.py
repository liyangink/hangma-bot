"""以未晋升研究父代提出统一残余结构；独立身份、固定开发对照。"""

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

OUT = b.HERE / 'comparable-shape-20260920'
NAME = 'comparable-shape-terra-max'


def prepare():
    """按真实分歧冻结一份M1、最多一次合同修复；不预先指定结果或追加模型档位。"""
    assert not OUT.exists()
    parent = b.HERE / 'discard-shape-20260920/discard-shape-terra-max/run/iterations/iter-02/generation'
    binding = b.search.av_generate().av_parent_binding(parent)
    _, verdict = b.search._av_m1_feedback({'plan': {'parent_dir': str(parent), 'parent_candidate_id': binding['candidate_id']}})
    assert verdict['ok'], verdict
    old_decision = b.read(b.HERE / 'discard-shape-20260920/discard-shape-terra-max/development-decision.json')
    assert old_decision['continue_second_seen_panel'] is False
    diagnosis = b.HERE / 'discard-shape-mix-diagnostic-20260920'
    evidence = b.read(diagnosis / 'audit.json')
    assert evidence['status'] == 'COMPLETE_DIAGNOSTIC_ONLY'
    instruction = previous.COMMON + '本次M1从未晋升的弃牌结构研究父代提出新的统一残余结构机制，不是第三次修复或旧权重扫描。父代已修正完整可见手牌表示；完整核心256桌H +0.1875、M -0.03125、等权+0.078125，按运行前H/M均正条件停止晋升。不能将它说成已增强或已通过，也不能以低于V2却高于父代的结果晋升。\n已完成M最早正/负案例对称重放，双臂8桌全部复现，2603请求19改选，其中13个父代平分、9个跨旧结构项激活边界。终局标签不能证明某个局部动作正确，H/M不同牌山不能归因为对手类型。\n诊断例一：正M首次分歧，父代的父代给弃1w/发同为-265，直接向听3、支持35。当前研究父代给弃1w后3个孤张修正-1.5，弃发因为动作不是数牌而完全不计算结构，修正0。数牌残余量在不同弃牌类型没有共同计算口径。例二：负M首次分歧，弃2b/6t原分都-81、向听1；当前父代分别残留1孤张(-0.5)或1活隔张(+0.5)，两者都激活，不能把所有失败归于字牌。另一负案例父代原分西-67、9b-68，9b结构+1.5后反超，其直接支持枚数22对26，说明不只打破平分。\n本次新假设：在既有直接牌效上，用同一可见手牌结构量衡量不同弃牌后的保留价值，消除“字牌动作免算、数牌动作承担整手代价”等隐含不对称；同时明确字牌孤张、成对、数牌相邻/隔张结构和财神不可直接类比的边界。由你选择一种一致的数学口径，可用共同基准的结构变化或其他连贯方案，不预先指定公式。仅把旧0.5/4改成相邻常数、仅改旧手牌拼接、仅把数牌限制去掉但不解释字牌残余结构，都不算新机制。允许否定监督者假设并给出同范围合理机制，必须恰好一份、可独立消融，不多方案网格。\n保留父代其他评分行为；只替换旧的shape_part机制，不叠加两个结构项。不得改胡优先、财神原代价、公开河牌/喂牌分项、吃碰杠/过牌策略及最终未知锚定。胡数值随已知最大分变化允许，但全批胡优先必须不变。限定直接可信hand_progress弃牌，在标准路线事实可用且当前最优的边界研究；结构只是启发特征，不重算向听/拆解精确胡牌/合法性。若扩展字牌必须说明为何其自然对子/孤张同口径可比；白不是普通字牌，财神非自然结构牌。七对不适用、财神可替牌及副露资格仍由生产事实裁定。公开剩余枚数不是摸牌概率，不把重叠搭子或同一进张重复当独立收益。不识别牌名组合、样例数字、root或结果标签。\n明确语义：visible_state.my_hand不包含独立drawn_tile。本人副露组数m=melds[seat]的组数。drawn_tile非None时，my_hand必须13-3m张，再追加摸牌一次，即便码已存在；drawn_tile=None时要求14-3m张，直接复制。按张保留重复、从完整手牌恰好移除所选弃牌一次。异常张数/不存在待弃牌/缺结构支持时精确退回不含新旧结构项的原基础评分（旧结构项已整体替换），不能抹掉独立直接牌效。followup_branches只用于吃碰后的弃牌，不含普通弃牌下一摸再弃的两步事实。没有hand_codes字段。\n交付须写清：新机制与旧shape的实质区别；量的单位/尺度/上界/主向听保护；跨数牌与字牌的共同口径；两个都数牌的反例为何仍可能失败；至少一个数牌/字牌比较手算、一个数牌/数牌手算、一个重复摸牌或副露边界、一个财神/白边界、一个缺证据退化。不能只给自己源码同构的伪测试。说明删除新块如何回到无shape的V2相近起点，以及如何单独恢复旧shape作父代对照。监督者会独立验算、比较CPython和受限执行、用真实生产choose复核触发，再执行冻结开发面板；任何负效果不算可修复的实现错误。未见开发或确认身份尚未分配。'
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
        'scope': '统一残余结构新机制；未晋升研究父代，独立对照V2与父代，不扫描旧常数',
        'author_feedback_mode': 'compact_prefix_v1',
        'confirmation_roots': 0, 'release_eligible': False})
    panel = b.HERE / 'pattern-generalization-diagnostic-v2-20260920/panel.json'
    auth = b.unified_document(batch_label=NAME, authorization_id='r10-'+NAME,
        accounts={'tokens_input': 393216, 'tokens_output': 131072, 'tables_full': 300,
                  'tables_partial': 8, 'prefix_generation': 8},
        issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
        'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
        'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
        'requested_model': 'gpt-5.6-terra', 'requested_reasoning_effort': 'max',
        'autonomous_admission': False, 'author_feedback_mode': 'compact_prefix_v1', 'supervisor_feedback': instruction,
        'issuance_basis': '用户持续推进和原生Terra作者授权；已完成对称正负诊断，一份新弃牌结构M1；最多一次合同修复，负效果不修复',
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
        'unpromoted-shape-parent': {'dir': parent.parent, 'source_sha256': manifest['parent_sha256']}})
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    b.write(sub / 'parent-terminal-comparison.json', compare(SimpleNamespace(
        ROOT=OUT, NAME=NAME, PARENT=parent, ITER_DIR=state['iter_dir'])))
    closure = b.read(sub / 'batch-closure.json')
    paired = closure['versus_parents']['unpromoted-shape-parent']
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
