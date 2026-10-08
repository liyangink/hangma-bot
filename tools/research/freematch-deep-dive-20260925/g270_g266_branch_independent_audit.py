#!/usr/bin/env python3
"""G270：只读独立复核 G266 全部结果盲选定根的双臂分支。

完整 67 根、汇总文件及错误目录状态未齐备时，入口在打开任何分支收益前
拒绝运行。本文件不导入 G266 执行器，也不调用其汇总函数。分支落盘时
省略了完整决策序列：此处仅能独立核历史父代首动作、决策数为正及八局
逐局结算/终分恒等；完整逐动作恒等依赖冻结执行器生成时的断言，不能
声称由该落盘证据独立重算。
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
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import random
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
DEFAULT_OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g266-plain-baotou-entry-development-20260929')
G269 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g269-g266-first-block-audit-20260929/result.json')
EXPECTED_MANIFEST_SHA256 = "4bc4e6320d5e997a7dae0937a73c68a9a7af946f972d7b4a0b3b4fe6f43c42b9"
EXPECTED_SELECTION_SHA256 = "ecab19f37cfa08e9bed19dbb92722b261c6db680aef41935736f9033b8378abe"
LAYERS = ("B_nonready", "B_ready", "C", "A")
MIXES = ("H", "M")
CLASSES = ("plain_no_baotou", "plain_baotou", "seven_pairs",
           "other_self_special", "other_win", "draw")
RUNTIME_ZERO = ("fallbacks", "illegal_choices", "timeouts", "auto_actions", "audit_missing")
SETTLEMENT = ("round_no", "scores_before", "scores_after", "score_delta",
              "winner_seat", "is_draw", "fan", "details")


def require(condition: bool, message: str) -> None:
    """统一拒绝缺失、坏类型和不守恒证据。"""
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    """读取严格 JSON 对象；文件路径仅来自冻结清单。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"非 JSON 对象：{path}")
    return value


def file_hash(path: Path) -> str:
    """按原始字节计算 SHA-256。"""
    return sha256(path.read_bytes()).hexdigest()


def root_id(seed: int, mix: str, root: int) -> str:
    """种子、对手池和根编号共同决定独立聚类单元。"""
    return f"{seed}|{mix}|{root}"


def half_for(identity: str) -> str:
    """按事前冻结的最后一个哈希字节分半批。"""
    return "even" if sha256(identity.encode("ascii")).digest()[-1] % 2 == 0 else "odd"


