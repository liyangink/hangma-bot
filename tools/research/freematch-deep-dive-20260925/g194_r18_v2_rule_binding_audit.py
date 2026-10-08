#!/usr/bin/env python3
"""G194：旧冻结规则与当前规则的同源码 R18 v2 完整桌逐位对账。"""

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

from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g194-r18-v2-rule-binding-20260929')
OLD = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g194-r18-v2-rule-binding-20260929/pre-rulefacts.json')
CURRENT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g194-r18-v2-rule-binding-20260929/current-rulefacts.json')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g194-r18-v2-rule-binding-20260929/result.json')
PANEL_SEED = 20261229195


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def normalized(row: dict) -> dict:
    """仅去除旧发布包与研究包装必然不同的策略诊断身份。"""
    copy = json.loads(json.dumps(row))
    for table in copy["tables"]:
        policy_ids = table["execution"].pop("policy_ids_by_seat")
        if sum(("r18_integrated_positive_v2" in name
                or "r18-integrated-positive-v2" in name)
               for name in policy_ids) != 1:
            raise ValueError("每桌必须恰有一个 R18 v2 焦点座位")
    return copy


def main() -> None:
    """完整比较同牌山阶段分、逐局摘要与除策略名外的执行计数。"""
    if RESULT.exists():
        raise FileExistsError("G194 已生成结果，拒绝覆盖")
    old = json.loads(OLD.read_text(encoding="utf-8"))
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    expected = [
        [mix, root, seat, "r18_v2", PANEL_SEED]
        for mix in ("H", "M") for root in (1, 2) for seat in range(4)
    ]
    if (len(old) != 16 or len(current) != 16
            or [row["unit"] for row in old] != expected
            or [row["unit"] for row in current] != expected):
        raise ValueError("G194 阶段身份、牌山或双池四座覆盖不符")
    mismatches = []
    scored = 0
    for before, after in zip(old, current, strict=True):
        for row in (before, after):
            if len(row["tables"]) != 2:
                raise ValueError("G194 缺少完整桌")
        if normalized(before) != normalized(after):
            mismatches.append(before["unit"])
        scored += sum(table["execution"]["action_value_scored"]
                      for table in before["tables"])
    payload = {
        "schema": "g194-r18-v2-rule-binding-audit/1",
        "old_commit": "49e00d436",
        "current_commit_at_execution": "fbe1559fa",
        "rules_hash_before": "d8a6346c8303a891523952bff618989931beb62fa041a511805b807ee471a6ef",
        "rules_hash_after": "14e670edd631cb91a2c4c31d8131e360e9ebfb2d82d7c9ac9425f01d099e678d",
        "panel_seed": PANEL_SEED,
        "stage_pairs": len(old),
        "table_pairs": 32,
        "focus_scored_decisions_before": scored,
        "mismatched_stages_except_policy_id": mismatches,
        "input_sha256": {"before": digest(OLD), "after": digest(CURRENT),
                         "script": digest(Path(__file__))},
        "boundary": "仅 2 池×2 根×4 座的本地完整桌兼容性证据；不替代新绑定发布前的规则、时限、官方接线门。",
    }
    RESULT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
