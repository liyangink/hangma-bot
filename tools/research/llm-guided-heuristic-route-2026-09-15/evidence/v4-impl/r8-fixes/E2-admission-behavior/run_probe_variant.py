"""等行为探针的「修复前 / 修复后」对照跑（隔离树，不改仓库）。

做法：把 tools/ 目录按**符号链接**铺进临时树，只把 tools/sitin_model_admission.py
换成指定版本（before = git HEAD 的冻结版；after = 当前工作树），然后把该临时树放到
sys.path 最前面再跑探针。这样两个版本各跑一次，唯一差别就是被判分的实现文件本身。

用法（从仓库根）：
    .venv/bin/python <本文件> --variant before|after --out <等行为探针 JSON> \
        [--probe-out <反作弊探针 JSON>]
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
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = _PROJECT_ROOT
BASE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
ADMISSION_REL = 'tools/offline/sitin/sitin_model_admission.py'


def _pre_fix_source() -> str:
    """修复前版本 = git HEAD 的冻结文件（当前工作树的改动尚未提交）。"""
    result = subprocess.run(
        ["git", "show", "HEAD:" + ADMISSION_REL], cwd=str(REPO),
        capture_output=True, text=True, check=True)
    return result.stdout


def _build_tree(variant: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="admission-variant-"))
    tree_base = root / "review" / "llm-guided-heuristic-route-2026-09-15"
    (tree_base / "tools").mkdir(parents=True)
    (root / "src").symlink_to(_project_file(_PROJECT_ROOT, REPO / "src"))
    (tree_base / "evidence").symlink_to(_project_file(_PROJECT_ROOT, BASE / "evidence"))
    for path in sorted(TOOLS.iterdir()):
        if path.name == "__pycache__" or not path.is_file():
            continue
        # **复制**而不是符号链接：工具模块用 Path(__file__).resolve() 推自己的目录，
        # 符号链接会让它解析回真实 tools/，进而导入错误的 admission（假绿）。
        shutil.copy2(path, tree_base / "tools" / path.name)
    target = tree_base / "tools" / "sitin_model_admission.py"
    target.unlink()
    if variant == "before":
        target.write_text(_pre_fix_source(), encoding="utf-8")
    else:
        target.write_text((_project_file(_PROJECT_ROOT, TOOLS / "sitin_model_admission.py")).read_text(
            encoding="utf-8"), encoding="utf-8")
    return tree_base / "tools"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", required=True, choices=("before", "after"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--probe-out", default=None)
    args = parser.parse_args(argv)

    tools_dir = _build_tree(args.variant)
    sys.path.insert(0, str(tools_dir))
    import sitin_model_admission as adm          # noqa: E402
    import sitin_model_admission_probes as probes  # noqa: E402

    equivalence = probes.run_equivalence_probe()
    Path(args.out).write_text(json.dumps(equivalence, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    rows = probes._run(probes.BASELINE_PROBES + probes.R3_PROBES)
    anticheat = {"all_caught": all(row["caught"] for row in rows),
                 "probes": len(rows),
                 "caught": sum(1 for row in rows if row["caught"])}
    if args.probe_out:
        Path(args.probe_out).write_text(
            json.dumps({"schema": "sitin-model-admission-probe-report/1",
                        "variant": args.variant,
                        "all_caught": anticheat["all_caught"],
                        "probes": rows}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    print(json.dumps({"variant": args.variant,
                      "admission_file": str(tools_dir / "sitin_model_admission.py"),
                      "contract_sha256": getattr(adm, "CAPABILITY_CONTRACT_SHA256", None),
                      "equivalence_ok": equivalence["ok"],
                      "failed_probes": equivalence["failed_probes"],
                      "anticheat": anticheat}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
