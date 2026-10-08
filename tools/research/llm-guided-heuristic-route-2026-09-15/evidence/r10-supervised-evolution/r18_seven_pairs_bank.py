"""R18 七对门清机会题库：真实规则事实、全动作 oracle 与正式策略接缝。

题库包含两个互斥层：

* ``seven_pairs_tradeoff``：同一手同时存在下一摸平胡路线与七对路线，七对
  的官方结算倍率使其条件期望严格更高；
* ``standard_switch``：手中仍有多对，但下一摸只有普通型路线产生正期望，
  用作“不能一律保七对”的负控。

每个 14 张状态都能由庄家初始 13 张加一次摸牌到达，所有牌码不超过四张。
oracle 只消费 ``HangmaRules`` 已生产的完整 ``CandidateValueFacts``，并给题面
全部合法动作赋值；它是声明的一次本人自摸条件代理，不冒充完整牌局 Q 值。
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
import itertools
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
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile  # noqa: E402
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState  # noqa: E402
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


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-seven-pairs-bank-01-20260922')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
GENERATOR_SEED = 202609220703
QUOTAS = {"seven_pairs_tradeoff": 64, "standard_switch": 32}
HIDDEN_QUOTAS = {"seven_pairs_tradeoff": 16, "standard_switch": 8}
WHITE = "白"


def canonical_bytes(value: Any) -> bytes:
    """返回稳定 JSON 字节。"""

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_value(value: Any) -> str:
    """返回 JSON 值摘要。"""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(path: Path) -> str:
    """返回文件摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def observation_of(case_id: str, hand13: tuple[str, ...], draw: str) -> PlayerObservation:
    """构造庄家起手后第一次摸牌的公开观察。"""

    counts = Counter(hand13 + (draw,))
    if len(hand13) != 13 or any(value > 4 for value in counts.values()):
        raise ValueError(case_id + " 不是物理可达的 13+1 张状态")
    return PlayerObservation(
        game_id=case_id,
        seat=0,
        round_no=1,
        snapshot_seq=1,
        consumed_seq=1,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(code) for code in hand13),
        drawn_tile=Tile(draw),
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=83,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile(WHITE), False, 0, False),
        public_history=(),
        chain_piao=0,
        gang_draw=False,
    )


def route_branches(request: Any) -> dict[str, set[str]]:
    """读取规则条件结算中的胡牌分支标签。"""

    result = {}
    for candidate in request.rules.legal_candidates:
        labels = set()
        if candidate.value_facts is not None:
            for route in candidate.value_facts.routes:
                labels.update(route.conditional_settlement.details)
        result[candidate.action_key] = labels
    return result


def classify(request: Any, values: tuple[OracleActionValue, ...]) -> str:
    """按全动作 oracle 与规则结算标签划分互斥题型。"""

    table = {item.action_key: float(item.value) for item in values}
    best = max(table.values())
    optimal = {key for key, value in table.items() if value == best}
    branches = route_branches(request)
    optimal_labels = {label for key in optimal for label in branches[key]}
    seven_best = "七对" in optimal_labels
    lower_plain = any(
        value > 0.0 and value < best and "平胡" in branches[key]
        for key, value in table.items()
    )
    if seven_best and lower_plain:
        return "seven_pairs_tradeoff"
    if "平胡" in optimal_labels and "七对" not in optimal_labels:
        facts = [
            candidate.facts for candidate in request.rules.legal_candidates
            if candidate.action_key.startswith("discard:") and candidate.facts is not None
        ]
        if facts and min(
            item.seven_pairs_shanten_after
            for item in facts if item.seven_pairs_shanten_after is not None
        ) <= 1:
            return "standard_switch"
    return "other"


