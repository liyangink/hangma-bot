
from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
EV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for p in (_project_file(_PROJECT_ROOT, ROOT/"src"), _project_file(_PROJECT_ROOT, ROUTE/"tools"), EV):
    sys.path.insert(0, str(p))
import confirmation_execution_identity as guard
import sitin_natural_panel as natural
import sitin_opportunities as opportunities
import sitin_search as search
import strong_seed_batch as batch
import r18_p16_catch_play_natural_exposure as p16
import claim_counterfactual_pilot as core
import r18_p9_midgame_hidden_world_teacher as p9
import r18_p11_settlement_cascade_teacher as p11
import r18_p13_development_seven_pairs_teacher as p13
import r18_p85_hu_deferral_natural_exposure as p85
print("imports OK")
print("CONTRACT", p85.CONTRACT, p85.CONTRACT.exists())
print("LIMITS", p16.LIMITS)
print("PANEL_SEED p85", p85.PANEL_SEED)
print("utc_now", search.utc_now())
print("unified", sorted(batch.unified_document(batch_label="probe", authorization_id="probe", accounts={"tables_full": 1}, issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False).keys()))
auth = batch.unified_document(batch_label="probe", authorization_id="probe", accounts={"tables_full": 1}, issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False)
print("budgets", search.av_ledger_budgets_from_authorization(auth))
print("require", natural.require_authorization(auth).get("authorization_id"))
