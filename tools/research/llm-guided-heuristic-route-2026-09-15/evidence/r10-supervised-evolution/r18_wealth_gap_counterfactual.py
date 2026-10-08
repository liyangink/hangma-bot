"""R18 多财神缺口三分层的同世界反事实方向校准。"""

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


BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-bank-01-20260922')
DEVELOPMENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-bank-01-20260922/development.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-counterfactual-01-20260922')
STRATA = (
    "three_wealth_piao",
    "three_wealth_keep",
    "four_wealth_keep",
)
SHAPES_PER_STRATUM = 6
WORLDS_PER_SHAPE = 32


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def oracle_values(row: dict[str, Any]) -> dict[str, float]:
    return {
        item["action_key"]: float(item["value"])
        for item in row["action_values"]
    }


def target_action(row: dict[str, Any]) -> str:
    """选择预声明分层的确定目标动作；并列保财按动作键排序。"""

    values = oracle_values(row)
    best = max(values.values())
    best_keys = sorted(key for key, value in values.items() if value == best)
    if row["opportunity_stratum"] == "three_wealth_piao":
        if best_keys != ["discard:白"]:
            raise ValueError("三财神应飘题的唯一最优动作不再是 discard:白")
        return "discard:白"
    keep = [
        key for key in best_keys
        if key.startswith("discard:") and key != "discard:白"
    ]
    if not keep or "hu" in best_keys:
        raise ValueError("保财题不再具备严格优于立即胡的非财神弃牌")
    return keep[0]


def oracle_delta(row: dict[str, Any]) -> float:
    values = oracle_values(row)
    return values[target_action(row)] - values["hu"]


def selected_rows() -> dict[str, list[dict[str, Any]]]:
    document = json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
    selected = {}
    for stratum in STRATA:
        rows = [
            row for row in document["cases"]
            if row["opportunity_stratum"] == stratum
        ]
        rows.sort(key=lambda row: hashlib.sha256(
            ("r18-wealth-gap-cf|" + stratum + "|" + row["request_sha256"]).encode()
        ).hexdigest())
        if len(rows) < SHAPES_PER_STRATUM:
            raise ValueError(stratum + " 开发手牌不足")
        selected[stratum] = rows[:SHAPES_PER_STRATUM]
    return selected


def sources() -> dict[str, str]:
    paths = (
        Path(__file__),
        Path(pilot.__file__),
        _project_file(_PROJECT_ROOT, BANK / "manifest.json"),
        DEVELOPMENT,
        _project_file(_PROJECT_ROOT, BANK / "development-parent-score.json"),
    )
    return {str(path): digest(path) for path in paths}


def prepare() -> None:
    """冻结三分层各 6 种开发手牌；不读取 hidden。"""

    if OUT.exists():
        raise SystemExit("多财神缺口反事实目录已存在；拒绝覆盖")
    groups = selected_rows()
    shapes = []
    for stratum in STRATA:
        for rank, row in enumerate(groups[stratum], 1):
            shapes.append({
                "opportunity_stratum": stratum,
                "shape_rank": rank,
                "case_id": row["case_id"],
                "request_sha256": row["request_sha256"],
                "reachability_witness_sha256": row["reachability_witness_sha256"],
                "target_action_key": target_action(row),
                "oracle_target_minus_hu": oracle_delta(row),
            })
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-wealth-gap-counterfactual-manifest/1",
        "source_hashes": sources(),
        "shape_selection": "每分层按sha256('r18-wealth-gap-cf|'+stratum+'|'+request_sha256)取前6",
        "shapes": shapes,
        "worlds_per_shape": WORLDS_PER_SHAPE,
        "pairs": len(shapes) * WORLDS_PER_SHAPE,
        "arms": "立即 hu vs 该形状冻结 oracle 最优动作；首动作后四家稳定 V2",
        "world_identity": "global_index=stratum_rank*1000000+shape_rank*10000+local_index；复用已审计完整世界构造",
        "direction_rule": {
            "SUPPORT": "该手牌机械全通过且配对均值bootstrap 95%下界>0",
            "CONTRADICT": "该手牌机械全通过且配对均值bootstrap 95%上界<0",
            "INCONCLUSIVE": "其余情况",
        },
        "hidden_bank_read": False,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "strata": len(STRATA),
        "shapes": len(shapes),
        "pairs": len(shapes) * WORLDS_PER_SHAPE,
    }, ensure_ascii=False))


def verify(manifest: dict[str, Any]) -> None:
    if manifest.get("source_hashes") != sources():
        raise ValueError("多财神缺口反事实冻结来源漂移")
    expected = selected_rows()
    actual = [
        (row["opportunity_stratum"], row["request_sha256"])
        for row in manifest["shapes"]
    ]
    current = [
        (stratum, row["request_sha256"])
        for stratum in STRATA for row in expected[stratum]
    ]
    if actual != current:
        raise ValueError("多财神缺口手牌选择漂移")


