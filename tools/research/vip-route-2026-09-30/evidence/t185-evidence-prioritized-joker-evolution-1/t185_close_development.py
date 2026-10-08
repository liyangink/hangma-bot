"""T182 完整自然桌开发读回；全批终态齐全前不提取积分，不授确认或上线。"""
from __future__ import annotations

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
import ctypes
import fcntl
import gzip
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter
from hangma_bot.policy.action_value import CANDIDATE_KIND
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_NAME
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1/DEVELOPMENT-PLAN.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1/DEVELOPMENT-READOUT-CONTRACT.md')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1/DEVELOPMENT-CLOSED.json')
PARENT_SHA = "2a59cbb18aefa3d24aadf0b3df70f5a4359c204b96a3f0dc208f77d53c196f30"
BOOTSTRAP_SEED = 20261005
BOOTSTRAP_REPLICATES = 20000
RUNTIME_KEYS = {"timeouts", "illegal_choices", "fallbacks", "auto_actions", "audit_missing"}
ACCOUNT_KEYS = (
    "net", "ordinary_hu_income", "large_hu_income", "payments", "hands", "own_hu",
    "ordinary_hu", "large_hu", "own_hu_ge8", "own_hu_ge16", "own_hu_ge32",
    "own_hu_ge8_income", "own_hu_ge16_income", "own_hu_ge32_income", "other_first_hu", "draws",
)


@dataclass(frozen=True)
class TableEvidence:
    """通过全批终态预检的原桌证据；还没有提取积分或生成统计。"""

    index: int  # 计划母来源的1起始序号；不是新的独立样本身份
    rotation: int  # 焦点物理座位0—3；逻辑席位i映射(i+rotation)%4
    arm_index: int  # 0为固定S02，1—3为计划顺序的候选
    directory: Path  # 该原桌独有目录，不允许补跑覆盖
    start_pin: dict  # START原字节的SHA及字节数
    closure_pin: dict  # CLOSURE原字节的SHA及字节数
    pairing_pin: dict  # 本桌运行时实际对手映射原件的SHA及字节数，不是事前计划文件


def require(condition, message):
    """缺失或矛盾时显式停止；不依赖可能被python -O关闭的assert。"""
    if not condition:
        raise ValueError(message)


def pin(path):
    """流式核原文件SHA及实际字节数；不读取牌山或生成任何新样本。"""
    digest, size = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"sha256": digest.hexdigest(), "bytes": size}


def _pairs(items):
    """重复JSON键是身份歧义，拒绝最后值覆盖前值。"""
    result = {}
    for key, value in items:
        require(key not in result, "JSON含重复键")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("JSON含非有限常量")


def _float(value):
    result = float(value)
    require(math.isfinite(result), "JSON含溢出非有限浮点数")
    return result


def decode(raw):
    """严格解析原导出JSON；非有限数、重复键和格式错误原样拒绝。"""
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)


