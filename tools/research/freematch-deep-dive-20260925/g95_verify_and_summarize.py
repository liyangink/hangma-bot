#!/usr/bin/env python3
"""独立复核 G95 机读分支结算，并以窗口为单位汇总方向。"""

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


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g95-wider-discard-same-hand-preflight-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g95-wider-discard-same-hand-preflight-20260928/verification.json')


def sha(path: Path) -> str:
    """用字节摘要检测已冻结结果或输入变动。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(hand: dict, focal_seat: int) -> str:
    """仅由已完成单局结算复判实际收入类别。"""
    if hand["is_draw"]:
        return "draw"
    if hand["winner_seat"] != focal_seat:
        return "other_win"
    return "plain_self_win" if hand["details"] == ["平胡"] else "special_self_win"


def validate_hand(hand: dict) -> None:
    """只允许最小结算投影，逐座位验算积分守恒。"""
    if set(hand) != {"coverage", "round_no", "dealer_seat", "scores_before",
                     "scores_after", "score_delta", "winner_seat", "is_draw",
                     "fan", "details"} or hand["coverage"] != "settlement_only":
        raise ValueError("G95 非最小单局结算或字段缺失")
    before, after, delta = (hand[name] for name in
                            ("scores_before", "scores_after", "score_delta"))
    if any(not isinstance(x, list) or len(x) != 4 or
           any(type(v) is not int for v in x) for x in (before, after, delta)):
        raise ValueError("G95 四座积分向量格式错误")
    if any(before[i] + delta[i] != after[i] for i in range(4)) or sum(delta) != 0:
        raise ValueError("G95 单局积分不守恒")


def main() -> None:
    """验证冻结面板与每条双分支，输出可复核的分层统计。"""
    if OUT.exists():
        raise FileExistsError("G95 独立核验已存在，拒绝覆盖")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data["schema"] != "g95-wider-discard-same-hand-preflight/1":
        raise ValueError("G95 证据 schema 漂移")
    if data["panel_seed"] != 2026110901 or data["sample_keys"] != [
            f"g95-{i:02d}" for i in range(1, 9)]:
        raise ValueError("G95 冻结根或样本键漂移")
    expected_inputs = {
        "prereg": _project_file(_PROJECT_ROOT, HERE / "G95-WIDER-DISCARD-SAME-HAND-PREFLIGHT-PREREG-2026-09-28.md"),
        "script": _project_file(_PROJECT_ROOT, HERE / "g95_wider_discard_same_hand_preflight.py"),
        "g93_script": _project_file(_PROJECT_ROOT, HERE / "g93_same_hand_branch_preflight.py"),
    }
    for name, path in expected_inputs.items():
        if data["input_sha256"][name] != sha(path):
            raise ValueError("G95 " + name + " 输入摘要漂移")
    if len(data["rows"]) != 8 or {
        (row["mix"], row["focal_seat"]) for row in data["rows"]
    } != {(mix, seat) for mix in ("H", "M") for seat in range(4)}:
        raise ValueError("G95 H/M 四座面板不完整或身份重复")

    windows = []
    pair_count = 0
    for row in data["rows"]:
        if row["status"] == "no_window":
            if "world_pairs" in row:
                raise ValueError("G95 未命中桌包含分支结果")
            continue
        if row["status"] != "paired":
            raise ValueError("G95 未知桌状态")
        target = row["target_window"]
        focal = row["focal_seat"]
        if target["seat"] != focal:
            raise ValueError("G95 目标座位身份不一致")
        facts = row["visible_action_facts"]
        parent, alternate = row["parent_action"], row["alternate_action"]
        if (set(facts) != {parent, alternate} or
                facts[parent]["standard_shanten_after"] !=
                facts[alternate]["standard_shanten_after"] or
                facts[alternate]["ordinary_codes"] <= facts[parent]["ordinary_codes"] or
                facts[alternate]["public_unseen_capacity"] <=
                facts[parent]["public_unseen_capacity"]):
            raise ValueError("G95 不是预登记的同向听双严格宽面动作对")
        pairs = row["world_pairs"]
        if len(pairs) != 9 or [item["sample_key"] for item in pairs] != [
                "historical", *data["sample_keys"]]:
            raise ValueError("G95 单窗口配对世界数或顺序错误")
        deltas = []
        for item in pairs:
            p, a = item["parent"], item["alternate"]
            if p["first_decision_action"] != parent or a["first_decision_action"] != alternate:
                raise ValueError("G95 首动作与冻结动作对不符")
            if p["forced_once"] != 0 or a["forced_once"] != 1:
                raise ValueError("G95 备选不是恰好一次干预")
            for arm in (p, a):
                validate_hand(arm["settlement"])
                if any(arm["runtime_counts"].get(key, 0) for key in
                       ("fallbacks", "illegal_choices", "timeouts")):
                    raise ValueError("G95 分支存在降级、非法或超时")
            ph, ah = p["settlement"], a["settlement"]
            if ph["round_no"] != target["round_no"] or ah["round_no"] != target["round_no"]:
                raise ValueError("G95 结算单局号与目标不符")
            if ph["scores_before"] != ah["scores_before"]:
                raise ValueError("G95 双分支单局起分不同")
            delta = ah["score_delta"][focal] - ph["score_delta"][focal]
            if delta != item["focal_delta_alt_minus_parent"]:
                raise ValueError("G95 本人差分错误")
            if classify(ph, focal) != item["parent_class"] or classify(ah, focal) != item["alternate_class"]:
                raise ValueError("G95 胡牌类别错误")
            deltas.append(delta)
            pair_count += 1
        resampled = deltas[1:]
        signs = Counter("positive" if value > 0 else "negative" if value < 0 else "zero"
                        for value in resampled)
        windows.append({"mix": row["mix"], "focal_seat": focal,
                        "table_id": row["table_id"],
                        "standard_shanten_after": facts[parent]["standard_shanten_after"],
                        "white_before": row["white_before"],
                        "historical_delta": deltas[0],
                        "resampled_sum": sum(resampled),
                        "resampled_signs": dict(signs),
                        "both_signs_observed": signs["positive"] > 0 and signs["negative"] > 0})
    result = {"schema": "g95-verify-and-summarize/1",
              "source_sha256": sha(SOURCE),
              "tables": len(data["rows"]), "paired_windows": len(windows),
              "no_window_tables": 8 - len(windows), "paired_worlds": pair_count,
              "historical_nonzero": sum(row["historical_delta"] != 0 for row in windows),
              "resampled_sign_total": dict(sum((Counter(row["resampled_signs"])
                                                for row in windows), Counter())),
              "both_signs_window_count": sum(row["both_signs_observed"] for row in windows),
              "windows": windows,
              "boundary": "每窗九世界相关；样本等权公开一致并非后验；此处不做显著性或完整桌收益推断。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("paired_windows", "paired_worlds", "historical_nonzero",
                       "resampled_sign_total", "both_signs_window_count")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
