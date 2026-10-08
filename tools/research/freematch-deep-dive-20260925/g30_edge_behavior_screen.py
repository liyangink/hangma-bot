#!/usr/bin/env python3
"""G30：在完整官方父代轨迹重判候选动作、合法性、覆盖与耗时。"""

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
import time

import g11_cross_family_action_atlas as atlas
import g17_one_draw_value_gap as g17
import g23_three_draw_teacher as g23
import g28_c01_simple_controls as controls
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.engine import _build_context
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer


HERE = Path(__file__).resolve().parent
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G30-EDGE-TIE-ONEWHITE-V1.py')
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
G23 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/selection.json')
G29 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g29-room-disjoint-edge-20260927/selection.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g30-edge-behavior-20260927/result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def _g10() -> dict[tuple[str, int, int], str]:
    source = json.loads(G10.read_text(encoding="utf-8"))
    if source.get("outcome_blind") is not True:
        raise ValueError("G10 旧行为来源不是结果盲")
    return {key(row): row["alternate_action"] for row in source["rows"]}


def _g11() -> dict[tuple[str, int, int], str]:
    source = json.loads(G11.read_text(encoding="utf-8"))
    if source.get("outcome_blind") is not True:
        raise ValueError("G11 旧行为来源不是结果盲")
    return {key(row): row["candidate_action"] for row in source["changed"]}


def main() -> None:
    """对所有已接受父代弃牌重跑同一候选；异常不静默跳过。"""

    if OUT.exists():
        raise SystemExit("G30 轨迹筛查已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909 or frozen.get("parent_source_sha256") != "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618":
        raise ValueError("完整桌或冻结父代源码身份漂移")
    g10 = _g10()
    g11 = _g11()
    g23_samples = {key(row) for row in json.loads(G23.read_text(encoding="utf-8"))["selected"]}
    g29_samples = {key(row) for row in json.loads(G29.read_text(encoding="utf-8"))["selected"]}
    scorer = ActionValueScorer("g30-edge-tie-onewhite-v1", CANDIDATE.read_text(encoding="utf-8"))
    counts = Counter()
    changed = []
    durations = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("房间父代源码身份漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if context.get("game_id") not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent:
                continue
            counts["accepted_parent_draw_discards"] += 1
            request = decision_request_from_json(raw)
            view = build_scoring_view(request)
            started = time.perf_counter()
            scored = scorer.score(view)
            durations.append((time.perf_counter() - started) * 1000)
            if scored.status != "SCORED" or not scored.entries:
                raise ValueError("G30 候选在父代已接受窗口未能完整评分")
            best = min(scored.entries, key=lambda item: (-item.score, item.action_key))
            if best.action_key == parent:
                continue
            window = context["game_id"], context["round_no"], context["trigger_seq"]
            legal = {item["action_key"]: item.get("facts") or {} for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if best.action_key not in legal or not best.action_key.startswith("discard:"):
                raise ValueError("G30 改选非法或非弃牌")
            pf, af = legal[parent], legal[best.action_key]
            if (not g23._eligible(pf) or not g23._eligible(af) or
                    any(g17._vector(pf, field) != g17._vector(af, field)
                        for field in ("standard_useful_tiles", "useful_tiles"))):
                raise ValueError("G30 改选不满足冻结牌效条件")
            obs = observation_from_json(raw["observation"])
            if sum(tile.code == "白" for tile in _build_context(obs).full_hand()) != 1:
                raise ValueError("G30 改选窗口并非持一白")
            score_rows = {item["action_key"]: item.get("total_score") for item in ranked}
            gap = score_rows[parent] - score_rows[best.action_key]
            if type(gap) not in (int, float) or not 0 <= gap <= 3:
                raise ValueError("G30 改选父代分差超界")
            if not controls.edge_key(best.action_key) < controls.edge_key(parent):
                raise ValueError("G30 改选不满足简约弃牌键")
            candidate_trace = next(item.trace for item in scored.entries if item.action_key == best.action_key)
            if candidate_trace.get("g30_edge_tie") != "one_white_v1":
                raise ValueError("G30 改选缺少候选追踪标识")
            counts["changed_windows"] += 1
            if window in g10:
                counts["g10_window_overlap"] += 1
                counts["g10_same_action"] += int(g10[window] == best.action_key)
            if window in g11:
                counts["g11_window_overlap"] += 1
                counts["g11_same_action"] += int(g11[window] == best.action_key)
            if window in g23_samples:
                counts["g23_sample_window_overlap"] += 1
            if window in g29_samples:
                counts["g29_sample_window_overlap"] += 1
            changed.append({"room_id": room["room_id"], "game_id": window[0],
                            "round_no": window[1], "trigger_seq": window[2],
                            "seat": obs.seat, "parent_action": parent,
                            "candidate_action": best.action_key, "parent_score_gap": gap,
                            "g10_same_action": window in g10 and g10[window] == best.action_key,
                            "g11_same_action": window in g11 and g11[window] == best.action_key})
    durations.sort()
    if not durations:
        raise ValueError("G30 没有可评分父代窗口")
    result = {"schema": "g30-edge-behavior/1", "outcome_blind": True,
              "frozen_rooms_sha256": sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "candidate_source_sha256": sha(CANDIDATE),
              "g10_source_sha256": sha(G10), "g11_source_sha256": sha(G11),
              "g23_selection_sha256": sha(G23), "g29_selection_sha256": sha(G29),
              "probe_script_sha256": sha(Path(__file__)),
              "complete_official_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "changed_complete_tables": len({row["game_id"] for row in changed}),
              "changed_rooms": len({row["room_id"] for row in changed}),
              "elapsed_ms_p50": round(durations[len(durations) // 2], 3),
              "elapsed_ms_p95": round(durations[int(len(durations) * .95)], 3),
              "elapsed_ms_p99": round(durations[int(len(durations) * .99)], 3),
              "elapsed_ms_max": round(durations[-1], 3),
              "changed": changed,
              "boundary": "结果盲父代轨迹重判，不包含候选改选后的后续场次或净分。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "changed"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
