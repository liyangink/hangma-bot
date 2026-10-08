"""分支相容聚合的合成算术探针；不是规则生成窗口，不用于选留或强度统计。"""
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
import sys
from dataclasses import replace
from pathlib import Path

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))
from hangma_bot.kernel.actions import Pass, Peng, Tile
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value import ActionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer, build_sample_view


def probe_view(conflicting=True):
    """构造两条不同弃牌分支：最高牌效与最高条件结算可相容或不相容。

    故意直接构造评分合同事实来隔离算术；没有声明此手牌/结算组合由规则引擎
    实际生成过。每个 remaining_estimate 都不超过四张，支持数不是概率。
    """
    wide = tuple({"code": code, "remaining_estimate": 4} for code in ("1w", "2w", "3w", "4w"))
    narrow = ({"code": "5w", "remaining_estimate": 4},)
    direct_useful = tuple(UsefulTileFact(item["code"], item["remaining_estimate"]) for item in wide)
    branches = tuple({"followup_key": "peng:1t#" + discard,
                      "followup_discard": discard, "combined_shanten": 0,
                      "support_remaining": support, "useful_tiles": useful}
                     for discard, support, useful in (("6w", 16, wide), ("7w", 4, narrow)))

    def route(discard, gain, useful):
        return {"followup_discard": discard, "shanten": 0, "useful_tiles": useful,
                "conditional_settlement": {"self_delta": gain}, "conditions": {},
                "support": "conditional_witness"}

    claim_routes = (route("6w", 32, wide), route("7w", 128, narrow)) if conflicting else (
        route("6w", 128, wide), route("7w", 32, narrow))
    actions = (
        ActionView(action_key="pass", action=Pass(), action_type="pass", is_legal=True,
                   fact_kind="hand_progress", shanten_after=0, useful_tiles=direct_useful,
                   routes=(route(None, 96, wide),), value_coverage="complete"),
        ActionView(action_key="peng:1t", action=Peng(Tile("1t")), action_type="peng", is_legal=True,
                   fact_kind="hand_progress", shanten_after=0, useful_tiles=direct_useful,
                   best_followup_discard="6w", followup_branches=branches,
                   routes=claim_routes, value_coverage="complete"),
    )
    return replace(build_sample_view(), actions=actions)


def run_probe(parent_source: str, candidate_source: str) -> dict:
    """通过受限生产评分器执行两种合成输入，返回可复核分数，无外部副作用。"""
    result = {"purpose": "synthetic_mechanism_arithmetic_only", "selection_eligible": False,
              "release_eligible": False, "cases": {}}
    for name, conflicting in (("conflicting_followups", True), ("compatible_followups", False)):
        outputs = {}
        for label, source in (("parent", parent_source), ("candidate", candidate_source)):
            batch = ActionValueScorer(label, source).score(probe_view(conflicting))
            scores = {entry.action_key: entry.score for entry in batch.entries}
            outputs[label] = {"status": batch.status, "scores": scores,
                              "preferred": min(scores, key=lambda key: (-scores[key], key)) if scores else None}
        result["cases"][name] = outputs
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("输出已存在，保留历史证据")
    result = run_probe(args.parent.read_text(), args.candidate.read_text())
    with args.out.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(result, ensure_ascii=False))
