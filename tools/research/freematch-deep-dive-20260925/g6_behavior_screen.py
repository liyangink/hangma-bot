#!/usr/bin/env python3
"""对冻结 R18 v2 的真实审计视图运行 G6 源码，结果盲核对行为接缝。"""

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
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path[:0] = [str(HERE), str(_project_file(_PROJECT_ROOT, ROOT / ".team-work/p6-baotou-route"))]

import natural_shape_loss_screen as screen  # noqa: E402
import p6_lib  # noqa: E402

SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G6-TIE-ROUTE-PARETO-V1.py')


def _scorer(source: str):
    namespace = {"__name__": "frozen"}
    exec(compile(source, "<read-only-research-source>", "exec"), namespace)
    return namespace["score_actions"]


def _first(plan):
    entries = plan.get("entries") or []
    return min(entries, key=lambda item: (-float(item["score"]), item["action_key"])) if entries else None


def main() -> int:
    parent = _scorer(p6_lib.frozen_source())
    candidate = _scorer(SOURCE.read_text(encoding="utf-8"))
    seen = set()
    counts = Counter()
    by_room = defaultdict(Counter)
    by_game = defaultdict(Counter)
    examples = []
    for room in screen.ROOMS:
        audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / room / "audit/runs")
        for run in sorted(audit.glob("*")):
            manifest = run / "manifest.json"
            if not manifest.is_file():
                continue
            meta = (json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
            if (meta.get("policy_release") or {}).get("candidate_source_sha256") != screen.PARENT_SHA256:
                continue
            for context, request, planned in screen._iter_decisions(run):
                key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
                if key in seen:
                    counts["duplicate"] += 1
                    continue
                seen.add(key)
                counts["windows"] += 1
                view = p6_lib.build_view(request)
                try:
                    parent_plan = parent(view)
                    candidate_plan = candidate(view)
                    a = _first(parent_plan)
                    b = _first(candidate_plan)
                except Exception:
                    counts["score_error"] += 1
                    continue
                if a is None or b is None or parent_plan.get("status") != "SCORED" or candidate_plan.get("status") != "SCORED":
                    counts["abstain"] += 1
                    continue
                actual = (planned.get("candidates") or [{}])[0].get("action_key")
                if actual != a["action_key"]:
                    counts["parent_replay_mismatch"] += 1
                    continue
                counts["parent_verified"] += 1
                if b["action_key"] == a["action_key"]:
                    continue
                counts["changed"] += 1
                by_room[room]["changed"] += 1
                by_game[key[0]]["changed"] += 1
                if (request.get("observation") or {}).get("phase") != "draw":
                    counts["non_draw_change"] += 1
                if not a["action_key"].startswith("discard:") or not b["action_key"].startswith("discard:"):
                    counts["non_discard_change"] += 1
                candidates = {c.get("action_key"): c for c in (request.get("rules") or {}).get("legal_candidates") or []}
                a_facts = (candidates.get(a["action_key"]) or {}).get("facts") or {}
                b_facts = (candidates.get(b["action_key"]) or {}).get("facts") or {}
                for field in ("shanten_after", "standard_shanten_after", "seven_pairs_shanten_after"):
                    if b_facts.get(field) is None or a_facts.get(field) is None or b_facts[field] > a_facts[field]:
                        counts["worse_" + field] += 1
                if len(examples) < 8:
                    examples.append((room, key, a["action_key"], b["action_key"], a["score"], b["score"]))
    output = {"counts": dict(counts),
              "rooms": {name: dict(value) for name, value in by_room.items()},
              "affected_official_games": len(by_game), "examples": examples}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not any(counts[name] for name in (
        "score_error", "non_draw_change", "non_discard_change",
        "worse_shanten_after", "worse_standard_shanten_after", "worse_seven_pairs_shanten_after"
    )) else 1


if __name__ == "__main__":
    raise SystemExit(main())
