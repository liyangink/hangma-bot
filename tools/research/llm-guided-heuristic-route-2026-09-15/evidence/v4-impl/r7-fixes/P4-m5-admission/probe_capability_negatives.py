"""P4/M5 负例成绩探针：三类负例 + 复审反例在每个评分器任务上的通过情况。

修复前后各跑一次（同一脚本、同一输入），产出可比较的成绩：
    .venv/bin/python <本文件> --out <结果 JSON>
判据：三类负例与复审反例在修复后必须**一个评分器任务都不通过**。
只跑进程内合成视图（0 真实 LLM、0 真实桌赛），只读既有产物。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r7-fixes/P4-m5-admission'

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
import sys
from pathlib import Path

REPO = _PROJECT_ROOT
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(TOOLS))
import sitin_model_admission as adm  # noqa: E402

PKG = adm.PACKAGE_DIR
HERE = Path(__file__).resolve().parent
NEG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r7-fixes/P4-m5-admission/negative-examples')
SCORER = ("T05", "T06", "T07", "T08", "T09", "T10")
REVISION = ("T06", "T07", "T08")

REVIEWER_REPLY = '''{只弃权的反例评分器，验证格式准入是否会误当作作者能力。}
```json
{"trigger":"反馈：任何窗口", "changed_branches":"①：所有窗口均弃权", "expected_direction":"全部弃权", "counterexample":"从不实际评分"}
```
```python
def score_actions(view):
    """只返回有理由的弃权，用于有限准入反例。"""
    return {"status": "ABSTAIN", "reason": "no scoring implemented"}
```
'''


def _cases():
    cases = []
    for tid in SCORER:
        for cls, path in (("reviewer-counterexample", None),
                          ("always-abstain", _project_file(_PROJECT_ROOT, NEG / (tid + "-always-abstain.txt"))),
                          ("constant-scoring", _project_file(_PROJECT_ROOT, NEG / (tid + "-constant.txt")))):
            if path is None and cls != "reviewer-counterexample":
                continue
            text = REVIEWER_REPLY if path is None else path.read_text(encoding="utf-8")
            cases.append((cls, tid, text))
    for tid in REVISION:
        cases.append(("mechanism-only", tid,
                      (_project_file(_PROJECT_ROOT, NEG / (tid + "-mechanism-only.txt"))).read_text(encoding="utf-8")))
    return cases


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    rows = []
    for cls, tid, text in _cases():
        task = json.loads((PKG / "tasks" / (tid + ".json")).read_text(encoding="utf-8"))
        outcome = adm.check_code(text, task["validation"], PKG)
        rows.append({"class": cls, "task": tid, "pass": outcome["pass"],
                     "violation": outcome["violation"],
                     "problems": outcome["problems"][:4]})
    summary = {}
    for row in rows:
        bucket = summary.setdefault(row["class"], {"tasks": 0, "passed": 0, "passed_tasks": []})
        bucket["tasks"] += 1
        if row["pass"]:
            bucket["passed"] += 1
            bucket["passed_tasks"].append(row["task"])
    payload = {"schema": "sitin-model-admission-negative-probe/1",
               "note": "三类负例 + 复审反例的通过情况；修复后应为 0。",
               "budget_note": "0 真实 LLM、0 真实桌赛。",
               "summary": summary, "rows": rows}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({cls: {"passed": v["passed"], "tasks": v["tasks"],
                            "passed_tasks": v["passed_tasks"]}
                      for cls, v in summary.items()}, ensure_ascii=False))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
