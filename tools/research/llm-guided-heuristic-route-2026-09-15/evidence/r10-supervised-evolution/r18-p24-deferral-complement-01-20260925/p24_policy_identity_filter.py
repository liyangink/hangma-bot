"""P24 池的策略身份过滤（主审新增硬纪律）。

3,920 局全量样本混着多个策略版本；「父代选了 hu」只有在**真正跑冻结 R18 v2** 的
run 上才等于「父代行为」。本脚本把 game_id 映射回产生它的 run 与
policy_release.candidate_source_sha256，只保留冻结父代 R18 v2，并重报池子大小。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

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
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
FROZEN_SOURCE_SHA = "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618"
USER_ID = "u_13495c3d79c8"


def run_index() -> dict[str, dict[str, str]]:
    """game_id -> {run_id, room, candidate_source_sha256, strategy}（按 games/ 文件名）。"""

    index: dict[str, dict[str, str]] = {}
    manifest_pattern = str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / "*" / "audit"
                           / "runs" / "*" / "manifest.json"))
    manifests = sorted(glob.glob(manifest_pattern))
    for manifest in manifests:
        run_dir = os.path.dirname(manifest)
        try:
            payload = json.loads(Path(manifest).read_text(encoding="utf-8")).get("payload") or {}
        except (ValueError, OSError):
            continue
        release = payload.get("policy_release") or {}
        record = {"run_id": os.path.basename(run_dir),
                  "room": run_dir.split("/audit/runs/")[0].rsplit("/", 1)[-1],
                  "candidate_source_sha256": str(release.get("candidate_source_sha256") or ""),
                  "strategy": str(release.get("strategy") or "")}
        games_dir = os.path.join(run_dir, "participants", USER_ID, "games")
        for path in glob.glob(os.path.join(games_dir, "*.jsonl")):
            index.setdefault(os.path.basename(path)[:-len(".jsonl")], record)
    print("审计 run manifest %d 份；索引到唯一牌局 %d 个" % (len(manifests), len(index)))
    return index


def main() -> int:
    census = json.loads((_project_file(_PROJECT_ROOT, HERE / "census.json")).read_text(encoding="utf-8"))["full"]
    index = run_index()
    rows = census["me_hu_rows"]
    v3 = [row for row in rows
          if str(row["chose"]) == "hu" and not row["broad"]
          and int(row["fan"]) == 1 and row["baotou"] is False]

    def attribute(items):
        out = collections.Counter()
        kept = []
        for row in items:
            record = index.get(row["game_id"])
            if record is None:
                out["unattributed"] += 1
                continue
            if record["candidate_source_sha256"] == FROZEN_SOURCE_SHA:
                out["frozen_r18_v2"] += 1
                kept.append(row)
            else:
                out["other_policy"] += 1
                out["other:" + (record["strategy"] or "unknown")] += 1
        return out, kept

    hu_counts, _hu_kept = attribute(rows)
    v3_counts, v3_kept = attribute(v3)
    kept_by_room = collections.Counter(index[row["game_id"]]["room"] for row in v3_kept)
    all_by_room = collections.Counter(
        (index[row["game_id"]]["room"] if row["game_id"] in index else "unattributed")
        for row in v3)
    payload = {
        "schema": "r18-p24-policy-identity-filter/1",
        "frozen_source_sha256": FROZEN_SOURCE_SHA,
        "run_index_games": len(index),
        "me_hu_windows_attribution": dict(sorted(hu_counts.items())),
        "v3_pool_windows_attribution": dict(sorted(v3_counts.items())),
        "v3_pool_windows": len(v3),
        "v3_pool_windows_frozen_r18_v2": len(v3_kept),
        "v3_pool_distinct_games_frozen_r18_v2": len({row["game_id"] for row in v3_kept}),
        "v3_pool_distinct_rounds_frozen_r18_v2": len({(row["game_id"], row["round_no"])
                                                      for row in v3_kept}),
        "v3_pool_by_room_all": dict(sorted(all_by_room.items())),
        "v3_pool_frozen_by_room": dict(sorted(kept_by_room.items())),
    }
    (_project_file(_PROJECT_ROOT, HERE / "census-policy-identity.json")).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + chr(10),
        encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
