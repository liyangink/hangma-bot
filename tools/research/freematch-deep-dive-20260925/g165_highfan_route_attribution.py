#!/usr/bin/env python3
"""G165：开发层赛后拆分七对系与普通型高番自摸收入。"""

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
from statistics import mean


HERE = Path(__file__).resolve().parent
G161 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928/rows.jsonl')
G164 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g164-first-response-score-conflict-20260928/rows.jsonl')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g165-highfan-route-attribution-20260928/result-v2.json')
ROUTES = ("seven_pairs_highfan", "ordinary_highfan")
RESPONSE = ("same", "changed")


def sha(path: Path) -> str:
    """以原始字节固定已看开发来源。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(arm: dict, arm_class: str, seat: int) -> tuple[str, float] | None:
    """只按实际终局明细分七对系与普通型高番，不猜测未成胡路线。"""
    if arm_class != "special_self_win":
        return None
    settlement = arm["settlement"]
    if (settlement["winner_seat"] != seat or settlement["is_draw"]
            or settlement["fan"] < 2):
        raise ValueError("G165 高番自摸分类与结算矛盾")
    # 官方结算以“七对”或“豪华七对×N”表示分支；后者不含独立“七对”元素。
    seven = any(detail == "七对" or detail.startswith("豪华七对×")
                for detail in settlement["details"])
    if not seven and "平胡" not in settlement["details"]:
        raise ValueError("G165 未知高番胡牌分支明细")
    route = "seven_pairs_highfan" if seven else "ordinary_highfan"
    amount = float(arm["focal_score_delta"])
    if amount != float(settlement["score_delta"][seat]):
        raise ValueError("G165 本座高番自摸收入不守恒")
    return route, amount


def load() -> list[dict]:
    """逐窗逐世界对齐 G161 结算与 G164 首响应。"""
    rows = [json.loads(line) for line in G161.read_text(
        encoding="utf-8").splitlines()]
    responses = [json.loads(line) for line in G164.read_text(
        encoding="utf-8").splitlines()]
    if len(rows) != len(responses) or len(rows) != 49:
        raise ValueError("G165 只分析 49 个完整开发窗口")
    result = []
    for row, response in zip(rows, responses):
        for name in ("mix", "root_index", "focal_seat", "round_no",
                     "white_before", "observation_sha256", "parent_action",
                     "alternate_action"):
            if row[name] != response[name]:
                raise ValueError("G165 G161/G164 窗口身份不一致")
        if len(row["world_pairs"]) != len(response["world_pairs"]) or len(
                row["world_pairs"]) != 33:
            raise ValueError("G165 相关世界数不守恒")
        parts = Counter()
        counts = Counter()
        for pair, response_pair in zip(row["world_pairs"],
                                       response["world_pairs"]):
            if (pair["sample_key"] != response_pair["sample_key"]
                    or pair["focal_delta_alt_minus_parent"] !=
                       response_pair["focal_delta_alt_minus_parent"]):
                raise ValueError("G165 G161/G164 世界或结算漂移")
            bucket = "same" if response_pair["same_response"] else "changed"
            for sign, arm_name in ((-1, "parent"), (1, "alternate")):
                found = classify(pair[arm_name], pair[arm_name + "_class"],
                                 row["focal_seat"])
                if found is None:
                    continue
                route, amount = found
                parts[(route, bucket)] += sign * amount / 33
                counts[(arm_name, route)] += 1
        result.append({"mix": row["mix"], "white_before": row["white_before"],
                       "root_index": row["root_index"],
                       "window_contribution": parts,
                       "terminal_counts": counts})
    return result


def summarize(rows: list[dict]) -> dict:
    """先按同窗 33 个相关世界求贡献，再对窗口等权；根不扩充样本数。"""
    values = {(route, bucket): [r["window_contribution"][(route, bucket)]
                                for r in rows]
              for route in ROUTES for bucket in RESPONSE}
    counts = Counter()
    for row in rows:
        counts.update(row["terminal_counts"])
    return {"windows": len(rows),
            "roots": len({r["root_index"] for r in rows}),
            "related_world_pairs": len(rows) * 33,
            "window_equal_income_contribution": {
                route: {bucket: mean(values[(route, bucket)]) if rows else None
                        for bucket in RESPONSE}
                for route in ROUTES},
            "terminal_counts": {arm + "/" + route: counts[(arm, route)]
                                for arm in ("parent", "alternate")
                                for route in ROUTES}}


def main() -> None:
    """保留赛后分型属性，不改 G164 事前分析口径。"""
    if OUT.exists():
        raise FileExistsError("G165 结果已有，拒绝覆盖")
    rows = load()
    groups = {mix: summarize([r for r in rows if r["mix"] == mix])
              for mix in ("H", "M")}
    for mix in ("H", "M"):
        for white in (0, 1):
            groups[f"{mix}/{white}"] = summarize([
                r for r in rows if r["mix"] == mix and r["white_before"] == white])
    data = {"schema": "g165-highfan-route-attribution/2",
            "input_sha256": {"g161": sha(G161), "g164": sha(G164),
                             "script": sha(Path(__file__))},
            "groups": groups,
            "boundary": "G161/G164 收益已看后的终局明细分型；不是行动前价值标签或独立候选验收。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    for key in ("H", "M", "M/1"):
        print(json.dumps({key: groups[key]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
