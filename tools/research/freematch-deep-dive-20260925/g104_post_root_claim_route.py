#!/usr/bin/env python3
"""G104：从 G103 父代根后的全部官方吃碰杠，核对生产规则后继路线。"""

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
import copy
import gzip
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g05_strong_draw_reconstruction as g05
import g69_route_chain_analysis as g69
import g76_confirmed_response_atlas as g76
import g103_official_route_horizon as g103


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g103-official-route-horizon-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G104-POST-ROOT-CLAIM-ROUTE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g104-post-root-claim-route-20260928')
SKIP = g05.SKIP_EVENT_TYPES


def sha(path: Path) -> str:
    """冻结输入与审计程序的原始字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_material(events: list[dict], index: int) -> dict | None:
    """从动作之后取得下一个非过牌／超时事件。"""
    return next((event for event in events[index + 1:]
                 if event["type"] not in SKIP), None)


def prior_material(events: list[dict], index: int) -> dict | None:
    """从动作之前取得上一个非过牌／超时事件。"""
    return next((event for event in reversed(events[:index])
                 if event["type"] not in SKIP), None)


def round_contexts(doc: dict) -> dict[int, tuple[list[dict], dict[int, dict]]]:
    """逐局按官方零和分数更新当前可见比分，保存弃牌后快照。"""
    context = {}
    scores = [0, 0, 0, 0]
    metadata = c31.round_metadata(doc)
    for round_no, events, start_hands in g05.anatomy.round_blocks(doc):
        if start_hands is None or round_no not in metadata:
            raise ValueError("G104 官方单局起手或庄位缺失")
        snaps = c31.reconstruct(events, start_hands, scores, metadata[round_no]["dealer"])
        if round_no in context:
            raise ValueError("G104 同一桌单局重复")
        context[round_no] = (events, snaps)
        ended = [event for event in events if event["type"] == "round_ended"]
        if len(ended) != 1 or len((ended[0].get("data") or {}).get("scores") or []) != 4:
            raise ValueError("G104 官方终局四座分数缺失")
        scores = [a + b for a, b in zip(scores, ended[0]["data"]["scores"])]
    return context


def perturb_other_hand(snap: dict, seat: int, phase: str,
                       game_id: str, round_no: int, observation: object) -> bool:
    """他家暗牌内容变化且张数不变，不得改变本座生产观察。"""
    altered = copy.deepcopy(snap)
    other = (seat + 1) % 4
    length = sum(altered["hands"][other].values())
    altered["hands"][other] = Counter({"1w": length})
    rebuilt = c31.build_observation(altered, seat, phase, game_id, round_no)
    return rebuilt == observation


def analyze_claim(*, game_id: str, round_no: int, room: str, seat: int,
                  events: list[dict], snaps: dict[int, dict], index: int,
                  checked_rooms: set[str]) -> dict:
    """官方吃碰 → 生产合法鸣牌 → 实际即时跟打 → 下一次胡牌入口。"""
    claim = events[index]
    prior = prior_material(events, index)
    if prior is None or prior["type"] != "tile_discarded" or prior["seat"] == seat:
        raise ValueError("G104 吃碰前不是他家触发弃牌")
    snap = snaps.get(prior["seq"])
    if snap is None or snap["claim_seat"] != seat or snap["claim_kind"] != claim["type"]:
        raise ValueError("G104 官方已接受鸣牌不在触发弃牌快照")
    if snap["baotou"][seat] is None:
        raise ValueError("G104 鸣牌前本人爆头状态未知")
    phase = "response_peng" if claim["type"] == "peng" else "response_chi"
    observation = c31.build_observation(snap, seat, phase, game_id, round_no)
    if room not in checked_rooms:
        if not perturb_other_hand(snap, seat, phase, game_id, round_no, observation):
            raise ValueError("G104 他家暗牌扰动改变本人可见观察")
        checked_rooms.add(room)
    analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    accepted = g76.action_key(claim)
    candidate = next((item for item in analysis.legal_candidates
                      if item.action_key == accepted), None)
    if candidate is None:
        raise ValueError("G104 官方吃碰不在生产规则合法动作中")
    post = c31.post_claim_observation(observation, candidate.action)
    if post is None:
        raise ValueError("G104 鸣后公开观察无法构建")
    post_analysis = c31.RULES.analyze(post, value_limits=c31.VALUE_LIMITS)
    following = next_material(events, index)
    if following is None or following["type"] != "tile_discarded" or following["seat"] != seat:
        raise ValueError("G104 吃碰后下一实质事件不是本人即时弃牌")
    actual = "discard:" + following["tile"]
    discard = next((item for item in post_analysis.legal_candidates
                    if item.action_key == actual), None)
    if discard is None:
        raise ValueError("G104 官方吃碰后即时弃牌不在生产合法集合")
    after = snaps.get(following["seq"])
    if after is None:
        raise ValueError("G104 鸣后实际跟打没有弃牌后快照")
    expected = Counter(tile.code for tile in post.my_hand)
    expected[following["tile"]] -= 1
    expected += Counter()
    if expected != after["hands"][seat]:
        raise ValueError("G104 鸣后本人暗牌前后不连续")
    facts = g69.route_facts(discard, seat)
    if facts is None:
        raise ValueError("G104 鸣后弃牌生产分值事实不完整")
    return {
        "schema": "g104-post-root-claim-row/1", "status": "verified",
        "room": room, "game_id": game_id, "round_no": round_no,
        "claim_seq": claim["seq"], "claim_kind": claim["type"],
        "trigger_discard_seq": prior["seq"], "accepted_action": accepted,
        "followup_discard_seq": following["seq"], "followup_action": actual,
        "seat": seat, "entry": facts,
    }


def analyze_gang(*, game_id: str, round_no: int, room: str, seat: int,
                 events: list[dict], index: int) -> dict:
    """杠补牌按官方事件事实单列；不伪造生产普通摸打路线。"""
    gang = events[index]
    replenish = next_material(events, index)
    if (replenish is None or replenish["type"] != "tile_drawn" or
            replenish["seat"] != seat or
            (replenish.get("data") or {}).get("gang_replenish") is not True):
        raise ValueError("G104 杠后没有官方本人补牌事件")
    following_index = next(i for i, event in enumerate(events) if event["seq"] == replenish["seq"])
    following = next_material(events, following_index)
    if following is None:
        raise ValueError("G104 杠补牌后无后续实质事件")
    immediate_win = (following["type"] == "round_ended" and
                     following["seat"] == seat and not (following.get("data") or {}).get("draw"))
    return {
        "schema": "g104-post-root-gang-row/1", "status": "replenish_verified",
        "room": room, "game_id": game_id, "round_no": round_no,
        "claim_seq": gang["seq"], "claim_kind": "gang",
        "gang_kind": (gang.get("data") or {}).get("kind"),
        "replenish_seq": replenish["seq"], "next_type": following["type"],
        "immediate_win": immediate_win,
        "immediate_fan": (following.get("data") or {}).get("fan") if immediate_win else None,
        "seat": seat,
        "boundary": "杠后补牌不是普通自摸；生产条件胡路线尚未在本量具重建。",
    }


def main() -> None:
    """全量冻结父代根后 60 个吃碰杠事件，逐个保存可见性与未知。"""
    if OUT.exists():
        raise FileExistsError("G104 证据目录已有，拒绝覆盖")
    g103_result = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if g103_result["root_count"] != 170 or g103_result["counts"].get("future_claims") != 60:
        raise ValueError("G104 G103 冻结行动链入口漂移")
    roots = [json.loads(line) for line in gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"), "rt", encoding="utf-8")]
    games, digests = g103.official_games(g103.selected_roots())
    if digests != g103_result["official_game_canonical_sha256"]:
        raise ValueError("G104 官方事件原文与 G103 来源摘要不一致")
    contexts = {}
    rows = []
    checked_rooms: set[str] = set()
    counts = Counter()
    by_hand: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for root in roots:
        room, game_id, round_no, _ = root["key"]
        if game_id not in contexts:
            contexts[game_id] = round_contexts(games[game_id])
        events, snaps = contexts[game_id][round_no]
        claim_indices = [i for i, event in enumerate(events)
                         if (root["root_discard_seq"] < event["seq"] < root["round_end_seq"]
                             and event["seat"] == root["seat"]
                             and event["type"] in ("chi", "peng", "gang"))]
        if len(claim_indices) != root["future_own_claim_count"]:
            raise ValueError("G104 官方鸣牌次数与 G103 逐局计数不等")
        for index in claim_indices:
            event = events[index]
            counts["target/" + event["type"]] += 1
            try:
                if event["type"] == "gang":
                    row = analyze_gang(game_id=game_id, round_no=round_no, room=room,
                                       seat=root["seat"], events=events, index=index)
                else:
                    row = analyze_claim(game_id=game_id, round_no=round_no, room=room,
                                        seat=root["seat"], events=events, snaps=snaps,
                                        index=index, checked_rooms=checked_rooms)
                counts["verified/" + event["type"]] += 1
                if row["status"] == "verified":
                    counts["entry_any"] += row["entry"]["any_capacity"] > 0
                    counts["entry_plain"] += row["entry"]["plain_capacity"] > 0
                    counts["entry_high"] += row["entry"]["high_capacity"] > 0
                else:
                    counts["gang_immediate_win"] += row["immediate_win"]
            except (ValueError, TypeError, KeyError) as exc:
                reason = type(exc).__name__ + ": " + str(exc)[:160]
                row = {"schema": "g104-unavailable-row/1", "status": "unavailable",
                       "room": room, "game_id": game_id, "round_no": round_no,
                       "claim_seq": event["seq"], "claim_kind": event["type"],
                       "reason": reason}
                counts["unavailable/" + event["type"]] += 1
                counts["reason/" + reason] += 1
            rows.append(row)
            by_hand[(game_id, round_no)].append(row)
    if len(rows) != 60 or sum(counts["target/" + kind] for kind in ("chi", "peng", "gang")) != 60:
        raise ValueError("G104 全量鸣牌数未对齐")
    recovered = []
    for root in roots:
        if not (root["outcome"] == "self_win" and
                type(root["terminal_fan"]) is int and root["terminal_fan"] >= 2 and
                root["first_entry_ordinal"]["high"] is None):
            continue
        key = (root["key"][1], root["key"][2])
        claims = by_hand.get(key, [])
        if not claims:
            raise ValueError("G104 G103 未覆盖高番实胡局无任何本人吃碰杠")
        recovered.append({"key": root["key"],
                          "claim_types": [row["claim_kind"] for row in claims],
                          "post_claim_high_entry": any(
                              row.get("status") == "verified" and
                              row["entry"]["high_capacity"] > 0 for row in claims),
                          "gang_immediate_win": any(row.get("immediate_win") is True for row in claims)})
    if len(recovered) != 4:
        raise ValueError("G104 G103 四个未覆盖高番实胡局漂移")
    result = {
        "schema": "g104-post-root-claim-route/1", "exploratory": True,
        "outcome_labels_opened": True, "root_hands": 170, "claim_events": len(rows),
        "counts": dict(sorted(counts.items())),
        "rooms_with_chi_peng": len({row["room"] for row in rows if row["claim_kind"] in ("chi", "peng")}),
        "rooms_with_hidden_perturbation_passed": sorted(checked_rooms),
        "previously_missing_high_wins": recovered,
        "input_sha256": {"g103_result": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
                         "g103_rows": sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
                         "prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "c31_reconstruction": sha(_project_file(_PROJECT_ROOT, HERE / "c31_action_layer_gap.py")),
                         "g69_route": sha(_project_file(_PROJECT_ROOT, HERE / "g69_route_chain_analysis.py"))},
        "boundary": "只读父代已发生吃碰杠；杠补牌仅核事件，未建条件后继收益；不能证明另一弃牌收益。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).write_bytes(gzip.compress(body.encode("utf-8"), compresslevel=9, mtime=0))
    print(json.dumps({"claim_events": len(rows), "counts": result["counts"],
                      "recovered": recovered}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
