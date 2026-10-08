#!/usr/bin/env python3
"""G202：原样复用 G197 可选弃胡搜索，核 G201 八窗边界。"""

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

from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g197_optional_hu_three_draw_pilot as g197
import g201_multiwhite_near_ready_route as g201
import g201_multiwhite_near_ready_select as source


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G202-MULTIWHITE-OPTIONAL-HU-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g202-multiwhite-optional-hu-20260929/result.json')


def digest(path: Path) -> str:
    """冻结量具、固定观察与已知强制胡值的文件身份。"""

    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """每臂每包络独立计时；无法完整算完即整窗弃权。"""

    if OUT.exists():
        raise FileExistsError("G202 结果已存在，拒绝覆盖")
    selection = json.loads(source.OUT.read_text(encoding="utf-8"))
    forced = json.loads(g201.OUT.read_text(encoding="utf-8"))
    if (selection["schema"] != "g201-multiwhite-near-ready-selection/1"
            or forced["schema"] != "g201-multiwhite-near-ready-route/1"
            or forced["source_sha256"]["selection"] != digest(source.OUT)
            or len(selection["selected"]) != 8
            or len(forced["rows"]) != 8
            or any(row["status"] != "complete" for row in forced["rows"])):
        raise ValueError("G202 冻结八窗或强制胡基线漂移")
    results = []
    stopped_layers = set()
    for row, baseline in zip(selection["selected"], forced["rows"], strict=True):
        layer = row["layer"]
        if layer in stopped_layers:
            continue
        identity = ("layer", "room_id", "game_id", "round_no", "trigger_seq",
                    "seat", "parent_action", "alternate_action", "observation_sha256")
        if any(row[key] != baseline[key] for key in identity):
            raise ValueError("G202 选样与强制胡行身份错位")
        result = {key: row[key] for key in identity}
        result["arms"] = {}
        try:
            observation = g201.observe(row)
            g201.check_rules(row, observation)
            for name in ("parent", "alternate"):
                key = row[name + "_action"]
                modes = {}
                for mode in g201.MODES:
                    search = g197.OptionalHuSearch(observation, c31.RULE_CONFIG, key)
                    started = time.perf_counter()
                    optional = search.evaluate(restricted=mode == "restricted").json()
                    elapsed = (time.perf_counter() - started) * 1000
                    original = baseline["arms"][name]["values"][mode]
                    if optional["total"] + 1e-8 < original["total"]:
                        raise ValueError("G202 合法可选胡搜索低于强制胡基线")
                    modes[mode] = {
                        "forced": original, "optional": optional,
                        "optional_minus_forced": {field: round(optional[field] - original[field], 9)
                                                  for field in ("plain", "special", "depth1",
                                                                "depth2", "depth3", "total")},
                        "continue_over_hu": search.continue_over_hu,
                        "elapsed_ms": round(elapsed, 3),
                        "legal_leaf_count": search.legal_leaf_count,
                    }
                result["arms"][name] = modes
            result["status"] = "complete"
        except (g197.g196.RouteLimitExceeded, ValueError) as exc:
            result["status"] = "abstained"
            result["reason"] = type(exc).__name__ + ": " + str(exc)
            stopped_layers.add(layer)
        results.append(result)
        print(json.dumps({"attempted": len(results), "layer": layer,
                          "status": result["status"],
                          "reason": result.get("reason")},
                         ensure_ascii=False), flush=True)
    payload = {
        "schema": "g202-multiwhite-optional-hu/1",
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "selection": digest(source.OUT), "g201_forced": digest(g201.OUT),
                          "g197_script": digest(Path(g197.__file__)),
                          "g196_script": digest(Path(g197.g196.__file__))},
        "selected_count": 8, "attempted_count": len(results),
        "stopped_layers": sorted(stopped_layers), "rows": results,
        "boundary": "已见 G201 八窗的可选弃胡机制诊断；可交换未知池、三摸和两种未来资格包络，不含真实墙后验与对手先胡；非净收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": sum(row["status"] == "complete" for row in results),
                      "attempted": len(results), "stopped_layers": payload["stopped_layers"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
