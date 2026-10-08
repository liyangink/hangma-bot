#!/usr/bin/env python3
"""G102：未来第一次摸白后，同一合法留白弃牌的普通／高番二摸路线对账。"""

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
import g52_shared_horizon as g52
import g99_joint_successor_route_audit as g99
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma import hand_analysis, progression, settlement, special_rules
from hangma_bot.hangma.candidate_facts import _remaining
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928/selection')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G102-WHITE-ARRIVAL-FAN-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g102-white-arrival-fan-20260928')


def sha(path: Path) -> str:
    """固定来源和算法字节身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drop(hand: tuple[Tile, ...], code: str) -> tuple[Tile, ...]:
    """仅供离线条件枝，去掉合法动作所弃的一张牌。"""
    held = list(hand)
    for index, tile in enumerate(held):
        if tile.code == code:
            del held[index]
            return tuple(held)
    raise ValueError("后继弃牌不在条件暗手")


def dissect_leaf(obs: object, root_action: str, leaf: dict) -> dict:
    """完全沿 G52 的同一张后继弃牌枚举第二摸，按生产番数拆账。"""
    root_discard = root_action.split(":", 1)[1]
    meld_count = len(obs.melds[obs.seat])
    context = _build_context(obs)
    root = drop(context.full_hand(), root_discard)
    root_baotou = progression.baotou_after_discard(root, meld_count)
    root_chain, root_piao = progression.chain_after_action(
        obs.rule_state.chain_count, obs.chain_piao, obs.rule_state.baotou,
        Discard(Tile(root_discard)),
    )
    if root_piao is None:
        raise ValueError("根弃牌后飘链未知")
    first_full = root + (Tile("白"),)
    first_discard = leaf["discard"]
    waiting = drop(first_full, first_discard)
    first_baotou = progression.baotou_after_draw(
        root_baotou, root, meld_count, Tile("白"), replacement=False,
    )
    chain, piao = progression.chain_after_discard(
        root_chain, root_piao, first_baotou, Tile(first_discard),
    )
    after_baotou = progression.baotou_after_discard(waiting, meld_count)
    public = count_public_tiles(obs)
    own_visible_whites = sum(tile.code == "白" for tile in obs.discards[obs.seat])
    missing_own_piao = max(0, (obs.chain_piao or 0) - own_visible_whites)
    new_public = Counter([root_discard, first_discard])
    waiting_counts = counts_from_tiles(waiting)
    counts = Counter()
    for code in TILE_ORDER:
        capacity = _remaining(code, waiting_counts, public, dict(new_public))
        if code == "白":
            capacity -= missing_own_piao
        if capacity < 0:
            raise ValueError("G102 公开容量和飘白矛盾")
        if capacity == 0:
            continue
        counts["total_capacity"] += capacity
        split = hand_analysis.win_split(waiting + (Tile(code),), meld_count)
        second_baotou = progression.baotou_after_draw(
            after_baotou, waiting, meld_count, Tile(code), replacement=False,
        )
        if split is None or special_rules.you_cai_bi_kao_block(
            c31.RULE_CONFIG.you_cai_bi_kao, split, second_baotou,
        ):
            continue
        result = settlement.settle_win(
            split, chain, piao, second_baotou, c31.RULE_CONFIG.base_score,
            obs.seat, obs.dealer_seat,
        )
        field = "special" if result.fan >= 2 else "ordinary"
        counts[field + "_capacity"] += capacity
        counts[field + "_mass"] += capacity * result.score_delta[obs.seat]
    total_mass = counts["ordinary_mass"] + counts["special_mass"]
    if counts["total_capacity"] != leaf["capacity"] or total_mass != leaf["mass"]:
        raise ValueError("G102 分番质量与 G52 同叶质量不守恒")
    return {"discard": first_discard, "ordinary_capacity": counts["ordinary_capacity"],
            "special_capacity": counts["special_capacity"],
            "ordinary_mass": counts["ordinary_mass"],
            "special_mass": counts["special_mass"],
            "total_mass": total_mass, "total_capacity": counts["total_capacity"],
            "natural_need": leaf["ordinary_natural_need"],
            "natural_progress_capacity": leaf["ordinary_natural_progress_capacity"],
            "whites_held": leaf["whites_held"]}


def arm(obs: object, analysis: object, key: str) -> dict:
    """摸白条件枝的全部留白合法叶各自拆账，不拼接叶特征。"""
    candidate = next((item for item in analysis.legal_candidates if item.action_key == key), None)
    if candidate is None or candidate.value_facts is None:
        raise ValueError("G102 根动作无生产合法分值事实")
    tree = g52.evaluate_root(obs, {
        "action_key": key,
        "value_facts": candidate_value_facts_to_json(candidate.value_facts),
    }, c31.RULE_CONFIG, include_all_leaves=True)
    edge = next((item for item in tree["edges"] if item["draw"] == "白"), None)
    if edge is None:
        raise ValueError("G102 公开未见白板容量为零")
    leaves = edge["best_second"]["unrestricted"]["legal_leaves"]
    floor = tree["root_whites_held"] + 1
    retaining = [leaf for leaf in leaves if leaf["whites_held"] >= floor]
    if not retaining:
        raise ValueError("G102 不受限包络无合法留白叶")
    split = [dissect_leaf(obs, key, leaf) for leaf in retaining]
    natural = min(retaining, key=g99.natural_key)
    natural_result = next(item for item in split if item["discard"] == natural["discard"])
    highfan = min(split, key=lambda item: (
        -item["special_mass"], item["natural_need"],
        -item["natural_progress_capacity"], item["discard"],
    ))
    return {"white_draw_public_capacity": edge["capacity"],
            "retaining_leaf_count": len(split),
            "natural_preferred": natural_result,
            "highfan_preferred": highfan,
            "any_special_route": highfan["special_mass"] > 0}


def direction(value: float) -> str:
    """只做方向描述，不计算不具独立性的窗口显著性。"""
    return "positive" if value > 1e-9 else "negative" if value < -1e-9 else "zero"


def main() -> None:
    """完整处理 G101 已冻结目标窗，未知与对账失败单列。"""
    if OUT.exists():
        raise FileExistsError("G102 冻结结果已存在，拒绝覆盖")
    selected = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if selected["outcome_labels_opened"] is not False:
        raise ValueError("G102 输入不是结果盲")
    rows = [json.loads(line) for line in gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"), "rt", encoding="utf-8")]
    if len(rows) != selected["counts"]["target_windows"]:
        raise ValueError("G102 冻结目标窗数量漂移")
    output = []
    counts = Counter()
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        try:
            obs = observation_from_json(row["observation"])
            analysis = c31.RULES.analyze(obs, value_limits=c31.VALUE_LIMITS)
            parent = arm(obs, analysis, row["parent_action"])
            alternate = arm(obs, analysis, row["alternate_action"])
            if parent["white_draw_public_capacity"] != alternate["white_draw_public_capacity"]:
                raise ValueError("G102 两臂摸白公开容量不等")
            item = {"key": row["key"], "status": "complete",
                    "white_before": row["white_before"], "shanten": row["shanten"],
                    "parent_action": row["parent_action"],
                    "alternate_action": row["alternate_action"],
                    "parent": parent, "alternate": alternate,
                    "delta": {}}
            for route in ("natural_preferred", "highfan_preferred"):
                item["delta"][route] = {}
                for metric in ("natural_progress_capacity", "natural_need",
                               "ordinary_capacity", "special_capacity",
                               "ordinary_mass", "special_mass", "total_mass"):
                    value = alternate[route][metric] - parent[route][metric]
                    item["delta"][route][metric] = value
                    label = route + "/" + metric + "/" + direction(value)
                    counts[label] += 1
                    rooms[label].add(row["key"][0])
            counts["complete"] += 1
            counts["either_arm_highfan_route"] += parent["any_special_route"] or alternate["any_special_route"]
            counts["both_arm_highfan_route"] += parent["any_special_route"] and alternate["any_special_route"]
        except (ValueError, TypeError) as exc:
            reason = type(exc).__name__ + ": " + str(exc)[:160]
            item = {"key": row["key"], "status": "unavailable", "reason": reason}
            counts["unavailable"] += 1
            counts["unavailable/" + reason] += 1
        output.append(item)
    result = {
        "schema": "g102-white-arrival-fan-audit/1", "outcome_labels_opened": False,
        "total_targets": len(rows), "counts": dict(sorted(counts.items())),
        "room_coverage": {key: len(value) for key, value in sorted(rooms.items())},
        "input_sha256": {"selection": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
                         "selection_rows": sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
                         "prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "g52": sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py"))},
        "boundary": "只看未来摸白后不受抓打圈限制的条件二摸；各指标同叶对账，不是实际牌墙、他家截尾或整桌收入。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    body = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in output)
    (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).write_bytes(gzip.compress(body.encode("utf-8"), compresslevel=9, mtime=0))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
