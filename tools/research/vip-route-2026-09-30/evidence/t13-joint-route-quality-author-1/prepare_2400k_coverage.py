"""T13闭合单根的行动前覆盖面板；沿已登记分层，只读A轨迹，不挑赢牌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib,json
from pathlib import Path
from hangma_bot.offline.vip_eoh_input_sources import build_public_input_panel
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1')
RAW=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/S01-natural-recording-2400k-16')
SEAL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/natural-2400k-closure-1/RAW-FIRST-SEAL.json')
AUDIT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/natural-2400k-closure-1/AUDIT.json')
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads(AUDIT.read_text())
assert a['accepted_engineering_chain'] and a['tables']==16 and a['runtime_faults_all_zero']
prereg=json.loads((_project_file(_PROJECT_ROOT, BASE/'2400K-COVERAGE-EXPANSION-PREREG.json')).read_text())
assert prereg['source_dir']==str(RAW) and prereg['selection_limits']=={'per_stratum':1,'max_windows':64,'max_windows_per_source_root':64}
spec={'schema':'vip-eoh-input-source/2','source_id':'t13-2400k-natural-root1-A','source_kind':prereg['source_kind'],'audit_dir':str(RAW),'raw_seal':{'path':str(SEAL),'sha256':h(SEAL)},'manifest':{'path':str(_project_file(_PROJECT_ROOT, RAW/'manifest.json')),'sha256':h(_project_file(_PROJECT_ROOT, RAW/'manifest.json'))}}
sf=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/2400K-NATURAL-SOURCE-SPEC.json')
with sf.open('x') as f:json.dump(spec,f,ensure_ascii=False,indent=2);f.write('\n')
start={'schema':'t13-coverage-panel-build-start/1','status':'START','source_spec_sha256':h(sf),'raw_seal_sha256':h(SEAL),'root_audit_sha256':h(AUDIT),'prereg_sha256':h(_project_file(_PROJECT_ROOT, BASE/'2400K-COVERAGE-EXPANSION-PREREG.json')),'actual_table_or_model_or_score_calls_in_builder':0,'prior_known_development_source_not_confirmation':True}
with (_project_file(_PROJECT_ROOT, BASE/'ROOT-2400K-COVERAGE-BUILD-START.json')).open('x') as f:json.dump(start,f,ensure_ascii=False,indent=2);f.write('\n')
panel=build_public_input_panel([{'path':str(sf),'sha256':h(sf)}],_project_file(_PROJECT_ROOT, BASE/'2400k-natural-coverage-panel-1'),limits=prereg['selection_limits'])
plan=json.loads((_project_file(_PROJECT_ROOT, BASE/'S01-2400k-PROBE-PLAN.json')).read_text())
plan['input_view_limits']['max_views']=64
pf=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/S01-2400k-COVERAGE-PROBE-PLAN.json')
with pf.open('x') as f:json.dump(plan,f,ensure_ascii=False,indent=2);f.write('\n')
start={'schema':'t13-coverage-public-probe-start/1','status':'START','panel_sha256':h(_project_file(_PROJECT_ROOT, BASE/'2400k-natural-coverage-panel-1/panel.json')),'plan_sha256':h(pf),'window_count':panel['window_count'],'planned_scores':2*panel['window_count'],'new_model_calls':0,'new_table_calls':0,'selection_uses_final_results':False,'not_confirmation':True}
with (_project_file(_PROJECT_ROOT, BASE/'ROOT-2400K-COVERAGE-PROBE-START.json')).open('x') as f:json.dump(start,f,ensure_ascii=False,indent=2);f.write('\n')
print(start)
