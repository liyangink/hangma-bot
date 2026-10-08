#!/usr/bin/env python3
"""G61 探索性复盘：强手严格弃牌分歧中的不动用白板自然进张。"""

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
import hashlib
import json
from pathlib import Path

import g11_longitudinal_route_audit as g11
import g13_two_draw_baotou_support as g13
import g14_white_reserve_frontier as g14


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/white_reserve_profile.json')


def sha(path: Path) -> str:
    """核验既有逐窗证据未变；摘要不包含未来结果。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def marker(row: dict) -> tuple[str, int, int]:
    """房内唯一的官方小局和摸牌序号。"""

    return row["game_id"], row["round_no"], row["draw_seq"]


def main() -> None:
    """仅研究结果盲 G61 正常摸打，输出不可直接当作候选收益。"""

    if OUT.exists():
        raise SystemExit("G61 白板保留画像已存在，拒绝覆盖")
    batch_path, profile_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json"), _project_file(_PROJECT_ROOT, SOURCE / "shape_profile.json")
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if (batch["outcome_labels_opened"] is not False or
            profile["outcome_labels_opened"] is not False or
            profile["batch_sha256"] != sha(batch_path)):
        raise ValueError("G61 来源或结果盲边界漂移")
    strict = defaultdict(dict)
    for row in profile["strict_discard_rows"]:
        key = (row["peer"], row["room"], *marker(row))
        if key in strict:
            raise ValueError("严格弃牌窗口重复")
        strict[key] = row
    counts: dict[str, Counter] = defaultdict(Counter)
    room_scopes: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    examples = defaultdict(list)
    consumed = set()
    for unit, record in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G61 逐窗摘要不符")
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            key = (peer, room, *marker(window))
            if key not in strict:
                continue
            if key in consumed:
                raise ValueError("严格弃牌窗口二次使用")
            consumed.add(key)
            row = strict[key]
            observation = window["observation"]
            hand = g11._hand(observation)
            if hand is None:
                raise ValueError("G61 正常摸打不满足 G11 前态约束")
            full, _, melds = hand
            discards, exposed = g13._public_counts(observation)
            alternatives = {}
            for label, action in (("parent", row["parent_action"]),
                                  ("strong", row["strong_action"])):
                after = g11._after_discard(full, action)
                if after is None:
                    raise ValueError("G61 弃牌不在本人手牌")
                alternatives[label] = g14._frontier(
                    after, melds, discards, exposed, action.split(":", 1)[1])
            parent, strong = alternatives["parent"], alternatives["strong"]
            groups = (peer + "/all", peer + "/white_" +
                      ("2plus" if row["white_before"] >= 2 else str(row["white_before"])))
            for group in groups:
                c = counts[group]
                c["strict_discard_rows"] += 1
                if parent["whites_held"] != strong["whites_held"]:
                    c["different_whites_after_discard"] += 1
                    continue
                c["same_whites_after_discard"] += 1
                if row["delta"]["ordinary_delta"] != 0 or row["delta"]["combined_delta"] != 0:
                    c["ordinary_or_combined_layer_changed"] += 1
                    continue
                c["same_ordinary_and_combined_layer"] += 1
                p_need = parent["standard_natural_draws_needed_by_reserved_whites"][-1]
                s_need = strong["standard_natural_draws_needed_by_reserved_whites"][-1]
                diff_need = s_need - p_need
                c["all_white_reserved_need_better" if diff_need < 0 else
                  "all_white_reserved_need_worse" if diff_need > 0 else
                  "all_white_reserved_need_same"] += 1
                if diff_need != 0:
                    continue
                code_diff = (strong["all_whites_reserved_natural_tile_types"] -
                             parent["all_whites_reserved_natural_tile_types"])
                cap_diff = (strong["all_whites_reserved_public_capacity_upper"] -
                            parent["all_whites_reserved_public_capacity_upper"])
                c["reserved_natural_codes_wider" if code_diff > 0 else
                  "reserved_natural_codes_narrower" if code_diff < 0 else
                  "reserved_natural_codes_same"] += 1
                c["reserved_natural_capacity_wider" if cap_diff > 0 else
                  "reserved_natural_capacity_narrower" if cap_diff < 0 else
                  "reserved_natural_capacity_same"] += 1
                if code_diff > 0:
                    room_scopes[group]["natural_codes_wider"].add(room)
                    if cap_diff <= 0:
                        c["natural_codes_wider_without_capacity_gain"] += 1
                        room_scopes[group]["natural_codes_wider_without_capacity_gain"].add(room)
                    if row["delta"]["ordinary_support_codes_delta_same_layer"] <= 0:
                        c["natural_wider_without_production_ordinary_code_gain"] += 1
                        room_scopes[group]["natural_wider_without_production_ordinary_code_gain"].add(room)
                    if len(examples[group]) < 6:
                        examples[group].append({
                            "room": room, "game_id": row["game_id"],
                            "round_no": row["round_no"], "draw_seq": row["draw_seq"],
                            "parent_action": row["parent_action"],
                            "strong_action": row["strong_action"],
                            "white_after": parent["whites_held"],
                            "natural_code_delta": code_diff,
                            "natural_capacity_delta": cap_diff,
                            "production_ordinary_code_delta": row["delta"]["ordinary_support_codes_delta_same_layer"],
                            "parent_score_gap": row["parent_score_gap"]})
    if len(consumed) != len(strict):
        raise ValueError("G61 严格弃牌窗口未全部核验")
    result = {"schema": "g61-white-reserve-action-profile/1",
              "batch_sha256": sha(batch_path), "shape_profile_sha256": sha(profile_path),
              "script_sha256": sha(Path(__file__)), "outcome_labels_opened": False,
              "counts": {key: dict(sorted(value.items())) for key, value in sorted(counts.items())},
              "room_coverage": {key: {name: len(rooms) for name, rooms in value.items()}
                                for key, value in sorted(room_scopes.items())},
              "examples": dict(examples),
              "boundary": "探索性行为画像；全保留白板的自然缺口和公开容量不是未来牌墙概率，强手选择不是因果收益。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "room_coverage": result["room_coverage"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
