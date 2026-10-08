#!/usr/bin/env python3
"""G262：未按赢家筛选地审计 G61 强手房吃碰响应与弃白后继的可达性。"""

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
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g184_classic_highhand_shadow as g184
from hangma_bot.application.audit_codec import observation_to_json


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
SOURCE_ROOT = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions")
PEERS = {"xuanwu_2346": "u_380da525337c",
         "tengshe_0638": "u_b2aa6abe7811"}


def sha(path: Path) -> str:
    """返回本地冻结来源或分析器的 SHA-256；不读取认证配置。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    """读取官方本地牌谱或冻结结果，不访问网络。"""

    return json.loads(path.read_text(encoding="utf-8"))


def selected_units() -> tuple[dict, dict]:
    """从 G61 锁定的强手－房与十张完整桌构造未按赢家筛选的母体。"""

    batch = read(_project_file(_PROJECT_ROOT, G61 / "result.json"))
    if batch["outcome_labels_opened"] is not False or len(batch["units"]) != 32:
        raise ValueError("G61 冻结房或结果盲标记漂移")
    units = {}
    games = defaultdict(list)
    for unit, manifest in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        if peer not in PEERS:
            raise ValueError("未知强手身份")
        source = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "result.json")
        if sha(source) != manifest["result_sha256"]:
            raise ValueError("G61 房结果摘要漂移：" + unit)
        item = read(source)
        if (item["room_id"] != room or item["target_user_id"] != PEERS[peer] or
                len(item["selected_games"]) != 10):
            raise ValueError("G61 房强手或完整桌名单漂移")
        units[unit] = item["selected_games"]
        for game_id in item["selected_games"]:
            games[game_id].append((peer, room))
    if len(games) != 310:
        raise ValueError("G61 物理完整桌分母不是 310")
    return units, games


def source_files(game_ids: set[str]) -> tuple[dict[str, Path], dict[str, str]]:
    """只扫描 artifacts/sessions；重复官方牌谱要求字节摘要相同。"""

    found = defaultdict(list)
    for path in SOURCE_ROOT.rglob("events.json"):
        try:
            doc = read(path)
        except (OSError, ValueError):
            continue
        game_id = doc.get("game_id")
        if game_id in game_ids:
            found[game_id].append(path)
    if set(found) != game_ids:
        raise ValueError("本地 artifacts 缺 G61 完整桌：" + str(len(game_ids - set(found))))
    chosen, hashes = {}, {}
    for game_id, paths in sorted(found.items()):
        digests = {sha(path) for path in paths}
        if len(digests) != 1:
            raise ValueError("同一完整桌重复官方下载内容不一致：" + game_id)
        chosen[game_id] = sorted(paths)[0]
        hashes[game_id] = digests.pop()
    return chosen, hashes


def response_after(events: list[dict]) -> dict[int, tuple[dict | None, dict | None]]:
    """只为观察标签取本次弃牌后紧接的鸣牌及无摸跟打，不作决策特征。"""

    result = {}
    for index, event in enumerate(events):
        if event.get("type") != "tile_discarded":
            continue
        cursor = index + 1
        while cursor < len(events) and events[cursor].get("type") in ("pass", "timeout"):
            cursor += 1
        claim = None
        followup = None
        if cursor < len(events) and (events[cursor].get("type") in ("chi", "peng") or
                                     (events[cursor].get("type") == "gang" and
                                      (events[cursor].get("data") or {}).get("kind") == "ming")):
            claim = events[cursor]
            cursor += 1
            while cursor < len(events) and events[cursor].get("type") in ("pass", "timeout"):
                cursor += 1
            if cursor < len(events):
                followup = events[cursor]
        result[event["seq"]] = (claim, followup)
    return result


def phase_label(snap: dict, seat: int, phase: str, legal_phases: tuple[str, ...],
                claim: dict | None) -> str:
    """把明确过牌、超时、他人抢先、无响应记录分别保留。"""

    if claim is not None and claim.get("seat") == seat:
        actual = claim.get("type")
        if actual == "gang":
            return "claimed_ming_gang"
        return "claimed_this_phase" if phase == "response_" + actual else "claimed_other_phase"
    suffix = phase.removeprefix("response_")
    responses = [item for item in snap["responses"] if item[0] == seat]
    typed = [item[1] for item in responses if item[2] == suffix]
    if "pass" in typed:
        return "explicit_pass"
    if "timeout" in typed:
        return "timeout"
    untyped_pass = any(item[1] == "pass" and item[2] is None for item in responses)
    if untyped_pass:
        return "explicit_pass" if len(legal_phases) == 1 else "pass_phase_ambiguous"
    if claim is not None:
        return "preempted_or_unrecorded"
    return "no_response_event"


def white_branch(candidate) -> dict | None:
    """只读取生产吃碰后继的合法弃白分支与弃后爆头／飘链事实。"""

    facts = candidate.facts
    branches = None if facts is None else facts.followup_branches
    if branches is None:
        return None
    matches = [branch for branch in branches if branch.followup_discard == "白"]
    if len(matches) > 1:
        raise ValueError("同一吃碰候选存在重复弃白分支")
    if not matches:
        return None
    branch = matches[0]
    return {
        "combined_shanten_after": branch.combined_shanten,
        "public_support_after": branch.support_remaining,
        "baotou_after": branch.baotou_after,
        "chain_count_after": branch.chain_count_after,
        "chain_piao_after": branch.chain_piao_after,
        "four_white_qualified_after": branch.four_white_qualified_after,
    }


def summarize(rows: list[dict]) -> tuple[dict, dict]:
    """按强手和强手－房计数；两强手重合房不可作两间独立房。"""

    by_peer = {}
    by_unit = {}
    for peer in PEERS:
        subset = [row for row in rows if row["peer"] == peer]
        counter = Counter()
        for row in subset:
            counter["legal_response_phase_windows"] += 1
            counter["legal_claim_candidates"] += len(row["claim_candidates"])
            counter["response_" + row["observed_response"]] += 1
            counter["r18_top_" + row["r18_top"].split(":", 1)[0]] += 1
            counter["white_branch_candidates"] += sum(
                choice["white_branch"] is not None for choice in row["claim_candidates"])
            counter["white_baotou_candidates"] += sum(
                choice["white_branch"] is not None and
                choice["white_branch"]["baotou_after"] is True
                for choice in row["claim_candidates"])
            counter["white_chain_piao_candidates"] += sum(
                choice["white_branch"] is not None and
                (choice["white_branch"]["chain_piao_after"] or 0) > 0
                for choice in row["claim_candidates"])
            counter["white_chain_unknown_candidates"] += sum(
                choice["white_branch"] is not None and
                choice["white_branch"]["chain_piao_after"] is None
                for choice in row["claim_candidates"])
            counter["white_chain_piao_without_baotou_candidates"] += sum(
                choice["white_branch"] is not None and
                choice["white_branch"]["baotou_after"] is False and
                (choice["white_branch"]["chain_piao_after"] or 0) > 0
                for choice in row["claim_candidates"])
            counter["white_baotou_windows"] += any(
                choice["white_branch"] is not None and
                choice["white_branch"]["baotou_after"] is True
                for choice in row["claim_candidates"])
            counter["white_baotou_actual_claim"] += (
                row["actual_claim_key"] is not None and any(
                    choice["action_key"] == row["actual_claim_key"] and
                    choice["white_branch"] is not None and
                    choice["white_branch"]["baotou_after"] is True
                    for choice in row["claim_candidates"]))
            counter["actual_claim_followup_white"] += row["actual_followup_discard"] == "白"
            counter["actual_claim_followup_white_keeps_baotou"] += (
                row["actual_followup_discard"] == "白" and
                row["actual_followup_white_branch"] is not None and
                row["actual_followup_white_branch"]["baotou_after"] is True)
        by_peer[peer] = dict(sorted(counter.items()))
        for room in sorted({row["room"] for row in subset}):
            unit_rows = [row for row in subset if row["room"] == room]
            by_unit[peer + "/" + room] = {
                "legal_response_phase_windows": len(unit_rows),
                "white_baotou_windows": sum(any(
                    item["white_branch"] is not None and
                    item["white_branch"]["baotou_after"] is True
                    for item in row["claim_candidates"]) for row in unit_rows),
                "actual_claim_followup_white_keeps_baotou": sum(
                    row["actual_followup_discard"] == "白" and
                    row["actual_followup_white_branch"] is not None and
                    row["actual_followup_white_branch"]["baotou_after"] is True
                    for row in unit_rows),
            }
    return by_peer, by_unit


def main() -> None:
    """全量 G61 同房强手响应分母，只对当前合法吃碰窗重算冻结 R18。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=_project_file(_PROJECT_ROOT, HERE / "evidence/g262-strong-claim-white-feasibility-20260929"))
    args = parser.parse_args()
    out = args.output_dir
    if out.exists() and any(out.iterdir()):
        raise SystemExit("输出目录已有文件，拒绝覆盖")
    units, games = selected_units()
    sources, source_sha = source_files(set(games))
    parent = c31.load_parent()
    rows = []
    audit = Counter()
    physical_keys = set()
    for game_id, path in sorted(sources.items()):
        doc = read(path)
        room = doc.get("room_id")
        if (doc.get("game_id") != game_id or doc.get("status") != "finished" or
                any(unit_room != room for _, unit_room in games[game_id])):
            raise ValueError("官方完整桌身份或完成状态漂移：" + game_id)
        seats = [item.get("user_id") for item in doc.get("seats") or []]
        if len(seats) != 4:
            raise ValueError("官方完整桌座位不全")
        targets = []
        for peer, _ in games[game_id]:
            if seats.count(PEERS[peer]) != 1:
                raise ValueError("G61 同房强手不在选定完整桌")
            targets.append((peer, seats.index(PEERS[peer])))
        blocks = list(c31.AL.round_blocks(doc))
        if len(blocks) != 8:
            raise ValueError("G61 选定完整桌不是八局：" + game_id)
        table_scores = [0, 0, 0, 0]
        for round_no, events, start_hands in blocks:
            ended_dealer, ended_scores = c31.round_end_facts(events)
            dealer = next((i for i, hand in enumerate(start_hands)
                           if len(hand) == 14), ended_dealer)
            if dealer is None or ended_scores is None:
                raise ValueError("官方单局庄位或终局积分缺失")
            snaps = c31.reconstruct(events, start_hands, table_scores, dealer)
            after = response_after(events)
            for seq, snap in sorted(snaps.items()):
                if snap["tile"] == "白":
                    audit["white_discard_no_chi_peng_window"] += len(targets)
                    continue
                claim, followup = after[seq]
                for peer, seat in targets:
                    if seat == snap["discarder"]:
                        continue
                    possible = []
                    if seat in c31._peng_members(snap["discarder"], snap["tile"], snap["owner"]):
                        possible.append("response_peng")
                    if seat in c31._chi_members(snap["discarder"], snap["tile"], snap["owner"]):
                        possible.append("response_chi")
                    if not possible:
                        continue
                    physical_keys.add((peer, room, game_id, round_no, seq, seat))
                    audit["physical_discard_seat_opportunities"] += 1
                    if snap["baotou"][seat] is None:
                        audit["unknown_pre_response_baotou"] += 1
                        continue
                    for phase in possible:
                        audit["possible_phase_windows"] += 1
                        observation = c31.build_observation(
                            snap, seat, phase, game_id, round_no)
                        analysis = c31.RULES.analyze(
                            observation, value_limits=c31.VALUE_LIMITS)
                        candidates = {item.action_key: item for item in analysis.legal_candidates}
                        claims = {name: item for name, item in candidates.items()
                                  if name.startswith("chi:") or name.startswith("peng:")}
                        if not claims:
                            continue
                        audit["legal_response_phase_windows"] += 1
                        if "pass" not in candidates:
                            raise ValueError("合法吃碰响应缺 pass 候选")
                        view, scores, status, reason, _analysis, *_ = c31.score_window(
                            observation, parent)
                        if status != "SCORED" or scores is None or set(scores) != set(candidates):
                            raise ValueError("冻结 R18 响应评分失败：" + str(reason))
                        r18_top = min(scores, key=lambda name: (-scores[name], name))
                        actual_claim_key = None
                        if claim is not None and claim.get("seat") == seat:
                            actual_claim_key = g184.actual_key(claim)
                            if (claim.get("type") == phase.removeprefix("response_") and
                                    actual_claim_key not in candidates):
                                raise ValueError("强手已确认吃碰不在生产合法动作中")
                        followup_code = None
                        actual_white_branch = None
                        if actual_claim_key in claims:
                            if (followup is not None and
                                    followup.get("type") == "tile_discarded" and
                                    followup.get("seat") == seat):
                                followup_code = followup["tile"]
                            else:
                                audit["claim_followup_unverified"] += 1
                            branch = claims[actual_claim_key].facts.followup_branches
                            if followup_code is not None and (branch is None or not any(
                                    item.followup_discard == followup_code for item in branch)):
                                raise ValueError("强手鸣牌后实际跟打不在生产合法后继")
                            if followup_code == "白":
                                actual_white_branch = white_branch(claims[actual_claim_key])
                                if actual_white_branch is None:
                                    raise ValueError("实际弃白缺规则白后继")
                        claim_rows = []
                        for action, candidate in sorted(claims.items()):
                            branch = white_branch(candidate)
                            if (sum(tile.code == "白" for tile in observation.my_hand) > 0
                                    and branch is None):
                                raise ValueError("持白吃碰候选缺生产弃白后继")
                            claim_rows.append({
                                "action_key": action,
                                "r18_score_gap_parent_minus_claim": scores[r18_top] - scores[action],
                                "best_followup_discard_by_rules": (
                                    candidate.facts.best_followup_discard
                                    if candidate.facts is not None else None),
                                "white_branch": branch,
                            })
                        row = {
                            "peer": peer, "room": room, "game_id": game_id,
                            "round_no": round_no, "discard_seq": seq,
                            "seat": seat, "phase": phase,
                            "observation_seq": observation.snapshot_seq,
                            "white_held_before": sum(tile.code == "白" for tile in observation.my_hand),
                            "baotou_before": observation.rule_state.baotou,
                            "chain_count_before": observation.rule_state.chain_count,
                            "chain_piao_before": observation.chain_piao,
                            "wall_remaining": observation.remaining_tile_count,
                            "table_scores_before": list(observation.scores),
                            "score_position": (
                                "sole_leader" if observation.scores[seat] == max(observation.scores)
                                and observation.scores.count(observation.scores[seat]) == 1
                                else "sole_last" if observation.scores[seat] == min(observation.scores)
                                and observation.scores.count(observation.scores[seat]) == 1
                                else "tied_leader" if observation.scores[seat] == max(observation.scores)
                                else "tied_last" if observation.scores[seat] == min(observation.scores)
                                else "middle"),
                            "dealer_seat": observation.dealer_seat,
                            "observed_response": phase_label(
                                snap, seat, phase, tuple(possible), claim),
                            "explicit_response_events": [
                                {"kind": kind, "window": window}
                                for s, kind, window in snap["responses"] if s == seat],
                            "actual_claim_key": actual_claim_key,
                            "actual_followup_discard": followup_code,
                            "actual_followup_white_branch": actual_white_branch,
                            "r18_top": r18_top,
                            "r18_pass_score": scores["pass"],
                            "claim_candidates": claim_rows,
                            "observation_sha256": hashlib.sha256(json.dumps(
                                observation_to_json(observation), ensure_ascii=False,
                                sort_keys=True).encode("utf-8")).hexdigest(),
                        }
                        rows.append(row)
            table_scores = [old + delta for old, delta in zip(table_scores, ended_scores)]
    rows.sort(key=lambda row: (row["peer"], row["room"], row["game_id"],
                               row["round_no"], row["discard_seq"], row["seat"], row["phase"]))
    by_peer, by_unit = summarize(rows)
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "response_windows.jsonl"
    with rows_path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False) + "\n")
    result = {
        "schema": "g262-strong-claim-white-feasibility/1",
        "result_blind": True,
        "denominator": {"physical_rooms": len({unit.split("/", 1)[1] for unit in units}),
                        "peer_room_units": len(units), "physical_complete_tables": len(sources),
                        "unit_complete_tables": sum(len(items) for items in units.values()),
                        "legal_response_phase_windows": len(rows),
                        "legal_response_unique_discard_seat_windows": len({
                            (row["peer"], row["room"], row["game_id"], row["round_no"],
                             row["discard_seq"], row["seat"]) for row in rows})},
        "audit": dict(sorted(audit.items())),
        "by_peer": by_peer, "by_peer_room": by_unit,
        "source_sha256": {"script": sha(Path(__file__)),
                          "g61_result": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
                          "selected_events_by_game": source_sha,
                          "c31_reconstructor": sha(Path(c31.__file__)),
                          "g184_key_parser": sha(Path(g184.__file__))},
        "evidence_sha256": {"response_windows.jsonl": sha(rows_path)},
        "boundary": "只用本座当前 PlayerObservation 重算合法性、R18 和弃白规则分支；当前弃牌后的吃碰/过牌及紧接跟打仅作已执行动作标签，不进入决策特征。超时、被抢先及缺响应不冒称主动 pass。",
    }
    (out / "result.json").open("x", encoding="utf-8").write(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2,
                   allow_nan=False) + "\n")
    print(json.dumps({"denominator": result["denominator"],
                      "audit": result["audit"], "by_peer": by_peer},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
