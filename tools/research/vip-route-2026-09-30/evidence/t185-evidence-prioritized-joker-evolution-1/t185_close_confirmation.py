"""T185独立确认：1024原桌全闭后一次读回，128来源聚类，不继承上线资格。"""

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
import argparse
import json
import random
from fractions import Fraction
from pathlib import Path
from common import HERE
import t185_close_development as dev
from t185_prepare_confirmation import PLAN, CONTRACT, background_priority, new_json, postprocess_lock, read_confirmation_plan, confirmation_worker_evidence
OUTPUT = _project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json")

def preflight(plan, plan_pin):
    """完整性/身份/物理牌山预检无任何积分提取；缺失/失败使全部确认未知。"""
    evidence, initial_hashes, wall_hashes, opponent_vectors = [], {}, {}, {}
    arms = [plan["parent"], plan["candidates"][0]]
    for index, root in enumerate(plan["roots"], 1):
        for rotation in plan["rotations"]:
            for arm_index, arm in enumerate(arms):
                directory = _project_file(_PROJECT_ROOT, HERE / "natural-confirmation" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}")
                start, start_pin = dev.read(directory / "START.json")
                closure, closure_pin = dev.read(directory / "CLOSURE.json")
                pairing, pairing_pin = dev.read(directory / "PAIRING-IDENTITY.json")
                label = f"原确认桌{index}/{rotation}/{arm_index}"
                for row in (start, closure):
                    dev.require(row.get("root") == root and row.get("rotation") == rotation and row.get("arm") == arm and
                                row.get("plan_pin") == plan_pin and row.get("confirmation_only") is True and
                                row.get("model_calls") == 0, label + "未绑定原计划/来源/策略/确认身份")
                dev.require(start.get("table_starts_reserved") == 1 and start.get("logical_clock_not_official_deadline") is True,
                            label + "启动声明不符")
                dev.require(closure.get("complete") is True and closure.get("failure") is None and
                            closure.get("source_stable") is True and closure.get("actual_table_starts") == 1 and
                            closure.get("focal_seat") == rotation and closure.get("normal_fallbacks_allowed") is False and
                            closure.get("deadline_or_strength_admission") is False, label + "原终态未完成/失败/漂移/降级")
                outcome = closure.get("outcome")
                dev.require(type(outcome) is dict and outcome.get("status") == "complete" and outcome.get("completed_hands") == 8 and
                            outcome.get("error_reason") is None and outcome.get("blocked_reason") is None,
                            label + "不是完整八单局")
                counts = outcome.get("runtime_counts")
                dev.require(type(counts) is dict and set(counts) == dev.RUNTIME_KEYS and
                            all(type(v) is int and v == 0 for v in counts.values()), label + "运行故障计数未知或非零")
                dev.require(type(closure.get("settlements")) is list and len(closure["settlements"]) == 8,
                            label + "结算分母不完整")
                capture = closure.get("capture")
                dev.require(type(capture) is dict and type(capture.get("terminal")) is dict and
                            all(capture["terminal"].get(k) is True for k in
                                ("terminal_valid", "closed", "verified", "store_calls_reconciled")) and
                            capture["terminal"].get("errors") == [], label + "输入捕获终态无效")
                dev.integer(closure.get("actual_focal_decisions"), "焦点决策数", 1)
                dev.integer(closure.get("actual_focal_score_calls"), "实际评分数", 1)
                dev.require((directory / "focal-decisions.jsonl.gz").is_file() and (directory / "views.jsonl.gz").is_file(),
                            label + "缺评分原件")
                dev.require(pairing_pin == closure.get("pairing_identity_pin") and pairing.get("root") == root and
                            pairing.get("rotation") == rotation and pairing.get("arm") == arm and pairing.get("evidence") ==
                            "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None", label + "实际装配映射原件不符")
                opponents = pairing.get("opponent_policy_ids_physical")
                dev.require(type(opponents) is list and len(opponents) == 4 and opponents[rotation] is None and
                            all(type(opponents[s]) is str and opponents[s] for s in range(4) if s != rotation) and
                            opponents == closure.get("opponent_policy_ids_physical") and
                            opponent_vectors.setdefault((index, rotation), opponents) == opponents, label + "父子实际三对手不同或身份未知")
                proofs = closure.get("pairing_proofs")
                dev.require(type(proofs) is list and len(proofs) == 8, label + "八单局配对证明缺失")
                for round_no, proof in enumerate(proofs, 1):
                    dev.require(type(proof.get("round_no")) is int and proof["round_no"] == round_no and
                                type(proof.get("dealer_seat")) is int and 0 <= proof["dealer_seat"] < 4 and
                                proof.get("export_matches_frozen_sampler") is True and
                                proof.get("teacher_only_not_policy_input") is True, label + "公开导出/冻结采样器证明无效")
                    wall = dev.sha256(proof.get("physical_wall_sha256"), "确认物理牌山")
                    initial = dev.sha256(proof.get("actual_initial_sha256"), "确认起手")
                    dev.require(wall_hashes.setdefault((index, round_no), wall) == wall, label + "同来源同单局实际物理牌山不相同")
                    if round_no == 1:
                        dev.require(proof["dealer_seat"] == 0 and initial_hashes.setdefault(index, initial) == initial,
                                    label + "所有臂/换座实际首局起手或初庄不同")
                evidence.append(dev.TableEvidence(index, rotation, arm_index, directory, start_pin, closure_pin, pairing_pin))
    dev.require(len(evidence) == 1024, "确认原完整桌分母不等于1024")
    return evidence

