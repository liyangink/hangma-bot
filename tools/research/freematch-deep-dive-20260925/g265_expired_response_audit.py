#!/usr/bin/env python3
"""G265：按官方牌谱与原始 /state，逐窗复核自由赛过期响应是否漏掉合法动作。

只读运行中账本与既有审计记录；输出仅含房号、事件序号、规则事实和摘要，
不复制 Token、Cookie 或 HTTP 认证头。固定房名单见同名证据目录 cohort.json。
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
import json
from pathlib import Path

import c31_action_layer_gap as c31
import live_integrity_audit as live


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g265-live-reliability-20260929')
COHORT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g265-live-reliability-20260929/cohort.json')
STATE = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
OFFICIAL = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-sse-freematch-campaign-20260925b/official")


def sha(path: Path) -> str:
    """对本地既有来源文件计算 SHA-256，避免重复牌谱发生静默差异。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    """读取本地 JSON；此脚本不发官方请求。"""
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_melds(rows) -> list[list[tuple[str, tuple[str, ...]]]]:
    """吃牌内部顺序不影响明刻/明顺身份；比较牌种多重集。"""
    return [sorted((meld["kind"], tuple(sorted(meld["tiles"]))) for meld in row)
            for row in rows]


def cohort_windows() -> tuple[list[dict], dict[str, dict], dict]:
    """从冻结 20 房找所有「提交零次且响应窗已过期」的决策记录。"""
    cohort = read(COHORT)
    ledger = read(STATE)
    if ledger.get("campaign") != cohort["campaign"]:
        raise ValueError("战役账本身份不符")
    room_index = {item["room_id"]: item for item in ledger["rooms"]}
    room_ids = cohort["room_ids"]
    if len(room_ids) != 20 or len(set(room_ids)) != 20:
        raise ValueError("冻结房名单不完整或重复")

    windows = []
    input_hashes = {}
    releases = Counter()
    response_window_count = 0
    for room_id in room_ids:
        room = room_index[room_id]
        if room.get("terminal_reason") != "tournament_finished" or len(room["games"]) != 10:
            raise ValueError("冻结房不是 10 张完整桌：" + room_id)
        audit_dir = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        manifest = live.read_manifest(audit_dir / "manifest.json")
        error = live.verify_manifest_release(manifest)
        if error:
            raise ValueError("房间受控发布包不符：" + room_id + ": " + error)
        releases[manifest["release_package_id"]] += 1
        decisions = audit_dir / "participants" / live.ME / "decisions.jsonl"
        input_hashes[room_id] = sha(decisions)
        with decisions.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("kind") != "decision_ended":
                    continue
                payload = record.get("payload") or {}
                window = payload.get("window") or {}
                phase = window.get("phase")
                if not isinstance(phase, str) or not phase.startswith("response_"):
                    continue
                response_window_count += 1
                if payload.get("end_reason") != "deadline":
                    continue
                if payload.get("sent_attempts") != 0:
                    raise ValueError("过期窗并非零提交：" + room_id)
                windows.append({
                    "room_id": room_id,
                    "game_id": window["game_id"],
                    "round_no": window["round_no"],
                    "trigger_seq": window["trigger_seq"],
                    "phase": phase,
                    "seat": window["seat"],
                    "decision_id": (record.get("context") or {}).get("decision_id"),
                    "release_package_id": manifest["release_package_id"],
                    "audit_dir": room["audit_dir"],
                })
    if len(windows) != cohort["expected_expired_response_windows"]:
        raise ValueError("过期响应窗数量偏离冻结母体")
    return windows, room_index, {
        "response_window_count": response_window_count,
        "decision_input_sha256": input_hashes,
        "release_package_ids": dict(releases),
        "room_ids": room_ids,
    }


