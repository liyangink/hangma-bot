#!/usr/bin/env python3
"""G178：用生产无白手牌数学核普通型有效张的自然进张语义。"""

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

import c31_action_layer_gap as c31
import g101_visible_route_audit as g101
from hangma_bot.hangma import hand_analysis, public_tile_counts
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G178-NATURAL-VS-STANDARD-SUPPORT-PREREG-2026-09-28.md')
SOURCE = g101.SOURCE / "rows.jsonl.gz"
SELECTION = g101.SOURCE / "result.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g178-natural-vs-standard-support-20260928/result.json')


def sha(path: Path) -> str:
    """返回输入或程序原始字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _drop(full, code: str):
    """只用于已由规则确认合法的弃牌根；不自行推定合法性。"""

    held = list(full)
    for i, tile in enumerate(held):
        if tile.code == code:
            del held[i]
            return tuple(held)
    raise ValueError("G178 生产合法弃牌不在完整本人暗手")


def natural(root, unseen: tuple, meld_count: int) -> tuple[int, dict[str, int]]:
    """白板不当百搭，直接调用唯一生产普通型缺口求解器。"""

    counts = counts_from_tiles(root)
    natural_counts = counts[:33]
    need = hand_analysis._need_std(natural_counts, 0, 4 - meld_count, True)
    support = {}
    for index, code in enumerate(TILE_ORDER[:33]):
        capacity = unseen[index]
        if capacity is None or type(capacity) is not int or capacity < 0:
            raise ValueError("G178 非白公开未知容量缺失")
        if capacity == 0:
            continue
        after_draw = (natural_counts[:index] + (natural_counts[index] + 1,)
                      + natural_counts[index + 1:])
        if hand_analysis._need_std(after_draw, 0, 4 - meld_count, True) < need:
            support[code] = capacity
    return need, support


def production(facts) -> dict[str, int]:
    """生产普通型有效张去白后仅保留正公开容量，未知即失败。"""

    if facts is None or facts.standard_useful_tiles is None:
        raise ValueError("G178 生产普通型有效张未知")
    support = {}
    for item in facts.standard_useful_tiles:
        if item.code == "白":
            continue
        amount = item.remaining_estimate
        if (item.code in support or type(amount) is not int or
                not 0 <= amount <= 4):
            raise ValueError("G178 生产逐码容量重复或无效")
        if amount > 0:
            support[item.code] = amount
    return support


def _direction(before: int, after: int) -> str:
    """按冻结父代与备选的有符号差分类。"""

    return "up" if after > before else "down" if after < before else "equal"


def compare_one(row: dict) -> dict:
    """重建一个官方行动前观察，核全部合法非白弃牌及目标动作对。"""

    obs = observation_from_json(row["observation"])
    if obs.phase != "draw" or obs.seat != row["seat"]:
        raise ValueError("G178 冻结观察身份漂移")
    rules = c31.RULES.analyze(obs, value_limits=c31.VALUE_LIMITS)
    legal = {item.action_key: item for item in rules.legal_candidates}
    if (len(legal) != len(rules.legal_candidates) or
            row["parent_action"] not in legal or row["alternate_action"] not in legal):
        raise ValueError("G178 冻结父代或备选已不合法")
    full = _build_context(obs).full_hand()
    meld_count = len(obs.melds[obs.seat])
    unseen = public_tile_counts.count_unseen_tiles(obs)
    if any(value is None for value in unseen[:33]):
        raise ValueError("G178 当前公开未知池不完整")
    if sum(tile.code == "白" for tile in full) != row["white_before"]:
        raise ValueError("G178 行动前白板数漂移")
    actions = {}
    for key, item in legal.items():
        if not key.startswith("discard:") or key == "discard:白":
            continue
        code = key.split(":", 1)[1]
        root = _drop(full, code)
        need, direct = natural(root, unseen, meld_count)
        existing = production(item.facts)
        only_direct = {tile: amount for tile, amount in direct.items()
                       if tile not in existing}
        only_existing = {tile: amount for tile, amount in existing.items()
                         if tile not in direct}
        changed = {tile: (direct[tile], existing[tile]) for tile in direct.keys() & existing.keys()
                   if direct[tile] != existing[tile]}
        actions[key] = {
            "natural_need": need,
            "standard_shanten_after": item.facts.standard_shanten_after,
            "natural_capacity": sum(direct.values()),
            "natural_types": len(direct),
            "production_capacity": sum(existing.values()),
            "production_types": len(existing),
            "equal_vector": direct == existing,
            "natural_only": only_direct,
            "production_only": only_existing,
            "capacity_mismatch": changed,
        }
    parent = actions.get(row["parent_action"])
    alternate = actions.get(row["alternate_action"])
    if parent is None or alternate is None:
        raise ValueError("G178 冻结目标动作不是非白弃牌")
    pair = {}
    for measure in ("capacity", "types"):
        before_direct = parent["natural_" + measure]
        after_direct = alternate["natural_" + measure]
        before_existing = parent["production_" + measure]
        after_existing = alternate["production_" + measure]
        pair[measure] = {
            "natural": _direction(before_direct, after_direct),
            "production": _direction(before_existing, after_existing),
            "natural_delta": after_direct - before_direct,
            "production_delta": after_existing - before_existing,
        }
    return {"key": row["key"], "white_before": row["white_before"],
            "parent_action": row["parent_action"],
            "alternate_action": row["alternate_action"],
            "actions": actions, "pair": pair}


def main() -> None:
    """完整 203 窗一次性核对；结果不覆盖，未知原样保存。"""

    if OUT.exists():
        raise FileExistsError("G178 结果已存在，拒绝覆盖")
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    if selection["outcome_labels_opened"] is not False:
        raise ValueError("G178 官方目标窗不再结果盲")
    rows = [json.loads(line) for line in gzip.open(SOURCE, "rt", encoding="utf-8")]
    if len(rows) != 203 or len(rows) != selection["counts"]["target_windows"]:
        raise ValueError("G178 203 窗冻结母体漂移")
    output = []
    summary = defaultdict(Counter)
    for row in rows:
        layer = ("0" if row["white_before"] == 0 else
                 "1" if row["white_before"] == 1 else "2plus")
        try:
            item = compare_one(row)
            item["status"] = "complete"
            counts = summary[layer]
            counts["windows_complete"] += 1
            for action in item["actions"].values():
                counts["actions"] += 1
                counts["equal_vectors"] += int(action["equal_vector"])
                counts["natural_only_actions"] += bool(action["natural_only"])
                counts["natural_only_codes"] += len(action["natural_only"])
                counts["natural_only_capacity"] += sum(action["natural_only"].values())
                counts["production_only_actions"] += bool(action["production_only"])
                counts["production_only_codes"] += len(action["production_only"])
                counts["production_only_capacity"] += sum(action["production_only"].values())
                counts["capacity_mismatch_actions"] += bool(action["capacity_mismatch"])
            for measure, pair in item["pair"].items():
                counts[measure + "/direction_" + (
                    "equal" if pair["natural"] == pair["production"] else "different")] += 1
        except (ValueError, TypeError) as exc:
            item = {"key": row["key"], "white_before": row["white_before"],
                    "status": "unavailable", "reason": type(exc).__name__ + ": " + str(exc)[:180]}
            summary[layer]["windows_unavailable"] += 1
        output.append(item)
    payload = {
        "schema": "g178-natural-vs-standard-support/1",
        "source_sha256": {name: sha(path) for name, path in {
            "plan": PLAN, "script": Path(__file__), "selection": SELECTION,
            "source_rows": SOURCE,
            "hand_math": Path(hand_analysis.__file__),
            "public_counts": Path(public_tile_counts.__file__),
        }.items()},
        "source_windows": len(rows),
        "summary": {key: dict(sorted(counts.items())) for key, counts in sorted(summary.items())},
        "rows": output,
        "boundary": "结果盲官方观察上的生产数学字段对账；自然容量是公开未知上界，不是牌墙概率、策略收益或发布证据。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
