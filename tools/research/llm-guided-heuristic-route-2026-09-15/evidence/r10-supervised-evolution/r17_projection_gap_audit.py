"""R17 前置零桌审计：量化终局路线缺口与公开牌效路径的可用范围。

本脚本只读取 R16 已消费的真实公开窗口并调用既有 ScoringView 投影；
不生成候选、不运行桌赛，也不把未见牌数解释为摸牌概率。
"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (HERE, _project_file(_PROJECT_ROOT, ROUTE / "tools")):
    sys.path.insert(0, str(path))

import r16_goal_first_preflight_02 as r16  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-projection-gap-audit-01-20260921')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _branch_tiles(action: Any) -> tuple[tuple[Any, ...], ...]:
    """返回规则已投影的一步推进牌集合；吃碰逐后继弃牌保留分支。"""

    if action.followup_branches:
        return tuple(tuple(branch.useful_tiles) for branch in action.followup_branches)
    return (tuple(action.useful_tiles),)


def main() -> None:
    """生成不可覆盖的零桌审计结果；既有目录存在时拒绝覆盖。"""

    if OUT.exists():
        raise SystemExit("R17 投影缺口审计已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = r16.load_windows()
    counts: Counter[str] = Counter()
    action_type: Counter[str] = Counter()
    progress_edges: list[int] = []
    distinct_progress_tiles: list[int] = []
    differentiated_windows = 0
    multi_action_windows = 0
    for _name, request, _origins in windows:
        view = r16.behavior.build_scoring_view(request)
        signatures = []
        for action in view.actions:
            counts["actions"] += 1
            action_type[action.action_type] += 1
            counts["fact_projected_actions"] += int(action.fact_kind is not None)
            counts["shanten_projected_actions"] += int(action.shanten_after is not None)
            counts["terminal_route_actions"] += int(bool(action.routes))
            branch_tiles = _branch_tiles(action)
            edge_count = sum(len(tiles) for tiles in branch_tiles)
            tile_codes = {tile.code for tiles in branch_tiles for tile in tiles}
            progress_edges.append(edge_count)
            distinct_progress_tiles.append(len(tile_codes))
            counts["progress_path_actions"] += int(edge_count > 0)
            counts["progress_edges"] += edge_count
            support = sum(tile.remaining_estimate for tile in action.useful_tiles)
            signatures.append(
                (
                    action.shanten_after,
                    support,
                    action.standard_shanten_after,
                    action.seven_pairs_shanten_after,
                )
            )
        if len(signatures) >= 2:
            multi_action_windows += 1
        if len(set(signatures)) >= 2:
            differentiated_windows += 1

    non_hu_actions = counts["actions"] - action_type["hu"]
    result = {
        "schema": "r17-projection-gap-audit/1",
        "status": "PASS_PUBLIC_PROGRESS_PROJECTION_SCOPE_FOR_R17_DESIGN",
        "deduplicated_windows": len(windows),
        "tables_run": 0,
        "model_calls": 0,
        "counts": dict(sorted(counts.items())),
        "action_type_counts": dict(sorted(action_type.items())),
        "coverage": {
            "terminal_route_action_fraction": counts["terminal_route_actions"]
            / counts["actions"],
            "public_progress_action_fraction": counts["progress_path_actions"]
            / counts["actions"],
            "public_progress_non_hu_fraction": counts["progress_path_actions"]
            / non_hu_actions,
            "fact_projection_fraction": counts["fact_projected_actions"]
            / counts["actions"],
            "differentiated_multi_action_window_fraction": differentiated_windows
            / multi_action_windows,
        },
        "windows": {
            "multi_action": multi_action_windows,
            "differentiated_public_progress_signature": differentiated_windows,
        },
        "progress_edge_distribution": {
            "per_action_min": min(progress_edges),
            "per_action_median": statistics.median(progress_edges),
            "per_action_max": max(progress_edges),
            "distinct_tile_per_action_min": min(distinct_progress_tiles),
            "distinct_tile_per_action_median": statistics.median(
                distinct_progress_tiles
            ),
            "distinct_tile_per_action_max": max(distinct_progress_tiles),
        },
        "interpretation": {
            "proved": (
                "现有规则投影已经为全部非胡动作提供至少一条公开一步推进边；"
                "其覆盖范围足以进入有界公开自摸路径投影的接口与性能试验"
            ),
            "not_proved": (
                "一步推进边不是摸牌概率、完整未来状态或增强证据；"
                "必须由HangmaRules扩展后继叶事实并经完整阶段评价"
            ),
        },
        "inputs": {
            "loader": str(_project_file(_PROJECT_ROOT, HERE / "r16_goal_first_preflight_02.py")),
            "loader_sha256": digest(_project_file(_PROJECT_ROOT, HERE / "r16_goal_first_preflight_02.py")),
            "panels": [
                {"path": str(path), "sha256": digest(path)} for path in r16.PANELS
            ],
        },
        "strength_claim": False,
        "confirmation_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
