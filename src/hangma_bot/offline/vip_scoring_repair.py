"""G37两项已复现评分缺陷的确定性修复；不是LLM提案或强度准入。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time


FAULT_SOURCE_SHA256 = "b3960980015519d1da24e63273310fe2872b159eea77cac7126660e71c411bca"
REPAIR_ID = "vip-g37-fee-and-continuation-tie/1"
SCORING_REPAIR_ROLE = "scoring_defect_repair"
SCORING_REPAIR_PROVENANCE = "vip-scoring-defect-repair-provenance/1"

_OLD_FEE = '''                steps = max(familysteps, bound)
                extra = max(0.0, steps - familysteps)
                quote = (familyquote + prior - EXTRAPATH * extra
                         - WHITEHOLD * float(retained - 1)
                         - (ladder(steps) - ladder(familysteps)))'''
_NEW_FEE = '''                # 普通等待也含最后一摸；这里只支付新增自然路径负担。
                baseline = familysteps + 1.0
                steps = max(baseline, bound)
                extra = max(0.0, steps - baseline)
                quote = (familyquote + prior
                         - WHITEHOLD * float(retained - 1)
                         - (ladder(steps) - ladder(baseline)))'''

_SHADOW_SITE = '''    joint = core + dividend
    option = None'''
_SHADOW = '''    joint = core + dividend
    # 当前可胡时，重叠进张码仍可支持不同的保白用途。
    # 这里只生成同价继续动作的辅助质量，不加进胡/继续主报价。
    repair_shadow = None
    if anchor is not None:
        shadow = dividend
        for position in range(len(routes)):
            if position == winner:
                continue
            route = routes[position]
            detail = route[4]
            if detail is None or detail[5] <= 0.0:
                continue
            overlap = 0
            for code in route[2]:
                if code in occupied and stock[codeindex[code]][0] > 0.0:
                    overlap += 1
            if overlap > 0:
                gapvalue = max(0.0, core - route[0])
                distgap = max(0.0, route[1] - routes[winner][1])
                closeness = 1.0 / (1.0 + DIVCLOSE * gapvalue)
                maturity = 1.0 / (1.0 + DIVGAP * distgap)
                shadow += (DIVCAP * float(overlap) / (DIVREF + float(overlap))
                           * detail[5] * closeness * maturity * scale)
        repair_shadow = core + min(DIVTOTAL, shadow)
    option = None'''

_TIE_FUNCTION = '''def rank_continuation_ties(entries, quality_rows):
    """只细分主报价相同的弃牌；每组最高报价及所有Hu报价保持。

    辅助质量只用于已报价相同的继续动作，不补概率、不改变原不同
    价组的顺序，也不提高弃胡诱因。输入entries是本调用新建的输出。
    """
    bases = {entry["action_key"]: entry["score"] for entry in entries}
    qualities = {row[0]: row[1] for row in quality_rows}
    ranked = []
    for entry in entries:
        key = entry["action_key"]
        if key not in qualities:
            ranked.append(entry)
            continue
        base = bases[key]
        peak = qualities[key]
        members = 0
        for peer in entries:
            peerkey = peer["action_key"]
            if peerkey in qualities and bases[peerkey] == base:
                members += 1
                if qualities[peerkey] > peak:
                    peak = qualities[peerkey]
        difference = peak - qualities[key]
        if members < 2 or difference <= 0.0:
            ranked.append(entry)
            continue
        gap = None
        for peer in entries:
            distance = base - bases[peer["action_key"]]
            if distance > 0.0 and (gap is None or distance < gap):
                gap = distance
        limit = DIVTOTAL if gap is None else min(DIVTOTAL, gap / 4.0)
        penalty = limit * difference / (1.0 + difference)
        trace_rows = [(name, value) for name, value in entry["trace"].items()]
        trace_rows.append(("repair_base_score", base))
        trace_rows.append(("repair_tie_penalty", penalty))
        ranked.append({"action_key": key, "score": base - penalty, "trace": dict(trace_rows)})
    return ranked


'''


def _replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError("已知G37修复位置不唯一或源内容不同")
    return source.replace(before, after, 1)


def scoring_repair_phases(fault_source: str) -> dict[str, str]:
    """只接受已核G37，输出三个隔离阶段；不执行源码、规则、模型或桌赛。

    F1只改用途额外费用；F2只加当前可胡时的辅助质量/解释；RF1才
    细分同价弃牌。模块常量、支付聚合、普通牌效及Hu主报价保持。
    返回值是源码字符串；效果、有限评分及发布仍需独立回归。
    """
    if hashlib.sha256(fault_source.encode()).hexdigest() != FAULT_SOURCE_SHA256:
        raise ValueError("修复只适用于已核G37故障源码；不能套到P0或重复修复")
    fee = _replace_once(fault_source, _OLD_FEE, _NEW_FEE)
    shadow = _replace_once(fee, _SHADOW_SITE, _SHADOW)
    shadow = _replace_once(shadow,
        "             option, qualcost, ready, prepstats)",
        "             option, qualcost, ready, prepstats, repair_shadow)")
    shadow = _replace_once(shadow,
        "        if not entries:\n            pairs.append((\"unit\", \"heuristic_rank_points\"))",
        "        if facts is not None and facts[11] is not None:\n"
        "            pairs.append((\"repair_shadow\", facts[11]))\n"
        "        if not entries:\n            pairs.append((\"unit\", \"heuristic_rank_points\"))")
    fixed = _replace_once(shadow, "def score_actions(view):", _TIE_FUNCTION + "def score_actions(view):")
    fixed = _replace_once(fixed, "    entries = []\n    actioncount =", "    entries = []\n    repair_quality_rows = []\n    actioncount =")
    fixed = _replace_once(fixed,
        "        if facts is not None and facts[11] is not None:\n"
        "            pairs.append((\"repair_shadow\", facts[11]))",
        "        if facts is not None and facts[11] is not None:\n"
        "            pairs.append((\"repair_shadow\", facts[11]))\n"
        "            if kind == \"discard\":\n"
        "                repair_quality_rows.append((action[\"action_key\"], facts[11]))")
    fixed = _replace_once(fixed,
        "    return {\"status\": \"SCORED\", \"entries\": entries}",
        "    if anchor is not None:\n"
        "        entries = rank_continuation_ties(entries, repair_quality_rows)\n"
        "    return {\"status\": \"SCORED\", \"entries\": entries}")
    fixed = _replace_once(fixed, "vip_ladder_frontier_exclusive_dividend_e1/1", REPAIR_ID)
    return {"F1": fee, "F2": shadow, "RF1": fixed}


def _pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def validate_scoring_repair_package(path, record, source, batch, identity, lineage):
    """核固定修复谱系和原件；禁止伪装LLM调用或继承父代准入。"""
    from .vip_eoh_generate import VipEohError, _load_vip_parents

    proof = record.get("provenance", {})
    if (proof.get("schema") != SCORING_REPAIR_PROVENANCE or proof.get("repair_id") != REPAIR_ID
            or record.get("backend") != SCORING_REPAIR_ROLE
            or record.get("is_model_output") is not False or record.get("model_identity") is not None
            or record.get("new_model_calls") != 0 or record.get("admission", {}).get("admitted") is not False
            or record.get("publication", {}).get("published") is not False):
        raise VipEohError("评分修复身份、零模型费用或未准入状态不符")
    parent_path = Path(proof["parent_path"])
    parent = _load_vip_parents([parent_path], batch, lineage=lineage)[0]
    if (proof["parent_identity"] != parent["identity"]
            or proof["parent_record_pin"] != _pin(parent_path / "generation.json")
            or proof["parent_source_pin"] != _pin(parent_path / "candidate.py")
            or (path / "fault-generation.json").read_bytes() != (parent_path / "generation.json").read_bytes()
            or (path / "fault-source.py").read_text() != parent["source"]
            or proof["transformer_pin"] != _pin(Path(__file__))
            or source != scoring_repair_phases(parent["source"])["RF1"]):
        raise VipEohError("评分修复原件或固定最小变换漂移")
    before, after = dict(parent["identity"]), dict(identity)
    for key in ("candidate_id", "source_sha256"):
        before.pop(key)
        after.pop(key)
    if before != after:
        raise VipEohError("评分修复不得改变规则、合同、依赖或执行额度")


def write_scoring_repair_package(*, parent_path: Path, batch_file: Path, output: Path) -> dict:
    """新建诚实修复包并装载，不评分、不调用作者、不授发布资格。

    来源/输出为本地目录；已有输出拒绝覆盖。持续时间使用单调秒。
    固定源不适配、静态语言或身份漂移抛错，父源及其费用记录保持。
    """
    from .vip_eoh_generate import (VIP_EOH_GENERATION_SCHEMA, VIP_EOH_PROFILE,
                                   VipEohBatch, load_vip_parents)
    from ..policy.action_value_executor import ActionValueExecutor
    from ..policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND

    started = time.monotonic()
    parent_path, output = Path(parent_path).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("修复包另存，不能覆盖原件")
    batch = VipEohBatch.read(batch_file)
    parent = load_vip_parents([parent_path], batch)[0]
    source = scoring_repair_phases(parent["source"])["RF1"]
    identity = batch.identity(source)
    ActionValueExecutor(source, max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    record = {"schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "artifact_role": SCORING_REPAIR_ROLE,
        "backend": SCORING_REPAIR_ROLE, "status": "loaded_not_admitted",
        "identity": identity, "identity_stable": True, "source_sha256": identity["source_sha256"],
        "is_model_output": False, "model_identity": None, "new_model_calls": 0,
        "thought": "统一G37额外等待费用；同价继续动作保留真实重叠用途质量，保持最高继续/Hu报价。",
        "operator_actual": "deterministic_defect_repair_not_eoh",
        "load": {"ok": True, "method": "constructor_and_exact_scoring_repair_validation", "score_calls": 0},
        "admission": {"admitted": False}, "publication": {"published": False}, "tables_run": 0,
        "billing": {"new_model_calls": 0, "inherited_author_credit": False},
        "provenance": {"schema": SCORING_REPAIR_PROVENANCE, "repair_id": REPAIR_ID,
            "parent_path": str(parent_path), "parent_identity": parent["identity"],
            "parent_record_pin": _pin(parent_path / "generation.json"),
            "parent_source_pin": _pin(parent_path / "candidate.py"), "transformer_pin": _pin(Path(__file__))}}
    output.mkdir(parents=True)
    (output / "candidate.py").write_text(source)
    (output / "fault-source.py").write_text(parent["source"])
    (output / "fault-generation.json").write_bytes((parent_path / "generation.json").read_bytes())
    (output / "batch.json").write_bytes(batch.raw)
    record["elapsed_monotonic_seconds"] = time.monotonic() - started
    try:
        validate_scoring_repair_package(output, record, source, batch, identity, (output,))
    except Exception as error:
        record["status"] = "repair_validation_failed"
        record["load"]["ok"] = False
        record["error"] = {"type": type(error).__name__, "reason": str(error)}
        (output / "generation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        raise
    (output / "generation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return record
