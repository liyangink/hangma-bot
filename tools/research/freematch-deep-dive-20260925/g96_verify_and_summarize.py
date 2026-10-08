#!/usr/bin/env python3
"""G96 独立核验：配对身份、最小结算、动作和分层方向。"""

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

from g95_verify_and_summarize import classify, validate_hand


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/verification.json')


def sha(path: Path) -> str:
    """对冻结方案与执行器做字节身份对账。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stratum(row: dict) -> str:
    """事前声明的向听/白板分层；H/M 在外层保留。"""
    shanten = row["visible_action_facts"][row["parent_action"]]["standard_shanten_after"]
    return ("near" if shanten <= 1 else "far") + "/white_" + (
        "1plus" if row["white_before"] > 0 else "0")


def main() -> None:
    """按桌和窗口核验，不把八个世界误当独立自然桌。"""
    if OUT.exists():
        raise FileExistsError("G96 核验已存在，拒绝覆盖")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data["schema"] != "g96-wider-discard-branch-expansion/1":
        raise ValueError("G96 schema 错误")
    if data["panel_seed"] != 2026111001 or data["sample_keys"] != [
            f"g96-{index:02d}" for index in range(1, 9)]:
        raise ValueError("G96 根或样本键漂移")
    inputs = {
        "prereg": _project_file(_PROJECT_ROOT, HERE / "G96-WIDER-DISCARD-BRANCH-EXPANSION-PREREG-2026-09-28.md"),
        "script": _project_file(_PROJECT_ROOT, HERE / "g96_wider_discard_branch_expansion.py"),
        "g95_script": _project_file(_PROJECT_ROOT, HERE / "g95_wider_discard_same_hand_preflight.py"),
        "g93_script": _project_file(_PROJECT_ROOT, HERE / "g93_same_hand_branch_preflight.py"),
    }
    for name, path in inputs.items():
        if data["input_sha256"][name] != sha(path):
            raise ValueError("G96 输入摘要漂移：" + name)
    expected = {(mix, root, seat) for mix in ("H", "M")
                for root in range(1, 5) for seat in range(4)}
    rows = data["rows"]
    if len(rows) != 32 or {(r["mix"], r["root_index"], r["focal_seat"])
                           for r in rows} != expected:
        raise ValueError("G96 32 张表身份缺漏/重复")

    windows = []
    transitions = Counter()
    for row in rows:
        if row["status"] == "no_window":
            if "world_pairs" in row:
                raise ValueError("G96 未命中桌有分支")
            continue
        if row["status"] != "paired":
            raise ValueError("G96 未知桌状态")
        target = row["target_window"]
        focal = row["focal_seat"]
        if target["seat"] != focal:
            raise ValueError("G96 目标座位身份漂移")
        parent, alternate = row["parent_action"], row["alternate_action"]
        facts = row["visible_action_facts"]
        if (set(facts) != {parent, alternate}
                or parent == "discard:白" or alternate == "discard:白"
                or facts[parent]["standard_shanten_after"] !=
                facts[alternate]["standard_shanten_after"]
                or facts[alternate]["ordinary_codes"] <= facts[parent]["ordinary_codes"]
                or facts[alternate]["public_unseen_capacity"] <=
                facts[parent]["public_unseen_capacity"]):
            raise ValueError("G96 动作对不符合预登记的双严格宽面")
        pairs = row["world_pairs"]
        if len(pairs) != 9 or [pair["sample_key"] for pair in pairs] != [
                "historical", *data["sample_keys"]]:
            raise ValueError("G96 九个配对世界缺失/乱序")
        values = []
        for pair in pairs:
            p, a = pair["parent"], pair["alternate"]
            if (p["first_decision_action"] != parent
                    or a["first_decision_action"] != alternate
                    or p["forced_once"] != 0 or a["forced_once"] != 1):
                raise ValueError("G96 分支动作身份或一次干预失败")
            for arm in (p, a):
                hand = arm["settlement"]
                validate_hand(hand)
                if hand["round_no"] != target["round_no"]:
                    raise ValueError("G96 结算局号错位")
                if any(arm["runtime_counts"].get(key, 0) for key in
                       ("fallbacks", "illegal_choices", "timeouts")):
                    raise ValueError("G96 分支发生降级/非法/超时")
            ph, ah = p["settlement"], a["settlement"]
            if ph["scores_before"] != ah["scores_before"]:
                raise ValueError("G96 两臂起始积分不同")
            value = ah["score_delta"][focal] - ph["score_delta"][focal]
            if value != pair["focal_delta_alt_minus_parent"]:
                raise ValueError("G96 本人结算差分错误")
            if (classify(ph, focal) != pair["parent_class"]
                    or classify(ah, focal) != pair["alternate_class"]):
                raise ValueError("G96 结算类别错误")
            if pair["sample_key"] != "historical":
                transitions[(pair["parent_class"], pair["alternate_class"])] += 1
            values.append(value)
        signs = Counter("positive" if value > 0 else "negative" if value < 0 else "zero"
                        for value in values[1:])
        windows.append({
            "mix": row["mix"], "root_index": row["root_index"],
            "focal_seat": focal, "table_id": row["table_id"],
            "stratum": stratum(row),
            "shanten": facts[parent]["standard_shanten_after"],
            "white_before": row["white_before"],
            "historical_delta": values[0],
            "resampled_signs": dict(signs),
            "resampled_delta_sum": sum(values[1:]),
            "both_signs": signs["positive"] > 0 and signs["negative"] > 0,
        })
    by_stratum = defaultdict(list)
    for row in windows:
        by_stratum[(row["mix"], row["stratum"])].append(row)
    summary = {}
    for (mix, name), subset in sorted(by_stratum.items()):
        counts = sum((Counter(row["resampled_signs"]) for row in subset), Counter())
        summary[mix + "/" + name] = {
            "windows": len(subset),
            "roots": len({row["root_index"] for row in subset}),
            "positive_zero_negative": [counts["positive"], counts["zero"], counts["negative"]],
            "both_signs_windows": sum(row["both_signs"] for row in subset),
            "status": "OBSERVED" if len(subset) >= 5 else "INSUFFICIENT",
        }
    result = {
        "schema": "g96-verify-and-summarize/1", "source_sha256": sha(SOURCE),
        "tables": len(rows), "paired_windows": len(windows),
        "no_window_tables": len(rows) - len(windows),
        "paired_worlds": sum(len(row["world_pairs"]) for row in rows
                             if row["status"] == "paired"),
        "historical_nonzero": sum(row["historical_delta"] != 0 for row in windows),
        "both_signs_window_count": sum(row["both_signs"] for row in windows),
        "resampled_sign_total": dict(sum((Counter(row["resampled_signs"])
                                          for row in windows), Counter())),
        "by_stratum": summary, "windows": windows,
        "resampled_class_transitions": {left + "->" + right: count
                                        for (left, right), count in sorted(transitions.items())},
        "boundary": "分层仅作探索，不对八个非后验隐藏样本做独立显著性或发布收益推断。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("paired_windows", "paired_worlds", "both_signs_window_count",
                       "resampled_sign_total", "by_stratum")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
