"""公开受限评分器的支持映射算术探针；合成事实不作赛事效果证据。"""
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
import json
from dataclasses import replace
from pathlib import Path

from branch_joint_probe import ActionView, ActionValueScorer, Pass, Peng, Tile, UsefulTileFact, build_sample_view


def probe(source: str) -> dict:
    """核对直接动作与吃碰分支同标尺、16以上分辨率及一个向听步长边界。"""
    scorer = ActionValueScorer("support-resolution-probe", source)
    codes = tuple(str(n) + suit for suit in ("w", "t", "b") for n in range(1, 10)) + ("东", "南", "西", "北", "白")
    rows = []
    for support in (0, 1, 4, 15, 16, 17, 79, 87, 128):
        useful = tuple(UsefulTileFact(code, min(4, support - i * 4))
                       for i, code in enumerate(codes) if i * 4 < support)
        branches = ({"followup_key": "peng:1t#6w", "followup_discard": "6w",
                     "combined_shanten": 4, "support_remaining": support,
                     "useful_tiles": tuple({"code": u.code, "remaining_estimate": u.remaining_estimate} for u in useful)},)
        actions = (
            ActionView(action_key="pass", action=Pass(), action_type="pass", is_legal=True,
                fact_kind="hand_progress", shanten_after=4, useful_tiles=useful),
            ActionView(action_key="peng:1t", action=Peng(Tile("1t")), action_type="peng", is_legal=True,
                fact_kind="hand_progress", shanten_after=4, useful_tiles=useful,
                best_followup_discard="6w", followup_branches=branches),
        )
        view = replace(build_sample_view(), actions=actions)
        batch = scorer.score(view)
        scores = {entry.action_key: entry.score for entry in batch.entries}
        expected = 8.0 + 8.0 * support / (support + 16.0)
        assert batch.status == "SCORED" and set(scores) == {"pass", "peng:1t"}
        assert all(abs(value - expected) < 1e-10 for value in scores.values())
        assert 8.0 <= scores["pass"] < 16.0
        rows.append({"support": support, "scores": scores})
    assert all(left["scores"]["pass"] < right["scores"]["pass"] for left, right in zip(rows, rows[1:]))
    # 向听3且支持0的牌效为16，严格高于向听4且支持128的读数；路线等其它项未纳入。
    better = replace(actions[0], shanten_after=3, useful_tiles=())
    better_score = scorer.score(replace(view, actions=(better,))).entries[0].score
    assert better_score == 16.0 and better_score > rows[-1]["scores"]["pass"]
    return {"purpose": "synthetic_support_arithmetic_only", "rows": rows,
            "one_shanten_step_boundary_passed": True, "selection_eligible": False,
            "release_eligible": False,
            "limitations": "只验证牌效分量；不是规则生成牌局；不证明含路线/结算的总分仍按向听优先"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("输出已存在，不覆盖")
    result = probe(args.source.read_text())
    with args.out.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"cases": len(result["rows"]), "one_shanten_step_boundary_passed": True}))
