"""在原开发正反起点上测试第二子代；只要求原父尾段精确复现。"""

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
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from prepare_second_author import pin

HERE = Path(__file__).resolve().parent


def main():
    """复制已验恢复材料，冻结新公式整段续打，零业务调用。"""
    probe = _project_file(_PROJECT_ROOT, HERE / 'S02-public-probe')
    checked = json.loads((probe / 'ROOT-READBACK.json').read_text())
    assert checked['complete'] and checked['actual_tool_terminal']['exit_code'] == 0
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    package = _project_file(_PROJECT_ROOT, HERE / 'S02-model-output')
    child = load_vip_parents([package], VipEohBatch.read(batch_file))[0]
    reader = (_project_file(_PROJECT_ROOT, HERE / 'S01-continuation-root009/readback.py')).read_text()
    reader = reader.replace("assert len(groups) == plan['max_continuations'] == 6", "assert len(groups) == plan['max_continuations'] == 3")
    ast.parse(reader)
    jobs = []
    for case in ('root003-loss', 'root030-gain'):
        old = _project_file(_PROJECT_ROOT, HERE / ('S01-fresh-' + case))
        out = _project_file(_PROJECT_ROOT, HERE / ('S02-fresh-' + case))
        out.mkdir(exist_ok=False)
        plan = json.loads((old / 'RUN-PREPARED.json').read_text())
        for n in ('run_causal.py', 'io_helpers.py', 'TEACHER-SOURCE-TRACES.json.gz', 'PUBLIC-TARGETS.json'):
            (out / n).write_bytes((old / n).read_bytes())
        (out / 'readback.py').write_text(reader)
        plan.update(child_source_file=str(package / 'candidate.py'), child_identity=child['identity'],
            status='prepared_not_started', scope='second whole child at exposed parent start; old S01 C is historical reference only',
            predecessor_results={'directory':str(old),'S01_C_reference_not_current_child':True,'outcomes_not_transferred':True})
        files = [Path(__file__), out / 'run_causal.py', out / 'io_helpers.py', out / 'readback.py',
            out / 'TEACHER-SOURCE-TRACES.json.gz', out / 'PUBLIC-TARGETS.json',
            package / 'candidate.py', package / 'generation.json', batch_file,
            probe / 'ROOT-READBACK.json', probe / 'ACTUAL-READBACK-TERMINAL.json',
            old / 'ROOT-READBACK.json', old / 'ACTUAL-READBACK-TERMINAL.json',
            Path(plan['raw_source_file'])]
        plan['files'] = {str(p): pin(p) for p in files}
        with (out / 'RUN-PREPARED.json').open('x') as stream:
            json.dump(plan, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
        jobs.append({'directory':str(out),'continuations':3,'focal_seat':plan['focal_seat']})
    with (_project_file(_PROJECT_ROOT, HERE / 'S02-FRESH-DIAGNOSTIC-PREPARATION.json')).open('x') as stream:
        json.dump({'complete':True,'jobs':jobs,'new_models_rules_scores_worlds_tables':0}, stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print({'prepared':True,'jobs':2,'continuations':6,'business_calls':0})


if __name__ == '__main__':
    main()
