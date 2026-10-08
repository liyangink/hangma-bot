#!/usr/bin/env python3
"""G220：把 G65 官方后继标签与 G61 可见抓打资格逐窗对账。"""

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
from hashlib import sha256
import json
from pathlib import Path
import random

import g203_future_catch_play_reach as g203
import g219_two_draw_settlement_route as g219


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G65 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g65-next-draw-survival-20260928')
G64 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g64-strong-win-timing-20260928/result.json')
G219 = g219.OUT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g220-future-qualification-audit-20260929/result.json')
BOOT_SEED = 20261229220
BOOT_REPS = 10_000


def digest(path: Path) -> str:
    """把归档来源与审计执行器绑定到原始字节。"""
    return sha256(path.read_bytes()).hexdigest()


def key(peer: str, room: str, row: dict, seq_name: str = "draw_seq") -> tuple:
    """同一强手可见正常摸牌窗口的全局身份。"""
    return (peer, room, row["game_id"], row["round_no"],
            row[seq_name], row["seat"])


def windows() -> dict[tuple, dict]:
    """只读 G61 玩家观察；逐房核冻结哈希与全量窗口数。"""
    source = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    if (source["schema"] != "g61-strong-draw-action-atlas-batch/1"
            or source["outcome_labels_opened"] is not False
            or source["totals"]["legal_verified_windows"] != 17_938):
        raise ValueError("G61 冻结母体漂移")
    index = {}
    for unit, record in source["units"].items():
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (peer + "--" + room) / "windows.json")
        if digest(path) != record["windows_sha256"]:
            raise ValueError("G61 强手房可见观察摘要漂移")
        rows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        if len(rows) != record["counts"]["legal_verified_windows"]:
            raise ValueError("G61 强手房观察数量漂移")
        for row in rows:
            identity = key(peer, room, row)
            if identity in index:
                raise ValueError("G61 正常摸牌窗口重复")
            index[identity] = row
    if len(index) != 17_938:
        raise ValueError("G61 总可见窗口数漂移")
    return index


def labels() -> dict[tuple, dict]:
    """只用 G65 已冻结事件标签，不重新取未来牌谱或生成反事实。"""
    result = json.loads((_project_file(_PROJECT_ROOT, G65 / "result.json")).read_text(encoding="utf-8"))
    path = _project_file(_PROJECT_ROOT, G65 / "rows.jsonl.gz")
    if (result["schema"] != "g65-next-draw-survival-result/1"
            or digest(path) != result["rows_sha256"]):
        raise ValueError("G65 后继标签摘要漂移")
    index = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            identity = key(row["peer"], row["room"], row)
            if identity in index:
                raise ValueError("G65 同一官方根重复")
            index[identity] = row
    if len(index) != 17_938:
        raise ValueError("G65 标签行数漂移")
    return index


def hand_status() -> dict[tuple, str]:
    """未重建下一摸时只标本局最终赢家，绝不冒称下一摸立刻胡。"""
    doc = json.loads(G64.read_text(encoding="utf-8"))
    if doc["schema"] != "g64-strong-win-timing-result/1" or len(doc["rows"]) != 2560:
        raise ValueError("G64 已归档强手单局母体漂移")
    result = {}
    for row in doc["rows"]:
        identity = (row["peer"], row["room"], row["game_id"], row["round_no"])
        if identity in result:
            raise ValueError("G64 同一强手单局重复")
        result[identity] = row["actors"][row["peer"]]["status"]
    return result


def successor(identity: tuple, label: dict, visible: dict,
              final_status: dict) -> str:
    """先分终局／下一摸；仅在下一摸有可见观察时判抓打资格。"""
    if label["label"] == 0:
        if label["terminal_kind"] not in ("other_win", "wall_draw"):
            raise ValueError("G65 下一摸前终点未知")
        return "terminal/" + label["terminal_kind"]
    if label["label"] != 1 or label["terminal_kind"] != "next_own_draw":
        raise ValueError("G65 下一摸事件非二值标签")
    future = identity[:4] + (label["next_seq"], identity[5])
    observation = visible.get(future)
    if observation is None:
        eventual = final_status[identity[:4]]
        if eventual not in ("win", "other_win", "draw"):
            raise ValueError("G64 终局类型未知")
        return "unreconstructed/eventual_" + eventual
    mode = g203.window_mode(observation["observation"])
    if mode not in ("free", "restricted", "unknown"):
        raise ValueError("未来玩家资格非生产规则三态")
    if mode == "free" and observation["catch_play"] and (
            observation["observation"]["rule_state"]["catch_play_owner_seat"]
            != observation["seat"]):
        raise ValueError("G61 抓打标记与生产资格不一致")
    return "reconstructed/" + mode


