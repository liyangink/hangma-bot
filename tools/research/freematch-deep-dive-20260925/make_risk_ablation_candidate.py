#!/usr/bin/env python3
"""从 R18 v2 冻结源码机械生成唯一风险项零权候选。"""

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

from pathlib import Path

from hangma_bot.policy.action_value_executor import static_check
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-G1-RISK0.py')
OLD = "total -= round(6.0 * risk_units, 1)"
NEW = "total -= round(0.0 * risk_units, 1)"


def main() -> None:
    """验证仅一处语句变化、静态合同通过后写研究候选。"""
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if source.count(OLD) != 1:
        raise ValueError("风险扣分锚点必须恰好出现一次")
    candidate = source.replace(OLD, NEW, 1)
    before = source.splitlines()
    after = candidate.splitlines()
    different = [(a, b) for a, b in zip(before, after) if a != b]
    if len(before) != len(after) or different != [("                " + OLD, "                " + NEW)]:
        raise ValueError("候选超出一行零权消融")
    compile(candidate, str(OUT), "exec")
    static_check(candidate)
    if OUT.exists():
        raise FileExistsError("候选已经生成，拒绝覆盖")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(candidate, encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()