def official_sources(game_ids: set[str]) -> tuple[dict[str, Path], dict[str, str]]:
    """校验官方下载 source.json 的原文字节摘要，同桌重复采集不得冲突。"""
    paths = defaultdict(list)
    for source_path in OFFICIAL.glob("dl-*/source.json"):
        source = read(source_path)
        game_id = source.get("game_id")
        if game_id not in game_ids:
            continue
        event_path = source_path.parent / "events.json"
        digest = sha(event_path)
        if digest != source.get("original_sha256"):
            raise ValueError("官方牌谱原文摘要不符：" + game_id)
        paths[game_id].append((event_path, digest))
    if set(paths) != game_ids:
        raise ValueError("缺少官方完整牌谱：" + str(sorted(game_ids - set(paths))))
    selected = {}
    hashes = {}
    for game_id, candidates in sorted(paths.items()):
        distinct = {digest for _, digest in candidates}
        if len(distinct) != 1:
            raise ValueError("同一桌官方下载原文冲突：" + game_id)
        selected[game_id] = sorted(path for path, _ in candidates)[0]
        hashes[game_id] = distinct.pop()
    return selected, hashes


def raw_snapshots(audit_dir: Path, game_id: str) -> tuple[list[dict], dict[str, str]]:
    """只取已保存的原始 /state 快照；认证报文不进入结果文件。"""
    raw_dir = audit_dir / "participants" / live.ME / "raw"
    paths = sorted(raw_dir.glob(game_id + ".*.jsonl.gz"))
    if not paths:
        raise ValueError("缺少原始 /state：" + game_id)
    states = []
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                payload = (json.loads(line).get("payload") or {})
                if payload.get("source") != "state_response":
                    continue
                raw = payload.get("raw")
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except ValueError:
                        continue
                if isinstance(raw, dict) and isinstance(raw.get("snapshot"), dict):
                    states.append(raw)
    return states, {str(path.relative_to(ROOT)): sha(path) for path in paths}


def response_segment(events: list[dict], discard_seq: int) -> list[dict]:
    """官方弃牌后的同一响应段；下一项非 pass/timeout 事件即为边界。"""
    index = next(i for i, event in enumerate(events) if event.get("seq") == discard_seq)
    if events[index]["type"] != "tile_discarded":
        raise ValueError("响应段起点不是官方弃牌")
    segment = []
    for event in events[index + 1:]:
        if event["type"] not in ("pass", "timeout"):
            break
        segment.append(event)
    return segment


def compare_state(snapshot: dict, observation) -> dict[str, bool]:
    """核对从牌谱投影的九组可见字段与当时已保存的官方 /state。"""
    god = snapshot.get("god") or {}
    expected_god = {
        "baotou": observation.rule_state.baotou,
        "chain_count": observation.rule_state.chain_count,
        "catch_play": observation.rule_state.catch_play,
        "god_discarder_seat": (-1 if observation.rule_state.catch_play_owner_seat is None
                                else observation.rule_state.catch_play_owner_seat),
    }
    projected_melds = [[
        {"kind": item.kind, "tiles": [tile.code for tile in item.tiles]}
        for item in row] for row in observation.melds]
    return {
        "hand": Counter(snapshot.get("my_hand") or []) == Counter(
            tile.code for tile in observation.my_hand),
        "scores": tuple(snapshot.get("scores") or []) == observation.scores,
        "wall": snapshot.get("wall_remaining") == observation.remaining_tile_count,
        "hand_counts": tuple(snapshot.get("hand_counts") or []) == observation.hand_counts,
        "god": god == expected_god,
        "turn": snapshot.get("turn") == observation.turn_seat,
        "dealer": snapshot.get("dealer") == observation.dealer_seat,
        "discards": snapshot.get("discards") == [
            [tile.code for tile in row] for row in observation.discards],
        "melds": canonical_melds(snapshot.get("melds") or []) == canonical_melds(projected_melds),
    }