def summarize(rows: list[tuple[str, str]]) -> dict:
    """缺观察保持未知；完整分母给出自由与受限的保守界。"""
    counts = Counter(event for _, event in rows)
    total = len(rows)
    if not total:
        raise ValueError("G220 空来源层")
    next_draw = sum(value for name, value in counts.items()
                    if name.startswith(("reconstructed/", "unreconstructed/")))
    free = counts["reconstructed/free"]
    restricted = counts["reconstructed/restricted"]
    unknown = next_draw - free - restricted
    if sum(counts.values()) != total or next_draw < free + restricted:
        raise ValueError("G220 后继分区不守恒")
    by_room = defaultdict(Counter)
    for room, event in rows:
        by_room[room][event] += 1
    rooms = sorted(by_room)
    sample = []
    rng = random.Random(BOOT_SEED + total)
    for _ in range(BOOT_REPS):
        draws = [by_room[rooms[rng.randrange(len(rooms))]] for _ in rooms]
        known_free = sum(item["reconstructed/free"] for item in draws)
        known_restricted = sum(item["reconstructed/restricted"] for item in draws)
        if known_free + known_restricted:
            sample.append(known_free / (known_free + known_restricted))
    sample.sort()
    return {
        "windows": total, "rooms": len(rooms),
        "events": dict(sorted(counts.items())),
        "next_draw": next_draw,
        "mode_reconstructed": free + restricted,
        "free_among_reconstructed": free / (free + restricted)
                                    if free + restricted else None,
        "free_among_reconstructed_room_bootstrap_95": [
            sample[int(.025 * len(sample))], sample[int(.975 * len(sample)) - 1]
        ] if sample else None,
        "free_share_lower_bound_among_all_next_draws": free / next_draw
                                                      if next_draw else None,
        "restricted_share_upper_bound_among_all_next_draws": (restricted + unknown) / next_draw
                                                            if next_draw else None,
    }


def g219_chain(visible: dict, labeled: dict, final_status: dict) -> dict:
    """G219 已看行为窗仅作相关性核查；不得用于选择候选权重。"""
    doc = json.loads(G219.read_text(encoding="utf-8"))
    if doc["schema"] != "g219-two-draw-settlement-route/1" or len(doc["rows"]) != 64:
        raise ValueError("G219 已看窗口身份漂移")
    first = []
    second = []
    by_peer = defaultdict(list)
    for row in doc["rows"]:
        identity = key(row["peer"], row["room"], row)
        if identity not in labeled or identity not in visible:
            raise ValueError("G219 根未在 G61/G65 官方事实中")
        event = successor(identity, labeled[identity], visible, final_status)
        first.append((row["room"], event))
        by_peer[row["peer"]].append((row["room"], event))
        if event.startswith("reconstructed/"):
            next_identity = identity[:4] + (labeled[identity]["next_seq"], identity[5])
            if next_identity not in labeled:
                raise ValueError("已重建第一摸没有 G65 后继标签")
            second.append((row["room"], successor(
                next_identity, labeled[next_identity], visible, final_status)))
    return {"first": summarize(first), "second_given_reconstructed_first": summarize(second),
            "by_peer_first": {peer: summarize(rows) for peer, rows in sorted(by_peer.items())}}


def main() -> None:
    """只审计已冻结父代／强手轨迹的资格与终局，不改变生产策略。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    visible = windows()
    labeled = labels()
    if visible.keys() != labeled.keys():
        raise ValueError("G61 与 G65 根窗口不能一一对账")
    final_status = hand_status()
    groups = defaultdict(list)
    for identity, row in labeled.items():
        layer = "postclaim" if row["features"]["own_melds"] >= 1 else "closed"
        event = successor(identity, row, visible, final_status)
        groups[layer].append((row["room"], event))
        groups[row["peer"] + "/" + layer].append((row["room"], event))
    result = {
        "schema": "g220-future-qualification-audit/1",
        "source_sha256": {"script": digest(Path(__file__)),
                          "g61": digest(_project_file(_PROJECT_ROOT, G61 / "result.json")),
                          "g65_result": digest(_project_file(_PROJECT_ROOT, G65 / "result.json")),
                          "g65_rows": digest(_project_file(_PROJECT_ROOT, G65 / "rows.jsonl.gz")),
                          "g64": digest(G64), "g219": digest(G219),
                          "catch_play_production": digest(
                              _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/catch_play.py"))},
        "groups": {name: summarize(rows) for name, rows in sorted(groups.items())},
        "g219_actual_strong_path": g219_chain(visible, labeled, final_status),
        "boundary": "已执行强手动作及父代局结果的观察性后继；缺重建下一摸不填成自由或受限，最终赢家不等于该次摸牌立即胡；不是备选弃牌的反事实概率或候选收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"postclaim": result["groups"]["postclaim"],
                      "g219_first": result["g219_actual_strong_path"]["first"],
                      "g219_second": result["g219_actual_strong_path"][
                          "second_given_reconstructed_first"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
