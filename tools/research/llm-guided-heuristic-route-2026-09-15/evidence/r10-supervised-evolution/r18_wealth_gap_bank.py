"""R18 多财神剩余缺口题库：三财神飘/保财与四财神保财。

``generate`` 只使用生产规则和冻结 oracle，候选不可见；``score-development``
随后才装载当前 P4 父代，并且只读取 development 文件。hidden 依机会分层冻结，
留给新候选完成配对反事实校准后的一次性准入。
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
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import r18_multi_wealth_bank as bank  # noqa: E402
from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_request_from_json,
    decision_request_to_json,
)
from hangma_bot.hangma.progression import recompute_baotou  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile  # noqa: E402
from hangma_bot.offline.opportunity_capability import (  # noqa: E402
    OpportunityCapabilityCase,
    OracleActionValue,
    evaluate_pair,
    summarize_family,
)
from hangma_bot.offline.opportunity_oracle import (  # noqa: E402
    ORACLE_VERSION,
    build_one_draw_self_win_oracle,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-bank-01-20260922')
PARENT = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
)
OLD_BANKS = (
    _project_file(_PROJECT_ROOT, HERE / "r18-multi-wealth-bank-02-20260922"),
    _project_file(_PROJECT_ROOT, HERE / "r18-p4-shape-bank-01-20260922"),
)
GENERATOR_SEED = 202609220503
QUOTAS = {
    "three_wealth_piao": 32,
    "three_wealth_keep": 32,
    "four_wealth_keep": 32,
}
HIDDEN_QUOTAS = {key: 8 for key in QUOTAS}
STRATUM_WEALTH = {
    "three_wealth_piao": 3,
    "three_wealth_keep": 3,
    "four_wealth_keep": 4,
}
STRATUM_DECISION = {
    "three_wealth_piao": "piao",
    "three_wealth_keep": "keep_wealth",
    "four_wealth_keep": "keep_wealth",
}
WHITE = "白"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def excluded_hands() -> set[tuple[str, ...]]:
    """排除前两套多财神题库的全部开发/隐藏手牌。"""

    values: set[tuple[str, ...]] = set()
    for directory in OLD_BANKS:
        for name in ("development.json", "hidden.json"):
            payload = json.loads((directory / name).read_text(encoding="utf-8"))
            for row in payload["cases"]:
                values.add(tuple(row["reachability_witness"]["hand13"]))
    return values


def candidate_hand(rng: random.Random, wealth_count: int) -> tuple[str, ...]:
    """从四副非财神物理牌中抽牌，再加入指定张数的白板财神。"""

    nonwhite = [
        code for code in CANONICAL_TILE_ORDER if code != WHITE for _ in range(4)
    ]
    return tuple(sorted(
        rng.sample(nonwhite, 13 - wealth_count) + [WHITE] * wealth_count
    ))


def possible_draws(hand: tuple[str, ...], rng: random.Random) -> list[str]:
    """枚举不会形成非财神四同张的当前直抽，顺序由种子冻结。"""

    counts = Counter(hand)
    values = [
        code for code in CANONICAL_TILE_ORDER
        if code != WHITE and counts[code] <= 2
    ]
    rng.shuffle(values)
    return values


def classify(values: tuple[OracleActionValue, ...]) -> str:
    best = max(item.value for item in values)
    keys = {item.action_key for item in values if item.value == best}
    if "hu" in keys:
        return "take_hu"
    if "discard:白" in keys:
        return "piao"
    if any(key.startswith("discard:") for key in keys):
        return "keep_wealth"
    return "other"


def build_case(
    *,
    hand: tuple[str, ...],
    draw: str,
    ordinal: int,
    generator_hash: str,
    rules_hash: str,
) -> dict[str, Any]:
    case_id = "r18-wgap-{0:03d}".format(ordinal)
    wealth_count = hand.count(WHITE)
    observation = bank.observation_of(case_id, hand, draw)
    request = bank.request_of(case_id, observation)
    oracle = build_one_draw_self_win_oracle(request)
    legal = {item.action_key for item in request.rules.legal_candidates}
    valued = {item.action_key for item in oracle.values}
    if oracle.issues or legal != valued:
        raise RuntimeError(case_id + " oracle 不完整")
    request_json = decision_request_to_json(request)
    witness = {
        "kind": "initial_deal_plus_dealer_draw",
        "hand13": list(hand),
        "draw": draw,
        "physical_counts": dict(sorted(Counter(hand + (draw,)).items())),
        "wall_remaining": 83,
        "pre_draw_baotou": True,
        "baotou_after_draw": True,
        "no_nonwealth_quad_after_draw": max(
            (
                count
                for code, count in Counter(hand + (draw,)).items()
                if code != WHITE
            ),
            default=0,
        ) < 4,
    }
    decision_type = classify(oracle.values)
    suffix = {
        "piao": "piao",
        "keep_wealth": "keep",
    }.get(decision_type, decision_type)
    stratum = (
        ("three_wealth_" if wealth_count == 3 else "four_wealth_") + suffix
    )
    return {
        "case_id": case_id,
        "base_scenario_id": case_id,
        "family": "multi_wealth_baotou",
        "split": "unassigned",
        "wealth_count": wealth_count,
        "decision_type": decision_type,
        "opportunity_stratum": stratum,
        "generator_seed": GENERATOR_SEED,
        "rules_hash": rules_hash,
        "generator_sha256": generator_hash,
        "oracle_version": ORACLE_VERSION,
        "oracle_level": "declared_conditional_proxy",
        "request_sha256": digest_value(request_json),
        "reachability_witness_sha256": digest_value(witness),
        "request": request_json,
        "reachability_witness": witness,
        "unseen_tile_count": oracle.unseen_tile_count,
        "action_values": [asdict(item) for item in oracle.values],
    }


def _fill_wealth(
    *,
    wealth_count: int,
    target_strata: tuple[str, ...],
    selected: dict[str, list[dict[str, Any]]],
    seen: set[tuple[str, ...]],
    excluded: set[tuple[str, ...]],
    rng: random.Random,
    generator_hash: str,
    rules_hash: str,
) -> dict[str, int]:
    attempts = valid_hands = analyzed_states = 0
    while any(len(selected[key]) < QUOTAS[key] for key in target_strata):
        attempts += 1
        if attempts > 2_000_000:
            raise RuntimeError("达到手牌尝试上限仍未填满分层配额")
        hand = candidate_hand(rng, wealth_count)
        if hand in seen or hand in excluded:
            continue
        seen.add(hand)
        if not recompute_baotou(tuple(Tile(code) for code in hand), 0, wealth_count):
            continue
        valid_hands += 1
        for draw in possible_draws(hand, rng):
            analyzed_states += 1
            probe = build_case(
                hand=hand,
                draw=draw,
                ordinal=sum(len(values) for values in selected.values()) + 1,
                generator_hash=generator_hash,
                rules_hash=rules_hash,
            )
            stratum = probe["opportunity_stratum"]
            if stratum in target_strata and len(selected[stratum]) < QUOTAS[stratum]:
                selected[stratum].append(probe)
                break
    return {
        "hand_attempts": attempts,
        "valid_baotou_hands": valid_hands,
        "analyzed_hand_draw_states": analyzed_states,
    }


def generate() -> None:
    """先冻结 96 个零重叠基础手牌，再按分层哈希切开发/隐藏。"""

    if OUT.exists():
        raise SystemExit("R18 多财神缺口题库目录已存在；拒绝覆盖")
    generator_hash = digest(Path(__file__))
    rules_hash = bank.rules_sha256()
    rng = random.Random(GENERATOR_SEED)
    excluded = excluded_hands()
    seen: set[tuple[str, ...]] = set()
    selected = {key: [] for key in QUOTAS}
    work = {
        "wealth_3": _fill_wealth(
            wealth_count=3,
            target_strata=("three_wealth_piao", "three_wealth_keep"),
            selected=selected,
            seen=seen,
            excluded=excluded,
            rng=rng,
            generator_hash=generator_hash,
            rules_hash=rules_hash,
        ),
        "wealth_4": _fill_wealth(
            wealth_count=4,
            target_strata=("four_wealth_keep",),
            selected=selected,
            seen=seen,
            excluded=excluded,
            rng=rng,
            generator_hash=generator_hash,
            rules_hash=rules_hash,
        ),
    }
    cases = [case for key in sorted(selected) for case in selected[key]]
    cases.sort(key=lambda case: (
        case["opportunity_stratum"],
        case["reachability_witness"]["hand13"],
        case["reachability_witness"]["draw"],
    ))
    # case_id 在请求和窗口键内；排序后必须从规则入口完整重建。
    for ordinal, old in enumerate(tuple(cases), 1):
        witness = old["reachability_witness"]
        cases[ordinal - 1] = build_case(
            hand=tuple(witness["hand13"]),
            draw=witness["draw"],
            ordinal=ordinal,
            generator_hash=generator_hash,
            rules_hash=rules_hash,
        )
    for stratum in QUOTAS:
        group = [case for case in cases if case["opportunity_stratum"] == stratum]
        hidden_ids = {
            case["case_id"]
            for case in sorted(
                group,
                key=lambda item: digest_value((
                    GENERATOR_SEED,
                    item["reachability_witness_sha256"],
                )),
            )[: HIDDEN_QUOTAS[stratum]]
        }
        for case in group:
            case["split"] = "hidden" if case["case_id"] in hidden_ids else "development"
    counts = Counter(
        (case["split"], case["opportunity_stratum"]) for case in cases
    )
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-wealth-gap-bank-manifest/1",
        "generator_seed": GENERATOR_SEED,
        "generator_sha256": generator_hash,
        "rules_hash": rules_hash,
        "oracle_version": ORACLE_VERSION,
        "cases": len(cases),
        "unique_hand13": len({
            tuple(case["reachability_witness"]["hand13"]) for case in cases
        }),
        "old_bank_overlap": sum(
            tuple(case["reachability_witness"]["hand13"]) in excluded
            for case in cases
        ),
        "quotas": QUOTAS,
        "hidden_quotas": HIDDEN_QUOTAS,
        "generation_work": work,
        "counts": [
            {"split": split, "opportunity_stratum": stratum, "count": count}
            for (split, stratum), count in sorted(counts.items())
        ],
        "split_rule": "每分层按(seed, reachability_witness_sha256)哈希排序取8个hidden；候选评分前冻结",
        "scope": "三/四财神、庄家起手首次摸牌、无副露无牌河；96个唯一13张手牌",
        "limitations": [
            "真值是下一次本人摸牌立即胡的条件代理，配对反事实校准后才能开启隐藏准入",
            "不覆盖牌局中段、杠链、鸣牌或赛事处境",
            "hidden 只允许冻结候选与反事实方向后的一次性准入程序读取",
        ],
        "candidate_evaluated_during_generation": False,
    })
    for split in ("development", "hidden"):
        write_json(_project_file(_PROJECT_ROOT, OUT / (split + ".json")), {
            "schema": "r18-opportunity-bank/1",
            "cases": [case for case in cases if case["split"] == split],
        })
    print(json.dumps({
        "status": "GENERATED",
        "cases": len(cases),
        "counts": {
            f"{split}:{stratum}": count
            for (split, stratum), count in sorted(counts.items())
        },
        "generation_work": work,
    }, ensure_ascii=False, indent=2))


def load_development() -> tuple[list[OpportunityCapabilityCase], list[dict[str, Any]]]:
    """只解析开发集；函数没有 hidden 输入路径。"""

    payload = json.loads((_project_file(_PROJECT_ROOT, OUT / "development.json")).read_text(encoding="utf-8"))
    cases = []
    metadata = []
    for row in payload["cases"]:
        if digest_value(row["request"]) != row["request_sha256"]:
            raise RuntimeError("开发题请求摘要不符")
        if digest_value(row["reachability_witness"]) != row["reachability_witness_sha256"]:
            raise RuntimeError("开发题可达见证摘要不符")
        cases.append(OpportunityCapabilityCase(
            case_id=row["case_id"],
            base_scenario_id=row["base_scenario_id"],
            family=row["family"],
            split=row["split"],
            generator_seed=row["generator_seed"],
            rules_hash=row["rules_hash"],
            generator_sha256=row["generator_sha256"],
            oracle_version=row["oracle_version"],
            oracle_level=row["oracle_level"],
            request_sha256=row["request_sha256"],
            reachability_witness_sha256=row["reachability_witness_sha256"],
            request=decision_request_from_json(row["request"]),
            action_values=tuple(OracleActionValue(**item) for item in row["action_values"]),
        ))
        metadata.append({"opportunity_stratum": row["opportunity_stratum"]})
    return cases, metadata


async def evaluate_development() -> tuple[list[Any], list[dict[str, Any]]]:
    cases, metadata = load_development()
    parent = ActionValuePolicy(ActionValueScorer(
        "r18-P4-wealth-gap-development", PARENT.read_text(encoding="utf-8")
    ))
    baseline = ComparableHeuristicPolicyV2()
    rows = [
        await evaluate_pair(parent, baseline, case, bank.budget) for case in cases
    ]
    return rows, metadata


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def score_development() -> None:
    """评价当前 P4 父代，只输出开发集分层缺口。"""

    target = _project_file(_PROJECT_ROOT, OUT / "development-parent-score.json")
    if target.exists():
        raise SystemExit("开发父代评分已存在；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest.get("candidate_evaluated_during_generation") is not False:
        raise ValueError("题库生成与候选评价边界不成立")
    rows, metadata = asyncio.run(evaluate_development())
    strata = {}
    for stratum in QUOTAS:
        selected = [
            row for row, meta in zip(rows, metadata)
            if meta["opportunity_stratum"] == stratum
        ]
        strata[stratum] = {
            "cases": len(selected),
            "scored": sum(row.capability_gain is not None for row in selected),
            "changed": sum(
                row.candidate.chosen_action_key != row.baseline.chosen_action_key
                for row in selected
            ),
            "improved": sum(
                row.capability_gain is not None and row.capability_gain > 0
                for row in selected
            ),
            "regressed": sum(
                row.capability_gain is not None and row.capability_gain < 0
                for row in selected
            ),
            "parent_optimal": sum(
                row.candidate.chosen_action_key in row.candidate.optimal_action_keys
                for row in selected
            ),
            "baseline_optimal": sum(
                row.baseline.chosen_action_key in row.baseline.optimal_action_keys
                for row in selected
            ),
            "mean_parent_regret": _mean([
                float(row.candidate.regret) for row in selected
                if row.candidate.regret is not None
            ]),
            "mean_baseline_regret": _mean([
                float(row.baseline.regret) for row in selected
                if row.baseline.regret is not None
            ]),
            "mean_capability_gain": _mean([
                float(row.capability_gain) for row in selected
                if row.capability_gain is not None
            ]),
        }
    result = {
        "schema": "r18-wealth-gap-development-parent-score/1",
        "parent_sha256": digest(PARENT),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "split": "development",
        "hidden_read": False,
        "summary": asdict(summarize_family(
            rows, family="multi_wealth_baotou", split="development"
        )),
        "strata": strata,
        "hidden_evaluation_started": False,
        "release_eligible": False,
    }
    write_json(target, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("generate", "score-development"))
    args = parser.parse_args()
    globals()[args.operation.replace("-", "_")]()
