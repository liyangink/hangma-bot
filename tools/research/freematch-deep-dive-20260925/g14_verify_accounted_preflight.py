#!/usr/bin/env python3
"""逐字复核 G14 结算旁路与冻结自然面板的同牌山机械恒等性。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
from pathlib import Path

from g13_hand_accounting import summarize_hands


HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-accounted-pair-preflight-20260927')
MINIMAL_HAND_FIELDS = frozenset((
    "round_no", "hand_id", "result_confirmed", "scores_before", "scores_after",
    "score_delta", "winner_seat", "is_draw", "fan", "details",
))


def _read(path: Path) -> dict:
    """读取冻结 JSON，缺件直接失败。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    """证据文件摘要，防止两套阶段目录被无声调换。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict:
    """验收两臂十六阶段；只忽略预期变化的研究驱动版本标识。"""
    current = BASE
    legacy = _project_file(_PROJECT_ROOT, BASE / "legacy")
    new_manifest, old_manifest = (_read(directory / "manifest.json")
                                  for directory in (current, legacy))
    for field in ("panel_seed", "root_start", "roots_per_mix", "mixes",
                  "seats", "arms", "tables_per_stage", "planned_complete_tables"):
        if new_manifest[field] != old_manifest[field]:
            raise ValueError("新旧面板身份或计划不一致：" + field)
    names = {path.name for path in (current / "stages").glob("*.json")}
    old_names = {path.name for path in (legacy / "stages").glob("*.json")}
    if names != old_names or len(names) != 16:
        raise ValueError("新旧阶段文件集合不一致")
    stages = tables = hands = 0
    for name in sorted(names):
        new = _read(current / "stages" / name)
        old = _read(legacy / "stages" / name)
        if any(new.get(field) != old.get(field) for field in
               ("mix", "root_index", "focal_seat", "arm")):
            raise ValueError("阶段外层身份不符：" + name)
        a, b = new["stage"], old["stage"]
        for field in ("status", "focal_stage_score", "stage_totals_by_participant",
                      "u_interval", "execution_review"):
            if a[field] != b[field]:
                raise ValueError("阶段评估发生变化：" + name + " " + field)
        if len(a["tables"]) != len(b["tables"]) or len(a["tables"]) != 2:
            raise ValueError("阶段桌数漂移：" + name)
        stages += 1
        for ta, tb in zip(a["tables"], b["tables"]):
            for field in ("table_id", "seed", "scores_by_seat", "policy_execution"):
                if ta[field] != tb[field]:
                    raise ValueError("桌身份、结果或策略审计变化：" + name + " " + field)
            for field in ("game_key", "runtime_counts", "scores_after", "status"):
                if ta["result"][field] != tb["result"][field]:
                    raise ValueError("桌运行字段变化：" + name + " " + field)
            account = ta["hand_account"]
            records = ta["hand_records"]
            if len(records) != 8 or any(set(record) != MINIMAL_HAND_FIELDS
                                        for record in records):
                raise ValueError("逐局结算不是八局最小字段集：" + name)
            again = summarize_hands(
                records, focal_seat=account["focal_seat"],
                initial_scores=(0, 0, 0, 0), final_scores=ta["scores_by_seat"],
                expected_hands=8)
            if again != account:
                raise ValueError("逐局拆账重算不符：" + name)
            tables += 1
            hands += len(records)
    new_result, old_result = (_read(directory / "result.json")
                              for directory in (current, legacy))
    if (new_result["descriptive_mean_delta_vs_baseline_per_table"] !=
            old_result["descriptive_mean_delta_vs_baseline_per_table"]):
        raise ValueError("根级配对差值改变")
    if tables != new_manifest["planned_complete_tables"] or hands != tables * 8:
        raise ValueError("完成桌/局数与清单不符")
    return {"schema": "g14-accounted-preflight-verification/1",
            "status": "pass", "stages": stages, "tables": tables, "hands": hands,
            "candidate_runner_sha256": _sha(_project_file(_PROJECT_ROOT, HERE / "g14_accounted_paired_panel.py")),
            "accounting_runner_sha256": _sha(_project_file(_PROJECT_ROOT, HERE / "g13_accounted_panel.py")),
            "legacy_manifest_sha256": _sha(legacy / "manifest.json"),
            "current_manifest_sha256": _sha(current / "manifest.json"),
            "effect_boundary": "同根机械对照；不是独立效果确认。"}


if __name__ == "__main__":
    result = verify()
    target = _project_file(_PROJECT_ROOT, BASE / "verification.json")
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != encoded:
        raise SystemExit("已有机械验证结果不同，拒绝覆盖")
    target.write_text(encoded, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
