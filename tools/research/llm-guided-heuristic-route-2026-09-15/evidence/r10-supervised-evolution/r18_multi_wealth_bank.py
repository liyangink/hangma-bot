"""R18 首个多财神/爆头机会题库：生成、冻结并用正式 BotPolicy 评分。

首版只使用可证明可达的“庄家起手后首次摸牌”状态：本人 13 张初始暗牌、
牌墙 83 张、无副露无牌河，规则模块证明摸前任意听，当前摸牌后同时存在
合法胡与弃牌。oracle 复用 hangma 的完整一次摸牌价值事实，属于声明条件
代理，不声称是真实完整桌赛最优。
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
import time


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_request_from_json,
    decision_request_to_json,
)
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.hangma.progression import (  # noqa: E402
    baotou_after_draw,
    recompute_baotou,
)
from hangma_bot.kernel.actions import (  # noqa: E402
    CANONICAL_TILE_ORDER,
    Tile,
    WindowKey,
    WindowPhase,
)
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.kernel.observation import (  # noqa: E402
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)
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
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import (  # noqa: E402
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922')
GENERATOR_SEED = 2026092201
RULE_CONFIG = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
RULES = HangmaRules(RULE_CONFIG)
LIMITS = ValueAnalysisLimits(max_expansions=20000, max_routes_per_candidate=256)
WHITE = "白"
BASES_PER_WEALTH = 8


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest_value(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generator_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def rules_sha256() -> str:
    """绑定生产规则源码与配置；不同源码树不能复用题库身份。"""

    sha = hashlib.sha256(canonical_bytes(asdict(RULE_CONFIG)))
    for path in sorted((_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma")).glob("*.py")):
        sha.update(str(path.relative_to(ROOT)).encode("utf-8"))
        sha.update(hashlib.sha256(path.read_bytes()).digest())
    return sha.hexdigest()


def _meld_pool() -> tuple[tuple[str, ...], ...]:
    melds = []
    for suit in ("w", "b", "t"):
        for start in range(1, 8):
            melds.append(tuple(str(start + offset) + suit for offset in range(3)))
    for code in CANONICAL_TILE_ORDER:
        if code != WHITE:
            melds.append((code, code, code))
    return tuple(melds)


def _one_wealth_hands(rng: random.Random, count: int) -> list[tuple[str, ...]]:
    """四个确定面子加单白：规则上摸任意牌都能以财神配对。"""

    pool = _meld_pool()
    hands = set()
    while len(hands) < count:
        flattened = tuple(code for meld in rng.sample(pool, 4) for code in meld)
        counts = Counter(flattened)
        if max(counts.values(), default=0) > 3:
            continue
        hand = tuple(sorted(flattened + (WHITE,)))
        if recompute_baotou(tuple(Tile(code) for code in hand), 0, 1):
            hands.add(hand)
    return sorted(hands)


def _sample_baotou_hands(
    rng: random.Random, wealth_count: int, count: int,
) -> list[tuple[str, ...]]:
    nonwhite_deck = [
        code for code in CANONICAL_TILE_ORDER if code != WHITE for _ in range(4)
    ]
    hands = set()
    attempts = 0
    while len(hands) < count and attempts < 1_000_000:
        attempts += 1
        hand = tuple(sorted(
            rng.sample(nonwhite_deck, 13 - wealth_count)
            + [WHITE] * wealth_count
        ))
        counts = Counter(hand)
        if max((n for code, n in counts.items() if code != WHITE), default=0) > 3:
            continue
        if recompute_baotou(tuple(Tile(code) for code in hand), 0, wealth_count):
            hands.add(hand)
    if len(hands) < count:
        raise RuntimeError(
            "无法生成足量爆头手牌: wealth={0}, found={1}, attempts={2}".format(
                wealth_count, len(hands), attempts
            )
        )
    return sorted(hands)


def base_hands() -> dict[int, list[tuple[str, ...]]]:
    rng = random.Random(GENERATOR_SEED)
    return {
        1: _one_wealth_hands(rng, BASES_PER_WEALTH),
        2: _sample_baotou_hands(rng, 2, BASES_PER_WEALTH),
        3: _sample_baotou_hands(rng, 3, BASES_PER_WEALTH),
        4: _sample_baotou_hands(rng, 4, BASES_PER_WEALTH),
    }


def choose_draw(hand: tuple[str, ...], index: int) -> str:
    counts = Counter(hand)
    choices = [
        code for code in CANONICAL_TILE_ORDER
        if counts[code] <= 2 and code != WHITE
    ]
    if not choices:
        raise RuntimeError("没有避免形成非财神杠的可达摸牌")
    return choices[(GENERATOR_SEED + index) % len(choices)]


def observation_of(case_id: str, hand: tuple[str, ...], draw: str) -> PlayerObservation:
    tiles = tuple(Tile(code) for code in hand)
    drawn = Tile(draw)
    if not baotou_after_draw(False, tiles, 0, drawn, replacement=False):
        raise RuntimeError(case_id + " 不能由起手状态证明爆头")
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
        my_hand=tiles,
        drawn_tile=drawn,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=83,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile(WHITE), True, 0, False),
        public_history=(),
        chain_piao=0,
        gang_draw=False,
    )


def request_of(case_id: str, observation: PlayerObservation) -> DecisionRequest:
    analysis = RULES.analyze(observation, value_limits=LIMITS)
    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="r18-opportunity-bank",
            stage_no=None,
            stage_role=None,
            stage_total=None,
            participant_rank=None,
            ranking=(),
            observed_at_unix_ms=0,
        ),
        rules=analysis,
        decision_id=case_id,
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(
            game_id=observation.game_id,
            round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=WindowPhase.DRAW,
            seat=observation.seat,
        ),
        rejected_attempts=(),
    )


def decision_type(values: tuple[OracleActionValue, ...]) -> str:
    best = max(item.value for item in values)
    keys = {item.action_key for item in values if item.value == best}
    if "hu" in keys:
        return "take_hu"
    if "discard:白" in keys:
        return "piao"
    if any(key.startswith("discard:") for key in keys):
        return "keep_wealth"
    if any(key.startswith("gang:") for key in keys):
        return "gang_or_decline"
    return "other"


def generate() -> None:
    if OUT.exists():
        raise SystemExit("R18 多财神题库目录已存在；拒绝覆盖")
    generator_hash = generator_sha256()
    rules_hash = rules_sha256()
    cases = []
    counts = Counter()
    for wealth_count, hands in base_hands().items():
        for index, hand in enumerate(hands):
            case_id = "r18-mw-w{0}-{1:02d}".format(wealth_count, index + 1)
            draw = choose_draw(hand, index + wealth_count * 100)
            request = request_of(case_id, observation_of(case_id, hand, draw))
            oracle = build_one_draw_self_win_oracle(request)
            legal = {item.action_key for item in request.rules.legal_candidates}
            valued = {item.action_key for item in oracle.values}
            if oracle.issues or valued != legal:
                raise RuntimeError(
                    case_id + " oracle 不完整: " + repr((oracle.issues, sorted(legal - valued)))
                )
            if "hu" not in legal or "discard:白" not in legal:
                raise RuntimeError(case_id + " 不同时具备胡与飘选择")
            request_json = decision_request_to_json(request)
            request_hash = digest_value(request_json)
            witness = {
                "kind": "initial_deal_plus_dealer_draw",
                "hand13": list(hand),
                "draw": draw,
                "physical_counts": dict(sorted(Counter(hand + (draw,)).items())),
                "wall_remaining": 83,
                "pre_draw_baotou": True,
                "baotou_after_draw": True,
                "no_nonwealth_quad_after_draw": max(
                    (n for code, n in Counter(hand + (draw,)).items() if code != WHITE),
                    default=0,
                ) < 4,
            }
            dtype = decision_type(oracle.values)
            cases.append({
                "case_id": case_id,
                "base_scenario_id": case_id,
                "family": "multi_wealth_baotou",
                "split": "unassigned",
                "wealth_count": wealth_count,
                "decision_type": dtype,
                "generator_seed": GENERATOR_SEED,
                "rules_hash": rules_hash,
                "generator_sha256": generator_hash,
                "oracle_version": ORACLE_VERSION,
                "oracle_level": "declared_conditional_proxy",
                "request_sha256": request_hash,
                "reachability_witness_sha256": digest_value(witness),
                "request": request_json,
                "reachability_witness": witness,
                "unseen_tile_count": oracle.unseen_tile_count,
                "action_values": [asdict(item) for item in oracle.values],
            })
    # 分层按 oracle 决策类型完成，候选运行前冻结。每个财神数保留 2 个隐藏
    # 基础场景；有 piao/keep_wealth 时优先各保留一个，避免隐藏集只剩易收胡题。
    for wealth_count in range(1, 5):
        group = [case for case in cases if case["wealth_count"] == wealth_count]
        hidden_ids = []
        for dtype in ("piao", "keep_wealth", "take_hu", "gang_or_decline", "other"):
            matches = sorted(
                (case for case in group if case["decision_type"] == dtype),
                key=lambda case: digest_value((GENERATOR_SEED, case["case_id"])),
            )
            if matches and len(hidden_ids) < 2:
                hidden_ids.append(matches[0]["case_id"])
        if len(hidden_ids) < 2:
            for case in sorted(group, key=lambda item: item["case_id"]):
                if case["case_id"] not in hidden_ids:
                    hidden_ids.append(case["case_id"])
                if len(hidden_ids) == 2:
                    break
        for case in group:
            case["split"] = "hidden" if case["case_id"] in hidden_ids else "development"
            counts[(case["split"], wealth_count, case["decision_type"])] += 1
    manifest = {
        "schema": "r18-multi-wealth-bank-manifest/1",
        "generator_seed": GENERATOR_SEED,
        "generator_sha256": generator_hash,
        "rules_hash": rules_hash,
        "oracle_version": ORACLE_VERSION,
        "cases": len(cases),
        "unique_base_scenarios": len({case["base_scenario_id"] for case in cases}),
        "development_cases": sum(case["split"] == "development" for case in cases),
        "hidden_cases": sum(case["split"] == "hidden" for case in cases),
        "split_rule": "每个财神数2个隐藏基础场景；按piao/keep_wealth/take_hu/gang_or_decline/other顺序各取确定性哈希首项，再补case_id；候选运行前冻结",
        "counts": [
            {"split": split, "wealth_count": wealth, "decision_type": dtype, "count": n}
            for (split, wealth, dtype), n in sorted(counts.items())
        ],
        "scope": "庄家起手后首次摸牌；无副露、牌河、杠候选和赛事处境；只校准胡/飘/保财",
        "limitations": [
            "oracle 只算候选后下一次本人摸牌立即胡，不建模他家先胡、鸣牌、轮转和更远续值",
            "本批不覆盖杠，不能独立满足完整 multi_wealth_baotou 家族准入",
            "隐藏题只靠运行隔离；制品在仓库内，作者提示构建时必须排除 hidden 文件",
        ],
    }
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    write_json(_project_file(_PROJECT_ROOT, OUT / "development.json"), {
        "schema": "r18-opportunity-bank/1",
        "cases": [case for case in cases if case["split"] == "development"],
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "hidden.json"), {
        "schema": "r18-opportunity-bank/1",
        "cases": [case for case in cases if case["split"] == "hidden"],
    })
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def load_cases() -> list[OpportunityCapabilityCase]:
    rows = []
    for name in ("development.json", "hidden.json"):
        payload = json.loads((_project_file(_PROJECT_ROOT, OUT / name)).read_text(encoding="utf-8"))
        for row in payload["cases"]:
            request = decision_request_from_json(row["request"])
            if digest_value(row["request"]) != row["request_sha256"]:
                raise RuntimeError(row["case_id"] + " request 哈希不符")
            if digest_value(row["reachability_witness"]) != row["reachability_witness_sha256"]:
                raise RuntimeError(row["case_id"] + " 可达见证哈希不符")
            rows.append(OpportunityCapabilityCase(
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
                request=request,
                action_values=tuple(OracleActionValue(**item) for item in row["action_values"]),
            ))
    return rows


class MappedControlPolicy:
    """只验证尺子的 oracle 感知控制；不得作为候选或作者父代。"""

    def __init__(self, choices: dict[str, str]):
        self.choices = choices

    async def choose(self, request, budget):
        del budget
        key = self.choices[request.decision_id]
        candidate = next(item for item in request.rules.legal_candidates if item.action_key == key)
        ranked = RankedCandidate(
            action=candidate.action,
            action_key=candidate.action_key,
            rank=1,
            total_score=0.0,
            score_parts=(),
            reasons=("R18 尺子控制",),
        )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.trigger_seq,
            revision=1,
            candidates=(ranked,),
            degraded_reasons=(),
        )


def budget() -> DecisionBudget:
    now = time.monotonic()
    return DecisionBudget(now + 10.0, now + 20.0, now + 30.0)


async def _score() -> dict:
    cases = load_cases()
    best = {}
    worst = {}
    for case in cases:
        ordered = sorted(case.action_values, key=lambda item: (item.value, item.action_key))
        worst[case.case_id] = ordered[0].action_key
        best[case.case_id] = ordered[-1].action_key
    v2 = ComparableHeuristicPolicyV2()
    positive = MappedControlPolicy(best)
    negative = MappedControlPolicy(worst)
    rows = {
        "v2": [],
        "positive_control": [],
        "negative_control": [],
    }
    for case in cases:
        rows["v2"].append(await evaluate_pair(v2, v2, case, budget))
        rows["positive_control"].append(await evaluate_pair(positive, v2, case, budget))
        rows["negative_control"].append(await evaluate_pair(negative, v2, case, budget))
    summaries = {}
    for name, outcomes in rows.items():
        summaries[name] = {
            split: asdict(summarize_family(
                outcomes,
                family="multi_wealth_baotou",
                split=split,
            ))
            for split in ("development", "hidden")
        }
    return {
        "schema": "r18-multi-wealth-bank-score/1",
        "controls_are_oracle_aware_and_for_measurement_only": True,
        "summaries": summaries,
        "rows": {
            name: [asdict(item) for item in outcomes]
            for name, outcomes in rows.items()
        },
    }


def score() -> None:
    result = asyncio.run(_score())
    write_json(_project_file(_PROJECT_ROOT, OUT / "score.json"), result)
    print(json.dumps(result["summaries"], ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("generate", "score"))
    args = parser.parse_args()
    globals()[args.operation]()


if __name__ == "__main__":
    main()
