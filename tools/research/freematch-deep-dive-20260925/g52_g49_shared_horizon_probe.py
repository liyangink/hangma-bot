#!/usr/bin/env python3
"""对 G49 的 102 个官方结果盲改选窗，计算双臂同一两摸时域的规则事实。"""

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
import time

import g11_cross_family_action_atlas as atlas
import g17_one_draw_value_gap as g17
import g18_strict_two_draw_probe as g18
from g52_shared_horizon import evaluate_root
from hangma_bot.hangma.candidate_facts import FactsAnalysisError
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G49 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-official-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g52-g49-shared-horizon-20260927/result.json')
ROWS = OUT.with_name("rows.jsonl.gz")
MODES = ("restricted", "unrestricted")
SURVIVALS = ("0.0", "0.5", "1.0")
ROUTES = {
    "ordinary": ("best_natural_progress", "ordinary_natural_need",
                 "ordinary_natural_progress_capacity"),
    "seven": ("best_seven_natural_progress", "seven_natural_need",
              "seven_natural_progress_capacity"),
}


def _sha(path: Path) -> str:
    """返回冻结输入或程序内容的 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sign(value: float) -> str:
    """只给数值差分组；零附近的浮点误差不产生伪方向。"""

    return "positive" if value > 1e-9 else "negative" if value < -1e-9 else "equal"


def _route_summary(root: dict) -> dict:
    """在同一次本人摸牌分支内，分别选择普通型与七对自然后继。

    公开容量是条件枚举权重，不是牌墙后验；不同补牌缺口层的
    `progress_capacity` 不直接比较为胜率。
    """

    total = root["first_draw_public_capacity"]
    if total <= 0:
        raise ValueError("G52 第一摸容量非正")
    answer = {}
    for mode in MODES:
        answer[mode] = {}
        for route, (choice, need, progress) in ROUTES.items():
            picked = [edge["best_second"][mode][choice] for edge in root["edges"]]
            if all(leaf is None for leaf in picked):
                answer[mode][route] = None
                continue
            if any(leaf is None for leaf in picked):
                raise ValueError("G52 七对路线在同一根内部分支缺失")
            answer[mode][route] = {
                "expected_natural_need": sum(
                    edge["capacity"] * leaf[need]
                    for edge, leaf in zip(root["edges"], picked)
                ) / total,
                "expected_progress_capacity": sum(
                    edge["capacity"] * leaf[progress]
                    for edge, leaf in zip(root["edges"], picked)
                ) / total,
                "expected_whites_held": sum(
                    edge["capacity"] * leaf["whites_held"]
                    for edge, leaf in zip(root["edges"], picked)
                ) / total,
                "conditional_second_hu_value": sum(
                    edge["capacity"] * leaf["mass"] / leaf["capacity"]
                    for edge, leaf in zip(root["edges"], picked)
                ) / total,
            }
    return answer


def main() -> None:
    """核验 102 个冻结窗并写入全行；结果文件存在时拒绝覆盖。"""

    if OUT.exists() or ROWS.exists():
        raise SystemExit("G52 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    source = json.loads(G49.read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or
            source.get("parent_source_sha256") != frozen["parent_source_sha256"] or
            len(source.get("changed") or []) != 102 or
            source.get("candidate_source_sha256") != _sha(_project_file(_PROJECT_ROOT, HERE / "g49_natural_route_policy.py"))):
        raise ValueError("G49 结果盲输入、父代或候选源码漂移")
    targets = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
               for row in source["changed"]}
    if len(targets) != 102 or len(atlas._complete_ids()) != 909:
        raise ValueError("G52 唯一动作窗或完整桌母体漂移")
    config = RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                        base_score=1, you_cai_bi_kao=False)
    rows = []
    seen = set()
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    timings = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("G52 冻结房动作文件字节数漂移")
        payload = json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}
        release = payload.get("policy_release") or {}
        if (release.get("candidate_source_sha256") != frozen["parent_source_sha256"] or
                payload.get("ruleset_version") != config.ruleset_version or
                payload.get("base_score") != config.base_score or
                payload.get("you_cai_bi_kao") is not False):
            raise ValueError("G52 冻结房父代或规则配置漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = context.get("game_id"), context.get("round_no"), context.get("trigger_seq")
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("G52 目标房或窗口重复")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context.get("decision_id")) != target["parent_action"]):
                raise ValueError("G52 父代已接受弃牌与 G49 不一致")
            legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {action.get("action_key"): action for action in legal_list}
            if (len(legal) != len(legal_list) or
                    target["parent_action"] not in legal or
                    target["candidate_action"] not in legal):
                raise ValueError("G52 同窗生产合法弃牌对缺失")
            observation = observation_from_json(raw["observation"])
            if observation.remaining_tile_count != target["wall_remaining"]:
                raise ValueError("G52 墙余与 G49 冻结记录不一致")
            pair = {}
            started = time.perf_counter()
            error = None
            for arm, action_key in (("parent", target["parent_action"]),
                                    ("candidate", target["candidate_action"])):
                try:
                    root = evaluate_root(observation, legal[action_key], config)
                    production_mass = g17._one_draw_mass(legal[action_key], observation.seat)
                    if production_mass is None or production_mass != root["first_hu_mass"]:
                        raise ValueError("G52 第一摸条件结算与生产 value_facts 不一致")
                    pair[arm] = {**g18._summary(root), "routes": _route_summary(root)}
                except (ValueError, FactsAnalysisError) as exc:
                    error = type(exc).__name__ + ": " + str(exc)[:180]
                    break
            elapsed = (time.perf_counter() - started) * 1000
            timings.append(elapsed)
            row = {"room_id": target["room_id"], "game_id": key[0],
                   "round_no": key[1], "trigger_seq": key[2],
                   "parent_action": target["parent_action"],
                   "candidate_action": target["candidate_action"],
                   "elapsed_ms": round(elapsed, 3)}
            if error is not None:
                row["unavailable"] = error
                counts["unavailable"] += 1
                rows.append(row)
                continue
            if pair["parent"]["first_capacity"] != pair["candidate"]["first_capacity"]:
                raise ValueError("G52 两臂第一摸总公开容量不同")
            row.update(pair)
            row["delta"] = {
                s: {mode: pair["candidate"]["conditional_value"][s][mode] -
                           pair["parent"]["conditional_value"][s][mode]
                    for mode in MODES}
                for s in SURVIVALS
            }
            row["route_delta"] = {}
            for mode in MODES:
                row["route_delta"][mode] = {}
                for route in ROUTES:
                    parent_route = pair["parent"]["routes"][mode][route]
                    candidate_route = pair["candidate"]["routes"][mode][route]
                    if parent_route is None or candidate_route is None:
                        row["route_delta"][mode][route] = None
                        continue
                    row["route_delta"][mode][route] = {
                        name: candidate_route[name] - parent_route[name]
                        for name in parent_route
                    }
            counts["complete_pair"] += 1
            tables["complete_pair"].add(key[0])
            first = row["delta"]["0.0"]["unrestricted"]
            counts["first_hu_" + _sign(first)] += 1
            for s in ("0.5", "1.0"):
                for mode in MODES:
                    delta = row["delta"][s][mode]
                    counts[f"s{s}_{mode}_{_sign(delta)}"] += 1
                    if delta > 1e-9 and first <= 1e-9:
                        counts[f"s{s}_{mode}_positive_beyond_first"] += 1
                        tables[f"s{s}_{mode}_positive_beyond_first"].add(key[0])
            for mode in MODES:
                for route in ROUTES:
                    delta = row["route_delta"][mode][route]
                    if delta is None:
                        counts[f"{mode}_{route}_unavailable"] += 1
                        continue
                    counts[f"{mode}_{route}_need_{_sign(-delta['expected_natural_need'])}"] += 1
                    counts[f"{mode}_{route}_white_{_sign(delta['expected_whites_held'])}"] += 1
            rows.append(row)
    if seen != set(targets) or len(rows) != 102:
        raise ValueError("G52 冻结 102 窗未全量复原")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    timings.sort()
    result = {"schema": "g52-g49-shared-horizon/1", "outcome_blind": True,
              "source_g49_sha256": _sha(G49),
              "joint_script_sha256": _sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py")),
              "probe_script_sha256": _sha(Path(__file__)),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "official_rooms": len(frozen["rooms"]), "complete_official_tables": 909,
              "targets": len(targets), "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "elapsed_ms_p50": round(timings[len(timings) // 2], 3),
              "elapsed_ms_p95": round(timings[int(len(timings) * .95)], 3),
              "elapsed_ms_max": round(timings[-1], 3),
              "rows_sha256": _sha(ROWS),
              "boundary": "结果盲条件两次本人摸牌；公开未见容量不等于牌墙概率，s 非继续概率；无对手先胡、鸣牌或未来墙。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"],
                      "table_coverage": result["table_coverage"],
                      "elapsed_ms_p95": result["elapsed_ms_p95"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
