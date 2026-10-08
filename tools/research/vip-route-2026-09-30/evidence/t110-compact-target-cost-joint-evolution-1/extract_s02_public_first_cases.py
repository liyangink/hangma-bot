"""纯读十六个已闭合首分歧来源，核公共前缀并提取作者可见事实。

每源按固定换座顺序取一个代表，包括终分持平、损失和收益；不挑成功终局。只保存
本座公开输入与原评分，不生成教师恢复路径，也不运行任何牌局业务。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import json
from pathlib import Path

from read_s02_first_divergences import normalize


HERE = Path(__file__).resolve().parent
NEW = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S02-natural-development-1')
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S01-natural-development-1')


def main():
    """完整公共前缀相等后输出十六源事实；终局不作为首动作金标。"""
    differences = json.loads((_project_file(_PROJECT_ROOT, HERE / "S02-COMPLETE-FIRST-DIVERGENCES.json")).read_text())
    # 每个发生首分歧的来源按固定换座序取一个代表，不按终分挑例。
    selected_by_root = {}
    for case in sorted(differences["differences"], key=lambda r: (r["root_serial"], r["group_file"])):
        selected_by_root.setdefault(case["root_serial"], case)
    selected = list(selected_by_root.values())
    assert len(selected) == len(differences["independent_changed_roots"]) == 16
    jobs = {}
    for case in selected:
        block = (int(case["root_serial"]) - 1) // 4 + 1
        for arm, campaign, actual_block in (("P", PRIOR, block + 4), ("C", NEW, block)):
            with gzip.open(campaign / f"block-{actual_block:02d}" / case["group_file"], "rt") as stream:
                group = json.load(stream)
            plan = json.loads((campaign / f"BLOCK-{actual_block:02d}-PLAN.json").read_text())
            cid = plan["candidate_identity"]["candidate_id"]
            record = next(r for r in group["match_records"] if r["match_id"].endswith("vip:" + cid))
            jobs[(case["root_serial"], arm)] = {"case": case, "source": campaign / f"block-{actual_block:02d}",
                "match_id": record["match_id"], "prefix": [], "target": None}
    for source in {r["source"] for r in jobs.values()}:
        matching = [r for r in jobs.values() if r["source"] == source]
        with gzip.open(source / "decisions.jsonl.gz", "rt") as stream:
            for line in stream:
                row = None
                for job in matching:
                    if job["target"] is not None or job["match_id"] not in line:
                        continue
                    row = json.loads(line) if row is None else row
                    if row["match_id"] != job["match_id"]:
                        continue
                    assert row["status"] == "chosen"
                    job["prefix"].append({k: row[k] for k in ("window_key", "observation", "legal_action_keys", "seat")})
                    if len(job["prefix"]) - 1 == job["case"]["first_decision_index"]:
                        assert row["seat"] == job["case"]["seat"] and row["c_self_scored"]
                        assert row["window_key"]["trigger_seq"] == job["case"]["window"]["trigger_seq"]
                        job["target"] = row
                if all(r["target"] is not None for r in matching):
                    break
    public = []
    wanted = set()
    for case in selected:
        p, c = jobs[(case["root_serial"], "P")], jobs[(case["root_serial"], "C")]
        assert p["target"] is not None and c["target"] is not None
        assert normalize(p["prefix"]) == normalize(c["prefix"])
        targets = {}
        for arm, job in (("P", p), ("C", c)):
            row = job["target"]
            receipt = row["scoring_calls"][0]
            assert receipt["status"] == "SCORED" and receipt["input_capture"]["saved_before_score"]
            digest = receipt["input_capture"]["view_sha256"]
            wanted.add(digest)
            targets[arm] = {"first_action": row["selected_action_key"], "actual_scores": row["candidates"],
                            "view_sha256": digest, "white_count": row["white_count"],
                            "current_opportunity": row["current_opportunity"]}
        public.append({"label": "T110-S02-first:" + case["root_serial"],
                       "observation": p["target"]["observation"], "window_key": p["target"]["window_key"],
                       "legal_action_keys": p["target"]["legal_action_keys"], "arms": targets,
                       "all_seat_public_prefix_rows_verified": len(p["prefix"]),
                       "public_prefix_equal": True, "not_optimal_action_gold": True})
    captured = set()
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "S02-PUBLIC-FIRST-CASE-VIEWS.jsonl.gz"), "xt") as output:
        for source in {r["source"] for r in jobs.values()}:
            with gzip.open(source / "views.jsonl.gz", "rt") as stream:
                for line in stream:
                    if not any(digest in line for digest in wanted - captured):
                        continue
                    row = json.loads(line)
                    digest = row["view_sha256"]
                    if digest in wanted and digest not in captured:
                        output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                        captured.add(digest)
    assert captured == wanted
    result = {"scope": "all_sixteen_changed_development_sources_fixed_rotation_order_first_differences",
              "cases": public, "new_business_calls": 0, "complete_full_public_DTOs": len(captured),
              "new_independent_confirmation_sources": 0, "future_wall_or_teacher_recovery_saved": False}
    with (_project_file(_PROJECT_ROOT, HERE / "S02-PUBLIC-FIRST-CASES.json")).open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"public_cases": [{"label": r["label"], "white_count": r["arms"]["P"]["white_count"],
                        "parent_first": r["arms"]["P"]["first_action"], "child_first": r["arms"]["C"]["first_action"],
                        "verified_prefix_rows": r["all_seat_public_prefix_rows_verified"]} for r in public],
                      "complete_DTOs": len(captured), "new_business_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
