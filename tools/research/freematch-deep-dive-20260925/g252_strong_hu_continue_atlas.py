#!/usr/bin/env python3
"""G252：重建强手本人正常摸牌时「合法胡／继续」的结果盲行为母体。

标签只来自本窗口官方已执行动作；继续后的牌墙、终局和其他座位暗牌
均不进入样本特征。已执行胡的官方结算只用于与生产规则交叉核验。
"""

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
import io
import json
from pathlib import Path

import anatomy_lib as anatomy
import c31_action_layer_gap as c31
import g05_strong_draw_reconstruction as g05
from extract_room_scores import load_rooms
from hangma_bot.application.audit_codec import decision_request_to_json
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g252-strong-hu-continue-atlas-20260929')
GANG_KINDS = {"an": "concealed", "bu": "added", "ming": "exposed"}


def sha(path: Path) -> str:
    """读取源文件原始字节摘要，避免旧证据或源码静默变更。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_sha(doc: dict) -> str:
    """牌谱内容摘要；load_rooms 已按 game_id 去重但不返回源路径。"""

    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_new(path: Path, payload: dict) -> None:
    """研究产物只允许首次写入或逐字幂等复跑。"""

    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != body:
        raise ValueError(f"冻结产物漂移：{path}")
    if not path.exists():
        path.write_text(body, encoding="utf-8")


def write_rows(path: Path, rows: list[dict]) -> None:
    """稳定压缩行为行，供后续按房切分训练／验证。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        for row in rows:
            zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n").encode("utf-8"))
    body = raw.getvalue()
    if path.exists() and path.read_bytes() != body:
        raise ValueError(f"逐窗冻结产物漂移：{path}")
    if not path.exists():
        path.write_bytes(body)


def candidate_view(observation, scorer: ActionValueScorer):
    """同一玩家可见观察上以生产规则生成合法动作并用冻结父代评分。"""

    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="g252-official-replay", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        ),
        rules=rules,
        decision_id=f"g252:{observation.game_id}:{observation.round_no}:{observation.snapshot_seq}",
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(
            game_id=observation.game_id, round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=WindowPhase.DRAW, seat=observation.seat,
        ),
        rejected_attempts=(),
    )
    scored = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError(f"冻结父代评分失败：{scored.status} {scored.reason}")
    entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    legal = {candidate.action_key: candidate for candidate in rules.legal_candidates}
    if len(legal) != len(rules.legal_candidates):
        raise ValueError("生产合法动作键重复")
    return request, legal, entries


def make_row(observation, *, peer: str, room: str, action: str,
             source_kind: str, next_seq: int, source_sha: str,
             scorer: ActionValueScorer, official_end: dict | None = None) -> dict:
    """保存全部线上可见特征、当窗胡价和强手已接受动作。"""

    request, legal, entries = candidate_view(observation, scorer)
    hu = legal.get("hu")
    if hu is None or action not in legal:
        raise ValueError(f"本窗不具合法胡／官方动作不合法：{action}")
    immediate = hu.value_facts.immediate_settlement
    if immediate is None:
        raise ValueError("合法胡没有完整生产结算")
    delta = list(immediate.score_delta)
    if len(delta) != 4 or sum(delta) != 0:
        raise ValueError("生产胡结算四座分不守恒")
    if official_end is not None:
        data = official_end.get("data") or {}
        if (official_end.get("seat") != observation.seat
                or data.get("draw") is not False
                or data.get("fan") != immediate.fan
                or data.get("scores") != delta):
            raise ValueError("官方已接受胡与生产番分／四座结算不一致")
    scores = {entry.action_key: entry.score for entry in entries}
    return {
        "schema": "g252-strong-hu-continue-window/1",
        "peer": peer, "room_id": room,
        "game_id": observation.game_id, "round_no": observation.round_no,
        "seat": observation.seat, "draw_seq": observation.snapshot_seq,
        "accepted_event_seq": next_seq, "source_kind": source_kind,
        "source_payload_sha256": source_sha,
        "label": "hu" if action == "hu" else "continue",
        "actual_action": action,
        "observation": decision_request_to_json(request)["observation"],
        "legal_action_keys": sorted(legal),
        "immediate_hu": {
            "fan": immediate.fan,
            "score_delta_by_physical_seat": delta,
            "focal_delta": delta[observation.seat],
            "details": list(immediate.details),
        },
        "parent_top_action": entries[0].action_key,
        "parent_score_gap_top_minus_actual": round(entries[0].score - scores[action], 6),
        "parent_score_hu_minus_actual": round(scores["hu"] - scores[action], 6),
    }


