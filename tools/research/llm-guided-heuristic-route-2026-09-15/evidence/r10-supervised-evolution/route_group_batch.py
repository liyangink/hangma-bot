"""基于真实条件路线分组的独立 M1；不重写麻将规则或夸大概率语义。"""

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

NAME = 'route-group-sol-high'
ROOT = b.HERE / 'route-group-20260920'
PARENT = b.BATCH / 'route-terra-max/run/iterations/iter-01/generation'
FEEDBACK = '''本次是一个新的反馈驱动M1，唯一父代为所附route-terra-max源码。任务是检验“按同一真实后继归并已生产的不同成胡牌种”，不是继续微调财神扣分或强制胡牌。
父代开发结果：共同核心H/M各8根时H +0.125、M +0.125；另一个已见开发清单H +0.0625、M -0.234375。尚未超过V2，没有发布资格。此前强制胡牌优先的工程消融，核心H/M等权增量0、第二清单反而更差，不能把跳过合法Hu一概当错误；本次保持Hu与其他非路线逻辑尽量不变。
生产与数学事实已经核对：routes中每项由同一等待手牌、draw_kind、meld_count、chain_count、chain_piao、baotou和条件结算分组。每项useful_tiles是{code,remaining_estimate}的列表/元组；同一等待后继会因不同成胡牌种的番数/结算不同而有多条路线。生产引擎在单一等待手牌中逐牌种算一次再分组，所以正常完整生产输出同一个后继的牌种不会重复；但候选仍应检测冲突，不能把不一致假输入重复计数。
现有父代逐路线评分后择优，可能只看中某个小支持的高番分组，或者漏看分散在多个条件结算分组中的合法成胡牌。请先读父代实际实现，再围绕这个问题设计一个连贯且可核对的后继聚合估值。
可行方向（工程假设，不是指定答案）：先用完整条件身份与followup_discard区分不同后继，再把同一后继内互不重复的成胡牌种支持汇总，并使用按支持枚数加权的条件结算/番数代理；最后才在不同后继择优。不能把不同弃牌、不同摸牌来源或互不相容规则状态的最佳部分拼接。不允许直接把多条条件结算的self_delta相加，当成一次能兑现多个胡。
总支持数、按支持加权的条件均值都是已知事实上的启发代理；不称实际摸牌概率、真实期望收益或晋级概率，不用真实未来牌墙。若你需要归一化或非线性，说明意义及边界；不要另造一套手牌数学，也不要臆造没有投影的总未知牌数。数值必须有限、布尔不得冒充计数；已知0支持不制造收益，未知支持与部分value_coverage须显式处理，不能把缺失路线当已知没有。
吃碰分支的正式生产字段是followup_key/followup_discard/combined_shanten/standard_shanten_after/seven_pairs_shanten_after/useful_tiles/support_remaining；可空项可省略。分支useful_tiles是牌码元组，不同于routes的逐牌计数。生产分支没有hand_codes/progress/route_state；不能把兼容别名当可用事实，动作级family_progress_entries也不是逐后继独立家族证据。
新发现的故障边界：分支机械分析与条件路线分析相互隔离，因此followup_branches=None且routes非空是实际生产入口在故障注入下能产生的状态。路线自带followup_discard与conditions，不能仅因没有机械分支键而把这一独立已知证据抹成未知；同时不能从缺失补出具体合法弃牌或假分支。缺少聚合条件时应保留单条已知路线的受限估值/明确退化，不放松全部未知的锚定合同。
范围：只改变路线归并与相应估值组织；保持直接牌效、已知动作费用、立即结算等尽量稳定，确需改变须给因果理由。不要同时修订另一个作者的财神-65设计；不要加入对手预测、剩余赛程、时钟或外部依赖。说明如何移除本机制做消融，并给两个同后继分组与两个不同后继不可混合的算术例。构造例不冒充真实轨迹或开发成绩，动作族必须相容。
杭麻依据为本项目冻结官方指南v34和唯一HangmaRules：只自摸，无点炮/抢杠胡，财神不被吃碰杠；七对与副露互斥，爆头/财飘/杠链/四白均使用已生产条件，不能靠其它麻将规则臆推。LLM只做离线作者，目标仍是完整阶段前二效用。
主入口view是纯字典，直接get；不调用.candidate_view，不导入、不读文件/模型、不重算合法性/向听/结算，不硬编码开发根/样本。按M1合同交付简短机制说明、JSON四字段、唯一完整Python源码；不声称自测或效果提升。
'''


def prepare():
    """冻结一份 Sol high 初答和至多一次实际错误修复，不累加其它候选调用上限。"""
    if ROOT.exists():
        raise SystemExit('已冻结，不覆盖')
    ROOT.mkdir()
    sub = _project_file(_PROJECT_ROOT, ROOT / NAME)
    sub.mkdir()
    panel = b.HERE / 'batch03-known-root-diagnostic/panel.json'
    auth = b.unified_document(batch_label=NAME, authorization_id='r10-route-group-sol-high',
        accounts={'tokens_input': 393216, 'tokens_output': 131072,
                  'tables_full': 300, 'tables_partial': 8, 'prefix_generation': 8},
        issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
        'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
        'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
        'requested_model': 'gpt-5.6-sol', 'requested_reasoning_effort': 'high',
        'autonomous_admission': False, 'supervisor_feedback': FEEDBACK,
        'issuance_basis': '用户持续推进和强模型作者授权；独立路线聚合机制，一初答至多一修复',
        'scope': '256自然完整开发桌赛及条件费用；零独立确认，不发布',
        'development_behavior_panel': {'path': str(panel), 'panel_digest': b.behavior.load_panel(panel)[0]}})
    b.write(sub / 'authorization.json', auth)
    state = b.search.av_start_iteration(sub / 'run', operator='m1', parent_dir=PARENT,
        generation_mode='delegate', predicate='branch_open', opponent='H', natural_roots=8,
        natural_seats=4, prefix_source='v2_behavior', panel_seed=2026092001, authorization=auth,
        archive_in={'source': 'empty', 'path': None, 'applied_operator': 'm1',
                    'note': 'route-terra-max为显式机制探索父代，未效果晋升'})
    if state.get('stop_reason'):
        raise ValueError(state['stop_reason'])
    result = b.search.av_iteration_advance(b.search.av_latest_state_path(sub / 'run'),
        sub / 'run', authorization=auth, stop_after='BEHAVIOR_CHECKED')
    assert result.get('waiting_for_reply')
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    prompt = b.Path(state['generation']['pending_dir']) / 'prompt.txt'
    b.write(sub / 'author-task.json', {'model': 'gpt-5.6-sol', 'effort': 'high',
        'task': 'M1同后继条件路线归并', 'prompt': str(prompt),
        'prompt_sha256': b.digest(prompt.read_bytes()), 'reply_path': str(sub / 'author-reply.txt')})
    b.write(_project_file(_PROJECT_ROOT, ROOT / 'manifest.json'), {'created_at_utc': b.search.utc_now(),
        'parent_path': str(PARENT / 'candidate.py'),
        'parent_sha256': b.digest((PARENT / 'candidate.py').read_bytes()),
        'initial_proposals': 1, 'max_author_calls': 2, 'max_native_turn_seconds': 1800,
        'native_tokens': 'unknown; conservative reservation only', 'release_eligible': False})
    print({'prompt': str(prompt), 'chars': len(prompt.read_text())}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'ingest', 'evaluate'])
    action = parser.parse_args().action
    if action == 'prepare':
        prepare()
    else:
        b.BATCH = ROOT
        b.advance(NAME, action == 'evaluate')
