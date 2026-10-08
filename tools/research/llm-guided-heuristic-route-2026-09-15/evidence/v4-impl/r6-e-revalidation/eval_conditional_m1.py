"""R6 M1 同合同条件重评。"""

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
SRC = Path('tests/fixtures/research/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation/gen/m1/attempts/m1-f028b5b3b18c/candidate.py').read_text(encoding="utf-8")

out = Path("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation/eval/m1-conditional")
out.mkdir(parents=True, exist_ok=True)
ledger = search.ActionValueLedger(
    Path("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation/eval/av-ledger.json"),
    authorized_budgets=AUTH.get("budgets"))
rc = opp.RuleConfig(ruleset_version="v26", base_score=1, you_cai_bi_kao=False)
runtime = opp.build_real_runtime(rules_config=rc, rounds_per_game=8)
ev = search.run_av_evaluation(out, SRC, prefix_source="v2_behavior", predicate="branch_open",
                              opponent="H", authorization=AUTH, attempts_cap=16,
                              ledger=ledger, runtime=runtime)
panel = ev.get("panel") or {}
print("ok:", ev.get("ok"), "| attempts:", panel.get("prefix_attempts", {}).get("hit"), "hits")
samples = ev.get("samples", [])
if samples:
    for arm, p in (samples[0].get("arms") or {}).items():
        print(" ", arm, p.get("policy_id") or p.get("focal_policy_id"),
              "U:", p.get("u"), "[", p.get("u_low"), ",", p.get("u_high"), "]")