def rule_source_hash() -> str:
    """独立按规则源文件路径与逐文件摘要重算生产规则指纹。"""
    rules = _project_file(_PROJECT_ROOT, REPO / "src/hangma_bot/hangma")
    paths = sorted(p for p in rules.rglob("*") if p.is_file()
                   and p.suffix in {".py", ".c", ".h"})
    require(bool(paths), "规则源文件清单为空")
    entries = [[p.relative_to(REPO).as_posix(), file_hash(p)] for p in paths]
    encoded = json.dumps(entries, ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def verify_manifest_selection(out: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """核 G269 冻结指纹、16 项输入、规则源和严格 67 根选样全集。"""
    g269 = read_json(G269)
    require(g269.get("manifest_sha256") == EXPECTED_MANIFEST_SHA256
            and g269.get("selection_sha256") == EXPECTED_SELECTION_SHA256
            and g269.get("branch_outcomes_opened") is False
            and g269.get("effect_estimated") is False,
            "G269 事前审查锚点漂移")
    manifest_path, selection_path = out / "manifest.json", out / "selection.json"
    require(file_hash(manifest_path) == EXPECTED_MANIFEST_SHA256, "G266 清单字节摘要漂移")
    require(file_hash(selection_path) == EXPECTED_SELECTION_SHA256, "G266 选择清单字节摘要漂移")
    manifest, selection = read_json(manifest_path), read_json(selection_path)
    require(manifest.get("schema") == "g266-plain-baotou-entry-branch-manifest/1"
            and manifest.get("blocks") == [{"panel_seed": 2026122966, "roots": [3, 66]},
                                            {"panel_seed": 2026122967, "roots": [3, 66]}]
            and manifest.get("mixes") == ["H", "M"]
            and manifest.get("focal_seats") == [0, 1, 2, 3]
            and manifest.get("samples") == ["historical"] +
            [f"g266-{i:02d}" for i in range(1, 9)]
            and manifest.get("layer_priority") == list(LAYERS)
            and manifest.get("versions", {}).get("rounds_per_game") == 8,
            "G266 面板、九世界或八单局合同漂移")
    inputs = manifest.get("input_identity")
    require(isinstance(inputs, dict) and len(inputs) == 16, "冻结输入清单非 16 项")
    for name, recorded in inputs.items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts,
                "输入清单路径越界")
        require(file_hash(_project_file(_PROJECT_ROOT, REPO / relative)) == recorded, f"冻结输入字节漂移：{name}")
    require(rule_source_hash() == manifest.get("rules_source_hash"), "生产规则源摘要漂移")
    require(manifest.get("parent_algorithm_sha256") ==
            "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618",
            "父代评分摘要漂移")
    require(selection.get("schema") == "g266-result-blind-root-selection/1"
            and selection.get("manifest_sha256") == EXPECTED_MANIFEST_SHA256
            and selection.get("result_blind") is True
            and selection.get("second_block_opened") is False
            and selection.get("branch_allowed") is True
            and selection.get("first_block_main_exposed_roots") == {"H": 23, "M": 26}
            and selection.get("all_main_exposed_roots") == {"H": 23, "M": 26}
            and selection.get("selected_roots") == 67,
            "G266 结果盲选择或首块暴露身份漂移")
    rows = selection.get("roots")
    require(isinstance(rows, list) and len(rows) == 128, "选择清单须覆盖 H/M 各 64 根")
    expected = {(2026122966, mix, root) for mix in MIXES for root in range(3, 67)}
    seen: set[tuple[int, str, int]] = set()
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        seed, mix, root = row["panel_seed"], row["mix"], row["root_index"]
        require(type(seed) is int and type(root) is int and mix in MIXES,
                "选择根身份类型错误")
        key = (seed, mix, root)
        require(key in expected and key not in seen, "选择根缺失、重复或来自计划外种子")
        seen.add(key)
        identity = root_id(seed, mix, root)
        require(row.get("root_identity") == identity
                and row.get("half") == half_for(identity), "根身份或哈希半批漂移")
        if row.get("selection_status") == "selected":
            layer, hit = row.get("priority_layer"), row.get("priority_hit")
            require(layer in LAYERS and isinstance(hit, dict)
                    and hit.get("layer") == layer
                    and type(hit.get("seat")) is int
                    and hit["seat"] in (0, 1, 2, 3), "入选根行动窗身份缺失")
            selected.append(row)
            counts[layer] += 1
    require(seen == expected and len(selected) == 67
            and dict(counts) == {"B_nonready": 49, "B_ready": 2, "C": 16},
            "入选根数、层数或首块全集与 G269 不同")
    return manifest, selection, selected


def branch_file(out: Path, row: dict[str, Any]) -> Path:
    """由冻结身份构造唯一结果路径。"""
    return out / "branches" / (f"p{row['panel_seed']}-{row['mix']}-"
                               f"r{row['root_index']:04d}.json")


def stage_file(out: Path, row: dict[str, Any], seat: int) -> Path:
    """由冻结身份构造父代第一桌路径。"""
    return out / "stages" / (f"p{row['panel_seed']}-{row['mix']}-"
                             f"r{row['root_index']:04d}-s{seat}.json")


def require_complete_before_outcomes(out: Path, selected: list[dict[str, Any]]) -> None:
    """运行中只看文件名与错误数，禁止先读已完成根的中途收益。"""
    expected = {branch_file(out, row).name for row in selected}
    actual = {p.name for p in (out / "branches").glob("*.json")}
    require(actual == expected, f"分支未完整收齐或有计划外根：{len(actual)}/67")
    require((out / "result.json").is_file(), "完整汇总尚未落盘")
    errors = list((out / "errors").glob("*.json"))
    require(not errors, f"G266 存在失败证据：{len(errors)}")


def integer(value: Any, label: str) -> int:
    """拒绝 Python bool 冒充整数积分、次数或序号。"""
    require(type(value) is int, f"{label} 必须为整数")
    return value


def verify_runtime(counts: Any, label: str) -> None:
    """非法、超时、降级、自动动作和审计缺口均必须为整数零。"""
    require(isinstance(counts, dict), f"{label} 运行计数缺失")
    for name in RUNTIME_ZERO:
        require(type(counts.get(name)) is int and counts[name] == 0,
                f"{label} {name} 非整数零")


def settlement(hand: dict[str, Any]) -> dict[str, Any]:
    """忽略非结算元数据，仅抽官方规则结算所需的八字段。"""
    return {name: hand[name] for name in SETTLEMENT}


def hand_class(hand: dict[str, Any], seat: int) -> str:
    """按互斥权威结算而非 G13 的普通／特殊自摸粗类划账。"""
    require(type(hand["is_draw"]) is bool, "流局标记非布尔")
    if hand["is_draw"]:
        require(hand["winner_seat"] is None, "流局存在胡牌座位")
        return "draw"
    winner = integer(hand["winner_seat"], "胡牌座位")
    require(0 <= winner < 4, "胡牌座位越界")
    if winner != seat:
        return "other_win"
    details = hand["details"]
    require(isinstance(details, list) and bool(details)
            and all(isinstance(item, str) for item in details), "本人胡牌明细缺失")
    if details[0] == "平胡":
        return "plain_baotou" if "爆头" in details else "plain_no_baotou"
    if details[0] == "七对" or details[0].startswith("豪华七对×"):
        return "seven_pairs"
    return "other_self_special"


def verify_arm(arm: dict[str, Any], *, seat: int, hit: dict[str, Any],
               first_action: str, forced: int, where: str) -> dict[str, Any]:
    """独立重算每局四座守恒、六类净分和机会缺失传播。"""
    verify_runtime(arm.get("runtime_counts"), where)
    require(arm.get("first_action") == first_action
            and integer(arm.get("forced_once"), where + " 强制次数") == forced
            and integer(arm.get("decision_count"), where + " 决策数") > 0,
            f"{where} 首动作或恰好一次强制动作错误")
    hands, final = arm.get("hands"), arm.get("final_scores")
    require(isinstance(hands, list) and len(hands) == 8
            and isinstance(final, list) and len(final) == 4, f"{where} 非完整八局")
    counts = {name: 0 for name in CLASSES}
    income = {name: 0 for name in CLASSES}
    labels: list[str] = []
    piao_tags: list[list[str]] = []
    prior: list[int] | None = None
    for number, hand in enumerate(hands, 1):
        before, after, delta = (hand[name] for name in
                                ("scores_before", "scores_after", "score_delta"))
        require(hand.get("round_no") == number
                and all(isinstance(v, list) and len(v) == 4
                        for v in (before, after, delta)), f"{where} 单局序号或积分向量错误")
        for j in range(4):
            integer(before[j], where + " 局前积分")
            integer(after[j], where + " 局后积分")
            integer(delta[j], where + " 积分增量")
        require(prior is None or before == prior, f"{where} 单局积分不连续")
        require(all(before[j] + delta[j] == after[j] for j in range(4))
                and sum(delta) == 0, f"{where} 四座积分不守恒")
        prior = after
        category = hand_class(hand, seat)
        counts[category] += 1
        income[category] += delta[seat]
        labels.append(category)
        details = hand.get("details") or []
        piao_tags.append([v for v in details if "飘" in v]
                         if hand.get("winner_seat") == seat else [])
    require(prior == final and sum(counts.values()) == 8
            and sum(income.values()) == final[seat] - hands[0]["scores_before"][seat],
            f"{where} 完整桌或六类净分不守恒")
    actual = arm.get("income")
    require(isinstance(actual, dict) and set(actual.get("by_class", {})) == set(CLASSES),
            f"{where} 六类分账缺类")
    for category in CLASSES:
        item = actual["by_class"][category]
        require(integer(item.get("count"), where + category + " 次数") == counts[category]
                and integer(item.get("focal_net_score"), where + category + " 净分")
                == income[category], f"{where} {category} 分账不符")
    require(actual.get("hand_labels") == labels
            and actual.get("piao_tags_by_hand") == piao_tags,
            f"{where} 单局互斥标签或财飘旁标错误")
    account = arm.get("account")
    require(isinstance(account, dict)
            and account.get("complete_hands") == 8
            and account.get("focal_seat") == seat
            and account.get("focal_table_delta") == sum(income.values()),
            f"{where} G13 总账与六类净分不符")
    target_no = integer(hit["round_no"], "目标单局号")
    require(1 <= target_no <= 8
            and settlement(arm.get("target_hand")) == settlement(hands[target_no - 1])
            and arm.get("target_class") == labels[target_no - 1],
            f"{where} 目标单局结算或结局分类漂移")
    timeline = arm.get("timeline")
    require(isinstance(timeline, dict) and isinstance(timeline.get("events"), list)
            and bool(timeline["events"]), f"{where} 机会时间线缺失")
    events = timeline["events"]
    require(events[0].get("status") == "no"
            and events[0].get("trigger_seq") == hit["trigger_seq"]
            and events[0].get("selected_action") == first_action,
            f"{where} 根窗机会或首动作不一致")
    require(all(event.get("round_no") == target_no
                and event.get("status") in {"yes", "no", "unknown"}
                and type(event.get("trigger_seq")) is int for event in events),
            f"{where} 机会状态含未知枚举或错误单局")
    unknown = any(event["status"] == "unknown" for event in events[1:])
    entered = any(event["status"] == "yes" for event in events[1:])
    require(type(timeline.get("unknown_after_root")) is bool
            and timeline["unknown_after_root"] == unknown
            and type(timeline.get("first_entered_before_target_end")) is bool
            and timeline["first_entered_before_target_end"] == entered
            and timeline.get("target_end") == labels[target_no - 1]
            and timeline.get("entered_then_other_win") is
            (entered and labels[target_no - 1] == "other_win"),
            f"{where} unknown 被计作无机会或首次进入状态不符")
    return {"income": income, "labels": labels, "unknown": unknown,
            "entered": entered, "target_net": hands[target_no - 1]["score_delta"][seat],
            "table_net": sum(income.values()), "target_class": labels[target_no - 1],
            "entered_then_other_win": entered and labels[target_no - 1] == "other_win"}


def verify_branch_payload(branch: dict[str, Any], stage: dict[str, Any],
                          selected: dict[str, Any], samples: list[str],
                          manifest_hash: str, selection_hash: str) -> dict[str, Any]:
    """只用原始分支／父代表重算根内九世界配对，不读 G266 汇总。"""
    identity, hit = branch.get("identity"), selected["priority_hit"]
    require(branch.get("schema") == "g266-plain-baotou-entry-root-branch/1"
            and branch.get("manifest_sha256") == manifest_hash
            and branch.get("selection_sha256") == selection_hash
            and isinstance(identity, dict), "分支冻结身份漂移")
    seat = hit["seat"]
    for name, expected in (("panel_seed", selected["panel_seed"]),
                           ("mix", selected["mix"]),
                           ("root_index", selected["root_index"]),
                           ("root_identity", selected["root_identity"]),
                           ("half", selected["half"]),
                           ("focal_seat", seat),
                           ("layer", selected["priority_layer"]),
                           ("hit", hit)):
        require(identity.get(name) == expected, f"根身份 {name} 漂移")
    table = stage.get("table")
    require(stage.get("manifest_sha256") == manifest_hash
            and stage.get("panel_seed") == selected["panel_seed"]
            and stage.get("mix") == selected["mix"]
            and stage.get("root_index") == selected["root_index"]
            and stage.get("focal_seat") == seat
            and isinstance(table, dict)
            and table.get("layers", {}).get(selected["priority_layer"]) == hit,
            "原父代表阶段或行动窗冻结身份漂移")
    verify_runtime(table.get("runtime_counts"), "扫描父代表")
    require(isinstance(table.get("hands"), list) and len(table["hands"]) == 8
            and isinstance(table.get("final_scores"), list)
            and len(table["final_scores"]) == 4, "扫描父代表非完整八局")
    pairs = branch.get("paired_worlds")
    require(isinstance(pairs, list) and len(pairs) == 9
            and [pair.get("sample_key") for pair in pairs] == samples,
            "根分支九世界不完整、重复或排序漂移")
    scores: list[int] = []
    target_scores: list[int] = []
    income_deltas = {category: [] for category in CLASSES}
    first_enter_deltas: list[int] = []
    unknown_worlds = 0
    target_classes = {"parent": Counter(), "alternate": Counter()}
    entered_then_other_win = {"parent": 0, "alternate": 0}
    target_no = hit["round_no"]
    for index, pair in enumerate(pairs):
        where = identity["root_identity"] + "/" + samples[index]
        parent_arm, alt_arm = pair["parent"], pair["alternate"]
        parent = verify_arm(parent_arm, seat=seat, hit=hit,
                            first_action=hit["parent_action"], forced=0,
                            where=where + "/parent")
        alternate = verify_arm(alt_arm, seat=seat, hit=hit,
                               first_action=hit["alternate_action"], forced=1,
                               where=where + "/alternate")
        require(parent_arm["hands"][0]["scores_before"] ==
                alt_arm["hands"][0]["scores_before"]
                and [settlement(h) for h in parent_arm["hands"][:target_no - 1]] ==
                [settlement(h) for h in alt_arm["hands"][:target_no - 1]]
                and parent_arm["hands"][target_no - 1]["scores_before"] ==
                alt_arm["hands"][target_no - 1]["scores_before"] ==
                hit["scores_by_seat"],
                f"{where} 双臂同世界起点或目标前缀不恒等")
        require([settlement(h) for h in parent_arm["hands"][:target_no - 1]] ==
                [settlement(h) for h in table["hands"][:target_no - 1]],
                f"{where} 隐藏世界重采样改写历史前缀")
        if index == 0:
            require([settlement(h) for h in parent_arm["hands"]] ==
                    [settlement(h) for h in table["hands"]]
                    and parent_arm["final_scores"] == table["final_scores"],
                    "原历史世界父代逐局结算或终分与扫描父代表不一致")
        score = alternate["table_net"] - parent["table_net"]
        target_score = alternate["target_net"] - parent["target_net"]
        require(integer(pair.get("focal_complete_table_delta"), where + " 桌差") == score
                and integer(pair.get("focal_target_hand_delta"), where + " 目标局差")
                == target_score,
                f"{where} 已存双臂差与逐局重算不符")
        scores.append(score)
        target_scores.append(target_score)
        for category in CLASSES:
            income_deltas[category].append(
                alternate["income"][category] - parent["income"][category])
        if parent["unknown"] or alternate["unknown"]:
            unknown_worlds += int(parent["unknown"]) + int(alternate["unknown"])
        else:
            first_enter_deltas.append(int(alternate["entered"]) - int(parent["entered"]))
        for arm_name, verified in (("parent", parent), ("alternate", alternate)):
            target_classes[arm_name][verified["target_class"]] += 1
            entered_then_other_win[arm_name] += int(verified["entered_then_other_win"])
    require(sum(sum(parts) for parts in income_deltas.values()) == sum(scores),
            "根内六类双臂差与完整桌差不守恒")
    return {"identity": identity, "mean_table_delta": sum(scores) / 9,
            "mean_target_hand_delta": sum(target_scores) / 9,
            "historical_table_delta": scores[0],
            "first_four_resampled_table_delta": sum(scores[1:5]) / 4,
            "last_four_resampled_table_delta": sum(scores[5:]) / 4,
            "first_enter_delta": (sum(first_enter_deltas) / 9
                                  if unknown_worlds == 0 else None),
            "first_enter_unknown_arm_worlds": unknown_worlds,
            "focal_income_delta": {category: sum(income_deltas[category]) / 9
                                   for category in CLASSES},
            "target_classes": {arm: dict(target_classes[arm])
                               for arm in ("parent", "alternate")},
            "entered_then_other_win": entered_then_other_win,
            "resampled_positive_worlds": sum(v > 0 for v in scores[1:]),
            "resampled_negative_worlds": sum(v < 0 for v in scores[1:])}


def mean(values: list[float]) -> float | None:
    """空组保持缺测，不误写零收益。"""
    return sum(values) / len(values) if values else None


def cluster_interval(values: list[float], seed: int) -> list[float] | None:
    """九世界先归根，再对独立根有放回抽样 5,000 次。"""
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(5000))
    return [draws[124], draws[4874]]


