#!/usr/bin/env python3
"""G19 结果盲近听持白弃牌对：一摸结算与第二次本人自摸条件值对账。"""

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
from g18_two_self_draw_joint import evaluate_root
from hangma_bot.hangma.candidate_facts import FactsAnalysisError
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g19-near-win-two-draw-20260927/result.json')
ROWS = OUT.with_name("rows.jsonl.gz")
SURVIVALS = ("0.0", "0.5", "1.0")
MODES = ("restricted", "unrestricted")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sign(value: float) -> str:
    return "positive" if value > 1e-9 else "negative" if value < -1e-9 else "equal"


def _target_rows(frozen: dict) -> dict[tuple[str, int, int], dict]:
    """只用已冻结 G14 动作选择与当前可见向听/墙余定义输入。"""

    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or source.get("rows") != 2134 or
            source.get("rows_sha256") != _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")) or
            source.get("parent_source_sha256") != frozen["parent_source_sha256"] or
            source.get("source_frozen_rooms_sha256") != _sha(atlas.FROZEN)):
        raise ValueError("G14 自然前沿或冻结父代输入漂移")
    targets = {}
    for row in g18._load_rows(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")):
        if (row["parent_shape"]["combined_shanten"] > 1 or
                row["wall_remaining"] <= 20):
            continue
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        if key in targets:
            raise ValueError("G19 预登记动作窗重复")
        targets[key] = row
    if len(targets) != 1415 or len({key[0] for key in targets}) != 582:
        raise ValueError("G19 预登记 1415 窗/582 完整桌漂移")
    return targets


def main() -> None:
    """重放指定近听窗；产出条件价值、自然进度及旧方案重合，不读赛果。"""

    if OUT.exists() or ROWS.exists():
        raise SystemExit("G19 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    targets = _target_rows(frozen)
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("完整桌母体漂移")
    old_g10, old_g11, old_p28a, old_p28b = g18._old_actions()
    config = RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                        base_score=1, you_cai_bi_kao=False)
    counts = Counter()
    scope: dict[str, set[str]] = defaultdict(set)
    rows = []
    seen = set()
    elapsed_ms = []

    def record(name: str, game_id: str) -> None:
        counts[name] += 1
        scope[name].add(game_id)

    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作文件字节数漂移")
        payload = json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}
        release = payload.get("policy_release") or {}
        if (release.get("candidate_source_sha256") != frozen["parent_source_sha256"] or
                payload.get("ruleset_version") != config.ruleset_version or
                payload.get("base_score") != config.base_score or
                payload.get("you_cai_bi_kao") is not False):
            raise ValueError("冻结房父代源码或规则配置漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"] or key[0] not in complete:
                raise ValueError("G19 目标房、完整桌或唯一性漂移")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context.get("decision_id")) != target["parent_action"]):
                raise ValueError("父代已接受动作与 G14 记录不一致")
            legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {action.get("action_key"): action for action in legal_list}
            if (len(legal) != len(legal_list) or
                    target["parent_action"] not in legal or
                    target["alternative_action"] not in legal):
                raise ValueError("G19 同窗生产合法动作缺失")
            observation = observation_from_json(raw["observation"])
            if (observation.remaining_tile_count != target["wall_remaining"] or
                    observation.seat != target["seat"]):
                raise ValueError("G14 墙余或本人座位漂移")
            pair = {}
            error = None
            started = time.perf_counter()
            for name, action_key in (("parent", target["parent_action"]),
                                     ("alternative", target["alternative_action"])):
                action = legal[action_key]
                production_mass = g17._one_draw_mass(action, observation.seat)
                try:
                    result = evaluate_root(observation, action, config)
                    if production_mass is None or production_mass != result["first_hu_mass"]:
                        raise ValueError("G19 第一摸价值与生产 value_facts 不一致")
                    pair[name] = g18._summary(result)
                except (ValueError, FactsAnalysisError) as exc:
                    error = type(exc).__name__ + ": " + str(exc)[:160]
                    break
            duration = (time.perf_counter() - started) * 1000
            elapsed_ms.append(duration)
            row = {"room_id": room["room_id"], "game_id": key[0],
                   "round_no": key[1], "trigger_seq": key[2],
                   "parent_action": target["parent_action"],
                   "alternative_action": target["alternative_action"],
                   "whites_held": target["parent_frontier"]["whites_held"],
                   "standard_shanten": target["parent_shape"]["standard_shanten"],
                   "combined_shanten": target["parent_shape"]["combined_shanten"],
                   "seven_shanten": target["parent_shape"]["seven_shanten"],
                   "policy_score_gap": target["parent_policy_score"] - target["alternate_policy_score"],
                   "g10_old_action": old_g10.get(key), "g11_old_action": old_g11.get(key),
                   "p28a_action_if_replayed": old_p28a.get(key),
                   "p28b_action_if_replayed": old_p28b.get(key),
                   "elapsed_ms": round(duration, 3)}
            if error is not None:
                row["unavailable"] = error
                record("unavailable", key[0])
                rows.append(row)
                continue
            row.update(pair)
            record("complete_pair", key[0])
            first_delta = (pair["alternative"]["conditional_value"]["0.0"]["restricted"] -
                           pair["parent"]["conditional_value"]["0.0"]["restricted"])
            row["first_delta"] = first_delta
            first_sign = _sign(first_delta)
            record("first_" + first_sign, key[0])
            delta = {}
            residual = {}
            for survival in SURVIVALS:
                delta[survival] = {}
                residual[survival] = {}
                for mode in MODES:
                    value = (pair["alternative"]["conditional_value"][survival][mode] -
                             pair["parent"]["conditional_value"][survival][mode])
                    delta[survival][mode] = value
                    residual[survival][mode] = value - first_delta
                    if survival != "0.0":
                        record(f"s{survival}_{mode}_{_sign(value)}", key[0])
                        record(f"residual_s{survival}_{mode}_{_sign(value-first_delta)}", key[0])
            row["delta"] = delta
            row["increment_beyond_first"] = residual
            robust_positive = all(delta[survival][mode] > 1e-9
                                  for survival in ("0.5", "1.0") for mode in MODES)
            novel = target["alternative_action"] not in (old_g10.get(key), old_g11.get(key),
                                                            old_p28a.get(key), old_p28b.get(key))
            row["both_envelopes_positive"] = robust_positive
            row["not_known_old_action"] = novel
            if robust_positive:
                record("both_envelopes_positive", key[0])
                record("both_positive_first_" + first_sign, key[0])
                if novel:
                    record("both_positive_not_known_old_action", key[0])
            for mode in MODES:
                natural_delta = (pair["alternative"]["ordinary_natural_progress_capacity"][mode] -
                                 pair["parent"]["ordinary_natural_progress_capacity"][mode])
                record(f"natural_{mode}_{_sign(natural_delta)}", key[0])
            rows.append(row)
    if seen != set(targets) or len(rows) != 1415:
        raise ValueError("G19 预登记窗口未全量复原")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    elapsed_ms.sort()
    result = {"schema": "g19-near-win-two-draw/1", "outcome_blind": True,
              "joint_script_sha256": _sha(_project_file(_PROJECT_ROOT, HERE / "g18_two_self_draw_joint.py")),
              "probe_script_sha256": _sha(Path(__file__)),
              "source_g14_result_sha256": _sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
              "source_g14_rows_sha256": _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "official_rooms": len(frozen["rooms"]),
              "complete_official_tables": len(complete),
              "targets": len(targets), "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(scope.items())},
              "elapsed_ms_p50": elapsed_ms[len(elapsed_ms)//2],
              "elapsed_ms_p95": elapsed_ms[int(len(elapsed_ms)*0.95)],
              "elapsed_ms_max": elapsed_ms[-1], "rows_sha256": _sha(ROWS),
              "boundary": "公开容量不是牌墙后验；s 非真实继续概率；未建模对手响应、先胡、墙末；仅 G14 既选近听动作，不证明整桌净分。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "table_coverage": result["table_coverage"],
                      "elapsed_ms_p95": result["elapsed_ms_p95"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
