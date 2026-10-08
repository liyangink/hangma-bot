#!/usr/bin/env python3
"""G11 结果盲审计：父代已接受的鸣/过和胡/继续窗口的公开路线冲突。"""

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

import g8_public_response_training_rows as source


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
TRAIN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/result.json')
TRAIN_ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/rows.jsonl.gz')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-cross-family-action-atlas-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _int(facts: dict, field: str) -> int | None:
    value = facts.get(field)
    return value if type(value) is int else None


def _capacity(facts: dict, field: str) -> int | None:
    entries = facts.get(field)
    if not isinstance(entries, list):
        return None
    amounts = [entry.get("remaining_estimate") for entry in entries]
    return sum(amounts) if all(type(value) is int for value in amounts) else None


def _family(key: str) -> str:
    return key.split(":", 1)[0]


def _complete_ids() -> set[str]:
    """只从既有完整牌谱训练清单取 game_id；绝不读其标签列。"""

    train = json.loads(TRAIN.read_text(encoding="utf-8"))
    if _sha(TRAIN_ROWS) != train["rows_gzip_sha256"]:
        raise ValueError("完整官方桌赛 ID 来源摘要漂移")
    ids: set[str] = set()
    with gzip.open(TRAIN_ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            ids.add(json.loads(line)["game_id"])
    if len(ids) != train["counts"]["official_games"]:
        raise ValueError("完整官方桌赛数量不符")
    return ids


def main() -> None:
    """只使用动作前观察与合法事实；最终计数按核验完整桌 ID 去重。"""

    if OUT.exists():
        raise SystemExit("G11 跨动作族图谱已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    complete_ids = _complete_ids()
    totals = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    windows: dict[str, set[tuple]] = defaultdict(set)
    by_room: dict[str, dict] = {}
    examples: dict[str, list[dict]] = defaultdict(list)
    marker_details: dict[str, Counter] = defaultdict(Counter)
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代决策字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码摘要漂移")
        accepted = source._accepted(decision_file)
        room_counts = Counter()
        seen = set()
        for context, request, plan in source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if game_id not in complete_ids:
                continue
            phase = (request.get("window_key") or {}).get("phase")
            if phase == "draw":
                family = "draw"
            elif isinstance(phase, str) and phase.startswith("response_"):
                family = "response"
            else:
                continue
            window = (game_id, context.get("round_no"), context.get("trigger_seq"), phase)
            if window in seen:
                raise ValueError("核验完整桌内动作窗口重复")
            seen.add(window)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                room_counts["unranked"] += 1
                continue
            parent_key = ranked[0].get("action_key")
            if accepted.get(context.get("decision_id")) != parent_key:
                room_counts["parent_not_accepted"] += 1
                continue
            legal = {item["action_key"]: item.get("facts") or {} for item in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            if len(legal) != len((request.get("rules") or {}).get("legal_candidates") or []):
                raise ValueError("规则合法动作键重复")
            if parent_key not in legal:
                raise ValueError("父代已接受动作不在规则合法候选")
            parent = legal[parent_key]
            parent_kind = _family(parent_key)
            parent_score = ranked[0].get("total_score")
            observation = request.get("observation") or {}
            seat = observation.get("seat")
            melds = observation.get("melds")
            own_meld_count = (len(melds[seat]) if type(seat) is int
                              and isinstance(melds, list) and 0 <= seat < len(melds)
                              and isinstance(melds[seat], list) else None)
            white_count = (observation.get("my_hand") or []).count("白")
            room_counts[f"accepted_{family}_{parent_kind}"] += 1
            if family == "draw" and parent_kind != "hu":
                continue
            if family == "response" and parent_kind not in ("pass", "chi", "peng", "gang"):
                continue
            for item in ranked[1:]:
                alt_key = item.get("action_key")
                if alt_key not in legal:
                    raise ValueError("父代评分备选不在规则合法候选")
                alt_kind = _family(alt_key)
                if family == "response":
                    if parent_kind == "pass" and alt_kind in ("chi", "peng", "gang"):
                        direction = "pass_to_claim"
                    elif parent_kind in ("chi", "peng", "gang") and alt_kind == "pass":
                        direction = "claim_to_pass"
                    else:
                        continue
                elif alt_kind in ("discard", "gang"):
                    direction = "hu_to_continue"
                else:
                    continue
                alt = legal[alt_key]
                alt_score = item.get("total_score")
                markers = [direction]
                parent_std = _int(parent, "standard_shanten_after")
                alt_std = _int(alt, "standard_shanten_after")
                parent_cap = _capacity(parent, "standard_useful_tiles")
                alt_cap = _capacity(alt, "standard_useful_tiles")
                parent_total = _capacity(parent, "useful_tiles")
                alt_total = _capacity(alt, "useful_tiles")
                if parent_std is not None and alt_std is not None:
                    if alt_std < parent_std:
                        markers.append(direction + "_standard_faster")
                    elif alt_std == parent_std and parent_cap is not None and alt_cap is not None:
                        if alt_cap > parent_cap:
                            markers.append(direction + "_same_standard_more_support")
                        elif alt_cap == parent_cap:
                            markers.append(direction + "_same_standard_same_support")
                else:
                    room_counts[direction + "_standard_unknown"] += 1
                if alt.get("baotou_after") is True and parent.get("baotou_after") is False:
                    markers.append(direction + "_baotou_gain")
                if (direction == "pass_to_claim" and alt_kind == "chi"
                        and own_meld_count is not None and own_meld_count > 0
                        and parent_std is not None and alt_std == parent_std
                        and parent_cap is not None and alt_cap is not None and alt_cap > parent_cap
                        and _int(parent, "shanten_after") is not None
                        and _int(alt, "shanten_after") == _int(parent, "shanten_after")
                        and parent_total is not None and alt_total is not None
                        and alt_total >= parent_total):
                    markers.append("pass_to_chi_open_standard_local_dominance")
                for marker in markers:
                    windows[marker].add(window)
                    scopes[marker].add(game_id)
                    detail = marker_details[marker]
                    detail["alternative_" + alt_kind] += 1
                    detail["phase_" + phase] += 1
                    detail["parent_open_" + ("unknown" if own_meld_count is None else
                                              "yes" if own_meld_count > 0 else "no")] += 1
                    detail["white_" + ("2plus" if white_count >= 2 else str(white_count))] += 1
                    for name, field in (("combined", "shanten_after"),
                                        ("seven_pairs", "seven_pairs_shanten_after")):
                        parent_value, alt_value = _int(parent, field), _int(alt, field)
                        relation = ("unknown" if parent_value is None or alt_value is None else
                                    "faster" if alt_value < parent_value else
                                    "same" if alt_value == parent_value else "slower")
                        detail[name + "_" + relation] += 1
                    total_relation = ("unknown" if parent_total is None or alt_total is None else
                                      "higher" if alt_total > parent_total else
                                      "same" if alt_total == parent_total else "lower")
                    detail["combined_support_" + total_relation] += 1
                    parent_seven = _int(parent, "seven_pairs_shanten_after")
                    detail["parent_seven_" + ("unknown" if parent_seven is None else
                                              "competitive" if parent_std is not None
                                              and parent_seven <= parent_std else "behind")] += 1
                    if type(parent_score) in (int, float) and type(alt_score) in (int, float):
                        gap = float(parent_score) - float(alt_score)
                        detail["parent_score_gap_" + ("zero" if gap == 0 else
                                                      "le_10" if 0 < gap <= 10 else
                                                      "gt_10" if gap > 10 else "negative")] += 1
                    else:
                        detail["parent_score_gap_unknown"] += 1
                    if len(examples[marker]) < 5:
                        examples[marker].append({"room_id": room["room_id"],
                                                 "game_id": game_id, "round_no": window[1],
                                                 "trigger_seq": window[2], "phase": phase,
                                                 "parent_action": parent_key,
                                                 "alternative_action": alt_key,
                                                 "parent_standard_shanten": parent_std,
                                                 "alternative_standard_shanten": alt_std,
                                                 "parent_standard_support": parent_cap,
                                                 "alternative_standard_support": alt_cap})
        by_room[room["room_id"]] = dict(sorted(room_counts.items()))
        totals.update(room_counts)
    result = {"schema": "g11-cross-family-action-atlas/1", "outcome_blind": True,
              "source_frozen_rooms_sha256": _sha(FROZEN),
              "source_complete_ids_sha256": _sha(TRAIN_ROWS),
              "source_parent_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "official_rooms": len(frozen["rooms"]),
              "counts": dict(sorted(totals.items())),
              "scopes": {name: {"action_windows": len(windows[name]),
                                "complete_tables_with_parent_trace_entry": len(ids),
                                "required_conditional_gain_for_plus2_all_tables":
                                    2 * len(complete_ids) / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "marker_details": {name: dict(sorted(counts.items()))
                                 for name, counts in sorted(marker_details.items())},
              "first_examples": dict(examples), "by_room": by_room,
              "boundary": "动作前自然父代轨迹的合法取舍覆盖；不读取终局/未来墙选窗口；非候选策略、非收益或严格上界。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("first_examples", "by_room", "marker_details")}, ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
