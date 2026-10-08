#!/usr/bin/env python3
"""G0.5：只读官方赛后牌谱，重建强手本人摸牌窗的可见合法动作。"""

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

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROOT / "review/baotou-anatomy-20260925"), HERE):
    sys.path.insert(0, str(path))

import anatomy_lib as anatomy  # noqa: E402
import c31_action_layer_gap as c31  # noqa: E402
from extract_room_scores import load_rooms  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402
from hangma_bot.kernel.actions import WindowKey, WindowPhase  # noqa: E402
from hangma_bot.kernel.observation import CompetitionContext  # noqa: E402

DEFAULT_ROOM = "a_f8ddc4c3bd9b"
XUANWU = "u_380da525337c"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-strong-draw-feasibility-10games-01')
SKIP_EVENT_TYPES = {"pass", "timeout"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def public_observation(
    before: dict[str, Any], draw: dict[str, Any], *, game_id: str,
    round_no: int, dealer: int, scores: list[int], hand_override: list[Counter] | None = None,
) -> PlayerObservation:
    """只取本座暗牌与其余座位手牌张数；赛后他家牌码不得进入观察。"""
    seat = int(draw["seat"])
    code = str(draw["tile"])
    hands = before["hands"] if hand_override is None else hand_override
    if before["baotou"][seat] is None:
        raise ValueError("摸前爆头状态未知")
    my_before = c31._tiles(hands[seat])
    baotou = c31.progression.baotou_after_draw(
        bool(before["baotou"][seat]), my_before,
        int(before["melds_count"][seat]), Tile(code),
    )
    counts = [sum(hand.values()) for hand in hands]
    counts[seat] += 1
    rivers = before["rivers"]
    melds = before["melds"]
    meld_tiles = sum(len(group["tiles"]) for row in melds for group in row)
    wall_remaining = c31.WALL_TOTAL - sum(counts) - sum(map(len, rivers)) - meld_tiles
    if not 0 <= wall_remaining <= c31.WALL_TOTAL:
        raise ValueError("重建墙余不在物理范围")
    owner = before["owner"]
    # C31 的响应窗重建器会累积杠链，但不在普通弃牌后清零；这里只纳入
    # 本座最近一次弃牌不是白板的窗口，按 progression.chain_after_discard
    # 可严格推出摸前链已断。白板飘牌链另列为待补覆盖，不猜零。
    own_river = before["rivers"][seat]
    if own_river and own_river[-1] == c31.WEALTH:
        raise ValueError("最近一次本人弃白后的链状态待单独重建")
    chain = 0
    return PlayerObservation(
        game_id=game_id, seat=seat, round_no=round_no,
        snapshot_seq=int(draw["seq"]), phase="draw", dealer_seat=dealer,
        # 官方已证实摸牌窗口把 drawn_tile 同时附在 my_hand 末尾；
        # HangmaRules 会归一化该重复实例，保持与生产 DTO 的形态一致。
        turn_seat=seat, responding_seats=(), my_hand=my_before + (Tile(code),),
        drawn_tile=Tile(code),
        discards=tuple(tuple(Tile(tile) for tile in river) for river in rivers),
        melds=tuple(tuple(c31.PublicMeld(
            seat=index, kind=group["kind"],
            tiles=tuple(Tile(tile) for tile in group["tiles"]),
            # 官方生产快照在这些赛后房未保留副露供牌座位；不用赛后
            # 事件里虽可推导但线上观察未提供的 from 信息。
            from_seat=None,
        ) for group in melds[index]) for index in range(4)),
        hand_counts=tuple(counts),
        # 官方摸牌快照不携带上一个响应窗的 last_discard。
        last_discard=None,
        remaining_tile_count=wall_remaining, scores=tuple(scores),
        rule_state=RulePublicState(
            wealth_god=Tile(c31.WEALTH), baotou=bool(baotou),
            chain_count=chain, catch_play=owner is not None,
            catch_play_owner_seat=owner,
        ),
        public_history=(), chain_piao=0,
        gang_draw=None,
    )


def analysis_row(
    observation: PlayerObservation, discard: dict[str, Any], scorer: ActionValueScorer,
) -> dict[str, Any]:
    """生产规则与冻结父代同窗评分；只存当前可见事实和真实动作。"""
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    actual = "discard:" + str(discard["tile"])
    legal = {candidate.action_key for candidate in rules.legal_candidates}
    if actual not in legal:
        raise ValueError("官方弃牌不在规则候选：" + actual)
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="g05-official-replay", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        ),
        rules=rules, decision_id="g05:" + str(observation.snapshot_seq),
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(
            game_id=observation.game_id, round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=WindowPhase.DRAW, seat=observation.seat,
        ), rejected_attempts=(),
    )
    view = build_scoring_view(request, value_limits=c31.VALUE_LIMITS)
    scored = scorer.score(view)
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError("冻结父代评分失败：" + scored.status + ":" + str(scored.reason))
    ordered = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    top = ordered[0].action_key
    chosen_score = next(item.score for item in ordered if item.action_key == actual)
    return {
        "schema": "g05-strong-draw-window/1",
        "game_id": observation.game_id, "round_no": observation.round_no,
        "draw_seq": observation.snapshot_seq, "seat": observation.seat,
        "dealer_seat": observation.dealer_seat,
        "remaining_tile_count": observation.remaining_tile_count,
        "actual_action": actual, "parent_top_action": top,
        "parent_agrees": actual == top,
        "parent_score_gap_top_minus_actual": ordered[0].score - chosen_score,
        "legal_candidate_count": len(legal),
        "legal_action_keys": sorted(legal),
        "legal_action_types": dict(sorted(Counter(key.split(":", 1)[0] for key in legal).items())),
        "observation": decision_request_to_json(request)["observation"],
        "my_hand_count": len(observation.my_hand),
        "drawn_tile": observation.drawn_tile.code,
        "own_meld_count": len(observation.melds[observation.seat]),
        "catch_play": observation.rule_state.catch_play,
        "baotou": observation.rule_state.baotou,
    }


