#!/usr/bin/env python3
"""G127：只读 G126 行动前目标窗，按规则阶段与白板核支持集。"""

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

import g126_all_draw_natural_width_exposure as g126


SOURCE = g126.OUT / "rows.jsonl"
SUMMARY = g126.OUT / "result.json"
OUT = g126.OUT / "g127-support.json"


def sha(path: Path) -> str:
    """绑定行动前原件与审计程序。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shanten_bin(value: int) -> str:
    """将普通型向听 2 及以上合并，未知必须拒绝。"""
    if type(value) is not int or value < 0:
        raise ValueError("G127 普通型向听不是非负整数")
    return str(value) if value <= 1 else "2plus"


def white_bin(value: int) -> str:
    """当前实持白板 2 及以上合并，不按未来摸白分层。"""
    if type(value) is not int or not 0 <= value <= 4:
        raise ValueError("G127 当前白板数量非法")
    return str(value) if value <= 1 else "2plus"


def main() -> None:
    """检查每桌八单局、同一单局首窗唯一及宽面谓词。"""
    if OUT.exists():
        raise FileExistsError("G127 已有支持集审计，拒绝覆盖")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if summary["status"] != "complete" or len(rows) != 256:
        raise ValueError("G127 G126 整桌暴露未完成")
    groups = defaultdict(list)
    all_keys = set()
    for row in rows:
        if row["status"] != "complete" or row["hands"] != 8:
            raise ValueError("G127 父代表不是八单局完整桌")
        rounds = [target["round_no"] for target in row["target_windows"]]
        if len(rounds) != len(set(rounds)) or len(rounds) > 8:
            raise ValueError("G127 同一单局多次选窗")
        for target in row["target_windows"]:
            facts = target["score_facts"]
            if (facts["ordinary_codes_delta"] <= 0
                    or facts["public_unseen_capacity_delta"] <= 0
                    or facts["parent_score_gap"] < 0
                    or target["parent_action"] == target["alternate_action"]
                    or not target["parent_action"].startswith("discard:")
                    or not target["alternate_action"].startswith("discard:")
                    or "discard:白" in (target["parent_action"], target["alternate_action"])):
                raise ValueError("G127 严格宽面或非白动作身份不成立")
            key = (row["mix"], row["root_index"], row["focal_seat"],
                   target["round_no"])
            if key in all_keys:
                raise ValueError("G127 目标窗口重复")
            all_keys.add(key)
            group = (row["mix"],
                     "0" if facts["own_chi_peng_count"] == 0 else "1plus",
                     shanten_bin(facts["standard_shanten_after"]),
                     white_bin(facts["white_before"]))
            groups[group].append((row, target))
    out_groups = {}
    for key, items in sorted(groups.items()):
        out_groups["/".join(key)] = {
            "windows": len(items),
            "roots": len({row["root_index"] for row, _ in items}),
            "tables": len({row["table_id"] for row, _ in items}),
            "mean_codes_delta": mean(target["score_facts"]["ordinary_codes_delta"]
                                     for _, target in items),
            "mean_capacity_delta": mean(target["score_facts"]["public_unseen_capacity_delta"]
                                        for _, target in items),
            "mean_parent_score_gap": mean(target["score_facts"]["parent_score_gap"]
                                          for _, target in items),
        }
    counts = Counter((row["mix"], "0" if target["score_facts"]["own_chi_peng_count"] == 0
                      else "1plus", shanten_bin(target["score_facts"]["standard_shanten_after"]))
                     for row in rows for target in row["target_windows"])
    result = {
        "schema": "g127-all-draw-width-support/1",
        "input_sha256": {"script": sha(Path(__file__)), "g126_rows": sha(SOURCE),
                         "g126_summary": sha(SUMMARY)},
        "tables": len(rows), "target_windows": len(all_keys),
        "by_mix_claim_shanten": {"/".join(key): value
                                 for key, value in sorted(counts.items())},
        "groups": out_groups,
        "boundary": "只含父代行动前合法事实和第一冲突；既非备选收益，也非独立窗口样本。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"tables": result["tables"],
                      "target_windows": result["target_windows"],
                      "by_mix_claim_shanten": result["by_mix_claim_shanten"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