def analyze_windows(windows: list[dict], room_index: dict, sources: dict[str, Path]) -> tuple[list[dict], dict]:
    """单桌单局重建一次，只将目标座位的玩家可见投影交给生产规则与父代。"""
    grouped = defaultdict(list)
    for window in windows:
        grouped[window["game_id"]].append(window)
    parent = c31.load_parent()
    rows = []
    raw_hashes = {}
    for game_id, targets in sorted(grouped.items()):
        document = read(sources[game_id])
        if document.get("status") != "finished" or document.get("game_id") != game_id:
            raise ValueError("官方桌未完成或身份错误：" + game_id)
        room_id = targets[0]["room_id"]
        if document.get("room_id") != room_id:
            raise ValueError("官方房身份错误：" + game_id)
        seat_ids = [item.get("user_id") for item in document.get("seats") or []]
        if seat_ids.count(live.ME) != 1:
            raise ValueError("本人座位不唯一：" + game_id)
        states, hashes = raw_snapshots(_project_file(_PROJECT_ROOT, ROOT / room_index[room_id]["audit_dir"]), game_id)
        raw_hashes.update(hashes)
        table_scores = [0, 0, 0, 0]
        blocks = list(c31.AL.round_blocks(document))
        if len(blocks) != 8:
            raise ValueError("不是八局完整桌：" + game_id)
        for round_no, events, start_hands in blocks:
            ended_dealer, delta = c31.round_end_facts(events)
            dealer = next((seat for seat, hand in enumerate(start_hands)
                           if len(hand) == 14), ended_dealer)
            if dealer is None or delta is None:
                raise ValueError("官方局庄位或结算缺失：" + game_id)
            relevant = [item for item in targets if item["round_no"] == round_no]
            if relevant:
                snapshots = c31.reconstruct(events, start_hands, table_scores, dealer)
                for item in relevant:
                    if item["seat"] != seat_ids.index(live.ME):
                        raise ValueError("审计响应座位不是本人")
                    prior = [event for event in events if event["seq"] <= item["trigger_seq"]
                             and event["type"] == "tile_discarded"]
                    if not prior:
                        raise ValueError("响应触发前没有弃牌")
                    discard_seq = prior[-1]["seq"]
                    snapshot = snapshots[discard_seq]
                    between = [event for event in events
                               if discard_seq < event["seq"] <= item["trigger_seq"]]
                    if any(event["type"] not in ("pass", "timeout") for event in between):
                        raise ValueError("响应触发与弃牌之间发生非响应事件")
                    phase = item["phase"]
                    members = (c31._peng_members(snapshot["discarder"], snapshot["tile"],
                                                 snapshot["owner"])
                               if phase == "response_peng" else
                               c31._chi_members(snapshot["discarder"], snapshot["tile"],
                                                snapshot["owner"]))
                    if item["seat"] not in members or snapshot["baotou"][item["seat"]] is None:
                        raise ValueError("窗口成员或爆头规则事实无法重建")
                    segment = response_segment(events, discard_seq)
                    timeout_events = [event for event in segment
                                      if event["type"] == "timeout"
                                      and event.get("seat") == item["seat"]
                                      and (event.get("data") or {}).get("kind") == "response"
                                      and (event.get("data") or {}).get("window") == phase.removeprefix("response_")]
                    if len(timeout_events) != 1:
                        raise ValueError("官方本人该响应窗 timeout 不唯一")
                    timeout_seq = timeout_events[0]["seq"]
                    observation = c31.build_observation(
                        snapshot, item["seat"], phase, game_id, round_no)
                    exact = [state for state in states
                             if discard_seq <= state.get("seq", -1) <= timeout_seq
                             and state["snapshot"].get("round_no") == round_no
                             and state["snapshot"].get("seat") == item["seat"]
                             and state["snapshot"].get("phase") == phase
                             and state["snapshot"].get("last_discard") == snapshot["tile"]]
                    if not exact:
                        raise ValueError("官方原始 /state 缺同相位窗口快照")
                    authority = max(exact, key=lambda state: state["seq"])
                    matches = compare_state(authority["snapshot"], observation)
                    if not all(matches.values()):
                        raise ValueError("牌谱投影与原始 /state 不一致：" + str(matches))
                    analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
                    candidate_keys = [candidate.action_key
                                      for candidate in analysis.legal_candidates]
                    _, scores, status, reason, *_ = c31.score_window(observation, parent)
                    if status != "SCORED" or scores is None or set(scores) != set(candidate_keys):
                        raise ValueError("冻结 R18 v2 重判不可用：" + str(reason))
                    non_pass = []
                    for candidate in analysis.legal_candidates:
                        if candidate.action_key == "pass":
                            continue
                        settlement = (None if candidate.value_facts is None else
                                      candidate.value_facts.immediate_settlement)
                        facts = candidate.facts
                        non_pass.append({
                            "action_key": candidate.action_key,
                            "fact_kind": None if facts is None else facts.fact_kind.value,
                            "shanten_after": None if facts is None else facts.shanten_after,
                            "best_followup_discard": (None if facts is None else
                                                      facts.best_followup_discard),
                            "baotou_after": None if facts is None else facts.baotou_after,
                            "immediate_fan": None if settlement is None else settlement.fan,
                            "immediate_score_delta": (None if settlement is None else
                                                      list(settlement.score_delta)),
                        })
                    rows.append({
                        "room_id": room_id, "game_id": game_id,
                        "round_no": round_no, "decision_id": item["decision_id"],
                        "trigger_seq": item["trigger_seq"], "discard_seq": discard_seq,
                        "timeout_seq": timeout_seq, "phase": phase, "seat": item["seat"],
                        "discard_tile": snapshot["tile"],
                        "white_count_before": sum(tile.code == "白" for tile in observation.my_hand),
                        "legal_action_keys": candidate_keys, "non_pass_candidates": non_pass,
                        "r18_scores": scores,
                        "r18_top_action": min(scores, key=lambda key: (-scores[key], key)),
                        "rules_completeness": analysis.completeness.value,
                        "rule_issues": [{"area": issue.area, "reason": issue.reason}
                                        for issue in analysis.issues],
                        "state_seq": authority["seq"],
                        "state_projection_match": matches,
                        "release_package_id": item["release_package_id"],
                    })
            table_scores = [old + change for old, change in zip(table_scores, delta)]
    rows.sort(key=lambda item: (item["room_id"], item["game_id"], item["round_no"],
                                item["trigger_seq"], item["phase"]))
    if len(rows) != len(windows):
        raise ValueError("有过期窗未获规则重建")
    return rows, raw_hashes


