#!/usr/bin/env python3
"""用生产评分视图重放冻结 G7 自然窗，核对与已关闭 G6 的行为重合。"""

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
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import natural_shape_loss_screen as screen  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE, R18_INTEGRATED_POSITIVE_V2_SHA256,
)

SELECTED = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-three-draw-exposure-20260927/result.json')
G6 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G6-TIE-ROUTE-PARETO-V1.py')
G6_SHA256 = "a680bc44e19b369c27ff176ca0e84c50ff61ba1a51bb348746b06810c4c818e8"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-g6-overlap-20260927/result.json')


def _best(batch):
    if batch.status != "SCORED":
        raise ValueError("父代或 G6 在冻结官方窗口弃权")
    return min(batch.entries, key=lambda item: (-item.score, item.action_key)).action_key


def _useful_distribution(raw: dict, key: str):
    actions = {item.get("action_key"): item for item in
               (raw.get("rules") or {}).get("legal_candidates") or []}
    facts = (actions.get(key) or {}).get("facts") or {}
    tiles = facts.get("useful_tiles")
    if not isinstance(tiles, list):
        return None
    values = []
    for item in tiles:
        code = item.get("code")
        amount = item.get("remaining_estimate")
        if not isinstance(code, str) or type(amount) is not int or not 0 <= amount <= 4:
            return None
        values.append((code, amount))
    return tuple(sorted(values))


def _requests(rows):
    needed = defaultdict(set)
    for row in rows:
        needed[row["room"]].add((row["game_id"], row["round_no"], row["trigger_seq"]))
    found = {}
    for room, keys in needed.items():
        for run in sorted((screen.ROOT / "artifacts/sessions" / room / "audit/runs").glob("*")):
            manifest = run / "manifest.json"
            if not manifest.is_file():
                continue
            source = ((json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
                      .get("policy_release") or {}).get("candidate_source_sha256")
            if source != screen.PARENT_SHA256:
                continue
            for context, request, plan in screen._iter_decisions(run):
                key = (context.get("game_id"), context.get("round_no"),
                       context.get("trigger_seq"))
                if key not in keys:
                    continue
                if key in found and found[key][0] != request:
                    raise ValueError("冻结窗口存在不一致官方观察：" + str(key))
                found[key] = (request, plan)
            if keys.issubset(found):
                break
        if not keys.issubset(found):
            raise ValueError("冻结官方观察缺失：" + room)
    return found


def main() -> int:
    if hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise SystemExit("冻结 R18 v2 源码摘要不符")
    g6_source = G6.read_text(encoding="utf-8")
    if hashlib.sha256(g6_source.encode()).hexdigest() != G6_SHA256:
        raise SystemExit("已关闭 G6 源码摘要不符")
    selected = json.loads(SELECTED.read_text(encoding="utf-8"))
    rows = selected["selected"]
    if len(rows) != 72 or selected.get("selection_lock_sha256") is None:
        raise SystemExit("G7a 固定 72 窗与选样锁缺失")
    requests = _requests(rows)
    parent = ActionValueScorer("g7:parent-replay", R18_INTEGRATED_POSITIVE_V2_SOURCE)
    g6 = ActionValueScorer("g7:closed-g6-replay", g6_source)
    results = []
    counts = Counter()
    for row in rows:
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        raw, plan = requests[key]
        view = build_scoring_view(decision_request_from_json(raw))
        parent_key = _best(parent.score(view))
        g6_key = _best(g6.score(view))
        actual = (plan.get("candidates") or [{}])[0].get("action_key")
        if parent_key != actual or parent_key != row["a"]:
            raise ValueError("生产投影父代重放与审计不一致：" + str(key))
        new_three_only = row["delta_2"] == 0 and row["delta_3"] != 0
        useful_a = _useful_distribution(raw, row["a"])
        useful_b = _useful_distribution(raw, row["b"])
        if useful_a is None or useful_b is None:
            raise ValueError("G7a 已选窗口的一步有效牌分布不可复算：" + str(key))
        same_useful = useful_a == useful_b
        counts["windows"] += 1
        if new_three_only:
            counts["three_only"] += 1
        if same_useful:
            counts["same_full_useful_distribution"] += 1
            if new_three_only:
                counts["three_only_same_full_useful_distribution"] += 1
        if g6_key != parent_key:
            counts["g6_changed"] += 1
            if new_three_only:
                counts["three_only_g6_changed"] += 1
        if new_three_only and g6_key == row["b"]:
            counts["three_only_g6_exact_b"] += 1
        if new_three_only and same_useful and g6_key == parent_key:
            counts["three_only_same_useful_g6_unchanged"] += 1
        results.append({"game_id": key[0], "round_no": key[1], "trigger_seq": key[2],
                        "group": row["group"], "parent": parent_key,
                        "g6": g6_key, "b": row["b"],
                        "same_full_useful_distribution": same_useful,
                        "delta_2": row["delta_2"], "delta_3": row["delta_3"]})
    output = {"schema": "g7-g6-overlap/1", "parent_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
              "g6_sha256": G6_SHA256,
              "g7_selection_lock_sha256": selected["selection_lock_sha256"],
              "counts": dict(counts), "rows": results,
              "note": "生产 ScoringView 投影重放父代与 G6；仅行为重合，不是收益比较"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(output["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
