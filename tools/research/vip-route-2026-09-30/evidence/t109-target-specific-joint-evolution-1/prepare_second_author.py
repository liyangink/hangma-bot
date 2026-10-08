"""第一份超预算后冻结第二且最后一份GLM联合提案，原失败不覆盖。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


def canonical(value):
    """规范有限公开JSON，不读取凭据或教师世界。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """冻结明确输入，不将将来变化的生成账本或锁文件当输入。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(name, value):
    """只新建第二作者材料，第一候选与失败不修改。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    """复用103公开窗和原144保留来源，零业务准备后发最后一次API。"""
    failed = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/FAILED-MECHANICAL-READBACK.json')).read_text())
    assert failed['readback_complete'] and not failed['mechanical_passed']
    assert failed['actual_tool_terminal']['exit_code'] == 1 and failed['failed_attempts'] == 1
    algebra = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-OWN-TARGET-COST-ALGEBRA.json')).read_text())
    assert algebra['complete'] and algebra['counts']['different_need_nodes_still_all_same_effort'] == 0
    raw = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')).read_text())
    raw.update(batch_id='vip-t109-second-target-specific-simplification-20261003',
        input_bound=json.loads((_project_file(_PROJECT_ROOT, E / 't108-target-cost-joint-evolution-1/AUTHOR-BATCH.json')).read_text())['input_bound'])
    raw['budgets'].update(model_calls=1, input_tokens=1048576, output_tokens=65536)
    save('S02-API-BATCH.json', raw)
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S02-API-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    parent = load_vip_parents([parent_path], batch)[0]
    assert parent['identity']['candidate_id'] == '10cba94704291038653f586127be1809ef518dcaf68fa1fe38d1fc9ab92ca18f'
    case_by_label = {r['label']: r for r in json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json')).read_text())['cases']}
    original_rows = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/CLOSURE.json')).read_text())['rows']
    failed_digest = failed['failures'][0]['input_sha256']
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL-VIEWS.jsonl.gz'), 'rt') as stream:
        view = next(r['view'] for r in map(json.loads, stream) if r['view_sha256'] == failed_digest)
    assert hashlib.sha256(canonical(view)).hexdigest() == failed_digest
    sample = [n for n in view['nodes'] if n['waiting'] is not None][:3]
    failure_feedback = {'input_sha256': failed_digest,
        'observation': case_by_label[failed['failures'][0]['label']]['observation'],
        'legal_root_actions': view['actions'], 'workload': view['workload'], 'limits': view['limits'],
        'node_kind_counts': dict(Counter(n['kind'] for n in view['nodes'])),
        'three_actual_waiting_nodes': sample,
        'scope': 'partial DTO summary only; all remaining nodes intentionally omitted, not full input',
        'parent_actual_complete_scores': case_by_label[failed['failures'][0]['label']]['parent_scores'],
        'error': failed['failures'][0]['error']}
    payload = {'S01_reference_source_not_formal_parent': (_project_file(_PROJECT_ROOT, HERE / 'S01-model-output/candidate.py')).read_text(),
        'S01_actual_partial_mechanical': failed, 'failed_public_input_summary': failure_feedback,
        'S01_completed_window_actual_scores': [r for r in original_rows if r['status'] == 'complete'],
        'S01_own_target_cost_component_readback': algebra,
        'earlier_joint_public_controls': json.loads((_project_file(_PROJECT_ROOT, HERE / 'SELECTED-PUBLIC-FEEDBACK.json')).read_text()),
        'no_hidden_worlds_future_wall_or_reserved_seeds': True}
    prefix = '''这是T109第二且最后一份m1完整联合提案，正式父仍T101，不是机械失败的S01。
第一份Sol max完整联合公式已经真实静态装载，但实际15次评分尝试仅14完成，第21窗old:public:20超480万操作（4800006时抛异常）；20窗口已完成、82未启动、6窗口只完整DTO复用。失败不是输入来源或源码漂移，也不是生成语法错误。不能隐瞒失败、调高预算或跳过复杂窗口。
纯源码/DTO代数检查97输入2616普通保白前驱目标：349节点不同目标缺张，新effort已全部区分；这说明之前代价压平在这个分量上解除，不是强度证据。已完成前20窗只有两次首选变化，其他焦点还未评分，全部完整桌和续打都未启动。
请保留目标自身成本、自然发展和高番用途完整联合机制，但用更紧凑的表示和计算简化，使复杂条件图也在480万内完整合法返回。S01用较多逐目标字典、集合并集和备用offers排序，可能消耗大量操作；这是源码结构推论，不是假造精确热点剖析。可考虑固定位置元组/紧凑候选状态、一次支持复用、按34码直接取最大备用、只保留必要主报价和用途摘要；不得通过删路线、删合法根、抹未知分支或全回普通牌效来换通过。
不要求与S01分值逐项完全相同，允许生成真正更好的完整联合公式。但必须保留不同用途自身成本区别：全自然准备作为另一路，不作为近目标共同必付成本；普通出口、自然成型、白用途、逐码条件支付和边际备用共同取舍。不能只改单个胡阈值或添加统一保白奖励。
父T101源与运行合同按正式提示。S01只是失败参考；两个机制不能混成虚假正式谱系。operator=m1、parent_differences填T101完整摘要；parameter_changes=[]表示执行参数不变，纯评分系数可改变。源码UTF8<=65536字节、解释/操作/集合/投影原限制不变，保留所有动作及未知状态，完整后序共享节点只计算一次。
已曝光历史正负/零例和32源完整分账保留为开发材料，不是正确动作金标；不能硬编码牌码、来源、序号或结局。普通效率损失可由跨来源真实大牌净收益覆盖，但目前没有证明S01强度。当前胡只用即时结算，下一摸支付绑定同码资格条件，远用途只是先验。不读取他家暗牌、未来墙、教师恢复轨迹或新来源。赛事压力第一版只记录，正常决策零R18回退。按正式合同交付完整可执行源码与可反驳机制，不承诺已增强。
以下仅本座公开事实、真实旧评分和有限失败输入摘要。无模型调用重试；生成后根代理验证全部103窗口和续打，再决定新自然桌。
'''
    feedback = prefix + canonical(payload).decode()
    (_project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt')).write_text(feedback)
    save('S02-SELECTED-PUBLIC-FEEDBACK.json', payload)
    emission = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission'),
        operator='m1', parent_paths=[parent_path], feedback=feedback)
    assert emission['status'] == 'prompt_emitted' and emission['identity_stable']
    probe = (_project_file(_PROJECT_ROOT, HERE / 'probe.py')).read_text().replace('AUTHOR-PREPARATION-CLOSED-REVISION-2.json',
        'S02-AUTHOR-PREPARATION-CLOSED.json').replace('AUTHOR-BATCH.json', 'S02-API-BATCH.json')
    ast.parse(probe)
    (_project_file(_PROJECT_ROOT, HERE / 'S02-probe.py')).write_text(probe)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'run_second_author.py'), _project_file(_PROJECT_ROOT, HERE / 'S02-probe.py'),
        batch_file, _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json'), _project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json'),
        _project_file(_PROJECT_ROOT, HERE / 'EVOLUTION-PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED-REVISION-2.json'),
        _project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json'), _project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt'), _project_file(_PROJECT_ROOT, HERE / 'S02-SELECTED-PUBLIC-FEEDBACK.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S01-model-output/candidate.py'), _project_file(_PROJECT_ROOT, HERE / 'S01-model-output/generation.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/FAILED-MECHANICAL-READBACK.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/ACTUAL-TOOL-TERMINAL.json'), _project_file(_PROJECT_ROOT, HERE / 'S01-OWN-TARGET-COST-ALGEBRA.json'),
        parent_path / 'candidate.py', parent_path / 'generation.json']
    save('S02-AUTHOR-PREPARATION-CLOSED.json', {'complete': True, 'stage': 'before_second_actual_author_call',
        'formal_parent': parent['identity']['candidate_id'], 'public_windows': 103,
        'prompt_sha256': emission['prompt_sha256'],
        'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt')).stat().st_size,
        'frozen_files': {str(p): pin(p) for p in files}, 'new_models_rules_scores_worlds_tables': 0,
        'actual_author_slots_already_used': 1, 'only_remaining_slot': 'S02',
        'model': 'glm-5.3', 'reasoning_effort': 'not sent by existing API backend; provider default',
        'fresh_development_and_confirmation_roots_unchanged': True})
    print({'prepared': True, 'public_windows': 103,
        'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt')).stat().st_size, 'new_business_calls': 0})


if __name__ == '__main__':
    main()
