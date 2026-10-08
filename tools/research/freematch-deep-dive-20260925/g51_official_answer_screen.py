#!/usr/bin/env python3
"""G51：结果盲核查两份 GLM 提案在 G49 官方改选窗的数学可达性。"""

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
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles


HERE = Path(__file__).resolve().parent
G49 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-official-behavior-20260927/result.json')
G51 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g51-glm-route-mechanisms-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g51-glm-route-mechanisms-20260927/official_static_screen.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def vector(facts: dict, name: str) -> dict[str, int] | None:
    """只采生产逐码公开未见上界；未知与重复牌码均弃权。"""

    entries = facts.get(name)
    if not isinstance(entries, list):
        return None
    result = {}
    for item in entries:
        code, value = item.get("code"), item.get("remaining_estimate")
        if not isinstance(code, str) or type(value) is not int or value < 0 or code in result:
            return None
        if code != "白" and value > 0:
            result[code] = value
    return result


def overlap(standard: dict[str, int], pairs: dict[str, int]) -> tuple[int, int]:
    """照作者 A 的 W/R 原式计算，不擅自换成已否证的总宽度公式。"""

    common = standard.keys() & pairs.keys()
    w = sum(min(min(standard[code], pairs[code]), 2) for code in common)
    r = sum(min(pairs[code], 2) for code in pairs.keys() - standard.keys())
    return w, r


def shared_count(entries: dict[str, int], unseen: dict[str, int | None]) -> int | None:
    """照作者 B 的同观察 count_unseen_tiles 口径求和；任一码未知即弃权。"""

    values = [unseen.get(code) for code in entries]
    return None if any(type(value) is not int for value in values) else sum(values)


def main() -> None:
    """只判断数值入口，不执行作者算子或打开官方后续结算。"""

    if OUT.exists():
        raise SystemExit("G51 官方静态筛查已存在，拒绝覆盖")
    source = json.loads(G49.read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or
            source["counts"]["changed_windows"] != 102):
        raise ValueError("G49 结果盲改选入口漂移")
    answers = {name: json.loads((_project_file(_PROJECT_ROOT, G51 / f"{name}.answer.txt")).read_text(encoding="utf-8"))
               for name in ("a_dual_route_exit", "b_timing_guard")}
    if any(answer.get("status") != "proposed" for answer in answers.values()):
        raise ValueError("G51 模型答卷状态不符")
    target = {key(row): row for row in source["changed"]}
    if len(target) != 102:
        raise ValueError("G49 官方改选窗口重复")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    counts = Counter()
    rows = []
    seen = set()
    rooms = {row["room_id"] for row in target.values()}
    for room in frozen["rooms"]:
        if room["room_id"] not in rooms:
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("G51 冻结官方审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != source["parent_source_sha256"]:
            raise ValueError("G51 房间父代源码身份漂移")
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            window = context.get("game_id"), context.get("round_no"), context.get("trigger_seq")
            if window not in target:
                continue
            if window in seen:
                raise ValueError("G51 官方窗口重复")
            seen.add(window)
            parent, alternate = target[window]["parent_action"], target[window]["candidate_action"]
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or ranked[0]["action_key"] != parent:
                raise ValueError("G51 官方父代动作漂移")
            legal = {item["action_key"]: item.get("facts") or {}
                     for item in (raw.get("rules") or {}).get("legal_candidates") or []}
            if parent not in legal or alternate not in legal:
                raise ValueError("G51 官方动作缺规则事实")
            request = decision_request_from_json(raw)
            unseen_tuple = count_unseen_tiles(request.observation)
            unseen = dict(zip(TILE_ORDER, unseen_tuple))
            pair = {}
            for arm, action in (("parent", parent), ("alternate", alternate)):
                facts = legal[action]
                std = vector(facts, "standard_useful_tiles")
                seven = vector(facts, "seven_pairs_useful_tiles")
                if std is None or seven is None:
                    raise ValueError("G51 官方目标窗缺逐码有效张事实")
                pair[arm] = {"standard_tier": facts.get("standard_shanten_after"),
                             "seven_tier": facts.get("seven_pairs_shanten_after"),
                             "combined_tier": facts.get("shanten_after"),
                             "a_overlap_and_pairs_only": overlap(std, seven),
                             "b_candidate_fact_support": (sum(std.values()), sum(seven.values())),
                             "b_shared_unseen_support": (shared_count(std, unseen),
                                                          shared_count(seven, unseen))}
            p, a = pair["parent"], pair["alternate"]
            if a["standard_tier"] != p["standard_tier"] - 1:
                raise ValueError("G51 G49 普通型跨层事实漂移")
            counts["windows"] += 1
            for field in ("a_overlap_and_pairs_only", "b_candidate_fact_support",
                          "b_shared_unseen_support"):
                pv, av = p[field], a[field]
                if None in (*pv, *av):
                    counts[field + "|unknown"] += 1
                    continue
                counts[field + "|first_higher"] += int(av[0] > pv[0])
                counts[field + "|first_equal"] += int(av[0] == pv[0])
                counts[field + "|first_lower"] += int(av[0] < pv[0])
                counts[field + "|second_higher"] += int(av[1] > pv[1])
                counts[field + "|second_equal"] += int(av[1] == pv[1])
                counts[field + "|second_lower"] += int(av[1] < pv[1])
                counts[field + "|both_nonworse"] += int(av[0] >= pv[0] and av[1] >= pv[1])
                counts[field + "|lex_prefer_alternate"] += int(av > pv)
            rows.append({"room_id": room["room_id"], "game_id": window[0],
                         "round_no": window[1], "trigger_seq": window[2],
                         "parent_action": parent, "alternate_action": alternate,
                         "parent": p, "alternate": a})
    if seen != set(target):
        raise ValueError(f"G51 漏读 G49 官方窗口：{len(set(target)-seen)}")
    output = {"schema": "g51-official-answer-static-screen/1", "outcome_blind": True,
              "g49_behavior_sha256": sha(G49),
              "answer_sha256": {name: sha(_project_file(_PROJECT_ROOT, G51 / f"{name}.answer.txt")) for name in answers},
              "script_sha256": sha(Path(__file__)),
              "counts": dict(sorted(counts.items())), "rows": rows,
              "boundary": "只在 G49 已知合法改选窗口核作者数值入口，不表示独立全策略行为、未来收益或证明收益方向。"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": output["counts"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
