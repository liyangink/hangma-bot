#!/usr/bin/env python3
"""G94：按房和单局去重核对强手宽进张窗口及实际后继。"""

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


HERE = Path(__file__).resolve().parent
SOURCES = {
    "g64": _project_file(_PROJECT_ROOT, HERE / "evidence/g64-strong-win-timing-20260928/result.json"),
    "g86": _project_file(_PROJECT_ROOT, HERE / "evidence/g86-post-claim-normal-draw-chain-20260928/result.json"),
    "g87": _project_file(_PROJECT_ROOT, HERE / "evidence/g87-post-claim-score-trace-20260928/result.json"),
    "g88": _project_file(_PROJECT_ROOT, HERE / "evidence/g88-post-claim-familiar-behavior-20260928/result.json"),
}
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g94-cumulative-free-reaudit-20260928/result.json')


def window_key(row: dict) -> tuple:
    """用强手、房、桌、单局、官方摸牌序号定位同一个真实弃牌窗口。"""
    return (row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"])


def hand_key(row: dict) -> tuple:
    """同一强手在同一官方单局的多次摸打只能算一个单局单位。"""
    return (row["peer"], row["room"], row["game_id"], row["round_no"])


def main() -> None:
    """复核冻结证据身份、逐窗连接、去重与实际路径；不估计备选动作收益。"""
    if OUT.exists():
        raise FileExistsError("G94 结果已存在，拒绝覆盖")
    source_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for name, path in SOURCES.items()}
    sources = {name: json.loads(path.read_text(encoding="utf-8"))
               for name, path in SOURCES.items()}
    expected = {"g64": "g64-strong-win-timing-result/1",
                "g86": "g86-post-claim-normal-draw-chain/1",
                "g87": "g87-post-claim-score-trace/1",
                "g88": "g88-post-claim-familiar-behavior/1"}
    for name, schema in expected.items():
        if sources[name]["schema"] != schema:
            raise ValueError(f"{name} 证据 schema 漂移")

    g87 = sources["g87"]["rows"]
    g86 = {window_key(row): row for row in sources["g86"]["rows"]}
    g88 = {window_key(row): row for row in sources["g88"]["rows"]
           if row["panel"] == "g61"}
    g64 = {hand_key(row): row for row in sources["g64"]["rows"]}
    if len(g87) != 1083 or len(g86) != 1083 or len(g88) != 1083:
        raise ValueError("G86/G87/G88 目标窗数不一致")
    if len({window_key(row) for row in g87}) != len(g87):
        raise ValueError("G87 目标窗重复")
    if {window_key(row) for row in g87} != set(g86) or set(g86) != set(g88):
        raise ValueError("三份逐窗证据键不一致")

    wide = [row for row in g87 if row["strong_ordinary_codes_delta"] > 0
            and row["strong_ordinary_capacity_delta"] > 0]
    first_by_hand = {}
    for row in sorted(wide, key=lambda item: item["draw_seq"]):
        first_by_hand.setdefault(hand_key(row), row)
    if not set(first_by_hand) <= set(g64):
        raise ValueError("宽面单局缺少 G64 官方结算")

    def summarize(rows: list[dict]) -> dict:
        """窗口级结果保留去重分母；实际结算另按单局汇总。"""
        component = defaultdict(Counter)
        next_status = Counter()
        for row in rows:
            delta = row["component_parent_minus_strong"]
            for part in ("base_score", "river_part", "risk_part", "style_part"):
                component[part]["parent_favoured"] += delta[part] > 0
                component[part]["strong_favoured"] += delta[part] < 0
                component[part]["sum"] += delta[part]
            next_status[g86[window_key(row)]["chain"]["next_status"]] += 1
        changed = [row for row in rows if
                   g88[window_key(row)]["candidate_action"] != row["parent_action"]]
        return {
            "windows": len(rows), "rooms": len({row["room"] for row in rows}),
            "distinct_hands": len({hand_key(row) for row in rows}),
            "white_0_windows": sum(row["white_before"] == 0 for row in rows),
            "claim_draw_bucket": dict(sorted(Counter(row["bucket"] for row in rows).items())),
            "codes_delta": dict(sorted(Counter(row["strong_ordinary_codes_delta"]
                                             for row in rows).items())),
            "capacity_delta": dict(sorted(Counter(row["strong_ordinary_capacity_delta"]
                                                for row in rows).items())),
            "component": {part: dict(counts) for part, counts in sorted(component.items())},
            "next_actual_status": dict(sorted(next_status.items())),
            "g88_changed_windows": len(changed),
            "g88_matched_strong_windows": sum(
                g88[window_key(row)]["candidate_action"] == row["strong_action"]
                for row in changed),
        }

    first_rows = list(first_by_hand.values())
    actual = {}
    for label, rows in [("all", first_rows)] + [
        (peer, [row for row in first_rows if row["peer"] == peer])
        for peer in ("xuanwu_2346", "tengshe_0638")
    ]:
        actors = [g64[hand_key(row)]["actors"][row["peer"]] for row in rows]
        actual[label] = {
            "hands": len(rows), "rooms": len({row["room"] for row in rows}),
            "win_hands": sum(actor["status"] == "win" for actor in actors),
            "score_sum": sum(actor["score"] for actor in actors),
            "white_0_hands": sum(row["white_before"] == 0 for row in rows),
        }

    result = {
        "schema": "g94-cumulative-free-reaudit/1", "exploratory": True,
        "sources_sha256": source_hashes,
        "wide_windows": summarize(wide),
        "wide_first_per_hand": summarize(first_rows),
        "wide_by_peer": {peer: summarize([row for row in wide if row["peer"] == peer])
                         for peer in ("xuanwu_2346", "tengshe_0638")},
        "actual_path_of_wide_first_per_hand": actual,
        "boundary": "强手实际弃牌后的后继和结算是观察值；未执行的父代弃牌没有官方反事实。"
                    "窗口同局相关，不能把窗口数当独立收益样本；G88 模仿率不是强度。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"wide_windows": result["wide_windows"]["windows"],
                      "distinct_hands": result["wide_windows"]["distinct_hands"],
                      "rooms": result["wide_windows"]["rooms"],
                      "actual": actual["all"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
