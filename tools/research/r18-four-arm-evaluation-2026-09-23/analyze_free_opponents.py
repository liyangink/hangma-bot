"""对拍公开自由赛牌谱与房级账，描述不同时期的真实对手组成和打法。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics


ROOT = _PROJECT_ROOT
R18_SUMMARIES = _project_file(_PROJECT_ROOT, 'review/r18-auto-match-2026-09-23/rooms')
V2_LEDGER = _project_file(_PROJECT_ROOT, 'review/auto-match-value-2026-09-08/ledger-snapshot.json')
OUT = _project_file(_PROJECT_ROOT, 'review/r18-four-arm-evaluation-2026-09-23/free-opponent-recheck.json')


def expected_r18() -> dict[tuple[str, int], dict]:
    """从 31 份房级摘要取明确的 game_id、座位、终局分与策略时期。"""
    expected = {}
    files = list(R18_SUMMARIES.glob("a_*.md"))
    if len(files) != 31:
        raise ValueError("R18 房级摘要不是 31 房")
    for path in files:
        body = path.read_text(encoding="utf-8")
        match = re.search(r"(?:战役)?第\s*(\d+)\s*房", body)
        if not match:
            raise ValueError("房级序号缺失：" + str(path))
        room_index = int(match.group(1))
        policy = "r18_v1" if room_index <= 24 else "r18_v2"
        for line in body.splitlines():
            if not line.startswith("|"):
                continue
            cells = [cell.strip().strip("`* ") for cell in line.split("|")[1:-1]]
            if not cells:
                continue
            game_id = None
            game_cell = next((i for i, cell in enumerate(cells)
                              if re.fullmatch(r"a_[A-Za-z0-9_]+_r\d+_b\d+_t\d+", cell)), None)
            if game_cell is not None:
                game_id = cells[game_cell]
                batch = int(re.search(r"_b(\d+)_", game_id).group(1))
                first_number = game_cell + 1
            elif re.fullmatch(r"b\d+", cells[0]):
                batch = int(cells[0][1:])
                first_number = 1
            else:
                continue
            if len(cells) <= first_number + 1:
                raise ValueError("房级明细字段不足：" + str(path))
            seat = re.fullmatch(r"[0-3]", cells[first_number])
            # 房级 Markdown 混用 ASCII 与排版用的 Unicode 负号。
            score_text = cells[first_number + 1].translate(str.maketrans("−–﹣＋", "---+"))
            score = re.search(r"[+-]?\d+", score_text)
            if not seat or not score:
                raise ValueError("房级明细座位或终局分无效：" + str(path))
            key = path.stem, batch
            expected[key] = {"game_id": game_id, "seat": int(seat.group()),
                             "score": int(score.group()), "room_index": room_index, "policy": policy}
    if len(expected) != 310:
        raise ValueError("R18 房级摘要不是 310 场：" + str(len(expected)))
    return expected


def expected_v2() -> dict[tuple[str, int], dict]:
    """从旧稳定 V2 冻结账本取四十房的终局座位与分数。"""
    ledger = json.loads(V2_LEDGER.read_text(encoding="utf-8"))
    expected = {}
    for room_index, room in enumerate(ledger["rooms"], 1):
        for game in room["games"]:
            match = re.search(r"_b(\d+)_", game["game_id"])
            if not match:
                raise ValueError("旧账本场次 ID 无 batch：" + game["game_id"])
            expected[room["room_id"], int(match.group(1))] = {
                "game_id": game["game_id"], "seat": game["seat"],
                "score": game["final_score"], "room_index": room_index, "policy": "v2",
            }
    if len(expected) != 400:
        raise ValueError("V2 冻结账本不是 400 场：" + str(len(expected)))
    return expected


def source_index(session: Path) -> dict[tuple[str, int], Path]:
    """按完整 source.json 选赛后原文；失败或半截下载不进入分析。"""
    index = {}
    for source_path in sorted((session / "official").glob("dl-*/source.json")):
        source = json.loads(source_path.read_text(encoding="utf-8"))
        key = source["room_id"], source["batch"]
        events_path = source_path.with_name("events.json")
        if hashlib.sha256(events_path.read_bytes()).hexdigest() != source["original_sha256"]:
            raise ValueError("官方原文摘要不一致：" + str(events_path))
        index[key] = events_path
    return index


def analyze_campaign(expected: dict, source: dict, *, allow_missing: bool = False) -> dict:
    """只按官方完整桌结算计分，并用玩家 ID 统计对手池重复情况。"""
    missing = sorted(set(expected) - set(source))
    if missing and not allow_missing:
        raise ValueError("官方牌谱尚缺 {0} 场，例如 {1}".format(len(missing), missing[:3]))
    rows = []
    for key in sorted(expected):
        path = source.get(key)
        if path is None:
            continue
        exp = expected[key]
        doc = json.loads(path.read_text(encoding="utf-8"))
        if (doc.get("status") != "finished" or doc.get("room_id") != key[0]
                or doc.get("batch") != key[1]
                or (exp["game_id"] is not None and doc.get("game_id") != exp["game_id"])):
            raise ValueError("房间/场次/终态与账本不一致：" + str(path))
        focal_seat = exp["seat"]
        seats = doc["seats"]
        focal_user = seats[focal_seat]["user_id"]
        if len(seats) != 4 or not isinstance(focal_user, str):
            raise ValueError("座位身份不完整：" + str(path))
        # 公开档案的 rounds 摘要偶有漏掉零分流局，但完整事件块保留
        # round_ended。逐单局结算以该权威事件为准，并对摘要已有行对拍。
        round_end_events = {}
        for block in doc["blocks"]:
            if block.get("truncated"):
                raise ValueError("官方事件块被截断：" + str(path))
            for event in block["events"]:
                if event.get("type") == "round_ended":
                    round_no = (event.get("data") or {}).get("round_no")
                    if round_no in round_end_events:
                        raise ValueError("单局结算事件重复：" + str(path))
                    round_end_events[round_no] = event
        if sorted(round_end_events) != list(range(1, len(round_end_events) + 1)):
            raise ValueError("单局结算事件缺口：" + str(path))
        for summary_round in doc["rounds"]:
            ended = round_end_events.get(summary_round["round_no"])
            if ended is None or ended["data"]["scores"] != summary_round["scores"]:
                raise ValueError("单局摘要与结算事件不一致：" + str(path))
        final_scores = [sum(event["data"]["scores"][seat]
                            for event in round_end_events.values()) for seat in range(4)]
        if final_scores[focal_seat] != exp["score"]:
            raise ValueError("终局分与房级账不一致：" + str(path))
        if sum(final_scores) != 0:
            raise ValueError("桌内终局分不守恒：" + str(path))
        claims = Counter()
        round_draws = Counter()
        for block in doc["blocks"]:
            for event in block["events"]:
                kind = event.get("type")
                seat = event.get("seat")
                if kind in ("chi", "peng", "gang") and isinstance(seat, int):
                    claims[seat] += 1
                if kind == "tile_drawn":
                    round_draws[block["round_no"]] += 1
        rounds = []
        for round_no, ended in sorted(round_end_events.items()):
            outcome = ended["data"]
            winner = ended["seat"]
            if outcome["draw"]:
                winner = None
            elif not isinstance(winner, int) or not 0 <= winner < 4:
                raise ValueError("终局赢家座位无效：" + str(path))
            rounds.append({"winner_is_focal": winner == focal_seat,
                           "winner_is_opponent": winner is not None and winner != focal_seat,
                           "winner_seat": winner,
                           "fan": outcome.get("fan"),
                           "draw_count": round_draws[round_no],
                           "dealer_is_focal": outcome["dealer"] == focal_seat})
        opponents = []
        for seat, seat_row in enumerate(seats):
            if seat == focal_seat:
                continue
            opponents.append({
                "user_id": seat_row["user_id"], "seat": seat,
                "final_score": final_scores[seat], "claims": claims[seat],
                "round_wins": sum(row["winner_seat"] == seat for row in rounds),
            })
        rows.append({"room_id": key[0], "batch": key[1], "room_index": exp["room_index"],
                     "policy": exp["policy"], "game_id": doc["game_id"],
                     "focal_user_id": focal_user, "focal_seat": focal_seat,
                     "opponent_user_ids": [row["user_id"] for seat, row in enumerate(seats)
                                           if seat != focal_seat],
                     "opponents": opponents,
                     "final_scores": final_scores, "focal_score": final_scores[focal_seat],
                     "focal_strict_first": all(final_scores[focal_seat] > score
                                               for seat, score in enumerate(final_scores)
                                               if seat != focal_seat),
                     "focal_claims": claims[focal_seat],
                     "opponent_claims": sum(value for seat, value in claims.items()
                                            if seat != focal_seat),
                     "rounds": rounds})
    segments = {}
    for policy in sorted({row["policy"] for row in rows}):
        subset = [row for row in rows if row["policy"] == policy]
        all_rounds = [round_row for row in subset for round_row in row["rounds"]]
        opponent_ids = [user for row in subset for user in row["opponent_user_ids"]]
        opponent_fans = [round_row["fan"] for round_row in all_rounds
                         if round_row["winner_is_opponent"] and isinstance(round_row["fan"], int)]
        focal_fans = [round_row["fan"] for round_row in all_rounds
                      if round_row["winner_is_focal"] and isinstance(round_row["fan"], int)]
        opponent_win_draws = [round_row["draw_count"] for round_row in all_rounds
                              if round_row["winner_is_opponent"]]
        focal_win_draws = [round_row["draw_count"] for round_row in all_rounds
                           if round_row["winner_is_focal"]]
        opponents = [opponent for row in subset for opponent in row["opponents"]]
        per_user = defaultdict(lambda: {"table_exposures": 0, "round_wins": 0,
                                        "final_score_total": 0, "claims": 0})
        user_rooms = defaultdict(set)
        for row in subset:
            for opponent in row["opponents"]:
                profile = per_user[opponent["user_id"]]
                profile["table_exposures"] += 1
                profile["round_wins"] += opponent["round_wins"]
                profile["final_score_total"] += opponent["final_score"]
                profile["claims"] += opponent["claims"]
                user_rooms[opponent["user_id"]].add(row["room_id"])
        for user_id, profile in per_user.items():
            profile["room_exposures"] = len(user_rooms[user_id])
        room_scores = defaultdict(list)
        for row in subset:
            room_scores[row["room_id"]].append(row["focal_score"])
        segments[policy] = {
            "rooms": len(room_scores), "complete_tables": len(subset),
            "rounds": len(all_rounds),
            "focal_score_total": sum(row["focal_score"] for row in subset),
            "focal_score_per_table": statistics.mean(row["focal_score"] for row in subset),
            "room_score_per_table_sd": (statistics.stdev(sum(scores) / len(scores)
                                                           for scores in room_scores.values())
                                        if len(room_scores) > 1 else None),
            "focal_strict_first_tables": sum(row["focal_strict_first"] for row in subset),
            "focal_round_wins": sum(row["winner_is_focal"] for row in all_rounds),
            "opponent_round_wins": sum(row["winner_is_opponent"] for row in all_rounds),
            "drawn_rounds": sum(not row["winner_is_focal"] and not row["winner_is_opponent"]
                                for row in all_rounds),
            "opponent_winning_fan_mean": statistics.mean(opponent_fans) if opponent_fans else None,
            "opponent_winning_fan_observed": len(opponent_fans),
            "focal_winning_fan_mean": statistics.mean(focal_fans) if focal_fans else None,
            "opponent_winning_draw_count_median": (statistics.median(opponent_win_draws)
                                                   if opponent_win_draws else None),
            "focal_winning_draw_count_median": (statistics.median(focal_win_draws)
                                                if focal_win_draws else None),
            "opponent_final_score_per_seat_table": statistics.mean(
                opponent["final_score"] for opponent in opponents),
            "focal_claims_per_round": sum(row["focal_claims"] for row in subset) / len(all_rounds),
            "opponent_claims_per_round_per_player": (sum(row["opponent_claims"] for row in subset)
                                                     / (3 * len(all_rounds))),
            "opponent_seat_exposures": len(opponent_ids),
            "distinct_opponent_user_ids": len(set(opponent_ids)),
            "opponent_ids_seen_at_least_twice": sum(n >= 2 for n in Counter(opponent_ids).values()),
            "opponent_profiles": dict(per_user),
        }
    return {"expected_tables": len(expected), "downloaded_tables": len(rows),
            "missing_tables": len(missing), "missing_room_batches": missing,
            "segments": segments, "tables": rows}


def main() -> None:
    """先核对 R18；旧 V2 档案齐全时再给同口径的跨时期描述。"""
    r18 = analyze_campaign(expected_r18(), source_index(
        _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-history-redownload-20260923")))
    v2_source = source_index(_project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/v2-history-redownload-20260923"))
    v2 = analyze_campaign(expected_v2(), v2_source) if len(v2_source) == 400 else None
    r18_ids = {user for row in r18["tables"] for user in row["opponent_user_ids"]}
    v2_ids = {user for row in v2["tables"] for user in row["opponent_user_ids"]} if v2 else set()
    body = {"schema": "r18-real-opponent-recheck/1", "r18": r18, "historical_v2": v2,
            "cross_period_opponent_user_id_overlap": len(r18_ids & v2_ids) if v2 else None,
            "caveat": "跨时期对手画像受我方策略、匹配时段与指南版本混杂；同桌表现不构成对手独立实力评级。"}
    OUT.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
