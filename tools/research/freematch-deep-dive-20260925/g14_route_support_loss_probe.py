#!/usr/bin/env python3
"""结果盲压力测试：最短自然完成组合失去一种公开支持后还剩多少。"""

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
from itertools import combinations_with_replacement
import gzip
import hashlib
import json
from pathlib import Path
import time

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as hands
import g13_two_draw_baotou_support as public
import g14_latent_next_draw_audit as latent
import g14_natural_second_discard_distribution as second
from hangma_bot.hangma._standard import need as standard_need
from hangma_bot.hangma.internal_types import TILE_ORDER


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-route-support-loss-20260927')
NATURAL = tuple(TILE_ORDER[:33])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _route_support(after: Counter, melds: int, capacity: dict[str, int]) -> dict:
    """精确列举 2/3 张最短自然补牌多重集；不是合法后继或墙概率。"""
    counts = tuple(after[code] for code in NATURAL)
    left = 4 - melds
    if not 1 <= left <= 4:
        raise ValueError("剩余面子数越界")
    gap = standard_need(counts, 0, left, True)
    result = {"natural_need": gap, "routes": 0, "q1": 0,
              "tested_multisets": 0}
    if gap not in (2, 3):
        return result
    support = tuple(i for i, code in enumerate(NATURAL) if capacity[code] > 0)
    cap = tuple(capacity[code] for code in NATURAL)
    saturated = Counter()
    routes = 0
    tested = 0
    examples = []
    for indices in combinations_with_replacement(support, gap):
        multiset = Counter(indices)
        if any(amount > cap[i] for i, amount in multiset.items()):
            continue
        tested += 1
        drawn = tuple(counts[i] + multiset[i] for i in range(33))
        if standard_need(drawn, 0, left, True) != 0:
            continue
        routes += 1
        if len(examples) < 5:
            examples.append([NATURAL[i] for i in indices])
        for i, amount in multiset.items():
            if amount == cap[i]:
                saturated[i] += 1
    result.update({"routes": routes,
                   "q1": routes - max(saturated.values(), default=0),
                   "tested_multisets": tested,
                   "route_examples": examples})
    return result


def main() -> None:
    """复原既定 237 窗两臂，只读玩家可见事实，不读未来或结算。"""
    if OUT.exists():
        raise SystemExit("路线压力结果已存在，拒绝覆盖")
    source = latent.SOURCE
    previous = json.loads((source / "result.json").read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (previous.get("outcome_blind") is not True or
            previous["rows_sha256"] != _sha(source / "rows.jsonl.gz") or
            previous["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("冻结父代或源窗口身份漂移")
    targets = {}
    with gzip.open(source / "rows.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            if item["tier"] == "same_exact_immediate_vectors":
                key = (item["game_id"], item["round_no"], item["trigger_seq"])
                if key in targets:
                    raise ValueError("严格目标窗重复")
                targets[key] = item
    if len(targets) != previous["counts"]["same_exact_immediate_vectors"]:
        raise ValueError("严格层目标数量漂移")
    rows = []
    counts = Counter()
    scopes = defaultdict(set)
    seen = set()
    started = time.monotonic()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("房间审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码身份漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("目标重复或房间错配")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != target["parent_action"]
                    or accepted.get(context["decision_id"]) != target["parent_action"]
                    or target["alternative_action"] not in legal):
                raise ValueError("父代已接受或备选合法性漂移")
            parsed = hands._hand(raw["observation"])
            if parsed is None:
                raise ValueError("目标正常摸打无法复原")
            full, _, melds = parsed
            discards, exposed = public._public_counts(raw["observation"])
            scores = {}
            for arm, action in (("parent", target["parent_action"]),
                                ("alternative", target["alternative_action"])):
                after = hands._after_discard(full, action)
                if after is None:
                    raise ValueError("目标弃牌不在手牌")
                capacity = second._capacity(after, discards, exposed, action)
                scores[arm] = _route_support(after, melds, capacity)
            p, a = scores["parent"], scores["alternative"]
            if p["natural_need"] != a["natural_need"]:
                counts["need_mismatch"] += 1
            if p["natural_need"] not in (2, 3) or a["natural_need"] not in (2, 3):
                direction = "outside_gap_scope"
            else:
                direction = ("q1_better" if a["q1"] > p["q1"] else
                             "q1_worse" if a["q1"] < p["q1"] else "q1_equal")
            counts[direction] += 1
            scopes[direction].add(key[0])
            if direction == "q1_better" and not any(
                    target["old_action"][old] for old in ("g10", "g11")):
                counts["q1_better_outside_g10_g11"] += 1
                scopes["q1_better_outside_g10_g11"].add(key[0])
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "alternative_action": target["alternative_action"],
                         "white_after": target["white_after"],
                         "score_gap": target["score_gap"],
                         "old_action": target["old_action"],
                         "parent": p, "alternative": a,
                         "direction": direction})
    if seen != set(targets) or len(rows) != len(targets):
        raise ValueError("严格目标窗未全量复原")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g14-route-support-loss/1", "outcome_blind": True,
              "source_latent_result_sha256": _sha(source / "result.json"),
              "source_latent_rows_sha256": _sha(source / "rows.jsonl.gz"),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "script_sha256": _sha(Path(__file__)), "rows_sha256": _sha(rows_path),
              "targets": len(targets), "counts": dict(sorted(counts.items())),
              "scopes": {name: len(ids) for name, ids in sorted(scopes.items())},
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "boundary": "短缺口全自然完成组合的静态公开支持；不含未来墙、他家暗手、合法响应和桌分。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                                sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"],
                      "elapsed_seconds": result["elapsed_seconds"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
