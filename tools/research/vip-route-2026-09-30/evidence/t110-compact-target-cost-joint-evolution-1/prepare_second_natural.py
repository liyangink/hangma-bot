"""第二子代复用已闭父代，只新增128完整桌；准备阶段不生成世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import difflib
import gzip
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S01-natural-development-1')


def change(text, old, new):
    """仅替换唯一的已核模板位置；上游漂移时拒绝继续。"""
    assert text.count(old) == 1, old
    return text.replace(old, new)


def adapted_template():
    """只读取固定模板并校验替换位置，不读运行积分，不生成世界。"""
    before = (_project_file(_PROJECT_ROOT, HERE / 'prepare_natural.py')).read_text()
    text = before
    text = change(text, "    assert slot == 'S01', '第二份需单独准备父结果复用，不能重算已闭父代'",
        "    assert slot == 'S02'\n    prior = HERE / 'S01-natural-development-1'")
    # 读入口与输入钉住列表必须同时绑定第二子代自己的读回。
    assert text.count("HERE / 'S01-public-probe/ROOT-READBACK.json'") == 2
    text = text.replace("HERE / 'S01-public-probe/ROOT-READBACK.json'", "HERE / 'S02-public-probe/ROOT-READBACK.json'")
    text = change(text, "HERE / 'S01-CONTINUATION-PREPARATION.json'", "HERE / 'S02-CONTINUATION-PREPARATION.json'")
    text = change(text, "child_path = HERE / 'S01-model-output'", "child_path = HERE / 'S02-model-output'")
    text = change(text, "out = HERE / 'S01-natural-development-1'", "out = HERE / 'S02-natural-development-1'")
    text = change(text, "HERE / 'AUTHOR-PREPARATION-CLOSED.json',", "HERE / 'S02-AUTHOR-PREPARATION-CLOSED.json',")
    text = change(text, "parent_path / 'candidate.py', parent_path / 'generation.json', *tails]",
        "parent_path / 'candidate.py', parent_path / 'generation.json', prior / 'CAMPAIGN-CLOSURE.json', prior / 'ACTUAL-READBACK-TERMINAL.json', prior / 'ALL-PROCESS-HANDLES.json', *tails]")
    text = change(text, "'stage': 'author-pre-reserved development; not independent confirmation',",
        "'stage': 'same16 development; second author used no S01 table outcomes; not independent confirmation',")
    text = change(text, "'planned_actual_tables': 256, 'planned_hands': 2048,",
        "'planned_actual_tables': 128, 'planned_hands': 1024, 'analysed_historical_tables':256, 'reused_parent_actual_tables':128, 'batch_actual_tables_including_S01':384,")
    text = change(text, "'blocks': 8, 'roots_per_block': 4,", "'blocks': 4, 'roots_per_block': 4,")
    text = change(text, "'old_admission_or_results_transferred': False,",
        "'old_admission_or_results_transferred': False, 'closed_parent_results_reused_for_development':True,")
    text = text.replace('original256 denominator retained', 'original128 new-instance denominator retained; prior128 parent charged historically')
    text = text.replace('until all8 actual handles terminal', 'until all4 new actual handles terminal; four parent handles already terminal')
    text = change(text, '    for block in range(1, 9):', '    for block in range(1, 5):')
    text = change(text, "'actual_tables_planned': 256,", "'actual_tables_planned': 128, 'parent_tables_reused':128,")
    # 读取器仍核八块共同数据；父块只读取原批，不产生新的父费用。
    marker = "    for name, before, after in [('run_block.py', old_runner, runner), ('close_pilot.py', old_reader, reader)]:"
    additions = """    runner = change(runner, 'choices=range(1,9)', 'choices=range(1,5)')
    reader = change(reader, 'HERE=Path(__file__).resolve().parent',
        'HERE=Path(__file__).resolve().parent\\nPRIOR=Path(' + repr(str(prior)) + ')')
    reader = change(reader, \"path=HERE/f'block-{i:02d}/costs.json'\",
        \"path=(PRIOR if i>4 else HERE)/f'block-{i:02d}/costs.json'\")
    reader = change(reader, \"'charged_instances':sum(e['charged_table_instances'] for e in es),\",
        \"'charged_instances':sum(e['charged_table_instances'] for e in es),'reused_prior_closed':i>4,'new_charged_instances':sum(e['charged_table_instances'] for e in es) if i<=4 else 0,\")
    reader = change(reader, \"out=HERE/f'block-{i:02d}';bp=json.loads((HERE/f'BLOCK-{i:02d}-PLAN.json').read_text())\",
        \"out=(PRIOR if i>4 else HERE)/f'block-{i:02d}';bp=json.loads(((PRIOR if i>4 else HERE)/f'BLOCK-{i:02d}-PLAN.json').read_text())\")
    reader = change(reader, \"assert helper.sha(out/'RUNNER.py')==helper.sha(HERE/'run_block.py')\",
        \"assert helper.sha(out/'RUNNER.py')==helper.sha((PRIOR if i>4 else HERE)/'run_block.py')\")
    reader = change(reader, \"'planned_actual_tables':256,'observed_actual_tables':sum(c['actual_started_known_subtotal'] for c in costs),\",
        \"'planned_actual_tables':128,'observed_actual_tables':sum(c['actual_started_known_subtotal'] for c in costs if not c['reused_prior_closed']),'analysed_historically_executed_tables':256,'reused_prior_actual_tables':128,'new_hands':1024,'batch_development_actual_tables_including_S01':384,\")
    reader = reader.replace('sixteen new development roots', 'sixteen same development roots; parent reused at zero new cost')
"""
    text = change(text, marker, additions + marker)
    ast.parse(text)
    return before, text


def main():
    """父波闭合、第二子评分及18续打有效后，冻结同16来源的开发比较。"""
    # 此处只检查已有终态。完整父结果和首子结果不得在运行中读入。
    closed = json.loads((_project_file(_PROJECT_ROOT, PRIOR / 'CAMPAIGN-CLOSURE.json')).read_text())
    terminal = json.loads((_project_file(_PROJECT_ROOT, PRIOR / 'ACTUAL-READBACK-TERMINAL.json')).read_text())
    assert closed['whole_batch_valid'] and terminal['exit_code'] == 0
    assert closed['observed_actual_tables'] == 256
    before, text = adapted_template()
    namespace = {'__file__': str(Path(__file__).resolve()), '__name__': 'second_natural_preparation', 'change': change}
    exec(compile(text, str(Path(__file__).resolve()), 'exec'), namespace)
    namespace['main']('S02')
    out = _project_file(_PROJECT_ROOT, HERE / 'S02-natural-development-1')
    handles = json.loads((_project_file(_PROJECT_ROOT, PRIOR / 'ALL-PROCESS-HANDLES.json')).read_text())['processes']
    reused = [row for row in handles if row['block'] > 4]
    assert len(reused) == 4 and all(row['actual_tool_terminal']['exit_code'] == 0 for row in reused)
    for row in reused:
        name = f"BLOCK-{row['block']:02d}-TERMINAL.json"
        (out / name).write_bytes((_project_file(_PROJECT_ROOT, PRIOR / name)).read_bytes())
    (out / 'REUSED-PARENT-HANDLES.json').write_text(json.dumps({
        'source':str(PRIOR), 'processes':reused, 'new_parent_tables':0}, ensure_ascii=False, indent=2)+'\n')
    with gzip.open(out / 'SECOND-PREPARATION-DIFF.diff.gz', 'xb') as stream:
        stream.write(''.join(difflib.unified_diff(before.splitlines(True), text.splitlines(True))).encode())


if __name__ == '__main__':
    main()
