"""复审反例复跑（逐字复刻复审脚本，仅改输出路径以便不改动冻结产物）。

来源：review/llm-guided-heuristic-route-2026-09-15/evidence/r6-implementation-review-2026-09-17/admission_probe.py
（复审脚本把结果写回同目录的 admission-probe-result.json；该产物已冻结，本复跑脚本
只复刻探针文本与判分循环，结果写到 r7-fixes/P4-m5-admission/ 下的独立目录。）

用法（仓库根）：
    .venv/bin/python <本文件> --out <结果 JSON 路径>
"""

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
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / 'review/llm-guided-heuristic-route-2026-09-15/tools')))
import sitin_model_admission as adm

#: 复审反例原文（四字段写普通描述、代码始终 ABSTAIN）——逐字复制，不得改动。
REPLY = '''{只弃权的反例评分器，验证格式准入是否会误当作作者能力。}
```json
{"trigger":"反馈：任何窗口", "changed_branches":"①：所有窗口均弃权", "expected_direction":"全部弃权", "counterexample":"从不实际评分"}
```
```python
def score_actions(view):
    """只返回有理由的弃权，用于有限准入反例。"""
    return {"status": "ABSTAIN", "reason": "no scoring implemented"}
```
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(Path(__file__).with_name("reviewer-counterexample.json")))
    args = parser.parse_args(argv)
    rows = []
    for tid in ['T05', 'T06', 'T07', 'T08', 'T09', 'T10']:
        task = json.loads((adm.PACKAGE_DIR / 'tasks' / (tid + '.json')).read_text())
        result = adm.check_code(REPLY, task['validation'], adm.PACKAGE_DIR)
        rows.append({'task': tid, **result})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({'passed': sum(r['pass'] for r in rows), 'tasks': len(rows),
                      'per_task': {r['task']: r['pass'] for r in rows},
                      'output': str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
