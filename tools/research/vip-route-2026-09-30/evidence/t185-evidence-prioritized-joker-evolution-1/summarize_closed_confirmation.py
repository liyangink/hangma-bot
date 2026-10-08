"""只读本批已闭确认，对账完整桌并保存紧凑汇总；不重新评分或重跑桌赛。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

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
from collections import Counter
from pathlib import Path

from common import HERE, pin, save


def require(condition, message):
    """证据矛盾时拒绝生成成功汇总，保留原始终态。"""
    if not condition:
        raise ValueError(message)


def main():
    """对照128来源、四换座和父子收据；输出单位均为每份完整桌。"""
    names = ["CONFIRMATION-PLAN.json", "CONFIRMATION-CLOSED.json",
             "confirmation-dispatch/CLOSED.json", "post-confirmation/CLOSED.json"]
    names += [f"confirmation-workers/worker-{i}/{n}.json"
              for i in range(2) for n in ("START", "CLOSE")]
    paths = [_project_file(_PROJECT_ROOT, HERE / n) for n in names]
    pins = {str(p): pin(p) for p in paths}
    data = {n: json.loads((_project_file(_PROJECT_ROOT, HERE / n)).read_text()) for n in names}
    plan, closed = data[names[0]], data[names[1]]
    dispatch, post = data[names[2]], data[names[3]]
    comparison = closed["comparison"]
    require(closed["complete"] and closed["source_stable"] and
            closed["confirmation_resource_receipts_verified"], "完整确认或原资源证据未闭合")
    require(dispatch["complete"] and dispatch["resources_released"] and
            dispatch["readout_exit_code"] == 0 and dispatch["worker_returncodes"] == [0, 0],
            "派发器未正常结束")
    require(dispatch["confirmation_closed_pin"] == pins[str(paths[1])], "确认原件摘要不对应")
    require(len(plan["roots"]) == 128 and plan["rounds"] == 8 and
            plan["planned_table_instances"] == 1024 and len(plan["candidates"]) == 1,
            "不是本批冻结样本或配置")
    require(comparison["candidate_id"] == plan["selected_candidate_id"], "候选身份漂移")
    expected = {(r["root_id"], s, a) for r in plan["roots"] for s in range(4) for a in range(2)}
    tables = {(t["root_id"], t["rotation"], t["arm_index"]): t for t in closed["tables"]}
    require(len(tables) == len(closed["tables"]) == 1024 and set(tables) == expected,
            "完整桌有重漏或来源不对应")
    require(sum(t["account"]["hands"] for t in tables.values()) ==
            closed["completed_hand_instances"] == 8192, "单局数量不对账")
    require(sum(t["audit"]["actual_score_calls"] for t in tables.values()) ==
            closed["actual_focal_score_calls"] == closed["actual_focal_decisions"] == 384516,
            "本家实际评分数量不对账")
    totals, source_ids = Counter(), []
    for root, source in zip(plan["roots"], comparison["sources"], strict=True):
        require(source["root_id"] == root["root_id"] and source["seed"] == root["seed"],
                "独立来源身份不对应")
        source_ids.append(source["root_id"])
        local = Counter()
        require(len(source["paired_tables"]) == 4, "来源未完成四换座")
        for rotation, pair in enumerate(source["paired_tables"]):
            require(pair["rotation"] == rotation, "换座顺序不对应")
            for arm, label in enumerate(("parent", "child")):
                require(pair[label] == tables[(root["root_id"], rotation, arm)]["account"],
                        "配对分账与完整桌原分账不对应")
            for key, value in pair["delta"].items():
                require(value == pair["child"][key] - pair["parent"][key], "父子差不对账")
                local[key] += value
            d = pair["delta"]
            require(d["net"] == d["ordinary_hu_income"] + d["large_hu_income"] + d["payments"]
                    == d["dealer_net"] + d["non_dealer_net"], "净分分账不对账")
        require(dict(local) == source["four_seat_delta_sums"] and
                all(source["mean_delta"][k] == v / 4 for k, v in local.items()),
                "母来源均值不对账")
        totals.update(local)
    require(len(source_ids) == len(set(source_ids)) == 128, "独立母来源重漏")
    require(all(comparison["mean_delta"][k] == v / 512 for k, v in totals.items()) and
            totals["net"] == comparison["net_delta_sum_512_tables"] == 2515,
            "完整批均值不对账")
    workers = []
    for slot in range(2):
        start, end = (data[f"confirmation-workers/worker-{slot}/{n}.json"] for n in ("START", "CLOSE"))
        ordinals = list(range(slot, 1024, 2))
        require(start["pid"] == end["pid"] and end["complete"] and end["failure"] is None and
                end["attempted_ordinals"] == end["completed_ordinals"] == ordinals and
                end["actual_table_calls"] == 512 and
                end["start_pin"] == pins[str(_project_file(_PROJECT_ROOT, HERE / f"confirmation-workers/worker-{slot}/START.json"))],
                "worker原始收据未自然完整结束")
        workers.append({"slot": slot, "pid": end["pid"], "actual_table_calls": 512})
    require(not comparison["independent_strength_evidence_passed"] and
            not comparison["net_score_signal_gate_passed"] and
            not post["complete"] and post["phases"] == [] and post["source_stable"] and
            post["failure"]["message"] == "确认均值或来源区间未通过",
            "统计未通过与接续停点不对应")
    require(all(pin(Path(p)) == h for p, h in pins.items()), "只读期间原件漂移")
    archive = _project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json.gz")
    raw = paths[1].read_bytes()
    with archive.open("xb") as stream:
        stream.write(gzip.compress(raw, compresslevel=6, mtime=0))
    require(gzip.decompress(archive.read_bytes()) == raw, "压缩原件恢复不同")
    result = {
        "schema": "t185-confirmation-summary/1", "complete": True,
        "candidate_id": comparison["candidate_id"], "baseline": "T110-S02/free_v6",
        "actual_table_instances": 1024, "paired_complete_tables": 512,
        "independent_mother_sources": 128, "completed_hand_instances": 8192,
        "actual_focal_score_calls": 384516, "workers": workers,
        "mean_delta_per_complete_table": comparison["mean_delta"],
        "net_source_bootstrap95": comparison["net_source_bootstrap95"],
        "source_sign_counts": {k: len(comparison[k + "_sources"])
                               for k in ("positive", "negative", "zero")},
        "large_hu_positive_sources": len(comparison["large_hu_positive_sources"]),
        "net_delta_sum_512_tables": totals["net"], "all_accounting_checks_passed": True,
        "independent_strength_evidence_passed": False, "online_admission": False,
        "post_confirmation_phases_executed": 0, "no_new_scores_worlds_tables_models_HTTP": True,
        "future_author_use": "本批现为已暴露开发证据，不可作为修订候选的新独立确认",
        "original_files": pins, "archive": {"path": str(archive), "pin": pin(archive),
            "uncompressed_pin": pins[str(paths[1])], "exact_decompression_verified": True},
        "raw_per_table_audits_archived_to_git": False,
    }
    save(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-READOUT-SUMMARY-014.json"), result)
    print(json.dumps({"complete": True, "mean_net": totals["net"] / 512,
                      "independent_strength_evidence_passed": False}))


if __name__ == "__main__":
    main()