def group_summary(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    """独立聚类重算 H/M、哈希半批、六类、尾部和机会完整性。"""
    values = [row["mean_table_delta"] for row in rows]
    desc = sorted(values, reverse=True)
    income = {kind: mean([row["focal_income_delta"][kind] for row in rows])
              for kind in CLASSES}
    if rows:
        require(abs(sum(income.values()) - mean(values)) < 1e-8,
                "组内六类净分与完整桌差不守恒")
    complete = all(row["first_enter_delta"] is not None for row in rows)
    halves = {}
    for half in ("even", "odd"):
        subset = [row for row in rows if row["identity"]["half"] == half]
        subset_complete = all(row["first_enter_delta"] is not None for row in subset)
        halves[half] = {"n": len(subset),
                        "mean_table_delta": mean([r["mean_table_delta"] for r in subset]),
                        "first_enter_complete": subset_complete,
                        "mean_first_enter_delta":
                        mean([r["first_enter_delta"] for r in subset])
                        if subset_complete else None}
    classes = {arm: dict(sum((Counter(row["target_classes"][arm]) for row in rows),
                             Counter())) for arm in ("parent", "alternate")}
    return {"independent_roots": len(rows), "mean_table_delta": mean(values),
            "root_cluster_95pct_interval": cluster_interval(values, seed),
            "mean_target_hand_delta": mean([r["mean_target_hand_delta"] for r in rows]),
            "first_enter_complete": complete,
            "first_enter_unknown_arm_worlds": sum(r["first_enter_unknown_arm_worlds"]
                                                   for r in rows),
            "mean_first_enter_delta":
            mean([r["first_enter_delta"] for r in rows]) if complete else None,
            "mean_focal_income_delta": income, "half": halves,
            "mean_without_best_root": mean(desc[1:]),
            "mean_without_best_two_roots": mean(desc[2:]),
            "positive_roots": sum(v > 0 for v in values),
            "negative_roots": sum(v < 0 for v in values),
            "zero_roots": sum(v == 0 for v in values),
            "minimum_root_delta": min(values) if values else None,
            "maximum_root_delta": max(values) if values else None,
            "first_four_resampled_mean":
            mean([r["first_four_resampled_table_delta"] for r in rows]),
            "last_four_resampled_mean":
            mean([r["last_four_resampled_table_delta"] for r in rows]),
            "target_classes": classes,
            "entered_then_other_win": {arm: sum(r["entered_then_other_win"][arm]
                                                for r in rows)
                                       for arm in ("parent", "alternate")}}


def compare(actual: Any, expected: Any, label: str) -> None:
    """逐字段核汇总，数值允许浮点求和次序造成的微小误差。"""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected),
                label + " 字段集合漂移")
        for key, value in expected.items():
            compare(actual[key], value, label + "." + str(key))
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected),
                label + " 列表长度漂移")
        for index, value in enumerate(expected):
            compare(actual[index], value, f"{label}[{index}]")
    elif isinstance(expected, bool):
        require(type(actual) is bool and actual is expected, label + " 布尔漂移")
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        require(type(actual) in (float, int)
                and abs(actual - expected) <= 1e-8 * max(1, abs(expected)),
                label + " 数值漂移")
    else:
        require(actual == expected, label + " 值漂移")


