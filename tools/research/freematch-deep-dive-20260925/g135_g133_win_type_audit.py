#!/usr/bin/env python3
"""G135：在 G134 对拍通过后按本人胡牌明细拆分已看 G131 开发根。"""

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

import hashlib
import json
from pathlib import Path

import g134_g133_hand_accounting_verify as verified


OUT = verified.NEW / "win_type_audit.json"
TYPES = ("plain", "plain_baotou", "seven_pairs_baotou",
         "seven_pairs_other", "other_special")


def classify(details: list[str]) -> str:
    """按结算明细给本人胡牌分互斥类；只用于赛后归因。"""
    if details == ["平胡"]:
        return "plain"
    if details[0] == "七对" or details[0].startswith("豪华七对×"):
        return "seven_pairs_baotou" if "爆头" in details else "seven_pairs_other"
    if details[0] == "平胡":
        return "plain_baotou" if "爆头" in details else "other_special"
    raise ValueError("G135 未知胡牌明细：" + repr(details))


def main() -> None:
    """独立重算已核验逐局的胡型收入，并守恒到 G134 收入分量。"""
    if OUT.exists():
        raise FileExistsError("G135 已存在，拒绝覆盖")
    audit_path = verified.OUT
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit["same_stage_table_score_execution"] is not True
            or audit["complete_tables"] != 384 or audit["complete_hands"] != 3072):
        raise ValueError("G135 必须先完成 G134 对拍")
    totals: dict[tuple[str, int, str, str], dict[str, int]] = {}
    for mix in ("H", "M"):
        for root in range(1, 9):
            for seat in range(4):
                for arm in verified.ARMS:
                    unit = (mix, root, seat, arm, 2026123101)
                    row = json.loads(verified.g14.paired.unit_path(
                        verified.NEW, unit).read_text(encoding="utf-8"))
                    for table in row["stage"]["tables"]:
                        focal_seat = table["hand_account"]["focal_seat"]
                        for hand in table["hand_records"]:
                            if hand["winner_seat"] != focal_seat:
                                continue
                            kind = classify(hand["details"])
                            key = (mix, root, arm, kind)
                            rec = totals.setdefault(key, {"wins": 0, "income": 0})
                            rec["wins"] += 1
                            rec["income"] += hand["score_delta"][focal_seat]
    root_rows = []
    for prior in audit["root_rows"]:
        mix, root, arm = prior["mix"], prior["root_index"], prior["arm"]
        delta = {}
        for kind in TYPES:
            new = totals.get((mix, root, arm, kind), {"wins": 0, "income": 0})
            old = totals.get((mix, root, "r18_v2", kind), {"wins": 0, "income": 0})
            delta[kind] = {name: (new[name] - old[name]) / 8
                           for name in ("wins", "income")}
        if (abs(delta["plain"]["income"]
                - prior["component_delta_per_table"]["plain_self_win_delta"]) > 1e-9
                or abs(sum(delta[k]["income"] for k in TYPES[1:])
                       - prior["component_delta_per_table"]["special_self_win_delta"]) > 1e-9):
            raise ValueError("G135 胡型拆分与 G134 不守恒："
                             + repr((mix, root, arm, delta,
                                     prior["component_delta_per_table"])))
        root_rows.append({"mix": mix, "root_index": root, "arm": arm,
                          "delta_per_table": delta})
    mean_by_mix = {}
    absolute_by_mix = {}
    for mix in ("H", "M"):
        mean_by_mix[mix] = {}
        absolute_by_mix[mix] = {}
        for arm in verified.ARMS:
            absolute_by_mix[mix][arm] = {
                kind: {name: sum(totals.get((mix, root, arm, kind),
                                            {"wins": 0, "income": 0})[name]
                                 for root in range(1, 9))
                       for name in ("wins", "income")}
                for kind in TYPES}
        for arm in verified.ARMS[1:]:
            rows = [r for r in root_rows if r["mix"] == mix and r["arm"] == arm]
            mean_by_mix[mix][arm] = {
                kind: {name: sum(r["delta_per_table"][kind][name] for r in rows) / 8
                       for name in ("wins", "income")}
                for kind in TYPES}
    output = {"schema": "g135-g133-win-type-audit/1",
              "inputs_sha256": {"g134_verification": hashlib.sha256(
                  audit_path.read_bytes()).hexdigest(),
                  "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "root_rows": root_rows, "mean_by_mix": mean_by_mix,
              "absolute_by_mix": absolute_by_mix,
              "boundary": "赛后已看开发根胡型拆分，不能推断动作时可知或独立确认。"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(mean_by_mix, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
