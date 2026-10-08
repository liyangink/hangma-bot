"""从正负诊断提出弃牌结构机制；单份M1、固定开发评价，不继承失败奖励。"""

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

OUT = b.HERE / 'discard-shape-20260920'
NAME = 'discard-shape-terra-max'


def prepare():
    """按真实分歧冻结一份M1、最多一次合同修复；不预先指定结果或追加模型档位。"""
    assert not OUT.exists()
    assert b.read(parent_run.OUT / 'summary.json')['status'] == 'COMPLETE_DEVELOPMENT_ONLY'
    assert b.read(parent_run.OUT / 'parent/feedback-consumption-check.json')['ok']
    parent = parent_run.OUT / 'parent/generation'
    diagnosis = b.HERE / 'pattern-generalization-diagnostic-v2-20260920'
    evidence = b.read(diagnosis / 'audit.json')
    assert evidence['status'] == 'COMPLETE_DIAGNOSTIC_ONLY'
    assert evidence['counts']['parent_vs_v2_first_changed'] == 0
    assert evidence['saved_changes'] == 19
    instruction = previous.COMMON + '本次M1从唯一父代——当前核心已验收的V2相近种子——提出一个新的弃牌结构机制。目标是完整阶段前二指标U；你不只是在修语法或提升行为改选数。不要继承已停止的普通型/七对次优奖励，也不要重开其8张截顶、1/2间距或倍率的参数扫描。其他已有失败机制包括：全局路线简化在第二清单退步；熟张/喂牌偏好调整H正M负；纯阶段名次风格H微正M零。它们不是有效父代。\n实际反馈：上一候选在两张已见清单均正，但32个新开发根512桌H=0、M=+0.0078125，等权平分识别差下界=0，按运行前条件停止。我们对H/M各一正一负座位重放双臂16桌，所有终局复现；5495个焦点请求中父代和V2首选完全一致，候选19次改选全部只是打破父代平分。以下4个首次分歧是事后对称诊断，不是动作优劣标签：\n正H例：余牌68，父代弃2b与6w同为-84，普通向听1/支持16；6w保留的七对路线间距2/独有支持16获得+1，而2b间距3无奖励。\n负H例：余牌74，父代弃3b与3t同为-275，七对向听3/支持25；3b次优普通间距2、独有支持59获+1，3t间距1、独有支持42获+2。\n正M例：余牌52，父代弃7t与发同为14，七对听牌/支持9；两者次优普通间距2、独有支持7/11，奖励0.875/1使之改选。\n负M例：余牌82，父代弃1b与5w同为-85，七对向听1/支持13；前者普通间距2独有支持21获+1，后者间距1独有支持14获+2。\n诊断说明“相同直接向听/枚数不足以区分保留结构”，不说明上述正例动作天然优、负例动作天然劣。不要把牌名、余牌数字、分数、seed或样例hash做识别器；终局差可能随之后许多行动变化。公开未见枚数不是摸牌概率。\n新的单机制方向：同等或相近的直接牌效下，利用依法可见的本人手牌、弃牌后的自然牌结构、已生产的直接有效牌/分牌型事实，区分后续改良空间与已消耗结构。由你设计一个连贯、可解释、可独立消融的弃牌偏好；例如拆散搭子/孤张的实际结构机会代价，而非给“存在近次优牌型”统一加分。可以对这一方向提出更好的同范围公式，但只交付一个候选，不给网格或多方案。不强制限制只能打破精确平分，允许有理由的连续偏好；必须保留主向听尺度与有限有界运行量，不能把未知变成乐观确定事实。\n规则与数据约束：只对直接已知hand_progress弃牌起作用；其余胡/过/吃/碰/杠动作评分、胡优先层、财神相关原分项、公开河牌/喂牌风险分项与未知锚定保持父代行为。副露七对不适用、财神可替牌等由生产规则事实裁定，不自行判胡/算向听/重算合法性或结算。不照搬日麻防放铳——本项目官方指南v34（2026-09-15本地快照）只能自摸，无点炮与抢杠胡。白不是普通字牌，不能把它当自然孤张惩罚；吃碰喂牌影响提速需和放铳分开。可以计算简单手牌几何结构作偏好特征，但不得冒充精确规则分析或期望收益。标准手牌和七对的牌效按合同可缺失，不把不适用七对看作零向听。已有综合有效牌已并集；新机制不能将同一进张枚数重复当独立收益。\nvisible_state.my_hand与drawn_tile的生产语义按合同：先确认摸牌是否已包含在my_hand，不能重复加入摸牌或对不存在的弃牌减张。弃牌后的结构仅由当前可见事实推导；不能读取完整世界、对手暗手、未来牌墙、文件或历史诊断路径。没有hand_codes兼容字段可依赖。不要把麻将规则实现写进候选；花色数字关系等只作为启发特征，不决定合法动作。\n新机制事实不足、不可信、字段形状不符时，精确沿用父代该动作评分，不能把独立已知直接牌效抹成未知。必须保证已知/未知严格锚定在最终加分后仍正确，支持负修正时尤其说明下界；trace如实反映锚定顺序，不继承旧标签歧义。整批有合法Hu时不得用新机制压过Hu。\n交付完整受限Python源码、机制说明、至少一个非零手算、一个两个直接牌效相同但结构不同的可区分例、一个结构信息缺失时精确退化例、一个财神/副露/重复牌边界及一个会误导该机制的反例。解释新增分项尺度和去除它如何还原父代；不将任何分数称为校准概率。只可按任务包提供的合同操作，原始正负轨迹没有附在提示里，四例文字不承担完整输入。负效果不允许以“修复”为名再次调参。'
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
        'scope': '弃牌保留结构单机制；不继承失败次优奖励，不扫描其常数',
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
