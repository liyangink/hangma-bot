#!/usr/bin/env python3
"""G184：官方大牌榜前五手的可见状态重判；不伪称反事实复赛。"""

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

import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.interface import WinDescription
from hangma_bot.hangma.settlement import infer_piao_count
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import (
    CompetitionContext, PlayerObservation, PublicDiscard, PublicEvent,
    PublicMeld, RulePublicState,
)
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SOURCE, R18_INTEGRATED_POSITIVE_V2_SHA256,
)

import c31_action_layer_gap as c31


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g184-classic-highhand-20260928')
SOURCE_FILES = tuple(_project_file(_PROJECT_ROOT, OUT / f"rank{rank}-round.json") for rank in range(1, 17))
KIND_MAP = {"an": "concealed", "ming": "exposed", "bu": "added"}


def sha(path: Path) -> str:
    """绑定官方复盘原文，不保存会话 Cookie。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_events(frames: list[dict], stop: int) -> tuple[PublicEvent, ...]:
    """仅取当前帧之前已公开的事件；他家暗手不进入策略观察。"""

    result = []
    for frame in frames[1:stop + 1]:
        event = frame.get("ev") or {}
        if not event:
            continue
        data = event.get("data") or {}
        code = event.get("tile") or ""
        result.append(PublicEvent(
            seq=int(event["seq"]), kind=event["type"], seat=event.get("seat"),
            tiles=(Tile(code),) if code else (),
            occurred_at_unix_sec=event.get("ts"),
            detail_kind=data.get("kind"),
            catch_play=data.get("catch_play"),
            gang_replenish=data.get("gang_replenish"),
            response_window=data.get("window"),
        ))
    return tuple(result)


def observation(doc: dict, before_index: int, seat: int) -> PlayerObservation:
    """从全知赛后帧只投影该座位依法可见字段，链飘用生产规则推断。"""

    frames = doc["frames"]
    frame = frames[before_index]
    snap = frame["snapshot"]
    past = public_events(frames, before_index)
    god = snap["god"]
    chain_count = int(god["chain_count"][seat])
    piao = infer_piao_count(past, seat, chain_count, snap["seq"])
    if piao is None:
        raise ValueError("官方公开事件不足以核当前链内飘次数")
    last_event = next((event for event in reversed(past)
                       if event.kind == "tile_discarded"), None)
    last = (PublicDiscard(last_event.seat, last_event.tiles[0], last_event.seq)
            if last_event is not None and last_event.seat is not None else None)
    last_code = snap.get("last_discard")
    if last_code not in (None, "", "0w") and last is not None and last.tile.code != last_code:
        raise ValueError("复盘快照与公开末弃牌不一致")
    owner = next((event.seat for event in reversed(past)
                  if event.kind == "tile_discarded" and event.tiles
                  and event.tiles[0].code == "白" and event.catch_play), None)
    if not god["catch_play"]:
        owner = None
    drawn = snap.get("drawn_tile") or None
    current = frame.get("ev") or {}
    current_data = current.get("data") or {}
    return PlayerObservation(
        game_id=doc["game_id"], seat=seat, round_no=int(doc["round_no"]),
        snapshot_seq=int(snap["seq"]), phase=snap["phase"],
        dealer_seat=int(snap["dealer"]), turn_seat=int(snap["turn"]),
        responding_seats=tuple(snap.get("responding_seats") or ()),
        my_hand=tuple(Tile(code) for code in snap["hands"][seat]),
        drawn_tile=Tile(drawn) if drawn else None,
        discards=tuple(tuple(Tile(code) for code in river)
                       for river in snap["discards"]),
        melds=tuple(tuple(PublicMeld(
            seat=index, kind=meld["kind"],
            tiles=tuple(Tile(code) for code in meld["tiles"]),
            from_seat=meld.get("from_seat"))
            for meld in row) for index, row in enumerate(snap["melds"])),
        hand_counts=tuple(len(hand) for hand in snap["hands"]),
        last_discard=last, remaining_tile_count=snap.get("wall_remaining"),
        scores=tuple(snap["scores"]),
        rule_state=RulePublicState(
            wealth_god=Tile("白"), baotou=bool(god["baotou"][seat]),
            chain_count=chain_count, catch_play=bool(god["catch_play"]),
            catch_play_owner_seat=owner),
        public_history=past, consumed_seq=int(snap["seq"]),
        history_complete=bool(past), chain_piao=piao,
        gang_draw=current_data.get("gang_replenish"),
    )


def actual_key(event: dict) -> str | None:
    """只比较赢家已确认的主动弃、吃、碰、杠和胡；不猜 timeout 意图。"""

    kind = event.get("type")
    if kind == "tile_discarded":
        return "discard:" + event["tile"]
    if kind == "peng":
        return "peng:" + event["tile"]
    if kind == "chi":
        data = event.get("data") or {}
        tiles = data.get("tiles") or ()
        if len(tiles) != 3:
            raise ValueError("官方吃事件缺完整三张牌")
        return "chi:" + ",".join(sorted(tiles, key=CANONICAL_TILE_INDEX.__getitem__))
    if kind == "gang":
        data = event.get("data") or {}
        gang_kind = KIND_MAP.get(data.get("kind"))
        if gang_kind is None:
            raise ValueError("未知官方杠种")
        return "gang:" + gang_kind + ":" + event["tile"]
    if kind == "round_ended" and not (event.get("data") or {}).get("draw"):
        return "hu"
    return None


def request_for(value: PlayerObservation, rank: int) -> DecisionRequest:
    """用生产规则和同一评分视图重建行动请求；赛事缓存排序留空。"""

    rules = c31.RULES.analyze(value, value_limits=c31.VALUE_LIMITS)
    phase = WindowPhase(value.phase)
    return DecisionRequest(
        observation=value,
        competition=CompetitionContext(
            tournament_id="g184-classic-shadow", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0),
        rules=rules, decision_id=f"g184-rank{rank}-{value.snapshot_seq}",
        trigger_seq=value.snapshot_seq,
        window_key=WindowKey(value.game_id, value.round_no,
                             value.snapshot_seq, phase, value.seat),
        rejected_attempts=(),
    )


def run_one(rank: int, leaderboard: dict, scorer: ActionValueScorer) -> dict:
    """每个历史赢家动作只作同窗影子重判；不累计成候选轨迹。"""

    source = SOURCE_FILES[rank - 1]
    doc = json.loads(source.read_text(encoding="utf-8"))
    row = leaderboard["top"][rank - 1]
    final = next((frame["ev"] for frame in reversed(doc["frames"])
                  if (frame.get("ev") or {}).get("type") == "round_ended"), None)
    if final is None:
        raise ValueError("官方复盘缺单局终局事件")
    winner = final["seat"]
    if (doc["game_id"], doc["round_no"], winner,
            final["data"]["fan"], final["data"]["scores"][winner]) != (
                row["game_id"], row["round_no"],
                next(index for index, seat in enumerate(doc["seats"])
                     if seat["user_id"] == row["user_id"]),
                row["fan"], row["score"]):
        raise ValueError("大牌榜与复盘终局身份或结算不一致")
    actions = []
    for index, frame in enumerate(doc["frames"][1:], start=1):
        event = frame.get("ev") or {}
        if event.get("seat") != winner:
            continue
        actual = actual_key(event)
        if actual is None:
            continue
        visible = observation(doc, index - 1, winner)
        request = request_for(visible, rank)
        legal = {candidate.action_key for candidate in request.rules.legal_candidates}
        if actual not in legal:
            raise ValueError(f"rank{rank} seq{event['seq']} 历史赢家动作不在生产合法集合: {actual}")
        scored = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
        if scored.status != "SCORED" or not scored.entries:
            raise ValueError("冻结 R18 未能重算本窗")
        scores = {entry.action_key: entry.score for entry in scored.entries}
        top = min(scores, key=lambda key: (-scores[key], key))
        settlement = (c31.RULES.score(WinDescription(visible, winner))
                      if "hu" in legal else None)
        actions.append({
            "event_seq": event["seq"], "observation_seq": visible.snapshot_seq,
            "phase": visible.phase, "actual": actual, "r18_top": top,
            "r18_score_gap": round(scores[top] - scores[actual], 8),
            "agrees": top == actual, "legal_count": len(legal),
            "white_held": sum(tile.code == "白" for tile in visible.my_hand),
            "baotou": visible.rule_state.baotou,
            "chain_count": visible.rule_state.chain_count,
            "chain_piao": visible.chain_piao,
            "available_hu_fan": settlement.fan if settlement else None,
            "available_hu_self_delta": (
                settlement.score_delta[winner] if settlement else None),
        })
    if not actions or actions[-1]["actual"] != "hu":
        raise ValueError("复盘缺赢家终局动作")
    if (actions[-1]["available_hu_fan"],
            actions[-1]["available_hu_self_delta"]) != (row["fan"], row["score"]):
        raise ValueError("生产规则计算与官方榜单终局番分不一致")
    first = next((item for item in actions if not item["agrees"]), None)
    first_positive_gap = next((item for item in actions
                               if not item["agrees"] and item["r18_score_gap"] > 1e-8), None)
    return {"rank": rank, "name": row["name"], "game_id": doc["game_id"],
            "round_no": doc["round_no"], "winner_seat": winner,
            "initial_white": doc["frames"][0]["snapshot"]["hands"][winner].count("白"),
            "historical_fan": row["fan"], "historical_self_delta": row["score"],
            "winner_actions": len(actions),
            "local_agreements": sum(item["agrees"] for item in actions),
            "first_divergence_seq": first["event_seq"] if first else None,
            "first_divergence_actual": first["actual"] if first else None,
            "first_divergence_r18": first["r18_top"] if first else None,
            "first_positive_gap_seq": (first_positive_gap["event_seq"]
                                       if first_positive_gap else None),
            "actions": actions}


def main() -> None:
    """保存可复算差异和边界；不能从赢家牌谱单独估计继续的期望值。"""

    leaderboard_path = _project_file(_PROJECT_ROOT, OUT / "leaderboard.json")
    leaderboard = json.loads(leaderboard_path.read_text(encoding="utf-8"))
    scorer = ActionValueScorer("g184-r18-shadow", R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = [run_one(rank, leaderboard, scorer) for rank in range(1, 17)]
    result = {
        "schema": "g184-classic-highhand-shadow/1",
        "source_sha256": {path.name: sha(path)
                          for path in (leaderboard_path, *SOURCE_FILES, Path(__file__))},
        "parent_scorer_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "rows": rows,
        "boundary": "官方赢家历史可见状态影子重判；首个异动后不再是同一候选轨迹。"
                    "赢家条件抽样，不能单独给弃胡/飘白净收益或发布分数。",
    }
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                                 sort_keys=True, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(json.dumps({key: row[key] for key in (
            "rank", "game_id", "winner_actions", "local_agreements",
            "first_divergence_seq", "first_divergence_actual", "first_divergence_r18",
            "first_positive_gap_seq")},
            ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
