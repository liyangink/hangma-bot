#!/usr/bin/env python3
"""G208：强手宽进张发现集按本人副露/七对可用性做来源绑定审计。"""

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


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
SOURCES = {
    "g61": _project_file(_PROJECT_ROOT, EVIDENCE / "g61-strong-draw-action-atlas-20260927/shape_profile.json"),
    "g87": _project_file(_PROJECT_ROOT, EVIDENCE / "g87-post-claim-score-trace-20260928/result.json"),
    "g94": _project_file(_PROJECT_ROOT, EVIDENCE / "g94-cumulative-free-reaudit-20260928/result.json"),
}
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g208-width-strata-20260929/result.json')


def key(row: dict) -> tuple:
    """强手－房－完整桌－单局－官方摸牌事件共同键。"""

    return (row["peer"], row["room"], row["game_id"],
            row["round_no"], row["draw_seq"])


def counts(rows: list[dict]) -> dict:
    """窗口、单局和完整桌分别去重，不把摸打当独立桌赛。"""

    return {
        "windows": len(rows),
        "rooms": len({row["room"] for row in rows}),
        "tables": len({row["game_id"] for row in rows}),
        "hands": len({(row["game_id"], row["round_no"]) for row in rows}),
        "white_before": dict(sorted(Counter(str(row["white_before"])
                                           for row in rows).items())),
        "parent_ordinary_shanten": dict(sorted(Counter(
            str(row["parent_fact"]["ordinary"]) for row in rows).items())),
        "parent_seven_known": sum(row["parent_fact"]["seven"] is not None
                                  for row in rows),
        "strong_seven_known": sum(row["strong_fact"]["seven"] is not None
                                  for row in rows),
    }


def main() -> None:
    """只用已保存的同窗玩家可见规则事实，不读赛后动作效果。"""

    if OUT.exists():
        raise FileExistsError("G208 已冻结结果存在，拒绝覆盖")
    source_sha = {name: sha256(path.read_bytes()).hexdigest()
                  for name, path in SOURCES.items()}
    sources = {name: json.loads(path.read_text(encoding="utf-8"))
               for name, path in SOURCES.items()}
    g61 = sources["g61"]["strict_discard_rows"]
    g87 = sources["g87"]["rows"]
    g94 = sources["g94"]
    if len(g61) != 2726 or len(g87) != 1083:
        raise ValueError("G61/G87 冻结同窗来源规模漂移")
    if len({key(row) for row in g61}) != len(g61):
        raise ValueError("G61 同窗键重复")
    by_key = {key(row): row for row in g61}
    if len({key(row) for row in g87}) != len(g87):
        raise ValueError("G87 同窗键重复")
    if not set(map(key, g87)) <= by_key.keys():
        raise ValueError("G87 不是 G61 后副露子集")
    if any(by_key[key(row)]["own_meld_count"] == 0 for row in g87):
        raise ValueError("G87 混入门清窗口")

    wider = [row for row in g61
             if row["delta"]["ordinary_delta"] == 0
             and (row["delta"]["ordinary_support_codes_delta_same_layer"] or 0) > 0
             and (row["delta"]["ordinary_support_capacity_delta_same_layer"] or 0) > 0]
    closed = [row for row in wider if row["own_meld_count"] == 0]
    melded = [row for row in wider if row["own_meld_count"] > 0]
    g87_wide = [by_key[key(row)] for row in g87
                if row["strong_ordinary_codes_delta"] > 0
                and row["strong_ordinary_capacity_delta"] > 0]
    if (len(g87_wide) != g94["wide_windows"]["windows"]
            or len(g87_wide) != 349
            or not {key(row) for row in g87_wide} <= {key(row) for row in melded}):
        raise ValueError("G87/G94 宽面与 G61 后副露窗口不一致")

    strata = {
        "all_strict_wider": counts(wider),
        "concealed_hand": counts(closed),
        "melded_hand": counts(melded),
        "g87_g94_scored_melded": counts(g87_wide),
        "g61_melded_not_in_g87": counts(
            [row for row in melded if key(row) not in {key(x) for x in g87}]
        ),
    }
    strata["melded_by_meld_count"] = {
        str(n): counts([row for row in melded if row["own_meld_count"] == n])
        for n in sorted({row["own_meld_count"] for row in melded})
    }
    if (strata["all_strict_wider"]["windows"] != 860
            or strata["concealed_hand"]["windows"] != 507
            or strata["melded_hand"]["windows"] != 353
            or strata["g61_melded_not_in_g87"]["windows"] != 4
            or strata["g87_g94_scored_melded"]["parent_seven_known"] != 0):
        raise ValueError("冻结分层事实漂移")
    result = {
        "schema": "g208-width-strata-audit/1",
        "source_sha256": source_sha,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "strata": strata,
        "boundary": (
            "同一强手真实动作与冻结父代影子首选的行动前分层；强手动作不是"
            "收益标签。G87/G94 的 349 窗全部有本人副露，七对事实不适用；"
            "G61 另有门清宽面窗，不能把两类谓词或分母混用。公开未见容量"
            "不等于未来牌墙概率；不同桌数不能推为新候选触达率。"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {field: value[field]
                             for field in ("windows", "rooms", "tables", "hands",
                                           "parent_seven_known")}
                      for name, value in strata.items() if name != "melded_by_meld_count"},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
