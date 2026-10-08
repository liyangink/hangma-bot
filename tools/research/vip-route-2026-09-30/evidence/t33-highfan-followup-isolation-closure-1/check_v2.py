"""纯读两个已结束分歧实验；核实际输入、真父分、首动作与后段精确复现。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t33-highfan-followup-isolation-closure-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t33-highfan-followup-isolation-preparation-1')
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-source-preparation-1')


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def material(directory):
    paths, scores = defaultdict(list), {}
    for line in (directory / "calls-and-choices.jsonl").open():
        row = json.loads(line)
        key = row["root_id"], row.get("variant"), row.get("arm")
        if row["event"] == "advance" and row["status"] == "advanced":
            paths[key].append(row["choices"])
        if row["event"] == "score_call" and row["kind"] == "C":
            scores[(*key, canonical(row["window_key"]))] = row
    return paths, scores


def main():
    plan, result, start = (read(_project_file(_PROJECT_ROOT, SOURCE / name)) for name in ("PREPARED.json", "COSTS-AND-RESULT.json", "ROOT-START.json"))
    assert result["status"] == "diagnostic_batch_closed_not_strength_confirmation"
    for path, expected in start["gate_files"].items():
        assert pin(Path(path)) == expected
    files = {str(p.resolve()): pin(p) for p in SOURCE.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert read(_project_file(_PROJECT_ROOT, HERE / "RAW-FIRST-SEAL.json"))["files"] == files
    spec = importlib.util.spec_from_file_location("t26_existing_core_pure_checker", _project_file(_PROJECT_ROOT, HERE / "base_check.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = module.check(SOURCE)
    assert plan["planned_continuation_instances"] == result["completed_arms"] == 20
    assert plan["planned_source_windows"] == 4 and plan["planned_mother_roots"] == 3
    assert plan["variant_order"] == ["closed_recorded_world"]
    assert result["actual_calls"].get("public_hidden_resample_calls", 0) == 0
    assert result["actual_calls"]["target_preflight_projection_calls"] == 4
    paths, scores = material(SOURCE)
    old_paths, old_scores = material(OLD)
    previous = read(_project_file(_PROJECT_ROOT, OLD / "PREPARED.json"))
    rows, checked_paths, decisions = [], 0, 0
    for ordinal, root in enumerate(plan["roots"], 1):
        rd = _project_file(_PROJECT_ROOT, SOURCE / f"root-{ordinal:02d}")
        nested = root["nested_start"]
        restored = read(rd / "NESTED-START.json")
        assert restored["status"] == "restored_closed_nested_start"
        assert restored["successful_prefix_advances"] == nested["original_advance_cut"]
        assert restored["target_window"] == root["source"]["target_window"]
        assert restored["focal_observation"] == nested["focal_observation"]
        preflight = read(rd / "TARGET-INPUT-PREFLIGHT.json")
        assert preflight["view_sha256"] == root["source"]["source_C_full_DTO_sha256"] and preflight["score_calls"] == 0
        variant = plan["variant_order"][0]
        old_root, old_variant = nested["original_T32_root_id"], nested["original_T32_variant"]
        key = canonical(root["source"]["target_window"])
        outcomes = {a: read(rd / variant / (a + "-outcome.json")) for a in plan["arm_order"]}
        for arm in ("A", "Sol-C", "S02-C"):
            assert "force_count" not in outcomes[arm]
        for name in ("Sol", "S02"):
            assert outcomes[name + "-B"]["force_count"] == 1
            assert outcomes[name + "-C"]["first_action_key"] == outcomes[name + "-B"]["first_action_key"]
            new = scores[root["root_id"], variant, name + "-C", key]
            old = old_scores[old_root, old_variant, name + "-C", key]
            assert new["input_capture"]["view_sha256"] == old["input_capture"]["view_sha256"] == root["source"]["source_C_full_DTO_sha256"]
            assert {e["action_key"]: e["score"] for e in new["scores"]["entries"]} == {e["action_key"]: e["score"] for e in old["scores"]["entries"]}
            assert new["ranking"][0] == outcomes[name + "-C"]["first_action_key"]
            assert paths[root["root_id"], variant, name + "-C"] == old_paths[old_root, old_variant, name + "-C"][nested["original_advance_cut"]:]
            old_ordinal = next(i for i, r in enumerate(previous["roots"], 1) if r["root_id"] == old_root)
            old_outcome = read(_project_file(_PROJECT_ROOT, OLD / f"root-{old_ordinal:02d}" / old_variant / (name + "-C-outcome.json")))
            assert outcomes[name + "-C"]["settlement"] == old_outcome["settlement"]
            checked_paths += 1
            decisions += sum(len(frame) for frame in paths[root["root_id"], variant, name + "-C"])
        net = {a: o["focal_net_score"] for a, o in outcomes.items()}
        rows.append({"mother_root": root["mother_root"], "original_T32_variant": old_variant,
                     "target_window": root["source"]["target_window"],
                     "first_action_keys": {a: o["first_action_key"] for a, o in outcomes.items()},
                     "focal_single_hand_scores": net,
                     "child_C_minus_parent_C": net["Sol-C"] - net["S02-C"],
                     "child_first_B_minus_parent_first_B": net["Sol-B"] - net["S02-B"],
                     "child_followup_C_minus_own_B": net["Sol-C"] - net["Sol-B"],
                     "parent_followup_C_minus_own_B": net["S02-C"] - net["S02-B"],
                     "settlements": {a: o["settlement"] for a, o in outcomes.items()},
                     "known_development_not_confirmation": True})
    for path, expected in files.items():
        assert pin(Path(path)) == expected
    receipt = {**base, "schema": "t33-highfan-followup-causal-closure/1", "planned_mother_roots": 3,
               "qualified_mother_roots": 3, "qualified_source_windows": 4,
               "worlds": 4, "complete_single_hand_continuations": 20,
               "all_normal_A_C_unforced": True, "only_B_first_forced_once": True,
               "child_and_true_T24_full_target_score_maps_exact": 8,
               "prior_C_full_tail_paths_exact": checked_paths, "prior_all_seat_tail_decisions_exact": decisions,
               "new_hidden_worlds": 0, "new_independent_reviews": 0,
               "not_confirmation_or_release": True}
    write("ROOT-CLOSED-CHECK.json", receipt)
    write("DEVELOPMENT-BEHAVIOR.json", {"status": "closed_known_highfan_subsequent_isolation",
                                       "independent_mother_roots": 3, "rows": rows})
    print(json.dumps({k: receipt[k] for k in ("status", "C_score_calls", "R18_score_calls", "unique_actual_full_inputs", "prior_C_full_tail_paths_exact")}))
    print(json.dumps([{k: r[k] for k in ("original_T32_variant", "first_action_keys", "focal_single_hand_scores", "child_first_B_minus_parent_first_B", "child_followup_C_minus_own_B", "parent_followup_C_minus_own_B")} for r in rows], ensure_ascii=False))


if __name__ == "__main__":
    main()
