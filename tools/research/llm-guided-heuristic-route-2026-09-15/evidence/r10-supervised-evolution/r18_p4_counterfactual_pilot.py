"""R18 P4 四财神飘链：同完整世界、只改首动作的配对反事实校准。

开发题 ``r18-mw-w4-03`` 的单步条件代理认为：当前胡为 +192，飘白后
下一次本人摸牌立即胡的条件期望为 +384。本试点不把该代理当标签，而是
构造 64 个确定性完整世界；每个世界分别强制当前胡与飘白一次，随后四家
都恢复稳定 V2，比较本单局焦点座位终局积分。

本文件只读 development 题库，禁止读取 hidden 题库。它是方向校准与样本
量估计，不是候选选留、隐藏验收、完整桌赛强度或发布证据。
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

import argparse
import asyncio
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.application.deadline import BudgetPolicy  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    MatchDriverConfig,
    frame_observation_summary,
    resume_match,
)
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.simulation import (  # noqa: E402
    DEAL_ALGORITHM,
    GUIDE_CAPTURED_AT,
    GUIDE_VERSION,
    RESERVE_TILES,
    SimulationChoice,
    SimulationEngine,
    hand_id,
    split_group_id,
)
from hangma_bot.simulation.engine import WORLD_SCHEMA  # noqa: E402


BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922/development.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-counterfactual-pilot-01-20260922')
CASE_ID = "r18-mw-w4-03"
ROOT_SEED = 202609220401
PAIRS = 64
BOOTSTRAP_REPLICATES = 20_000
TARGET_MARGIN = 16.0
RULE_CONFIG = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
RULES = HangmaRules(RULE_CONFIG)


def canonical_bytes(value: Any) -> bytes:
    """生成稳定 JSON 字节，用于冻结输入和世界身份。"""

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_value(value: Any) -> str:
    """返回 JSON 值的 SHA-256。"""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_file(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入 UTF-8、可读且键序稳定的 JSON 证据。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def source_paths() -> tuple[Path, ...]:
    """列出结果解释依赖的源码与开发输入；hidden 明确不在其中。"""

    import hangma_bot.hangma.engine as rules_engine
    import hangma_bot.offline.evaluate as evaluate
    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.policy.heuristic_v2 as heuristic_v2
    import hangma_bot.simulation.engine as simulation_engine

    return (
        Path(__file__),
        BANK,
        Path(rules_engine.__file__),
        Path(evaluate.__file__),
        Path(forced_action.__file__),
        Path(heuristic_v2.__file__),
        Path(simulation_engine.__file__),
    )


def source_hashes() -> dict[str, str]:
    """冻结全部输入摘要。"""

    return {str(path): digest_file(path) for path in source_paths()}


def read_case() -> dict[str, Any]:
    """只从 development 题库读取指定 P4 场景。"""

    document = json.loads(BANK.read_text(encoding="utf-8"))
    case = next(
        (item for item in document["cases"] if item["case_id"] == CASE_ID), None
    )
    if case is None:
        raise ValueError("development 题库缺少 " + CASE_ID)
    if case.get("split") != "development":
        raise ValueError(CASE_ID + " 不是 development 场景")
    if case.get("wealth_count") != 4 or case.get("decision_type") != "piao":
        raise ValueError(CASE_ID + " 不再是四财神飘场景")
    return case


def build_world_row(case: dict[str, Any], pair_index: int) -> dict[str, Any]:
    """按配对编号构造完整物理世界；两臂复用同一行。

    焦点座位轮换，但始终是庄家。三家暗牌和 83 张剩余墙从移除焦点
    起手/直抽后的物理牌组确定性洗牌得到，保证 136 张守恒。
    """

    witness = case["reachability_witness"]
    focal_hand = list(witness["hand13"])
    dealer_drawn = str(witness["draw"])
    focal_seat = (pair_index - 1) % 4
    pair_seed = ROOT_SEED + pair_index
    deck = [code for code in CANONICAL_TILE_ORDER for _ in range(4)]
    for code in focal_hand + [dealer_drawn]:
        deck.remove(code)
    rng = random.Random(pair_seed)
    rng.shuffle(deck)
    hands: list[list[str]] = [[] for _ in range(4)]
    hands[focal_seat] = focal_hand
    cursor = 0
    for seat in range(4):
        if seat == focal_seat:
            continue
        hands[seat] = deck[cursor : cursor + 13]
        cursor += 13
    wall = deck[cursor:]
    if len(wall) != 83:
        raise AssertionError("完整世界剩余墙必须为 83 张")
    physical = Counter(code for hand in hands for code in hand)
    physical[dealer_drawn] += 1
    physical.update(wall)
    if any(physical[code] != 4 for code in CANONICAL_TILE_ORDER):
        raise AssertionError("完整世界牌张不守恒")

    match_id = "r18-p4-cf-{0:03d}".format(pair_index)
    scenario_id = "r18-p4-cf-world-{0:03d}".format(pair_index)
    wall_back = len(wall) - RESERVE_TILES
    payload = {
        "world_schema": WORLD_SCHEMA,
        "deal_algorithm": DEAL_ALGORITHM,
        "seed": pair_seed,
        "scenario_id": scenario_id,
        "match_id": match_id,
        "round_no": 1,
        "rounds_per_game": 1,
        "parent_hand_id": None,
        "dealer_seat": focal_seat,
        "initial_scores": [0, 0, 0, 0],
        "rule_config": {
            "ruleset_version": RULE_CONFIG.ruleset_version,
            "base_score": RULE_CONFIG.base_score,
            "you_cai_bi_kao": RULE_CONFIG.you_cai_bi_kao,
        },
        "timing": {
            "peng_timeout_sec": 1.0,
            "chi_timeout_sec": 1.0,
            "discard_timeout_sec": 3.0,
        },
        "rules_hash": case["rules_hash"],
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "hands": hands,
        "dealer_drawn_tile": dealer_drawn,
        "wall": wall,
        "wall_front": 0,
        "wall_back": wall_back,
        "seq": 0,
    }
    initial_hands = [
        hand + ([dealer_drawn] if seat == focal_seat else [])
        for seat, hand in enumerate(hands)
    ]
    return {
        "replay_schema_version": 1,
        "hand_id": hand_id("hangma-simulation", scenario_id, match_id, 1),
        "split_group_id": split_group_id(["hangma-simulation", scenario_id]),
        "origin": "simulated",
        "parent_hand_id": None,
        "coverage": "full_world",
        "game_key": {
            "source_namespace": "hangma-simulation",
            "tournament_id": scenario_id,
            "game_id": match_id,
        },
        "round_no": 1,
        "rule_config": payload["rule_config"],
        "rules_hash": case["rules_hash"],
        "guide_version": GUIDE_VERSION,
        "guide_captured_at": GUIDE_CAPTURED_AT,
        "initial": {
            "dealer_seat": focal_seat,
            "hands": initial_hands,
            "drawn_tile": dealer_drawn,
            "drawn_seat": focal_seat,
            "draw_identity_known": True,
            "wall": wall,
            "world_schema": WORLD_SCHEMA,
            "world_payload": payload,
            "source_refs": [],
        },
        "events": [],
        "scores_before": [0, 0, 0, 0],
        "scores_after": None,
        "score_delta": None,
        "winner_seat": None,
        "is_draw": None,
        "attempt_status": "unknown",
        "result_confirmed": False,
        "missing_fields": [],
        "source_refs": [],
    }


def driver_config() -> MatchDriverConfig:
    """返回逻辑时钟完整单局驱动配置；本试点不产生性能结论。"""

    return MatchDriverConfig(
        clock_mode="logical",
        step_limit=100_000,
        budget_policy=BudgetPolicy(),
        competition_tournament_id="r18-p4-counterfactual-pilot",
    )


async def run_arm(
    row: dict[str, Any], focal_seat: int, forced_action_key: str
) -> dict[str, Any]:
    """从完整世界独立重建一条臂，强制首动作一次后续打到单局终点。"""

    engine = SimulationEngine(RULES, rules_hash=str(row["rules_hash"]))
    world = engine.from_replay(row)
    frame = engine.frame(world)
    if len(frame.decisions) != 1 or frame.decisions[0].window_key.seat != focal_seat:
        raise ValueError("完整世界首帧不是焦点庄家单一摸牌窗口")
    target_window = frame.decisions[0].window_key
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    forced = ForceFirstActionPolicy(
        policies[focal_seat],
        target_window=target_window,
        forced_action_key=forced_action_key,
        policy_id="r18-p4-cf-" + forced_action_key,
    )
    policies[focal_seat] = forced
    outcome = await resume_match(
        engine=engine,
        world=world,
        policies_by_seat=tuple(policies),
        rules=RULES,
        choice_factory=SimulationChoice,
        config=driver_config(),
        now_monotonic=lambda: 800.0,
        wall_clock=None,
        remaining_schedule={"declared_endpoint": "hand_complete"},
        stage_snapshot={
            "observation_summary": frame_observation_summary(frame),
            "match_spec": {"match_id": row["initial"]["world_payload"]["match_id"]},
        },
        value_limits=None,
    )
    # resume_match 从已经核对过的首帧开始；决策审计保持执行顺序，因此第 0
    # 条就是目标窗口。这里不自行重建 WindowKey 序列化格式，避免证据读取层
    # 与 kernel.serialization 形成第二套合同。
    first = outcome.decisions[0] if outcome.decisions else None
    return {
        "status": outcome.status,
        "completed_hands": outcome.completed_hands,
        "final_scores": None if outcome.final_scores is None else list(outcome.final_scores),
        "blocked_reason": outcome.blocked_reason,
        "error_reason": outcome.error_reason,
        "steps": outcome.steps,
        "decisions": len(outcome.decisions),
        "first_action_key": None if first is None else first.action_key,
        "force_count": forced.force_count,
        "runtime_counts": {
            "timeouts": outcome.runtime_counts.timeouts,
            "illegal_choices": outcome.runtime_counts.illegal_choices,
            "fallbacks": outcome.runtime_counts.fallbacks,
            "auto_actions": outcome.runtime_counts.auto_actions,
            "audit_missing": outcome.runtime_counts.audit_missing,
        },
    }


async def run_pair(case: dict[str, Any], pair_index: int) -> dict[str, Any]:
    """执行同一完整世界的当前胡/飘白两臂。"""

    row = build_world_row(case, pair_index)
    focal_seat = int(row["initial"]["dealer_seat"])
    hu = await run_arm(row, focal_seat, "hu")
    piao = await run_arm(row, focal_seat, "discard:白")
    mechanical_ok = all(
        arm["status"] == "complete"
        and arm["completed_hands"] == 1
        and arm["force_count"] == 1
        and arm["first_action_key"] == expected
        and all(value == 0 for value in arm["runtime_counts"].values())
        for arm, expected in ((hu, "hu"), (piao, "discard:白"))
    )
    delta = None
    if hu["final_scores"] is not None and piao["final_scores"] is not None:
        delta = piao["final_scores"][focal_seat] - hu["final_scores"][focal_seat]
    return {
        "pair_index": pair_index,
        "pair_seed": ROOT_SEED + pair_index,
        "focal_seat": focal_seat,
        "world_sha256": digest_value(row["initial"]["world_payload"]),
        "arms": {"hu": hu, "piao": piao},
        "piao_minus_hu_focal_score": delta,
        "mechanical_ok": mechanical_ok,
    }


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """用冻结随机种子计算配对均值的百分位 bootstrap 95% 区间。"""

    rng = random.Random(ROOT_SEED + 999_999)
    n = len(values)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[math.floor(0.025 * (len(means) - 1))]
    hi = means[math.ceil(0.975 * (len(means) - 1))]
    return lo, hi


def prepare() -> None:
    """在看任何终局标签前冻结样本、判据和源码摘要。"""

    if OUT.exists():
        raise SystemExit("P4 反事实目录已存在；拒绝覆盖")
    case = read_case()
    current = source_hashes()
    OUT.mkdir(parents=True)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p4-counterfactual-pilot-manifest/1",
            "purpose": "校准四财神飘链单步代理方向，并估计后续样本量",
            "case_id": CASE_ID,
            "case_request_sha256": case["request_sha256"],
            "case_reachability_witness_sha256": case[
                "reachability_witness_sha256"
            ],
            "source_hashes": current,
            "hidden_bank_read": False,
            "root_seed": ROOT_SEED,
            "pairs": PAIRS,
            "seat_schedule": "focal_seat=(pair_index-1)%4；焦点始终为庄家",
            "world_construction": "同一可达13张焦点手牌与庄家直抽；从完整136张牌移除后确定性洗牌，依次发三家13张，余83张为墙",
            "arms": {
                "hu": "首动作强制合法 hu 一次，随后稳定 V2",
                "piao": "首动作强制合法 discard:白 一次，随后稳定 V2",
            },
            "continuation": "四家 ComparableHeuristicPolicyV2；同一对内完整世界完全相同",
            "mechanical_pass": "64/64 两臂 complete；force_count=1；首动作逐字匹配；零 timeout/illegal/fallback/auto/audit_missing",
            "direction_rule": {
                "SUPPORT": "配对均值>0且确定性bootstrap 95%下界>0",
                "CONTRADICT": "配对均值<0且确定性bootstrap 95%上界<0",
                "INCONCLUSIVE": "其余情况",
            },
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "sample_size_estimate": "试点样本标准差 s；后续达到均值半宽16分的近似样本量 ceil((1.96*s/16)^2)，至少64",
            "training": False,
            "selection_eligible": False,
            "hidden_eligible": False,
            "table_strength_claim": False,
            "release_eligible": False,
        },
    )
    print(json.dumps({"status": "PREPARED", "pairs": PAIRS}, ensure_ascii=False))


def verify_manifest(manifest: dict[str, Any]) -> None:
    """执行前后核对冻结来源，拒绝输入漂移。"""

    current = source_hashes()
    if manifest.get("source_hashes") != current:
        changed = sorted(
            key
            for key in set(current) | set(manifest.get("source_hashes") or {})
            if current.get(key) != (manifest.get("source_hashes") or {}).get(key)
        )
        raise ValueError("P4 反事实冻结来源漂移：" + repr(changed))


def run() -> None:
    """执行冻结的 64 对并写入机械与方向校准结果。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify_manifest(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("P4 反事实已执行；拒绝覆盖")
    case = read_case()
    pairs = [asyncio.run(run_pair(case, index)) for index in range(1, PAIRS + 1)]
    valid = [item for item in pairs if item["mechanical_ok"]]
    deltas = [
        float(item["piao_minus_hu_focal_score"])
        for item in valid
        if item["piao_minus_hu_focal_score"] is not None
    ]
    mechanics = len(valid) == PAIRS and len(deltas) == PAIRS
    mean = statistics.fmean(deltas) if deltas else None
    median = statistics.median(deltas) if deltas else None
    standard_deviation = statistics.stdev(deltas) if len(deltas) > 1 else None
    interval = bootstrap_interval(deltas) if deltas else (None, None)
    direction = "MECHANICAL_FAIL"
    if mechanics and mean is not None:
        if mean > 0 and interval[0] is not None and interval[0] > 0:
            direction = "SUPPORT"
        elif mean < 0 and interval[1] is not None and interval[1] < 0:
            direction = "CONTRADICT"
        else:
            direction = "INCONCLUSIVE"
    needed = None
    if standard_deviation is not None:
        needed = max(
            PAIRS,
            math.ceil((1.96 * standard_deviation / TARGET_MARGIN) ** 2),
        )
    result = {
        "schema": "r18-p4-counterfactual-pilot-result/1",
        "status": "PASS_MECHANICS" if mechanics else "FAIL_MECHANICS",
        "direction": direction,
        "manifest_sha256": digest_file(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "pairs": pairs,
        "summary": {
            "pairs_planned": PAIRS,
            "pairs_mechanically_valid": len(valid),
            "mean_piao_minus_hu_focal_score": mean,
            "median_piao_minus_hu_focal_score": median,
            "sample_standard_deviation": standard_deviation,
            "bootstrap_mean_95_interval": list(interval),
            "piao_better": sum(value > 0 for value in deltas),
            "tie": sum(value == 0 for value in deltas),
            "piao_worse": sum(value < 0 for value in deltas),
            "min": min(deltas) if deltas else None,
            "max": max(deltas) if deltas else None,
            "estimated_pairs_for_mean_half_width_16": needed,
            "selection_eligible": False,
            "hidden_eligible": False,
            "table_strength_claim": False,
        },
    }
    write_json(result_path, result)
    verify_manifest(manifest)
    print(json.dumps(result["summary"] | {"direction": direction}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
