#!/usr/bin/env python3
"""C 方向：响应窗口"过牌等待"的对账——**并把证据落盘**。

为什么单独写：主仓的 scan_decisions.py 收集了 pass_upgrade_events 却**只写了 decline_events**，
576 个窗口的细节被丢弃，summary 里只剩一个计数。因此该方向此前无法被复核，也无法续做。
本脚本做同一口径的扫描，但把每个窗口的可见上下文写进 pass-wait-cases.jsonl.gz。

口径（与主仓一致）：phase 以 response 开头、返回计划 rank1 = pass、且 rank1 理由含
升级/等胡/爆头/飘语义。

只做对账，不判定"该不该过"——那需要反事实续打。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import collections
import glob
import gzip
import json
from pathlib import Path

ROOT = Path("/Users/liyang/Projects/Opensource/hangma-bot")
OUT = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
ME = "u_13495c3d79c8"
UPGRADE_MARKS = ("等胡", "升级", "爆头", "飘")


def wall_band(remaining):
    if not isinstance(remaining, int):
        return "?"
    if remaining < 40:
        return "0(24-39)"
    if remaining < 64:
        return "1(40-63)"
    return "2(>=64)"


def main():
    idx = json.loads((_project_file(_PROJECT_ROOT, ROOT / "datasets/derived/auto-match-rooms-20260910/INDEX.json")).read_text())
    rooms = [r for r in idx["rooms"] if r["hands"] > 0]
    cases = []
    total_windows = 0
    phase_counter = collections.Counter()
    for room in rooms:
        pattern = str(_project_file(_PROJECT_ROOT, ROOT / room["source_session"] /
                      "audit/runs/*/participants" / ME / "decisions.jsonl"))
        for dec_path in sorted(glob.glob(pattern)):
            with open(dec_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("kind") != "decision_planned":
                        continue
                    payload = rec.get("payload") or {}
                    total_windows += 1
                    plan = payload.get("returned_plan") or {}
                    cands = plan.get("candidates") or []
                    if not cands:
                        continue
                    top = cands[0] or {}
                    chosen = top.get("action_key") or "?"
                    window = payload.get("window") or {}
                    phase = window.get("phase") or "?"
                    if not phase.startswith("response") or chosen != "pass":
                        continue
                    reasons = " ".join(top.get("reasons") or [])
                    if not any(mark in reasons for mark in UPGRADE_MARKS):
                        continue
                    phase_counter[phase] += 1
                    obs = payload.get("observation_snapshot") or {}
                    rule_state = obs.get("rule_state") or {}
                    legal = [c.get("action", {}).get("kind") for c in (payload.get("candidates") or [])]
                    ctx = rec.get("context") or {}
                    cases.append(dict(
                        game_id=ctx.get("game_id"), round_no=ctx.get("round_no"),
                        room=room["room"], phase=phase,
                        remaining=obs.get("remaining_tile_count"),
                        wall_band=wall_band(obs.get("remaining_tile_count")),
                        baotou=rule_state.get("baotou"), chain_count=rule_state.get("chain_count"),
                        is_my_turn=obs.get("turn_seat") == obs.get("seat"),
                        legal_kinds=sorted(set(k for k in legal if k)),
                        alternative_count=len(cands) - 1,
                        reason=reasons[:160]))
    OUT.joinpath("pass-wait-cases.jsonl.gz").write_bytes(b"")
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "pass-wait-cases.jsonl.gz"), "wt", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + chr(10))
    claim_kinds = collections.Counter()
    for case in cases:
        for kind in case["legal_kinds"]:
            if kind in ("chi", "peng", "gang"):
                claim_kinds[kind] += 1
    summary = dict(schema="pass-wait/1", rooms=len(rooms), decision_windows=total_windows,
                   pass_wait_windows=len(cases),
                   share=len(cases) / total_windows if total_windows else None,
                   by_phase=dict(phase_counter),
                   by_wall_band=dict(collections.Counter(c["wall_band"] for c in cases)),
                   with_claim_available=dict(claim_kinds),
                   only_pass_legal=sum(1 for c in cases if c["legal_kinds"] == ["pass"]),
                   baotou_true=sum(1 for c in cases if c["baotou"] is True))
    (_project_file(_PROJECT_ROOT, OUT / "pass-wait-summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
