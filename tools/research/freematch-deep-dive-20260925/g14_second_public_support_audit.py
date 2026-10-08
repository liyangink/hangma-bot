#!/usr/bin/env python3
"""G14：冻结 417 窗的第二弃牌公开自然支持面和普通型逐牌代价。"""

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
import g11_longitudinal_route_audit as g11
import g13_two_draw_baotou_support as g13
import g14_natural_second_discard_distribution as earlier
import g14_white_reserve_frontier as frontier_math


HERE = Path(__file__).resolve().parent
FRONTIER = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
EARLIER = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-natural-second-discard-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-second-public-support-20260927')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public_support(after: Counter, melds: int, discards: Counter,
                    exposed: Counter, first: str, second: str) -> tuple[int, int]:
    """第二弃牌后，下一自然摸牌能减少全留白缺口的公开支持面。"""

    visible = discards.copy()
    visible[first.split(":", 1)[1]] += 1
    visible[second] += 1
    counts = earlier._counts(after)
    natural = counts[:33]
    need = frontier_math._need(natural, 0, 4 - melds)
    kinds = 0
    capacity = 0
    for i, code in enumerate(earlier.NATURAL):
        amount = 4 - after[code] - max(visible[code], exposed[code])
        if not 0 <= amount <= 4:
            raise ValueError("第二弃牌公开自然容量越界")
        if amount == 0:
            continue
        drawn = natural[:i] + (natural[i] + 1,) + natural[i + 1:]
        if frontier_math._need(drawn, 0, 4 - melds) < need:
            kinds += 1
            capacity += amount
    return kinds, capacity


def _window(full: Counter, melds: int, parent_action: str, alternative_action: str,
            discards: Counter, exposed: Counter) -> dict:
    """重放旧量具固定选牌，新增普通型与公开宽度对账。"""

    parent = g11._after_discard(full, parent_action)
    alternative = g11._after_discard(full, alternative_action)
    if parent is None or alternative is None or parent["白"] != alternative["白"]:
        raise ValueError("冻结首弃不能保持同数白板")
    pcap = earlier._capacity(parent, discards, exposed, parent_action)
    acap = earlier._capacity(alternative, discards, exposed, alternative_action)
    weights = {code: min(pcap[code], acap[code]) for code in earlier.NATURAL}
    total = sum(weights.values())
    if total == 0:
        raise ValueError("旧量具目标窗口共同公开容量为零")
    values = Counter()
    for drawn, weight in weights.items():
        if weight == 0:
            continue
        pfull = parent.copy()
        afull = alternative.copy()
        pfull[drawn] += 1
        afull[drawn] += 1
        pbest = earlier._best_second(earlier._counts(pfull), melds)
        abest = earlier._best_second(earlier._counts(afull), melds)
        values["physical_width_delta_weighted"] += weight * (abest[2] - pbest[2])
        values["standard_worse_capacity"] += weight * (abest[3] > pbest[3])
        values["standard_better_capacity"] += weight * (abest[3] < pbest[3])
        pafter = g11._after_discard(pfull, "discard:" + pbest[5])
        aafter = g11._after_discard(afull, "discard:" + abest[5])
        if pafter is None or aafter is None:
            raise ValueError("旧量具第二弃牌不在条件手牌")
        pkind, pamount = _public_support(pafter, melds, discards, exposed,
                                        parent_action, pbest[5])
        akind, aamount = _public_support(aafter, melds, discards, exposed,
                                        alternative_action, abest[5])
        values["public_width_delta_weighted"] += weight * (akind - pkind)
        values["public_capacity_delta_weighted"] += weight * (aamount - pamount)
        values["public_width_better_capacity"] += weight * (akind > pkind)
        values["public_width_worse_capacity"] += weight * (akind < pkind)
    return {"common_public_capacity_upper": total,
            "weighted": dict(sorted(values.items())),
            "public_width_gain": values["public_width_delta_weighted"] / total,
            "public_capacity_gain": values["public_capacity_delta_weighted"] / total}


