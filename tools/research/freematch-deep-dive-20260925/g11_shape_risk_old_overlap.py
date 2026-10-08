#!/usr/bin/env python3
"""在已冻结的 G11 改选窗上复算旧 G6/P21b 程序的相同改选。"""

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
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer


HERE = Path(__file__).resolve().parent
BEHAVIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G6 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G6-TIE-ROUTE-PARETO-V1.py')
P21B = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-C11-NEARTIE10.py')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-old-overlap-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _top(scorer: ActionValueScorer, view) -> str:
    result = scorer.score(view)
    if result.status != "SCORED" or not result.entries:
        raise ValueError("旧对照在父代已接受窗口未能评分")
    return min(result.entries, key=lambda item: (-item.score, item.action_key)).action_key


def main() -> None:
    """只用同一动作前合法视图识别行为重合；不读后续结算。"""

    if OUT.exists():
        raise SystemExit("G11 旧行为重合结果已存在，拒绝覆盖")
    behavior = json.loads(BEHAVIOR.read_text(encoding="utf-8"))
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if behavior["candidate_source_sha256"] != _sha(_project_file(_PROJECT_ROOT, HERE / "candidates/G11-SHAPE-RISK-PARETO-V1.py")):
        raise ValueError("G11 候选摘要漂移")
    targets = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
               for row in behavior["changed"]}
    g10_keys = {(row["game_id"], row["round_no"], row["trigger_seq"])
                for row in g10["rows"]}
    g6 = ActionValueScorer("g6-tie", G6.read_text(encoding="utf-8"))
    p21b = ActionValueScorer("p21b-neartie", P21B.read_text(encoding="utf-8"))
    counts = Counter()
    rows = []
    for room in frozen["rooms"]:
        base = atlas.source.ROOT / room["audit_dir"]
        for context, raw, _plan in atlas.source.screen._iter_decisions(base):
            key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            view = build_scoring_view(decision_request_from_json(raw))
            old_g6 = _top(g6, view)
            old_p21b = _top(p21b, view)
            g6_same = old_g6 == target["candidate_action"]
            p21b_same = old_p21b == target["candidate_action"]
            if g6_same:
                counts["g6_same_action"] += 1
            if p21b_same:
                counts["p21b_same_action"] += 1
            if key in g10_keys:
                counts["g10_surface_overlap"] += 1
            rows.append({"game_id": key[0], "round_no": key[1], "trigger_seq": key[2],
                         "g11_action": target["candidate_action"],
                         "g6_action": old_g6, "p21b_action": old_p21b,
                         "g10_surface_overlap": key in g10_keys})
    if len(rows) != len(targets):
        raise ValueError("旧行为复算未覆盖全部 G11 改选窗口")
    result = {"schema": "g11-shape-risk-old-overlap/1", "outcome_blind": True,
              "behavior_sha256": _sha(BEHAVIOR), "g10_screen_sha256": _sha(G10),
              "g6_source_sha256": _sha(G6), "p21b_source_sha256": _sha(P21B),
              "changed_windows": len(rows), "counts": dict(sorted(counts.items())),
              "rows": rows,
              "boundary": "旧程序在同一父代动作前视图上的行为重合，不复用其开发赛桌分作新候选收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
