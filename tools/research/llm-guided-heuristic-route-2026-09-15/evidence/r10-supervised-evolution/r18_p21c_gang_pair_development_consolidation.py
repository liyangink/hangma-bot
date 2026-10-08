"""R18 P21c：合并 P21 摸牌窗口与 P21b 明杠响应窗口开发标签。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p21_gang_pair_development_teacher as p21  # noqa: E402
import r18_p21b_exposed_gang_future_wall_teacher as p21b  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p21c-gang-pair-development-consolidation-01-20260922')
P21_SUMMARY = p21.OUT / "run-summary.json"
P21_TARGETS = p21.OUT / "targets.json"
P21B_RESULT = p21b.OUT / "result.json"
FAMILIES = p21.OPEN_FAMILIES


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bootstrap(values: list[float], salt: int) -> list[float]:
    rng = random.Random(202609222100 + salt)
    means = sorted(
        statistics.fmean(rng.choice(values) for _ in values)
        for _ in range(20_000)
    )
    return [means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]]


def _draw_family_states(targets: list[Mapping[str, Any]], family: str) -> list[dict[str, Any]]:
    states = []
    for target in targets:
        if target["split"] != "development" or target["family"] != family:
            continue
        rows = [
            json.loads(p21.rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, p21.ROLLOUTS_PER_STATE + 1)
        ]
        direct = [row["focal_current_round_settlement_delta"] for row in rows]
        full = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"], "family": family,
            "source": target["source"], "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "hidden_world_rollouts": len(rows),
            "mechanical_ok": all(row["mechanical_ok"] for row in rows),
            "mean_current_round_settlement_delta": statistics.fmean(direct),
            "mean_remaining_table_score_delta": statistics.fmean(full),
            "positive_hidden_worlds": sum(value > 0 for value in direct),
            "zero_hidden_worlds": sum(value == 0 for value in direct),
            "negative_hidden_worlds": sum(value < 0 for value in direct),
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
            "sampling_scope": "public-consistent opponent hands plus unconsumed wall; not history posterior",
        })
    return states


def build() -> None:
    """验证失败边界与修复边界后，生成三家族统一开发结论。"""

    if OUT.exists():
        raise SystemExit("P21c 目录已存在；拒绝覆盖")
    summary = json.loads(P21_SUMMARY.read_text(encoding="utf-8"))
    failures = summary["failures"]
    if summary["rollout_files"] != 1024 or summary["actual_tables"] != 2048:
        raise ValueError("P21 成功部分必须恰为32状态×32世界×2臂")
    if len(failures) != 512 or any(
        not row["target_id"].startswith("r18-p21-exposed-development-")
        or "隐藏世界只可在未阻塞的本人摸牌决策窗口重采样" not in row["error"]
        and "目标局必须按参考臂、干预臂各捕获一次，实际 0" not in row["error"]
        for row in failures
    ):
        raise ValueError("P21 失败边界不是完整的明杠响应层")
    targets = json.loads(P21_TARGETS.read_text(encoding="utf-8"))["targets"]
    p21b_result = json.loads(P21B_RESULT.read_text(encoding="utf-8"))
    if not p21b_result.get("mechanical_ok") or p21b_result.get("base_states") != 16:
        raise ValueError("P21b 明杠修复未完整通过")

    states = []
    states.extend(_draw_family_states(targets, "concealed.gang_to_nongang"))
    states.extend(_draw_family_states(targets, "added.gang_to_nongang"))
    states.extend({
        **row,
        "family": "exposed.gang_to_nongang",
        "sampling_scope": p21b_result["sampling_scope"],
    } for row in p21b_result["states"])
    by_family = {}
    for salt, family in enumerate(FAMILIES, 1):
        items = [row for row in states if row["family"] == family]
        values = [row["mean_current_round_settlement_delta"] for row in items]
        interval = _bootstrap(values, salt)
        positive = sum(value > 0 for value in values)
        mechanical = all(row["mechanical_ok"] for row in items)
        mean = statistics.fmean(values)
        by_family[family] = {
            "independent_states": len(items),
            "mean_non_gang_minus_gang_current_round_settlement": mean,
            "bootstrap_95_interval": interval,
            "positive_state_means": positive,
            "zero_state_means": sum(value == 0 for value in values),
            "negative_state_means": sum(value < 0 for value in values),
            "sampling_scope": sorted({row["sampling_scope"] for row in items}),
            "open_for_rule_authoring": bool(
                mechanical and len(items) == 16 and mean > 0
                and interval[0] > 0 and positive >= 10
            ),
        }
    open_families = [
        family for family in FAMILIES if by_family[family]["open_for_rule_authoring"]
    ]
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p21c-gang-pair-consolidation-manifest/1",
        "inputs": {
            "p21_run_summary": digest(P21_SUMMARY),
            "p21_targets": digest(P21_TARGETS),
            "p21b_result": digest(P21B_RESULT),
        },
        "criterion": "每家族均值>0、基础状态bootstrap下界>0、至少10/16正状态且机械全绿",
        "failed_rows_policy": "P21原512失败行保留且不补零；明杠只使用P21b独立修复批",
        "replication_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p21c-gang-pair-development-result/1",
        "status": "COMPLETE_P21C_GANG_PAIR_DEVELOPMENT_CONSOLIDATION",
        "mechanical_ok": all(row["mechanical_ok"] for row in states),
        "development_states": len(states),
        "successful_rollouts": 48 * 32,
        "successful_tables": 48 * 32 * 2,
        "preserved_failed_rollouts": len(failures),
        "states": states,
        "by_family": by_family,
        "families_open_for_rule_authoring": open_families,
        "families_closed_by_development_teacher": [
            family for family in FAMILIES if family not in open_families
        ],
        "replication_states_kept_blind": 48,
        "replication_labels_opened": False,
        "decision": "三个P5选杠家族均无总体正的非杠替代信号；不调用作者模型、不打开复验标签，关闭本轮非支配杠修正规则搜索",
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "COMPLETE_P21C_GANG_PAIR_DEVELOPMENT_CONSOLIDATION",
        "by_family": by_family,
        "families_open_for_rule_authoring": open_families,
        "replication_labels_opened": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