def account(settlements, seat, root_id):
    """先核原确认match_id，再仅在内存映射名称以复用既有分账；不改变结算或原件。

    兼容副本只把外层match_id由t185-confirmation换成原读回器要求的
    t185-development前缀，root_id、八局积分/番数/赢家/庄家全部原样。
    原确认身份已逐条严格核验，所有原字节仍由闭合文件清单绑定。
    """
    dev.require(all(row.get("match_id") == "t185-confirmation:" + root_id for row in settlements),
                "实际结算不是本来源确认运行")
    compatible = [{**row, "match_id": "t185-development:" + root_id} for row in settlements]
    return dev.account(compatible, seat, root_id)

def bootstrap_interval(cluster_totals):
    """128来源四座差和等权有放回20,000次，分母512桌；固定seed20261005。"""
    dev.require(len(cluster_totals) == 128 and all(type(v) is int for v in cluster_totals), "确认bootstrap分母须128来源")
    rng = random.Random(20261005)
    totals = sorted(sum(cluster_totals[rng.randrange(128)] for _ in range(128)) for _ in range(20000))
    def percentile(fraction):
        position = (len(totals) - 1) * fraction
        lower = position.numerator // position.denominator
        upper, weight = min(lower + 1, len(totals) - 1), position - lower
        return float((totals[lower] * (1 - weight) + totals[upper] * weight) / 512)
    return [percentile(Fraction(1, 40)), percentile(Fraction(39, 40))]

