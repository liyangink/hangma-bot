"""定向变异 runner（R8 E2 · 复审 §5 M3）：证明关键断言确实会失败（不是恒真）。

每个变异只改**一处**实现，其余同当前工作树；跑两件事：
  1. 专属测试（`tools/test_sitin_model_admission.py`）——必须转红；
  2. 等行为探针（`sitin_model_admission_probes.run_equivalence_probe`）——必须转红。

已登记变异：
  - score-diff-counts-as-behavior：第 ④ 条里只要**评分签名**不同就发放修订信用
    （= 复审 §5 M3 描述的缺陷本身：分数变化被当成行为变化）；
  - parent-incompatible-autocredit：父代在声明视图上全弃权时**改回自动发信用**
    （= 把「材料不兼容」终态静默退回「与它不同即算能力」；Lead 裁决 3 要求防回归）。

用法（从仓库根）：
    .venv/bin/python <本文件> --mutation <name> --out <pytest 输出> --equivalence-out <探针 JSON>
    .venv/bin/python <本文件> --list
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

MUTATIONS = {
    "score-diff-counts-as-behavior": {
        "where": "check_capability 第 ④ 条",
        "anchor": "            revision = revision_behavior_delta(code_text, parent_code, declared)",
        "mutant": ("            revision = revision_behavior_delta(code_text, parent_code, declared)\n"
                   "            if score_signature_digest(code_text, declared) != \\\n"
                   "                    score_signature_digest(parent_code, declared):\n"
                   '                revision["verdict"] = REVISION_OBSERVED\n'
                   '                revision["credited"] = True\n'
                   '                revision["mutated"] = "score-diff-counts-as-behavior"'),
        "expect_tests": ["test_reviewer_uniform_score_shift_is_no_longer_a_revision",
                         "test_equivalent_negative_set_translate_scale_relabel_all_fail",
                         "test_parent_all_abstain_is_material_incompatibility",
                         "test_parent_version_mismatch_terminal_state_is_material_incompatibility",
                         "test_frozen_task_parent_material_state_is_classified_not_credited"],
        "expect_probe_failures": ["T06-translate", "T06-scale", "T07-translate",
                                  "T07-scale", "T08-translate", "T08-scale",
                                  "review-affine-shift-T06", "frozen-material-T06"],
    },
    "parent-incompatible-autocredit": {
        "where": "revision_behavior_delta 的父代不可判分支",
        "anchor": ("    if not parent_observable:\n"
                   "        verdict = REVISION_PARENT_INCOMPATIBLE"),
        "mutant": ("    if not parent_observable:\n"
                   "        verdict = (REVISION_OBSERVED if child_observable\n"
                   "                   else REVISION_CHILD_NO_EVIDENCE)\n"
                   '        mutated = "parent-incompatible-autocredit"'),
        "expect_tests": ["test_parent_version_mismatch_terminal_state_is_material_incompatibility",
                         "test_parent_all_abstain_is_material_incompatibility",
                         "test_frozen_task_parent_material_state_is_classified_not_credited"],
        "expect_probe_failures": ["frozen-material-T06"],
    },
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutation", choices=sorted(MUTATIONS))
    parser.add_argument("--out", default=None)
    parser.add_argument("--equivalence-out", default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list or not args.mutation:
        print(json.dumps({name: {"where": row["where"],
                                 "expect_tests": row["expect_tests"],
                                 "expect_probe_failures": row["expect_probe_failures"]}
                          for name, row in MUTATIONS.items()},
                         ensure_ascii=False, indent=1))
        return 0

    spec = MUTATIONS[args.mutation]
    tools_dir = rpv._build_tree("after")
    target = tools_dir / "sitin_model_admission.py"
    text = target.read_text(encoding="utf-8")
    if spec["anchor"] not in text:
        raise SystemExit("变异锚点未找到（实现已改，请同步本脚本）：" + args.mutation)
    target.write_text(text.replace(spec["anchor"], spec["mutant"], 1), encoding="utf-8")
    print("mutation:", args.mutation, "→", spec["where"])

    out = Path(args.out) if args.out else _project_file(_PROJECT_ROOT, _HERE / (args.mutation + "-pytest.txt"))
    proc = subprocess.run(
        [str(rpv.REPO / ".venv/bin/python"), "-m", "pytest",
         str(tools_dir / "test_sitin_model_admission.py"), "-q", "-rA",
         "-p", "no:cacheprovider"],
        cwd=str(rpv.REPO), capture_output=True, text=True)
    out.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    failed = sorted({line.split("::")[-1] for line in proc.stdout.splitlines()
                     if line.startswith("FAILED")})
    print("pytest:", proc.stdout.strip().splitlines()[-1])
    print("failed tests:", failed)
    missing = [name for name in spec["expect_tests"] if name not in failed]
    print("expected-but-not-failed:", missing)

    sys.path.insert(0, str(tools_dir))
    import sitin_model_admission  # noqa: E402,F401 —— 先钉住被变异的那一份
    import sitin_model_admission_probes as probes  # noqa: E402
    equivalence = probes.run_equivalence_probe()
    eq_out = Path(args.equivalence_out) if args.equivalence_out else \
        _project_file(_PROJECT_ROOT, _HERE / (args.mutation + "-equivalence.json"))
    eq_out.write_text(json.dumps(equivalence, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print("probe:", json.dumps({"equivalence_ok": equivalence["ok"],
                                "failed_probes": equivalence["failed_probes"]},
                               ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
