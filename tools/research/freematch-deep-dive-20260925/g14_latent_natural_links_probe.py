#!/usr/bin/env python3
"""结果盲筛查：即时有效牌相同时，未被计入的自然两张牌连接能否区分弃牌。"""

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

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
import g13_two_draw_baotou_support as public
import g14_discard_width_baseline as width


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-latent-natural-links-20260927')
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
P28A = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-exact-overlap-20260927/rows.jsonl.gz')
P28B = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-b-exact-overlap-20260927/rows.jsonl.gz')


def _sha(path: Path) -> str:
    """冻结来源与本脚本摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _support_vector(facts: dict, field: str) -> tuple[tuple[str, int], ...] | None:
    """逐牌公开未见数；缺失、重复或越界时不伪造零。"""
    entries = facts.get(field)
    if not isinstance(entries, list):
        return None
    result = []
    for item in entries:
        code, amount = item.get("code"), item.get("remaining_estimate")
        if not isinstance(code, str) or type(amount) is not int or not 0 <= amount <= 4:
            return None
        result.append((code, amount))
    if len(set(code for code, _ in result)) != len(result):
        return None
    return tuple(sorted(result))


def _natural_pair_completions(after: Counter) -> set[str]:
    """两张自然牌可补成刻子/顺子的牌码集合；只作结构候选，不代替规则有效牌。"""
    result: set[str] = set()
    for suffix in "wbt":
        counts = [0] + [after[f"{rank}{suffix}"] for rank in range(1, 10)]
        for rank in range(1, 10):
            if counts[rank] >= 2:
                result.add(f"{rank}{suffix}")
            if rank <= 8 and counts[rank] and counts[rank + 1]:
                if rank >= 2:
                    result.add(f"{rank - 1}{suffix}")
                if rank <= 7:
                    result.add(f"{rank + 2}{suffix}")
            if rank <= 7 and counts[rank] and counts[rank + 2]:
                result.add(f"{rank + 1}{suffix}")
    for code in "东南西北中发":
        if after[code] >= 2:
            result.add(code)
    return result


def _latent(after: Counter, action: str, facts: dict,
            discards: Counter, exposed: Counter) -> dict | None:
    """当前非即时有效的自然接牌公开容量上界；不是可摸墙概率。"""
    immediate = _support_vector(facts, "standard_useful_tiles")
    if immediate is None:
        return None
    immediate_codes = {code for code, amount in immediate if amount > 0}
    visible_discards = discards.copy()
    visible_discards[action.split(":", 1)[1]] += 1
    support = {}
    for code in sorted(_natural_pair_completions(after) - immediate_codes):
        upper = 4 - after[code] - max(visible_discards[code], exposed[code])
        if not 0 <= upper <= 4:
            raise ValueError("本人/公开牌计数超过同牌四张上限")
        if upper > 0:
            support[code] = upper
    return {"types": len(support), "capacity_upper": sum(support.values()),
            "tile_upper": support}


def _known_old_actions() -> tuple[dict, dict, dict, dict]:
    """旧失败动作只按同一官方窗口精确键比较；P28 的范围有限。"""
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11old = json.loads(G11.read_text(encoding="utf-8"))
    if g10.get("outcome_blind") is not True or g11old.get("outcome_blind") is not True:
        raise ValueError("旧动作图谱不是结果盲来源")
    old10 = {(r["game_id"], r["round_no"], r["trigger_seq"]): r["alternate_action"]
             for r in g10["rows"]}
    old11 = {(r["game_id"], r["round_no"], r["trigger_seq"]): r["candidate_action"]
             for r in g11old["changed"]}
    old28a, old28b = {}, {}
    with gzip.open(P28A, "rt", encoding="utf-8") as stream:
        for line in stream:
            r = json.loads(line)
            old28a[(r["game_id"], r["round_no"], r["trigger_seq"])] = r["p28_a_action"]
    with gzip.open(P28B, "rt", encoding="utf-8") as stream:
        for line in stream:
            r = json.loads(line)
            old28b[(r["game_id"], r["round_no"], r["trigger_seq"])] = r["p28_b_action"]
    return old10, old11, old28a, old28b


def _tier(parent: dict, alternate: dict, pf: dict, af: dict) -> str | None:
    """从旧量摘要相同推进到逐牌向量也相同的严格对照层。"""
    for key in ("standard_shanten", "combined_shanten"):
        if parent[key] is None or alternate[key] != parent[key]:
            return None
    if parent["seven_shanten"] is not None:
        if alternate["seven_shanten"] is None or alternate["seven_shanten"] > parent["seven_shanten"]:
            return None
    if any(parent[key] is None or alternate[key] is None for key in ("standard", "combined")):
        return None
    if any(alternate[key][0] < parent[key][0] for key in ("standard", "combined")):
        return None
    if (alternate["standard"] != parent["standard"] or
            alternate["combined"] != parent["combined"]):
        return "old_capacity_or_types_differ"
    pstd = _support_vector(pf, "standard_useful_tiles")
    astd = _support_vector(af, "standard_useful_tiles")
    pc = _support_vector(pf, "useful_tiles")
    ac = _support_vector(af, "useful_tiles")
    if None in (pstd, astd, pc, ac):
        return None
    return ("same_exact_immediate_vectors" if pstd == astd and pc == ac
            else "same_old_summary_different_vectors")


def main() -> None:
    """扫描冻结父代已接受弃牌，逐窗挑唯一最高结构备选，不看任何结果。"""
    if OUT.exists():
        raise SystemExit("G14 潜在连接结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    old10, old11, old28a, old28b = _known_old_actions()
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11old = json.loads(G11.read_text(encoding="utf-8"))
    if (len(complete) != 909 or g10["source_parent_sha256"] != frozen["parent_source_sha256"]
            or g11old["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("父代母体或旧行为源码身份漂移")
    counts = Counter()
    scopes = defaultdict(set)
    strata = defaultdict(Counter)
    examples = []
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("房间父代源码身份漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if (context.get("game_id") not in complete or
                    (raw.get("window_key") or {}).get("phase") != "draw"):
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda x: x.get("rank", 10**9))
            if not ranked:
                continue
            parent_action = ranked[0].get("action_key")
            if (not isinstance(parent_action, str) or not parent_action.startswith("discard:")
                    or accepted.get(context.get("decision_id")) != parent_action):
                continue
            hand = g11._hand(raw.get("observation") or {})
            if hand is None:
                continue
            full, _, _melds = hand
            parent_after = g11._after_discard(full, parent_action)
            if parent_after is None:
                raise ValueError("父代已接受弃牌不在手牌")
            if parent_after["白"] < 1:
                continue
            legal_raw = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in legal_raw}
            if len(legal) != len(legal_raw) or parent_action not in legal:
                raise ValueError("父代规则动作缺失或重复")
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            if type(scores.get(parent_action)) not in (int, float):
                continue
            discards, exposed = public._public_counts(raw["observation"])
            pf = legal[parent_action]
            pshape = width._shape(pf)
            platent = _latent(parent_after, parent_action, pf, discards, exposed)
            if platent is None:
                continue
            counts["parent_keeps_white_valid"] += 1
            choices = defaultdict(list)
            for action, af in legal.items():
                if action == parent_action or not action.startswith("discard:"):
                    continue
                after = g11._after_discard(full, action)
                if after is None or after["白"] != parent_after["白"]:
                    continue
                ashape = width._shape(af)
                tier = _tier(pshape, ashape, pf, af)
                if tier is None:
                    continue
                alatent = _latent(after, action, af, discards, exposed)
                if alatent is None or alatent["capacity_upper"] <= platent["capacity_upper"]:
                    continue
                score = scores.get(action)
                if type(score) not in (int, float):
                    continue
                gap = float(scores[parent_action]) - float(score)
                if gap < 0:
                    raise ValueError("父代首选比分低于备选")
                if gap > 3:
                    continue
                choices[tier].append((action, alatent, ashape, gap))
            if not choices:
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            for tier, options in choices.items():
                action, alt, ashape, gap = min(options, key=lambda item: (
                    -item[1]["capacity_upper"], -item[1]["types"], item[3], item[0]))
                marker = tier
                counts[marker] += 1
                scopes[marker].add(context["game_id"])
                strata[f"white_{parent_after['白']}"][marker] += 1
                old = {"g10": old10.get(key) == action, "g11": old11.get(key) == action,
                       "p28a": old28a.get(key) == action, "p28b": old28b.get(key) == action,
                       "p28_observed": key in old28a}
                if not old["g10"] and not old["g11"]:
                    counts[marker + "_outside_g10_g11"] += 1
                    scopes[marker + "_outside_g10_g11"].add(context["game_id"])
                if old["p28_observed"]:
                    counts[marker + "_p28_observed"] += 1
                    if old["p28a"] or old["p28b"]:
                        counts[marker + "_same_p28_action"] += 1
                record = {"room_id": room["room_id"], "game_id": key[0],
                          "round_no": key[1], "trigger_seq": key[2],
                          "parent_action": parent_action, "alternative_action": action,
                          "tier": tier, "white_after": parent_after["白"],
                          "score_gap": gap, "parent_shape": pshape, "alternative_shape": ashape,
                          "parent_latent": platent, "alternative_latent": alt,
                          "old_action": old}
                rows.append(record)
                if len(examples) < 12:
                    examples.append(record)
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g14-latent-natural-links/1", "outcome_blind": True,
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "source_g10_sha256": _sha(G10), "source_g11_sha256": _sha(G11),
              "source_p28a_sha256": _sha(P28A), "source_p28b_sha256": _sha(P28B),
              "script_sha256": _sha(Path(__file__)), "rows_sha256": _sha(rows_path),
              "complete_official_tables": len(complete), "counts": dict(sorted(counts.items())),
              "scopes": {name: len(ids) for name, ids in sorted(scopes.items())},
              "strata": {name: dict(sorted(values.items()))
                         for name, values in sorted(strata.items())},
              "examples": examples,
              "boundary": "仅结果盲自然两张连接，不计独立牌块；公开未见上界含他家暗手与保留区。P28 仅在旧 371 窗有精确动作，其他窗不能称与 P28 不同。结构改善不是收益。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                                sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
