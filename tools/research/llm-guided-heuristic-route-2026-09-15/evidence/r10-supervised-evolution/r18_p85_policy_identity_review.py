"""P85 结果盲身份复核：真实自然轨迹策略身份与冻结首选动作。"""

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

import r18_p85_hu_deferral_natural_exposure as p85  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


def main() -> None:
    """核对所有来源桌的焦点策略，以及所有入选窗口的生产策略首选。"""

    sources = p85.verify()
    result = json.loads((p85.OUT / "result.json").read_text(encoding="utf-8"))
    dataset = json.loads((p85.OUT / "dataset.json").read_text(encoding="utf-8"))
    if result["tables"] != p85.PLANNED_TABLES or len(sources) != len(p85.sources()):
        raise ValueError("P85 自然来源未完整冻结")
    if not dataset["outcome_blind"] or dataset["replication_labels_opened"]:
        raise ValueError("P85 结果盲数据边界漂移")
    rows = list(dataset["rows"])
    policy = ActionValuePolicy(ActionValueScorer(
        "r18-p85-independent-policy-review", p85.parent_source(),
    ))
    for row in rows:
        request = decision_request_from_json(row["request"])
        plan = asyncio.run(policy.choose(request, None))
        actual = None if not plan.candidates else action_key(plan.candidates[0].action)
        if actual != row["reference_action"]:
            raise ValueError("冻结窗口首选动作不一致：" + row["source"]["source_id"])
        if row["intervention_action"] != "hu":
            raise ValueError("冻结对照动作不是立即胡")
    identity_tables = 0
    for source in sources:
        saved = json.loads(p85.source_path(source).read_text(encoding="utf-8"))
        expected = "action_value_v1:r18-p85-trajectory-" + str(source["source_id"])
        ids = list(saved["focal_policy_ids"])
        if saved["status"] != "complete" or ids != [expected, expected]:
            raise ValueError("逐桌焦点策略身份错误：" + str(source["source_id"]))
        if saved["audit"]["problems"]:
            raise ValueError("自然来源评分有异常：" + str(source["source_id"]))
        identity_tables += len(ids)
    summary = {
        "schema": "r18-p85-policy-identity-review/1",
        "source_units": len(sources), "actual_tables": result["tables"],
        "candidate_policy_identity_tables": identity_tables,
        "selected_window_policy_top_checked": len(rows),
        "selected_window_policy_top_mismatches": 0,
        "outcome_labels_opened": False,
        "review_passed": identity_tables == result["tables"] and len(rows) == result["selected_states"],
    }
    p85.write_json(p85.OUT / "policy-identity-review.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
