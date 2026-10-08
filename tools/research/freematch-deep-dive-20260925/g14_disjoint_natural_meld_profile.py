#!/usr/bin/env python3
"""结果盲审计：生产求解器对互不重叠自然面子的分段完工缺口。"""

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
import g11_longitudinal_route_audit as hands
import g14_latent_next_draw_audit as latent
from hangma_bot.hangma._standard import need as standard_need
from hangma_bot.hangma.internal_types import TILE_ORDER


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-disjoint-natural-meld-profile-20260927')
NATURAL = tuple(TILE_ORDER[:33])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile(after: Counter, exposed_melds: int) -> tuple[int, ...]:
    """全保留白板，求互不共用牌的 1..剩余面子数最少自然补牌数。

    此为局部自然面子进度，不计将、七对、牌墙或实际可达性；完整
    牌型补牌数是另一指标，不得将本向量冒充独立胜率。
    """
    counts = tuple(after[code] for code in NATURAL)
    if any(type(value) is not int or not 0 <= value <= 4 for value in counts):
        raise ValueError("自然手牌物理张数越界")
    left = 4 - exposed_melds
    if not 1 <= left <= 4:
        raise ValueError("剩余面子数越界")
    return tuple(standard_need(counts, 0, n, False) for n in range(1, left + 1))


def main() -> None:
    """只用冻结父代的观察、规则事实与 237 个既定严格层窗口，不读结果。"""
    if OUT.exists():
        raise SystemExit("互不重叠面子审计已存在，拒绝覆盖")
    source = latent.SOURCE
    source_result = json.loads((source / "result.json").read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (source_result.get("outcome_blind") is not True or
            source_result["rows_sha256"] != _sha(source / "rows.jsonl.gz") or
            source_result["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("父代或潜在连接来源身份漂移")
    targets = {}
    with gzip.open(source / "rows.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["tier"] == "same_exact_immediate_vectors":
                key = (row["game_id"], row["round_no"], row["trigger_seq"])
                if key in targets:
                    raise ValueError("目标窗重复")
                targets[key] = row
    if len(targets) != source_result["counts"]["same_exact_immediate_vectors"]:
        raise ValueError("严格目标窗数量漂移")
    counts = Counter()
    scopes = defaultdict(set)
    rows = []
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("父代审计字节数漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or room["room_id"] != target["room_id"]:
                raise ValueError("重复或房间错配")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != target["parent_action"]
                    or accepted.get(context["decision_id"]) != target["parent_action"]
                    or target["alternative_action"] not in legal):
                raise ValueError("父代首选、接受或备选合法性漂移")
            parsed = hands._hand(raw["observation"])
            if parsed is None:
                raise ValueError("正常摸打手牌缺失")
            full, _, melds = parsed
            parent = hands._after_discard(full, target["parent_action"])
            alternate = hands._after_discard(full, target["alternative_action"])
            if parent is None or alternate is None or parent["白"] != alternate["白"]:
                raise ValueError("目标弃牌或留白数漂移")
            p = _profile(parent, melds)
            a = _profile(alternate, melds)
            delta = tuple(pv - av for pv, av in zip(p, a, strict=True))
            direction = ("pareto_better" if any(value > 0 for value in delta) and
                         all(value >= 0 for value in delta) else
                         "pareto_worse" if any(value < 0 for value in delta) and
                         all(value <= 0 for value in delta) else
                         "identical" if all(value == 0 for value in delta) else "mixed")
            counts[direction] += 1
            scopes[direction].add(key[0])
            for i, value in enumerate(delta, 1):
                counts[f"{i}_meld_better" if value > 0 else
                       f"{i}_meld_worse" if value < 0 else
                       f"{i}_meld_equal"] += 1
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "alternative_action": target["alternative_action"],
                         "exposed_melds": melds, "white_after": parent["白"],
                         "score_gap": target["score_gap"],
                         "parent_natural_meld_need": p,
                         "alternate_natural_meld_need": a,
                         "parent_minus_alternate": delta, "direction": direction,
                         "old_action": target["old_action"]})
    if seen != set(targets) or len(rows) != len(targets):
        raise ValueError("严格目标窗口未全量复原")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g14-disjoint-natural-meld-profile/1",
              "outcome_blind": True,
              "source_latent_result_sha256": _sha(source / "result.json"),
              "source_latent_rows_sha256": _sha(source / "rows.jsonl.gz"),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "script_sha256": _sha(Path(__file__)),
              "rows_sha256": _sha(rows_path), "targets": len(targets),
              "counts": dict(sorted(counts.items())),
              "scopes": {key: len(ids) for key, ids in sorted(scopes.items())},
              "boundary": "精确不重叠自然面子局部缺口；不是完整胡牌、白板概率或桌分。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                                sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
