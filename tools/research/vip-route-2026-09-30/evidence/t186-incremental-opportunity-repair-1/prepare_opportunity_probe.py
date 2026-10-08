"""冻结全部不同来源改选与两个失胡控制；条件样本不充当自然增强证据。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

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

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, OLD, pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """先封存目标、抽样律、费用和源码，再产生世界；不挑隐藏抽样结果。"""
    gate = json.loads((_project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")).read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    rows = [json.loads(x) for x in (_project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")).read_text().splitlines()]
    cases = {c["label"]: c for c in json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"]}
    paths = {f"closed-confirmation:{r['ordinal']:03d}": r for r in
        [json.loads(x) for x in (_project_file(_PROJECT_ROOT, HERE / "confirmation-paths/rows.jsonl")).read_text().splitlines()]}
    selected, used = [], set()
    for row in sorted(rows, key=lambda r: r["label"]):
        if row["first_changed"] and row["root_id"] not in used:
            assert row["label"] in paths and row["parent_first"] == "hu"
            selected.append((row, row["candidate_first"], "不同来源实际改选，按公开原标签取首条；全七来源"))
            used.add(row["root_id"])
    assert len(selected) == 7
    # root019是与三白释放正例相近的既有双白失胡反例；root002为最早不同来源控制。
    # 二者均已被公开诊断与作者材料暴露，选择不是新独立验证抽样。
    for root_id in ["t185-confirmation-002", "t185-confirmation-019"]:
        row = next(r for r in rows if r["root_id"] == root_id and "wait_lost" in r["classes"])
        assert row["parent_first"] == row["candidate_first"] == "hu"
        selected.append((row, cases[row["label"]]["S02_first"], "已暴露失胡控制；B强制旧S02继续，A/C仍及时胡"))
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
    proposal = load_vip_parents([package], batch)[0]
    assert proposal["identity"] == gate["identity"]
    parent = _project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-incremental-model-output/candidate.py")
    original = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json")).read_text())
    targets, source_paths = [], []
    for row, forced, why in selected:
        case = dict(cases[row["label"]])
        case["legal_action_keys"] = sorted(e["action_key"] for e in case["original_S02_entries"])
        path = paths[row["label"]]
        closure_path = _project_file(_PROJECT_ROOT, PRIOR / f"natural-confirmation/root-{path['root_index']:03d}/seat-{path['rotation']}-arm-0/CLOSURE.json")
        closure = json.loads(closure_path.read_text())
        assert closure["complete"] and closure["root"]["root_id"] == row["root_id"]
        targets.append({"case": case, "composition": closure["root"], "focal_seat": path["rotation"],
            "source_closure": str(closure_path), "parent_first": row["parent_first"],
            "candidate_first": row["candidate_first"], "forced_first": forced, "selection": why})
        source_paths.append(closure_path)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_opportunity_probe.py"), _project_file(_PROJECT_ROOT, HERE / "close_opportunity_probe.py"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "CASES.json"), _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json"),
        _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl"), _project_file(_PROJECT_ROOT, HERE / "confirmation-paths/rows.jsonl"),
        parent, package / "candidate.py", package / "generation.json", package / "DERIVATION.json",
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-model-output/generation.json"), _project_file(_PROJECT_ROOT, PRIOR / "common.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "reuse_causal_helpers.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"), _project_file(_PROJECT_ROOT, PRIOR / "t185_prepare_confirmation.py"),
        OLD / "run_causal.py", *source_paths]
    save(_project_file(_PROJECT_ROOT, HERE / "OPPORTUNITY-PROBE-PLAN.json"), {"schema": "t186-public-conditional-opportunity-probe/1",
        "targets": targets, "arms_sources": {"parent": {"source_file": str(parent), "identity": batch.identity(parent.read_text())},
            "child": {"source_file": str(package / "candidate.py"), "identity": proposal["identity"]}},
        "files": {str(p): pin(p) for p in files}, "source_manifest": original["source_manifest"],
        "worlds_per_target": 4, "planned_single_hand_continuations": 108, "cpu_worker_count": 4,
        "step_limit": 50000, "wall_seconds_per_target": 1800,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "A": "formal9adb持续，首手立即胡", "B": "9adb仅首手强制继续，其后9adb", "C": "357e持续；按公开图自行选择",
        "sampler_interpretation": "四个等权公开相容隐藏分配；保留本家完整观察，三家暗手与未消费牌墙联合洗牌。未按他家历史策略似然加权，非真实后验或自然场频率。",
        "readout": "所有目标自然闭合后统一读回B−A、C−A、C−B与实际番数、支付、失胡；保留失败，不以条件分数替代完整桌。",
        "original_confirmations_exposed_development_only": True, "online_or_strength_admission": False,
        "additional_model_calls": 0, "automatic_table_or_confirmation_dispatch": False})
    print(json.dumps({"frozen_targets": len(targets), "planned_single_hand_continuations": 108, "new_worlds_or_scores": 0}))


if __name__ == "__main__":
    main()
