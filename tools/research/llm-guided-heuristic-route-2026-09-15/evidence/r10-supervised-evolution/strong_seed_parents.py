"""在强模型批次的同一冻结根集补评两个父代，保存完整终端结果。"""

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
import json
from pathlib import Path

import strong_seed_batch as batch
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel
from hangma_bot.simulation.artifacts import compute_rules_hash


def main(name):
    """每父代固定256桌；失败保留现场，不隐式重跑或改变清单。"""
    source_path=batch.HERE / {
        'parent-a':'mechanism-batch-04/run/iterations/iter-01/generation/candidate.py',
        'parent-b':'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py'}[name]
    out=batch.BATCH/name
    if out.exists(): raise SystemExit('父代目录已存在，不隐式重跑')
    reference=batch.BATCH/'hard-sol-high/run'
    state=batch.search.av_state_load(batch.search.av_latest_state_path(reference))
    ok,why,_=batch.search.av_verify_run_identity(state)
    if not ok: raise SystemExit(why)
    out.mkdir()
    auth=batch.unified_document(batch_label=name,authorization_id='r10-strong-'+name,
        accounts={'tables_full':256},issued_by='lead',issued_at_utc=batch.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户授权推进六份种子共同开发对照；固定256桌父代补评，无模型或确认'
    contract=batch.read(batch.ROUTE/'contracts/group-dev-v1.json')
    rules_hash=compute_rules_hash(batch.ROUTE.parents[1])
    source=source_path.read_text()
    batch.write(out/'authorization.json',auth)
    batch.write(out/'manifest.json',{'source_path':str(source_path),'source_sha256':batch.digest(source.encode()),
        'rules_hash':rules_hash,'panel_seed':2026092001,'roots':list(range(1,9)),
        'opponents':['H','M'],'seats':4,'tables':256,'release_eligible':False,
        'frozen_deps_digest':state['identity']['deps_digest']})
    results=[];means=[]
    for mix in ['H','M']:
        ok,why,_=batch.search.av_verify_run_identity(state)
        if not ok: raise SystemExit(why)
        natural.run_natural_panel(candidate_source=source,opponent=mix,roots=8,seats_per_root=4,
            contract=contract,out_dir=out/('natural-'+mix),authorization=auth,panel_seed=2026092001,
            ledger_path=out/'ledger.json',ledger_authorized_budgets=batch.search.av_ledger_budgets_from_authorization(auth),
            min_roots=8)
        panel=batch.read(out/('natural-'+mix)/'panel.json')
        results.append(verify_full_panel(panel,contract,expected_identity=panel['identity'],
            expected_root_indices=list(range(1,9)),expected_rules_hash=rules_hash))
        means.append(panel['statistics'])
        print(json.dumps({'parent':name,'mix':mix,'full_results_verified':results[-1]['full_results_verified']}),flush=True)
    batch.write(out/'full-result-reconciliation.json',{'results':results})
    ledger=batch.read(out/'ledger.json')
    batch.write(out/'batch-closure.json',{'status':'COMPLETE_PARENT_CORE','full_results_verified':256,
        'statistics':means,'spent':ledger['spent'],'release_eligible':False})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('name',choices=['parent-a','parent-b'])
    main(p.parse_args().name)