def summarize(plan, tables):
    """128母来源聚类子−父净分与机会分账；信号门和实际发布门分开。"""
    sources = []
    for index, root in enumerate(plan["roots"], 1):
        paired = []
        for rotation in plan["rotations"]:
            parent, child = tables[(index, rotation, 0)], tables[(index, rotation, 1)]
            dev.require(parent["opponent_policy_ids_physical"] == child["opponent_policy_ids_physical"] and
                        [p["physical_wall_sha256"] for p in parent["pairing_proofs"]] ==
                        [p["physical_wall_sha256"] for p in child["pairing_proofs"]], "父子实际对手/物理牌山不相同")
            delta = {key: child["account"][key] - parent["account"][key] for key in parent["account"]}
            dev.require(delta["net"] == delta["ordinary_hu_income"] + delta["large_hu_income"] + delta["payments"], "确认配对分账不相等")
            paired.append({"rotation": rotation, "parent": parent["account"], "child": child["account"], "delta": delta})
        sums = {key: sum(row["delta"][key] for row in paired) for key in paired[0]["delta"]}
        sources.append({"root_id": root["root_id"], "seed": root["seed"], "paired_tables": paired,
                        "four_seat_delta_sums": sums, "mean_delta": {key: value / 4 for key, value in sums.items()}})
    totals = [r["four_seat_delta_sums"]["net"] for r in sources]
    means = {key: sum(r["four_seat_delta_sums"][key] for r in sources) / 512 for key in sources[0]["mean_delta"]}
    interval = bootstrap_interval(totals)
    positive = [r["root_id"] for r in sources if r["four_seat_delta_sums"]["net"] > 0]
    negative = [r["root_id"] for r in sources if r["four_seat_delta_sums"]["net"] < 0]
    large_positive = [r["root_id"] for r in sources if r["four_seat_delta_sums"]["large_hu_income"] > 0]
    tail = [{"root_id": r["root_id"], "mean_delta": r["mean_delta"], "four_seat_net_delta_sum": r["four_seat_delta_sums"]["net"]}
            for r in sources]
    net_signal, opportunity = interval[0] > 0 and means['net'] >= 0.5, len(large_positive) >= 2
    return {"candidate_id": plan["selected_candidate_id"], "identity": plan["candidates"][0]["identity"],
        "independent_mother_sources": 128, "paired_complete_tables": 512, "sources": sources,
        "net_delta_sum_512_tables": sum(totals), "mean_delta": means, "net_source_bootstrap95": interval,
        "positive_sources": positive, "negative_sources": negative,
        "zero_sources": [r["root_id"] for r in sources if r["four_seat_delta_sums"]["net"] == 0],
        "large_hu_positive_sources": large_positive, "high_fan_cross_source_support": opportunity,
        "cumulative_high_fan_positive_sources": {str(t): [r["root_id"] for r in sources if
            r["four_seat_delta_sums"][f"own_hu_ge{t}_income"] > 0] for t in (8, 16, 32)},
        "positive_tail": sorted((r for r in tail if r["four_seat_net_delta_sum"] > 0),
                                key=lambda r: (-r["four_seat_net_delta_sum"], r["root_id"]))[:5],
        "negative_tail": sorted((r for r in tail if r["four_seat_net_delta_sum"] < 0),
                                key=lambda r: (r["four_seat_net_delta_sum"], r["root_id"]))[:5],
        "net_score_signal_gate_passed": net_signal, "opportunity_evidence_gate_passed": opportunity,
        "independent_strength_evidence_passed": net_signal,
        "strength_signal_is_not_online_admission": True}