def read(path):
    """读取小型原终态/计划；限制单文件64MiB，错误不改原文件。"""
    with Path(path).open("rb") as stream:
        raw = stream.read(67108865)
    require(len(raw) <= 67108864, "计划或原终态JSON超64MiB")
    return decode(raw), {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def integer(value, name, minimum=None):
    """计数及积分只认整数，拒绝bool和未知null。"""
    require(type(value) is int and (minimum is None or value >= minimum), name + "缺合法整数")
    return value


def sha256(value, name):
    """公开摘要须为64位小写十六进制，未知摘要不得参与相等比较。"""
    require(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
            name + "缺合法SHA256")
    return value


def seat_vector(value, name):
    """积分向量固定物理座位0—3，未知不能当0。"""
    require(type(value) is list and len(value) == 4, name + "缺四座向量")
    return [integer(v, name) for v in value]


def frozen(plan):
    """准备到读回结束核全部生产/研究源码与输入，不继承旧源码结果。"""
    require(type(plan.get("files")) is dict and type(plan.get("source_manifest")) is dict,
            "缺冻结文件或生产闭包")
    for path, expected in plan["files"].items():
        require(pin(Path(path)) == expected, "冻结文件漂移:" + path)
    for path, expected in plan["source_manifest"].items():
        require(pin(_project_file(_PROJECT_ROOT, ROOT / path)) == expected, "生产闭包漂移:" + path)


def validate_plan(plan):
    """固定32来源×四换座×八单局，候选与父代同规则、限深和480万操作。"""
    require(plan.get("schema") == "t185-natural-development/1", "开发计划版本不符")
    require(plan.get("rotations") == [0, 1, 2, 3] and plan.get("rounds") == 8,
            "必须四换座及完整八单局")
    require(plan.get("initial_dealer_physical") == 0 and
            seat_vector(plan.get("initial_scores_0_1_2_3"), "初分") == [0, 0, 0, 0], "初庄/初分不符")
    require(plan.get("no_early_score_peeking_or_additional_roots") is True and
            plan.get("max_independent_confirmed_candidates") == 1, "查看或选择上限不符")
    roots, candidates = plan.get("roots"), plan.get("candidates")
    require(type(roots) is list and len(roots) == 32, "必须32个原母来源")
    require(type(candidates) is list and 1 <= len(candidates) <= 3, "必须1—3个开发候选")
    require(len({r["root_id"] for r in roots}) == 32 and len({r["seed"] for r in roots}) == 32,
            "母来源/seed重复")
    for root in roots:
        integer(root["seed"], "牌山seed", 0)
        require(isinstance(root["root_id"], str) and root["root_id"], "母来源身份缺失")
        require(type(root.get("opponent_types_logical_1_2_3")) is list and
                len(root["opponent_types_logical_1_2_3"]) == 3 and
                all(t in ("normal_v0", "automatic_like", "r18") for t in root["opponent_types_logical_1_2_3"]),
                "三名逻辑对手组成不符")
    planned = 32 * 4 * (1 + len(candidates))
    require(plan.get("planned_table_instances") == planned <= 512 and
            plan.get("maximum_new_complete_table_instances") == 512, "完整桌预算不符")
    arms = [plan["parent"], *candidates]
    require(arms[0]["identity"]["source_sha256"] == PARENT_SHA, "父代不是固定S02")
    require(len({a["identity"]["candidate_id"] for a in arms}) == len(arms), "候选身份重复或等于父代")
    params = arms[0]["identity"]["params"]
    require(params["max_operations"] == 4800000 and params["projection_limits"]["max_replacement_depth"] == 1,
            "父代操作/补牌限深不符")
    for arm in arms:
        identity = arm["identity"]
        require(identity["params"] == params, "父子规则或执行限额不同")
        require(pin(Path(arm["source_file"]))["sha256"] == identity["source_sha256"], "公式身份漂移")
    required = (Path(__file__).resolve(), CONTRACT, _project_file(_PROJECT_ROOT, HERE / "t185_run_development.py"), _project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"))
    require(all(str(p) in plan["files"] for p in required), "计划未冻结读回器/合同/运行器/组成")
    for path in ("src/hangma_bot/simulation/engine.py", "src/hangma_bot/simulation/shuffle.py",
                 "src/hangma_bot/offline/qualifier_opponents.py", "src/hangma_bot/offline/vip_route_development.py"):
        require(path in plan["source_manifest"], "配对生成实现未冻结:" + path)
    compositions, _ = read(_project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"))
    require(compositions["pools"]["development"] == roots, "计划来源/对手不等于冻结开发组成")
    development_seeds = {r["seed"] for r in roots}
    for name in ("diagnostic_fresh", "confirmation"):
        require(not development_seeds & {r["seed"] for r in compositions["pools"][name]}, "开发与其他样本seed交叉")


def preflight(plan, plan_pin):
    """先核全部原桌终态及身份，尚不提取积分；任何缺桌/失败使整批未知。"""
    tables, arms, initial_hashes, wall_hashes, opponent_vectors = [], [plan["parent"], *plan["candidates"]], {}, {}, {}
    for index, root in enumerate(plan["roots"], 1):
        for rotation in plan["rotations"]:
            for arm_index, arm in enumerate(arms):
                directory = _project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}")
                start, start_pin = read(directory / "START.json")
                closure, closure_pin = read(directory / "CLOSURE.json")
                pairing, pairing_pin = read(directory / "PAIRING-IDENTITY.json")
                label = f"原桌{index}/{rotation}/{arm_index}"
                require(start.get("plan_pin") == plan_pin, label + "未绑定原计划")
                for record in (start, closure):
                    require(record.get("root") == root and record.get("rotation") == rotation and
                            record.get("arm") == arm, label + "来源/座位/公式身份不符")
                    require(record.get("model_calls") == 0, label + "意外模型费用")
                require(start.get("table_starts_reserved") == 1 and
                        start.get("logical_clock_not_official_deadline") is True, label + "启动声明不符")
                require(closure.get("complete") is True and closure.get("failure") is None and
                        closure.get("source_stable") is True, label + "未完成或原运行失败/漂移")
                require(closure.get("normal_fallbacks_allowed") is False and
                        closure.get("deadline_or_strength_admission") is False and
                        closure.get("focal_seat") == rotation, label + "回退/准入/焦点字段不符")
                require(closure.get("actual_table_starts") == 1, label + "启动次数不符")
                require(pairing_pin == closure.get("pairing_identity_pin"), label + "实际配对映射原件未绑定")
                require(pairing.get("root") == root and pairing.get("rotation") == rotation and
                        pairing.get("arm") == arm and pairing.get("evidence") ==
                        "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None",
                        label + "实际配对映射来源不符")
                opponents = pairing.get("opponent_policy_ids_physical")
                require(type(opponents) is list and len(opponents) == 4 and opponents[rotation] is None and
                        all(type(opponents[s]) is str and opponents[s] for s in range(4) if s != rotation) and
                        opponents == closure.get("opponent_policy_ids_physical"), label + "实际对手四席身份不完整")
                require(opponent_vectors.setdefault((index, rotation), opponents) == opponents,
                        label + "父子实际对手映射不同")
                proofs = closure.get("pairing_proofs")
                require(type(proofs) is list and len(proofs) == 8, label + "同牌山证明不足八单局")
                for round_no, proof in enumerate(proofs, 1):
                    require(type(proof.get("round_no")) is int and proof["round_no"] == round_no and type(proof.get("dealer_seat")) is int and
                            0 <= proof["dealer_seat"] < 4 and proof.get("export_matches_frozen_sampler") is True and
                            proof.get("teacher_only_not_policy_input") is True, label + "公开导出/冻结采样器证明无效")
                    wall_hash = sha256(proof.get("physical_wall_sha256"), "实际物理牌山")
                    initial_hash = sha256(proof.get("actual_initial_sha256"), "实际单局起手")
                    wall_key = (index, round_no)
                    require(wall_hashes.setdefault(wall_key, wall_hash) == wall_hash, label + "同源同单局物理牌山不相同")
                    if round_no == 1:
                        require(proof["dealer_seat"] == 0 and initial_hashes.setdefault(index, initial_hash) == initial_hash,
                                label + "所有臂/换座的实际初庄或首局起手不相同")
                outcome, capture = closure.get("outcome"), closure.get("capture")
                require(type(outcome) is dict and outcome.get("status") == "complete" and
                        outcome.get("completed_hands") == 8 and outcome.get("blocked_reason") is None and
                        outcome.get("error_reason") is None, label + "不是完整八单局")
                counts = outcome.get("runtime_counts")
                require(type(counts) is dict and set(counts) == RUNTIME_KEYS and
                        all(type(v) is int and v == 0 for v in counts.values()), label + "故障计数未知或非零")
                require(type(closure.get("settlements")) is list and len(closure["settlements"]) == 8,
                        label + "结算分母不足")
                require(type(capture) is dict and type(capture.get("terminal")) is dict and
                        all(capture["terminal"].get(k) is True for k in
                            ("terminal_valid", "closed", "verified", "store_calls_reconciled")) and
                        capture["terminal"].get("errors") == [], label + "输入捕获终态无效")
                integer(closure.get("actual_focal_decisions"), label + "焦点决策数", 1)
                integer(closure.get("actual_focal_score_calls"), label + "实际评分数", 1)
                require((directory / "views.jsonl.gz").is_file() and
                        (directory / "focal-decisions.jsonl.gz").is_file(), label + "缺评分原件")
                tables.append(TableEvidence(index, rotation, arm_index, directory, start_pin, closure_pin, pairing_pin))
    require(len(tables) == plan["planned_table_instances"], "全批原桌分母不符")
    return tables


def account(settlements, seat, root_id):
    """八份生产公开结算分账；高番累计阈值不是互斥收入，庄闲按每局实际庄家。"""
    overall = dict.fromkeys(ACCOUNT_KEYS, 0)
    dealer, non_dealer = overall.copy(), overall.copy()
    before = [0, 0, 0, 0]
    for round_no, exported in enumerate(settlements, 1):
        require(exported.get("evidence") == "public_export_hand_settlement" and
                exported.get("root_id") == root_id and exported.get("match_id") == "t185-development:" + root_id and
                exported.get("initial_dealer_physical") == 0 and exported.get("round_no") == round_no and
                exported.get("observation_scope") == "completed_hand_only", "结算导出身份或顺序不符")
        s = exported["settlement"]
        require(s.get("coverage") == "settlement_only" and s.get("round_no") == round_no, "结算公开结构不符")
        start, end, delta = (seat_vector(s.get(k), k) for k in ("scores_before", "scores_after", "score_delta"))
        require(start == before and sum(delta) == 0 and
                all(start[i] + delta[i] == end[i] for i in range(4)), "单局积分不守恒或前后不连续")
        dealer_seat = integer(s.get("dealer_seat"), "实际庄家", 0)
        require(dealer_seat < 4 and (round_no != 1 or dealer_seat == 0), "实际初庄或庄家座位不符")
        one = dict.fromkeys(ACCOUNT_KEYS, 0)
        one.update(net=delta[seat], hands=1)
        require(type(s.get("is_draw")) is bool, "流局状态未知")
        if s["is_draw"]:
            require(delta == [0, 0, 0, 0] and s.get("winner_seat") is None, "流局结算矛盾")
            one["draws"] = 1
        else:
            winner, fan = integer(s.get("winner_seat"), "赢家", 0), integer(s.get("fan"), "实际番数", 1)
            require(winner < 4 and delta[winner] > 0 and
                    all(delta[i] <= 0 for i in range(4) if i != winner), "赢家/支付方向不符")
            if winner == seat:
                ordinary = fan < 4
                one["own_hu"] = 1
                one["ordinary_hu" if ordinary else "large_hu"] = 1
                one["ordinary_hu_income" if ordinary else "large_hu_income"] = delta[seat]
                for threshold in (8, 16, 32):
                    if fan >= threshold:
                        one[f"own_hu_ge{threshold}"] = 1
                        one[f"own_hu_ge{threshold}_income"] = delta[seat]
            else:
                one.update(payments=delta[seat], other_first_hu=1)
        require(one["net"] == one["ordinary_hu_income"] + one["large_hu_income"] + one["payments"], "积分分账不相等")
        for ledger in (overall, dealer if dealer_seat == seat else non_dealer):
            for key in ACCOUNT_KEYS:
                ledger[key] += one[key]
        before = end
    result = {**overall, **{"dealer_" + k: v for k, v in dealer.items()},
              **{"non_dealer_" + k: v for k, v in non_dealer.items()}}
    require(overall["hands"] == 8 and overall["own_hu"] + overall["other_first_hu"] + overall["draws"] == 8,
            "八单局终局分账不完整")
    return result, before


LEGACY_INFORMATION = "评分兼容视图[legacy-pass-neutral-v1]：可信过牌恢复旧中性基线；原始规则事实不改写"
CATCH_INFORMATION = "抓打圈生效：排序仅在规则允许的硬约束候选内进行"
NORMAL_INFORMATION = frozenset((LEGACY_INFORMATION, CATCH_INFORMATION))
R18_DYNAMIC_ID = CANDIDATE_KIND + ":" + R18_INTEGRATED_POSITIVE_V2_NAME
KNOWN_TYPES = ("automatic_like", "normal_v0", "r18")


def decision_metadata(table, closure, plan):
    """焦点严格无降级；对手只按冻结物理对应类型接受精确信息和对象ID格式。"""
    seat, root = table.rotation, plan["roots"][table.index - 1]
    arm = [plan["parent"], *plan["candidates"]][table.arm_index]
    pairing, pairing_pin = read(table.directory / "PAIRING-IDENTITY.json")
    require(pairing_pin == table.pairing_pin == closure.get("pairing_identity_pin") and
            pairing.get("root") == root and pairing.get("rotation") == seat and pairing.get("arm") == arm and
            pairing.get("evidence") == "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None",
            "实际PAIRING原件/来源/臂/换座不符")
    actual_ids = pairing.get("opponent_policy_ids_physical")
    kinds = root.get("opponent_types_logical_1_2_3")
    require(type(kinds) is list and len(kinds) == 3 and all(k in KNOWN_TYPES for k in kinds), "未知对手装配类型")
    require(type(actual_ids) is list and len(actual_ids) == 4 and actual_ids[seat] is None and
            actual_ids == closure.get("opponent_policy_ids_physical"), "实际三对手物理映射不符")
    for logical, kind in enumerate(kinds, 1):
        declaration = actual_ids[(logical + seat) % 4]
        prefix = f"H{logical}:" if kind == "r18" else f"Q{logical}:{kind}:"
        require(type(declaration) is str and declaration.startswith(prefix), "实际对手declaration类型/逻辑座位不符")
        sha256(declaration[len(prefix):], "实际对手declaration摘要")
    focal, opponent_ids, all_ids = {}, {}, set()
    notes = {k: Counter() for k in KNOWN_TYPES}
    missing, totals, diagnostic_decisions = Counter(), Counter(), Counter()
    for d in closure["outcome"]["decisions"]:
        decision_id = d["decision_id"]
        require(type(decision_id) is str and decision_id and decision_id not in all_ids, "驱动决策标识空或重复")
        all_ids.add(decision_id)
        require(d.get("legal") is True and d.get("fallback_reason") is None, "原动作非法或发生回退")
        other = integer(d.get("seat"), "驱动座位", 0)
        require(other < 4 and type(d.get("window_key")) is dict and d["window_key"].get("seat") == other,
                "驱动窗口座位不符")
        reasons = d.get("degraded_reasons")
        require(type(reasons) is list and all(type(r) is str for r in reasons), "驱动诊断字段未知")
        if other == seat:
            require(reasons == [], "焦点含降级或信息诊断，拒绝")
            require(d.get("policy_id") == "vip:" + arm["identity"]["candidate_id"], "驱动焦点策略身份不符")
            focal[decision_id] = d
        else:
            logical = (other - seat) % 4
            kind, dynamic = kinds[logical - 1], d.get("policy_id")
            totals[kind] += 1
            if kind == "normal_v0":
                require(dynamic is None, "冻结正常V0不应伪造对象policy_id")
                require(len(reasons) == len(set(reasons)) and set(reasons) <= NORMAL_INFORMATION,
                        "正常V0含未知/重复诊断或真正降级")
            elif kind == "automatic_like":
                require(dynamic is None and reasons == [], "冻结自动对手对象ID/诊断不符")
            else:
                require(dynamic == R18_DYNAMIC_ID and reasons == [], "R18动态对象ID未知/缺失或含降级")
            if dynamic is None:
                missing[kind] += 1
            if reasons:
                diagnostic_decisions[kind] += 1
                notes[kind].update(reasons)
            opponent_ids.setdefault(logical, set()).add(dynamic)
    audit = {"opponent_decisions_by_type": {k: totals[k] for k in KNOWN_TYPES},
             "opponent_compatibility_diagnostic_decisions_by_type": {k: diagnostic_decisions[k] for k in KNOWN_TYPES},
             "opponent_compatibility_diagnostic_counts_by_type": {k: dict(sorted(notes[k].items())) for k in KNOWN_TYPES},
             "opponent_object_policy_id_missing_counts_by_type": {k: missing[k] for k in KNOWN_TYPES},
             "opponent_pairing_declaration_ids_logical_1_2_3": {str(i): actual_ids[(i + seat) % 4] for i in range(1, 4)},
             "actual_pairing_mapping_independently_verified": True,
             "focal_diagnostic_count": 0, "unknown_diagnostic_count": 0,
             "schema_repair_only_no_original_record_rewritten": True}
    return focal, opponent_ids, audit

def input_receipt_fields(receipt, number, limit):
    """原评分前输入收据严格检查；负例复用这个真实调用接缝，无新输入保存。"""
    require(type(receipt) is dict and receipt.get("store_call_no") == number and
            receipt.get("saved_before_score") is True and receipt.get("error") is None, "评分前输入未真实保存")
    sha, size = receipt.get("view_sha256"), integer(receipt.get("json_bytes"), "输入字节数", 1)
    sha256(sha, "输入视图")
    require(size <= limit, "输入字节数超限")
    return sha, size

def aggregate_audits(audits):
    """汇总真实信息诊断/对象ID缺失笔数；不读取积分或合并未知诊断。"""
    simple = ("opponent_decisions_by_type", "opponent_compatibility_diagnostic_decisions_by_type",
              "opponent_object_policy_id_missing_counts_by_type")
    result = {key: {kind: 0 for kind in KNOWN_TYPES} for key in simple}
    notes = {kind: Counter() for kind in KNOWN_TYPES}
    for audit in audits:
        for key in simple:
            for kind in KNOWN_TYPES:
                result[key][kind] += integer(audit[key][kind], key, 0)
        for kind in KNOWN_TYPES:
            notes[kind].update(audit["opponent_compatibility_diagnostic_counts_by_type"][kind])
    result["opponent_compatibility_diagnostic_counts_by_type"] = {k: dict(sorted(notes[k].items())) for k in KNOWN_TYPES}
    return result

def score_receipts(table, closure, plan):
    """从评分gzip核实际次数、输入小收据和最终实际动作；不重评分/重构输入。"""
    seat, root = table.rotation, plan["roots"][table.index - 1]
    arm = [plan["parent"], *plan["candidates"]][table.arm_index]
    outcome = closure["outcome"]
    focal, opponent_ids, diagnostics = decision_metadata(table, closure, plan)
    seen, views, stored, repeated, byte_total, operations = set(), {}, 0, 0, 0, []
    decision_path = table.directory / "focal-decisions.jsonl.gz"
    limit = plan["capture_limits"]["max_view_json_bytes"]
    with gzip.open(decision_path, "rb") as stream:
        while raw := stream.readline(limit + 513):
            byte_total += len(raw)
            require(len(raw) <= limit + 512 and byte_total <= 2 * plan["capture_limits"]["max_total_json_bytes"],
                    "评分小收据超预登记读取上界")
            row = decode(raw)
            did = row["decision_id"]
            require(did not in seen and did in focal, "评分决策重复或不在实际动作中")
            seen.add(did)
            require(row.get("root_id") == root["root_id"] and row.get("rotation") == seat and
                    row.get("arm") == table.arm_index and row.get("source_identity") == arm["identity"]["candidate_id"] and
                    row.get("seat") == seat and row.get("focal_vip") is True and
                    row.get("policy_id") == focal[did]["policy_id"] and row.get("window_key") == focal[did]["window_key"],
                    "评分收据来源/窗口/策略身份不符")
            require(row.get("status") == "chosen" and row.get("c_self_scored") is True and
                    row.get("degraded_reasons") == [] and row.get("scoring_cumulative_failed_calls") == 0 and
                    row.get("selected_action_key") == focal[did]["action_key"], "评分失败/降级或实际动作不符")
            calls = row.get("scoring_calls")
            require(type(calls) is list and len(calls) == 1, "每窗实际评分不是恰一次")
            call = calls[0]
            number = len(seen)
            require(call.get("call_no") == number and call.get("status") == "SCORED" and
                    call.get("actual_score_calls") == 1 and call.get("score_completed") is True and
                    call.get("full_legal_keys") is True and call.get("cumulative_failed_calls") == 0,
                    "实际评分次数/完整性不符")
            op = integer(call.get("candidate_operations"), "实际操作数", 1)
            require(op <= arm["identity"]["params"]["max_operations"], "评分超工作量")
            operations.append(op)
            legal, scored = row["legal_action_keys"], call["scored_action_keys"]
            require(len(legal) == len(set(legal)) == len(scored) == len(set(scored)) and set(legal) == set(scored),
                    "评分合法根集合不完整")
            ranked = row.get("candidates")
            require(type(ranked) is list and len(ranked) == len(legal), "完整排名条数不符")
            require({e.get("action_key") for e in ranked} == set(legal) and
                    [e.get("rank") for e in ranked] == list(range(1, len(legal) + 1)), "完整排名键/序号不符")
            require(all(type(e.get("score")) in (int, float) and math.isfinite(e["score"]) for e in ranked), "排名含非有限或非数字评分")
            require(ranked[0]["action_key"] == row["selected_action_key"], "实际动作不是排名第一")
            receipt = call["input_capture"]
            sha, size = input_receipt_fields(receipt, number, limit)
            if sha in views:
                require(receipt.get("status") == "deduplicated" and views[sha] == size, "输入去重收据矛盾")
                repeated += 1
            else:
                require(receipt.get("status") == "stored", "首份输入未保存")
                views[sha] = size
                stored += 1
    count = len(seen)
    require(seen == set(focal) and count == closure["actual_focal_decisions"] == closure["actual_focal_score_calls"],
            "实际动作/焦点决策/评分次数分母不一致")
    capture, terminal = closure["capture"], closure["capture"]["terminal"]
    require(capture.get("store_calls") == count and capture.get("unique_views_saved") == stored and
            capture.get("deduplicated_calls") == repeated and capture.get("failed_store_calls") == 0 and
            capture.get("gzip_write_result_uncertain_attempts") == 0 and terminal.get("verified_unique_views") == stored and
            capture.get("unique_json_bytes_saved") == sum(views.values()), "输入捕获计数/字节数未对账")
    views_path = table.directory / "views.jsonl.gz"
    capture_pin = pin(views_path)
    require(capture_pin["sha256"] == terminal.get("compressed_sha256") and
            capture_pin["bytes"] == terminal.get("observed_compressed_bytes"), "原输入压缩文件与核验终态不一致")
    require(stored <= plan["capture_limits"]["max_unique_views"] and
            sum(views.values()) <= plan["capture_limits"]["max_total_json_bytes"], "输入捕获超限")
    return {**diagnostics, "decisions": count, "actual_score_calls": count, "unique_views": stored,
            "maximum_operations": max(operations),
            "opponent_policy_ids_logical_1_2_3": {str(i): sorted(opponent_ids.get(i, set()), key=lambda v: "" if v is None else v)
                                                      for i in range(1, 4)},
            "opponent_actual_identity_independently_exported": all(
                opponent_ids.get(i) and None not in opponent_ids[i] for i in range(1, 4))}, {
                str(decision_path): pin(decision_path), str(views_path): capture_pin}


def bootstrap_interval(cluster_totals):
    """固定共同重采样索引：32母来源有放回20,000次，百分位线性插值95%区间。"""
    require(len(cluster_totals) == 32 and all(type(v) is int for v in cluster_totals), "bootstrap须32来源四座分差和")
    rng = random.Random(BOOTSTRAP_SEED)
    totals = sorted(sum(cluster_totals[rng.randrange(32)] for _ in range(32))
                    for _ in range(BOOTSTRAP_REPLICATES))
    def percentile(fraction):
        position = (len(totals) - 1) * fraction
        lower = position.numerator // position.denominator
        weight = position - lower
        upper = min(lower + 1, len(totals) - 1)
        return float((totals[lower] * (1 - weight) + totals[upper] * weight) / 128)
    return [percentile(Fraction(1, 40)), percentile(Fraction(39, 40))]


def comparisons(plan, tables):
    """先做完整桌配对差，再四座均值聚类；高番累计阈值不重复加到净积分。"""
    arms, result = [plan["parent"], *plan["candidates"]], []
    for arm_index, arm in enumerate(arms[1:], 1):
        sources = []
        for index, root in enumerate(plan["roots"], 1):
            paired = []
            for rotation in plan["rotations"]:
                parent, child = tables[(index, rotation, 0)], tables[(index, rotation, arm_index)]
                require(parent["pairing"] == child["pairing"], "父子同源/牌山/初庄/对手配对不符")
                require([p["physical_wall_sha256"] for p in parent["pairing_proofs"]] ==
                        [p["physical_wall_sha256"] for p in child["pairing_proofs"]], "父子八单局物理牌山摘要不同")
                delta = {key: child["account"][key] - parent["account"][key] for key in parent["account"]}
                require(delta["net"] == delta["ordinary_hu_income"] + delta["large_hu_income"] + delta["payments"],
                        "配对净分差无法分账")
                paired.append({"rotation": rotation, "parent": parent["account"], "child": child["account"], "delta": delta})
            sums = {key: sum(row["delta"][key] for row in paired) for key in paired[0]["delta"]}
            sources.append({"root_id": root["root_id"], "seed": root["seed"], "paired_tables": paired,
                            "four_seat_delta_sums": sums, "mean_delta": {key: value / 4 for key, value in sums.items()}})
        totals = [row["four_seat_delta_sums"]["net"] for row in sources]
        means = {key: sum(row["four_seat_delta_sums"][key] for row in sources) / 128 for key in sources[0]["mean_delta"]}
        positive = [r["root_id"] for r in sources if r["four_seat_delta_sums"]["net"] > 0]
        negative = [r["root_id"] for r in sources if r["four_seat_delta_sums"]["net"] < 0]
        large_positive = [r["root_id"] for r in sources if r["four_seat_delta_sums"]["large_hu_income"] > 0]
        tail = [{"root_id": r["root_id"], "mean_delta": r["mean_delta"],
                 "four_seat_net_delta_sum": r["four_seat_delta_sums"]["net"]} for r in sources]
        result.append({"candidate_id": arm["identity"]["candidate_id"], "identity": arm["identity"], "label": arm["label"],
            "independent_mother_sources": 32, "paired_complete_tables": 128, "sources": sources,
            "net_delta_sum_128_tables": sum(totals),
            "mean_delta": means, "net_source_bootstrap95": bootstrap_interval(totals),
            "positive_sources": positive, "negative_sources": negative,
            "zero_sources": [r["root_id"] for r in sources if r["four_seat_delta_sums"]["net"] == 0],
            "large_hu_positive_sources": large_positive, "high_fan_cross_source_support": len(large_positive) >= 2,
            "cumulative_high_fan_positive_sources": {
                str(t): [r["root_id"] for r in sources if r["four_seat_delta_sums"][f"own_hu_ge{t}_income"] > 0]
                for t in (8, 16, 32)},
            "positive_tail": sorted((r for r in tail if r["four_seat_net_delta_sum"] > 0),
                                    key=lambda r: (-r["four_seat_net_delta_sum"], r["root_id"]))[:5],
            "negative_tail": sorted((r for r in tail if r["four_seat_net_delta_sum"] < 0),
                                    key=lambda r: (r["four_seat_net_delta_sum"], r["root_id"]))[:5],
            "development_selection_eligible": sum(totals) > 0 and len(positive) >= 2,
            "confirmation_admission": False, "strength_admission": False, "release_admission": False})
    return result


def _readout(preflight_only=False):
    """全批核完才唯一新建DEVELOPMENT-CLOSED；不完整/失真时退出且不写成绩。"""
    require(not OUTPUT.exists(), "开发闭合已存在，拒绝覆盖或重复查看")
    plan, plan_pin = read(PLAN)
    validate_plan(plan)
    frozen(plan)
    evidence = preflight(plan, plan_pin)
    require(pin(PLAN) == plan_pin, "预检期间原计划漂移")
    if preflight_only:
        print(json.dumps({"status": "all_original_terminals_ready_no_score_readout", "planned_tables": len(evidence),
                          "scores_extracted": False, "confirmation_admission": False}, ensure_ascii=False))
        return
    files = {str(PLAN): plan_pin, str(Path(__file__).resolve()): pin(Path(__file__).resolve()), str(CONTRACT): pin(CONTRACT)}
    tables = {}
    for table in evidence:
        start_path, closure_path = table.directory / "START.json", table.directory / "CLOSURE.json"
        pairing_path = table.directory / "PAIRING-IDENTITY.json"
        require(pin(start_path) == table.start_pin, "全批预检后START漂移")
        closure, current_pin = read(closure_path)
        require(current_pin == table.closure_pin, "全批预检后CLOSURE漂移")
        require(pin(pairing_path) == table.pairing_pin, "全批预检后实际配对映射漂移")
        files.update({str(start_path): table.start_pin, str(closure_path): table.closure_pin, str(pairing_path): table.pairing_pin})
        root = plan["roots"][table.index - 1]
        ledger, end = account(closure["settlements"], table.rotation, root["root_id"])
        require(all(proof["dealer_seat"] == exported["settlement"]["dealer_seat"]
                    for proof, exported in zip(closure["pairing_proofs"], closure["settlements"])),
                "公开实际起手庄家与结算庄家不同")
        require(end == seat_vector(closure["outcome"].get("final_scores"), "桌终分") and ledger["net"] == end[table.rotation],
                "八局结算与四座桌终分不一致")
        audit, pins = score_receipts(table, closure, plan)
        files.update(pins)
        tables[(table.index, table.rotation, table.arm_index)] = {
            "root_id": root["root_id"], "rotation": table.rotation, "arm_index": table.arm_index,
            "account": ledger, "audit": audit, "final_scores_0_1_2_3": end,
            "pairing_proofs": closure["pairing_proofs"],
            "pairing": {"root_id": root["root_id"], "seed": root["seed"], "initial_dealer_physical": 0,
                "initial_scores_0_1_2_3": [0, 0, 0, 0], "rounds": 8,
                "opponent_types_logical_1_2_3": root["opponent_types_logical_1_2_3"],
                "opponent_policy_ids_physical": closure["opponent_policy_ids_physical"],
                "logical_to_physical_0_1_2_3": [(i + table.rotation) % 4 for i in range(4)]}}
    candidates = comparisons(plan, tables)
    eligible = sorted((r for r in candidates if r["development_selection_eligible"]),
                      key=lambda r: (-r["net_delta_sum_128_tables"], r["candidate_id"]))
    selected = None if not eligible else eligible[0]["candidate_id"]
    frozen(plan)
    require(all(pin(Path(path)) == expected for path, expected in files.items()), "读回期间原件漂移")
    result = {"schema": "t185-natural-development-closed/1", "complete": True,
        "status": "development_complete_not_confirmed", "files": files, "source_stable": True,
        "source_kind": "simulation", "parent_identity": plan["parent"]["identity"],
        "planned_table_instances": plan["planned_table_instances"], "actual_table_instances": len(tables),
        "completed_hand_instances": len(tables) * 8, "independent_mother_sources": 32,
        "actual_focal_decisions": sum(t["audit"]["decisions"] for t in tables.values()),
        "actual_focal_score_calls": sum(t["audit"]["actual_score_calls"] for t in tables.values()),
        "tables": list(tables.values()), "candidates": candidates,
        "opponent_compatibility_audit": aggregate_audits([t["audit"] for t in tables.values()]),
        "selected_candidate_id_for_confirmation_preparation": selected,
        "selection_is_development_screen_only": True,
        "bootstrap": {"seed": BOOTSTRAP_SEED, "replicates": BOOTSTRAP_REPLICATES,
            "unit": "32_mother_sources_each_four_seat_mean", "interval": "percentile_linear_0.025_0.975",
            "shared_resampling_indices_across_candidates": True, "formal_strength_claim": False},
        "pairing_evidence": "public_export_initial_exact_frozen_sampler_all_eight_physical_wall_hashes_and_actual_policy_mapping",
        "physical_wall_digest_public_export_verified": True,
        "actual_opponent_mapping_verified": True,
        "outcome_opponent_policy_id_coverage": all(
            t["audit"]["opponent_actual_identity_independently_exported"] for t in tables.values()),
        "deadline_admission": False, "confirmation_admission": False, "strength_admission": False,
        "release_admission": False, "new_models_scores_worlds_tables": 0}
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with OUTPUT.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"complete": True, "output": str(OUTPUT), "selected_candidate_id": selected,
                      "development_only": True, "strength_admission": False}, ensure_ascii=False))


