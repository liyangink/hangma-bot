"""在新候选评分前冻结原S02、执行合同和未生成牌墙的独立来源。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

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
from pathlib import Path
import secrets

from hangma_bot import bootstrap
from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.vip_s02_frozen_source import VIP_S02_SOURCE, VIP_S02_SOURCE_SHA256

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def pin(path):
    """只记录公开文件的精确字节数和摘要，不读取认证文件。"""
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(path, value):
    """排他新建证据；已有尝试不得覆盖。"""
    with Path(path).open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")


def main():
    """仅生成来源描述和身份，不生成世界、调用模型或执行桌赛。"""
    original = _project_file(_PROJECT_ROOT, HERE.parent / "t188-joint-score-mechanism-1/AUTHOR-BATCH.json")
    data = json.loads(original.read_text())
    data["batch_id"] = "t191-minimal-engineering-repairs-20261005"
    data["budgets"] = dict.fromkeys(data["budgets"], 0)
    data["input_bound"] = None
    save(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"), data)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"))
    raw = VIP_S02_SOURCE.encode()
    assert hashlib.sha256(raw).hexdigest() == VIP_S02_SOURCE_SHA256
    with (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).open("xb") as out:
        out.write(raw)
    identity = batch.identity(VIP_S02_SOURCE)
    ActionValueExecutor(VIP_S02_SOURCE, max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes)
    old_free = bootstrap._load_vip_free_manifest()
    assert old_free["source_manifest"] == bootstrap._vip_runtime_sources()
    paths = sorted(HERE.parent.glob("**/*ROOT*.json"))
    paths.extend(sorted(HERE.parent.glob("**/*ROOT*.json.gz")))
    paths = [p for p in paths if p.parent != HERE and ("FRESH" in p.name or p.name.startswith("ROOTS-BEFORE"))]
    occupied, history = set(), {}

    def numbers(value):
        if type(value) is int:
            occupied.add(value)
        elif isinstance(value, dict):
            for child in value.values():
                numbers(child)
        elif isinstance(value, list):
            for child in value:
                numbers(child)

    for p in paths:
        raw_old = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
        numbers(json.loads(raw_old))
        history[str(p.relative_to(ROOT))] = pin(p)
    pools = {}
    for name, count in (("development", 32), ("confirmation", 128), ("competitive_cost_probe", 2)):
        values = []
        for index in range(count):
            seed = secrets.randbits(63)
            while seed in occupied:
                seed = secrets.randbits(63)
            occupied.add(seed)
            values.append({"root_id": f"t191-{name}-{index + 1:03d}", "seed": seed})
        pools[name] = values
    save(_project_file(_PROJECT_ROOT, HERE / "FRESH-SOURCE-DESCRIPTORS.json"), {"schema": "t191-fresh-source-descriptors/1",
        "pools": pools, "collision_exclusion_files": history,
        "old_results_or_walls_read": False, "new_worlds_generated": 0,
        "pool_usage": "confirmation只在唯一胜者冻结后生成世界；强池只测成本，不混入海选效果"})
    compositions = {name: freeze_qualifier_compositions(values, 0.6)
        for name, values in pools.items() if name != "competitive_cost_probe"}
    save(_project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"), {"pools": compositions,
        "weak_fraction_setting": 0.6, "not_observed_platform_distribution": True,
        "new_worlds_generated": 0})
    files = [Path(__file__), original, _project_file(_PROJECT_ROOT, HERE / "README.md"), _project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "FRESH-SOURCE-DESCRIPTORS.json"),
        _project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json")]
    save(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-START.json"), {"schema": "t191-execution-start/1",
        "baseline_identity": identity, "parent_source_sha256": VIP_S02_SOURCE_SHA256,
        "live_free_package_id": old_free["release_package_id"],
        "live_runtime_source_manifest": bootstrap._vip_runtime_sources(),
        "files": {str(p.relative_to(ROOT)): pin(p) for p in files},
        "candidate_origin": "explicit_engineering_minimal_repair_not_new_model_output",
        "new_model_calls": 0, "new_scores": 0, "new_worlds": 0, "new_tables": 0,
        "maximum_minimal_candidates": 2, "maximum_final_winners": 1,
        "production_or_online_owner_modified": False})
    print(json.dumps({"complete": True, "fresh_sources": sum(map(len, pools.values())),
        "excluded_descriptor_files": len(paths), "new_model_calls_scores_worlds_tables": 0}))


if __name__ == "__main__":
    main()
