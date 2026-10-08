#!/usr/bin/env python3
"""G260：冻结强手观察上的白板用途和逐合法续行；只读、结果盲。

主母体仅使用 G61/G252 已冻结的动作前 PlayerObservation。G184 胡大牌榜
另存为赢家条件压力题，不并入分母、选样或候选阈值。
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

from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g184_classic_highhand_shadow as g184
from hangma_bot.hangma.hand_analysis import _need_std
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G252 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g252-strong-hu-continue-atlas-20260929')
G184 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g184-classic-highhand-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g260-white-use-route-audit-20260929')


def sha(path: Path) -> str:
    """按原始字节绑定冻结输入和分析代码。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, body: bytes) -> None:
    """只新建或核对逐字幂等产物，不覆盖漂移证据。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError("G260 既有证据漂移：" + str(path))
        return
    path.write_bytes(body)


def json_bytes(payload: object) -> bytes:
    """固定字段顺序与换行，便于复跑校验。"""

    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def gz_rows(rows: list[dict]) -> bytes:
    """固定 gzip 时间戳，不让运行时刻改变逐窗证据。"""

    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        for row in rows:
            zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n").encode("utf-8"))
    return raw.getvalue()


def white_bucket(observation: dict) -> str:
    """按当前本座可见手牌分层；3+ 不拆成稀疏假精度。"""

    count = observation["my_hand"].count("白")
    return "3+" if count >= 3 else str(count)


def support(items) -> dict | None:
    """公开未见容量只是物理上界，不解释为牌墙抽中概率。"""

    if items is None:
        return None
    return {"codes": [item.code for item in items if item.remaining_estimate > 0],
            "capacity": sum(item.remaining_estimate for item in items)}


def natural_profile(observation, action_key: str) -> dict | None:
    """用生产普通型数学比较把白作财神与全保留白的自然补牌缺口。"""

    if not action_key.startswith("discard:"):
        return None
    hand = list(observation.my_hand)
    hand.remove(Tile(action_key.split(":", 1)[1]))
    counts = counts_from_tiles(tuple(hand))
    whites = counts[33]
    sets_needed = 4 - len(observation.melds[observation.seat])
    need_by_usable_white = [_need_std(counts[:33], usable, sets_needed, True)
                            for usable in range(whites + 1)]
    with_white = need_by_usable_white[-1]
    reserve_white = need_by_usable_white[0]
    minimum_used = next(usable for usable, need in enumerate(need_by_usable_white)
                        if need == with_white)
    return {"white_held_after": whites,
            "natural_draws_needed_using_white": with_white,
            "natural_draws_needed_reserving_all_white": reserve_white,
            "white_substitution_gap": reserve_white - with_white,
            "minimum_white_used_for_current_ordinary_gap": minimum_used,
            "spare_white_at_current_ordinary_gap": whites - minimum_used}


def action_fact(observation, candidate) -> dict:
    """只序列化当窗合法候选及一次条件摸牌见证，空值保持未知。"""

    facts, value = candidate.facts, candidate.value_facts
    routes = []
    if value is not None:
        for route in value.routes:
            routes.append({
                "fan": route.conditional_settlement.fan,
                "details": list(route.conditional_settlement.details),
                "focal_delta": route.conditional_settlement.score_delta[observation.seat],
                "draw_kind": route.conditions.draw_kind,
                "followup_discard": route.followup_discard,
                "drawn_tile_support": support(route.useful_tiles),
                "pre_draw_white": route.conditions.pre_draw_hand.count("白"),
                "baotou_after_conditional_draw": route.conditions.baotou,
                "chain_piao": route.conditions.chain_piao,
            })
    branches = None
    if facts is not None and facts.followup_branches is not None:
        branches = [{"followup_discard": branch.followup_discard,
                     "ordinary": branch.standard_shanten_after,
                     "seven": branch.seven_pairs_shanten_after,
                     "support": support(branch.useful_tiles),
                     "baotou_after": branch.baotou_after,
                     "chain_piao_after": branch.chain_piao_after,
                     "four_white_after": branch.four_white_qualified_after}
                    for branch in facts.followup_branches]
    immediate = None if value is None or value.immediate_settlement is None else {
        "fan": value.immediate_settlement.fan,
        "details": list(value.immediate_settlement.details),
        "focal_delta": value.immediate_settlement.score_delta[observation.seat],
    }
    return {"action": candidate.action_key,
            "fact_kind": None if facts is None else facts.fact_kind.value,
            "completeness": None if facts is None else facts.completeness.value,
            "combined": None if facts is None else facts.shanten_after,
            "ordinary": None if facts is None else facts.standard_shanten_after,
            "seven": None if facts is None else facts.seven_pairs_shanten_after,
            "ordinary_support": None if facts is None else support(facts.standard_useful_tiles),
            "seven_support": None if facts is None else support(facts.seven_pairs_useful_tiles),
            "baotou_after": None if facts is None else facts.baotou_after,
            "natural": natural_profile(observation, candidate.action_key),
            "value_coverage": None if value is None else value.coverage.value,
            "immediate_hu": immediate, "one_draw_routes": routes,
            "followup_branches": branches}


def analyze_row(source: dict, *, scope: str) -> dict:
    """重算生产合法集合；所有策略特征仅源于本座 PlayerObservation。"""

    observation = observation_from_json(source["observation"])
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    legal = {item.action_key: item for item in rules.legal_candidates}
    if set(legal) != set(source["legal_action_keys"]):
        raise ValueError("G260 生产合法动作与冻结来源不同：" + str(source["game_id"]))
    actual, parent = source["actual_action"], source["parent_top_action"]
    if actual not in legal or parent not in legal:
        raise ValueError("G260 强手或父代动作不在合法集合")
    actions = [action_fact(observation, legal[key]) for key in sorted(legal)]
    by_action = {item["action"]: item for item in actions}
    for item in actions:
        natural = item["natural"]
        if natural is not None and item["ordinary"] is not None:
            if natural["natural_draws_needed_using_white"] != item["ordinary"] + 1:
                raise ValueError("自然缺口与生产普通型向听不符")
    return {"scope": scope, "peer": source["peer"], "room_id": source["room_id"],
            "game_id": source["game_id"], "round_no": source["round_no"],
            "draw_seq": source["draw_seq"], "seat": source["seat"],
            "white_before": source["observation"]["my_hand"].count("白"),
            "baotou_before": source["observation"]["rule_state"]["baotou"],
            "chain_piao_before": source["observation"].get("chain_piao"),
            "wall_remaining": source["observation"].get("remaining_tile_count"),
            "actual_action": actual, "parent_action": parent,
            "actual_fact": by_action[actual], "parent_fact": by_action[parent],
            "legal_actions": actions,
            "future_outcome_used": False}


def g252_rows() -> tuple[dict, list[dict], list[dict]]:
    """全量胡／继续分母入账；首分歧与父代一致负控均在结果盲状态选。"""

    result_path, rows_path = _project_file(_PROJECT_ROOT, G252 / "result.json"), _project_file(_PROJECT_ROOT, G252 / "rows.jsonl.gz")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result["rows"] != 940 or result["rows_sha256"] != sha(rows_path) or result["outcome_blind"] is not True:
        raise ValueError("G252 结果盲母体漂移")
    with gzip.open(rows_path, "rt", encoding="utf-8") as stream:
        source = [json.loads(line) for line in stream]
    if len(source) != 940:
        raise ValueError("G252 行数漂移")
    source.sort(key=lambda r: (r["peer"], r["game_id"], r["round_no"], r["draw_seq"]))
    counts = Counter()
    strata = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    residual, controls = [], []
    seen_hand = set()
    seen_control = set()
    for row in source:
        if row["actual_action"] not in row["legal_action_keys"] or "hu" not in row["legal_action_keys"]:
            raise ValueError("G252 胡／实际动作合法性漂移")
        direction = ("parent_hu_strong_continue" if row["parent_top_action"] == "hu" and row["label"] == "continue"
                     else "parent_continue_strong_hu" if row["parent_top_action"] != "hu" and row["label"] == "hu"
                     else "parent_agrees")
        bucket = white_bucket(row["observation"])
        counts[direction] += 1
        strata[(row["peer"], bucket, direction, row["immediate_hu"]["fan"])] += 1
        scopes[direction].add(row["room_id"])
        if direction != "parent_agrees":
            hand = (row["peer"], row["game_id"], row["round_no"])
            if hand not in seen_hand:
                seen_hand.add(hand)
                residual.append(row)
        else:
            # 父代一致负控：每强手／房／白层／标签／即时番数取首窗，不按赢家结局挑。
            control = (row["peer"], row["room_id"], bucket,
                       row["label"], row["immediate_hu"]["fan"])
            if control not in seen_control:
                seen_control.add(control)
                controls.append(row)
    report = {"rows": len(source), "direction": dict(sorted(counts.items())),
              "rooms": {key: len(value) for key, value in sorted(scopes.items())},
              "by_peer_white_direction_fan": [
                  {"peer": key[0], "white": key[1], "direction": key[2],
                   "immediate_fan": key[3], "windows": count}
                  for key, count in sorted(strata.items())],
              "first_residual_hands": len(residual),
              "parent_agree_controls": len(controls)}
    return report, residual, controls


def g61_rows() -> tuple[dict, list[dict], list[dict]]:
    """全量正常摸打分母入账；抽取多白首分歧和同房一致负控。"""

    result_path = _project_file(_PROJECT_ROOT, G61 / "result.json")
    batch = json.loads(result_path.read_text(encoding="utf-8"))
    if len(batch["units"]) != 32 or batch["outcome_labels_opened"] is not False:
        raise ValueError("G61 来源不是冻结结果盲母体")
    counts = Counter()
    strata = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    selected, controls = [], []
    selected_hand, control_room = set(), set()
    all_windows = []
    for key, record in sorted(batch["units"].items()):
        peer, room = key.split("/", 1)
        source = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "windows.json")
        if sha(source) != record["windows_sha256"]:
            raise ValueError("G61 逐房证据漂移：" + key)
        windows = json.loads(source.read_text(encoding="utf-8"))["windows"]
        if len(windows) != record["counts"]["legal_verified_windows"]:
            raise ValueError("G61 逐房行动窗数漂移：" + key)
        for row in windows:
            all_windows.append((peer, room, row))
    all_windows.sort(key=lambda item: (item[0], item[2]["game_id"], item[2]["round_no"], item[2]["draw_seq"]))
    for peer, room, row in all_windows:
        bucket = white_bucket(row["observation"])
        direction = "agree" if row["parent_agrees"] else "disagree"
        counts[direction] += 1
        strata[(peer, bucket, direction)] += 1
        scopes[(peer, bucket, direction)].add(room)
        row = dict(row, peer=peer)
        if direction == "disagree" and row["actual_action"].startswith("discard:") and row["parent_top_action"].startswith("discard:"):
            # 2+ 白每强手－单局－白层首分歧；一白每强手－房首分歧。
            marker = ((peer, row["game_id"], row["round_no"], bucket)
                      if bucket in ("2", "3+") else (peer, room, bucket))
            if bucket != "0" and marker not in selected_hand:
                selected_hand.add(marker)
                selected.append(row)
        if direction == "agree" and bucket != "0":
            marker = (peer, room, bucket)
            if marker not in control_room:
                control_room.add(marker)
                controls.append(row)
    if len(all_windows) != 17938 or counts["agree"] != 11855:
        raise ValueError("G61 全量母体对账漂移")
    report = {"windows": len(all_windows), "direction": dict(sorted(counts.items())),
              "by_peer_white_agreement": [
                  {"peer": key[0], "white": key[1], "direction": key[2],
                   "windows": count, "rooms": len(scopes[key])}
                  for key, count in sorted(strata.items())],
              "first_discard_disagreements_selected": len(selected),
              "parent_agree_controls_selected": len(controls)}
    return report, selected, controls


def g184_pressure() -> list[dict]:
    """赢家榜仅做响应窗压力题；此后验选样从不进入结果盲分母。"""

    output = []
    for rank in range(1, 17):
        doc = json.loads((_project_file(_PROJECT_ROOT, G184 / f"rank{rank}-round.json")).read_text(encoding="utf-8"))
        frames = doc["frames"]
        final = next(frame["ev"] for frame in reversed(frames)
                     if (frame.get("ev") or {}).get("type") == "round_ended")
        winner = final["seat"]
        for index, frame in enumerate(frames[1:], start=1):
            event = frame.get("ev") or {}
            if event.get("seat") != winner or event.get("type") not in ("chi", "peng"):
                continue
            visible = g184.observation(doc, index - 1, winner)
            rules = c31.RULES.analyze(visible, value_limits=c31.VALUE_LIMITS)
            actual = g184.actual_key(event)
            legal = {item.action_key: item for item in rules.legal_candidates}
            if actual not in legal:
                raise ValueError("G184 赢家响应动作不在生产合法集合")
            actions = [action_fact(visible, legal[key]) for key in sorted(legal)]
            output.append({"scope": "g184_winner_conditioned_pressure_only",
                           "rank": rank, "game_id": doc["game_id"],
                           "round_no": doc["round_no"], "event_seq": event["seq"],
                           "phase": visible.phase, "white_before": visible.my_hand.count(Tile("白")),
                           "actual_action": actual, "legal_actions": actions,
                           "winner_conditioned": True, "eligible_for_threshold_or_denominator": False})
    return output


def summarize(rows: list[dict]) -> dict:
    """只对已选结果盲窗计算行动前机械差异；不输出价值估计。"""

    counters = Counter()
    rooms: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        parent, strong = row["parent_fact"], row["actual_fact"]
        if row["actual_action"] == row["parent_action"]:
            continue
        if not (row["actual_action"].startswith("discard:") and
                row["parent_action"].startswith("discard:")):
            continue
        bucket = "3+" if row["white_before"] >= 3 else str(row["white_before"])
        group = row["scope"] + "/" + row["peer"] + "/white_" + bucket
        counters[group + "/paired_discards"] += 1
        p, s = parent["natural"], strong["natural"]
        if p is None or s is None:
            raise ValueError("配对弃牌缺自然缺口")
        changed = (p["white_held_after"] != s["white_held_after"]
                   or p["white_substitution_gap"] != s["white_substitution_gap"]
                   or p["spare_white_at_current_ordinary_gap"] != s["spare_white_at_current_ordinary_gap"]
                   or p["natural_draws_needed_reserving_all_white"] != s["natural_draws_needed_reserving_all_white"]
                   or parent["baotou_after"] != strong["baotou_after"])
        if changed:
            counters[group + "/white_use_or_baotou_changed"] += 1
            rooms[group + "/white_use_or_baotou_changed"].add(row["room_id"])
            if len(examples[group]) < 8:
                examples[group].append({"room": row["room_id"], "game_id": row["game_id"],
                                        "round_no": row["round_no"], "seq": row["draw_seq"],
                                        "strong": row["actual_action"], "parent": row["parent_action"],
                                        "ordinary": [strong["ordinary"], parent["ordinary"]],
                                        "seven": [strong["seven"], parent["seven"]],
                                        "natural_reserved": [s["natural_draws_needed_reserving_all_white"],
                                                             p["natural_draws_needed_reserving_all_white"]],
                                        "baotou": [strong["baotou_after"], parent["baotou_after"]]})
        if (strong["ordinary"] is not None and parent["ordinary"] is not None
                and strong["ordinary"] < parent["ordinary"]
                and s["natural_draws_needed_reserving_all_white"] < p["natural_draws_needed_reserving_all_white"]):
            counters[group + "/g49_like_ordinary_and_natural_improve"] += 1
        if (changed and strong["ordinary"] == parent["ordinary"]
                and (strong["seven"] is None or parent["seven"] is None
                     or strong["seven"] <= parent["seven"])):
            counters[group + "/same_ordinary_with_white_use_change"] += 1
            rooms[group + "/same_ordinary_with_white_use_change"].add(row["room_id"])
    return {"counts": dict(sorted(counters.items())),
            "rooms": {key: len(value) for key, value in sorted(rooms.items())},
            "examples": dict(sorted(examples.items()))}


def summarize_hu_routes(rows: list[dict]) -> dict:
    """胡／继续首分歧与一致负控同口径计数；条件路线不是价值标签。"""

    counts = Counter()
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not row["scope"].startswith("g252_"):
            continue
        scope = row["scope"]
        actual = row["actual_fact"]
        hu = next(item for item in row["legal_actions"] if item["action"] == "hu")
        fan = hu["immediate_hu"]["fan"]
        action_kind = "hu" if row["actual_action"] == "hu" else "continue"
        prefix = f"{scope}/{row['peer']}/{action_kind}"
        counts[prefix + "/rows"] += 1
        counts[prefix + f"/immediate_fan_{fan}"] += 1
        rooms[prefix].add(row["room_id"])
        if action_kind == "hu":
            continue
        routes = actual["one_draw_routes"]
        max_fan = max((route["fan"] for route in routes), default=0)
        if max_fan >= 2:
            counts[prefix + "/conditional_fan_2plus"] += 1
        if max_fan >= 4:
            counts[prefix + "/conditional_fan_4plus"] += 1
        if any(route["baotou_after_conditional_draw"] for route in routes):
            counts[prefix + "/conditional_baotou"] += 1
        if any(route["chain_piao"] > 0 for route in routes):
            counts[prefix + "/conditional_piao"] += 1
        if actual["ordinary"] == 0:
            counts[prefix + "/ordinary_ready_after"] += 1
        if actual["seven"] == 0:
            counts[prefix + "/seven_ready_after"] += 1
    return {"counts": dict(sorted(counts.items())),
            "rooms": {key: len(value) for key, value in sorted(rooms.items())}}


def summarize_speed_hu_guard(rows: list[dict]) -> dict:
    """即使存在更高番条件路线，也保留强手当前收胡的负例。"""

    counts = Counter()
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not row["scope"].startswith("g252_") or row["actual_action"] != "hu":
            continue
        group = row["scope"] + "/" + row["peer"]
        immediate_fan = row["actual_fact"]["immediate_hu"]["fan"]
        counts[group + "/hu"] += 1
        if immediate_fan == 1:
            counts[group + "/one_fan_hu"] += 1
        alternatives = [item for item in row["legal_actions"]
                        if item["action"].startswith("discard:")
                        and item["action"] != "discard:白"
                        and item["combined"] == 0
                        and item["value_coverage"] == "complete"
                        and any(route["fan"] > immediate_fan
                                for route in item["one_draw_routes"])]
        if alternatives:
            counts[group + "/legal_nonwhite_higher_fan_route_but_hu"] += 1
            rooms[group].add(row["room_id"])
    return {"counts": dict(sorted(counts.items())),
            "rooms_with_guard": {key: len(value) for key, value in sorted(rooms.items())}}


def summarize_pressure(rows: list[dict]) -> dict:
    """赢家条件压力题只数合法后继，不与结果盲分母相加。"""

    counts = Counter()
    for row in rows:
        counts["actual_chi_or_peng"] += 1
        actual = next(item for item in row["legal_actions"]
                      if item["action"] == row["actual_action"])
        branches = actual["followup_branches"] or []
        white = [branch for branch in branches if branch["followup_discard"] == "白"]
        if white:
            counts["actual_action_has_legal_white_followup"] += 1
        if any(branch["baotou_after"] and branch["chain_piao_after"] > 0 for branch in white):
            counts["white_followup_keeps_baotou_and_piao"] += 1
    return dict(sorted(counts.items()))


def prior_white_reserve() -> dict:
    """引用已冻结的全量严格弃牌口径，防止只看 G260 选中子集。"""

    profile = json.loads((_project_file(_PROJECT_ROOT, G61 / "white_reserve_profile.json")).read_text(encoding="utf-8"))
    if profile["outcome_labels_opened"] is not False or profile["batch_sha256"] != sha(_project_file(_PROJECT_ROOT, G61 / "result.json")):
        raise ValueError("G61 全留白画像身份漂移")
    return {peer: {key: profile["counts"][peer + "/all"].get(key, 0)
                   for key in ("strict_discard_rows", "same_whites_after_discard",
                               "same_ordinary_and_combined_layer", "all_white_reserved_need_same",
                               "natural_wider_without_production_ordinary_code_gain")}
            for peer in ("tengshe_0638", "xuanwu_2346")}


def main() -> None:
    """一次运行只重算结果盲首分歧和负控；不扫描 live 或 datamart。"""

    g61_report, g61_selected, g61_controls = g61_rows()
    g252_report, g252_selected, g252_controls = g252_rows()
    blind = []
    for scope, source in (("g252_first_residual", g252_selected),
                          ("g252_parent_agree_control", g252_controls),
                          ("g61_first_discard_disagreement", g61_selected),
                          ("g61_parent_agree_control", g61_controls)):
        for row in source:
            blind.append(analyze_row(row, scope=scope))
    pressure = g184_pressure()
    blind.sort(key=lambda row: (row["scope"], row["peer"], row["room_id"],
                                row["game_id"], row["round_no"], row["draw_seq"]))
    pressure.sort(key=lambda row: (row["rank"], row["event_seq"]))
    output = {"schema": "g260-white-use-route-audit/1",
              "source_sha256": {str(path.relative_to(HERE)): sha(path) for path in (
                  _project_file(_PROJECT_ROOT, G61 / "manifest.json"), _project_file(_PROJECT_ROOT, G61 / "result.json"), _project_file(_PROJECT_ROOT, G61 / "shape_profile.json"),
                  _project_file(_PROJECT_ROOT, G61 / "white_reserve_profile.json"), _project_file(_PROJECT_ROOT, G252 / "manifest.json"),
                  _project_file(_PROJECT_ROOT, G252 / "result.json"), _project_file(_PROJECT_ROOT, G252 / "rows.jsonl.gz"),
                  _project_file(_PROJECT_ROOT, G184 / "result.json"), *(_project_file(_PROJECT_ROOT, G184 / f"rank{rank}-round.json")
                                         for rank in range(1, 17)))},
              "script_sha256": sha(Path(__file__)),
              "main_outcome_blind": True,
              "g61_denominator": g61_report, "g252_denominator": g252_report,
              "main_rows": len(blind), "pressure_rows": len(pressure),
              "route_scan": summarize(blind), "hu_route_scan": summarize_hu_routes(blind),
              "speed_hu_guard": summarize_speed_hu_guard(blind),
              "winner_pressure_scan": summarize_pressure(pressure),
              "g61_prior_full_strict_white_reserve": prior_white_reserve(),
              "boundary": "G61/G252 未用动作后牌墙、对手暗手或终局；G184 仅赢家条件压力题。规则条件摸牌路线不是存活概率或完整桌价值。",
              "response_denominator_status": "G61/G252 不含强手吃碰响应；G184 赢家榜不能补为结果盲分母。"}
    write_new(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz"), gz_rows(blind))
    write_new(_project_file(_PROJECT_ROOT, OUT / "winner_pressure.jsonl.gz"), gz_rows(pressure))
    output["rows_sha256"] = sha(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz"))
    output["winner_pressure_sha256"] = sha(_project_file(_PROJECT_ROOT, OUT / "winner_pressure.jsonl.gz"))
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), json_bytes(output))
    print(json.dumps({"g61": g61_report["windows"], "g252": g252_report["rows"],
                      "main_rows": len(blind), "pressure_rows": len(pressure),
                      "route_counts": output["route_scan"]["counts"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