async def run_pair(
    row: dict[str, Any], action_key: str, pair_index: int,
) -> dict[str, Any]:
    world = pilot.build_world_row(row, pair_index)
    focal_seat = int(world["initial"]["dealer_seat"])
    hu = await pilot.run_arm(world, focal_seat, "hu")
    target = await pilot.run_arm(world, focal_seat, action_key)
    mechanical_ok = all(
        arm["status"] == "complete"
        and arm["completed_hands"] == 1
        and arm["force_count"] == 1
        and arm["first_action_key"] == expected
        and all(value == 0 for value in arm["runtime_counts"].values())
        for arm, expected in ((hu, "hu"), (target, action_key))
    )
    delta = None
    if hu["final_scores"] is not None and target["final_scores"] is not None:
        delta = target["final_scores"][focal_seat] - hu["final_scores"][focal_seat]
    return {
        "pair_index": pair_index,
        "world_sha256": pilot.digest_value(world["initial"]["world_payload"]),
        "mechanical_ok": mechanical_ok,
        "target_minus_hu_focal_score": delta,
        "hu_status": hu["status"],
        "target_status": target["status"],
    }


async def run_shape(
    row: dict[str, Any], *, stratum_rank: int, shape_rank: int,
) -> list[dict[str, Any]]:
    action_key = target_action(row)
    pairs = []
    for local_index in range(1, WORLDS_PER_SHAPE + 1):
        pair_index = stratum_rank * 1_000_000 + shape_rank * 10_000 + local_index
        pairs.append(await run_pair(row, action_key, pair_index))
    return pairs


def run() -> None:
    """执行 576 对完整世界并逐手牌报告，不用总体均值掩盖反例。"""

    target_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if target_path.exists():
        raise SystemExit("多财神缺口反事实已执行；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(manifest)
    groups = selected_rows()
    shape_results = []
    counterexamples = []
    for stratum_rank, stratum in enumerate(STRATA, 1):
        for shape_rank, row in enumerate(groups[stratum], 1):
            pairs = asyncio.run(run_shape(
                row, stratum_rank=stratum_rank, shape_rank=shape_rank
            ))
            valid = [pair for pair in pairs if pair["mechanical_ok"]]
            deltas = [
                float(pair["target_minus_hu_focal_score"])
                for pair in valid
                if pair["target_minus_hu_focal_score"] is not None
            ]
            interval = pilot.bootstrap_interval(deltas) if deltas else (None, None)
            direction = "INCONCLUSIVE"
            if len(valid) == WORLDS_PER_SHAPE and len(deltas) == WORLDS_PER_SHAPE:
                if interval[0] is not None and interval[0] > 0:
                    direction = "SUPPORT"
                elif interval[1] is not None and interval[1] < 0:
                    direction = "CONTRADICT"
            shape_results.append({
                "opportunity_stratum": stratum,
                "shape_rank": shape_rank,
                "case_id": row["case_id"],
                "request_sha256": row["request_sha256"],
                "target_action_key": target_action(row),
                "oracle_target_minus_hu": oracle_delta(row),
                "pairs": len(pairs),
                "mechanically_valid": len(valid),
                "mean_actual_target_minus_hu": statistics.fmean(deltas) if deltas else None,
                "median_actual_target_minus_hu": statistics.median(deltas) if deltas else None,
                "bootstrap_mean_95_interval": list(interval),
                "delta_histogram": dict(sorted(Counter(deltas).items())),
                "nonpositive": sum(value <= 0 for value in deltas),
                "direction": direction,
            })
            counterexamples.extend(
                {
                    "opportunity_stratum": stratum,
                    "case_id": row["case_id"],
                    "pair_index": pair["pair_index"],
                    "world_sha256": pair["world_sha256"],
                    "delta": pair["target_minus_hu_focal_score"],
                    "mechanical_ok": pair["mechanical_ok"],
                }
                for pair in pairs
                if not pair["mechanical_ok"]
                or pair["target_minus_hu_focal_score"] is None
                or pair["target_minus_hu_focal_score"] <= 0
            )
    strata = {}
    for stratum in STRATA:
        rows = [row for row in shape_results if row["opportunity_stratum"] == stratum]
        directions = Counter(row["direction"] for row in rows)
        if directions["SUPPORT"] == SHAPES_PER_STRATUM:
            status = "SUPPORTED_ALL_SHAPES"
        elif directions["CONTRADICT"]:
            status = "CONTRADICTED_ANY_SHAPE"
        else:
            status = "MIXED_OR_INCONCLUSIVE"
        strata[stratum] = {
            "status": status,
            "shape_count": len(rows),
            "directions": dict(sorted(directions.items())),
            "mean_of_shape_means": statistics.fmean(
                float(row["mean_actual_target_minus_hu"]) for row in rows
            ),
            "nonpositive_pairs": sum(row["nonpositive"] for row in rows),
        }
    result = {
        "schema": "r18-wealth-gap-counterfactual-result/1",
        "status": "PASS_MECHANICS" if all(
            row["mechanically_valid"] == WORLDS_PER_SHAPE for row in shape_results
        ) else "FAIL_MECHANICS",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "strata": strata,
        "shapes": shape_results,
        "counterexamples": counterexamples,
        "hidden_bank_read": False,
        "selection_eligible": False,
        "release_eligible": False,
        "next_rule": (
            "只有 SUPPORTED_ALL_SHAPES 的分层可进入作者任务；其余先修 oracle/状态定义"
        ),
    }
    write_json(target_path, result)
    verify(manifest)
    print(json.dumps({
        "status": result["status"],
        "strata": strata,
        "counterexamples": len(counterexamples),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
