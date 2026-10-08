"""在隔离树里跑专属测试：--variant before = 修复前 admission，after = 当前工作树。

用法（从仓库根）：
    .venv/bin/python <本文件> --variant before|after --out <pytest 输出文件>
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r8-fixes/E2-admission-behavior'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import run_probe_variant as rpv  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", required=True, choices=("before", "after"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    tools_dir = rpv._build_tree(args.variant)
    target = tools_dir / "test_sitin_model_admission.py"
    proc = subprocess.run(
        [str(rpv.REPO / ".venv/bin/python"), "-m", "pytest", str(target),
         "-q", "-rA", "-p", "no:cacheprovider"],
        cwd=str(rpv.REPO), capture_output=True, text=True)
    Path(args.out).write_text(proc.stdout + proc.stderr, encoding="utf-8")
    keep = [line for line in proc.stdout.splitlines()
            if line.startswith(("FAILED", "ERROR")) or " passed" in line
            or " failed" in line]
    print("\n".join(keep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
