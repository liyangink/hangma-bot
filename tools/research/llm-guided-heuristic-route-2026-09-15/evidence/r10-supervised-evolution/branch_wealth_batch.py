"""以已核实的生产字段冻结下一份 M1；分开记录机制变更与错误修复。"""

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

NAME = 'wealth-branch-terra-max'
ROOT = b.HERE / 'branch-wealth-20260920'
PARENT = b.BATCH / 'hard-terra-max/run/iterations/iter-01/generation'

FEEDBACK = '''本次是一份新M1，不冒充上一份的错误修复。唯一父代是所附hard-terra-max。
父代共同核心开发H +0.125、M +0.09375；已见的第二开发清单H +0.03125、M -0.046875。每层仅8根；没有显著增强和发布资格。
监督勘误：上一份分支任务要求分支家族/手牌修正，却没有先核实真实生产字段。另一份Terra衍生实现虽然把最终来源切到followup_branch，在32个真实窗159个动作中所有分数及排序仍与本父代相同；其完整开发评测正在运行，结果未知。不得假定已经负效果或全域等价。此次不提供那份衍生源码，避免继承其额外复杂度。
正式生产事实（已核对FollowupBranchFacts、candidate_facts和candidate_view真实投影）：
每条合法吃碰后继有followup_key、followup_discard、combined_shanten、standard_shanten_after、seven_pairs_shanten_after、useful_tiles、support_remaining。可空字段在映射中可能省略；用get保持未知。当前32窗19个吃碰动作共171条分支，实际出现前六种中的followup_key/followup_discard/combined_shanten/standard_shanten_after，以及useful_tiles/support_remaining；七对向听因副露不适用而未出现。useful_tiles是牌码元组，不是逐牌remaining字典；总支持枚数只读support_remaining。
生产分支没有hand_codes、progress、route_state；别名兼容或人工夹具可接受这些键不等于生产会提供。不要继续依赖这些键实现主机制。family_progress_entries是动作级摘要，不能声称是每个followup的家族事实；routes含followup_discard和相容条件，可按对应弃牌绑定。
杭麻依据：冻结官方指南v34 §1.1/§6与当前唯一规则实现，财神白不能参与吃碰；合法吃碰后先弃一张，因此手留财神变化恰为followup_discard为白时-1，否则0。这是对已生产合法分支的可见属性计算，不重写合法性或向听。已在171条真实分支用本人可见手牌核验，8条为弃白，守恒全部成立。不能由此推出弃白总是坏事，财飘/爆头/链的相容条件路线可能值得付代价。
本次目标：让吃碰候选对其真实后继弃牌的财神取舍具有可执行、可解释的评分，修复“想用但字段不存在”的死分项。结合父代实际弃牌策略审查前后刻度：父代直接弃白合计-65，而旧分支仅计划-5且从未生效。你需说明选择的刻度与实际后续策略是否一致；不强制沿用-65或-5，不扫描常数。围绕这一项构造连贯变异，尽量保留不相关弃牌、立即结算、过牌等原行为。
完整后继先计本分支的已知牌效及所选修正，再择优；不能让未修正动作摘要绕过同一后继代价。条件路线可以代表替代估值，但必须明确哪项实际计入，不能trace说扣了而总分没扣；不得把互斥路线相加、重复计算同一收益。缺失全分支时保留已有直接已知事实，部分分支时如实标记。不要把动作级家族摘要复制后称分支独立证据。
输出要有简短机制说明、规定JSON四字段和唯一完整Python源码；trace应能核对被选弃牌、财神变化、实际应用修正与总分。给一个吃/碰与过牌等相容动作族的算术反例，明确仅合成说明；不要把chi与discard放同一窗口，不硬编码真实样本、根或评测身份。主入口view是纯字典，不调用.candidate_view，不导入、不调用模型、不重算向听/结算。
没有要求胡牌必须压过一切。已完成的另一路线作者强制胡牌优先消融，在第二已见清单反而变弱，本次不要加入该变更。只自摸、无点炮/抢杠胡；未知不冒充0，支持枚数不是概率，统计目标仍是完整阶段前二效用。
'''


def prepare():
    """冻结一份新提案及至多一次实际错误修复，不复用前批费用账户。"""
    if ROOT.exists():
        raise SystemExit('已冻结，不覆盖')
    ROOT.mkdir()
    sub = _project_file(_PROJECT_ROOT, ROOT / NAME)
    sub.mkdir()
    panel = b.HERE / 'batch03-known-root-diagnostic/panel.json'
    auth = b.unified_document(
        batch_label=NAME, authorization_id='r10-production-wealth-branch',
        accounts={'tokens_input': 393216, 'tokens_output': 131072,
                  'tables_full': 300, 'tables_partial': 8, 'prefix_generation': 8},
        issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth.update({'generation_call_limits': {'tokens_input': 196608, 'tokens_output': 65536},
                 'max_model_calls': 2, 'max_proposals': 2, 'repair_calls_count_in_total': True,
                 'wall_clock_limit_seconds': 14400, 'author_channel': 'codex_native_subagent',
                 'requested_model': 'gpt-5.6-terra', 'requested_reasoning_effort': 'max',
                 'autonomous_admission': False, 'supervisor_feedback': FEEDBACK,
                 'issuance_basis': '用户持续推进与原生Terra作者授权；真实字段勘误后的一份新M1',
                 'scope': '256自然完整开发桌赛，条件费用另计；零独立确认，不发布',
                 'development_behavior_panel': {'path': str(panel),
                                               'panel_digest': b.behavior.load_panel(panel)[0]}})
    b.write(sub / 'authorization.json', auth)
    state = b.search.av_start_iteration(
        sub / 'run', operator='m1', parent_dir=PARENT, generation_mode='delegate',
        predicate='branch_open', opponent='H', natural_roots=8, natural_seats=4,
        prefix_source='v2_behavior', panel_seed=2026092001, authorization=auth,
        archive_in={'source': 'empty', 'path': None, 'applied_operator': 'm1',
                    'note': '显式机制探索父代；未晋升，不把既有成绩当新成绩'})
    if state.get('stop_reason'):
        raise ValueError(state['stop_reason'])
    result = b.search.av_iteration_advance(
        b.search.av_latest_state_path(sub / 'run'), sub / 'run',
        authorization=auth, stop_after='BEHAVIOR_CHECKED')
    assert result.get('waiting_for_reply')
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    prompt = b.Path(state['generation']['pending_dir']) / 'prompt.txt'
    b.write(sub / 'author-task.json', {
        'model': 'gpt-5.6-terra', 'effort': 'max', 'task': 'M1生产可用后继财神取舍',
        'prompt': str(prompt), 'prompt_sha256': b.digest(prompt.read_bytes()),
        'reply_path': str(sub / 'author-reply.txt')})
    b.write(_project_file(_PROJECT_ROOT, ROOT / 'manifest.json'), {
        'created_at_utc': b.search.utc_now(), 'parent_path': str(PARENT / 'candidate.py'),
        'parent_sha256': b.digest((PARENT / 'candidate.py').read_bytes()),
        'initial_proposals': 1, 'max_author_calls': 2, 'max_native_turn_seconds': 1800,
        'native_tokens': 'unknown; conservative reservation only',
        'production_audit': str(b.HERE / 'branch-refinement-20260920/production-capability-audit.json'),
        'release_eligible': False})
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
