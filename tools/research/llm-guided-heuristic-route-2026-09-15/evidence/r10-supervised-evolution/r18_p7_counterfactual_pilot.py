"""R18 P7 七对价值动作相对 P5 动作的同世界续打校准。"""

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
import concurrent.futures
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

import r18_p4_counterfactual_pilot as world  # noqa: E402


BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-seven-pairs-bank-01-20260922')
DEVELOPMENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-seven-pairs-bank-01-20260922/development.json')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p7-seven-pairs-value-01-20260922/development-preflight-01/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p7-counterfactual-pilot-01-20260922')
SHAPES = 16
WORLDS_PER_SHAPE = 32
WORKERS = 8


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def selected_rows() -> list[dict[str, Any]]:
    """从开发集确定性抽取 16 个七对取舍手牌。"""

    document = json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
    rows = [
        row for row in document["cases"]
        if row["decision_type"] == "seven_pairs_tradeoff"
    ]
    rows.sort(key=lambda row: hashlib.sha256(
        ("r18-p7-counterfactual|" + row["request_sha256"]).encode("utf-8")
    ).hexdigest())
    if len(rows) < SHAPES:
        raise ValueError("开发集七对取舍手牌不足")
    return rows[:SHAPES]


def action_map() -> dict[str, dict[str, str]]:
    """读取已经通过正式策略/直接评分一致性检查的父子动作。"""

    result = json.loads(ADMISSION.read_text(encoding="utf-8"))
    if result.get("status") != "PASS_P7_DEVELOPMENT":
        raise ValueError("P7 开发准入结果不可用")
    return {
        row["case_id"]: {
            "candidate": row["candidate_action"],
            "parent": row["parent_action"],
        }
        for row in result["rows"]
        if row["decision_type"] == "seven_pairs_tradeoff"
    }


def source_hashes() -> dict[str, str]:
    """冻结反事实解释所依赖的输入。"""

    paths = (
        Path(__file__),
        Path(world.__file__),
        _project_file(_PROJECT_ROOT, BANK / "manifest.json"),
        DEVELOPMENT,
        ADMISSION,
    )
    return {str(path): digest(path) for path in paths}


def prepare() -> None:
    """在读取任何续打终局标签前冻结手牌、世界数和判据。"""

    if OUT.exists():
        raise SystemExit("P7 反事实首尺目录已存在；拒绝覆盖")
    rows = selected_rows()
    actions = action_map()
    shapes = []
    for row in rows:
        case_actions = actions.get(row["case_id"])
        if case_actions is None or case_actions["candidate"] == case_actions["parent"]:
            raise ValueError(row["case_id"] + " 缺少父子动作分歧")
        shapes.append({
            "case_id": row["case_id"],
            "request_sha256": row["request_sha256"],
            "reachability_witness_sha256": row["reachability_witness_sha256"],
            "candidate_action": case_actions["candidate"],
            "parent_action": case_actions["parent"],
        })
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p7-counterfactual-pilot-manifest/1",
        "source_hashes": source_hashes(),
        "shape_selection": "开发 seven_pairs_tradeoff 按 sha256('r18-p7-counterfactual|'+request_sha256) 升序取前16",
        "shapes": shapes,
        "worlds_per_shape": WORLDS_PER_SHAPE,
        "pairs": SHAPES * WORLDS_PER_SHAPE,
        "world_construction": "复用已审计的完整136张物理世界构造；同一对仅强制首动作不同",
        "continuation": "首动作后四家均恢复稳定 ComparableHeuristicPolicyV2，完整打完当前单局",
        "arms": "P7 首选弃牌 vs P5 首选弃牌",
        "direction_rule": {
            "SUPPORT": "总体配对均值的冻结 bootstrap 95% 下界>0，且至少12/16手牌的配对均值>0",
            "CONTRADICT": "总体配对均值的冻结 bootstrap 95% 上界<0，且至多4/16手牌的配对均值>0",
            "INCONCLUSIVE": "其余情况",
        },
        "development_only": True,
        "selection_eligible": False,
        "table_strength_claim": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "shapes": SHAPES,
        "pairs": SHAPES * WORLDS_PER_SHAPE,
    }, ensure_ascii=False))


def verify(manifest: dict[str, Any]) -> None:
    """拒绝冻结后的输入或手牌漂移。"""

    if manifest.get("source_hashes") != source_hashes():
        raise ValueError("P7 反事实冻结来源漂移")
    rows = selected_rows()
    if [row["request_sha256"] for row in rows] != [
        row["request_sha256"] for row in manifest["shapes"]
    ]:
        raise ValueError("P7 反事实手牌选择漂移")


