#!/usr/bin/env python3
"""G18 严格即时向量层：两次本人自摸条件价值与自然进度的结果盲预检。"""

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
from g18_two_self_draw_joint import evaluate_root
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-latent-natural-links-20260927')
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
P28A = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-exact-overlap-20260927')
P28B = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-b-exact-overlap-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g18-two-self-draw-strict-20260927/result.json')
ROWS = OUT.with_name("rows.jsonl.gz")
SURVIVAL_SENSITIVITY = (0.0, 0.5, 1.0)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def _summary(root: dict) -> dict:
    """把条件树归约为不同继续系数/抓打包络的可比较值。"""

    total = root["first_draw_public_capacity"]
    if total <= 0:
        raise ValueError("第一摸公开容量必须为正")
    scores = {}
    natural = {}
    for mode in ("restricted", "unrestricted"):
        natural[mode] = sum(
            edge["capacity"] *
            edge["best_second"][mode]["best_natural_progress"]["ordinary_natural_progress_capacity"]
            for edge in root["edges"]
        ) / total
        for survival in SURVIVAL_SENSITIVITY:
            weighted = 0.0
            for edge in root["edges"]:
                leaf = edge["best_second"][mode]["best_second_hu"]
                if leaf["capacity"] <= 0:
                    raise ValueError("第二摸公开容量必须为正")
                continuation = survival * leaf["mass"] / leaf["capacity"]
                immediate = edge["first_hu_score"] or 0
                weighted += edge["capacity"] * max(immediate, continuation)
            scores[str(survival)] = scores.get(str(survival), {}) | {mode: weighted / total}
    return {"first_hu_mass": root["first_hu_mass"],
            "first_capacity": total, "conditional_value": scores,
            "ordinary_natural_progress_capacity": natural,
            "root_whites_held": root["root_whites_held"]}


def _old_actions() -> tuple[dict, dict, dict, dict]:
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11 = json.loads(G11.read_text(encoding="utf-8"))
    if g10.get("outcome_blind") is not True or g11.get("outcome_blind") is not True:
        raise ValueError("旧动作负控结果不是结果盲")
    key = lambda row: (row["game_id"], row["round_no"], row["trigger_seq"])
    a = {key(row): row["alternate_action"] for row in g10["rows"]}
    b = {key(row): row["candidate_action"] for row in g11["changed"]}
    p28a = {key(row): row["p28_a_action"] for row in _load_rows(_project_file(_PROJECT_ROOT, P28A / "rows.jsonl.gz"))
            if row.get("reduction_complete") is True and isinstance(row.get("p28_a_action"), str)}
    p28b = {key(row): row["p28_b_action"] for row in _load_rows(_project_file(_PROJECT_ROOT, P28B / "rows.jsonl.gz"))
            if row.get("reduction_complete") is True and isinstance(row.get("p28_b_action"), str)}
    return a, b, p28a, p28b