def main(preflight_only=False):
    """nice至少15、macOS后台IO及共用独占锁下读回；只等待赛后锁，不操作续赛。"""
    require(sys.platform == "darwin", "本批读回须使用已冻结的macOS后台IO环境")
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority < 15:
        os.nice(15 - priority)
    require(os.getpriority(os.PRIO_PROCESS, 0) >= 15, "读回CPU优先级未降到nice15")
    io_policy = ctypes.CDLL(None, use_errno=True).setiopolicy_np
    io_policy.argtypes, io_policy.restype = [ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    require(io_policy(0, 0, 3) == 0, "读回未获得macOS后台IO策略")
    lock_path = _project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")
    with lock_path.open("a+") as lock:
        print(json.dumps({"state": "waiting_postprocess_lock", "scores_extracted": False,
                          "nice_at_least": 15, "background_io": True}, ensure_ascii=False), flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return _readout(preflight_only)
        finally:
            primary = sys.exc_info()[1]
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as secondary:
                if primary is None:
                    raise
                primary.add_note("读回释放赛后锁再次失败:" + type(secondary).__name__ + ": " + str(secondary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true", help="只核全批原终态，不读取积分或写闭合")
    args = parser.parse_args()
    try:
        main(args.preflight_only)
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as error:
        print(json.dumps({"complete": False, "status": "unknown_or_invalid_no_readout_written",
                          "error_type": type(error).__name__, "reason": str(error),
                          "original_evidence_retained": True, "strength_admission": False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
