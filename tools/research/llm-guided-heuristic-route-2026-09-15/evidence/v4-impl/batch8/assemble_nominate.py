"""G 批次：组装正常通道档案与 panel_epoch，执行提名算法（v4 §8.3）。"""

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
import sitin_archive as arch  # noqa: E402

CANDS = {
    "i1-766712b6": "766712b65fafbaee16776eceaa288c3c1afa3f147a39fe70ab298d14eb3bb6ce",
    "m1-ab9b409e": "ab9b409e26e66158fdf3bb3b5f229b3930500a85ee14ed294c644c2e00a1c0af",
    "efficiency_seed-6d9c1d59": "6d9c1d5914509a966bf79a349142d41b2625c05eac55c28fb4b573b2ba56674e",
    "route_value_seed-1108e4be": "1108e4bef6ca6f9d3cce3d85c3d955e050028f2863f0e7f598f44e9667df6be2",
}

def load_samples(eval_dir: Path, mix: str, suffix: str = ""):
    """suffix：r2 目录（不同 seed 基）的根 id 重映射后缀——natural panel 的 root_id
    按序号命名（root01），不同 seed 基的同序号物理根必须区分，否则混聚违反
    独立来源根统计纪律。"""
    rows = []
    for line in (eval_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["scenario"] = "normal"
        row["opponent_mix"] = mix
        if suffix:
            for key in ("root_id", "source_root_id"):
                if row.get(key):
                    row[key] = row[key] + suffix
        rows.append(row)
    return rows

all_samples = {}
root_ids = {"H": set(), "M": set()}
for name, cid in CANDS.items():
    samples = []
    for mix in ("H", "M"):
        for sub in ("natural-" + mix, "natural-" + mix + "-r2"):
            d = BASE / "batch7" / "eval" / name / sub
            if not d.is_dir():
                continue
            sfx = "-r2" if sub.endswith("-r2") else ""
            for row in load_samples(d, mix, sfx):
                rid = row.get("root_id") or row.get("source_root_id")
                if rid:
                    root_ids[mix].add(rid)
                samples.append(row)
    all_samples[cid] = samples

print("root_ids:", {k: sorted(v) for k, v in root_ids.items()})
for cid, samples in all_samples.items():
    print(cid[:12], "samples:", len(samples),
          "roots:", len({r.get("root_id") or r.get("source_root_id") for r in samples}))

core_roots = (
    [{"root_id": rid, "opponent_mix": "H"} for rid in sorted(root_ids["H"])]
    + [{"root_id": rid, "opponent_mix": "M"} for rid in sorted(root_ids["M"])]
)
epoch = arch.build_channel_epoch("normal", core_roots, epoch_no=1)

entries = []
for name, cid in CANDS.items():
    entry = arch.build_archive_entry(cid, all_samples[cid], min_roots=1,
                                     source_ref={"evidence": "batch7/eval/" + name})
    entries.append(entry)

archive = arch.update_archive(entries)
result = arch.nominate_candidate(archive, epoch, budget=0)

out = BASE / "batch8"
out.mkdir(parents=True, exist_ok=True)
(out / "archive.json").write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
(out / "epoch-normal.json").write_text(json.dumps(epoch, ensure_ascii=False, indent=1), encoding="utf-8")
(out / "nomination.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1)[:1500])
