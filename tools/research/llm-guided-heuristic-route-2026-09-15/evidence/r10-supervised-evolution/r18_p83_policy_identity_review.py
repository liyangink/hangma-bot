"""P83 结果盲身份复核：逐桌策略身份与冻结窗口的实际策略首选。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p83_high_wealth_near_seven_claim_exposure as p83  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


def main() -> None:
    """拒绝任何非冻结父代策略身份或目标窗口首选动作不一致。"""

    _, sources = p83.verify()
    result = json.loads((p83.OUT / "result.json").read_text(encoding="utf-8"))
    dataset = json.loads((p83.OUT / "dataset.json").read_text(encoding="utf-8"))
    if result["tables"] != 512 or len(sources) != 256:
        raise ValueError("P83 自然来源未完整冻结")
    rows = list(dataset["rows"])
    policy = ActionValuePolicy(ActionValueScorer(
        "r18-p83-independent-policy-review", p83.parent_source(),
    ))
    checked = 0
    for row in rows:
        request = decision_request_from_json(row["request"])
        plan = asyncio.run(policy.choose(request, None))
        actual = None if not plan.candidates else action_key(plan.candidates[0].action)
        if actual != row["reference_action"]:
            raise ValueError("冻结窗口首选动作不一致：" + row["source"]["source_id"])
        checked += 1
    identity_tables = 0
    for source in sources:
        saved = json.loads(p83.source_path(source).read_text(encoding="utf-8"))
        expected = "action_value_v1:r18-p83-trajectory-" + str(source["source_id"])
        ids = list(saved["focal_policy_ids"])
        if saved["status"] != "complete" or ids != [expected, expected]:
            raise ValueError("逐桌焦点策略身份错误：" + str(source["source_id"]))
        identity_tables += len(ids)
    summary = {
        "schema": "r18-p83-policy-identity-review/1",
        "source_units": len(sources),
        "actual_tables": result["tables"],
        "candidate_policy_identity_tables": identity_tables,
        "selected_window_policy_top_checked": checked,
        "selected_window_policy_top_mismatches": 0,
        "outcome_labels_opened": False,
        "review_passed": identity_tables == result["tables"] and checked == len(rows),
    }
    p83.write_json(p83.OUT / "policy-identity-review.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
