"""R18 P4 跨手牌形状题库：四财神爆头的飘/收胡/保财分层。

生成与评分严格分步：``generate`` 只消费规则与 oracle，先冻结 64 个唯一
13 张焦点手牌及开发/隐藏分割；``score-development`` 之后才装载已冻结 P4，
且只读取 development 文件。
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


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-shape-bank-01-20260922')
OLD_BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922')
CANDIDATE = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
)
GENERATOR_SEED = 202609220402
QUOTAS = {"piao": 32, "take_hu": 16, "keep_wealth": 16}
HIDDEN_QUOTAS = {"piao": 8, "take_hu": 4, "keep_wealth": 4}
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


def old_hands() -> set[tuple[str, ...]]:
    """排除首尺全部 32 个焦点手牌，防止开发或隐藏状态重用。"""

    values: set[tuple[str, ...]] = set()
    for name in ("development.json", "hidden.json"):
        doc = json.loads((_project_file(_PROJECT_ROOT, OLD_BANK / name)).read_text(encoding="utf-8"))
        for row in doc["cases"]:
            values.add(tuple(row["reachability_witness"]["hand13"]))
    return values


def candidate_hand(rng: random.Random) -> tuple[str, ...]:
    """从四副非财神物理牌中抽 9 张，再加入四白。"""

    nonwhite = [
        code for code in CANONICAL_TILE_ORDER if code != WHITE for _ in range(4)
    ]
    return tuple(sorted(rng.sample(nonwhite, 9) + [WHITE] * 4))


def possible_draws(hand: tuple[str, ...], rng: random.Random) -> list[str]:
    """给出不会形成非财神四同张的直抽；顺序由生成随机源冻结。"""

    counts = Counter(hand)
    values = [
        code for code in CANONICAL_TILE_ORDER
        if code != WHITE and counts[code] <= 2
    ]
    rng.shuffle(values)
    return values


def classify(values: tuple[OracleActionValue, ...]) -> str:
    """按同一 oracle 最优集合划分 P4 题型。"""

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
    *, hand: tuple[str, ...], draw: str, ordinal: int, generator_hash: str,
    rules_hash: str,
) -> dict[str, Any]:
    case_id = "r18-p4s-{0:03d}".format(ordinal)
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
    return {
        "case_id": case_id,
        "base_scenario_id": case_id,
        "family": "multi_wealth_baotou",
        "split": "unassigned",
        "wealth_count": 4,
        "decision_type": classify(oracle.values),
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


def generate() -> None:
    """生成到每个预登记题型配额满，随后按哈希冻结新隐藏分割。"""

    if OUT.exists():
        raise SystemExit("P4 跨手牌题库目录已存在；拒绝覆盖")
    generator_hash = digest(Path(__file__))
    rules_hash = bank.rules_sha256()
    rng = random.Random(GENERATOR_SEED)
    excluded = old_hands()
    seen = set(excluded)
    selected: dict[str, list[dict[str, Any]]] = {
        key: [] for key in QUOTAS
    }
    attempts = valid_hands = analyzed_states = 0
    while any(len(selected[key]) < quota for key, quota in QUOTAS.items()):
        attempts += 1
        if attempts > 2_000_000:
            raise RuntimeError("达到手牌尝试上限仍未填满分层配额")
        hand = candidate_hand(rng)
        if hand in seen:
            continue
        seen.add(hand)
        if not recompute_baotou(tuple(Tile(code) for code in hand), 0, 4):
            continue
        valid_hands += 1
        # 每个基础手牌只选择一个摸牌；依确定性顺序寻找仍缺额的题型。
        for draw in possible_draws(hand, rng):
            analyzed_states += 1
            probe = build_case(
                hand=hand,
                draw=draw,
                ordinal=sum(len(values) for values in selected.values()) + 1,
                generator_hash=generator_hash,
                rules_hash=rules_hash,
            )
            dtype = probe["decision_type"]
            if dtype in QUOTAS and len(selected[dtype]) < QUOTAS[dtype]:
                selected[dtype].append(probe)
                break
    cases = [case for dtype in sorted(selected) for case in selected[dtype]]
    # 重编号只取决于最终类型与手牌/摸牌内容，避免搜索发现顺序进入 case 身份。
    cases.sort(key=lambda case: (
        case["decision_type"],
        case["reachability_witness"]["hand13"],
        case["reachability_witness"]["draw"],
    ))
    for ordinal, case in enumerate(cases, 1):
        old_id = case["case_id"]
        new_id = "r18-p4s-{0:03d}".format(ordinal)
        if old_id != new_id:
            # request 内含身份，必须以最终身份重新生成，不能只改外层标签。
            witness = case["reachability_witness"]
            case = build_case(
                hand=tuple(witness["hand13"]),
                draw=witness["draw"],
                ordinal=ordinal,
                generator_hash=generator_hash,
                rules_hash=rules_hash,
            )
            cases[ordinal - 1] = case
    for dtype in QUOTAS:
        group = [case for case in cases if case["decision_type"] == dtype]
        hidden = {
            case["case_id"]
            for case in sorted(
                group,
                key=lambda item: digest_value((
                    GENERATOR_SEED,
                    item["reachability_witness_sha256"],
                )),
            )[: HIDDEN_QUOTAS[dtype]]
        }
        for case in group:
            case["split"] = "hidden" if case["case_id"] in hidden else "development"
    counts = Counter((case["split"], case["decision_type"]) for case in cases)
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p4-shape-bank-manifest/1",
        "generator_seed": GENERATOR_SEED,
        "generator_sha256": generator_hash,
        "rules_hash": rules_hash,
        "oracle_version": ORACLE_VERSION,
        "cases": len(cases),
        "unique_hand13": len({tuple(case["reachability_witness"]["hand13"]) for case in cases}),
        "old_bank_overlap": sum(
            tuple(case["reachability_witness"]["hand13"]) in excluded for case in cases
        ),
        "quotas": QUOTAS,
        "hidden_quotas": HIDDEN_QUOTAS,
        "generation_work": {
            "hand_attempts": attempts,
            "valid_baotou_hands": valid_hands,
            "analyzed_hand_draw_states": analyzed_states,
        },
        "counts": [
            {"split": split, "decision_type": dtype, "count": count}
            for (split, dtype), count in sorted(counts.items())
        ],
        "split_rule": "每题型按(seed, reachability_witness_sha256)哈希排序取预登记hidden配额；候选评分前冻结",
        "scope": "四财神、庄家起手后首次摸牌、无副露无牌河；跨64个唯一13张手牌",
        "limitations": [
            "仍是下一次本人摸牌立即胡的条件代理；配对反事实另行校准",
            "本批不覆盖杠、鸣牌、赛事处境或三财神",
            "hidden 文件只允许冻结候选后的一次性准入程序读取",
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
        "generation_work": {
            "hand_attempts": attempts,
            "valid_baotou_hands": valid_hands,
            "analyzed_hand_draw_states": analyzed_states,
        },
    }, ensure_ascii=False, indent=2))


def load_development() -> tuple[list[OpportunityCapabilityCase], list[dict[str, Any]]]:
    """只读取开发题；本函数没有 hidden 路径参数。"""

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
        metadata.append({"decision_type": row["decision_type"]})
    return cases, metadata


async def evaluate_development() -> tuple[list[Any], list[dict[str, Any]]]:
    cases, metadata = load_development()
    source = CANDIDATE.read_text(encoding="utf-8")
    candidate = ActionValuePolicy(ActionValueScorer("r18-P4-shape-development", source))
    baseline = ComparableHeuristicPolicyV2()
    rows = [
        await evaluate_pair(candidate, baseline, case, bank.budget) for case in cases
    ]
    return rows, metadata


def score_development() -> None:
    """冻结后评价 P4 的跨手牌开发泛化；隐藏文件保持未读取。"""

    target = _project_file(_PROJECT_ROOT, OUT / "development-score.json")
    if target.exists():
        raise SystemExit("开发评分已存在；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest.get("candidate_evaluated_during_generation") is not False:
        raise ValueError("题库生成与候选评价边界不成立")
    rows, metadata = asyncio.run(evaluate_development())
    summary = asdict(summarize_family(
        rows, family="multi_wealth_baotou", split="development"
    ))
    strata = {}
    for dtype in QUOTAS:
        selected = [
            row for row, meta in zip(rows, metadata) if meta["decision_type"] == dtype
        ]
        strata[dtype] = {
            "cases": len(selected),
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
            "candidate_optimal": sum(
                row.candidate.chosen_action_key in row.candidate.optimal_action_keys
                for row in selected
            ),
            "baseline_optimal": sum(
                row.baseline.chosen_action_key in row.baseline.optimal_action_keys
                for row in selected
            ),
            "capability_gain_sum": sum(
                float(row.capability_gain or 0.0) for row in selected
            ),
        }
    result = {
        "schema": "r18-p4-shape-development-score/1",
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "split": "development",
        "hidden_read": False,
        "summary": summary,
        "strata": strata,
        "changed_count": sum(
            row.candidate.chosen_action_key != row.baseline.chosen_action_key for row in rows
        ),
        "improved_count": sum(
            row.capability_gain is not None and row.capability_gain > 0 for row in rows
        ),
        "regressed_count": sum(
            row.capability_gain is not None and row.capability_gain < 0 for row in rows
        ),
        "hidden_evaluation_started": False,
    }
    write_json(target, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("generate", "score-development"))
    args = parser.parse_args()
    globals()[args.operation.replace("-", "_")]()
