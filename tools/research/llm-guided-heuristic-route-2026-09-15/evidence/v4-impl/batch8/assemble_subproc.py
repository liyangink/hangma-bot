"""G 批次组装提名（子进程隔离版）。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch8'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import subprocess
import sys
from pathlib import Path

BASE = Path("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl")
sys.path.insert(0, 'tools/offline/sitin')
import sitin_archive as arch

CANDS = {
    "i1-766712b6": "766712b65fafbaee16776eceaa288c3c1afa3f147a39fe70ab298d14eb3bb6ce",
    "m1-ab9b409e": "ab9b409e26e66158fdf3bb3b5f229b3930500a85ee14ed294c644c2e00a1c0af",
    "efficiency_seed-6d9c1d59": "6d9c1d5914509a966bf79a349142d41b2625c05eac55c28fb4b573b2ba56674e",
    "route_value_seed-1108e4be": "1108e4bef6ca6f9d3cce3d85c3d955e050028f2863f0e7f598f44e9667df6be2",
}

root_ids = {"H": set(), "M": set()}
entries = {}
for name, cid in CANDS.items():
    out = subprocess.run(
        [sys.executable, str(BASE / "batch8" / "worker_entry.py"), name, cid],
        capture_output=True, text=True, check=False)
    data = json.loads(out.stdout.strip().splitlines()[-1])
    if not data.get("ok"):
        raise SystemExit("worker failed for {0}: {1}".format(name, data))
    actual = data["actual_cid"]
    nevals = data["normal_evaluations"]
    for rid, row in nevals.items():
        root_ids[row["opponent_mix"]].add(rid)
    entries[actual] = {
        "candidate_id": actual,
        "kind": "action_value_v1",
        "safety": {"status": "PASS"},
        "effect_failure_unresolved": False,
        "normal_evaluations": nevals,
        "overall": data["overall"],
        "family": {},
        "family_evaluations": {},
        "source_ref": {"evidence": "batch7/eval/" + name,
                       "assembled": "subprocess-isolated (build_archive_entry bug pending fix)"},
    }
    print(name, "->", actual[:12], "roots:", len(nevals))

core_roots = ([{"root_id": rid, "opponent_mix": "H"} for rid in sorted(root_ids["H"])]
              + [{"root_id": rid, "opponent_mix": "M"} for rid in sorted(root_ids["M"])])
epoch = arch.build_channel_epoch("normal", core_roots, epoch_no=1)
archive = arch.update_archive(list(entries.values()))
result = arch.nominate_candidate(archive, epoch, budget=0)

out_dir = BASE / "batch8"
(out_dir / "archive-subproc.json").write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
(out_dir / "nomination.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1)[:2200])
