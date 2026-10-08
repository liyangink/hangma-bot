#!/usr/bin/env python3
"""G143：将首次普通型爆头机会前的副露增长与已核官方吃碰响应逐局对齐。"""

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
import gzip
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
G138 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g138-official-plain-baotou-opportunity-20260928/result.json')
G76_ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/rows.jsonl.gz')
G76_RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g143-plain-baotou-claim-entry-20260928/result.json')


def sha(path: Path) -> str:
    """绑定不可变自由赛证据与当前分析代码字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """仅作已发生行动链归因范围审计，不以未来首次机会训练鸣牌收益。"""
    if OUT.exists():
        raise FileExistsError("G143 证据已经存在，拒绝覆盖")
    opportunity = json.loads(G138.read_text(encoding="utf-8"))
    atlas = json.loads(G76_RESULT.read_text(encoding="utf-8"))
    if (opportunity["normal_draw_discard_windows"] != 36080
            or len(opportunity["first_plain_baotou_rows"]) != 239
            or atlas["rows"] != 10366
            or atlas["source_sha256"]["rows_gzip"] != sha(G76_ROWS)):
        raise ValueError("G143 冻结母体或 G76 压缩逐阶段来源漂移")
    claims = defaultdict(list)
    with gzip.open(G76_ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["actual"] != "claim":
                continue
            key = (row["peer"], row["room"], row["game_id"],
                   row["round_no"], row["actor"])
            claims[key].append(row)
    counts = Counter()
    rooms = defaultdict(set)
    rows = []
    for record in opportunity["first_plain_baotou_rows"]:
        before = record["previous_normal_draw"]
        if before is None:
            continue
        increase = record["first_meld_count"] - before["meld_count"]
        if increase < 0:
            raise ValueError("G143 相邻本人正常摸打间副露组数减少")
        if increase == 0:
            continue
        key = (record["peer"], record["room"], record["game_id"],
               record["round_no"], record["actor"])
        matched = [claim for claim in claims[key]
                   if before["draw_seq"] < claim["discard_seq"] < record["first_draw_seq"]]
        if len(matched) != increase:
            raise ValueError("G143 副露增量与已核官方吃碰未逐一对账")
        group = record["peer"] + "/" + record["actor"]
        counts[group + "/entries"] += 1
        counts[group + "/claim_events"] += len(matched)
        rooms[group].add(record["room"])
        parent_pass = False
        for claim in matched:
            if claim["parent_key"] == "pass":
                category = "parent_pass"
                parent_pass = True
                counts[group + "/parent_pass_r6_exact"] += (
                    claim["r6_key"] == claim["accepted_key"])
                counts[group + "/parent_pass_r6_pass"] += claim["r6_key"] == "pass"
            elif claim["parent_key"] == claim["accepted_key"]:
                category = "parent_exact_claim"
            else:
                category = "parent_other_action"
            counts[group + "/" + category] += 1
        counts[group + "/entries_with_parent_pass"] += parent_pass
        if parent_pass:
            rooms[group + "/parent_pass"].add(record["room"])
        rows.append({"peer": record["peer"], "actor": record["actor"],
                     "room": record["room"], "game_id": record["game_id"],
                     "round_no": record["round_no"],
                     "previous_draw_seq": before["draw_seq"],
                     "first_entry_draw_seq": record["first_draw_seq"],
                     "white_before": before["white_before"],
                     "white_at_entry": record["first_white_before"],
                     "meld_increase": increase,
                     "claims": [{"discard_seq": claim["discard_seq"],
                                 "phase": claim["phase"],
                                 "accepted_key": claim["accepted_key"],
                                 "parent_key": claim["parent_key"],
                                 "r6_key": claim["r6_key"],
                                 "parent_margin": claim["parent_margin"],
                                 "pass_shanten": claim["pass_shanten"],
                                 "claim_shanten": claim["claim_shanten"],
                                 "pass_width": claim["pass_width"],
                                 "claim_width": claim["claim_width"]}
                                for claim in matched]})
    expected = {"xuanwu_2346/peer": (27, 34), "xuanwu_2346/us": (3, 3),
                "tengshe_0638/peer": (13, 13), "tengshe_0638/us": (11, 11)}
    for group, (entries, events) in expected.items():
        if (counts[group + "/entries"], counts[group + "/claim_events"]) != (entries, events):
            raise ValueError("G143 强手／我方吃碰数与首次机会分类账不守恒")
    result = {"schema": "g143-plain-baotou-claim-entry-join/1",
              "inputs_sha256": {"g138": sha(G138), "g76_rows": sha(G76_ROWS),
                                "g76_result": sha(G76_RESULT),
                                "script": sha(Path(__file__))},
              "counts": dict(sorted(counts.items())),
              "rooms_by_group": {key: len(value) for key, value in sorted(rooms.items())},
              "rows": sorted(rows, key=lambda row: (
                  row["peer"], row["room"], row["game_id"],
                  row["round_no"], row["actor"])),
              "boundary": "只按实际首次机会倒选已发生吃碰，父代对照是强手相同可见观察的动作；不能由此推出如果父代过牌，后续机会或整桌积分会怎样。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "rooms": result["rooms_by_group"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
