#!/usr/bin/env python3
"""G145：复核普通型爆头机会差是否只是正常摸打暴露量差。"""

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


HERE = Path(__file__).resolve().parent
G69_WINDOWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_windows.jsonl.gz')
G69_ROUNDS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_rounds.jsonl.gz')
G69_RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_result.json')
G138 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g138-official-plain-baotou-opportunity-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g145-opportunity-exposure-and-entry-20260928/result.json')
PEERS = ("xuanwu_2346", "tengshe_0638")


def sha(path: Path) -> str:
    """计算既有官方证据或本脚本的原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path: Path):
    """逐行读取压缩的已核官方座位单局或正常摸打记录。"""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def hand_key(row: dict) -> tuple:
    """以强手、房、完整桌、单局和座位身份连接证据。"""
    return (row["peer"], row["room"], row["game_id"], row["round_no"],
            row["actor"])


def main() -> None:
    """仅做描述性对账；结果不得当作替换弃牌策略的因果证据。"""
    if OUT.exists():
        raise FileExistsError("G145 已有证据，拒绝覆盖")
    g138 = json.loads(G138.read_text(encoding="utf-8"))
    g69 = json.loads(G69_RESULT.read_text(encoding="utf-8"))
    if (g138["actor_hands"] != 5120 or g138["normal_draw_discard_windows"] != 36080
            or g69["round_count"] != 5120 or g69["window_count"] != 36080):
        raise ValueError("G69/G138 冻结母体不一致")
    rounds = {hand_key(row): row for row in lines(G69_ROUNDS)}
    if len(rounds) != 5120:
        raise ValueError("G69 座位单局键重复或缺失")
    windows: dict[tuple, list[dict]] = defaultdict(list)
    for row in lines(G69_WINDOWS):
        key = hand_key(row)
        if key not in rounds:
            raise ValueError("正常摸打窗口没有已核座位单局")
        windows[key].append(row)
    if sum(map(len, windows.values())) != 36080:
        raise ValueError("G69 正常摸打窗口数漂移")
    for key, row in rounds.items():
        if len(windows[key]) != row["clean_windows"]:
            raise ValueError("G69 单局正常摸打窗口数漂移")
    first = {hand_key(row): row for row in g138["first_plain_baotou_rows"]}
    if len(first) != 239 or not first.keys() <= rounds.keys():
        raise ValueError("G138 首次机会身份重复或缺失")

    by_peer = {}
    for peer in PEERS:
        rooms = sorted({key[1] for key in rounds if key[0] == peer})
        actors = {}
        for actor in ("peer", "us"):
            subset = [(key, row) for key, row in rounds.items()
                      if key[0] == peer and key[4] == actor]
            opportunity = [first[key] for key, _ in subset if key in first]
            ordinary_first = []
            first_ready_by_white = Counter()
            baotou_after_first_ready_by_white = Counter()
            capacity_by_white = Counter()
            for key, _ in subset:
                offered = next((row for row in sorted(windows[key],
                                                      key=lambda item: item["draw_seq"])
                                if row["actual"]["plain_capacity"] > 0), None)
                if offered is not None:
                    ordinary_first.append(offered)
                    white = "2plus" if offered["white_before"] >= 2 else str(
                        offered["white_before"])
                    first_ready_by_white[white] += 1
                    capacity_by_white[white] += offered["actual"]["plain_capacity"]
                    if key in first and offered["draw_seq"] < first[key]["first_draw_seq"]:
                        baotou_after_first_ready_by_white[white] += 1
            same_white_meld_and_tenpai = sum(
                row["previous_normal_draw"] is not None
                and row["first_white_before"] == row["previous_normal_draw"]["white_before"]
                and row["first_meld_count"] == row["previous_normal_draw"]["meld_count"]
                and row["previous_normal_draw"]["chosen_standard_shanten"] == 0
                and row["first_chosen_standard_shanten"] == 0
                for row in opportunity)
            count = Counter()
            for key, row in subset:
                count["hands"] += 1
                count["windows"] += len(windows[key])
                count["first_plain_baotou_hands"] += key in first
            published = g138["hand_groups"][f"{peer}/{actor}"]
            if (count["hands"] != published["hands"]
                    or count["first_plain_baotou_hands"] != published[
                        "plain_baotou/hands_offered"]
                    or len(ordinary_first) != g69["round_groups"][f"{peer}/{actor}/all"][
                        "plain_ready_rounds"]):
                raise ValueError("G145 首次机会或普通型一摸入口不能与旧证据对账")
            early = g138["window_groups"][f"{peer}/{actor}/turn_le6"]
            late = g138["window_groups"][f"{peer}/{actor}/turn_ge7"]
            if early["windows"] + late["windows"] != count["windows"]:
                raise ValueError("G145 行动序号窗数不守恒")
            actors[actor] = {
                **count,
                "first_plain_baotou_per_100_hands": round(
                    100 * count["first_plain_baotou_hands"] / count["hands"], 4),
                "windows_le6": early["windows"],
                "windows_ge7": late["windows"],
                "plain_baotou_opportunity_windows_le6": early[
                    "plain_baotou/opportunity_yes"],
                "plain_baotou_opportunity_windows_ge7": late[
                    "plain_baotou/opportunity_yes"],
                "first_plain_ready_hands": len(ordinary_first),
                "first_plain_ready_mean_capacity": round(
                    sum(r["actual"]["plain_capacity"] for r in ordinary_first)
                    / len(ordinary_first), 4),
                "first_plain_ready_mean_action_ordinal": round(
                    sum(r["action_ordinal"] for r in ordinary_first)
                    / len(ordinary_first), 4),
                "first_plain_ready_by_white": dict(first_ready_by_white),
                "baotou_after_first_ready_by_white": dict(
                    baotou_after_first_ready_by_white),
                "first_plain_ready_mean_capacity_by_white": {
                    white: round(capacity_by_white[white] / n, 4)
                    for white, n in first_ready_by_white.items()},
                "first_baotou_from_prior_plain_ready": sum(
                    row["previous_normal_draw"] is not None
                    and row["previous_normal_draw"]["chosen_standard_shanten"] == 0
                    for row in opportunity),
                "first_baotou_same_white_meld_tenpai_to_tenpai":
                    same_white_meld_and_tenpai,
            }
        room_flags = Counter()
        for room in rooms:
            peer_hands = g138["room_hand_groups"][f"{peer}/{room}/peer"][
                "plain_baotou/hands_offered"]
            us_hands = g138["room_hand_groups"][f"{peer}/{room}/us"][
                "plain_baotou/hands_offered"]
            peer_windows = g138["room_window_groups"][f"{peer}/{room}/peer"]["windows"]
            us_windows = g138["room_window_groups"][f"{peer}/{room}/us"]["windows"]
            room_flags["more_opportunity_with_no_more_windows"] += (
                peer_hands > us_hands and peer_windows <= us_windows)
            room_flags["more_opportunity"] += peer_hands > us_hands
            room_flags["fewer_windows"] += peer_windows < us_windows
        by_peer[peer] = {"rooms": len(rooms), "actors": actors,
                         "room_flags": dict(room_flags)}
    result = {
        "schema": "g145-opportunity-exposure-and-entry/1",
        "inputs_sha256": {"g69_windows": sha(G69_WINDOWS),
                          "g69_rounds": sha(G69_ROUNDS),
                          "g69_result": sha(G69_RESULT),
                          "g138": sha(G138),
                          "script": sha(Path(__file__))},
        "peers": by_peer,
        "boundary": "同房官方轨迹的事后描述；摸打窗口数、第一次普通胡入口及首次爆头机会均受手牌、对手和终局截尾影响，不是同牌山策略因果效应。公开剩余容量不是牌墙概率。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(by_peer, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