def clean_draw_windows(
    events: list[dict[str, Any]], snapshots: dict[int, dict[str, Any]],
    target_seat: int,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]], Counter]:
    """只取普通摸牌后首个实质事件即本人弃牌、且摸前快照未被鸣改写的窗口。"""
    ordered_snaps = sorted(snapshots)
    counts = Counter()
    selected = []
    for index, draw in enumerate(events):
        if draw.get("type") != "tile_drawn" or draw.get("seat") != target_seat:
            continue
        counts["target_draw_events"] += 1
        next_event = next((event for event in events[index + 1:]
                           if event.get("type") not in SKIP_EVENT_TYPES), None)
        if next_event is None or next_event.get("type") != "tile_discarded" or next_event.get("seat") != target_seat:
            counts["excluded_non_discard_successor"] += 1
            continue
        prior = [seq for seq in ordered_snaps if seq < int(draw["seq"])]
        if not prior:
            counts["excluded_no_prior_discard"] += 1
            continue
        before = snapshots[prior[-1]]
        # 只允许前一张公开弃牌之后经过过牌/超时再摸牌；吃碰杠改变了
        # 手牌或副露时不能把旧快照假作当前状态。
        intervening = [event for event in events
                       if int(before["seq"]) < int(event["seq"]) < int(draw["seq"])
                       and event.get("type") not in SKIP_EVENT_TYPES]
        if intervening:
            counts["excluded_intervening_action"] += 1
            continue
        post = snapshots.get(int(next_event["seq"]))
        if post is None:
            counts["excluded_no_post_discard_snapshot"] += 1
            continue
        if before["baotou"][target_seat] is None:
            counts["excluded_unknown_baotou"] += 1
            continue
        if before["rivers"][target_seat] and before["rivers"][target_seat][-1] == c31.WEALTH:
            counts["excluded_recent_white_chain_uncertain"] += 1
            continue
        before_hand = Counter(before["hands"][target_seat])
        expected = before_hand + Counter([draw["tile"]])
        expected[next_event["tile"]] -= 1
        expected += Counter()
        if expected != Counter(post["hands"][target_seat]):
            counts["excluded_hand_continuity_mismatch"] += 1
            continue
        if (before["melds"] != post["melds"]
                or before["rivers"][target_seat] + [next_event["tile"]]
                != post["rivers"][target_seat]):
            counts["excluded_public_continuity_mismatch"] += 1
            continue
        selected.append((before, draw, next_event))
        counts["clean_windows"] += 1
    return selected, counts


