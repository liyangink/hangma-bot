#!/usr/bin/env python3
"""G254：用官方八局牌谱追回被误判为无结算的自由赛房。

默认只打印预演结果；--apply 才原子更新 watchdog 账本。官方牌谱必须是
指定七房、每房十桌、每桌八个唯一的 round_ended，且 game_ended 与逐局分一致。
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

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "scripts")))
import auto_match_watchdog as watchdog  # noqa: E402


SOURCE = _project_file(_PROJECT_ROOT, ROOT / "datasets/derived/g254-orphan-replay-20260929")
SOURCE_BUNDLE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g254-orphan-reconciliation-20260929/official-replays.tar.gz')
LEDGER = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
ORPHANS = frozenset({
    "a_97223c4196d6", "a_0b6ef066e8ce", "a_d97fd0b3b69f",
    "a_70d832b7afc6", "a_c4d50da7902c", "a_3611a37c5ea4",
    "a_17686e254cbd",
})


def sha(path: Path) -> str:
    """返回文件字节 SHA-256，绑定官方报文与操作前账本。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(source: Path):
    """从本机下载目录或已冻结压缩包读取仅有完整来源身份的牌谱。"""

    if source.is_file():
        with tarfile.open(source, "r:gz") as archive:
            members = {member.name: member for member in archive.getmembers()
                       if member.isfile()}
            for name in sorted(members):
                if not name.endswith("/events.json"):
                    continue
                meta_name = name.removesuffix("events.json") + "source.json"
                if meta_name not in members:
                    raise ValueError(f"压缩包缺来源：{name}")
                event_file = archive.extractfile(members[name])
                meta_file = archive.extractfile(members[meta_name])
                if event_file is None or meta_file is None:
                    raise ValueError(f"压缩包文件不可读：{name}")
                yield name, event_file.read(), meta_name, meta_file.read()
        return
    if not source.is_dir():
        raise FileNotFoundError(source)
    for path in sorted(source.glob("official/dl-*/events.json")):
        meta_path = path.with_name("source.json")
        if not meta_path.is_file():
            # 429 可能发生在 events.json 已落盘、source.json 尚未写入之后；
            # 这种目录只是失败诊断，不具有可计分的官方来源身份。
            continue
        yield (str(path.relative_to(source)), path.read_bytes(),
               str(meta_path.relative_to(source)), meta_path.read_bytes())


def official_games(source: Path) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """逐桌核官方八局和四座结算，返回每房完整十桌及输入摘要。"""

    games: dict[str, dict[str, dict]] = defaultdict(dict)
    hashes = {}
    for label, event_bytes, meta_label, meta_bytes in source_files(source):
        doc = json.loads(event_bytes)
        meta = json.loads(meta_bytes)
        room, gid = doc.get("room_id"), doc.get("game_id")
        batch = meta.get("batch")
        if (room not in ORPHANS or type(batch) is not int or batch not in range(10)
                or meta.get("room_id") != room or gid != f"{room}_r1_b{batch}_t0"
                or doc.get("status") != "finished"):
            raise ValueError(f"官方来源身份／完成状态不符：{label}")
        seats = [row.get("user_id") for row in doc.get("seats") or []]
        if len(seats) != 4 or seats.count(watchdog.ME) != 1:
            raise ValueError(f"本人身份或四座不完整：{gid}")
        seat = seats.index(watchdog.ME)
        endings: dict[int, list[dict]] = defaultdict(list)
        final_scores = []
        for block in doc.get("blocks") or []:
            round_no = block.get("round_no")
            for event in block.get("events") or []:
                if event.get("type") == "round_ended":
                    endings[round_no].append(event)
                elif event.get("type") == "game_ended":
                    final_scores.append((event.get("data") or {}).get("final_scores"))
        if sorted(endings) != list(range(1, 9)) or any(len(x) != 1 for x in endings.values()):
            raise ValueError(f"官方八个单局终局不唯一：{gid}")
        totals = [0, 0, 0, 0]
        for round_no in range(1, 9):
            end = endings[round_no][0]
            scores = (end.get("data") or {}).get("scores")
            if (not isinstance(scores, list) or len(scores) != 4 or
                    any(type(value) is not int for value in scores) or sum(scores) != 0):
                raise ValueError(f"官方第 {round_no} 局四座分非法：{gid}")
            totals = [a + b for a, b in zip(totals, scores)]
        if len(final_scores) != 1 or final_scores[0] != totals:
            raise ValueError(f"官方桌末分与八局积分不符：{gid}")
        row = {"game_id": gid, "seat": seat, "final_score": totals[seat],
               "source": "official_recovered_round_ended"}
        if gid in games[room] and games[room][gid] != row:
            raise ValueError(f"重复下载的同桌积分冲突：{gid}")
        games[room][gid] = row
        hashes[label] = hashlib.sha256(event_bytes).hexdigest()
        hashes[meta_label] = hashlib.sha256(meta_bytes).hexdigest()
    if set(games) != ORPHANS or any(len(rows) != 10 for rows in games.values()):
        raise ValueError("指定房各十桌官方牌谱未完整补齐")
    return {room: [games[room][gid] for gid in sorted(games[room])]
            for room in sorted(games)}, hashes


