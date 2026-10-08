"""R6 真实条件链评估：I1（v4-flash 生成）vs V2——真前缀 + 完整剩余阶段。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

sys.path.insert(0, 'tools/offline/sitin')
import sitin_search as search
import sitin_opportunities as opp

AUTH = json.loads(Path(".team-work/tasks/sitin-phase3-v4/llm-authorization-r6.json").read_text(encoding="utf-8"))
BUDGETS = {"tokens_input": 8e6, "tokens_output": 8e6, "tables_full": 512.0,
           "tables_partial": 512.0, "prefix_generation": 64.0}

SRC = Path('tests/fixtures/research/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation/gen/i1/attempts/i1-a828da7533db/candidate.py').read_text(encoding="utf-8")

out = Path("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation/eval/i1-conditional")
out.mkdir(parents=True, exist_ok=True)
ledger = search.ActionValueLedger(out / "av-ledger.json", authorized_budgets=BUDGETS)

rc = opp.RuleConfig(ruleset_version="v26", base_score=1, you_cai_bi_kao=False)
runtime = opp.build_real_runtime(rules_config=rc, rounds_per_game=8)
print("real runtime keys:", sorted(runtime)[:5] if isinstance(runtime, dict) else type(runtime).__name__)

ev = search.run_av_evaluation(
    out, SRC, prefix_source="v2_behavior", predicate="branch_open", opponent="H",
    authorization=AUTH, attempts_cap=16, ledger=ledger, runtime=runtime)
print("ok:", ev.get("ok"), "| refused:", str(ev.get("refused"))[:60])
panel = ev.get("panel") or {}
print("attempts:", panel.get("prefix_attempts"))
print("generator:", panel.get("generator"), "| fixture_mode:", panel.get("fixture_mode"), "| engine_kind:", panel.get("engine_kind"))
scenarios = panel.get("scenarios", [])
print("scenarios:", len(scenarios), [s.get("status") for s in scenarios])
samples = ev.get("samples", [])
print("samples:", len(samples))
if samples:
    s0 = samples[0]
    print("sample real_tables:", s0.get("real_table_instances"), "| fixture:", s0.get("fixture_mode"))
    da = s0.get("double_arm") or {}
    for arm, payload in (da.get("arms") or {}).items():
        print(" ", arm, "status:", payload.get("status"),
              "U:", payload.get("u"), payload.get("u_low"), payload.get("u_high"),
              "err:", str(payload.get("error"))[:60])
print("ledger tables_partial:", ledger.spent("tables_partial"), "| full:", ledger.spent("tables_full"))