def run(room_id: str, game_limit: int, target_user: str, out: Path) -> None:
    """只读固定房牌谱；对每个纳入窗口做可见信息及合法动作对账。"""
    source_games = []
    for _, room, _, game_id, doc in load_rooms():
        if room != room_id:
            continue
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if target_user not in seats:
            continue
        source_games.append((game_id, doc, seats.index(target_user)))
    source_games.sort(key=lambda item: item[0])
    if not source_games:
        raise ValueError("固定房中无目标强手官方牌谱")
    selected_games = source_games[:game_limit]
    scorer = ActionValueScorer("g05-official-strong-draw", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    counts = Counter()
    windows = []
    failures = []
    perturb_checked = False
    for game_id, doc, seat in selected_games:
        scores = [0, 0, 0, 0]
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            counts["rounds"] += 1
            if start_hands is None:
                counts["excluded_missing_start_hands_rounds"] += 1
                continue
            dealer = c31.round_metadata(doc).get(round_no, {}).get("dealer")
            if dealer is None:
                counts["excluded_unknown_dealer_rounds"] += 1
                continue
            snapshots = c31.reconstruct(events, start_hands, scores, dealer)
            selected, per_round = clean_draw_windows(events, snapshots, seat)
            counts.update(per_round)
            for before, draw, discard in selected:
                try:
                    observation = public_observation(
                        before, draw, game_id=game_id, round_no=round_no,
                        dealer=dealer, scores=scores,
                    )
                    if not perturb_checked:
                        modified = [Counter(hand) for hand in before["hands"]]
                        other = (seat + 1) % 4
                        modified[other] = Counter({"1w": sum(modified[other].values())})
                        negative = public_observation(
                            before, draw, game_id=game_id, round_no=round_no,
                            dealer=dealer, scores=scores, hand_override=modified,
                        )
                        if negative != observation:
                            raise ValueError("他家暗牌扰动改变了强手可见观察")
                        perturb_checked = True
                    row = analysis_row(observation, discard, scorer)
                    row["room_id"] = room_id
                    windows.append(row)
                    counts["legal_verified_windows"] += 1
                except Exception as exc:  # noqa: BLE001
                    failures.append({
                        "game_id": game_id, "round_no": round_no,
                        "draw_seq": draw["seq"], "discard_seq": discard["seq"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
                    counts["analysis_failures"] += 1
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                counts["excluded_no_round_ended"] += 1
                continue
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4:
                counts["excluded_invalid_round_scores"] += 1
                continue
            scores = [int(a) + int(b) for a, b in zip(scores, delta)]
    if not perturb_checked:
        raise ValueError("没有可验证的信息权限负控窗口")
    if out.exists():
        raise FileExistsError("结果目录已存在，拒绝覆盖")
    out.mkdir(parents=True)
    save(out / "result.json", {
        "schema": "g05-strong-draw-reconstruction-pilot/1",
        "script_sha256": digest(Path(__file__)),
        "c31_reconstruction_sha256": digest(Path(c31.__file__)),
        "anatomy_reconstruction_sha256": digest(Path(anatomy.__file__)),
        "parent_source_sha256": hashlib.sha256(
            c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest(),
        "room_id": room_id, "target_user_id": target_user,
        "selected_games": [game_id for game_id, _, _ in selected_games],
        "counts": dict(sorted(counts.items())),
        "failures": failures, "other_hidden_hand_perturbation_passed": perturb_checked,
        "outcome_labels_opened": False,
        "parent_agreement": sum(row["parent_agrees"] for row in windows),
        "parent_disagreement": sum(not row["parent_agrees"] for row in windows),
    })
    save(out / "windows.json", {"schema": "g05-strong-draw-windows/1", "windows": windows})
    print(json.dumps({"status": "DONE", "games": len(selected_games),
                      "counts": dict(sorted(counts.items())),
                      "parent_disagreement": sum(not row["parent_agrees"] for row in windows)},
                     ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", default=DEFAULT_ROOM)
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--target-user", default=XUANWU)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    if args.games <= 0:
        raise SystemExit("--games 必须为正数")
    run(args.room, args.games, args.target_user, args.out)


if __name__ == "__main__":
    main()
