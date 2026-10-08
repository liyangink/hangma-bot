#!/usr/bin/env python3
"""G67：在冻结自由赛观察上对父代前二弃牌做同一两摸时域的结果盲筛查。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
for directory in (_project_file(_PROJECT_ROOT, ROOT / "src"), HERE, _project_file(_PROJECT_ROOT, ROOT / "review/baotou-anatomy-20260925")):
    sys.path.insert(0, str(directory))

import c31_action_layer_gap as c31  # noqa: E402
import g05_strong_draw_reconstruction as g05  # noqa: E402
import g65_next_draw_survival as g65  # noqa: E402
from g52_shared_horizon import evaluate_root  # noqa: E402
from hangma_bot.application.audit_codec import candidate_value_facts_to_json  # noqa: E402
from hangma_bot.kernel.actions import WindowKey, WindowPhase  # noqa: E402
from hangma_bot.kernel.observation import CompetitionContext  # noqa: E402
from hangma_bot.kernel.serialization import observation_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402

SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g66-survival-transfer-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g67-action-specific-horizon-20260928')
STRATA = tuple((white, survival) for white in ("zero", "positive")
               for survival in ("low", "mid", "high"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row: dict) -> tuple:
    return (row.get("room_id", row.get("room")), row["game_id"],
            row["round_no"], row["draw_seq"], row["seat"])


def select() -> tuple[list[tuple[dict, dict]], dict]:
    """按预登记的当前事实和固定摘要抽样，不读未来标签。"""

    predictions = {}
    with gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "transfer_rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = identity(row)
            if key in predictions:
                raise ValueError("G66 逐窗预测身份重复")
            predictions[key] = {
                "features": row["features"],
                "p": row["prediction"]["enhanced"],
            }
    bins = defaultdict(list)
    observed = set()
    room_dirs = sorted((_project_file(_PROJECT_ROOT, SOURCE / "rooms")).iterdir())
    if len(room_dirs) != 40:
        raise ValueError("G66 40 房冻结母体漂移")
    for room_dir in room_dirs:
        doc = json.loads((room_dir / "windows.json").read_text(encoding="utf-8"))
        for row in doc["windows"]:
            key = identity(row)
            if key in observed or key not in predictions:
                raise ValueError("G66 重建窗与预测身份不一致")
            observed.add(key)
            observed_features = g65.features(row["observation"])
            pred = predictions[key]
            if observed_features != pred["features"]:
                raise ValueError("G66 预测特征不等于当前合法观察")
            p = pred["p"]
            if type(p) is not float or not 0 < p < 1:
                raise ValueError("G66 预测概率越界")
            if row["remaining_tile_count"] <= 20:
                continue
            white = "zero" if observed_features["whites"] == 0 else "positive"
            survival = "low" if p < 0.75 else "mid" if p < 0.90 else "high"
            hash_key = "/".join(map(str, key[:4]))
            bins[(white, survival)].append((hashlib.sha256(hash_key.encode()).hexdigest(), row, pred))
    if observed != set(predictions):
        raise ValueError("G66 预测有未匹配的重建窗")
    result = []
    per_room = Counter()
    for stratum in STRATA:
        for _, row, pred in sorted(bins[stratum], key=lambda item: item[0]):
            room = row["room_id"]
            if per_room[room] >= 3:
                continue
            result.append((row, pred))
            per_room[room] += 1
            if sum(1 for current, _ in result if
                   ("zero" if current["observation"]["my_hand"].count("白") == 0 else "positive",
                    "low" if predictions[identity(current)]["p"] < 0.75 else
                    "mid" if predictions[identity(current)]["p"] < 0.90 else "high") == stratum) >= 12:
                break
    return result, {"eligible_per_stratum": {str(key): len(value) for key, value in bins.items()},
                    "selected_rooms": len(per_room), "selected_per_room": dict(sorted(per_room.items()))}


def request_for(observation):
    """复用生产合法动作和冻结父代的原评分视图。"""

    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="g67-official-replay", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        ),
        rules=rules, decision_id="g67:" + str(observation.snapshot_seq),
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(
            game_id=observation.game_id, round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=WindowPhase.DRAW, seat=observation.seat,
        ), rejected_attempts=(),
    )
    return request


def horizon(root: dict, p: float, mode: str) -> dict:
    """同窗共用 p，仅折扣需要再一次本人摸牌的分支。"""

    capacity = root["first_draw_public_capacity"]
    if capacity <= 0:
        raise ValueError("首次摸牌公开容量非正")
    weighted = second_unconditional = ordinary_progress = 0.0
    for edge in root["edges"]:
        leaf = edge["best_second"][mode]["best_second_hu"]
        if leaf["capacity"] <= 0:
            raise ValueError("第二摸牌公开容量非正")
        first = edge["first_hu_score"] or 0
        second = leaf["mass"] / leaf["capacity"]
        weighted += edge["capacity"] * max(first, p * second)
        second_unconditional += edge["capacity"] * second
        natural = edge["best_second"][mode]["best_natural_progress"]
        ordinary_progress += edge["capacity"] * natural["ordinary_natural_progress_capacity"]
    return {"weighted_two_draw_value": weighted / capacity,
            "unweighted_second_value": second_unconditional / capacity,
            "ordinary_second_progress": ordinary_progress / capacity}


def support(candidate) -> int | None:
    facts = candidate.facts
    if facts is None:
        return None
    return sum(tile.remaining_estimate for tile in facts.standard_useful_tiles)


def process(row: dict, pred: dict, scorer: ActionValueScorer) -> dict:
    observation = observation_from_json(row["observation"])
    request = request_for(observation)
    view = build_scoring_view(request, value_limits=c31.VALUE_LIMITS)
    scored = scorer.score(view)
    if scored.status != "SCORED":
        return {"status": "abstain", "reason": scored.reason}
    ordered = sorted(scored.entries, key=lambda entry: (-entry.score, entry.action_key))
    if ordered[0].action_key != row["parent_top_action"]:
        raise ValueError("G66 冻结父代评分首选漂移")
    if not ordered[0].action_key.startswith("discard:"):
        return {"status": "excluded", "reason": "parent_not_discard"}
    discarded = [entry for entry in ordered if entry.action_key.startswith("discard:")]
    if len(discarded) < 2:
        return {"status": "excluded", "reason": "fewer_than_two_discards"}
    legal = {candidate.action_key: candidate for candidate in request.rules.legal_candidates}
    pair = {}
    for name, entry in zip(("parent", "alternative"), discarded[:2]):
        candidate = legal[entry.action_key]
        if candidate.value_facts is None:
            return {"status": "incomplete", "reason": "no_value_facts"}
        encoded = {"action_key": entry.action_key,
                   "value_facts": candidate_value_facts_to_json(candidate.value_facts)}
        try:
            root = evaluate_root(observation, encoded, c31.RULE_CONFIG)
        except (ValueError, TypeError) as exc:
            return {"status": "incomplete", "reason": type(exc).__name__ + ": " + str(exc)}
        pair[name] = {
            "action": entry.action_key, "score": entry.score,
            "ordinary_shanten": candidate.facts.standard_shanten_after if candidate.facts else None,
            "ordinary_support": support(candidate),
            "first_hu_mass": root["first_hu_mass"],
            "first_hu_value": root["first_hu_mass"] / root["first_draw_public_capacity"],
            "first_capacity": root["first_draw_public_capacity"],
            "root_whites_held": root["root_whites_held"],
            "restricted": horizon(root, pred["p"], "restricted"),
            "unrestricted": horizon(root, pred["p"], "unrestricted"),
        }
    return {"status": "complete", "p": pred["p"], "pair": pair}


def main() -> None:
    if OUT.exists():
        raise SystemExit("G67 结果目录已存在，拒绝覆盖")
    selected, selection = select()
    scorer = ActionValueScorer("g67-r18v2-frozen", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = []
    started = time.perf_counter()
    for window, pred in selected:
        finding = process(window, pred, scorer)
        rows.append({"identity": identity(window), "white_count": pred["features"]["whites"],
                     "wall": pred["features"]["wall"], **finding})
    if len(selected) != 72:
        raise ValueError("G67 预登记六格未各取足 12 窗")
    counts = Counter(row["status"] for row in rows)
    reasons = Counter(row.get("reason") for row in rows if row["status"] != "complete")
    complete = [row for row in rows if row["status"] == "complete"]
    def positive(row, mode):
        a, b = row["pair"]["parent"], row["pair"]["alternative"]
        return b[mode]["weighted_two_draw_value"] > a[mode]["weighted_two_draw_value"] + 1e-9
    reverse_both = [row for row in complete if all(positive(row, mode) for mode in ("restricted", "unrestricted"))]
    protected = [row for row in reverse_both if
                 row["pair"]["alternative"]["ordinary_shanten"] <= row["pair"]["parent"]["ordinary_shanten"]
                 and row["pair"]["alternative"]["ordinary_support"] >= row["pair"]["parent"]["ordinary_support"]]
    distinct = [row for row in protected if
                row["pair"]["alternative"]["first_hu_value"] <= row["pair"]["parent"]["first_hu_value"] + 1e-9
                and any(row["pair"]["alternative"][mode]["unweighted_second_value"] >
                        row["pair"]["parent"][mode]["unweighted_second_value"] + 1e-9
                        for mode in ("restricted", "unrestricted"))]
    outcome = {
        "schema": "g67-action-specific-horizon/1", "outcome_blind": True,
        "program_sha256": digest(Path(__file__)),
        "source_prediction_sha256": digest(_project_file(_PROJECT_ROOT, SOURCE / "transfer_rows.jsonl.gz")),
        "parent_source_sha256": hashlib.sha256(c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest(),
        "selection": selection, "counts": dict(counts), "failure_reasons": dict(reasons),
        "complete_rooms": len({row["identity"][0] for row in complete}),
        "reverse_both_modes": len(reverse_both),
        "reverse_both_rooms": len({row["identity"][0] for row in reverse_both}),
        "reverse_protects_ordinary": len(protected),
        "reverse_protects_ordinary_rooms": len({row["identity"][0] for row in protected}),
        "second_horizon_distinct_from_first_hu": len(distinct),
        "second_horizon_distinct_rooms": len({row["identity"][0] for row in distinct}),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "gate_pass": len(distinct) >= 20 and len({row["identity"][0] for row in distinct}) >= 10
        and len(protected) / max(1, len(reverse_both)) >= .75,
        "boundary": "结果盲两摸条件树；公开容量非墙概率；同窗 p 非动作因果存活概率；非整桌效果。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz"), "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
