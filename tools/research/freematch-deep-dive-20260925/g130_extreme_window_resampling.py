#!/usr/bin/env python3
"""G130：对已选极端窗扩大隐藏世界样本，核路线解释稳定性。"""

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
import os
from pathlib import Path
from statistics import mean

import g95_wider_discard_same_hand_preflight as g95
import g100_g96_visible_trajectory as g100
import g126_all_draw_natural_width_exposure as g126
import g128_no_claim_two_shanten_branch as g128


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G130-EXTREME-WINDOW-RESAMPLING-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g130-extreme-window-resampling-20260928')
KEY = ("M", 2, 2, 2)
SAMPLES = tuple("g130-" + str(i).zfill(3) for i in range(1, 129))


def sha(path: Path) -> str:
    """冻结代码、选样和父代表证据身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected() -> dict:
    """独立记录本批仅诊断的固定范围。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "selection": g128.select.OUT,
             "g128_development_rows": g128.BASE / "development/rows.jsonl",
             "g126_rows": g126.OUT / "rows.jsonl",
             "g100_script": Path(g100.__file__),
             "contract": g95.g93.paired.CONTRACT}
    return {"schema": "g130-extreme-window-resampling-manifest/1",
            "target": list(KEY), "sample_keys": list(SAMPLES),
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "已看负例的敏感性诊断；不是未见窗或完整桌确认。"}


def one_pair(sample_key: str, world, *, record, plan, contract, versions,
             runtime, rules, situation) -> dict:
    """同世界只改首个合法弃牌，保存必要结算与审计。"""
    parent = g100.run_branch(
        world=world, captured=record, plan=plan, contract=contract,
        versions=versions, runtime=runtime, rules=rules,
        situation=situation, mix="M", forced_key=None)
    alternate = g100.run_branch(
        world=world, captured=record, plan=plan, contract=contract,
        versions=versions, runtime=runtime, rules=rules,
        situation=situation, mix="M", forced_key=record.alternate_key)
    p, a = parent["settlement"], alternate["settlement"]
    if p["scores_before"] != a["scores_before"]:
        raise ValueError("G130 双臂起点积分不一致")
    return {"sample_key": sample_key,
            "focal_delta_alt_minus_parent":
                a["score_delta"][KEY[2]] - p["score_delta"][KEY[2]],
            "parent_class": g95.classify(p, KEY[2]),
            "alternate_class": g95.classify(a, KEY[2]),
            "parent_settlement": p, "alternate_settlement": a,
            "parent_runtime_counts": parent["runtime_counts"],
            "alternate_runtime_counts": alternate["runtime_counts"]}


def summary(rows: list[dict]) -> dict:
    """每 32 个预定键分段，避免只看累计均值掩盖异常。"""
    values = [row["focal_delta_alt_minus_parent"] for row in rows]
    chunks = []
    for start in range(0, 128, 32):
        part = values[start:start + 32]
        chunks.append({"first_key": SAMPLES[start],
                       "last_key": SAMPLES[min(start + 31, 127)],
                       "samples": len(part), "mean_delta": mean(part) if part else None})
    counts = Counter()
    for row in rows:
        counts["parent/" + row["parent_class"]] += 1
        counts["alternate/" + row["alternate_class"]] += 1
        counts["positive"] += row["focal_delta_alt_minus_parent"] > 0
        counts["negative"] += row["focal_delta_alt_minus_parent"] < 0
        counts["zero"] += row["focal_delta_alt_minus_parent"] == 0
    return {"schema": "g130-extreme-window-resampling-summary/1",
            "status": "complete" if len(rows) == 128 else "in_progress",
            "samples_completed": len(rows), "samples_planned": 128,
            "mean_delta": mean(values) if values else None,
            "chunks": chunks, "counts": dict(sorted(counts.items())),
            "boundary": "已看极端窗上的额外隐藏样本，不是独立动作窗或完整桌。"}


def main() -> None:
    """每世界落盘，可从固定 128 键的准确前缀继续。"""
    OUT.mkdir(parents=True, exist_ok=True)
    current = expected()
    manifest = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != current:
            raise ValueError("G130 冻结清单改变，拒绝混写")
    else:
        manifest.write_text(json.dumps(current, ensure_ascii=False,
                                       sort_keys=True, indent=2) + "\n", encoding="utf-8")
    selection = json.loads(g128.select.OUT.read_text(encoding="utf-8"))
    if sum(tuple(item["window"]) == KEY for item in selection["selected"]) != 1:
        raise ValueError("G130 目标不在唯一开发选样中")
    source, target = g128.target_index()[KEY]
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = g126.g87.c31.load_parent()
    plan = next(plan for mix, root, seat, plan in g126.plans(contract)
                if (mix, root, seat) == KEY[:3])
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = g126.CaptureEveryHandAllDrawPolicy
    try:
        captured, runtime, rules, situation, _hands, _ = g95.run_full(
            plan, contract, versions, "M")
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(KEY[3])
    if record is None or g126.scored_target(record, scorer) != target:
        raise ValueError("G130 目标观察或评分漂移")
    if (record.parent_key, record.alternate_key) != ("discard:4t", "discard:发"):
        raise ValueError("G130 父代或备选动作漂移")
    facts = {item.action_key: item.facts
             for item in record.request.rules.legal_candidates}
    p, a = facts[record.parent_key], facts[record.alternate_key]
    if (p.seven_pairs_shanten_after != a.seven_pairs_shanten_after
            or p.seven_pairs_useful_tiles is None or a.seven_pairs_useful_tiles is None
            or len(p.seven_pairs_useful_tiles) != len(a.seven_pairs_useful_tiles)
            or sum(t.remaining_estimate for t in p.seven_pairs_useful_tiles)
            != sum(t.remaining_estimate for t in a.seven_pairs_useful_tiles)):
        raise ValueError("G130 七对行动前宽度同值事实改变")
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > 128 or any(row["sample_key"] != key
                              for row, key in zip(rows, SAMPLES)):
        raise ValueError("G130 已有行非固定键前缀")
    with rows_path.open("a", encoding="utf-8") as stream:
        for key in SAMPLES[len(rows):]:
            world = runtime["engine"].resample_public_consistent_hidden_world(
                record.world, focal_seat=KEY[2], sample_key=key)
            if runtime["engine"].frame(world).decisions[0].observation != reference:
                raise ValueError("G130 重采样改变焦点依法可见观察")
            row = one_pair(key, world, record=record, plan=plan, contract=contract,
                           versions=versions, runtime=runtime, rules=rules,
                           situation=situation)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            if len(rows) % 16 == 0:
                print(json.dumps({"samples": len(rows),
                                  "mean_delta": mean(x["focal_delta_alt_minus_parent"]
                                                     for x in rows)},
                                 ensure_ascii=False), flush=True)
    result = summary(rows)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                                sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