def main() -> None:
    """重算固定房组并覆盖写入确定性的逐窗证据；不触碰线上进程。"""
    windows, room_index, meta = cohort_windows()
    sources, source_hashes = official_sources({item["game_id"] for item in windows})
    rows, raw_hashes = analyze_windows(windows, room_index, sources)
    non_pass = [item for item in rows if item["non_pass_candidates"]]
    result = {
        "schema": "g265-expired-response-audit/1",
        "boundary": "只用本人玩家可见投影与受控生产规则重建合法性；官方后续只用于核对 timeout，不用作策略输入。",
        "summary": {
            "rooms": len(meta["room_ids"]),
            "complete_tables": len(meta["room_ids"]) * 10,
            "response_windows": meta["response_window_count"],
            "expired_response_windows": len(rows),
            "official_timeout_confirmed": len(rows),
            "raw_state_projection_matched": sum(all(item["state_projection_match"].values())
                                                for item in rows),
            "only_pass_legal": len(rows) - len(non_pass),
            "non_pass_legal": len(non_pass),
            "legal_hu": sum(any(key.startswith("hu") for key in item["legal_action_keys"])
                            for item in rows),
            "legal_gang": sum(any(key.startswith("gang:") for key in item["legal_action_keys"])
                              for item in rows),
            "r18_top_non_pass": sum(item["r18_top_action"] != "pass" for item in rows),
        },
        "non_pass_windows": [{"room_id": item["room_id"], "game_id": item["game_id"],
                              "round_no": item["round_no"], "discard_seq": item["discard_seq"],
                              "phase": item["phase"], "r18_scores": item["r18_scores"],
                              "legal_action_keys": item["legal_action_keys"]}
                             for item in non_pass],
        "provenance": {
            "cohort_sha256": sha(COHORT),
            "analysis_source_sha256": sha(Path(__file__)),
            "c31_reconstructor_sha256": sha(Path(c31.__file__)),
            "official_events_sha256": source_hashes,
            "raw_audit_sha256": raw_hashes,
            "decision_input_sha256": meta["decision_input_sha256"],
            "release_package_ids": meta["release_package_ids"],
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (_project_file(_PROJECT_ROOT, OUT / "windows.jsonl")).write_text("".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rows
    ), encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
