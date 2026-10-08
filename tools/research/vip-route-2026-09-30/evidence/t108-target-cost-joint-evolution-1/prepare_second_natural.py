"""复用已闭合父代对照，只新跑第二子代的256个桌赛实例。

沿用已冻结的32来源、四换座、对手组成和判据。适应性开发不授留出
信用；读取器区分新费用、历史复用费用与实际参与分析的数据量。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1/S01-natural-development-1')


def change(text, old, new):
    """模板只有唯一已知位置才能改写，漂移不转成业务重跑。"""
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    """所有评分和续打实际结束后才冻结新八块；准备本身不推进世界。"""
    old = (_project_file(_PROJECT_ROOT, HERE / 'prepare_natural.py')).read_text()
    text = old
    text = change(text, "    batch_file = HERE / 'AUTHOR-BATCH.json'", """    for label in ('root003-loss', 'root030-gain'):
        path = HERE / (slot + '-fresh-' + label)
        actual = json.loads((path / 'ROOT-READBACK.json').read_text())
        assert actual['complete'] and actual['actual_tool_terminal']['exit_code'] == 0
        causal_files.extend([path / 'ROOT-READBACK.json', path / 'CAUSAL-CLOSURE.json'])
    prior = HERE / 'S01-natural-development-1'
    closed_parent = json.loads((prior / 'CAMPAIGN-CLOSURE.json').read_text())
    closed_terminal = json.loads((prior / 'ACTUAL-READBACK-TERMINAL.json').read_text())
    assert closed_parent['whole_batch_valid'] and closed_terminal['exit_code'] == 0
    batch_file = HERE / 'AUTHOR-BATCH.json'""")
    text = change(text, "    (out / 'run_block.py').write_text(runner)", """    runner = runner.replace('choices=range(1,17)', 'choices=range(1,9)')
    runner = runner.replace('sixteen_block512table_pilot', 'eight_new_block256table_pilot')
    runner = runner.replace('保留512分母', '保留256新实例分母')
    (out / 'run_block.py').write_text(runner)""")
    marker = "    ast.parse(reader)\n    (out / 'close_pilot.py').write_text(reader)"
    reader_changes = """    reader = change(reader, 'HERE=Path(__file__).resolve().parent',
        'HERE=Path(__file__).resolve().parent\\nPRIOR=Path(' + repr(str(prior)) + ')')
    reader = change(reader, "path=HERE/f'block-{i:02d}/costs.json'",
        "path=(PRIOR if i>8 else HERE)/f'block-{i:02d}/costs.json'")
    reader = change(reader, "'charged_instances':sum(e['charged_table_instances'] for e in es),",
        "'charged_instances':sum(e['charged_table_instances'] for e in es),'reused_prior_closed':i>8,'new_charged_instances':sum(e['charged_table_instances'] for e in es) if i<=8 else 0,")
    reader = change(reader, "out=HERE/f'block-{i:02d}';bp=json.loads((HERE/f'BLOCK-{i:02d}-PLAN.json').read_text())",
        "out=(PRIOR if i>8 else HERE)/f'block-{i:02d}';bp=json.loads(((PRIOR if i>8 else HERE)/f'BLOCK-{i:02d}-PLAN.json').read_text())")
    reader = change(reader, "assert helper.sha(out/'RUNNER.py')==helper.sha(HERE/'run_block.py')",
        "assert helper.sha(out/'RUNNER.py')==helper.sha((PRIOR if i>8 else HERE)/'run_block.py')")
    reader = change(reader, "'planned_actual_tables':512,'observed_actual_tables':sum(c['actual_started_known_subtotal'] for c in costs),",
        "'planned_actual_tables':256,'observed_actual_tables':sum(c['actual_started_known_subtotal'] for c in costs if not c['reused_prior_closed']), 'analysed_historically_executed_tables':512, 'reused_prior_actual_tables':256, 'new_hands':2048, 'whole_batch_development_actual_cost_including_S01':768,")
    reader = reader.replace('thirty-two pre-author development roots',
        'thirty-two previously exposed adaptive development roots; parent results reused with zero new parent costs')
    ast.parse(reader)
    (out / 'close_pilot.py').write_text(reader)"""
    text = change(text, marker, reader_changes)
    text = change(text, "HERE / 'AUTHOR-PREPARATION-CLOSED.json',", "HERE / 'S02-AUTHOR-PREPARATION-CLOSED.json',")
    text = change(text, "parent_package / 'candidate.py', parent_package / 'generation.json', *causal_files]",
        "parent_package / 'candidate.py', parent_package / 'generation.json', prior / 'CAMPAIGN-CLOSURE.json', prior / 'ACTUAL-READBACK-TERMINAL.json', prior / 'ALL-PROCESS-HANDLES.json', *causal_files]")
    text = change(text, "'stage': 'pre-author reserved fresh development, not confirmation',",
        "'stage': 'same32 exposed adaptive development, not confirmation; zero new parent worlds',")
    text = change(text, "'planned_actual_tables': 512, 'planned_hands': 4096, 'blocks': 16,",
        "'planned_actual_tables': 256, 'planned_hands': 2048, 'blocks': 8, 'analysed_dataset_tables':512, 'reused_parent_actual_tables':256, 'max_batch_development_actual_tables_including_S01':768,")
    text = text.replace('until all16 actual handles terminal', 'until all8 new actual handles terminal; eight parent handles already terminal')
    text = text.replace('original512 denominator retained', 'original256 new-instance denominator retained; prior256 parent evidence remains historical')
    # 旧父代结果用于当前共同开发对照，但不移转准入信用。
    text = change(text, "'old_admission_or_results_transferred': False,", "'old_admission_or_results_transferred': False, 'prior_parent_results_explicitly_reused':True,")
    text = change(text, '    for block in range(1, 17):', '    for block in range(1, 9):')
    text = change(text, "'actual_tables_planned': 512,", "'actual_tables_planned': 256, 'historical_parent_tables_reused':256,")
    ast.parse(text)
    # 同一源码生成器在本文件命名空间中执行，不修改原S01准备工具。
    namespace = {'__file__': str(Path(__file__).resolve()), '__name__': 'second_natural_preparation_template'}
    exec(compile(text, str(Path(__file__).resolve()), 'exec'), namespace)
    namespace['main']('S02')
    out = _project_file(_PROJECT_ROOT, HERE / 'S02-natural-development-1')
    prior_handles = json.loads((_project_file(_PROJECT_ROOT, PRIOR / 'ALL-PROCESS-HANDLES.json')).read_text())['processes']
    reused = [r for r in prior_handles if r['block'] > 8]
    assert len(reused) == 8 and all(r['actual_tool_terminal']['exit_code'] == 0 for r in reused)
    for row in reused:
        name = f"BLOCK-{row['block']:02d}-TERMINAL.json"
        (out / name).write_bytes((_project_file(_PROJECT_ROOT, PRIOR / name)).read_bytes())
    (out / 'REUSED-PARENT-HANDLES.json').write_text(json.dumps({'source':str(PRIOR),
        'processes':reused, 'new_parent_tables':0},ensure_ascii=False,indent=2)+'\n')
    (out / 'LIVE-PROCESS-HANDLES.json').write_text(json.dumps({'processes':reused,
        'remaining_blocks_not_started':list(range(1,9)), 'all_handles_known':False,
        'planned_new_actual_tables':256,'reused_historical_actual_tables':256,
        'inspection':'new progress/cost/fault only until8 new terminals'},ensure_ascii=False,indent=2)+'\n')
    with gzip.open(out / 'SECOND-PREPARATION-DIFF.diff.gz','xb') as f:
        import difflib
        f.write(''.join(difflib.unified_diff(old.splitlines(True),text.splitlines(True))).encode())


if __name__ == '__main__':
    main()
