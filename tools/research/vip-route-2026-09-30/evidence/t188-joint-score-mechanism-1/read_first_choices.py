"""只读全部已闭14来源的首评分，定位排序差异；不新增评分或续打。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save


def main(check_gain):
    """核完整来源及首手同公开输入，保存全合法评分；费用负信号时可返回非零。"""
    plan_path = _project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICE-PLAN.json")
    plan = json.loads(plan_path.read_text())
    assert all(pin(Path(p)) == h for p,h in plan["files"].items())
    closed = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-CONDITION-CLOSED.json")).read_text())
    original = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-CONDITION-PLAN.json")).read_text())
    assert closed["complete"] and closed["source_stable"] and closed["resources_released"]
    assert all(pin(Path(p)) == h for p,h in closed["files"].items())
    rows = []
    for index, target in enumerate(original["targets"],1):
        directory = _project_file(_PROJECT_ROOT, SOURCE / "exploration-condition" / f"target-{index:03d}")
        first = {}
        with gzip.open(directory / "decisions.jsonl.gz", "rt") as stream:
            for line in stream:
                record = json.loads(line)
                key = (record["sample"],record["arm"])
                if key not in first:
                    first[key] = record["row"]
        assert set(first) == {(s,a) for s in range(3) for a in ("A","C")}
        required = set()
        for s in range(3):
            a,c = first[(s,"A")], first[(s,"C")]
            assert canonical(a["observation"]) == canonical(c["observation"]) == canonical(target["case"]["observation"])
            assert a["window_key"] == c["window_key"] == target["case"]["window_key"]
            assert a["legal_action_keys"] == c["legal_action_keys"]
            assert a["scoring_calls"][0]["input_capture"]["view_sha256"] == c["scoring_calls"][0]["input_capture"]["view_sha256"]
            for row in (a,c):
                assert row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"]
                assert row["scoring_calls"][0]["actual_score_calls"] == 1
                assert sorted(e["action_key"] for e in row["candidates"]) == sorted(row["legal_action_keys"])
                required.add(row["scoring_calls"][0]["input_capture"]["view_sha256"])
        views = {}
        with gzip.open(directory / "views.jsonl.gz", "rt") as stream:
            for line in stream:
                item = json.loads(line)
                if item.get("view_sha256") in required and "view" in item:
                    assert hashlib.sha256(canonical(item["view"])).hexdigest() == item["view_sha256"]
                    views[item["view_sha256"]] = item["view"]
        assert set(views) == required and len(required) == 1
        a,c = first[(0,"A")],first[(0,"C")]
        detail = next(t for t in closed["target_summaries"] if t["target"] == index)
        rows.append({"target":index, "label":target["case"]["label"], "root_id":target["case"]["root_id"],
            "observation":a["observation"], "window_key":a["window_key"], "view_sha256":next(iter(required)),
            "view":views[next(iter(required))], "A":a, "C":c,
            "historical_sum_C_minus_A":detail["historical"]["C_minus_A"],
            "conditional_sum_C_minus_A":detail["two_conditional"]["sum_C_minus_A"],
            "first_differs":a["selected_action_key"] != c["selected_action_key"],
            "single_action_causal_claim":False})
    output = _project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICES.jsonl.gz")
    assert not output.exists()
    with gzip.open(output,"xb") as stream:
        for row in rows:stream.write(canonical(row)+b"\n")
    result = {"complete": True, "targets":14, "first_changed":sum(r["first_differs"] for r in rows),
        "source_stable":all(pin(Path(p)) == h for p,h in plan["files"].items()),
        "output_pin":pin(output), "plan_pin":pin(plan_path),
        "historical_sum_C_minus_A":closed["historical_exposed"]["sum_C_minus_A"],
        "conditional_sum_C_minus_A":closed["public_compatible_uniform"]["sum_C_minus_A"],
        "new_scores_worlds_tables_models_HTTP":0}
    save(_project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICE-CLOSED.json"),result)
    print(json.dumps({k:result[k] for k in ("complete","targets","first_changed","conditional_sum_C_minus_A","new_scores_worlds_tables_models_HTTP")}))
    return 1 if check_gain and result["conditional_sum_C_minus_A"]["net"] <= 0 else 0


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--assert-gain",action="store_true")
    raise SystemExit(main(parser.parse_args().assert_gain))
