#!/usr/bin/env python3
"""G212：逐桌按真实本座换位复核旧宽面实验的末名计数与净分口径。"""

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
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PANELS = (
    ("G11", "g11-shape-risk-development-20260927", 384, "old"),
    ("G89", "g89-g88-hm-development-20260928", 384, "old"),
    ("G168", "g168-zero-white-development-20260928", 256, "old"),
    ("G171", "g171-pareto-width-development-20260928", 512, "old"),
    ("G193", "g193-early-shape-development-20260929", 512, "old"),
    ("G211", "g211-g210-hm-development-20260929", 384, "corrected"),
)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g212-seat-rotation-tail-audit-20260929/result.json')


def digest(path: Path) -> str:
    """绑定旧证据字节身份，原始分析不覆盖。"""
    return sha256(path.read_bytes()).hexdigest()


def normalized_tail(value: dict) -> dict:
    """兼容 G11 旧键 bottom_including_tie，其余字段保持原口径。"""
    return {
        arm: {
            "tables": row["tables"],
            "last_including_tie": row.get("last_including_tie", row.get("bottom_including_tie")),
            "strict_last": row["strict_last"],
        } for arm, row in value.items()
    }


def audit_panel(label: str, dirname: str, expected_stages: int,
                published_basis: str) -> dict:
    """核每张桌的本座身份、阶段分守恒及旧/正确末名读数。"""
    base = _project_file(_PROJECT_ROOT, HERE / "evidence" / dirname)
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    analysis = json.loads((base / "analysis.json").read_text(encoding="utf-8"))
    paths = sorted((base / "stages").glob("*.json"))
    if len(paths) != expected_stages:
        raise ValueError(label + " 阶段文件数不符")
    old: dict[str, Counter] = defaultdict(Counter)
    correct: dict[str, Counter] = defaultdict(Counter)
    stage_scores: dict[tuple, list[int]] = defaultdict(list)
    stage_rows: dict[tuple, dict] = {}
    shifted = 0
    corpus_hash = sha256()
    for path in paths:
        corpus_hash.update(path.name.encode("utf-8") + b"\0")
        raw = path.read_bytes()
        corpus_hash.update(raw + b"\0")
        row = json.loads(raw)
        arm, mix, root, stage_seat = (row["arm"], row["mix"], row["root_index"],
                                       row["focal_seat"])
        key = mix, root, stage_seat, arm
        if key in stage_rows or row["stage"]["status"] != "complete":
            raise ValueError(label + " 重复或未完成阶段")
        stage_rows[key] = row
        total = 0
        for table in row["stage"]["tables"]:
            scores = table["scores_by_seat"]
            identities = table["stage_situation"]["participant_ids_by_seat"]
            if (len(scores) != 4 or len(identities) != 4
                    or identities.count("focal") != 1):
                raise ValueError(label + " 逐桌本座身份不唯一")
            actual_seat = identities.index("focal")
            if "hand_account" in table:
                account = table["hand_account"]
                if (account["focal_seat"] != actual_seat
                        or account["focal_table_delta"] != scores[actual_seat]):
                    raise ValueError(label + " 本座逐局账与桌面不守恒")
            shifted += actual_seat != stage_seat
            total += scores[actual_seat]
            for target, seat in ((old, stage_seat), (correct, actual_seat)):
                target[arm]["tables"] += 1
                target[arm]["last_including_tie"] += scores[seat] == min(scores)
                target[arm]["strict_last"] += (
                    scores[seat] == min(scores) and scores.count(scores[seat]) == 1)
        if total != row["stage"]["focal_stage_score"]:
            raise ValueError(label + " 实际本座逐桌分与阶段分不守恒")
        stage_scores[(mix, root, arm)].append(total)
    arms = manifest["arms"]
    if set(old) != set(arms) or set(correct) != set(arms):
        raise ValueError(label + " 臂别身份不符")
    baseline, candidate = arms
    roots = sorted({root for mix, root, arm in stage_scores})
    mixes = sorted({mix for mix, root, arm in stage_scores})
    if mixes != ["H", "M"]:
        raise ValueError(label + " H/M 对手池不完整")
    delta = {}
    for mix in mixes:
        values = []
        for root in roots:
            a, b = stage_scores[(mix, root, baseline)], stage_scores[(mix, root, candidate)]
            if len(a) != 4 or len(b) != 4:
                raise ValueError(label + " 根内四座不完整")
            table_count = int(manifest["tables_per_stage"])
            values.append((sum(b) - sum(a)) / (4 * table_count))
            for seat in range(4):
                first = stage_rows[(mix, root, seat, baseline)]["stage"]["tables"]
                second = stage_rows[(mix, root, seat, candidate)]["stage"]["tables"]
                if [table["seed"] for table in first] != [table["seed"] for table in second]:
                    raise ValueError(label + " 成对牌山 seed 不符")
        delta[mix] = sum(values) / len(values)
    delta["combined"] = (delta["H"] + delta["M"]) / 2
    reported = analysis["means_delta_per_complete_table"]
    if any(abs(delta[k] - reported[k]) > 1e-9 for k in delta):
        raise ValueError(label + " 阶段净分与旧根级分析不一致")
    old_json = {arm: dict(old[arm]) for arm in arms}
    correct_json = {arm: dict(correct[arm]) for arm in arms}
    published = normalized_tail(analysis["last_place_counts"])
    expected = old_json if published_basis == "old" else correct_json
    if published != expected:
        raise ValueError(label + " 已发表末名统计与标注基准不符")
    return {
        "panel": label, "stages": len(paths),
        "tables": sum(v["tables"] for v in correct.values()),
        "shifted_table_seat_count": shifted,
        "legacy_stage_seat_tail": old_json,
        "correct_table_seat_tail": correct_json,
        "published_basis": published_basis,
        "net_delta_per_complete_table_independently_reconciled": delta,
        "sha256": {
            "manifest": digest(base / "manifest.json"),
            "result": digest(base / "result.json"),
            "analysis": digest(base / "analysis.json"),
            "stage_corpus": corpus_hash.hexdigest(),
        },
    }


def main() -> None:
    """写入不可覆盖的系统性更正证据；不修改历史逐桌或旧分析原件。"""
    if OUT.exists():
        raise FileExistsError("G212 更正证据已存在，拒绝覆盖")
    rows = [audit_panel(*spec) for spec in PANELS]
    output = {
        "schema": "g212-seat-rotation-tail-audit/1",
        "rows": rows, "script_sha256": digest(Path(__file__)),
        "boundary": "更正描述性末名口径；每阶段真实本座分及 H/M 根级净收益独立守恒，旧原件保留。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps([{k: row[k] for k in ("panel", "tables", "shifted_table_seat_count",
                                           "correct_table_seat_tail")}
                      for row in rows], ensure_ascii=False))


if __name__ == "__main__":
    main()
