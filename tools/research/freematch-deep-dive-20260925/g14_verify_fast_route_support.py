#!/usr/bin/env python3
"""对冻结 237 对手牌全量对拍剪枝枚举与朴素枚举存档。"""

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

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as hands
import g13_two_draw_baotou_support as public
import g14_natural_second_discard_distribution as second
from g14_route_support_loss_fast import route_support_fast


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-route-support-loss-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-route-support-loss-fast-20260927/verification.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """逐窗复原输入，核行动/房间/生产数学及路线数与 Q1 完全相同。"""
    if OUT.exists():
        raise SystemExit("剪枝枚举对拍已存在，拒绝覆盖")
    result = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (result["rows_sha256"] != sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")) or
            result["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("来源身份漂移")
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            key = (item["game_id"], item["round_no"], item["trigger_seq"])
            if key in targets:
                raise ValueError("目标窗口重复")
            targets[key] = item
    if len(targets) != result["targets"]:
        raise ValueError("目标数量漂移")
    seen = set()
    counts = Counter()
    started = time.monotonic()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("审计大小漂移")
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
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context["decision_id"]) != target["parent_action"]):
                raise ValueError("父代首选或官方接受漂移")
            parsed = hands._hand(raw["observation"])
            if parsed is None:
                raise ValueError("正常摸打缺失")
            full, _, melds = parsed
            discards, exposed = public._public_counts(raw["observation"])
            for arm in ("parent", "alternative"):
                action = target[arm + "_action"]
                after = hands._after_discard(full, action)
                if after is None:
                    raise ValueError("目标弃牌不在手牌")
                capacity = second._capacity(after, discards, exposed, action)
                fast = route_support_fast(after, melds, capacity)
                old = target[arm]
                for field in ("natural_need", "routes", "q1"):
                    if fast[field] != old[field]:
                        raise ValueError(f"{key} {arm} {field} 剪枝与朴素枚举不一致")
                counts["arms_equal"] += 1
                counts["fast_tested_states"] += fast["tested_states"]
                counts["brute_tested_multisets"] += old["tested_multisets"]
    if seen != set(targets) or counts["arms_equal"] != 2 * len(targets):
        raise ValueError("目标没有全量对拍")
    OUT.parent.mkdir(parents=True)
    data = {"schema": "g14-route-support-loss-fast-verification/1",
            "outcome_blind": True, "source_result_sha256": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
            "source_rows_sha256": sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
            "script_sha256": sha(Path(__file__)),
            "fast_script_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g14_route_support_loss_fast.py")),
            "counts": dict(sorted(counts.items())),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "boundary": "同输入全量等价对拍；耗时含 91 房审计扫描，不是单动作时限。"}
    OUT.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": data["counts"],
                      "elapsed_seconds": data["elapsed_seconds"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
