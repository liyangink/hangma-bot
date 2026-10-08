#!/usr/bin/env python3
"""G209：只读复核 G207 作者机制的字段存在性与同源触发上界。"""

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
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
SOURCES = {
    "answer": _project_file(_PROJECT_ROOT, EVIDENCE / "g207-glm-broad-route-author-20260929/answer.txt"),
    "call": _project_file(_PROJECT_ROOT, EVIDENCE / "g207-glm-broad-route-author-20260929/call.json"),
    "g61": _project_file(_PROJECT_ROOT, EVIDENCE / "g61-strong-draw-action-atlas-20260927/shape_profile.json"),
    "g87": _project_file(_PROJECT_ROOT, EVIDENCE / "g87-post-claim-score-trace-20260928/result.json"),
    "g94": _project_file(_PROJECT_ROOT, EVIDENCE / "g94-cumulative-free-reaudit-20260928/result.json"),
    "g208": _project_file(_PROJECT_ROOT, EVIDENCE / "g208-width-strata-20260929/result.json"),
}
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g209-glm-route-review-20260929/result.json')


def hand_key(row: dict) -> tuple:
    """同一强手本人在一张完整桌的一个官方单局。"""

    return (row["peer"], row["game_id"], row["round_no"])


def third_window_ceiling(rows: list[dict]) -> dict:
    """至少三个来源窗才可能在前两次放过后改一次；仍是宽松上界。"""

    count = Counter(hand_key(row) for row in rows)
    possible = [row for row in rows if count[hand_key(row)] >= 3]
    return {
        "windows": len(rows),
        "hands": len(count),
        "frequency_by_hand": dict(sorted(Counter(str(v) for v in count.values()).items())),
        "hands_with_three_or_more": sum(value >= 3 for value in count.values()),
        "rooms_with_three_or_more": len({row["room"] for row in possible}),
        "tables_with_three_or_more": len({row["game_id"] for row in possible}),
    }


def main() -> None:
    """不执行模型答卷，不把强手选择或条件触发当策略净收益。"""

    if OUT.exists():
        raise FileExistsError("G209 已冻结结果存在，拒绝覆盖")
    source_sha = {key: sha256(path.read_bytes()).hexdigest()
                  for key, path in SOURCES.items()}
    source = {key: json.loads(path.read_text(encoding="utf-8"))
              for key, path in SOURCES.items()}
    answer, call, g61, g87, g94, g208 = (
        source[key] for key in ("answer", "call", "g61", "g87", "g94", "g208")
    )
    if (answer.get("status") != "proposed"
            or call.get("valid_json_contract") is not True
            or call.get("answer_sha256") != source_sha["answer"]
            or g208["strata"]["g87_g94_scored_melded"]["windows"] != 349):
        raise ValueError("G207 原答或引用的 G208 分层证据漂移")
    wide = [row for row in g87["rows"]
            if row["strong_ordinary_codes_delta"] > 0
            and row["strong_ordinary_capacity_delta"] > 0]
    if len(wide) != g94["wide_windows"]["windows"] or len(wide) != 349:
        raise ValueError("G87/G94 同源强手宽面窗漂移")
    g61_by_key = {
        (row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"]): row
        for row in g61["strict_discard_rows"]
    }
    joined = [g61_by_key[(row["peer"], row["room"], row["game_id"],
                           row["round_no"], row["draw_seq"])] for row in wide]
    if any(row["own_meld_count"] == 0 for row in joined):
        raise ValueError("G94 源中出现门清窗口")
    if any(row["parent_fact"]["seven"] is not None
           or row["strong_fact"]["seven"] is not None for row in joined):
        raise ValueError("G94 七对事实不再全部不适用")

    # 只复现作者写出的 α 中位数口径；不检验缺失的 F，也不据此编码候选。
    ratios = []
    for row in wide:
        parts = row["component_parent_minus_strong"]
        base_gain = -parts["base_score"]
        lost_overlay = sum(parts[name]
                           for name in ("river_part", "risk_part", "style_part"))
        if base_gain <= 0:
            raise ValueError("G94 原基础牌效不再逐窗支持更宽动作")
        ratios.append((lost_overlay / base_gain, row))
    alpha = median(ratio for ratio, _ in ratios)
    pass_ratio = [row for ratio, row in ratios if ratio <= alpha]
    trace_keys = sorted({name for row in wide for name in row["parent_trace"]})
    missing_fan_keys = [name for name in ("fan_part", "seven_pairs_part",
                                          "family_progress_part")
                        if name not in trace_keys]
    result = {
        "schema": "g209-glm-route-review/1",
        "source_sha256": source_sha,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "author_status": answer["status"],
        "g94_scored_melded": {
            "windows": len(wide),
            "seven_not_applicable_both_arms": len(joined),
            "parent_score_trace_keys": trace_keys,
            "explicit_fan_or_seven_trace_keys_missing": missing_fan_keys,
        },
        "same_source_third_conflict_envelope": {
            "all_wider": third_window_ceiling(wide),
            "alpha_ratio_median_if_repaired_to_allow_seven_not_applicable": alpha,
            "ratio_pass": third_window_ceiling(pass_ratio),
        },
        "boundary": (
            "只对作者引用的 G94 历史强手动作同源上界计数；其他合法备选"
            "可能另有触发，故不是整套策略的全局覆盖上界。原方案 E1 七对"
            "None 未定义且原 trace 无可拆出的 fan/seven 项；即使替它宽松"
            "允许已副露的七对不适用、忽略 F/白板/确认/鸣牌重置等保护，"
            "同源 α 比率通过后第三次冲突机会仍稀少。任何窗口计数都不是"
            "候选积分或高番收益。"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"alpha": alpha, "all_ceiling": result[
        "same_source_third_conflict_envelope"]["all_wider"],
        "ratio_ceiling": result["same_source_third_conflict_envelope"]["ratio_pass"],
        "trace_keys": trace_keys}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
