#!/usr/bin/env python3
"""G28：结果盲恢复 C01 公开对手门，随后报告旧 G23 三摸诊断。"""

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

import g11_cross_family_action_atlas as atlas
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927')
ANSWER = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g27-glm-constrained-wave-20260927/c01_opponent_race.answer.txt')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g28-c01-context-gate-20260927')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g28-c01-context-gate-20260927/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g28-c01-context-gate-20260927/result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(action: str, arm: dict) -> tuple[int, int, str]:
    """按 C01 原答使用弃牌码与动作后本人暗手近邻数；非白动作。"""

    code = action.split(":", 1)[1]
    if code == "白":
        raise ValueError("G23 固定样本应无弃白动作")
    if code[-1] not in "wbt":
        return 0, 0, code
    rank, suit = int(code[0]), code[1]
    near = sum(count for tile, count in zip(TILE_ORDER, arm["counts34"])
               if tile[-1] == suit and abs(int(tile[0]) - rank) <= 2)
    edge = 1 if rank in (1, 9) else 2 if rank in (2, 8) else 3
    return near, edge, code


def gate(observation) -> tuple[bool, list[dict]]:
    """逐字实现 C01 提议的公开副露/弃河门，未推断暗手。"""

    levels = []
    for seat in range(4):
        if seat == observation.seat:
            continue
        melds = len(observation.melds[seat])
        river = observation.discards[seat]
        concentration = 0.0
        if len(river) >= 8:
            concentration = max((sum(tile.code.endswith(suit) for tile in river) / len(river)
                                 for suit in "wbt"), default=0.0)
        level = melds + int(len(river) >= 8 and concentration >= 0.6)
        levels.append({"seat": seat, "melds": melds, "river_tiles": len(river),
                       "max_suit_fraction": round(concentration, 4), "level": level})
    return max(item["level"] for item in levels) >= 2, levels


def main() -> None:
    """只恢复目标动作前观察；不读取隐藏牌/未来墙/赛果。"""

    if ROWS.exists() or RESULT.exists():
        raise SystemExit("G28 已有证据，拒绝覆盖")
    source_result = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    source_rows = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    if source_result["rows_sha256"] != sha(source_rows) or source_result["sampled_pairs"] != 184:
        raise ValueError("G23 冻结输入漂移")
    answer = json.loads(ANSWER.read_text(encoding="utf-8"))
    if not answer.get("name", "").startswith("c01_opponent_race"):
        raise ValueError("G27 C01 作者身份漂移")
    original = [json.loads(line) for line in gzip.open(source_rows, "rt", encoding="utf-8")]
    targets = {(row["game_id"], row["round_no"], row["trigger_seq"]): row for row in original}
    if len(targets) != 184:
        raise ValueError("G23 目标窗口重复")
    seen = {}
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    rooms = {row["room_id"] for row in original}
    for room in frozen["rooms"]:
        if room["room_id"] not in rooms:
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代动作审计大小漂移")
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            window = context.get("game_id"), context.get("round_no"), context.get("trigger_seq")
            target = targets.get(window)
            if target is None:
                continue
            if window in seen or target["room_id"] != room["room_id"]:
                raise ValueError("G28 窗口重复或房身份漂移")
            obs = observation_from_json(raw["observation"])
            is_open, levels = gate(obs)
            parent_key = key(target["parent_action"], target["parent"])
            alternative_key = key(target["alternative_action"], target["alternative"])
            choose_alt_without_gate = alternative_key < parent_key
            seen[window] = {"room_id": target["room_id"], "game_id": target["game_id"],
                            "round_no": target["round_no"], "trigger_seq": target["trigger_seq"],
                            "split": target["split"], "white_after": target["white_after"],
                            "parent_action": target["parent_action"],
                            "alternative_action": target["alternative_action"],
                            "parent_key": parent_key, "alternative_key": alternative_key,
                            "gate_open": is_open, "opponent_levels": levels,
                            "key_prefers_alternative": choose_alt_without_gate,
                            "gated_change": is_open and choose_alt_without_gate,
                            "teacher_delta_2": target["delta_2"],
                            "teacher_delta_3": target["delta_3"]}
    if len(seen) != 184:
        raise ValueError(f"G28 恢复动作前观察只有 {len(seen)}/184")
    rows = [seen[(row["game_id"], row["round_no"], row["trigger_seq"])] for row in original]
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        white = min(row["white_after"], 2)
        split = row["split"]
        for label, value in (("gate_open", row["gate_open"]),
                             ("ungated_change", row["key_prefers_alternative"]),
                             ("gated_change", row["gated_change"])):
            if value:
                counts[label] += 1
                counts[f"{label}_white_{white}"] += 1
                counts[f"{label}_{split}"] += 1
                tables[label].add(row["game_id"])
        if row["gated_change"]:
            sign = "positive" if row["teacher_delta_3"] > 0 else "negative" if row["teacher_delta_3"] < 0 else "equal"
            counts[f"gated_teacher_{sign}"] += 1
            counts[f"gated_teacher_{sign}_white_{white}"] += 1
            counts[f"gated_teacher_{sign}_{split}"] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
    result = {"schema": "g28-c01-context-gate/1", "outcome_blind_inputs": True,
              "source_g23_rows_sha256": sha(source_rows), "source_answer_sha256": sha(ANSWER),
              "probe_script_sha256": sha(Path(__file__)), "rows_sha256": sha(ROWS),
              "pairs": len(rows), "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "boundary": "既有G23样本和已探索的留出房，仅属筛查；三摸教师不是整桌净收益，门只看公开副露/弃河。"}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
