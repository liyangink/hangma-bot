"""R18 P4 跨 12 种开发手牌的同世界反事实校准。"""

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
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import r18_p4_counterfactual_pilot as pilot  # noqa: E402


BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-bank-01-20260922')
DEVELOPMENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-bank-01-20260922/development.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-multishape-counterfactual-01-20260922')
SHAPES = 12
WORLDS_PER_SHAPE = 64


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def development_piao_rows() -> list[dict[str, Any]]:
    doc = json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
    rows = [row for row in doc["cases"] if row["decision_type"] == "piao"]
    rows.sort(key=lambda row: hashlib.sha256(
        ("r18-p4-multishape|" + row["request_sha256"]).encode("utf-8")
    ).hexdigest())
    if len(rows) < SHAPES:
        raise ValueError("开发应飘手牌不足 12 个")
    return rows[:SHAPES]


def oracle_delta(row: dict[str, Any]) -> float:
    values = {item["action_key"]: float(item["value"]) for item in row["action_values"]}
    return values["discard:白"] - values["hu"]


def sources() -> dict[str, str]:
    paths = (
        Path(__file__),
        Path(pilot.__file__),
        _project_file(_PROJECT_ROOT, BANK / "manifest.json"),
        DEVELOPMENT,
        _project_file(_PROJECT_ROOT, BANK / "development-score.json"),
        pilot.OUT / "result.json",
        pilot.OUT / "event-audit-v2.json",
    )
    return {str(path): digest(path) for path in paths}


def prepare() -> None:
    """冻结 12 个开发手牌和每手牌 64 个世界；不读取新 hidden。"""

    if OUT.exists():
        raise SystemExit("P4 跨手牌反事实目录已存在；拒绝覆盖")
    rows = development_piao_rows()
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p4-multishape-counterfactual-manifest/1",
        "source_hashes": sources(),
        "shape_selection": "开发piao题按sha256('r18-p4-multishape|'+request_sha256)升序取前12",
        "shapes": [
            {
                "case_id": row["case_id"],
                "request_sha256": row["request_sha256"],
                "reachability_witness_sha256": row["reachability_witness_sha256"],
                "oracle_piao_minus_hu": oracle_delta(row),
            }
            for row in rows
        ],
        "worlds_per_shape": WORLDS_PER_SHAPE,
        "pairs": SHAPES * WORLDS_PER_SHAPE,
        "world_index": "global_pair_index=shape_rank*10000+local_index；复用冻结完整世界构造",
        "arms": "hu vs discard:白；首动作后四家稳定V2",
        "pass_rule": "全部机械有效；12个手牌的配对均值与bootstrap 95%下界均>0",
        "hidden_bank_read": False,
        "selection_eligible": False,
        "table_strength_claim": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "shapes": SHAPES,
        "pairs": SHAPES * WORLDS_PER_SHAPE,
    }, ensure_ascii=False))


def verify(manifest: dict[str, Any]) -> None:
    if manifest.get("source_hashes") != sources():
        raise ValueError("P4 跨手牌反事实冻结来源漂移")
    actual = development_piao_rows()
    if [row["request_sha256"] for row in actual] != [
        row["request_sha256"] for row in manifest["shapes"]
    ]:
        raise ValueError("P4 手牌选择漂移")


async def run_shape(row: dict[str, Any], shape_rank: int) -> list[dict[str, Any]]:
    values = []
    for local_index in range(1, WORLDS_PER_SHAPE + 1):
        global_index = shape_rank * 10_000 + local_index
        values.append(await pilot.run_pair(row, global_index))
    return values


def run() -> None:
    """执行 768 个配对世界，按手牌分别裁定，不用总体均值掩盖反例。"""

    target = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if target.exists():
        raise SystemExit("P4 跨手牌反事实已执行；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(manifest)
    rows = development_piao_rows()
    shape_results = []
    all_deltas = []
    counterexamples = []
    for shape_rank, row in enumerate(rows, 1):
        pairs = asyncio.run(run_shape(row, shape_rank))
        valid = [pair for pair in pairs if pair["mechanical_ok"]]
        deltas = [
            float(pair["piao_minus_hu_focal_score"])
            for pair in valid
            if pair["piao_minus_hu_focal_score"] is not None
        ]
        interval = pilot.bootstrap_interval(deltas) if deltas else (None, None)
        shape_results.append({
            "case_id": row["case_id"],
            "request_sha256": row["request_sha256"],
            "oracle_piao_minus_hu": oracle_delta(row),
            "pairs": len(pairs),
            "mechanically_valid": len(valid),
            "mean_actual_piao_minus_hu": statistics.fmean(deltas) if deltas else None,
            "median_actual_piao_minus_hu": statistics.median(deltas) if deltas else None,
            "bootstrap_mean_95_interval": list(interval),
            "delta_histogram": dict(sorted(Counter(deltas).items())),
            "nonpositive": sum(value <= 0 for value in deltas),
            "pass_direction": (
                len(valid) == WORLDS_PER_SHAPE
                and len(deltas) == WORLDS_PER_SHAPE
                and interval[0] is not None
                and interval[0] > 0
            ),
        })
        all_deltas.extend(deltas)
        counterexamples.extend(
            {
                "case_id": row["case_id"],
                "pair_index": pair["pair_index"],
                "world_sha256": pair["world_sha256"],
                "delta": pair["piao_minus_hu_focal_score"],
                "mechanical_ok": pair["mechanical_ok"],
                "arms": pair["arms"],
            }
            for pair in pairs
            if not pair["mechanical_ok"]
            or pair["piao_minus_hu_focal_score"] is None
            or pair["piao_minus_hu_focal_score"] <= 0
        )
    passed = all(item["pass_direction"] for item in shape_results)
    result = {
        "schema": "r18-p4-multishape-counterfactual-result/1",
        "status": "PASS_ALL_SHAPES_DIRECTION" if passed else "FAIL_SOME_SHAPES_DIRECTION",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "shapes": shape_results,
        "summary": {
            "shape_count": len(shape_results),
            "shape_pass_count": sum(item["pass_direction"] for item in shape_results),
            "pairs": SHAPES * WORLDS_PER_SHAPE,
            "mechanically_valid": sum(item["mechanically_valid"] for item in shape_results),
            "overall_mean_actual_piao_minus_hu": statistics.fmean(all_deltas),
            "overall_delta_histogram": dict(sorted(Counter(all_deltas).items())),
            "counterexample_count": len(counterexamples),
        },
        "counterexamples": counterexamples,
        "hidden_bank_read": False,
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(target, result)
    verify(manifest)
    print(json.dumps({
        "status": result["status"],
        **result["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