async def run_pair(
    row: dict[str, Any], shape_rank: int, local_index: int,
    candidate_action: str, parent_action: str,
) -> dict[str, Any]:
    """从同一完整世界分别强制 P7/P5 首动作一次。"""

    global_index = shape_rank * 10_000 + local_index
    replay = world.build_world_row(row, global_index)
    focal_seat = int(replay["initial"]["dealer_seat"])
    candidate = await world.run_arm(replay, focal_seat, candidate_action)
    parent = await world.run_arm(replay, focal_seat, parent_action)
    mechanical_ok = all(
        arm["status"] == "complete"
        and arm["completed_hands"] == 1
        and arm["force_count"] == 1
        and arm["first_action_key"] == expected
        and all(value == 0 for value in arm["runtime_counts"].values())
        for arm, expected in (
            (candidate, candidate_action), (parent, parent_action)
        )
    )
    delta = None
    if candidate["final_scores"] is not None and parent["final_scores"] is not None:
        delta = (
            candidate["final_scores"][focal_seat]
            - parent["final_scores"][focal_seat]
        )
    return {
        "case_id": row["case_id"],
        "shape_rank": shape_rank,
        "local_index": local_index,
        "global_pair_index": global_index,
        "focal_seat": focal_seat,
        "world_sha256": world.digest_value(replay["initial"]["world_payload"]),
        "candidate_action": candidate_action,
        "parent_action": parent_action,
        "candidate_minus_parent_focal_score": delta,
        "mechanical_ok": mechanical_ok,
        "arms": {"candidate": candidate, "parent": parent},
    }


def run_one(args: tuple[dict[str, Any], int, int, str, str]) -> dict[str, Any]:
    """子进程入口。"""

    return asyncio.run(run_pair(*args))


def run() -> None:
    """执行 512 对世界并按手牌与总体分别汇总。"""

    target = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if target.exists():
        raise SystemExit("P7 反事实首尺已执行；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(manifest)
    rows = selected_rows()
    actions = action_map()
    tasks = [
        (
            row, shape_rank, local_index,
            actions[row["case_id"]]["candidate"],
            actions[row["case_id"]]["parent"],
        )
        for shape_rank, row in enumerate(rows, 1)
        for local_index in range(1, WORLDS_PER_SHAPE + 1)
    ]
    pairs = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for index, result in enumerate(pool.map(run_one, tasks), 1):
            pairs.append(result)
            if index % 64 == 0:
                print(json.dumps({"completed_pairs": index, "planned_pairs": len(tasks)}), flush=True)
    by_case = []
    all_deltas = []
    for row in rows:
        selected = [item for item in pairs if item["case_id"] == row["case_id"]]
        valid = [item for item in selected if item["mechanical_ok"]]
        deltas = [
            float(item["candidate_minus_parent_focal_score"])
            for item in valid
            if item["candidate_minus_parent_focal_score"] is not None
        ]
        interval = world.bootstrap_interval(deltas) if deltas else (None, None)
        by_case.append({
            "case_id": row["case_id"],
            "request_sha256": row["request_sha256"],
            "candidate_action": actions[row["case_id"]]["candidate"],
            "parent_action": actions[row["case_id"]]["parent"],
            "pairs": len(selected),
            "mechanically_valid": len(valid),
            "mean_candidate_minus_parent": statistics.fmean(deltas) if deltas else None,
            "median_candidate_minus_parent": statistics.median(deltas) if deltas else None,
            "bootstrap_mean_95_interval": list(interval),
            "delta_histogram": dict(sorted(Counter(deltas).items())),
        })
        all_deltas.extend(deltas)
    mechanical = len(all_deltas) == SHAPES * WORLDS_PER_SHAPE
    overall_interval = world.bootstrap_interval(all_deltas) if all_deltas else (None, None)
    positive_shapes = sum(
        float(item["mean_candidate_minus_parent"] or 0.0) > 0.0
        for item in by_case
    )
    direction = "MECHANICAL_FAIL"
    if mechanical:
        if overall_interval[0] is not None and overall_interval[0] > 0 and positive_shapes >= 12:
            direction = "SUPPORT"
        elif overall_interval[1] is not None and overall_interval[1] < 0 and positive_shapes <= 4:
            direction = "CONTRADICT"
        else:
            direction = "INCONCLUSIVE"
    result = {
        "schema": "r18-p7-counterfactual-pilot-result/1",
        "status": "PASS_MECHANICS" if mechanical else "FAIL_MECHANICS",
        "direction": direction,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "shapes": by_case,
        "summary": {
            "shape_count": len(by_case),
            "positive_shape_means": positive_shapes,
            "pairs": len(pairs),
            "mechanically_valid": len(all_deltas),
            "overall_mean_candidate_minus_parent": statistics.fmean(all_deltas) if all_deltas else None,
            "overall_median_candidate_minus_parent": statistics.median(all_deltas) if all_deltas else None,
            "overall_bootstrap_mean_95_interval": list(overall_interval),
            "candidate_better_worlds": sum(value > 0 for value in all_deltas),
            "tie_worlds": sum(value == 0 for value in all_deltas),
            "candidate_worse_worlds": sum(value < 0 for value in all_deltas),
        },
        "pairs": pairs,
        "development_only": True,
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(target, result)
    verify(manifest)
    print(json.dumps({
        "status": result["status"], "direction": direction, **result["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