def build_case(
    *, full14: tuple[str, ...], draw: str, ordinal: int,
    generator_hash: str, rules_hash: str,
) -> dict[str, Any]:
    """生成一个全动作可计值、可回放的机会题。"""

    case_id = "r18-7p-{0:03d}".format(ordinal)
    hand = list(full14)
    hand.remove(draw)
    hand13 = tuple(sorted(hand))
    request = bank.request_of(case_id, observation_of(case_id, hand13, draw))
    if any(not item.action_key.startswith("discard:") for item in request.rules.legal_candidates):
        raise RuntimeError(case_id + " 不是纯弃牌窗口")
    oracle = build_one_draw_self_win_oracle(request)
    legal = {item.action_key for item in request.rules.legal_candidates}
    valued = {item.action_key for item in oracle.values}
    if oracle.issues or legal != valued:
        raise RuntimeError(case_id + " oracle 不完整: " + repr((oracle.issues, sorted(legal - valued))))
    request_json = decision_request_to_json(request)
    witness = {
        "kind": "initial_deal_plus_dealer_draw",
        "hand13": list(hand13),
        "draw": draw,
        "full14": list(full14),
        "physical_counts": dict(sorted(Counter(full14).items())),
        "wall_remaining": 83,
        "no_melds_or_discards": True,
        "current_draw_removed_from_unknown_pool_by_observation": True,
    }
    return {
        "case_id": case_id,
        "base_scenario_id": case_id,
        "family": "seven_pairs_closed",
        "split": "unassigned",
        "decision_type": classify(request, oracle.values),
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


def tradeoff_states() -> list[tuple[tuple[str, ...], str]]:
    """枚举六对两单且同时存在平胡听口的结构模板。"""

    states = []
    for suit_a, suit_b, suit_c in itertools.permutations(("w", "b", "t"), 3):
        for start_a in range(1, 8):
            for start_b in range(1, 9):
                for start_c in range(1, 8):
                    pair_codes = [
                        str(start_a + offset) + suit_a for offset in range(3)
                    ] + [
                        str(start_b) + suit_b,
                        str(start_b + 1) + suit_b,
                        str(start_c) + suit_c,
                    ]
                    singles = (
                        str(start_c + 1) + suit_c,
                        str(start_c + 2) + suit_c,
                    )
                    full14 = tuple(sorted(
                        tuple(code for code in pair_codes for _ in range(2)) + singles
                    ))
                    states.append((full14, singles[1]))
    return states


def random_five_pair_state(rng: random.Random) -> tuple[tuple[str, ...], str]:
    """生成五对四单的物理可达状态，供筛选普通型胜出负控。"""

    codes = [code for code in CANONICAL_TILE_ORDER if code != WHITE]
    pairs = rng.sample(codes, 5)
    singles = rng.sample([code for code in codes if code not in pairs], 4)
    full14 = tuple(sorted(
        tuple(code for code in pairs for _ in range(2)) + tuple(singles)
    ))
    return full14, singles[-1]


def generate() -> None:
    """先生成并冻结题库，再允许任何候选读取开发题。"""

    if OUT.exists():
        raise SystemExit("七对题库目录已存在；拒绝覆盖")
    generator_hash = digest(Path(__file__))
    rules_hash = bank.rules_sha256()
    rng = random.Random(GENERATOR_SEED)
    candidates = tradeoff_states()
    rng.shuffle(candidates)
    selected: dict[str, list[dict[str, Any]]] = {key: [] for key in QUOTAS}
    seen = set()
    attempts = Counter()
    for full14, draw in candidates:
        if len(selected["seven_pairs_tradeoff"]) >= QUOTAS["seven_pairs_tradeoff"]:
            break
        identity = (full14, draw)
        if identity in seen:
            continue
        seen.add(identity)
        attempts["tradeoff_states"] += 1
        case = build_case(
            full14=full14,
            draw=draw,
            ordinal=sum(len(values) for values in selected.values()) + 1,
            generator_hash=generator_hash,
            rules_hash=rules_hash,
        )
        if case["decision_type"] == "seven_pairs_tradeoff":
            selected["seven_pairs_tradeoff"].append(case)
    while len(selected["standard_switch"]) < QUOTAS["standard_switch"]:
        attempts["standard_switch_states"] += 1
        if attempts["standard_switch_states"] > 200_000:
            raise RuntimeError("达到尝试上限仍未填满 standard_switch")
        full14, draw = random_five_pair_state(rng)
        identity = (full14, draw)
        if identity in seen:
            continue
        seen.add(identity)
        case = build_case(
            full14=full14,
            draw=draw,
            ordinal=sum(len(values) for values in selected.values()) + 1,
            generator_hash=generator_hash,
            rules_hash=rules_hash,
        )
        if case["decision_type"] == "standard_switch":
            selected["standard_switch"].append(case)
    if any(len(selected[key]) != quota for key, quota in QUOTAS.items()):
        raise RuntimeError("七对题库分层配额未填满")
    cases = [case for key in sorted(selected) for case in selected[key]]
    cases.sort(key=lambda case: (
        case["decision_type"],
        case["reachability_witness"]["full14"],
        case["reachability_witness"]["draw"],
    ))
    rebuilt = []
    for ordinal, case in enumerate(cases, 1):
        witness = case["reachability_witness"]
        rebuilt.append(build_case(
            full14=tuple(witness["full14"]),
            draw=witness["draw"],
            ordinal=ordinal,
            generator_hash=generator_hash,
            rules_hash=rules_hash,
        ))
    cases = rebuilt
    for dtype in QUOTAS:
        group = [case for case in cases if case["decision_type"] == dtype]
        hidden = {
            case["case_id"] for case in sorted(
                group,
                key=lambda item: digest_value((GENERATOR_SEED, item["reachability_witness_sha256"])),
            )[: HIDDEN_QUOTAS[dtype]]
        }
        for case in group:
            case["split"] = "hidden" if case["case_id"] in hidden else "development"
    counts = Counter((case["split"], case["decision_type"]) for case in cases)
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-seven-pairs-bank-manifest/1",
        "generator_seed": GENERATOR_SEED,
        "generator_sha256": generator_hash,
        "rules_hash": rules_hash,
        "oracle_version": ORACLE_VERSION,
        "cases": len(cases),
        "unique_base_scenarios": len({case["base_scenario_id"] for case in cases}),
        "quotas": QUOTAS,
        "hidden_quotas": HIDDEN_QUOTAS,
        "counts": [
            {"split": split, "decision_type": dtype, "count": count}
            for (split, dtype), count in sorted(counts.items())
        ],
        "generation_work": dict(sorted(attempts.items())),
        "split_rule": "每题型按(seed, reachability_witness_sha256)哈希排序取预登记hidden配额",
        "scope": "庄家起手后首次摸牌；无副露无牌河；纯弃牌窗口；七对/平胡下一摸价值取舍",
        "limitations": [
            "oracle 是下一次本人摸牌立即胡的条件代理，不含他家先胡、鸣牌、轮转和更远续值",
            "本批不含财神、爆头、杠、动作链或赛事处境，避免把多个特殊能力混成一题",
            "隐藏题只允许候选冻结后的一次性准入程序读取",
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
        "counts": {f"{split}:{dtype}": count for (split, dtype), count in sorted(counts.items())},
        "generation_work": dict(sorted(attempts.items())),
    }, ensure_ascii=False, indent=2))


