#!/usr/bin/env python3
"""G195：固定奇偶重采样世界，审计竞争路线事件能否作为稳定教师。"""

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
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G195-COMPETING-ROUTE-TEACHER-RELIABILITY-PREREG-2026-09-29.md')
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928/rows.jsonl')
MANIFEST = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g195-competing-route-teacher-reliability-20260929/result.json')
EVENTS = ("ready", "highfan_entry", "plain_win", "special_win", "other_win", "draw")


def digest(path: Path) -> str:
    """返回文件原始字节摘要，绑定既有开发教师和本次计算。"""

    return sha256(path.read_bytes()).hexdigest()


def terminal(arm: dict, seat: int) -> str:
    """把生产结算映射为四种互斥本座终点；不把机会当成已胡。"""

    settled = arm["settlement"]
    if settled["is_draw"]:
        return "draw"
    if settled["winner_seat"] != seat:
        return "other_win"
    fan = settled["fan"]
    if type(fan) is not int or fan < 1:
        raise ValueError("本人胡番数无效")
    return "plain_win" if fan == 1 else "special_win"


def observations(arm: dict, seat: int) -> dict[str, int]:
    """从一条已结算路径只取事件是否到达，不读取隐藏世界身份。"""

    result = {event: 0 for event in EVENTS}
    result["ready"] = int(arm["first_ready_draw_index"] is not None)
    result["highfan_entry"] = int(arm["first_highfan_draw_index"] is not None)
    result[terminal(arm, seat)] = 1
    return result


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """窗口等权相关；任一半样本恒定时标为未知，不冒充零。"""

    if len(xs) != len(ys) or len(xs) < 2:
        return None
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    xx = sum((x - xbar) ** 2 for x in xs)
    yy = sum((y - ybar) ** 2 for y in ys)
    if xx == 0 or yy == 0:
        return None
    value = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / math.sqrt(xx * yy)
    if not math.isfinite(value):
        raise ValueError("相关非有限")
    return value


def summarize(rows: list[dict], event: str) -> dict:
    """按窗口而非相关世界计稳定性，保留零差与相反方向分母。"""

    half_a = [row["delta_counts"]["A"][event] / 16 for row in rows]
    half_b = [row["delta_counts"]["B"][event] / 16 for row in rows]
    both = [(a, b) for a, b in zip(half_a, half_b) if a != 0 and b != 0]
    agree = sum((a > 0) == (b > 0) for a, b in both)
    full = [row["delta_counts"]["full32"][event] for row in rows]
    return {
        "windows": len(rows),
        "A_nonzero": sum(x != 0 for x in half_a),
        "B_nonzero": sum(x != 0 for x in half_b),
        "both_nonzero": len(both),
        "both_sign_agree": agree,
        "sign_agreement": agree / len(both) if both else None,
        "pearson": pearson(half_a, half_b),
        "full32_positive": sum(x > 0 for x in full),
        "full32_zero": sum(x == 0 for x in full),
        "full32_negative": sum(x < 0 for x in full),
        "full32_sum_delta": sum(full),
    }


def main() -> None:
    """核对来源、固定半样本并只写一次结果；不打开机制锁定窗。"""

    if OUT.exists():
        raise FileExistsError("G195 结果已存在；拒绝覆盖")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (manifest.get("status") != "complete"
            or manifest.get("windows_completed") != 49
            or manifest.get("rows_sha256") != digest(SOURCE)):
        raise ValueError("G161 冻结开发来源漂移")
    source_rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(source_rows) != 49:
        raise ValueError("G161 开发窗数量漂移")
    seen_windows = set()
    output = []
    for row in source_rows:
        key = (row["mix"], row["root_index"], row["focal_seat"], row["round_no"])
        if key in seen_windows or row["mix"] not in ("H", "M"):
            raise ValueError("开发窗口身份重复或对手池未知")
        seen_windows.add(key)
        worlds = row["world_pairs"]
        expected = {"historical"} | {f"g161-{i:03d}" for i in range(1, 33)}
        if len(worlds) != 33 or {w["sample_key"] for w in worlds} != expected:
            raise ValueError("开发窗口相关世界来源不完整或重复")
        counts = {name: {event: Counter() for event in EVENTS}
                  for name in ("A", "B", "full32")}
        for world in worlds:
            if world["sample_key"] == "historical":
                continue
            sample_number = int(world["sample_key"].split("-")[1])
            half = "A" if sample_number % 2 else "B"
            parent, alternate = world["parent"], world["alternate"]
            if (parent["first_decision_action"] != row["parent_action"]
                    or alternate["first_decision_action"] != row["alternate_action"]
                    or parent["forced_once"] != 0 or alternate["forced_once"] != 1):
                raise ValueError("续打动作身份或单次强制次数漂移")
            for arm in (parent, alternate):
                settled = arm["settlement"]
                if (len(settled["score_delta"]) != 4
                        or sum(settled["score_delta"]) != 0
                        or arm["focal_score_delta"] != settled["score_delta"][row["focal_seat"]]):
                    raise ValueError("单局结算不守恒")
            if (alternate["focal_score_delta"] - parent["focal_score_delta"]
                    != world["focal_delta_alt_minus_parent"]):
                raise ValueError("双臂本座积分差不守恒")
            prior = observations(parent, row["focal_seat"])
            other = observations(alternate, row["focal_seat"])
            for event in EVENTS:
                difference = other[event] - prior[event]
                counts[half][event]["delta"] += difference
                counts["full32"][event]["delta"] += difference
        delta_counts = {name: {event: counts[name][event]["delta"] for event in EVENTS}
                        for name in counts}
        for event in EVENTS:
            if delta_counts["A"][event] + delta_counts["B"][event] != delta_counts["full32"][event]:
                raise ValueError("两半计数不守恒")
        output.append({"mix": row["mix"], "root_index": row["root_index"],
                       "focal_seat": row["focal_seat"], "round_no": row["round_no"],
                       "white_before": row["white_before"],
                       "observation_sha256": row["observation_sha256"],
                       "parent_action": row["parent_action"],
                       "alternate_action": row["alternate_action"],
                       "delta_counts": delta_counts})
    output.sort(key=lambda row: (row["mix"], row["root_index"], row["focal_seat"], row["round_no"]))
    summary = {mix: {event: summarize([row for row in output if row["mix"] == mix], event)
                     for event in EVENTS} for mix in ("H", "M")}
    highfan = [summary[mix]["highfan_entry"] for mix in ("H", "M")]
    teacher_pass = all((item["both_nonzero"] >= 8
                        and item["sign_agreement"] is not None
                        and item["sign_agreement"] >= 0.70
                        and item["pearson"] is not None
                        and item["pearson"] >= 0.30) for item in highfan)
    payload = {
        "schema": "g195-competing-route-teacher-reliability/1",
        "source_sha256": {"g161_manifest": digest(MANIFEST), "g161_rows": digest(SOURCE),
                          "plan": digest(PLAN), "script": digest(Path(__file__))},
        "historical_world_excluded_from_halves": True,
        "worlds_per_half": 16,
        "window_count": len(output),
        "summary": summary,
        "highfan_event_teacher_pass": teacher_pass,
        "rows": output,
        "boundary": "已看 G161 开发续打的标签可靠性审计；不触碰 G160 机制锁定窗，不构成线上行动前特征或净收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"highfan_event_teacher_pass": teacher_pass,
                      "summary": summary}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
