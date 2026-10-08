#!/usr/bin/env python3
"""G41：对已复跑的首处分歧作生产数学三摸诊断。"""

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

import hashlib
import json
from pathlib import Path

import g7_three_self_draw_probe as g7
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g41-first-divergence-20260927')
SOURCES = (_project_file(_PROJECT_ROOT, EVIDENCE / "H-r08-s23.json"), _project_file(_PROJECT_ROOT, EVIDENCE / "M-r03-s03.json"))
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g41-first-divergence-20260927/analysis.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """首处分歧已按旧结算挑选，只作案例诊断，不估计候选收益。"""
    if OUT.exists():
        raise FileExistsError("拒绝覆盖 G41 诊断")
    rows = []
    for source in SOURCES:
        data = json.loads(source.read_text(encoding="utf-8"))
        for table in data["tables"]:
            if table["first_divergence_index"] is None:
                continue
            base = table["baseline_first"]
            other = table["candidate_first"]
            if base["window"] != other["window"] or base["observation"] != other["observation"]:
                raise ValueError("首处分歧不是同一动作前玩家观察")
            observation = observation_from_json(base["observation"])
            unseen = count_unseen_tiles(observation)
            if any(type(value) is not int or value < 0 for value in unseen):
                raise ValueError("公开未见牌容量缺失")
            pool = tuple(unseen)
            hand = _build_context(observation).full_hand()
            melds = len(observation.melds[observation.seat])
            capacities = {}
            for name, choice in (("baseline", base), ("candidate", other)):
                key = choice["ranked"][0]["action_key"]
                if not key.startswith("discard:"):
                    raise ValueError("首处分歧不是弃牌")
                after = list(hand)
                after.remove(Tile(key.split(":", 1)[1]))
                counts = counts_from_tiles(tuple(after))
                capacities[name] = {str(depth): g7.favorable(counts, pool, melds, depth)
                                    for depth in (2, 3)}
            rows.append({
                "table_id": table["table_id"], "mix": data["mix"],
                "root": data["root"], "focal_seat": table["focal_seat"],
                "round_no": base["window"]["round_no"],
                "trigger_seq": base["window"]["trigger_seq"],
                "baseline_action": base["ranked"][0]["action_key"],
                "candidate_action": other["ranked"][0]["action_key"],
                "baseline_table_score": table["baseline_score"],
                "candidate_table_score": table["candidate_score"],
                "capacity": capacities,
                "two_draw_delta": capacities["candidate"]["2"] - capacities["baseline"]["2"],
                "three_draw_delta": capacities["candidate"]["3"] - capacities["baseline"]["3"],
                "unseen_pool": sum(pool),
                "three_draw_denominator": g7.falling(sum(pool), 3),
            })
    result = {"schema": "g41-first-divergence-analysis/1",
              "source_sha256": {path.name: sha(path) for path in SOURCES},
              "script_sha256": sha(Path(__file__)), "rows": rows,
              "boundary": "四张已看结算的开发桌事后案例，不能推断三摸指标与净分因果；第三摸允许最优中途弃白，不能推断留白。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"rows": [{key: row[key] for key in
                                 ("table_id", "two_draw_delta", "three_draw_delta")}
                                for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