def load_development() -> tuple[list[OpportunityCapabilityCase], list[dict[str, Any]]]:
    """只读取开发题；候选冻结前没有隐藏题入口。"""

    payload = json.loads((_project_file(_PROJECT_ROOT, OUT / "development.json")).read_text(encoding="utf-8"))
    cases = []
    metadata = []
    for row in payload["cases"]:
        if digest_value(row["request"]) != row["request_sha256"]:
            raise RuntimeError(row["case_id"] + " 请求摘要不符")
        if digest_value(row["reachability_witness"]) != row["reachability_witness_sha256"]:
            raise RuntimeError(row["case_id"] + " 可达见证摘要不符")
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
        metadata.append({"decision_type": row["decision_type"]})
    return cases, metadata


async def score_parent_development() -> dict[str, Any]:
    """经正式 BotPolicy 接缝测 P5 在开发题上的 headroom。"""

    cases, metadata = load_development()
    parent = ActionValuePolicy(ActionValueScorer("r18-seven-pairs-bank-p5", PARENT.read_text(encoding="utf-8")))
    baseline = ComparableHeuristicPolicyV2()
    rows = [
        await evaluate_pair(parent, baseline, case, bank.budget)
        for case in cases
    ]
    by_type = {}
    for dtype in QUOTAS:
        chosen = [
            row for row, meta in zip(rows, metadata)
            if meta["decision_type"] == dtype
        ]
        by_type[dtype] = {
            "cases": len(chosen),
            "p5_optimal_hits": sum(
                row.candidate.chosen_action_key in row.candidate.optimal_action_keys
                for row in chosen
            ),
            "v2_optimal_hits": sum(
                row.baseline.chosen_action_key in row.baseline.optimal_action_keys
                for row in chosen
            ),
            "p5_mean_regret": sum(float(row.candidate.regret) for row in chosen) / len(chosen),
            "v2_mean_regret": sum(float(row.baseline.regret) for row in chosen) / len(chosen),
        }
    return {
        "schema": "r18-seven-pairs-bank-parent-score/1",
        "candidate": "P5",
        "candidate_sha256": digest(PARENT),
        "summary": asdict(summarize_family(
            rows, family="seven_pairs_closed", split="development"
        )),
        "by_type": by_type,
        "rows": [asdict(row) for row in rows],
        "selection_eligible": False,
        "release_eligible": False,
    }


def score_parent() -> None:
    """冻结后评价 P5 开发表现，不读取隐藏文件。"""

    target = _project_file(_PROJECT_ROOT, OUT / "development-parent-score.json")
    if target.exists():
        raise SystemExit("P5 开发评分已存在；拒绝覆盖")
    result = asyncio.run(score_parent_development())
    write_json(target, result)
    print(json.dumps({
        "summary": result["summary"],
        "by_type": result["by_type"],
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("generate", "score-parent"))
    args = parser.parse_args()
    if args.operation == "generate":
        generate()
    else:
        score_parent()


if __name__ == "__main__":
    main()
