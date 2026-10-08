"""同源码提高离线工作量额度，保留原失败；不提高发布动作时限。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path
from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents
from hangma_bot.offline.vip_eoh_rebind import rebind_vip_research_budget
from root_load_and_probe import save,probe_candidate

HERE=Path(__file__).resolve().parent
original=json.loads((_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json')).read_text())
original.update(batch_id='vip-t48-same-source-research-4800000-20261002',max_operations=4800000)
save('S01-research.batch.json',original)
record=rebind_vip_research_budget(source_batch_file=_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'),
    source_package=_project_file(_PROJECT_ROOT, HERE/'S01-model-output-2'),target_batch_file=_project_file(_PROJECT_ROOT, HERE/'S01-research.batch.json'),
    out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-research-capacity'),execution_evidence_files=[_project_file(_PROJECT_ROOT, HERE/'PUBLIC-PROBE-CLOSURE.json')])
assert record['status']=='loaded_not_admitted'
save('CURRENT-RESEARCH-CANDIDATE-PACKAGE.json',{'relative_package':'S01-research-capacity',
    'relative_batch':'S01-research.batch.json','probe_closure':'RESEARCH-PUBLIC-PROBE-CLOSURE.json',
    'candidate_identity':record['identity'],'source_unchanged':True,'original_failure_preserved':True,
    'model_calls':0,'admission_or_deadline_credit':False,
    'reason':'human previously allowed strong but costly candidates to be researched and subsequently optimized; offline capacity only'})
probe_candidate('S01-research-capacity',batch_name='S01-research.batch.json',output_prefix='RESEARCH-')
