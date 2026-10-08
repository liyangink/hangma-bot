"""同一共享支撑候选的唯一实际运行成本修复，使用新身份和独立有界费用。"""

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
import support_competition_batch as original
OUT=b.HERE/'support-runtime-repair-20260920'
NAME='support-runtime-repair-terra-max'

def prepare():
    """只降低等价计算成本；不按效果改公式、权重、机会或激活条件。"""
    assert not OUT.exists()
    parent=original.OUT/original.NAME/'run/iterations/iter-01/generation'
    failure=b.HERE/'support-workload-diagnostic-20260920'
    assert b.read(failure/'summary.json')['status']=='REPRODUCED_WORKLOAD_FAILURE'
    assert b.read(original.OUT/'handles.json')['author_calls']==1
    feedback='''这是共享支撑竞争提案的唯一实际实现错误修复，原初答1次，本次后该提案总作者调用达到2次。仅降低受限执行器计费操作数，不改变数学机制。必须保留全部分数、trace字段和语义、机会内容及顺序、质量0.75/0.5/1、激活条件、0.2和±10截顶、未知锚定/胡排序/财神/风格项。
真实自然窗口已复现：14个合法候选，原源码完整计算需要100241操作，生产100000限额使其在100001处整批失败并执行合法保底。普通固定压力检查最高94233没有覆盖这个真实窗。仅为离线诊断得到的100241不是放宽生产限额；不许改执行器或生产上限。
请优化重复解析或机会需求聚合等真正热点。尤其当前每个物理牌位重新扫描全部机会的需求累加，可以考虑保持机会顺序的等价聚合。你自行选择实现，但不能减少机会、截断候选、复杂牌形关掉机制或提前弃权；每个有效输入应与原标准Python无限额参考输出完全相同（包括分值与trace），并在原100000限额内工作。
必须说明原计算与新计算的等价关系及数值顺序。循环次数不等于计费操作数，不得未经执行就声称证明100000最坏上界。数学公式、几何含义或质量系数的设计缺陷不属于这次修复范围。
只写指定的新author-reply.txt，交完整受限源码及正式四字段。不得改原文件、测试、合同、生产核心，不能跑模拟/其他模型；最多JSON/Python语法自检。真实原生token未知如实标注。修复不是因成绩不佳，不消费第二清单中途成绩。
'''
    feedback+='\n故障请求：'+str(failure/'failing-request.json')+'\n计费与参考：'+str(failure/'offline-expanded-meter-reference.json')
    auth=b.unified_document(batch_label=NAME,authorization_id='r10-'+NAME,
        accounts={'tokens_input':196608,'tokens_output':65536,'tables_full':300,'tables_partial':8,'prefix_generation':8},
        issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    panel=b.HERE/'comparable-shape-second-diagnostic-20260920/panel.json'
    auth.update({'generation_call_limits':{'tokens_input':196608,'tokens_output':65536},
        'max_model_calls':1,'max_proposals':1,'repair_calls_count_in_total':True,
        'wall_clock_limit_seconds':14400,'author_channel':'codex_native_subagent',
        'requested_model':'gpt-5.6-terra','requested_reasoning_effort':'max','autonomous_admission':False,
        'author_feedback_mode':'compact_prefix_v1','supervisor_feedback':feedback,
        'issuance_basis':'用户持续推进和修复授权；实际运行超额复现，原提案唯一实现修复。新费用身份，不扩原批次历史预算。',
        'scope':'仅等价资源优化，先验收再评测，不继承旧成绩',
        'development_behavior_panel':{'path':str(panel),'panel_digest':b.behavior.load_panel(panel)[0]}})
    OUT.mkdir();sub=OUT/NAME;sub.mkdir();b.write(sub/'authorization.json',auth)
    b.write(OUT/'manifest.json',{'created_at_utc':b.search.utc_now(),'parent':str(parent),
        'parent_sha256':b.digest((parent/'candidate.py').read_bytes()),'max_author_calls_this_batch':1,
        'lineage_author_calls_including_this':2,'repair_index':1,'max_repair_index':1,
        'failure_request_sha256':b.digest((failure/'failing-request.json').read_bytes()),
        'scope':'新身份等价资源修复；原自然清单继续结案，不改原源码或成绩。',
        'allow_development_evaluation':False,'release_eligible':False})
    state=b.search.av_start_iteration(sub/'run',operator='m1',parent_dir=parent,generation_mode='delegate',
        predicate='branch_open',opponent='H',natural_roots=8,natural_seats=4,prefix_source='v2_behavior',
        panel_seed=2026092001,authorization=auth,
        archive_in={'source':'empty','path':None,'applied_operator':'m1','note':'实际成本错误的唯一等价修复，监督显式选父'})
    assert not state.get('stop_reason')
    result=b.search.av_iteration_advance(b.search.av_latest_state_path(sub/'run'),sub/'run',
        authorization=auth,stop_after='BEHAVIOR_CHECKED')
    assert result.get('waiting_for_reply'),result
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    prompt=b.Path(state['generation']['pending_dir'])/'prompt.txt'
    b.write(sub/'author-task.json',{'model':'gpt-5.6-terra','effort':'max','task':'m1_runtime_repair',
        'prompt':str(prompt),'prompt_sha256':b.digest(prompt.read_bytes()),
        'reply_path':str(sub/'author-reply.txt')})
    print('prepared',len(prompt.read_text()),str(prompt),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','ingest','evaluate']);a=p.parse_args()
    if a.action=='prepare':prepare()
    else:b.BATCH=OUT;b.advance(NAME,a.action=='evaluate')
