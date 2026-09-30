"""显式重绑定 VIP 研究执行额度；保留作者费用和失败证据，不产生新模型调用。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND

from .vip_eoh_generate import (
    ACCOUNTS, VIP_EOH_GENERATION_SCHEMA, VIP_EOH_PROFILE,
    VipEohBatch, VipEohError, load_vip_parents,
)

VIP_RESEARCH_REBIND_ROLE = "research_budget_rebind"
VIP_RESEARCH_REBIND_PROVENANCE_SCHEMA = "vip-research-budget-rebind-provenance/1"
ORIGINAL_AUTHOR_FIELDS = (
    "artifact_role", "backend", "batch_id", "batch_sha256", "attempt_id", "attempt_no",
    "operator_requested", "operator_actual", "is_model_output", "model_identity", "reply",
    "reply_sha256", "billing", "usage", "reservation", "status", "error",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def validate_vip_research_budget_batches(source: VipEohBatch, target: VipEohBatch) -> None:
    """只允许操作额度上升及新 batch_id 标签；其他配置含作者预算逐项相同。

    batch_id 是审计标签，不是作者或调用身份。两个原始批次字节分别保存，
    不修改旧批、旧账本或源包；配置语义按保留数值类型的规范 JSON 比较。
    """

    if (type(source.max_operations) is not int or type(target.max_operations) is not int
            or target.max_operations <= source.max_operations):
        raise VipEohError("研究重绑定只允许正整数 max_operations 严格提高")
    before, after = json.loads(source.raw), json.loads(target.raw)
    for data in (before, after):
        data.pop("max_operations")
        data.pop("batch_id")
    if _json_bytes(before) != _json_bytes(after):
        raise VipEohError("除 max_operations 提高和 batch_id 标签外，研究批次配置必须完全相同")


def validate_vip_research_rebind_identities(source: dict[str, Any], target: dict[str, Any]) -> None:
    """评分合同、依赖、规则和投影身份均相同，只能形成新的操作额度身份。"""

    before, after = json.loads(_json_bytes(source)), json.loads(_json_bytes(target))
    before.pop("candidate_id")
    after.pop("candidate_id")
    old_ops = before["params"].pop("max_operations")
    new_ops = after["params"].pop("max_operations")
    if (type(old_ops) is not int or type(new_ops) is not int or new_ops <= old_ops
            or _json_bytes(before) != _json_bytes(after)
            or source["candidate_id"] == target["candidate_id"]):
        raise VipEohError("评分身份只能改变 max_operations 与由其派生的 candidate_id")


def rebind_vip_research_budget(
    *, source_batch_file: Path, source_package: Path, target_batch_file: Path,
    out_dir: Path, execution_evidence_files: Sequence[Path] = (),
) -> dict[str, Any]:
    """逐字保留当前提案并提高研究执行额度；只装载，不评分、不准入。

    source_batch_file 是验证原执行身份的公开配置，未必是原作者生成批次；
    原作者批次、模型证据、费用仍由原 generation 原件保留。可选执行证据
    只作调用方显式提供的原样引用，不能从该引用推断效果或准入。输出目录
    必须不存在；源/合同/依赖首尾漂移则保留失效记录并抛 VipEohError。
    """

    started = time.monotonic()  # 本地重绑定持续时间，单位秒；不是模型墙钟计费。
    source_batch_file, target_batch_file = Path(source_batch_file).resolve(), Path(target_batch_file).resolve()
    source_package, out_dir = Path(source_package).resolve(), Path(out_dir).resolve()
    source_batch, target_batch = VipEohBatch.read(source_batch_file), VipEohBatch.read(target_batch_file)
    validate_vip_research_budget_batches(source_batch, target_batch)
    original = load_vip_parents([source_package], source_batch)[0]
    if original["artifact_role"] not in ("candidate_proposal", VIP_RESEARCH_REBIND_ROLE):
        raise VipEohError("研究重绑定只接受当前提案；人工种子须由公开种子入口重新建立")
    original_generation = (source_package / "generation.json").read_bytes()
    original_source = (source_package / "candidate.py").read_bytes()
    if (_sha(original_generation) != original["record_sha256"]
            or original_source.decode("utf-8") != original["source"]):
        raise VipEohError("源包在校验后发生漂移")
    original_record = json.loads(original_generation)
    target_identity = target_batch.identity(original["source"])
    validate_vip_research_rebind_identities(original["identity"], target_identity)
    ActionValueExecutor(original["source"], max_operations=target_batch.max_operations)
    snapshots = {"original-generation.json": original_generation,
                 "original-candidate.py": original_source,
                 "source-batch.json": source_batch.raw, "candidate.py": original_source,
                 "batch.json": target_batch.raw}
    optional = []
    for name, copy_name in (("source-raw.py", "original-source-raw.py"),
                            ("batch.json", "original-author-batch.json")):
        path = source_package / name
        if path.exists():
            data = path.read_bytes()
            snapshots[copy_name] = data
            optional.append({"original_path": str(path), "snapshot_path": copy_name,
                             "sha256": _sha(data), "bytes": len(data)})
    evidence = []
    for index, path in enumerate(execution_evidence_files):
        path = Path(path).resolve()
        data = path.read_bytes()
        copy_name = "execution-evidence/{0:03d}-{1}".format(index, path.name)
        snapshots[copy_name] = data
        evidence.append({"original_path": str(path), "snapshot_path": copy_name,
                         "sha256": _sha(data), "bytes": len(data)})
    provenance = {
        "schema": VIP_RESEARCH_REBIND_PROVENANCE_SCHEMA,
        "original_package_path": str(source_package), "source_batch_path": str(source_batch_file),
        "target_batch_path": str(target_batch_file), "original_generation_sha256": _sha(original_generation),
        "original_source_sha256": _sha(original_source), "source_batch_sha256": _sha(source_batch.raw),
        "target_batch_sha256": _sha(target_batch.raw), "source_identity": original["identity"],
        "target_identity": target_identity,
        "original_author_evidence": {name: original_record.get(name) for name in ORIGINAL_AUTHOR_FIELDS},
        "optional_original_files": optional, "execution_evidence": evidence,
        "execution_evidence_scope": "caller_supplied_original_bytes_not_admission_or_effect",
        "allowed_configuration_changes": ["max_operations_increase", "batch_id_audit_label"],
    }
    record = {
        "schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "artifact_role": VIP_RESEARCH_REBIND_ROLE,
        "backend": VIP_RESEARCH_REBIND_ROLE, "batch_id": target_batch.batch_id,
        "batch_sha256": _sha(target_batch.raw), "status": "loaded_not_admitted",
        "identity": target_identity, "identity_stable": True, "source_sha256": _sha(original_source),
        "is_model_output": False, "operator_requested": None, "operator_actual": None,
        "thought": original_record.get("thought"), "mechanism": original_record.get("mechanism"),
        "provenance": provenance, "parents": [], "model_identity": None,
        "load": {"ok": True, "method": "ActionValueExecutor_constructor_and_recursive_origin_validation",
                 "gates_run": [], "full_return_or_behavior_verified": False},
        "billing": {"scope": "research_rebinding_only_original_author_cost_retained_in_provenance",
                    "charged": {name: 0 for name in ACCOUNTS}, "call_started": False,
                    "status": "not_a_model_call"},
        "tables_run": 0, "behavior_change_credit": False,
        "admission": {"eligible": False, "gates_run": []}, "publication": {"published": False},
        "elapsed_monotonic_seconds": 0.0, "error": None,
    }
    out_dir.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in snapshots.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
        if (source_batch_file.read_bytes() != source_batch.raw
                or target_batch_file.read_bytes() != target_batch.raw
                or load_vip_parents([source_package], source_batch)[0] != original
                or target_batch.identity(original["source"]) != target_identity):
            raise VipEohError("研究重绑定首尾源包、批次或评分依赖漂移")
        for item in optional + evidence:
            if Path(item["original_path"]).read_bytes() != snapshots[item["snapshot_path"]]:
                raise VipEohError("原始作者材料或执行证据漂移")
        record["elapsed_monotonic_seconds"] = max(0.0, time.monotonic() - started)
        with (out_dir / "generation.json").open("xb") as stream:
            stream.write(_json_bytes(record))
        load_vip_parents([out_dir], target_batch)  # 新包仍经唯一公共装载门，不自授可装载资格。
    except Exception as error:
        record.update(status="rebind_invalid", identity_stable=False,
                      load={"ok": False, "gates_run": []},
                      error={"type": type(error).__name__, "reason": "研究重绑定未通过来源或身份校验"})
        (out_dir / "generation.json").write_bytes(_json_bytes(record))
        raise
    return record
