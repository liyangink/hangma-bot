"""绑定四个不同历史母牌山的已曝光开发输入，不沿用旧评分或旧投影身份。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

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

from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


def main():
    """只按预定母源和窗口键取旧观察；旧面板本身富集，不能估自然频率。"""
    panel_file = _project_file(_PROJECT_ROOT, EVIDENCE / "t110-compact-target-cost-joint-evolution-1/PUBLIC-PANEL.json")
    panel = json.loads(panel_file.read_text())
    specs = (
        ("t27-unchanged-control-new-source-1/PARENT-natural-first-block.batch.json", (2026102901,)),
        ("t29-second-pre-frozen-common-root-1/PARENT-natural-first-block.batch.json", (2026102902,)),
        ("t30-next-two-pre-frozen-common-roots-1/PARENT-natural-next2.batch.json", (2026102903, 2026102904)),
    )
    selected = []
    seeds = []
    pins = {str(panel_file): pin(panel_file)}
    for name, wanted in specs:
        source = _project_file(_PROJECT_ROOT, EVIDENCE / name)
        batch = json.loads(source.read_text())
        pins[str(source)] = pin(source)
        for root in batch["seeds"]:
            if root["seed"] not in wanted:
                continue
            seeds.append(root["seed"])
            candidates = [c for c in panel["cases"] if root["root_id"] in c["observation"]["game_id"]]
            assert candidates
            # 仅根据母源、当前白数及窗口身份排序；不读取parent_scores、first或结果。
            candidates.sort(key=lambda c: (c["window_key"]["round_no"],
                                            c["window_key"]["trigger_seq"],
                                            c["window_key"]["seat"]))
            keys = set()
            for case in candidates:
                key = tuple(case["window_key"].values())
                if key in keys:
                    continue
                keys.add(key)
                selected.append({"root_id": root["root_id"], "seed": root["seed"],
                    "label": case["label"], "observation": case["observation"],
                    "window_key": case["window_key"], "source_batch": name,
                    "role": "previously_exposed_historical_development_not_confirmation",
                    "original_panel_scope": panel["scope"], "old_score_or_view_credit": False})
                if len(keys) == 4:
                    break
    assert len(seeds) == 4 and len(set(seeds)) == 4
    save(_project_file(_PROJECT_ROOT, HERE / "HISTORICAL-PANEL-FROZEN.json"), {"schema": "t182-four-historical-roots/1",
        "cases": selected, "independent_mother_roots": 4, "files": pins,
        "selection_uses_current_outcomes_or_scores": False,
        "historical_panel_original_selection_not_claimed_result_blind": True,
        "old_scores_reused": False, "new_rules_scores_worlds_calls": 0})
    print(json.dumps({"historical_roots": 4, "historical_windows": len(selected),
                      "new_rules_scores_worlds_calls": 0}))


if __name__ == "__main__":
    main()
