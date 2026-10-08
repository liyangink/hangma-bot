"""修根封套缺字段，保留作者原答及失败；新包装不产生作者或API调用。"""

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
from datetime import datetime,timezone
from pathlib import Path
from hangma_bot.offline.vip_eoh_generate import run_vip_eoh_generate,VipEohBatch,load_vip_parents
from root_load_and_probe import probe_candidate,save,pin

HERE=Path(__file__).resolve().parent
delivery=json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-DELIVERY.json')).read_text())
for name,expected in delivery['files'].items(): assert pin(_project_file(_PROJECT_ROOT, HERE/name))==expected
envelope=json.loads((_project_file(_PROJECT_ROOT, HERE/'REPLAY-ENVELOPE.json')).read_text())
envelope.update(delegator='/root via /root/t48_sol_max_natural_highfan_joint_author',
                captured_at_utc=datetime.now(timezone.utc).isoformat(),
                note='Same immutable author answer. Root adds required delegator; failed envelope retained. Zero model repair/API calls; backend/tokens unknown.')
save('REPLAY-ENVELOPE-2.json',envelope)
record=run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'),out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-model-output-2'),
    operator='i1',backend='replay',feedback=(_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text(),reply_file=_project_file(_PROJECT_ROOT, HERE/'REPLAY-ENVELOPE-2.json'))
assert record['status']=='loaded_not_admitted',record['error']
batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'))
candidate=load_vip_parents([_project_file(_PROJECT_ROOT, HERE/'S01-model-output-2')],batch)[0]
save('CURRENT-CANDIDATE-PACKAGE.json',{'relative_package':'S01-model-output-2','candidate_identity':candidate['identity'],
    'root_only_packaging_recovery':True,'author_source_unchanged':True,'actual_author_delegations':1,
    'repair_model_calls':0,'replay_new_model_calls':0})
probe_candidate('S01-model-output-2')