def _selected_observation(snapshots, events: list[dict], draw_index: int,
                          *, game_id: str, round_no: int, dealer: int,
                          scores: list[int]) -> tuple[object | None, str | None]:
    """沿用 G05 的保守摸前快照门，不能补猜杠／飘后的链状态。"""

    draw = events[draw_index]
    prior = [seq for seq in snapshots if seq < int(draw["seq"])]
    if not prior:
        return None, "no_prior_discard_snapshot"
    before = snapshots[max(prior)]
    if any(int(before["seq"]) < int(event["seq"]) < int(draw["seq"])
           and event.get("type") not in g05.SKIP_EVENT_TYPES for event in events):
        return None, "intervening_action_since_snapshot"
    seat = draw["seat"]
    if before["baotou"][seat] is None:
        return None, "unknown_baotou"
    if before["rivers"][seat] and before["rivers"][seat][-1] == c31.WEALTH:
        return None, "recent_white_chain_uncertain"
    return g05.public_observation(
        before, draw, game_id=game_id, round_no=round_no,
        dealer=dealer, scores=scores,
    ), None


def main() -> None:
    """核对 G61 来源、官方当前动作与生产规则，写入分房逐窗证据。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, G61 / "manifest.json")).read_text(encoding="utf-8"))
    prior = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    if len(manifest["units"]) != 32 or prior.get("outcome_labels_opened") is not False:
        raise ValueError("G61 冻结母体身份不符")
    if prior.get("manifest_sha256") != sha(_project_file(_PROJECT_ROOT, G61 / "manifest.json")):
        raise ValueError("G61 结果／清单摘要不符")
    if sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")) != manifest["inputs_sha256"]["g05_strong_draw_reconstruction.py"]:
        raise ValueError("G05 重建器源码漂移")

    units = []
    source_ids = set()
    for unit in manifest["units"]:
        peer, room = unit["peer"], unit["room"]
        key = f"{peer}/{room}"
        record = prior["units"][key]
        folder = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}")
        if sha(folder / "result.json") != record["result_sha256"] or sha(folder / "windows.json") != record["windows_sha256"]:
            raise ValueError(f"G61 逐房证据漂移：{key}")
        record_doc = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        selected = record_doc["selected_games"]
        if len(selected) != 10 or record_doc["target_user_id"] != unit["target_user_id"]:
            raise ValueError(f"G61 完整桌或身份漂移：{key}")
        windows = json.loads((folder / "windows.json").read_text(encoding="utf-8"))["windows"]
        if len(windows) != record_doc["counts"]["legal_verified_windows"]:
            raise ValueError(f"G61 弃牌逐窗数量漂移：{key}")
        continuation = {(row["game_id"], row["round_no"], row["draw_seq"]): row
                        for row in windows if "hu" in row["legal_action_keys"]}
        if len(continuation) != sum("hu" in row["legal_action_keys"] for row in windows):
            raise ValueError(f"G61 合法胡弃牌键重复：{key}")
        units.append((peer, room, unit["target_user_id"], selected, continuation))
        source_ids.update(selected)

    games = {game_id: doc for _, _, _, game_id, doc in load_rooms() if game_id in source_ids}
    if len(games) != len(source_ids) or len(games) != 310:
        raise ValueError("G61 官方完整桌牌谱来源缺失或重复")
    sources = {game_id: payload_sha(doc) for game_id, doc in games.items()}
    summary_gaps = {}
    for game_id, doc in games.items():
        block_rounds = {block["round_no"] for block in doc.get("blocks") or []}
        if block_rounds != set(range(1, 9)):
            raise ValueError(f"官方牌谱事件块不是完整八局：{game_id}")
        summary_rounds = [row["round_no"] for row in doc.get("rounds") or []]
        if len(summary_rounds) != len(set(summary_rounds)):
            raise ValueError(f"官方牌谱摘要局号重复：{game_id}")
        missing = sorted(block_rounds - set(summary_rounds))
        if missing:
            summary_gaps[game_id] = missing
        if set(summary_rounds) - block_rounds:
            raise ValueError(f"官方牌谱摘要含事件块外局号：{game_id}")
    scorer = ActionValueScorer("g252-official-strong-hu", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = []
    totals = Counter()
    by_peer = defaultdict(Counter)
    by_room = defaultdict(Counter)
    exclusions = []
    for peer, room, target_user, selected, continuation in units:
        for game_id in selected:
            doc = games[game_id]
            if doc.get("room_id") != room or doc.get("status") != "finished":
                raise ValueError(f"非目标完赛官方桌：{game_id}")
            seats = [entry.get("user_id") for entry in doc.get("seats") or []]
            if seats.count(target_user) != 1:
                raise ValueError(f"强手本人座位不唯一：{game_id}")
            seat = seats.index(target_user)
            scores = [0, 0, 0, 0]
            metadata = c31.round_metadata(doc)
            official_rounds = {row["round_no"]: row for row in doc.get("rounds") or []}
            if len(official_rounds) != len(doc.get("rounds") or []):
                raise ValueError(f"官方单局号重复：{game_id}")
            for round_no, events, start_hands in anatomy.round_blocks(doc):
                if start_hands is None:
                    raise ValueError(f"官方完整桌单局缺起手牌：{game_id}/{round_no}")
                dealer = metadata.get(round_no, {}).get("dealer")
                if dealer is None:
                    raise ValueError(f"官方完整桌单局缺庄位：{game_id}/{round_no}")
                snapshots = c31.reconstruct(events, start_hands, scores, dealer)
                for index, draw in enumerate(events):
                    if draw.get("type") != "tile_drawn" or draw.get("seat") != seat:
                        continue
                    next_event = next((event for event in events[index + 1:]
                                       if event.get("type") not in g05.SKIP_EVENT_TYPES), None)
                    if next_event is None:
                        raise ValueError(f"本人摸牌无后继事件：{game_id}/{draw['seq']}")
                    kind = next_event.get("type")
                    if kind == "tile_discarded":
                        key = (game_id, round_no, draw["seq"])
                        source = continuation.get(key)
                        if source is None:
                            continue  # G61 的普通摸打保守连续性门未通过。
                        if next_event is not events[index + 1]:
                            raise ValueError(f"G61 强手弃牌与摸牌间有 timeout/pass：{key}")
                        if next_event.get("seat") != seat or source["actual_action"] != f"discard:{next_event['tile']}":
                            raise ValueError(f"G61 弃牌动作与原始牌谱不符：{key}")
                        observation = observation_from_json(source["observation"])
                        item = make_row(observation, peer=peer, room=room,
                                        action=source["actual_action"],
                                        source_kind="g61_verified_discard",
                                        next_seq=next_event["seq"], source_sha=sources[game_id],
                                        scorer=scorer)
                        if (item["legal_action_keys"] != source["legal_action_keys"]
                                or item["parent_top_action"] != source["parent_top_action"]
                                or abs(item["parent_score_gap_top_minus_actual"]
                                       - source["parent_score_gap_top_minus_actual"]) > 1e-6):
                            raise ValueError(f"G61 规则或父代评分漂移：{key}")
                        rows.append(item)
                        continuation.pop(key)
                    elif kind == "round_ended":
                        data = next_event.get("data") or {}
                        if (next_event.get("seat") != seat or data.get("draw") is not False):
                            continue
                        totals["official_hu_after_normal_draw"] += 1
                        if next_event is not events[index + 1]:
                            # 官方可胡超时可自动胡，此类不是强手主动胡标签。
                            totals["hu_excluded_intermediate_timeout_or_pass"] += 1
                            by_peer[peer]["hu_excluded_intermediate_timeout_or_pass"] += 1
                            continue
                        if (round_no in official_rounds
                                and official_rounds[round_no].get("winner") != seat):
                            raise ValueError(f"官方单局赢家与胡事件不符：{game_id}/{round_no}")
                        observation, reason = _selected_observation(
                            snapshots, events, index, game_id=game_id, round_no=round_no,
                            dealer=dealer, scores=scores)
                        if reason:
                            exclusions.append({"peer": peer, "room_id": room,
                                               "game_id": game_id, "round_no": round_no,
                                               "draw_seq": draw["seq"], "reason": reason})
                            totals["hu_excluded_" + reason] += 1
                            by_peer[peer]["hu_excluded_" + reason] += 1
                            continue
                        item = make_row(observation, peer=peer, room=room, action="hu",
                                        source_kind="official_accepted_self_draw_hu",
                                        next_seq=next_event["seq"], source_sha=sources[game_id],
                                        scorer=scorer, official_end=next_event)
                        rows.append(item)
                    elif kind == "gang":
                        totals["official_gang_after_normal_draw"] += 1
                        observation, reason = _selected_observation(
                            snapshots, events, index, game_id=game_id, round_no=round_no,
                            dealer=dealer, scores=scores)
                        if reason:
                            totals["gang_state_excluded_" + reason] += 1
                            continue
                        request, legal, _ = candidate_view(observation, scorer)
                        if "hu" not in legal:
                            continue
                        if next_event is not events[index + 1]:
                            raise ValueError(f"合法胡后杠与摸牌间有 timeout/pass：{game_id}/{draw['seq']}")
                        gang_kind = (next_event.get("data") or {}).get("kind")
                        action = f"gang:{GANG_KINDS.get(gang_kind)}:{next_event['tile']}"
                        if gang_kind not in GANG_KINDS or action not in legal:
                            raise ValueError(f"官方杠与生产候选不符：{game_id}/{draw['seq']}")
                        rows.append(make_row(
                            request.observation, peer=peer, room=room, action=action,
                            source_kind="official_accepted_gang", next_seq=next_event["seq"],
                            source_sha=sources[game_id], scorer=scorer))
                    else:
                        raise ValueError(f"意外本人正常摸牌后继：{game_id}/{draw['seq']} {kind}")
                ended = next((event for event in events if event.get("type") == "round_ended"), None)
                if ended is None:
                    raise ValueError(f"官方完整桌单局没有结束事件：{game_id}/{round_no}")
                delta = (ended.get("data") or {}).get("scores")
                if not isinstance(delta, list) or len(delta) != 4 or sum(delta) != 0:
                    raise ValueError(f"官方完整桌单局结算无效：{game_id}/{round_no}")
                if ((ended.get("data") or {}).get("round_no") != round_no
                        or (ended.get("data") or {}).get("dealer") != dealer):
                    raise ValueError(f"官方终局局号或庄位不符：{game_id}/{round_no}")
                summary = official_rounds.get(round_no)
                if summary is not None and (summary.get("scores") != delta
                                            or summary.get("dealer") != dealer
                                            or (None if summary.get("is_draw") else summary.get("winner"))
                                            != (None if (ended.get("data") or {}).get("draw") else ended.get("seat"))
                                            or summary.get("multiplier") != ((ended.get("data") or {}).get("fan") or 0)):
                    raise ValueError(f"官方局摘要与终局事件不符：{game_id}/{round_no}")
                if summary is None and ((ended.get("data") or {}).get("draw") is not True
                                        or any(delta)):
                    raise ValueError(f"官方摘要只允许省略零分流局：{game_id}/{round_no}")
                scores = [a + b for a, b in zip(scores, delta)]
        if continuation:
            raise ValueError(f"G61 合法胡续打未全部被官方牌谱找到：{peer}/{room}/{len(continuation)}")

    rows.sort(key=lambda row: (row["peer"], row["room_id"], row["game_id"],
                               row["round_no"], row["draw_seq"]))
    unique = {(row["peer"], row["game_id"], row["round_no"], row["draw_seq"])
              for row in rows}
    if len(unique) != len(rows):
        raise ValueError("强手同一正常摸牌窗口重复")
    for row in rows:
        peer, room = row["peer"], row["room_id"]
        family = row["label"] if row["actual_action"] == "hu" else row["actual_action"].split(":", 1)[0]
        fan = row["immediate_hu"]["fan"]
        for counter in (totals, by_peer[peer], by_room[f"{peer}/{room}"]):
            counter["rows"] += 1
            counter["label_" + row["label"]] += 1
            counter["action_" + family] += 1
            counter[f"{family}_fan_{fan}"] += 1
            counter["parent_disagrees"] += int(row["parent_top_action"] != row["actual_action"])
            parent_hu = row["parent_top_action"] == "hu"
            expert_hu = row["actual_action"] == "hu"
            counter["parent_hu_expert_continue"] += int(parent_hu and not expert_hu)
            counter["parent_continue_expert_hu"] += int(expert_hu and not parent_hu)
            counter["binary_hu_continue_disagreement"] += int(parent_hu != expert_hu)
    if totals["official_hu_after_normal_draw"] != 723 or totals["action_hu"] != 699:
        raise ValueError("强手胡正例保守覆盖与先导复核不符")
    if totals["action_discard"] != 235 or totals["action_gang"] != 6:
        raise ValueError("合法胡续打数与 G61／杠路径先导复核不符")
    manifest_out = {
        "schema": "g252-strong-hu-continue-manifest/1",
        "boundary": "正常摸牌；强手本人当窗合法胡与官方已接受动作。结果盲于弃胡之后的牌墙和结算。",
        "source_g61_manifest_sha256": sha(_project_file(_PROJECT_ROOT, G61 / "manifest.json")),
        "source_g61_result_sha256": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
        "source_g05_reconstruction_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g05_strong_draw_reconstruction.py")),
        "source_c31_reconstruction_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "c31_action_layer_gap.py")),
        "source_anatomy_sha256": sha(Path(anatomy.__file__)),
        "source_parent_sha256": hashlib.sha256(
            c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest(),
        "source_game_payload_sha256": dict(sorted(sources.items())),
        "source_round_summary_gaps": dict(sorted(summary_gaps.items())),
        "units": [{"peer": peer, "room": room, "target_user_id": user,
                   "games": selected} for peer, room, user, selected, _ in units],
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest_out)
    write_rows(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz"), rows)
    result = {
        "schema": "g252-strong-hu-continue-result/1", "outcome_blind": True,
        "script_sha256": sha(Path(__file__)), "manifest_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "rows_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")),
        "source_units": len(units), "distinct_rooms": len({room for _, room, _, _, _ in units}),
        "distinct_games": len(games), "rows": len(rows),
        "source_round_summary_gap_games": len(summary_gaps),
        "totals": dict(sorted(totals.items())),
        "by_peer": {key: dict(sorted(value.items())) for key, value in sorted(by_peer.items())},
        "by_room": {key: dict(sorted(value.items())) for key, value in sorted(by_room.items())},
        "exclusions": exclusions,
        "scope": "本窗口强手行为标签；动作前 PlayerObservation 与生产 HangmaRules；完整房聚类。未标注离线反事实收益。",
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"rows": len(rows), "totals": result["totals"],
                      "by_peer": result["by_peer"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