def _readout(preflight_only=False):
    """所有原确认桌齐全才一次读积分，源pin再验稳定后排他新建确认闭合。"""
    dev.require(not OUTPUT.exists(), "确认闭合已存在，拒绝覆盖或重复查看")
    plan, plan_pin = read_confirmation_plan(verify_development_evidence=True)
    resource_files = confirmation_worker_evidence(plan, plan_pin)
    evidence = preflight(plan, plan_pin)
    dev.require(dev.pin(PLAN) == plan_pin, "确认预检期间计划漂移")
    if preflight_only:
        print(json.dumps({"status": "all_confirmation_original_terminals_ready_no_score_readout",
                          "planned_tables": 1024, "scores_extracted": False}, ensure_ascii=False))
        return
    files = {**resource_files, str(PLAN): plan_pin, str(CONTRACT): dev.pin(CONTRACT),
             str(Path(__file__).resolve()): dev.pin(Path(__file__).resolve())}
    tables = {}
    for table in evidence:
        start_path, closure_path, pairing_path = (table.directory / n for n in ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json"))
        dev.require(dev.pin(start_path) == table.start_pin and dev.pin(pairing_path) == table.pairing_pin, "预检后确认身份原件漂移")
        closure, current_pin = dev.read(closure_path)
        dev.require(current_pin == table.closure_pin, "预检后确认原终态漂移")
        dev.require(all(resource_files.get(str(path)) == expected for path, expected in
                        ((start_path, table.start_pin), (closure_path, table.closure_pin), (pairing_path, table.pairing_pin))),
                    "确认资源AFTER未绑定实际原桌元数据")
        files.update({str(start_path): table.start_pin, str(closure_path): table.closure_pin, str(pairing_path): table.pairing_pin})
        root = plan["roots"][table.index - 1]
        ledger, end = account(closure["settlements"], table.rotation, root["root_id"])
        dev.require(end == dev.seat_vector(closure["outcome"].get("final_scores"), "确认桌终分") and ledger["net"] == end[table.rotation] and
                    all(p["dealer_seat"] == s["settlement"]["dealer_seat"] for p, s in zip(closure["pairing_proofs"], closure["settlements"])),
                    "确认八局结算与终分/实际庄家不一致")
        # 共用已核实际评分小收据规则；输入捕获/操作数/原动作完全按原件读回。
        audit, pins = dev.score_receipts(table, closure, plan)
        dev.require(all(resource_files.get(path) == expected for path, expected in pins.items()),
                    "确认资源AFTER未绑定实际评分／捕获原件")
        files.update(pins)
        tables[(table.index, table.rotation, table.arm_index)] = {"root_id": root["root_id"], "rotation": table.rotation,
            "arm_index": table.arm_index, "account": ledger, "audit": audit, "final_scores_0_1_2_3": end,
            "pairing_proofs": closure["pairing_proofs"], "opponent_policy_ids_physical": closure["opponent_policy_ids_physical"]}
    comparison = summarize(plan, tables)
    dev.frozen(plan)
    dev.require(all(dev.pin(Path(path)) == expected for path, expected in files.items()), "确认读回期间原件漂移")
    # 原开发大图不按每桌复读；确认闭合前统一再验一次已绑定开发原证据。
    for path, expected in plan["development_evidence_files"].items():
        dev.require(dev.pin(Path(path)) == expected, "确认期间开发原证据漂移:" + path)
    result = {"schema": "t185-natural-confirmation-closed/1", "complete": True, "source_stable": True,
        "status": "independent_confirmation_complete_evidence_only", "source_kind": "simulation", "files": files,
        "parent_identity": plan["parent"]["identity"], "candidate_id": plan["selected_candidate_id"],
        "planned_table_instances": 1024, "actual_table_instances": len(tables), "completed_hand_instances": len(tables) * 8,
        "independent_mother_sources": 128, "actual_focal_decisions": sum(t["audit"]["decisions"] for t in tables.values()),
        "actual_focal_score_calls": sum(t["audit"]["actual_score_calls"] for t in tables.values()),
        "tables": list(tables.values()), "comparison": comparison, "bootstrap": plan["bootstrap"],
        "physical_wall_digest_public_export_verified": True, "actual_opponent_mapping_verified": True,
        "outcome_opponent_policy_id_coverage": all(t["audit"]["opponent_actual_identity_independently_exported"] for t in tables.values()),
        "net_score_signal_gate_passed": comparison["net_score_signal_gate_passed"],
        "opportunity_evidence_gate_passed": comparison["opportunity_evidence_gate_passed"],
        "independent_strength_evidence_passed": comparison["independent_strength_evidence_passed"],
        "deadline_admission": False, "runtime_reliability_admission": False, "release_admission": False,
        "experimental_free_match_admission": False, "human_release_review_required": True,
        "development_dispatch_closed_pin": plan["development_dispatch_closed_pin"],
        "actual_successful_workers": [0, 1], "max_cpu_workers": 2, "partition": "worker=ordinal%2",
        "confirmation_resource_receipts_verified": True, "common_postprocess_lock_held_during_simulation": False,
        "new_models_scores_worlds_tables": 0}
    new_json(OUTPUT, result)
    print(json.dumps({"complete": True, "output": str(OUTPUT),
                      "independent_strength_evidence_passed": comparison["independent_strength_evidence_passed"],
                      "release_admission": False}, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    background_priority()
    with postprocess_lock("confirmation_readout"):
        _readout(args.preflight_only)
