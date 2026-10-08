#!/usr/bin/env python3
"""核 G7 三摸差异是否超出根节点生产逐牌有效向量，避免重包宽度。"""

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

import g7_natural_three_draw_exposure as g7


HERE = Path(__file__).resolve().parent
G7 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-three-draw-exposure-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g20-g7-three-draw-novelty-20260927/result.json')
VECTOR_FIELDS = ("standard_useful_tiles", "seven_pairs_useful_tiles", "useful_tiles")
SHANTEN_FIELDS = ("standard_shanten_after", "seven_pairs_shanten_after", "shanten_after")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector(facts: dict, field: str) -> tuple[tuple[str, int], ...] | None:
    items = facts.get(field)
    if not isinstance(items, list):
        return None
    pairs = []
    for item in items:
        code, amount = item.get("code"), item.get("remaining_estimate")
        if not isinstance(code, str) or type(amount) is not int or amount < 0:
            return None
        pairs.append((code, amount))
    if len({code for code, _ in pairs}) != len(pairs):
        return None
    return tuple(sorted(pairs))


def main() -> None:
    """只读原 G7 72 窗的玩家可见规则事实，不打开任何赛后成绩。"""

    if OUT.exists():
        raise SystemExit("G20 三摸新颖性结果已存在，拒绝覆盖")
    prior = json.loads((_project_file(_PROJECT_ROOT, G7 / "result.json")).read_text(encoding="utf-8"))
    if (prior.get("schema") != "g7-natural-three-draw-exposure/1" or
            prior.get("selection_lock_sha256") != _sha(_project_file(_PROJECT_ROOT, G7 / "selection-lock.json")) or
            len(prior.get("selected") or []) != 72):
        raise ValueError("G7 固定选样或结果身份漂移")
    targets = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
               for row in prior["selected"]}
    if len(targets) != 72:
        raise ValueError("G7 72 个窗口含重复键")
    details = []
    seen = set()
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    for _group, rooms in g7.GROUPS.items():
        for room in rooms:
            audit = g7.ROOT / "artifacts/sessions" / room / "audit/runs"
            for run in sorted(audit.glob("*")):
                manifest = run / "manifest.json"
                if not manifest.is_file():
                    continue
                release = ((json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
                           .get("policy_release") or {})
                if release.get("candidate_source_sha256") != g7.screen.PARENT_SHA256:
                    continue
                for context, request, _plan in g7.screen._iter_decisions(run):
                    key = (context.get("game_id"), context.get("round_no"),
                           context.get("trigger_seq"))
                    target = targets.get(key)
                    if target is None or key in seen:
                        continue
                    if target["room"] != room:
                        raise ValueError("G7 目标窗口来源房漂移")
                    seen.add(key)
                    legal_list = (request.get("rules") or {}).get("legal_candidates") or []
                    legal = {action.get("action_key"): action for action in legal_list}
                    if (len(legal) != len(legal_list) or
                            target["a"] not in legal or target["b"] not in legal):
                        raise ValueError("G7 同窗生产合法动作缺失或重复")
                    a, b = legal[target["a"]].get("facts") or {}, legal[target["b"]].get("facts") or {}
                    same_shanten = {field: a.get(field) == b.get(field)
                                    for field in SHANTEN_FIELDS}
                    vectors = {}
                    for field in VECTOR_FIELDS:
                        left, right = _vector(a, field), _vector(b, field)
                        if left is None or right is None:
                            raise ValueError("G7 生产有效向量缺失")
                        vectors[field] = left == right
                    three_only = target["delta_2"] == 0 and target["delta_3"] != 0
                    all_current_same = all(same_shanten.values()) and all(vectors.values())
                    row = {"game_id": key[0], "round_no": key[1], "trigger_seq": key[2],
                           "a": target["a"], "b": target["b"],
                           "delta_2": target["delta_2"], "delta_3": target["delta_3"],
                           "unknown_pool": target["unknown_pool"],
                           "three_only": three_only,
                           "same_shanten": same_shanten,
                           "same_vectors": vectors,
                           "all_current_progress_same": all_current_same}
                    details.append(row)
                    for label, condition in (
                        ("all", True), ("three_only", three_only),
                        ("three_only_all_current_progress_same", three_only and all_current_same),
                        ("three_only_standard_vector_same", three_only and vectors["standard_useful_tiles"]),
                        ("three_only_positive_all_current_same", three_only and all_current_same and target["delta_3"] > 0),
                    ):
                        if condition:
                            counts[label] += 1
                            tables[label].add(key[0])
    if seen != set(targets) or len(details) != 72:
        raise ValueError("G7 72 个选定窗口未完整重建")
    output = {"schema": "g20-g7-three-draw-novelty/1", "outcome_blind": True,
              "source_g7_result_sha256": _sha(_project_file(_PROJECT_ROOT, G7 / "result.json")),
              "source_g7_lock_sha256": _sha(_project_file(_PROJECT_ROOT, G7 / "selection-lock.json")),
              "parent_source_sha256": g7.screen.PARENT_SHA256,
              "script_sha256": _sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "rows": sorted(details, key=lambda row: (row["game_id"], row["round_no"], row["trigger_seq"])),
              "boundary": "三摸值仍是无对手/无抓打圈/无结算的理想化自然摸牌容量；源 G7 选样锁在首次读数后补做，只用于探索性新颖性复核。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": output["counts"], "table_coverage": output["table_coverage"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