def orphan_logs() -> dict[str, tuple[Path, dict, Path]]:
    """找到七个官方房对应的异常会话日志与审计目录。"""

    matched = {}
    for path in sorted((_project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog")).glob("session-*.log")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        result_lines = [line for line in lines if line.startswith("RESULT ")]
        if len(result_lines) != 1:
            continue
        result = json.loads(result_lines[0][7:])
        if result.get("terminal_reason") != "matching_unavailable":
            continue
        rel_audit = result.get("audit_dir")
        if not isinstance(rel_audit, str):
            continue
        audit = _project_file(_PROJECT_ROOT, ROOT / rel_audit)
        if not audit.is_dir():
            continue
        room = watchdog.room_id_of(str(audit))
        if room in ORPHANS:
            if room in matched:
                raise ValueError(f"同一异常房有重复会话日志：{room}")
            matched[room] = path, result, audit
    if set(matched) != ORPHANS:
        raise ValueError(f"七房异常会话日志未对齐：缺 {sorted(ORPHANS - set(matched))}")
    return matched


def reconcile(ledger: dict, games: dict[str, list[dict]], logs: dict,
              source: Path) -> tuple[dict, list[dict]]:
    """仅加入缺失的七房，并与已有审计终局逐桌核对。"""

    if ledger.get("campaign") != "r18-sse-freematch-campaign-20260925b":
        raise ValueError("watchdog 战役身份漂移")
    existing = {row["room_id"]: row for row in ledger.get("rooms") or []}
    if len(existing) != len(ledger.get("rooms") or []):
        raise ValueError("原账本已有重复房")
    if ledger.get("cumulative_total") != sum(row["room_subtotal"] for row in existing.values()):
        raise ValueError("原账本累计分与逐房分不符")
    added = []
    for room in sorted(ORPHANS):
        rows = games[room]
        total = sum(row["final_score"] for row in rows)
        log, result, audit = logs[room]
        for gid, outcome in watchdog.audit_outcomes(str(audit)).items():
            match = next((row for row in rows if row["game_id"] == gid), None)
            seat = outcome.get("seat")
            if (match is None or type(seat) is not int or seat != match["seat"] or
                    outcome["final_scores"][seat] != match["final_score"]):
                raise ValueError(f"异常房审计终局与官方牌谱冲突：{gid}")
        if room in existing:
            if (existing[room].get("room_subtotal") != total or
                    {row["game_id"]: row["final_score"] for row in existing[room]["games"]}
                    != {row["game_id"]: row["final_score"] for row in rows}):
                raise ValueError(f"已有房与官方追回牌谱冲突：{room}")
            continue
        row = {"room_id": room,
               "session_log": str(log.relative_to(ROOT)),
               "audit_dir": str(audit.relative_to(ROOT)),
               "download_dir": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT)
               else str(source),
               "terminal_reason": result["terminal_reason"],
               "settlement_status": "official_recovered_complete",
               "room_subtotal": total, "games": rows}
        ledger.setdefault("rooms", []).append(row)
        added.append({"room_id": room, "room_subtotal": total,
                      "session_log": row["session_log"], "games": len(rows)})
    ledger["rooms"].sort(key=lambda row: row["session_log"])
    ledger["cumulative_total"] = sum(row["room_subtotal"] for row in ledger["rooms"])
    streak = 0
    for row in reversed(ledger["rooms"]):
        if row["room_subtotal"] < 0:
            streak += 1
        else:
            break
    ledger["current_lose_streak"] = streak
    return ledger, added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--source", type=Path,
                        default=SOURCE if SOURCE.is_dir() else SOURCE_BUNDLE)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report and args.report.exists():
        raise FileExistsError(f"拒绝覆盖既有报告：{args.report}")
    before_bytes = args.ledger.read_bytes()
    ledger = json.loads(before_bytes)
    before = {"rooms": len(ledger["rooms"]), "score": ledger["cumulative_total"],
              "sha256": hashlib.sha256(before_bytes).hexdigest()}
    games, hashes = official_games(args.source)
    logs = orphan_logs()
    ledger, added = reconcile(ledger, games, logs, args.source)
    after = {"rooms": len(ledger["rooms"]), "score": ledger["cumulative_total"],
             "lose_streak": ledger["current_lose_streak"]}
    report = {"schema": "g254-orphan-room-reconciliation/1",
              "applied": bool(args.apply and added),
              "before": before, "after": after, "added": added,
              "official_orphan_score": sum(sum(row["final_score"] for row in rows)
                                           for rows in games.values()),
              "source_sha256": hashes,
              "boundary": "七个官方已完成十桌八局房；异常会话有实分，不能按 matching_unavailable 视作作废。"}
    if args.apply and added:
        backup = args.ledger.with_name(args.ledger.name + ".before-g254-" +
                                       datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
        shutil.copy2(args.ledger, backup)
        ledger["updated_at"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        ledger.setdefault("reconciliations", []).append({
            "at": ledger["updated_at"], "reason": "G254 官方七房牌谱追回 matching_unavailable 漏账",
            "rooms": [row["room_id"] for row in added],
            "official_orphan_score": report["official_orphan_score"],
            "source_script_sha256": sha(Path(__file__)),
        })
        temp = args.ledger.with_suffix(args.ledger.suffix + ".g254.tmp")
        temp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        os.replace(temp, args.ledger)
        report["backup"] = str(backup.relative_to(ROOT)) if backup.is_relative_to(ROOT) else str(backup)
        report["after"]["sha256"] = sha(args.ledger)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                          sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"before": before, "after": after,
                      "added": added, "official_orphan_score": report["official_orphan_score"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
