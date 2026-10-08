#!/usr/bin/env python3
"""G14：两条首弃路线在全部公开可有自然进张后的理想化第二弃牌分布。"""

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
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
import g13_two_draw_baotou_support as g13
import g14_white_reserve_frontier as frontier_math
from hangma_bot.hangma.hand_analysis import _chiitoi_pairs
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
FRONTIER = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-natural-second-discard-20260927')
NATURAL = tuple(TILE_ORDER[:33])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(hand: Counter) -> tuple[int, ...]:
    """生产规范牌序；只把手牌计数送入生产成面数学。"""

    return counts_from_tiles(tuple(Tile(code) for code in TILE_ORDER
                                   for _ in range(hand[code])))


@lru_cache(maxsize=400_000)
def _natural_width(natural: tuple[int, ...], melds: int, need: int) -> int:
    """下一自然摸牌可使全留白缺口下降的物理牌种数。"""

    result = 0
    for i, code in enumerate(NATURAL):
        if natural[i] == 4:
            continue
        drawn = natural[:i] + (natural[i] + 1,) + natural[i + 1:]
        result += frontier_math._need(drawn, 0, 4 - melds) < need
    return result


@lru_cache(maxsize=400_000)
def _best_second(full: tuple[int, ...], melds: int) -> tuple:
    """普通型/七对最佳向听优先，再最大化全留白自然进度和宽度。"""

    if sum(full) != 14 - 3 * melds:
        raise ValueError("第二本人摸牌后暗牌数不合法")
    whites = full[33]
    options = []
    for i, code in enumerate(NATURAL):
        if full[i] == 0:
            continue
        after = full[:i] + (full[i] - 1,) + full[i + 1:]
        natural = after[:33]
        standard = frontier_math._need(natural, whites, 4 - melds) - 1
        seven = (6 - _chiitoi_pairs(natural, whites)) if melds == 0 else None
        combined = standard if seven is None else min(standard, seven)
        need = frontier_math._need(natural, 0, 4 - melds)
        options.append((combined, need, code, natural, standard, seven))
    if not options:
        raise ValueError("保留所有白板后没有自然牌可弃")
    best_combined = min(item[0] for item in options)
    options = [item for item in options if item[0] == best_combined]
    best_need = min(item[1] for item in options)
    options = [item for item in options if item[1] == best_need]
    chosen = min(options, key=lambda item: (
        -_natural_width(item[3], melds, item[1]), item[2]))
    return (chosen[0], chosen[1], _natural_width(chosen[3], melds, chosen[1]),
            chosen[4], chosen[5], chosen[2], whites)


def _capacity(hand_after: Counter, discards: Counter, exposed: Counter,
              action: str) -> dict[str, int]:
    """沿用 G14 的公开容量上界口径，首弃追加到河后重算。"""

    visible = discards.copy()
    visible[action.split(":", 1)[1]] += 1
    amounts = {}
    for code in NATURAL:
        amount = 4 - hand_after[code] - max(visible[code], exposed[code])
        if not 0 <= amount <= 4:
            raise ValueError("自然牌本人及公开计数越界")
        amounts[code] = amount
    return amounts


def _window(full: Counter, melds: int, parent_action: str, alternate_action: str,
            discards: Counter, exposed: Counter) -> dict:
    """对两条首弃路线枚举相同自然摸牌；不读实际未来摸牌。"""

    parent = g11._after_discard(full, parent_action)
    alternate = g11._after_discard(full, alternate_action)
    if parent is None or alternate is None or parent["白"] != alternate["白"]:
        raise ValueError("首弃不能保持同数白板")
    pcap = _capacity(parent, discards, exposed, parent_action)
    acap = _capacity(alternate, discards, exposed, alternate_action)
    weights = {code: min(pcap[code], acap[code]) for code in NATURAL}
    total = sum(weights.values())
    if total == 0:
        return {"common_public_capacity_upper": 0}
    result = Counter()
    types = Counter()
    second_same = 0
    for code, weight in weights.items():
        if weight == 0:
            continue
        pfull = parent.copy()
        afull = alternate.copy()
        pfull[code] += 1
        afull[code] += 1
        p = _best_second(_counts(pfull), melds)
        a = _best_second(_counts(afull), melds)
        result["natural_need_delta_weighted"] += weight * (p[1] - a[1])
        result["natural_width_delta_weighted"] += weight * (a[2] - p[2])
        result["combined_shanten_delta_weighted"] += weight * (a[0] - p[0])
        result["standard_shanten_delta_weighted"] += weight * (a[3] - p[3])
        if a[4] is not None and p[4] is not None:
            result["seven_shanten_delta_weighted"] += weight * (a[4] - p[4])
        comparison = ("better_natural_need" if a[1] < p[1] else
                      "worse_natural_need" if a[1] > p[1] else
                      "equal_need_wider" if a[2] > p[2] else
                      "equal_need_narrower" if a[2] < p[2] else "equal")
        result[comparison + "_capacity"] += weight
        result["combined_worse_capacity"] += weight * (a[0] > p[0])
        result["seven_worse_capacity"] += weight * (
            a[4] is not None and p[4] is not None and a[4] > p[4])
        types[comparison] += 1
        second_same += p[5] == a[5]
    return {"common_public_capacity_upper": total,
            "draw_tile_types": sum(weight > 0 for weight in weights.values()),
            "second_same_tile_types": second_same,
            "weighted": dict(sorted(result.items())),
            "type_counts": dict(sorted(types.items())),
            "parent_capacity_upper": sum(pcap.values()),
            "alternative_capacity_upper": sum(acap.values()),
            "capacity_mismatch_tile_types": sum(pcap[code] != acap[code] for code in NATURAL)}