def main() -> None:
    """只读冻结父代当前窗口及 G14 已定行动，结果留摘要与逐窗证据。"""

    if OUT.exists():
        raise SystemExit("G14 第二弃牌公开支持面已存在，拒绝覆盖")
    old = json.loads((_project_file(_PROJECT_ROOT, EARLIER / "result.json")).read_text(encoding="utf-8"))
    new = json.loads((_project_file(_PROJECT_ROOT, FRONTIER / "result.json")).read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (old.get("outcome_blind") is not True or
            old["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, EARLIER / "rows.jsonl.gz")) or
            old["script_sha256"] != _sha(_project_file(_PROJECT_ROOT, HERE / "g14_natural_second_discard_distribution.py")) or
            new["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz")) or
            new["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("冻结来源、旧量具或父代身份漂移")
    frontier = {}
    with gzip.open(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            frontier[key] = row
    selected = {}
    with gzip.open(_project_file(_PROJECT_ROOT, EARLIER / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            prior = frontier[key]
            if (row["old_g11_same_action"] or prior["same_action_g10"] or
                    row["mean_natural_width_gain"] <= 0 or
                    row["weighted"]["combined_worse_capacity"] != 0 or
                    row["weighted"]["seven_worse_capacity"] != 0):
                continue
            selected[key] = row
    if len(selected) != 417:
        raise ValueError("探索性 417 窗入口漂移")
    rows = []
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            target = selected.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("417 窗重复或房间错配")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context["decision_id"]) != target["parent_action"] or
                    target["alternative_action"] not in legal or
                    (raw.get("window_key") or {}).get("phase") != "draw"):
                raise ValueError("417 窗父代行动或合法备选漂移")
            observation = raw["observation"]
            parsed = g11._hand(observation)
            if parsed is None:
                raise ValueError("417 窗不再能重建正常摸打")
            full, _, melds = parsed
            discards, exposed = g13._public_counts(observation)
            result = _window(full, melds, target["parent_action"],
                             target["alternative_action"], discards, exposed)
            if (result["common_public_capacity_upper"] != target["common_public_capacity_upper"] or
                    result["weighted"]["physical_width_delta_weighted"] !=
                    target["weighted"]["natural_width_delta_weighted"]):
                raise ValueError("旧物理宽度结果未能逐窗复现")
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "alternative_action": target["alternative_action"],
                         **result})
    if seen != set(selected):
        raise ValueError("417 窗未全量覆盖")
    reasons = Counter()
    for row in rows:
        standard_ok = row["weighted"]["standard_worse_capacity"] == 0
        width_ok = row["public_width_gain"] > 0
        capacity_ok = row["public_capacity_gain"] > 0
        reasons["standard_no_worse"] += standard_ok
        reasons["public_width_positive"] += width_ok
        reasons["public_capacity_positive"] += capacity_ok
        reasons["standard_and_public_width"] += standard_ok and width_ok
        reasons["standard_and_public_width_and_capacity"] += (
            standard_ok and width_ok and capacity_ok)
        reasons["standard_worse"] += not standard_ok
        reasons["public_width_not_positive"] += not width_ok
    survivors = [row for row in rows if row["weighted"]["standard_worse_capacity"] == 0
                 and row["public_width_gain"] > 0]
    OUT.mkdir(parents=True)
    path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    summary = {"schema": "g14-second-public-support-audit/1", "outcome_blind": True,
               "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
               "source_frontier_rows_sha256": _sha(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz")),
               "source_second_result_sha256": _sha(_project_file(_PROJECT_ROOT, EARLIER / "result.json")),
               "source_second_rows_sha256": _sha(_project_file(_PROJECT_ROOT, EARLIER / "rows.jsonl.gz")),
               "script_sha256": _sha(Path(__file__)), "rows_sha256": _sha(path),
               "selected_windows": len(rows),
               "selected_complete_tables": len({row["game_id"] for row in rows}),
               "surviving_windows": len(survivors),
               "surviving_complete_tables": len({row["game_id"] for row in survivors}),
               "surviving_rooms": len({row["room_id"] for row in survivors}),
               "counts": dict(sorted(reasons.items())),
               "boundary": "旧量具固定第二弃牌；公开容量仍含他家暗手，不是牌墙概率；没有真实响应/合法后继和 P28 行为去重，更没有整桌收益"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
