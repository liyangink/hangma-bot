"""查全部42配对的真正首次动作分歧，避免把首手相同当作策略相同。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import canonical, pin, save


def main():
    """逐步核共同公开前缀，记录第一次分歧；积分差只作后继关联。"""
    assert not (_project_file(_PROJECT_ROOT, HERE / "LATER-DIVERGENCES-CLOSED.json")).exists()
    closed_path = _project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-CONDITION-CLOSED.json")
    plan_path = _project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-CONDITION-PLAN.json")
    closed, plan = [json.loads(p.read_text()) for p in (closed_path, plan_path)]
    assert closed["complete"] and closed["source_stable"] and closed["resources_released"]
    assert closed["plan_pin"] == pin(plan_path)
    assert all(pin(Path(p)) == h for p, h in closed["files"].items())
    rows, public = [], []
    files = {str(p): pin(p) for p in (Path(__file__), closed_path, plan_path)}
    for index, target in enumerate(plan["targets"], 1):
        path = _project_file(_PROJECT_ROOT, SOURCE / "exploration-condition" / f"target-{index:03d}/decisions.jsonl.gz")
        files[str(path)] = pin(path)
        streams = {(s, a): [] for s in range(3) for a in ("A", "C")}
        with gzip.open(path, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                streams[row["sample"], row["arm"]].append(row["row"])
        for sample in range(3):
            a_rows, c_rows = streams[sample, "A"], streams[sample, "C"]
            changed = None
            for offset, (a, c) in enumerate(zip(a_rows, c_rows)):
                assert a["window_key"] == c["window_key"]
                assert canonical(a["observation"]) == canonical(c["observation"])
                assert a["legal_action_keys"] == c["legal_action_keys"]
                assert a["scoring_calls"][0]["input_capture"]["view_sha256"] == c["scoring_calls"][0]["input_capture"]["view_sha256"]
                if a["selected_action_key"] != c["selected_action_key"]:
                    changed = offset
                    public.append({
                        "target": index, "sample": sample, "original_label": target["case"]["label"],
                        "shared_focal_actions": offset, "A": a, "C": c,
                        "single_action_causal_claim": False,
                    })
                    break
            if changed is None:
                assert len(a_rows) == len(c_rows)
            comparison = next(
                p for p in closed["comparisons"] if p["target"] == index and p["sample"] == sample
            )
            rows.append({
                "target": index, "sample": sample, "original_label": target["case"]["label"],
                "same_first": a_rows[0]["selected_action_key"] == c_rows[0]["selected_action_key"],
                "first_divergence_offset": changed,
                "A_first_different": None if changed is None else a["selected_action_key"],
                "C_first_different": None if changed is None else c["selected_action_key"],
                "Hu_available": False if changed is None else "hu" in a["legal_action_keys"],
                "white_count_at_difference": None if changed is None else a["white_count"],
                "remaining_tiles": None if changed is None else a["observation"]["remaining_tile_count"],
                "C_minus_A": comparison["C_minus_A"],
            })
    raw_path = _project_file(_PROJECT_ROOT, HERE / "LATER-DIVERGENCES-PUBLIC.jsonl.gz")
    with gzip.open(raw_path, "xb") as output:
        for row in public:
            output.write(canonical(row) + b"\n")
    result = {
        "complete": True, "paired_continuations": len(rows), "rows": rows,
        "first_different_public_windows": len(public),
        "all_same_first_but_later_changed": sum(
            r["same_first"] and r["first_divergence_offset"] is not None for r in rows
        ),
        "public_rows_pin": pin(raw_path), "files": files,
        "new_scores_worlds_tables_models_HTTP": 0, "single_action_causal_claim": False,
    }
    save(_project_file(_PROJECT_ROOT, HERE / "LATER-DIVERGENCES-CLOSED.json"), result)
    print(json.dumps({
        k: result[k] for k in ("complete", "paired_continuations",
                              "first_different_public_windows", "all_same_first_but_later_changed")
    }))


if __name__ == "__main__":
    main()
