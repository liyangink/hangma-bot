"""R18 P4 公开开发尾部压力：扩大完整世界以搜索飘白等待期间的反例。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import r18_p4_counterfactual_pilot as pilot  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-tail-stress-01-20260922')
START_INDEX = 65
PAIRS = 2048
END_INDEX = START_INDEX + PAIRS - 1


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources() -> dict[str, str]:
    paths = (
        Path(__file__),
        Path(pilot.__file__),
        pilot.BANK,
        pilot.OUT / "manifest.json",
        pilot.OUT / "result.json",
        pilot.OUT / "event-audit-v2.json",
    )
    return {str(path): digest(path) for path in paths}


def prepare() -> None:
    """冻结额外 2048 个世界和零反例判据，不读取隐藏题。"""

    if OUT.exists():
        raise SystemExit("P4 尾部压力目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p4-tail-stress-manifest/1",
        "purpose": "搜索飘白后、本人下次摸牌前被对手先结束牌局的稀有反例",
        "source_hashes": sources(),
        "pair_index_start": START_INDEX,
        "pair_index_end": END_INDEX,
        "pairs": PAIRS,
        "world_rule": "完全复用已冻结P4试点世界构造；索引65起避免与首轮64对重叠",
        "arms": "每个世界仍完整执行hu与discard:白两臂；之后四家稳定V2",
        "pass_rule": "2048/2048机械有效，且不存在 piao_minus_hu_focal_score<=0",
        "tail_bound": "若零非正结果，报告二项零事件单侧95%上界 1-0.05^(1/n)",
        "hidden_bank_read": False,
        "training": False,
        "selection_eligible": False,
        "hidden_eligible": False,
        "table_strength_claim": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "pairs": PAIRS}, ensure_ascii=False))


def verify(manifest: dict[str, Any]) -> None:
    if manifest.get("source_hashes") != sources():
        raise ValueError("P4 尾部压力冻结来源漂移")


def run() -> None:
    """执行额外开发世界，只持久化分布和反例，不落完整暗牌/牌墙。"""

    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("P4 尾部压力已经执行；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(manifest)
    case = pilot.read_case()
    rows = [
        asyncio.run(pilot.run_pair(case, index))
        for index in range(START_INDEX, END_INDEX + 1)
    ]
    valid = [row for row in rows if row["mechanical_ok"]]
    deltas = [
        int(row["piao_minus_hu_focal_score"])
        for row in valid
        if row["piao_minus_hu_focal_score"] is not None
    ]
    counterexamples = [
        {
            "pair_index": row["pair_index"],
            "pair_seed": row["pair_seed"],
            "focal_seat": row["focal_seat"],
            "world_sha256": row["world_sha256"],
            "delta": row["piao_minus_hu_focal_score"],
            "arms": row["arms"],
        }
        for row in rows
        if not row["mechanical_ok"]
        or row["piao_minus_hu_focal_score"] is None
        or row["piao_minus_hu_focal_score"] <= 0
    ]
    mechanics = len(valid) == PAIRS and len(deltas) == PAIRS
    zero_nonpositive = not counterexamples
    upper = 1.0 - math.pow(0.05, 1.0 / PAIRS) if zero_nonpositive else None
    result = {
        "schema": "r18-p4-tail-stress-result/1",
        "status": (
            "PASS_ZERO_NONPOSITIVE"
            if mechanics and zero_nonpositive
            else "REVIEW_COUNTEREXAMPLES"
        ),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "pairs_planned": PAIRS,
        "pairs_mechanically_valid": len(valid),
        "delta_histogram": dict(sorted(Counter(deltas).items())),
        "nonpositive_count": sum(value <= 0 for value in deltas),
        "piao_worse_count": sum(value < 0 for value in deltas),
        "zero_nonpositive_one_sided_95_upper_probability": upper,
        "counterexamples": counterexamples,
        "hidden_bank_read": False,
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(result_path, result)
    verify(manifest)
    print(json.dumps({
        "status": result["status"],
        "pairs_mechanically_valid": len(valid),
        "delta_histogram": result["delta_histogram"],
        "nonpositive_count": result["nonpositive_count"],
        "one_sided_95_upper_probability": upper,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
