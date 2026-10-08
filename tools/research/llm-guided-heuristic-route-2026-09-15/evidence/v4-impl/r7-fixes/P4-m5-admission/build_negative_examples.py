"""生成 P4/M5 三类负例回复（始终弃权 / 常数评分 / 只改说明不改行为）。

负例是**输入夹具**：判分器对它必须给出「不达标」。文件写入
evidence/v4-impl/r7-fixes/P4-m5-admission/negative-examples/，供
tools/test_sitin_model_admission.py 与复审复跑共用（0 真实 LLM、0 真实桌赛）。

三类负例的构造口径：
1. always-abstain：四字段写普通描述（刻意命中各任务的机制关键词组，隔离出能力合同
   这一条），代码恒返回有因 ABSTAIN——复审反例的等价形态；
2. constant：SCORED 但所有动作同一分数——格式安全、无任何方向差异；
3. mechanism-only：父代源码 + 只改标签常量（MECH），四字段改写成「新机制」，
   源码与父代不同（过 must_differ_from）但行为签名与父代一致。
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

import json
from pathlib import Path

REPO = _PROJECT_ROOT
PKG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r7-fixes/P4-m5-admission/negative-examples')
SCORER = ("T05", "T06", "T07", "T08", "T09", "T10")
REVISION = ("T06", "T07", "T08")

THOUGHTS = {
    "T05": "全新评分器：任何窗口统一处理。",
    "T06": "按三段真实反馈修订父代 triax-v1。",
    "T07": "按指定修订主线①给出代价侧②的机制。",
    "T08": "预算边界：最后一次调用也只交付单个候选。",
    "T09": "输入缺口：缺失事实按未知降档，不按已知 0。",
    "T10": "受限子集：拒绝把 import/while 引入候选。",
}
#: 四字段按任务写普通描述；命中机制关键词组的 token 见 T06/T07/T09。
MECHANISM = {
    "T05": ("反馈：任何动作窗口", "①：全部窗口统一处理", "排序方向保持不变", "从不实际评分"),
    "T06": ("反馈：三段真实反馈要求修订", "①：按反馈调整权重", "方向：评估窗口排序变化",
            "从不实际评分"),
    "T07": ("①：按指定修订主线", "②：代价侧保持不变", "③：方向不变", "从不实际评分"),
    "T08": ("预算只剩一次调用", "①：只交付一个候选", "方向保持不变", "从不实际评分"),
    "T09": ("未知缺口：缺失事实不得按已知 0", "①：未知动作显式降档",
            "方向：未知排在已知之后", "从不实际评分"),
    "T10": ("受限子集：不得 import 或 while", "①：拒绝越界附带要求", "方向保持不变",
            "从不实际评分"),
}

ABSTAIN_CODE = '''def score_actions(view):
    """只返回有理由的弃权，用于有限准入反例。"""
    return {"status": "ABSTAIN", "reason": "no scoring implemented"}
'''

CONSTANT_CODE = '''CONSTANT_SCORE = -1.0


def score_actions(view):
    """常量评分反例：每个动作同一分数，不产生任何方向差异。"""
    entries = []
    for action in view["actions"]:
        entries.append({"action_key": action["action_key"], "score": CONSTANT_SCORE,
                        "trace": {"basis": "constant"}})
    return {"status": "SCORED", "entries": entries, "reason": None}
'''


def _reply(task_id: str, code: str) -> str:
    trigger, changed, direction, counter = MECHANISM[task_id]
    mechanism = json.dumps({"trigger": trigger, "changed_branches": changed,
                            "expected_direction": direction, "counterexample": counter},
                           ensure_ascii=False)
    return ("{" + THOUGHTS[task_id] + "}\n\n```json\n" + mechanism
            + "\n```\n\n```python\n" + code + "```\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for task_id in SCORER:
        path = _project_file(_PROJECT_ROOT, OUT / (task_id + "-always-abstain.txt"))
        path.write_text(_reply(task_id, ABSTAIN_CODE), encoding="utf-8")
        written.append(path.name)
        path = _project_file(_PROJECT_ROOT, OUT / (task_id + "-constant.txt"))
        path.write_text(_reply(task_id, CONSTANT_CODE), encoding="utf-8")
        written.append(path.name)
    parent = (_project_file(_PROJECT_ROOT, PKG / "materials" / "T06-parent-triax-v1.py")).read_text(encoding="utf-8")
    assert 'MECH = "triax-v1"' in parent
    variant = parent.replace('MECH = "triax-v1"', 'MECH = "triax-v1-relabelled"')
    assert variant != parent
    for task_id in REVISION:
        path = _project_file(_PROJECT_ROOT, OUT / (task_id + "-mechanism-only.txt"))
        path.write_text(_reply(task_id, variant), encoding="utf-8")
        written.append(path.name)
    print(json.dumps({"written": written, "dir": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
