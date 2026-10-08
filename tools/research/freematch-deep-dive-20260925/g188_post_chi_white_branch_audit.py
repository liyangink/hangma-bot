#!/usr/bin/env python3
"""G188：用新增的生产分支事实复核 G185 结果盲官方窗口。"""

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

from hangma_bot.application.audit_codec import observation_from_json

import c31_action_layer_gap as c31
import g11_cross_family_action_atlas as atlas
import g185_post_chi_white_route_reach as g185


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g188-post-chi-white-branch-audit-20260928/result.json')


def sha(path: Path) -> str:
    """绑定冻结来源与本次只读分析器；不落盘官方认证信息。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """只复核 G185 预先选定的窗口，不读取后续牌墙或桌赛结算。"""

    if OUT.exists():
        raise FileExistsError("G188 结果已存在，拒绝覆盖")
    previous = json.loads(g185.OUT.read_text(encoding="utf-8"))
    if previous["frozen_rooms_sha256"] != sha(atlas.FROZEN):
        raise ValueError("冻结官方房清单摘要漂移")
    if previous["script_sha256"] != sha(Path(g185.__file__)):
        raise ValueError("G185 来源脚本摘要漂移")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if previous["parent_source_sha256"] != frozen["parent_source_sha256"]:
        raise ValueError("R18 v2 父代源码身份漂移")

    targets = {
        (row["room_id"], row["game_id"], row["round_no"], row["trigger_seq"]): row
        for row in previous["rows"]
    }
    if len(targets) != len(previous["rows"]):
        raise ValueError("G185 同一吃响应窗口重复")
    target_rooms = {key[0] for key in targets}
    seen: set[tuple[str, str, int, int]] = set()
    counts: Counter[str] = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    rows: list[dict] = []
    for room in frozen["rooms"]:
        if room["room_id"] not in target_rooms:
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("官方父代决策文件长度漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("官方父代发布源码摘要漂移")
        for context, raw, _plan in atlas.source.screen._iter_decisions(audit):
            if (raw.get("window_key") or {}).get("phase") != "response_chi":
                continue
            key = (room["room_id"], context.get("game_id"),
                   context.get("round_no"), context.get("trigger_seq"))
            if key not in targets:
                continue
            if key in seen:
                raise ValueError("G185 来源窗口在官方审计中重复")
            seen.add(key)
            original = targets[key]
            observation = observation_from_json(raw["observation"])
            current = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            old_candidates = {
                item["action_key"]: item
                for item in (raw.get("rules") or {}).get("legal_candidates") or []
            }
            new_candidates = {item.action_key: item for item in current.legal_candidates}
            if set(new_candidates) != set(old_candidates):
                raise ValueError("生产规则合法动作集与冻结父代审计不同")
            for choice in original["choices"]:
                action_key = choice["action_key"]
                facts = new_candidates[action_key].facts
                if facts is None or facts.followup_branches is None:
                    raise ValueError("吃候选的后继分支不可分析")
                white = next((branch for branch in facts.followup_branches
                              if branch.followup_discard == "白"), None)
                if white is None or white.baotou_after is None:
                    raise ValueError("白后继或弃后爆头事实缺失")
                if (white.combined_shanten, white.support_remaining,
                        facts.best_followup_discard) != (
                            choice["white_branch_shanten"],
                            choice["white_branch_public_support"],
                            choice["best_followup_discard"]):
                    raise ValueError("G185 旧牌效事实与重新分析不同")
                old_facts = old_candidates[action_key].get("facts") or {}
                old_white = g185.white_branch(old_candidates[action_key])
                if (old_white is None
                        or old_facts.get("baotou_after") is not True
                        or old_white.get("combined_shanten") != white.combined_shanten
                        or old_white.get("support_remaining") != white.support_remaining):
                    raise ValueError("G185 原行动前规则事实不符")
                same_shape = choice["white_same_best_shanten_and_support"]
                counts["choices"] += 1
                counts["post_discard_baotou_" + str(white.baotou_after)] += 1
                counts["same_shape_" + str(same_shape)] += 1
                counts["baotou_" + str(white.baotou_after)
                       + "_same_shape_" + str(same_shape)] += 1
                counts["four_white_" + str(white.four_white_qualified_after)] += 1
                counts["chain_" + str(white.chain_count_after)] += 1
                if white.baotou_after:
                    scopes["post_discard_baotou"].add(key[1])
                rows.append({
                    "room_id": key[0], "game_id": key[1], "round_no": key[2],
                    "trigger_seq": key[3], "seat": original["seat"],
                    "white_held_before": original["white_held"],
                    "chain_count_before": original["chain_count"],
                    "action_key": action_key,
                    "white_same_best_shanten_and_support": same_shape,
                    "white_followup_baotou_after": white.baotou_after,
                    "white_followup_chain_count_after": white.chain_count_after,
                    "white_followup_chain_piao_after": white.chain_piao_after,
                    "white_followup_four_white_qualified_after":
                        white.four_white_qualified_after,
                })
    if seen != set(targets) or counts["choices"] != sum(
            len(row["choices"]) for row in previous["rows"]):
        raise ValueError("未完整覆盖 G185 的结果盲窗口与吃候选")
    rows.sort(key=lambda item: (item["room_id"], item["game_id"],
                                item["round_no"], item["trigger_seq"],
                                item["action_key"]))
    result = {
        "schema": "g188-post-chi-white-branch-audit/1",
        "g185_result_sha256": sha(g185.OUT),
        "frozen_rooms_sha256": sha(atlas.FROZEN),
        "script_sha256": sha(Path(__file__)),
        "parent_source_sha256": frozen["parent_source_sha256"],
        "source_windows": len(seen),
        "source_complete_tables": previous["complete_official_tables"],
        "counts": dict(sorted(counts.items())),
        "scopes": {name: {
            "complete_tables": len(game_ids),
            "gain_per_reached_table_needed_for_plus2_over_all":
                2 * previous["complete_official_tables"] / len(game_ids),
        } for name, game_ids in sorted(scopes.items())},
        "rows": rows,
        "boundary": "弃后爆头与飘链为当前可见规则事实；不代表下一摸概率或反事实桌分。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
                   + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
