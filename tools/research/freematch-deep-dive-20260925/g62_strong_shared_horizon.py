#!/usr/bin/env python3
"""G62：强手正常摸打分歧的同一两摸时域条件价值，结果盲。"""

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

import c31_action_layer_gap as c31
import g18_strict_two_draw_probe as g18
import g52_g49_shared_horizon_probe as g52
from g52_shared_horizon import evaluate_root
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g62-strong-shared-horizon-20260927')


def sha(path: Path) -> str:
    """绑定输入、代码和逐窗证据。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, payload: dict) -> None:
    """已有实验文件不得覆盖。"""

    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"G62 已有结果，拒绝覆盖：{path}")
    path.write_text(body, encoding="utf-8")


def key(row: dict) -> tuple[str, str, str, int, int]:
    """强手、房、小局与官方动作序号联合标识一个本人窗口。"""

    return row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"]


def cell(row: dict) -> str:
    """只依赖动作前牌形与两弃牌的生产事实分层。"""

    delta = row["delta"]
    wider = (delta["ordinary_support_capacity_delta_same_layer"] > 0 and
             delta["ordinary_support_codes_delta_same_layer"] > 0)
    return ("white0" if row["white_before"] == 0 else "white1plus") + "/" + (
        "wider_both" if wider else "other")


def selected_rows(profile: dict) -> tuple[list[dict], dict]:
    """32 单元各四层按固定摘要排序抽首窗，缺层显式记录。"""

    eligible: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in profile["strict_discard_rows"]:
        if row["delta"]["ordinary_delta"] != 0 or row["delta"]["combined_delta"] != 0:
            continue
        eligible[(row["peer"], row["room"], cell(row))].append(row)
    peers = {(row["peer"], row["room"]) for row in profile["strict_discard_rows"]}
    if len(peers) != 32:
        raise ValueError("G62 来源强手－房单元数漂移")
    selected = []
    coverage = {}
    for peer, room in sorted(peers):
        for stratum in ("white0/wider_both", "white0/other",
                        "white1plus/wider_both", "white1plus/other"):
            candidates = eligible[(peer, room, stratum)]
            candidates.sort(key=lambda row: hashlib.sha256(
                json.dumps(key(row), ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8")).hexdigest())
            coverage[peer + "/" + room + "/" + stratum] = len(candidates)
            if candidates:
                selected.append(candidates[0])
    return selected, coverage


def summarize(root: dict) -> dict:
    """两摸条件树只保存可比较摘要，避免把未来叶写成在线特征。"""

    return {**g18._summary(root), "routes": g52._route_summary(root)}


def delta(parent: dict, strong: dict) -> dict:
    """强手弃牌减父代首选；同一观察、同一后续本人摸牌时域。"""

    if parent["first_capacity"] != strong["first_capacity"]:
        raise ValueError("两合法弃牌的下一摸牌总公开容量不相等")
    answer = {"first_hu_mass": strong["first_hu_mass"] - parent["first_hu_mass"],
              "conditional_value": {}, "routes": {}}
    for survival in ("0.0", "0.5", "1.0"):
        answer["conditional_value"][survival] = {
            mode: strong["conditional_value"][survival][mode] -
                  parent["conditional_value"][survival][mode]
            for mode in ("restricted", "unrestricted")}
    for mode in ("restricted", "unrestricted"):
        answer["routes"][mode] = {}
        for route in ("ordinary", "seven"):
            a, p = strong["routes"][mode][route], parent["routes"][mode][route]
            if a is None and p is None:
                answer["routes"][mode][route] = None
            elif a is None or p is None:
                raise ValueError("两动作七对路线覆盖不一致")
            else:
                answer["routes"][mode][route] = {name: a[name] - p[name] for name in a}
    return answer


def main() -> None:
    """先固定样本再打开对应动作前观察，不读取动作后官方结算。"""

    profile_path, batch_path = _project_file(_PROJECT_ROOT, SOURCE / "shape_profile.json"), _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if (profile["outcome_labels_opened"] is not False or
            batch["outcome_labels_opened"] is not False or
            profile["batch_sha256"] != sha(batch_path)):
        raise ValueError("G62 来源结果盲边界漂移")
    sample, coverage = selected_rows(profile)
    manifest = {"schema": "g62-strong-shared-horizon-manifest/1",
                "outcome_labels_opened": False,
                "source_sha256": {"g61_batch": sha(batch_path),
                                  "g61_shape": sha(profile_path),
                                  "g52_tree": sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py")),
                                  "g62_prereg": sha(_project_file(_PROJECT_ROOT, HERE / "G62-STRONG-SHARED-HORIZON-PREREG-2026-09-27.md")),
                                  "g62_script": sha(Path(__file__))},
                "sample_keys": [list(key(row)) for row in sample],
                "eligible_by_cell": coverage}
    if OUT.exists():
        raise SystemExit("G62 结果目录已存在，拒绝覆盖")
    targets = {key(row): row for row in sample}
    if len(targets) != len(sample):
        raise ValueError("G62 抽样窗口重复")
    found = set()
    rows = []
    counts = Counter()
    for unit, record in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G62 G61 逐窗证据摘要不符")
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for window in windows:
            identity = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            target = targets.get(identity)
            if target is None:
                continue
            if identity in found or window["actual_action"] != target["strong_action"] or window["parent_top_action"] != target["parent_action"]:
                raise ValueError("G62 抽样动作或唯一性漂移")
            found.add(identity)
            observation = observation_from_json(window["observation"])
            analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            legal = {candidate.action_key: candidate for candidate in analysis.legal_candidates}
            row = {"key": list(identity), "cell": cell(target),
                   "strong_action": target["strong_action"],
                   "parent_action": target["parent_action"],
                   "parent_score_gap": target["parent_score_gap"],
                   "white_before": target["white_before"],
                   "wall_remaining": target["wall_remaining"]}
            try:
                pair = {}
                for label, action in (("parent", target["parent_action"]),
                                      ("strong", target["strong_action"])):
                    candidate = legal.get(action)
                    if candidate is None or candidate.value_facts is None:
                        raise ValueError("生产合法候选或分值事实缺失")
                    root = evaluate_root(observation, {
                        "action_key": action,
                        "value_facts": candidate_value_facts_to_json(candidate.value_facts),
                    }, c31.RULE_CONFIG)
                    pair[label] = summarize(root)
                row["delta"] = delta(pair["parent"], pair["strong"])
                row["pair"] = pair
                counts["complete_pairs"] += 1
            except (ValueError, FactsAnalysisError) as exc:
                row["unavailable"] = type(exc).__name__ + ": " + str(exc)[:200]
                counts["unavailable_pairs"] += 1
            rows.append(row)
    if found != set(targets) or len(rows) != len(sample):
        raise ValueError("G62 抽样动作未完全定位")
    result = {"schema": "g62-strong-shared-horizon-result/1",
              "manifest_sha256": hashlib.sha256((json.dumps(
                  manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
                      "utf-8")).hexdigest(),
              "outcome_labels_opened": False,
              "selected_windows": len(sample), "counts": dict(sorted(counts.items())),
              "rows": rows,
              "boundary": "条件本人两摸树不模拟他家先胡；公开未见容量不是牌墙分布，强手动作不是收益标签。"}
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"selected_windows": len(sample), "counts": result["counts"],
                      "nonempty_cells": sum(value > 0 for value in coverage.values())},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
