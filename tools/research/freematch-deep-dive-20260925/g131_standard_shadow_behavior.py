#!/usr/bin/env python3
"""G131：只在 G128 开发根复核固定研究种子的合法改选与触发。"""

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
import c32_cards as c32
import g87_post_claim_score_trace as g87
import g95_wider_discard_same_hand_preflight as g95
import g126_all_draw_natural_width_exposure as g126
import g128_no_claim_two_shanten_branch as g128


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G131-STANDARD-SHADOW-CANDIDATE-PREREG-2026-09-28.md')
CANDIDATES = (
    "G131-STANDARD-SHADOW-LOW-V1.py",
    "G131-STANDARD-SHADOW-HIGH-V1.py",
)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g131-standard-shadow-behavior-20260928/result.json')


def sha(path: Path) -> str:
    """绑定候选、源窗口和行为脚本。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """重建开发父代表，核同窗评分身份、合法性与候选改选。"""
    if OUT.exists():
        raise FileExistsError("G131 行为证据已存在，拒绝覆盖")
    items = g128.selected("development")
    index = g128.target_index()
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in g126.plans(contract)}
    parent = c31.load_parent()
    scorers = {}
    for name in CANDIDATES:
        scorer, loaded = c32.load_scorer(name)
        if scorer is None or loaded != name:
            raise ValueError("G131 候选不能装配：" + name)
        scorers[name] = scorer
    rows = []
    counts = Counter()
    for item in items:
        key = tuple(item["window"])
        source, target = index[key]
        original = g95.CaptureWiderPolicy
        g95.CaptureWiderPolicy = g126.CaptureEveryHandAllDrawPolicy
        try:
            captured, _, _, _, _, _ = g95.run_full(
                plans[key[:3]], contract, versions, source["mix"])
        finally:
            g95.CaptureWiderPolicy = original
        record = captured.records.get(target["round_no"])
        if record is None or g126.scored_target(record, parent) != target:
            raise ValueError("G131 开发父代目标漂移")
        view = g87.g05.build_scoring_view(
            record.request, value_limits=c31.VALUE_LIMITS).candidate_view()
        before = parent(view)
        if before["status"] != "SCORED":
            raise ValueError("G131 父代评分失败")
        legal = {entry["action_key"] for entry in view["actions"]
                 if entry["is_legal"] is True}
        parent_scores = {entry["action_key"]: float(entry["score"])
                         for entry in before["entries"]}
        parent_key = g87.argmax(parent_scores)
        if parent_key != target["parent_action"] or set(parent_scores) != legal:
            raise ValueError("G131 父代动作或合法表漂移")
        actions = {}
        for name, scorer in scorers.items():
            after = scorer(view)
            if after["status"] != "SCORED":
                raise ValueError("G131 候选评分失败：" + name)
            scores = {entry["action_key"]: float(entry["score"])
                      for entry in after["entries"]}
            if set(scores) != legal:
                raise ValueError("G131 候选改变合法动作表：" + name)
            chosen = g87.argmax(scores)
            if chosen not in legal:
                raise ValueError("G131 候选动作非法：" + name)
            triggered = any((entry.get("trace") or {}).get("g131_standard_shadow", {})
                            .get("bonus", 0) > 0 for entry in after["entries"])
            actions[name] = {"chosen": chosen, "changed": chosen != parent_key,
                             "triggered": triggered,
                             "chosen_score_delta": scores[chosen] - parent_scores[chosen]}
            counts[name + "/" + source["mix"] + "/changed"] += chosen != parent_key
            counts[name + "/" + source["mix"] + "/triggered"] += triggered
        rows.append({"window": item["window"], "white_bin": item["white_bin"],
                     "observation_sha256": target["observation_sha256"],
                     "parent": parent_key, "actions": actions})
    if len(rows) != 38:
        raise ValueError("G131 开发行为窗口不完整")
    result = {
        "schema": "g131-standard-shadow-behavior/1",
        "input_sha256": {"script": sha(Path(__file__)), "prereg": sha(PREREG),
                         "selection": sha(g128.select.OUT),
                         "g126_rows": sha(g126.OUT / "rows.jsonl"),
                         **{name: sha(c32.CAND_DIR / name) for name in CANDIDATES}},
        "windows": len(rows), "counts": dict(sorted(counts.items())),
        "rows": rows,
        "boundary": "仅冻结父代表行动前合法行为；无备选收益或完整桌强度。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"windows": len(rows), "counts": result["counts"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
