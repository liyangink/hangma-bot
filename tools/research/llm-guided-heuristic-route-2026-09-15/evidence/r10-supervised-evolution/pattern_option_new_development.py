"""两张已见清单通过后的新开发来源验证；固定32根512桌，不作正式确认。"""

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
import secrets
import statistics
import subprocess
import strong_seed_batch as b
import pattern_option_second_panel as previous
import curate_pattern_trace as curated
import route_executor_recovery as engine
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel

OUT=b.HERE/'pattern-option-new-dev-20260920'


def prepare():
    """先冻结源码、未使用面板种子、完整样本和分流；未看本批结果选样。"""
    assert not OUT.exists()
    previous_summary=previous.OUT/'summary.json'
    assert b.read(previous_summary)['continue_new_development'] is True
    derivation=b.read(curated.OUT/'derivation.json')
    source=curated.OUT/'candidate.py'
    assert b.digest(source.read_bytes())==derivation['curated_source_sha256']
    assert b.read(curated.OUT/'admission.json')['execution_safety_pass']
    seed=secrets.randbits(48)
    # 仅检查候选冻结前是否已有这个面板种子的记录；此处不生成或查看结果。
    scan=subprocess.run(['rg','-l','-F',str(seed),str(b.ROUTE/'evidence'),'-g','*.json','-g','*.jsonl','-g','*.md','-g','*.py'],capture_output=True,text=True,check=False)
    assert scan.returncode==1 and not scan.stdout, ('新种子已有记录或清单检索失败',scan.returncode,scan.stdout,scan.stderr)
    old=b.read(previous.OUT/'manifest.json')
    roots=list(range(1,17))
    plan={**old,'created_at_utc':b.search.utc_now(),'panel_seed':seed,'roots':roots,
        'sources':{'candidate':{'path':str(source),'sha256':b.digest(source.read_bytes())}},
        'full_tables':512,'max_full_tables':512,'tables_per_source':512,
        'scope':'候选冻结后首次签发的32个新开发根；仍沿用配置内配对设计，不是正式独立确认',
        'decision_rule':'全量512桌及完整结果、身份、费用通过；H/M相对稳定V2均正且等权识别差下界正才保留为正式确认准备对象；否则停止该提案追加，不改常数、不追加本批根。',
        'previous_summary_sha256':b.digest(previous_summary.read_bytes()),
        'curation_sha256':b.digest((curated.OUT/'derivation.json').read_bytes()),
        'seed_selection':'候选冻结后secrets.randbits(48)一次抽取，运行前登记；仓库证据文本无同值记录。不是对所有外部来源完整性的证明。',
        'seed_inventory_scan':{'returncode':scan.returncode,'scope':str(b.ROUTE/'evidence'),'file_types':['json','jsonl','md','py']},
        'trace_caveat':'已机械澄清未知底分输出标签，算术与控制流未变；新身份重新准入、用本批新结果验证，不改旧原答/旧成绩。',
        'model_calls':0,'confirmation_roots':0,'release_eligible':False}
    engine.verify(plan)
    OUT.mkdir();b.write(OUT/'manifest.json',plan)
    auth=b.unified_document(batch_label='pattern-new-development',authorization_id='r10-pattern-new-development',
        accounts={'tables_full':512},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；两张已见清单双正后固定32个新开发根，512桌零作者，不视为独立确认'
    b.write(OUT/'authorization.json',auth)
    b.write(OUT/'prepared.json',{'status':'READY','at_utc':b.search.utc_now()})
    print('new development frozen; 32 roots, 512 tables',flush=True)


def run():
    """全量固定执行；异常保留现场，不因中途得分重新抽样或重启。"""
    plan=b.read(OUT/'manifest.json');engine.verify(plan)
    assert b.read(OUT/'prepared.json')['status']=='READY'
    assert not (OUT/'started.json').exists()
    b.write(OUT/'started.json',{'at_utc':b.search.utc_now()})
    source=b.Path(plan['sources']['candidate']['path']).read_text()
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json');auth=b.read(OUT/'authorization.json')
    checks=[];stats={}
    for mix in plan['opponents']:
        engine.verify(plan)
        natural.run_natural_panel(candidate_source=source,opponent=mix,roots=len(plan['roots']),seats_per_root=4,
            contract=contract,out_dir=OUT/('natural-'+mix),authorization=auth,panel_seed=plan['panel_seed'],
            ledger_path=OUT/'ledger.json',ledger_authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth),min_roots=len(plan['roots']))
        panel=b.read(OUT/('natural-'+mix)/'panel.json')
        assert panel['identity']['candidate_source_sha256']==plan['sources']['candidate']['sha256']
        assert panel['identity']['panel_seed']==plan['panel_seed']
        checks.append(verify_full_panel(panel,contract,expected_identity=panel['identity'],
            expected_root_indices=plan['roots'],expected_rules_hash=plan['rules_hash']))
        stats[mix]=next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
        print(mix,checks[-1]['full_results_verified'],flush=True)
    engine.verify(plan)
    ledger=b.read(OUT/'ledger.json')
    assert ledger['spent']['tables_full']==512 and not any(r['status']=='reserved' for r in ledger['reservations'])
    root_rows=[row for s in stats.values() for row in s['root_rows']]
    low=statistics.mean(row['d_low'] for row in root_rows)
    b.write(OUT/'summary.json',{'status':'COMPLETE_NEW_DEVELOPMENT','statistics':stats,'verification':checks,
        'full_tables_verified':sum(c['full_results_verified'] for c in checks),'spent':ledger['spent'],
        'equal_mix_vs_v2':statistics.mean(s['mean_delta'] for s in stats.values()),'equal_mix_identification_low':low,
        'continue_confirmation_preparation':low>0 and all(s['mean_delta']>0 for s in stats.values()),
        'interval_kind':'平分识别区间，不是置信区间','confirmation_roots':0,'release_eligible':False})
    print('new development complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);args=p.parse_args()
    prepare() if args.action=='prepare' else run()