def main() -> None:
    """扫描冻结父代官方审计；保存逐窗结果，不读未来事件和结算。"""

    if OUT.exists():
        raise SystemExit("G14 下一摸打分布已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    frontier = json.loads((_project_file(_PROJECT_ROOT, FRONTIER / "result.json")).read_text(encoding="utf-8"))
    if (frontier.get("outcome_blind") is not True or
            frontier["parent_source_sha256"] != frozen["parent_source_sha256"] or
            frontier["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz"))):
        raise ValueError("冻结父代或 G14 前沿身份漂移")
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            if key in targets:
                raise ValueError("G14 前沿窗口重复")
            targets[key] = row
    if len(targets) != frontier["counts"]["any_natural_frontier_improvement"]:
        raise ValueError("G14 前沿窗口母体漂移")
    output = []
    counts = Counter()
    groups = defaultdict(Counter)
    scopes = defaultdict(set)
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
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("G14 目标窗口重叠或房间错配")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            parent_action = target["parent_action"]
            alternate_action = target["alternative_action"]
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != parent_action or
                    accepted.get(context["decision_id"]) != parent_action or
                    parent_action not in legal or alternate_action not in legal or
                    (raw.get("window_key") or {}).get("phase") != "draw"):
                raise ValueError("目标父代接受或备选合法性漂移")
            observation = raw["observation"]
            parsed = g11._hand(observation)
            if parsed is None:
                raise ValueError("目标不再是正常摸打")
            full, _, melds = parsed
            discards, exposed = g13._public_counts(observation)
            value = _window(full, melds, parent_action, alternate_action,
                            discards, exposed)
            if value["common_public_capacity_upper"] == 0:
                counts["zero_common_capacity"] += 1
                continue
            label = "g11_same" if target["same_action_g11"] else "other"
            weighted = value["weighted"]
            cap = value["common_public_capacity_upper"]
            result = {"room_id": room["room_id"], "game_id": key[0],
                      "round_no": key[1], "trigger_seq": key[2],
                      "white_count": target["parent_frontier"]["whites_held"],
                      "parent_action": parent_action,
                      "alternative_action": alternate_action,
                      "old_g11_same_action": target["same_action_g11"],
                      **value,
                      "mean_natural_need_gain": weighted["natural_need_delta_weighted"] / cap,
                      "mean_natural_width_gain": weighted["natural_width_delta_weighted"] / cap,
                      "mean_combined_shanten_cost": weighted["combined_shanten_delta_weighted"] / cap,
                      "boundary": "公开容量加权只作支持面代理；第二弃牌理想化，不是完整合法后继或收益"}
            output.append(result)
            counts["matched"] += 1
            groups[label]["windows"] += 1
            scopes[label].add(key[0])
            groups[label]["positive_second_width"] += result["mean_natural_width_gain"] > 0
            groups[label]["zero_second_width"] += result["mean_natural_width_gain"] == 0
            groups[label]["negative_second_width"] += result["mean_natural_width_gain"] < 0
            groups[label]["positive_natural_need"] += result["mean_natural_need_gain"] > 0
            groups[label]["combined_worse_capacity"] += weighted["combined_worse_capacity"]
            groups[label]["seven_worse_capacity"] += weighted["seven_worse_capacity"]
            groups[label]["total_capacity"] += cap
            groups[label]["sum_width_gain_weighted"] += weighted["natural_width_delta_weighted"]
            groups[label]["sum_need_gain_weighted"] += weighted["natural_need_delta_weighted"]
    if seen != set(targets) or counts["matched"] + counts["zero_common_capacity"] != len(targets):
        raise ValueError("G14 目标没有全量覆盖")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for row in output:
                compressed.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")) + "\n").encode("utf-8"))
    summary = {"schema": "g14-natural-second-discard/1", "outcome_blind": True,
               "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
               "source_frontier_result_sha256": _sha(_project_file(_PROJECT_ROOT, FRONTIER / "result.json")),
               "source_frontier_rows_sha256": _sha(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz")),
               "script_sha256": _sha(Path(__file__)),
               "rows_sha256": _sha(rows_path),
               "counts": dict(sorted(counts.items())),
               "groups": {name: {**dict(sorted(group.items())),
                                  "complete_tables": len(scopes[name])}
                          for name, group in sorted(groups.items())},
               "boundary": "全部自然摸牌来自决策时公开容量上界，不是牌墙概率；第二弃牌只作理想化形状搜索，不是响应后的官方合法后继；不能估计整桌收益"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
