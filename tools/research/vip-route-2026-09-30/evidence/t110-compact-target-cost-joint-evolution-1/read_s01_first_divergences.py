"""只读完整桌动作记录，区分终分持平和整段动作持平。

只给已闭合开发来源计数；不调用评分、规则或模拟，不把换座当独立
来源。不从未来结局给首动作贴正确标签。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
NEW = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S01-natural-development-1')
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S01-natural-development-1')


def normalize(value):
    """父子场次标识不同，仅移除game_id，其余窗口事实保留。"""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != "game_id"}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def main():
    """在统一核验已通过后检查全部64对子代／父代动作序列。"""
    closure = json.loads((_project_file(_PROJECT_ROOT, NEW / "CAMPAIGN-CLOSURE.json")).read_text())
    terminal = json.loads((_project_file(_PROJECT_ROOT, NEW / "ACTUAL-READBACK-TERMINAL.json")).read_text())
    assert closure["whole_batch_valid"] and terminal["exit_code"] == 0
    counts, differences, changed_roots = Counter(), [], set()
    for block in range(1, 5):
        child_id = json.loads((_project_file(_PROJECT_ROOT, NEW / f"BLOCK-{block:02d}-PLAN.json")).read_text())["candidate_identity"]["candidate_id"]
        parent_id = json.loads((_project_file(_PROJECT_ROOT, PRIOR / f"BLOCK-{block+4:02d}-PLAN.json")).read_text())["candidate_identity"]["candidate_id"]
        for path in sorted((_project_file(_PROJECT_ROOT, NEW / f"block-{block:02d}")).glob("group-*.json.gz")):
            with gzip.open(path, "rt") as stream:
                child_group = json.load(stream)
            with gzip.open(_project_file(_PROJECT_ROOT, PRIOR / f"block-{block+4:02d}" / path.name), "rt") as stream:
                parent_group = json.load(stream)
            child = next(r for r in child_group["match_records"] if r["match_id"].endswith("vip:" + child_id))
            parent = next(r for r in parent_group["match_records"] if r["match_id"].endswith("vip:" + parent_id))
            cs, ps = child["outcome"]["decisions"], parent["outcome"]["decisions"]
            counts["paired_candidate_tables"] += 1
            first = next((i for i, (p, c) in enumerate(zip(ps, cs))
                          if normalize(p["window_key"]) != normalize(c["window_key"])
                          or p["seat"] != c["seat"] or p["action_key"] != c["action_key"]), None)
            if first is None:
                if len(ps) != len(cs):
                    raise ValueError("动作相同前缀后长度不同，须另行定位")
                counts["full_action_sequence_identical_tables"] += 1
                continue
            p, c = ps[first], cs[first]
            same_window = normalize(p["window_key"]) == normalize(c["window_key"]) and p["seat"] == c["seat"]
            root = path.name.split("-")[1]
            changed_roots.add(root)
            counts["action_sequence_changed_tables"] += 1
            counts["first_difference_common_window"] += same_window
            counts["first_difference:" + p["action_key"].split(":")[0] + "->" + c["action_key"].split(":")[0]] += 1
            differences.append({"root_serial": root, "group_file": path.name, "first_decision_index": first,
                                "same_window_and_seat": same_window, "window": normalize(p["window_key"]),
                                "seat": p["seat"], "parent_action": p["action_key"], "child_action": c["action_key"],
                                "scope": "known complete-development first divergence; public observation equality still to verify"})
    assert counts["paired_candidate_tables"] == 64
    result = {"scope": "complete_exposed_development_action_sequences_not_single_action_value",
              "counts": dict(counts), "independent_changed_roots": sorted(changed_roots),
              "differences": differences, "new_business_calls": 0,
              "closure_sha256": hashlib.sha256((_project_file(_PROJECT_ROOT, NEW / "CAMPAIGN-CLOSURE.json")).read_bytes()).hexdigest(),
              "reader_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (_project_file(_PROJECT_ROOT, HERE / "S01-COMPLETE-FIRST-DIVERGENCES.json")).open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"counts": dict(counts), "changed_roots": sorted(changed_roots),
                      "first_differences": differences}, ensure_ascii=False))


if __name__ == "__main__":
    main()
