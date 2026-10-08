"""只冻结父代源码、运行身份与新母来源；不调用模型、规则评分或生成牌山。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.scoring_sources import source_manifest
from hangma_bot.policy.vip_s02_frozen_source import VIP_S02_SOURCE, VIP_S02_SOURCE_SHA256

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
ROOTS = (
    "hangma_bot.offline.vip_eoh_generate",
    "hangma_bot.offline.evaluate",
    "hangma_bot.offline.vip_route_development",
    "hangma_bot.offline.qualifier_opponents",
    "hangma_bot.offline.scoring_input_capture",
    "hangma_bot.policy.vip_s02_frozen_source",
)


def save(name: str, value: object) -> None:
    """只新建本批证据，不覆盖旧失败、旧来源或运行配置。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def roots_for(kind: str, count: int) -> list[dict]:
    """在独立命名空间登记63位洗牌种子；这里不会构造WorldState或牌山。"""
    values = []
    for index in range(1, count + 1):
        root_id = f"t182-step12-20261004:{kind}:{index:03d}"
        seed = int.from_bytes(hashlib.sha256(root_id.encode()).digest()[:8], "big") & ((1 << 63) - 1)
        values.append({"root_id": root_id, "seed": seed})
    return values


def main() -> None:
    """装配与验签均只读；实际父代移植、候选及桌赛仍需后续独立收据。"""
    assert hashlib.sha256(VIP_S02_SOURCE.encode()).hexdigest() == VIP_S02_SOURCE_SHA256
    for name in ("PARENT-FROZEN.json", "SOURCE-MANIFEST.json", "FRESH-ROOTS-BEFORE-AUTHOR.json", "COMPOSITIONS.json", "START-CLOSED.json"):
        assert not (_project_file(_PROJECT_ROOT, HERE / name)).exists(), "已有证据，拒绝覆盖：" + name
    driver_path = _project_file(_PROJECT_ROOT, HERE.parent / "t179-production-wiring-1/free_watchdog.py")
    spec = importlib.util.spec_from_file_location("t182_t179_readonly", driver_path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    production_identity = driver.preflight()
    manifest = source_manifest(ROOTS)
    descriptor = {kind: roots_for(kind, count) for kind, count in
                  (("diagnostic", 8), ("development", 32), ("confirmation", 128))}
    seeds = [r["seed"] for group in descriptor.values() for r in group]
    assert len(set(seeds)) == len(seeds)
    # 只读各历史批的种子登记，不读取其结果、牌山或确认标签。
    prior_seeds = set()
    prior_files = []
    for path in sorted(HERE.parent.glob("*/FRESH-ROOTS-BEFORE-AUTHOR.json")):
        if path.parent == HERE:
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("历史种子登记超过有界元数据读取上限：" + str(path))
        data = json.loads(path.read_text())
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if type(item.get("seed")) is int:
                    prior_seeds.add(item["seed"])
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        prior_files.append(str(path.relative_to(ROOT)))
    assert set(seeds).isdisjoint(prior_seeds), "新种子与已登记旧种子重复"
    at_utc = datetime.now(timezone.utc).isoformat()
    with (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).open("x") as stream:
        stream.write(VIP_S02_SOURCE)
    save("PARENT-FROZEN.json", {
        "at_utc": at_utc, "formula_sha256": VIP_S02_SOURCE_SHA256,
        "parent_source": str((_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).relative_to(ROOT)),
        "production_identity": production_identity,
        "source_manifest_file": "SOURCE-MANIFEST.json",
        "old_generation_identity_reused": False, "current_research_rebind_pending": True,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "models_rules_scores_worlds_tables_in_preparation": 0,
    })
    save("SOURCE-MANIFEST.json", manifest)
    save("FRESH-ROOTS-BEFORE-AUTHOR.json", {
        "at_utc": at_utc, **descriptor, "worlds_generated": 0,
        "confirmation_labels_read": 0, "author_may_read_confirmation": False,
        "seed_collision_check_prior_files": prior_files,
        "prior_seed_count_checked": len(prior_seeds),
        "same_root_rotations_not_independent": True,
    })
    compositions = {kind: freeze_qualifier_compositions(group, 0.6) for kind, group in descriptor.items()}
    save("COMPOSITIONS.json", {
        "at_utc": at_utc, "pools": compositions, "weak_fraction_setting": 0.6,
        "source": "user qualifier scenario; not measured current free-match population",
        "official_score_multiplier": 1, "composition_resampling_after_results": False,
    })
    paths = [_project_file(_PROJECT_ROOT, HERE / name) for name in ("README.md", "prepare_start.py", "parent-source.py", "PARENT-FROZEN.json", "SOURCE-MANIFEST.json", "FRESH-ROOTS-BEFORE-AUTHOR.json", "COMPOSITIONS.json")]
    save("START-CLOSED.json", {
        "at_utc": at_utc, "complete": True, "goal_status": "active",
        "files": {str(p.relative_to(ROOT)): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in paths},
        "source_files_frozen": len(manifest), "registered_diagnostic_roots": 8,
        "registered_development_roots": 32, "registered_confirmation_roots": 128,
        "actual_author_calls": 0, "actual_score_calls": 0, "worlds_generated": 0,
        "published": False, "admitted": False,
    })
    print(json.dumps({"complete": True, "source_files_frozen": len(manifest),
                      "registered_roots": len(seeds), "prior_seed_count_checked": len(prior_seeds),
                      "actual_calls_scores_worlds": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
