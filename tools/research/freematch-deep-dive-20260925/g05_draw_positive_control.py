#!/usr/bin/env python3
"""用我方生产审计逐窗核对官方牌谱重建的摸牌观察与合法候选。"""

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
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_melds(value: list[list[dict]]) -> list[list[dict]]:
    """吃副露牌序没有规则语义；其它字段逐字核对。"""
    return [[dict(meld, tiles=sorted(meld["tiles"])) for meld in seat] for seat in value]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--audit-jsonl", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("正控结果已有文件，拒绝覆盖")
    rows = json.loads(args.windows.read_text(encoding="utf-8"))["windows"]
    keys = {(r["game_id"], r["round_no"], r["draw_seq"]) for r in rows}
    observations = {}
    plans = {}
    for line in args.audit_jsonl.open(encoding="utf-8"):
        if '"decision_input"' not in line and '"decision_planned"' not in line:
            continue
        entry = json.loads(line)
        context = entry.get("context") or {}
        key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
        if key not in keys:
            continue
        if entry.get("kind") == "decision_input":
            request = (entry.get("payload") or {}).get("request") or {}
            if (request.get("observation") or {}).get("phase") == "draw":
                observations[key] = request
        elif entry.get("kind") == "decision_planned":
            candidates = (entry.get("payload") or {}).get("effective_candidates") or []
            if candidates:
                plans[key] = candidates[0]["action_key"]
    mismatches = Counter()
    examples = {}

    def check(name: str, same: bool, key: tuple) -> None:
        if not same:
            mismatches[name] += 1
            examples.setdefault(name, {"game_id": key[0], "round_no": key[1], "seq": key[2]})

    for row in rows:
        key = (row["game_id"], row["round_no"], row["draw_seq"])
        request = observations.get(key)
        if request is None:
            check("missing_production_input", False, key)
            continue
        ours = row["observation"]
        official = request["observation"]
        for field in (
            "seat", "phase", "dealer_seat", "turn_seat", "responding_seats",
            "drawn_tile", "hand_counts", "remaining_tile_count", "scores",
            "discards", "chain_piao", "gang_draw",
        ):
            check("observation." + field, ours.get(field) == official.get(field), key)
        check("observation.my_hand_multiset",
              Counter(ours["my_hand"]) == Counter(official["my_hand"]), key)
        check("observation.melds",
              normalized_melds(ours["melds"]) == normalized_melds(official["melds"]), key)
        for field in ("wealth_god", "baotou", "chain_count", "catch_play",
                      "catch_play_owner_seat"):
            check("observation.rule_state." + field,
                  ours["rule_state"].get(field) == official["rule_state"].get(field), key)
        for field in ("seat", "tile"):
            check("observation.last_discard." + field,
                  (ours.get("last_discard") or {}).get(field)
                  == (official.get("last_discard") or {}).get(field), key)
        # 官方快照的 last_discard.seq 有时用快照水位；物理弃牌序号
        # 单独记录，不把两种时钟基准混成语义错误。
        if ((ours.get("last_discard") or {}).get("seq")
                != (official.get("last_discard") or {}).get("seq")):
            mismatches["last_discard_seq_semantics"] += 1
        official_legal = {candidate["action_key"] for candidate in request["rules"]["legal_candidates"]}
        check("legal_action_keys", set(row["legal_action_keys"]) == official_legal, key)
        check("parent_top_action", row["parent_top_action"] == plans.get(key), key)
    result = {
        "schema": "g05-draw-positive-control/1", "window_count": len(rows),
        "matched_production_inputs": sum(key in observations for key in keys),
        "matched_production_plans": sum(key in plans for key in keys),
        "mismatches": dict(sorted(mismatches.items())), "examples": examples,
        "windows_sha256": sha(args.windows), "audit_jsonl_sha256": sha(args.audit_jsonl),
        "outcome_labels_opened": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                   indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
