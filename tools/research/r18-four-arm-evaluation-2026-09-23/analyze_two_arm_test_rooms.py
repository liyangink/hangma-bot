"""从官方赛后原文对账两臂测试房，保留房/桌聚类与座位、庄家构成。"""

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

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean


ROOT = _PROJECT_ROOT
STRATEGY_MAP = _project_file(_PROJECT_ROOT, ROOT / "datamart/strategy-map.json")
ARMS = ("r18_integrated_positive_v2", "v2_hu_upgrade_v1")


def analyze_pool(pool: Path, identity_strategy: dict[str, str]) -> dict:
    """逐官方桌赛核对 SHA、身份、每局结算及两臂净分守恒。"""

    tables = []
    seen = set()
    paths = sorted(pool.glob("official/*/official/dl-*/events.json"))
    if not paths:
        raise ValueError("没有官方赛后牌谱: " + str(pool))
    for path in paths:
        source = json.loads(path.with_name("source.json").read_text(encoding="utf-8"))
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["original_sha256"]:
            raise ValueError("官方原文 SHA 不符: " + str(path))
        doc = json.loads(path.read_text(encoding="utf-8"))
        game_id, room_id = doc["game_id"], doc["room_id"]
        if game_id in seen or doc.get("status") != "finished":
            raise ValueError("重复或未完成桌赛: " + game_id)
        seen.add(game_id)
        if source["room_id"] != room_id or source["batch"] != doc["batch"]:
            raise ValueError("来源房/批次与官方牌谱不符: " + game_id)
        seats = [identity_strategy.get(item["user_id"]) for item in doc["seats"]]
        if len(seats) != 4 or Counter(seats) != Counter({ARMS[0]: 2, ARMS[1]: 2}):
            raise ValueError("四席不是冻结的两臂各二: " + game_id)
        summaries = {row["round_no"]: row for row in doc["rounds"]}
        ended = []
        claims = Counter()
        for block in doc["blocks"]:
            if block.get("truncated"):
                raise ValueError("官方事件截断: " + game_id)
            for event in block["events"]:
                kind, seat = event["type"], event.get("seat")
                if kind in ("chi", "peng", "gang") and isinstance(seat, int):
                    claims[seats[seat]] += 1
                if kind == "round_ended":
                    ended.append(event)
        rounds = []
        for event in ended:
            data = event["data"]
            no = data["round_no"]
            if no in summaries and summaries[no]["scores"] != data["scores"]:
                raise ValueError("单局摘要与权威结算不符: " + game_id)
            winner_seat = None if data["draw"] else event["seat"]
            dealer_seat = data["dealer"]
            delta = data["scores"]
            if len(delta) != 4 or sum(delta) != 0:
                raise ValueError("结算向量不守恒: " + game_id)
            rounds.append({"round_no": no,
                           "net": {arm: sum(delta[seat] for seat in range(4) if seats[seat] == arm)
                                   for arm in ARMS},
                           "winner_arm": seats[winner_seat] if winner_seat is not None else None,
                           "dealer_arm": seats[dealer_seat],
                           "winning_fan": data.get("fan") if winner_seat is not None else None})
        if sorted(item["round_no"] for item in rounds) != list(range(1, 9)):
            raise ValueError("不是完整 8 局桌赛: " + game_id)
        table_net = {arm: sum(item["net"][arm] for item in rounds) for arm in ARMS}
        if sum(table_net.values()) != 0:
            raise ValueError("两臂完整桌净分不守恒: " + game_id)
        tables.append({"game_id": game_id, "room_id": room_id, "batch": doc["batch"],
                       "arm_by_seat": seats, "arm_net": table_net,
                       "claims": {arm: claims[arm] for arm in ARMS}, "rounds": rounds})
    room_ids = {table["room_id"] for table in tables}
    if len(room_ids) != 1 or len(tables) != 10:
        raise ValueError("一个池必须恰好一房十个完整桌赛")
    all_rounds = [item for table in tables for item in table["rounds"]]
    aggregate = {}
    for arm in ARMS:
        fans = [item["winning_fan"] for item in all_rounds if item["winner_arm"] == arm]
        aggregate[arm] = {
            "net": sum(table["arm_net"][arm] for table in tables),
            "wins": len(fans),
            "winning_fan_mean": mean(fans) if fans else None,
            "dealer_rounds": sum(item["dealer_arm"] == arm for item in all_rounds),
            "dealer_wins": sum(item["dealer_arm"] == arm and item["winner_arm"] == arm
                               for item in all_rounds),
            "claims": sum(table["claims"][arm] for table in tables),
            "seat_hands": {str(seat): 8 * sum(table["arm_by_seat"][seat] == arm for table in tables)
                           for seat in range(4)},
        }
    return {"pool": str(pool.relative_to(ROOT)), "room_id": next(iter(room_ids)),
            "tables": tables, "aggregate": aggregate}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    mapping = json.loads(STRATEGY_MAP.read_text(encoding="utf-8"))["identities"]
    rooms = [analyze_pool(path.resolve(), mapping) for path in args.pool]
    result = {"schema": "official-two-arm-test-room/1", "rooms": rooms,
              "limitations": ["每房十桌共享匹配时段与四个身份；单局不是独立样本。",
                              "两臂在同一桌相互对抗，跨房牌山不配对；这里不计算因果置信区间。",
                              "上周榜强手不在全自家测试房；本结果只供接线和机制线索。"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
