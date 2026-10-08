"""R6 冻结回复重判分的**归因对照**：同一棵工作树下，只把 tools/sitin_model_admission.py
换成修复前（git HEAD）与修复后（当前工作树）各判一遍，逐任务对比 pass/violation。

目的：把「本包改动带来的成绩变化」与「并行工作包改动 src/policy 带来的变化」分开——
判分器身份（grader_sha256 / capability_contract_sha256 / view_schema_version）一并留证。

用法（从仓库根）：
    .venv/bin/python <本文件> --out-dir <本目录>
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
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import run_probe_variant as rpv  # noqa: E402

REPLIES = rpv.REPO / "review" / "llm-guided-heuristic-route-2026-09-15" / \
    "evidence" / "v4-impl" / "r6-model-admission" / "replies"


def _grade(admission_file: Path, label: str, out_dir: Path, tag: str) -> dict:
    out = out_dir / "regrade-{0}-{1}.json".format(label, tag)
    proc = subprocess.run(
        [str(rpv.REPO / ".venv/bin/python"), str(admission_file), "grade",
         "--replies", str(REPLIES / label), "--out", str(out),
         "--round-label", label],
        cwd=str(rpv.REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("grade 失败：{0}\n{1}".format(proc.stdout, proc.stderr))
    return json.loads(out.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", default=str(_HERE))
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)

    before_tools = rpv._build_tree("before")
    report = {"schema": "sitin-model-admission-regrade-attribution/1",
              "note": "同一工作树、同一 src：唯一差别是 tools/sitin_model_admission.py 的版本。",
              "rounds": {}}
    for label in ("r1", "r2"):
        after = _grade(rpv.TOOLS / "sitin_model_admission.py", label, out_dir,
                       "after")
        before = _grade(before_tools / "sitin_model_admission.py", label, out_dir,
                        "before")
        a = {row["task_id"]: row for row in after["tasks"]}
        b = {row["task_id"]: row for row in before["tasks"]}
        flips = []
        for tid in sorted(a):
            ap, bp = bool(a[tid].get("pass")), bool(b[tid].get("pass"))
            if ap != bp:
                flips.append({"task_id": tid, "before_pass": bp, "after_pass": ap,
                              "before_problems": b[tid].get("problems"),
                              "after_problems": a[tid].get("problems")})
        report["rounds"][label] = {
            "identity": {
                "before": before["identity"],
                "after": after["identity"],
            },
            "summary": {"before": before["summary"], "after": after["summary"]},
            "failed_tasks": {"before": sorted(t for t in b if not b[t].get("pass")),
                             "after": sorted(t for t in a if not a[t].get("pass"))},
            "flips": flips,
            "warnings": after.get("warnings"),
        }
    (out_dir / "regrade-attribution.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for label, row in report["rounds"].items():
        print(label,
              "before pass=%d scorer=%d" % (row["summary"]["before"]["pass"],
                                            row["summary"]["before"]["scorer_pass"]),
              "after pass=%d scorer=%d" % (row["summary"]["after"]["pass"],
                                           row["summary"]["after"]["scorer_pass"]),
              "flips=%d" % len(row["flips"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