def audit(out: Path) -> dict[str, Any]:
    """只有全部结果齐备才打开收益，独立复算所有根与总汇。"""
    manifest, selection, selected = verify_manifest_selection(out)
    require_complete_before_outcomes(out, selected)
    selection_hash = file_hash(out / "selection.json")
    rows = []
    for selected_row in selected:
        branch = read_json(branch_file(out, selected_row))
        seat = selected_row["priority_hit"]["seat"]
        stage = read_json(stage_file(out, selected_row, seat))
        rows.append(verify_branch_payload(
            branch, stage, selected_row, manifest["samples"],
            EXPECTED_MANIFEST_SHA256, selection_hash))
    result = read_json(out / "result.json")
    require(result.get("schema") == "g266-plain-baotou-entry-branch-result/1"
            and result.get("manifest_sha256") == EXPECTED_MANIFEST_SHA256
            and result.get("selection_sha256") == EXPECTED_SELECTION_SHA256
            and result.get("selected_independent_roots") == 67,
            "G266 汇总冻结身份或根数漂移")
    compare(result.get("root_rows"), rows, "root_rows")
    groups: dict[str, dict[str, Any]] = {}
    for layer_index, layer in enumerate(LAYERS):
        groups[layer] = {}
        for mix_index, mix in enumerate(MIXES):
            subset = [row for row in rows
                      if row["identity"]["layer"] == layer
                      and row["identity"]["mix"] == mix]
            groups[layer][mix] = group_summary(
                subset, 2026122966 + layer_index * 10 + mix_index)
    compare(result.get("groups"), groups, "groups")
    gate = result.get("B_nonready_continue_diagnosis_gate")
    require(isinstance(gate, dict), "B_nonready 继续门缺失")
    hard = ("exposure_at_least_12", "conditional_mean_positive",
            "both_halves_positive", "without_best_positive",
            "first_enter_complete", "first_enter_positive",
            "route_cost_not_above_baotou_gain")
    computed = {}
    for mix in MIXES:
        main = groups["B_nonready"][mix]
        inc = main["mean_focal_income_delta"]
        loss = max(0, -(inc["plain_no_baotou"] or 0)) + max(0, -(inc["seven_pairs"] or 0))
        gain = max(0, inc["plain_baotou"] or 0)
        computed[mix] = {
            "exposure_at_least_12": selection["all_main_exposed_roots"][mix] >= 12,
            "conditional_mean_positive": (main["mean_table_delta"] or 0) > 0,
            "both_halves_positive": all(
                (main["half"][half]["mean_table_delta"] or 0) > 0
                for half in ("even", "odd")),
            "without_best_positive": (main["mean_without_best_root"] or 0) > 0,
            "first_enter_complete": main["first_enter_complete"],
            "first_enter_positive": main["first_enter_complete"]
            and (main["mean_first_enter_delta"] or 0) > 0,
            "ordinary_or_seven_loss": loss,
            "plain_baotou_gain_floor_zero": gain,
            "route_cost_not_above_baotou_gain": loss <= gain,
            "two_best_roots_sensitivity_positive":
            (main["mean_without_best_two_roots"] or 0) > 0,
        }
    compare(gate.get("per_mix"), computed, "B_nonready_continue_diagnosis_gate.per_mix")
    require(gate.get("hard_gate_names") == list(hard)
            and gate.get("all_hard_gates_pass") is
            all(computed[mix][name] for mix in MIXES for name in hard),
            "B_nonready 继续门决策未由原始根重算得到")
    return {"schema": "g270-g266-branch-independent-audit/1",
            "decision": "complete_verified", "selected_independent_roots": len(rows),
            "paired_worlds": len(rows) * 9, "arm_complete_tables": len(rows) * 18,
            "branch_source_imported": False,
            "six_class_and_root_cluster_verified": True,
            "historical_parent_first_action_and_settlement_verified": True,
            "historical_parent_full_action_sequence_artifact_available": False,
            "historical_parent_full_action_sequence_verification":
            "generation_time_assertion_only_not_independently_reconstructed",
            "unknown_opportunity_fail_closed": True,
            "B_nonready_continue_diagnosis_gate": gate["all_hard_gates_pass"]}


def main() -> None:
    """输出核验结论；永不修改执行器、冻结证据或在线接线。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(audit(args.out), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
