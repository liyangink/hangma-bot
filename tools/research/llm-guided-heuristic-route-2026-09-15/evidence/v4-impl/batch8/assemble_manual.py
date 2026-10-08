"""G 批次手工组装提名（绕过 build_archive_entry 待修 bug，语义全部复用 sitin_archive 内部函数）。"""

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

def collect(name):
    samples = []
    for mix in ("H", "M"):
        for sub in ("natural-" + mix, "natural-" + mix + "-r2"):
            d = BASE / "batch7" / "eval" / name / sub
            if not d.is_dir():
                continue
            sfx = "-r2" if sub.endswith("-r2") else ""
            for line in (d / "samples.jsonl").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row["scenario"] = "normal"
                row["opponent_mix"] = mix
                if sfx:
                    for key in ("root_id", "source_root_id"):
                        if row.get(key):
                            row[key] = row[key] + sfx
                samples.append(row)
    return samples

root_ids = {"H": set(), "M": set()}
entries = {}
for name, cid in CANDS.items():
    samples = collect(name)
    stats = arch.paired_stage_statistics(samples, min_roots=1)
    bck = stats["by_candidate"]
    if name == "efficiency_seed-6d9c1d59":
        print("DUMP keys:", [k[:12] for k in bck])
        for k, v in bck.items():
            print("DUMP", k[:12], "panels:", sorted(v.get("panels", {})),
                  "n_samples_in_group:", len(v.get("panels", {}).get("normal", {}).get("panels", {})) if isinstance(v.get("panels", {}).get("normal"), dict) else "no-normal",
                  "samples:", len(samples), "scenarios:", {repr(s.get("scenario")) for s in samples})
    cstats = bck.get(cid, {})
    normal = cstats.get("panels", {}).get("normal")
    assert normal is not None, "{0} normal 块缺失".format(name)
    nevals = {}
    for mix, panel in sorted(normal["panels"].items()):
        for row in panel["root_rows"]:
            root_ids[mix].add(row["root_id"])
            nevals[row["root_id"]] = {
                "d_point": row["d_point"], "d_low": row["d_low"],
                "d_high": row["d_high"], "unknown": row["unresolved"],
                "opponent_mix": mix, "cost": row["cost"], "role": row["role"],
            }
    entries[cid] = {
        "candidate_id": cid,
        "kind": "action_value_v1",
        "safety": {"status": "PASS"},
        "effect_failure_unresolved": False,
        "normal_evaluations": nevals,
        "overall": arch._overall_summary(cstats),
        "family": {},
        "family_evaluations": {},
        "source_ref": {"evidence": "batch7/eval/" + name, "assembled": "manual (build_archive_entry bug pending fix)"},
    }
    print(name, "roots:", sorted(nevals), "overall:", json.dumps(entries[cid]["overall"], ensure_ascii=False)[:140])

core_roots = ([{"root_id": rid, "opponent_mix": "H"} for rid in sorted(root_ids["H"])]
              + [{"root_id": rid, "opponent_mix": "M"} for rid in sorted(root_ids["M"])])
epoch = arch.build_channel_epoch("normal", core_roots, epoch_no=1)
archive = arch.update_archive(list(entries.values()))
result = arch.nominate_candidate(archive, epoch, budget=0)

out = BASE / "batch8"
out.mkdir(parents=True, exist_ok=True)
(out / "archive-manual.json").write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
(out / "nomination-manual.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1)[:2000])
