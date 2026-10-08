#!/usr/bin/env python3
"""G68：复用 G67 冻结抽样，探索父代所有合法弃牌的两摸可达前沿。"""

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

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import time

import g67_action_specific_horizon as g67
import c31_action_layer_gap as c31
from g52_shared_horizon import evaluate_root
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g68-all-discard-frontier-20260928')
MODES = ("restricted", "unrestricted")


def better(a: dict, b: dict, key: str) -> bool:
    return a[key] > b[key] + 1e-9


def main() -> None:
    if OUT.exists():
        raise SystemExit("G68 结果目录已存在，拒绝覆盖")
    selected, _ = g67.select()
    scorer = ActionValueScorer("g68-r18v2-frozen", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = []
    started = time.perf_counter()
    for window, pred in selected:
        observation = observation_from_json(window["observation"])
        request = g67.request_for(observation)
        batch = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
        if batch.status != "SCORED":
            raise ValueError("G68 父代评分失败")
        ordered = sorted(batch.entries, key=lambda item: (-item.score, item.action_key))
        if ordered[0].action_key != window["parent_top_action"]:
            raise ValueError("G68 父代首选与 G66 重建漂移")
        legal = {candidate.action_key: candidate for candidate in request.rules.legal_candidates}
        candidates = []
        failures = []
        for rank, entry in enumerate(ordered, 1):
            if not entry.action_key.startswith("discard:"):
                continue
            candidate = legal[entry.action_key]
            if candidate.value_facts is None:
                failures.append({"action": entry.action_key, "reason": "no_value_facts"})
                continue
            encoded = {"action_key": entry.action_key,
                       "value_facts": candidate_value_facts_to_json(candidate.value_facts)}
            try:
                root = evaluate_root(observation, encoded, c31.RULE_CONFIG)
            except (ValueError, TypeError) as exc:
                failures.append({"action": entry.action_key,
                                 "reason": type(exc).__name__ + ": " + str(exc)})
                continue
            candidates.append({
                "action": entry.action_key, "rank": rank, "parent_score": entry.score,
                "ordinary_shanten": candidate.facts.standard_shanten_after if candidate.facts else None,
                "ordinary_support": g67.support(candidate),
                "first_hu_value": root["first_hu_mass"] / root["first_draw_public_capacity"],
                "whites_held": root["root_whites_held"],
                **{mode: g67.horizon(root, pred["p"], mode) for mode in MODES},
            })
        parent = next((item for item in candidates if item["action"] == window["parent_top_action"]), None)
        if parent is None:
            rows.append({"identity": g67.identity(window), "status": "no_parent_tree",
                         "failures": failures})
            continue
        alternatives = []
        for item in candidates:
            if item is parent:
                continue
            protects = (item["ordinary_shanten"] is not None and
                        parent["ordinary_shanten"] is not None and
                        item["ordinary_shanten"] <= parent["ordinary_shanten"] and
                        item["ordinary_support"] is not None and
                        parent["ordinary_support"] is not None and
                        item["ordinary_support"] >= parent["ordinary_support"])
            two_draw_better = all(
                better(item[mode], parent[mode], "weighted_two_draw_value")
                for mode in MODES
            )
            first_not_better = not better(item, parent, "first_hu_value")
            second_better = all(
                better(item[mode], parent[mode], "unweighted_second_value")
                for mode in MODES
            )
            alternatives.append({**item, "protects_ordinary": protects,
                                 "two_draw_better_both": two_draw_better,
                                 "distinct_second_horizon": two_draw_better and first_not_better and second_better,
                                 "target_signal": protects and two_draw_better and first_not_better and second_better})
        rows.append({"identity": g67.identity(window), "status": "complete", "p": pred["p"],
                     "white_count": pred["features"]["whites"], "parent": parent,
                     "alternatives": alternatives, "failures": failures})
    complete = [row for row in rows if row["status"] == "complete"]
    counts = Counter()
    signal_rooms = set()
    for row in complete:
        alts = row["alternatives"]
        counts["alternatives_complete"] += len(alts)
        counts["alternative_failures"] += len(row["failures"])
        for key in ("protects_ordinary", "two_draw_better_both", "distinct_second_horizon", "target_signal"):
            counts[key + "_alternatives"] += sum(bool(item[key]) for item in alts)
            counts[key + "_windows"] += any(item[key] for item in alts)
        if any(item["target_signal"] for item in alts):
            signal_rooms.add(row["identity"][0])
    result = {
        "schema": "g68-all-discard-frontier/1", "exploratory": True,
        "selection": "复用 G67 已看结果的同一 72 窗；不可独立确认",
        "source_sha256": g67.digest(g67.SOURCE / "transfer_rows.jsonl.gz"),
        "program_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "counts": dict(sorted(counts.items())), "complete_windows": len(complete),
        "target_signal_rooms": len(signal_rooms), "elapsed_seconds": round(time.perf_counter()-started,2),
        "boundary": "仅官方当前观察与生产规则条件树；不含真实未来/赛果，且非完整桌赛效果。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz"), "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
