#!/usr/bin/env python3
"""主审：策略类清单 vs 注册表——找出「已经写好但从没被评估过」的策略族。"""
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

import ast
import glob
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
POLICY = _project_file(_PROJECT_ROOT, ROOT / "src" / "hangma_bot" / "policy")
BOOTSTRAP = (_project_file(_PROJECT_ROOT, ROOT / "src" / "hangma_bot" / "bootstrap.py")).read_text(encoding="utf-8")


def main() -> int:
    rows = []
    for path in sorted(POLICY.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            methods = {
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if "choose" not in methods:
                continue
            registered = node.name in BOOTSTRAP
            rows.append((node.name, path.name, registered))
    print("| 策略类 | 文件 | 在 bootstrap 里出现 |")
    print("| --- | --- | --- |")
    for name, fname, reg in rows:
        print("| %s | %s | %s |" % (name, fname, "是" if reg else "**否**"))
    print()
    un = [r for r in rows if not r[2]]
    print("未被 bootstrap 引用的策略类：%d / %d" % (len(un), len(rows)))
    for name, fname, _ in un:
        print("  - %s (%s)" % (name, fname))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