def main() -> None:
    """全量重放 237 个旧即时向量全同窗口，不读取任何桌赛结局。"""

    if OUT.exists() or ROWS.exists():
        raise SystemExit("G18 严层结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or
            source.get("parent_source_sha256") != frozen["parent_source_sha256"] or
            source.get("rows_sha256") != _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"))):
        raise ValueError("G14 严格输入或冻结父代摘要漂移")
    targets = {}
    for row in _load_rows(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")):
        if row.get("tier") != "same_exact_immediate_vectors":
            continue
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        if key in targets:
            raise ValueError("G14 严格窗口重复")
        targets[key] = row
    if len(targets) != 237:
        raise ValueError("G14 237 个严格窗口漂移")
    old_g10, old_g11, old_p28a, old_p28b = _old_actions()
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("核验完整桌母体漂移")
    config = RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                        base_score=1, you_cai_bi_kao=False)
    rows = []
    counts = Counter()
    scope: dict[str, set[str]] = defaultdict(set)
    seen = set()
    elapsed_ms = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作文件字节数漂移")
        payload = (json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                   .get("payload") or {})
        release = payload.get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        if (payload.get("ruleset_version") != config.ruleset_version or
                payload.get("base_score") != config.base_score or
                payload.get("you_cai_bi_kao") is not False):
            raise ValueError("冻结房规则配置与两摸条件树不一致")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"] or key[0] not in complete:
                raise ValueError("G18 目标房、完整桌或唯一性漂移")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context.get("decision_id")) != target["parent_action"]):
                raise ValueError("冻结父代已接受首选不一致")
            legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {action.get("action_key"): action for action in legal_list}
            if (len(legal) != len(legal_list) or
                    target["parent_action"] not in legal or
                    target["alternative_action"] not in legal):
                raise ValueError("生产合法弃牌对缺失")
            observation = observation_from_json(raw["observation"])
            pair = {}
            error = None
            started = time.perf_counter()
            for name, action_key in (("parent", target["parent_action"]),
                                     ("alternative", target["alternative_action"])):
                action = legal[action_key]
                production_mass = g17._one_draw_mass(action, observation.seat)
                try:
                    result = evaluate_root(observation, action, config)
                    if production_mass != result["first_hu_mass"]:
                        raise ValueError("G18 第一摸条件结算未与生产 value_facts 对账")
                    pair[name] = _summary(result)
                except (ValueError, FactsAnalysisError) as exc:
                    error = type(exc).__name__ + ": " + str(exc)[:160]
                    break
            timing = (time.perf_counter() - started) * 1000
            elapsed_ms.append(timing)
            entry = {"room_id": room["room_id"], "game_id": key[0],
                     "round_no": key[1], "trigger_seq": key[2],
                     "parent_action": target["parent_action"],
                     "alternative_action": target["alternative_action"],
                     "g10_old_action": old_g10.get(key),
                     "g11_old_action": old_g11.get(key),
                     "p28a_action_if_replayed": old_p28a.get(key),
                     "p28b_action_if_replayed": old_p28b.get(key),
                     "elapsed_ms": round(timing, 3)}
            if error is not None:
                entry["unavailable"] = error
                counts["unavailable"] += 1
            else:
                entry.update(pair)
                counts["complete_pair"] += 1
                scope["complete_pair"].add(key[0])
                delta = {}
                for survival in SURVIVAL_SENSITIVITY:
                    label = str(survival)
                    delta[label] = {
                        mode: pair["alternative"]["conditional_value"][label][mode] -
                              pair["parent"]["conditional_value"][label][mode]
                        for mode in ("restricted", "unrestricted")
                    }
                entry["delta"] = delta
                first_same = all(abs(value) < 1e-9 for value in delta["0.0"].values())
                entry["first_value_same"] = first_same
                positive = all(delta[label][mode] > 1e-9
                               for label in ("0.5", "1.0")
                               for mode in ("restricted", "unrestricted"))
                entry["strict_two_draw_positive"] = first_same and positive
                if first_same:
                    counts["first_value_same"] += 1
                    scope["first_value_same"].add(key[0])
                if first_same and positive:
                    counts["strict_two_draw_positive"] += 1
                    scope["strict_two_draw_positive"].add(key[0])
                    if (target["alternative_action"] != old_g10.get(key) and
                            target["alternative_action"] != old_g11.get(key)):
                        counts["strict_positive_not_g10_g11_action"] += 1
                        scope["strict_positive_not_g10_g11_action"].add(key[0])
                for label in ("0.5", "1.0"):
                    for mode in ("restricted", "unrestricted"):
                        value = delta[label][mode]
                        sign = "positive" if value > 1e-9 else "negative" if value < -1e-9 else "equal"
                        name = f"s{label}_{mode}_{sign}"
                        counts[name] += 1
                        scope[name].add(key[0])
                for mode in ("restricted", "unrestricted"):
                    natural_delta = (pair["alternative"]["ordinary_natural_progress_capacity"][mode] -
                                     pair["parent"]["ordinary_natural_progress_capacity"][mode])
                    name = (f"natural_{mode}_positive" if natural_delta > 1e-9 else
                            f"natural_{mode}_negative" if natural_delta < -1e-9 else
                            f"natural_{mode}_equal")
                    counts[name] += 1
                    scope[name].add(key[0])
            rows.append(entry)
    if seen != set(targets) or len(rows) != 237:
        raise ValueError("G18 严格窗口未全量复原")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    elapsed_ms.sort()
    result = {"schema": "g18-two-self-draw-strict/1", "outcome_blind": True,
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
              "elapsed_ms_max": elapsed_ms[-1],
              "rows_sha256": _sha(ROWS),
              "boundary": "仅条件两次本人自摸，s 是敏感性参数不是生存概率；未来他家响应、先胡、墙末与抓打圈归属未知；旧 P28 仅已重放窗有精确动作。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "table_coverage": result["table_coverage"],
                      "elapsed_ms_p95": result["elapsed_ms_p95"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
