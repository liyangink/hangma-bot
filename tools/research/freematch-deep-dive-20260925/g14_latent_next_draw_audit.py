#!/usr/bin/env python3
"""核潜在自然两张连接在下一本人摸打后是否转成生产数学的自然进度。"""

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
import g11_longitudinal_route_audit as g11
import g13_two_draw_baotou_support as public
import g14_natural_second_discard_distribution as second


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-latent-natural-links-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-latent-next-draw-20260927')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """目标窗在看结果前已由旧即时向量全同固定；不读真实未来与结算。"""
    if OUT.exists():
        raise SystemExit("G14 潜在连接下一摸打结果已存在，拒绝覆盖")
    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or
            source["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")) or
            source["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("潜在连接结果或父代源码身份漂移")
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["tier"] != "same_exact_immediate_vectors":
                continue
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            if key in targets:
                raise ValueError("严格即时向量窗重复")
            targets[key] = row
    if len(targets) != source["counts"]["same_exact_immediate_vectors"]:
        raise ValueError("严格即时向量窗数量漂移")
    counts = Counter()
    scopes = defaultdict(set)
    rows = []
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码身份漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("目标窗重复或房间错配")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [], key=lambda x: x.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != target["parent_action"]
                    or accepted.get(context["decision_id"]) != target["parent_action"]
                    or target["alternative_action"] not in legal):
                raise ValueError("父代已接受或备选合法性漂移")
            parsed = g11._hand(raw["observation"])
            if parsed is None:
                raise ValueError("目标不再是正常摸打")
            full, _, melds = parsed
            discards, exposed = public._public_counts(raw["observation"])
            value = second._window(full, melds, target["parent_action"],
                                   target["alternative_action"], discards, exposed)
            cap = value["common_public_capacity_upper"]
            if cap == 0:
                counts["zero_common_capacity"] += 1
                continue
            weighted = value["weighted"]
            need_gain = weighted["natural_need_delta_weighted"]
            width_gain = weighted["natural_width_delta_weighted"]
            combined_cost = weighted["combined_shanten_delta_weighted"]
            seven_cost = weighted.get("seven_shanten_delta_weighted", 0)
            marker = ("need_better" if need_gain > 0 else
                      "need_worse" if need_gain < 0 else "need_equal")
            counts[marker] += 1
            counts["width_better" if width_gain > 0 else
                   "width_worse" if width_gain < 0 else "width_equal"] += 1
            counts["combined_any_worse"] += weighted["combined_worse_capacity"] > 0
            counts["seven_any_worse"] += weighted["seven_worse_capacity"] > 0
            if need_gain >= 0 and width_gain > 0 and combined_cost <= 0 and seven_cost <= 0:
                counts["conservative_shape_positive"] += 1
                scopes["conservative_shape_positive"].add(key[0])
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "alternative_action": target["alternative_action"],
                         "old_action": target["old_action"],
                         "latent_gain": (target["alternative_latent"]["capacity_upper"] -
                                         target["parent_latent"]["capacity_upper"]),
                         "score_gap": target["score_gap"], **value})
    if seen != set(targets) or len(rows) + counts["zero_common_capacity"] != len(targets):
        raise ValueError("严格即时向量入口未全量复原")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g14-latent-next-draw/1", "outcome_blind": True,
              "source_latent_result_sha256": _sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
              "source_latent_rows_sha256": _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
              "script_sha256": _sha(Path(__file__)), "rows_sha256": _sha(rows_path),
              "targets": len(targets), "rows": len(rows),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: len(ids) for name, ids in sorted(scopes.items())},
              "boundary": "第二弃牌理想化且没有他家合法响应；生产数学形状不是实际净分。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                                sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"targets": len(targets), "counts": result["counts"],
                      "scopes": result["scopes"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
