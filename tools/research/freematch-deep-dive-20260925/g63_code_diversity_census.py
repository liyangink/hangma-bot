#!/usr/bin/env python3
"""G63：强手进张牌码增加但公开容量不增的全部 56 窗条件两摸普查。"""

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

import c31_action_layer_gap as c31
import g62_strong_shared_horizon as g62
from g52_shared_horizon import evaluate_root
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g63-code-diversity-census-20260928')


def main() -> None:
    """全量锁定 56 窗，缺证据共同弃权，不打开动作后的官方成绩。"""

    if OUT.exists():
        raise SystemExit("G63 结果目录已存在，拒绝覆盖")
    profile_path, batch_path = _project_file(_PROJECT_ROOT, SOURCE / "shape_profile.json"), _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if (profile["outcome_labels_opened"] is not False or
            batch["outcome_labels_opened"] is not False or
            profile["batch_sha256"] != g62.sha(batch_path)):
        raise ValueError("G63 结果盲来源漂移")
    targets = {}
    by_peer = Counter()
    for row in profile["strict_discard_rows"]:
        d = row["delta"]
        if (d["ordinary_delta"] != 0 or d["combined_delta"] != 0 or
                d["ordinary_support_codes_delta_same_layer"] <= 0 or
                d["ordinary_support_capacity_delta_same_layer"] > 0):
            continue
        identity = g62.key(row)
        if identity in targets:
            raise ValueError("G63 同一窗口重复")
        targets[identity] = row
        by_peer[row["peer"]] += 1
    if by_peer != {"xuanwu_2346": 27, "tengshe_0638": 29}:
        raise ValueError(f"G63 预登记入口漂移：{dict(by_peer)}")
    manifest = {"schema": "g63-code-diversity-manifest/1",
                "outcome_labels_opened": False,
                "source_sha256": {"g61_batch": g62.sha(batch_path),
                                  "g61_shape": g62.sha(profile_path),
                                  "g52_tree": g62.sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py")),
                                  "g62_helpers": g62.sha(_project_file(_PROJECT_ROOT, HERE / "g62_strong_shared_horizon.py")),
                                  "g63_prereg": g62.sha(_project_file(_PROJECT_ROOT, HERE / "G63-CODE-DIVERSITY-CENSUS-PREREG-2026-09-28.md")),
                                  "g63_script": g62.sha(Path(__file__))},
                "target_keys": [list(identity) for identity in sorted(targets)]}
    found = set()
    rows = []
    counts = Counter()
    for unit, record in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if g62.sha(path) != record["windows_sha256"]:
            raise ValueError("G63 G61 逐窗证据摘要不符")
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            identity = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            target = targets.get(identity)
            if target is None:
                continue
            if identity in found or window["actual_action"] != target["strong_action"] or window["parent_top_action"] != target["parent_action"]:
                raise ValueError("G63 目标窗口动作漂移")
            found.add(identity)
            observation = observation_from_json(window["observation"])
            analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            legal = {candidate.action_key: candidate for candidate in analysis.legal_candidates}
            row = {"key": list(identity), "white_before": target["white_before"],
                   "parent_action": target["parent_action"],
                   "strong_action": target["strong_action"],
                   "parent_score_gap": target["parent_score_gap"],
                   "ordinary_capacity_delta": target["delta"]["ordinary_support_capacity_delta_same_layer"],
                   "ordinary_codes_delta": target["delta"]["ordinary_support_codes_delta_same_layer"],
                   "seven_delta": target["delta"]["seven_delta"]}
            try:
                pair = {}
                for label, action in (("parent", target["parent_action"]),
                                      ("strong", target["strong_action"])):
                    candidate = legal.get(action)
                    if candidate is None or candidate.value_facts is None:
                        raise ValueError("生产合法动作或分值事实缺失")
                    root = evaluate_root(observation, {
                        "action_key": action,
                        "value_facts": candidate_value_facts_to_json(candidate.value_facts),
                    }, c31.RULE_CONFIG)
                    pair[label] = g62.summarize(root)
                row["delta"] = g62.delta(pair["parent"], pair["strong"])
                row["pair"] = pair
                counts["complete_pairs"] += 1
            except (ValueError, FactsAnalysisError) as exc:
                row["unavailable"] = type(exc).__name__ + ": " + str(exc)[:200]
                counts["unavailable_pairs"] += 1
            rows.append(row)
    if found != set(targets) or len(rows) != 56:
        raise ValueError("G63 入口未全量对齐")
    body = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    result = {"schema": "g63-code-diversity-result/1",
              "manifest_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
              "outcome_labels_opened": False, "targets": len(targets),
              "counts": dict(sorted(counts.items())), "rows": rows,
              "boundary": "结果盲适应性探索；公开未见容量非墙中概率，两摸不模拟他家截尾。"}
    g62.write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    g62.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"targets": len(targets), "counts": result["counts"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
