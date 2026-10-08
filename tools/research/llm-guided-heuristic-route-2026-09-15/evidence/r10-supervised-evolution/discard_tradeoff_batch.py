"""在V2相近父代上只探索弃牌公开偏好与牌效的取舍；父代正式反馈通过后才签发。"""

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

OUT = b.HERE / 'discard-tradeoff-20260920'
NAME = 'discard-terra-max'


def prepare():
    """按真实分歧冻结一份M1、最多一次合同修复；不预先指定结果或追加模型档位。"""
    assert not OUT.exists()
    assert b.read(parent_run.OUT / 'summary.json')['status'] == 'COMPLETE_DEVELOPMENT_ONLY'
    assert b.read(parent_run.OUT / 'parent/feedback-consumption-check.json')['ok']
    parent = parent_run.OUT / 'parent/generation'
    diagnosis = b.HERE / 'route-decision-diagnostic-20260920'
    evidence = b.read(diagnosis / 'v2-seed-comparison.json')
    assert evidence['source_sha256'] == b.digest((parent / 'candidate.py').read_bytes())
    instruction = previous.COMMON + '''本次M1的唯一父代是重新验收的V2相近种子，不是之前的路线父代。只改变弃牌排序中“公开信息偏好与直接牌效如何取舍”这一项机制；保留胡牌、吃碰、杠、财神保留代价及未知锚定等非目标逻辑，不恢复路线父代，不全面重写评分。
可证伪问题：父代熟张、公开副露邻近与名次风格分项是否会为了弱公开线索牺牲过多已知有效牌？如何保留有解释的同牌效区分，同时限制无依据的牌效牺牲？请自行选择一个可移除机制；可以否定“完全不应牺牲进张”这一解释，但必须说明规则和可见依据。不要求套用指定门槛、公式或把公开信息一律删除。不改财神相关分项，不放松已知/未知比较，不改规则或增加新字段。
新诊断是从失败后选出的3个已见M阶段重演，6桌终局完全复现。1887请求中原路线父代与V2有77次首选分歧，每阶段只保存前8个分歧，共24窗。其中19个弃牌分歧、5个吃转过分歧；19/24在路线父代下同分。当前绑定的V2相近种子24/24复现V2首选。这个观察支持保留较丰富的基线行为，不证明V2选择最优，不允许把24窗答案写入源码。
具体可复查例（候选只能使用合法可见状态，不能识别样本）：原路线父代在向听1、支持15张的discard:8t和discard:9b间同分，V2因9b熟张+3且领先风格+4选9b；另一窗口4b支持11张、8t支持10张，V2仍因后者熟张+3且领先风格+4选8t。第三个窗口有财神但均不弃财神，8w支持14张、2w支持13张，V2同样以熟张/风格选2w。前者是同牌效细化，后两者发生实际进张牺牲。这些只解释局部分歧，不声称后一选择错误或导致整阶段失利。
既往负结果约束：route简化在首清单改善、第二清单变差；不能据局部合理性许诺收益。旧river-sol-high同时重构基础结构与公开压力，以熟张每张+1上限2、下家chi邻近每组-5、自弃返还+2等规则得到首清单M负值，不能简单换常数复刻。旧非推进吃碰固定代价和强制Hu优先也无稳定收益，本次不重开这些问题。
请给出触发条件、保持不变的范围、反例、非零手算与如何移除此单机制。输出完整源码；避免不相关清理。最终效用仍由固定H/M完整阶段评测裁定，不以与V2更相似、进张更高或代码更短作成功标准。
'''
    assert len(instruction) <= 12000
    OUT.mkdir()
    sub = OUT / NAME
    sub.mkdir()
    sha = b.digest((parent / 'candidate.py').read_bytes())
    b.write(OUT / 'manifest.json', {'created_at_utc': b.search.utc_now(), 'parent': str(parent),
        'parent_sha256': sha, 'diagnostic_sha256': b.digest((diagnosis / 'v2-seed-comparison.json').read_bytes()),
        'model': 'gpt-5.6-terra', 'effort': 'max', 'initial_authors': 1, 'max_author_calls': 2,
        'max_native_turn_seconds': 1800, 'core_tables': 256, 'conditional_full_cap': 4,
        'selection_rule': '完整H/M对V2均正且对冻结父代等权识别差下界正才签发第二已见清单；否则本提案停止追加',
        'scope': '单机制开发修订，非调参扫描；不保证V2相似度与效果一致',
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
        'autonomous_admission': False, 'supervisor_feedback': instruction,
        'issuance_basis': '用户持续推进授权；6桌诊断明确后单份Terra max M1，不升级昂贵档位',
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
