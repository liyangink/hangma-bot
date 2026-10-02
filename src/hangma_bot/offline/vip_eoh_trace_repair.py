"""确定性修复 VIP 自然结构解释格式；原作者及失败保持，修后另建评分身份。"""

from __future__ import annotations

import ast
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND

from .vip_eoh_generate import (
    ACCOUNTS, VIP_EOH_GENERATION_SCHEMA, VIP_EOH_PROFILE, VipEohBatch, VipEohError,
    load_vip_parents,
)
from .vip_eoh_rebind import ORIGINAL_AUTHOR_FIELDS

VIP_TRACE_REPAIR_ROLE = "trace_codec_repair"
VIP_TRACE_REPAIR_PROVENANCE_SCHEMA = "vip-trace-codec-repair-provenance/1"
TRACE_CODEC_REPAIR_ID = "vip-natural-structure-trace-flat/1"
_TRACE_LAYOUT = ["family", "active", "weightedinventory", "extra", "credit", "*codes"]
_AUTHOR_TEXT_SCOPE = "original_author_history_trace_layout_claim_not_applicable_after_repair"
_OLD_SITE = "proxyrows.append((family, codes, active, weightedinventory, extra, credit))"
_NEW_SITE = "proxyrows.append((family, active, weightedinventory, extra, credit) + codes)"
_OLD_DESCRIPTION = "代理向量：家族、原码集、是否加权、加权库存代理、加权额外代理、评分。"
_NEW_DESCRIPTION = "代理向量：家族、是否加权、加权库存代理、加权额外代理、评分，其后平铺原码集。"
_LOAD_METHOD = "ActionValueExecutor_constructor_and_exact_trace_repair_origin_validation"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def repair_structure_trace_source(source: str) -> str:
    """在指定函数内只修复已知记录语句及其说明，不执行源码。

    牌码从记录内嵌元组改为末尾逐项平铺，顺序和重复保留。没有原格式、
    重复格式、位置或说明不符、已修源码均拒绝；不提供任意替换接口。
    是否保持实际评分仍由修后机械与数学门判断，不能据此授予行为信用。
    """

    try:
        tree = ast.parse(source)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == "make_support_credits"]
        old_ast = ast.dump(ast.parse(_OLD_SITE).body[0], include_attributes=False)
        sites = [n for n in ast.walk(tree) if isinstance(n, ast.Expr)
                 and ast.dump(n, include_attributes=False) == old_ast]
        if len(functions) != 1 or len(sites) != 1:
            raise VipEohError("解释修复必须有唯一固定函数和唯一已知记录语句")
        function, site = functions[0], sites[0]
        if site not in list(ast.walk(function)) or site.lineno != site.end_lineno:
            raise VipEohError("已知记录语句不在固定函数的单行区域")
        description = ast.get_docstring(function, clean=False)
        if (not description or description.count(_OLD_DESCRIPTION) != 1
                or source.count(_OLD_SITE) != 1 or source.count(_OLD_DESCRIPTION) != 1
                or _NEW_SITE in source or _NEW_DESCRIPTION in source):
            raise VipEohError("解释修复说明、记录数量或原格式不对应")
        line = source.splitlines(keepends=True)[site.lineno - 1]
        if line.strip() != _OLD_SITE:
            raise VipEohError("解释修复只接受已知完整记录语句")
        return source.replace(_OLD_SITE, _NEW_SITE, 1).replace(_OLD_DESCRIPTION, _NEW_DESCRIPTION, 1)
    except SyntaxError as error:
        raise VipEohError("解释修复源码不能解析") from error


def _validate_identities(before: dict[str, Any], after: dict[str, Any]) -> None:
    old, new = json.loads(_encoded(before)), json.loads(_encoded(after))
    for name in ("candidate_id", "source_sha256"):
        if old.pop(name) == new.pop(name):
            raise VipEohError("解释修复须产生新的源码及候选身份")
    if _encoded(old) != _encoded(new):
        raise VipEohError("解释修复不能改变合同、规则、依赖或执行额度")


def validate_vip_trace_repair_package(path, record, source, batch, identity, lineage):
    """唯一父包装载门使用的来源校验；核原件与确定性修复，不授准入。

    绝对原来源路径仍须存在。原生成工具清单记录历史调用，不要求与后来
    的离线工具相同；当前评分身份、原执行配置及全部显式附件必须匹配。
    """

    from .vip_eoh_generate import _load_vip_parents

    provenance = record.get("provenance")
    load, admission, publication = record.get("load"), record.get("admission"), record.get("publication")
    billing = record.get("billing")
    if (not isinstance(provenance, dict) or not isinstance(load, dict)
            or not isinstance(admission, dict) or not isinstance(publication, dict)
            or not isinstance(billing, dict)
            or provenance.get("schema") != VIP_TRACE_REPAIR_PROVENANCE_SCHEMA
            or provenance.get("repair_id") != TRACE_CODEC_REPAIR_ID
            or provenance.get("trace_layout") != _TRACE_LAYOUT
            or provenance.get("original_author_text_scope") != _AUTHOR_TEXT_SCOPE
            or provenance.get("universal_score_equivalence_claim") is not False
            or provenance.get("allowed_source_changes") != ["structure_support_trace_flatten_and_description"]
            or record.get("artifact_role") != VIP_TRACE_REPAIR_ROLE
            or record.get("backend") != VIP_TRACE_REPAIR_ROLE
            or record.get("is_model_output") is not False
            or record.get("operator_actual") is not None or record.get("operator_requested") is not None
            or record.get("model_identity") is not None or record.get("parents") != []
            or record.get("behavior_change_credit") is not False
            or type(record.get("tables_run")) is not int or record["tables_run"] != 0
            or load.get("method") != _LOAD_METHOD or load.get("gates_run") != []
            or load.get("full_return_or_behavior_verified") is not False
            or admission.get("eligible") is not False or admission.get("gates_run") != []
            or publication.get("published") is not False
            or billing.get("call_started") is not False or billing.get("status") != "not_a_model_call"
            or not isinstance(billing.get("charged"), dict)
            or set(billing["charged"]) != set(ACCOUNTS)
            or any(type(v) is not int or v != 0 for v in billing["charged"].values())):
        raise VipEohError("解释修复来源、角色、费用或准入声明不合法")
    try:
        source_batch_path = Path(provenance["source_batch_path"])
        source_batch = VipEohBatch.read(source_batch_path)
        if (source_batch.raw != (path / "batch.json").read_bytes()
                or provenance["source_batch_sha256"] != _sha(source_batch.raw)
                or record["batch_sha256"] != _sha(source_batch.raw)
                or record["batch_id"] != source_batch.batch_id):
            raise VipEohError("解释修复原执行批次漂移")
        original_path = Path(provenance["original_package_path"]).resolve()
        original = _load_vip_parents([original_path], source_batch, lineage=lineage)[0]
        original_raw = (original_path / "generation.json").read_bytes()
        original_source = (original_path / "candidate.py").read_bytes()
        original_record = json.loads(original_raw)
        if (original["artifact_role"] != "candidate_proposal" or original_record.get("is_model_output") is not True
                or _sha(original_raw) != original["record_sha256"]
                or original_raw != (path / "original-generation.json").read_bytes()
                or original_source != (path / "original-candidate.py").read_bytes()
                or provenance["original_generation_sha256"] != _sha(original_raw)
                or provenance["original_source_sha256"] != _sha(original_source)
                or _encoded(provenance["source_identity"]) != _encoded(original["identity"])
                or _encoded(provenance["target_identity"]) != _encoded(identity)
                or repair_structure_trace_source(original_source.decode("utf-8")) != source
                or _encoded(source_batch.identity(source)) != _encoded(identity)):
            raise VipEohError("解释修复必须逐字来自原模型提案和唯一确定性补丁")
        _validate_identities(original["identity"], identity)
        if (_encoded(provenance["original_author_evidence"]) != _encoded({
                name: original_record.get(name) for name in ORIGINAL_AUTHOR_FIELDS})
                or record.get("thought") != original_record.get("thought")
                or _encoded(record.get("mechanism")) != _encoded(original_record.get("mechanism"))):
            raise VipEohError("解释修复不能改写原模型、思想、机制或费用")
        expected_optional = {"original-source-raw.py": original_path / "source-raw.py",
                             "original-author-batch.json": original_path / "batch.json"}
        optional, evidence = provenance["optional_original_files"], provenance["execution_evidence"]
        if (not isinstance(optional, list) or not isinstance(evidence, list)
                or {i["snapshot_path"] for i in optional} != {
                    name for name, p in expected_optional.items() if p.exists()}):
            raise VipEohError("解释修复原作者附件遗漏或结构不合法")
        snapshots = []
        for item in optional + evidence:
            snapshot = Path(item["snapshot_path"])
            if snapshot.is_absolute() or ".." in snapshot.parts:
                raise VipEohError("解释修复快照必须位于新包内")
            snapshots.append(str(snapshot))
            original_file = Path(item["original_path"]).resolve()
            if item in optional:
                if original_file != expected_optional[str(snapshot)].resolve():
                    raise VipEohError("解释修复作者附件来源不对应")
            elif snapshot.parent != Path("execution-evidence"):
                raise VipEohError("解释修复执行附件目录不合法")
            raw = original_file.read_bytes()
            if (raw != (path / snapshot).read_bytes() or item["sha256"] != _sha(raw)
                    or type(item["bytes"]) is not int or item["bytes"] != len(raw)):
                raise VipEohError("解释修复原附件或复制件漂移")
        if len(snapshots) != len(set(snapshots)):
            raise VipEohError("解释修复附件快照重复")
        if _encoded(batch.identity(source)) != _encoded(identity):
            raise VipEohError("解释修复当前执行身份不对应")
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise VipEohError("解释修复谱系结构不完整") from error


def repair_vip_trace_codec(
    *, batch_file: Path, source_package: Path, out_dir: Path,
    execution_evidence_files: Sequence[Path] = (),
) -> dict[str, Any]:
    """从原已装载模型提案创建工程修复包；只构造，不评分或调用模型。

    新目录须不存在；配置完全沿用原执行配置。源漂移和装载失败保留失效
    记录并抛错误；原包、原账本与失败不覆盖。本地耗时以单调时钟秒记录。
    """

    started = time.monotonic()
    batch_file, source_package, out_dir = map(lambda p: Path(p).resolve(), (batch_file, source_package, out_dir))
    batch = VipEohBatch.read(batch_file)
    original = load_vip_parents([source_package], batch)[0]
    original_raw = (source_package / "generation.json").read_bytes()
    original_source = (source_package / "candidate.py").read_bytes()
    author = json.loads(original_raw)
    if (original["artifact_role"] != "candidate_proposal" or author.get("is_model_output") is not True
            or _sha(original_raw) != original["record_sha256"]
            or original_source.decode("utf-8") != original["source"]):
        raise VipEohError("解释修复只接受当前已装载模型提案，不接受人工种子或重修")
    repaired = repair_structure_trace_source(original["source"])
    identity = batch.identity(repaired)
    _validate_identities(original["identity"], identity)
    ActionValueExecutor(repaired, max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    snapshots = {"original-generation.json": original_raw, "original-candidate.py": original_source,
                 "candidate.py": repaired.encode("utf-8"), "batch.json": batch.raw}
    optional, evidence = [], []
    for name, copied in (("source-raw.py", "original-source-raw.py"), ("batch.json", "original-author-batch.json")):
        path = source_package / name
        if path.exists():
            raw = path.read_bytes()
            snapshots[copied] = raw
            optional.append({"original_path": str(path), "snapshot_path": copied, "sha256": _sha(raw), "bytes": len(raw)})
    for index, path in enumerate(execution_evidence_files):
        path = Path(path).resolve()
        raw = path.read_bytes()
        copied = "execution-evidence/{0:03d}-{1}".format(index, path.name)
        snapshots[copied] = raw
        evidence.append({"original_path": str(path), "snapshot_path": copied, "sha256": _sha(raw), "bytes": len(raw)})
    provenance = {"schema": VIP_TRACE_REPAIR_PROVENANCE_SCHEMA, "repair_id": TRACE_CODEC_REPAIR_ID,
                  "trace_layout": list(_TRACE_LAYOUT), "original_author_text_scope": _AUTHOR_TEXT_SCOPE,
                  "universal_score_equivalence_claim": False,
                  "allowed_source_changes": ["structure_support_trace_flatten_and_description"],
                  "original_package_path": str(source_package), "original_generation_sha256": _sha(original_raw),
                  "original_source_sha256": _sha(original_source), "source_batch_path": str(batch_file),
                  "source_batch_sha256": _sha(batch.raw), "source_identity": original["identity"],
                  "target_identity": identity, "original_author_evidence": {name: author.get(name) for name in ORIGINAL_AUTHOR_FIELDS},
                  "optional_original_files": optional, "execution_evidence": evidence}
    record = {"schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
              "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "artifact_role": VIP_TRACE_REPAIR_ROLE,
              "backend": VIP_TRACE_REPAIR_ROLE, "batch_id": batch.batch_id, "batch_sha256": _sha(batch.raw),
              "status": "loaded_not_admitted", "identity": identity, "identity_stable": True,
              "source_sha256": _sha(snapshots["candidate.py"]), "is_model_output": False,
              "operator_requested": None, "operator_actual": None, "model_identity": None, "parents": [],
              "thought": author.get("thought"), "mechanism": author.get("mechanism"), "provenance": provenance,
              "load": {"ok": True, "method": _LOAD_METHOD, "gates_run": [], "full_return_or_behavior_verified": False},
              "billing": {"scope": "trace_format_repair_only_original_author_cost_retained_in_provenance",
                          "charged": dict.fromkeys(ACCOUNTS, 0), "call_started": False, "status": "not_a_model_call"},
              "tables_run": 0, "behavior_change_credit": False,
              "admission": {"eligible": False, "gates_run": []}, "publication": {"published": False},
              "elapsed_monotonic_seconds": 0.0, "error": None}
    out_dir.mkdir(parents=True, exist_ok=False)
    try:
        for name, raw in snapshots.items():
            path = out_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
        if (batch_file.read_bytes() != batch.raw or load_vip_parents([source_package], batch)[0] != original
                or batch.identity(repaired) != identity):
            raise VipEohError("解释修复首尾源包、批次或评分依赖漂移")
        for item in optional + evidence:
            if Path(item["original_path"]).read_bytes() != snapshots[item["snapshot_path"]]:
                raise VipEohError("解释修复原附件首尾漂移")
        record["elapsed_monotonic_seconds"] = max(0.0, time.monotonic() - started)
        (out_dir / "generation.json").write_bytes(_encoded(record))
        load_vip_parents([out_dir], batch)
        record["elapsed_monotonic_seconds"] = max(0.0, time.monotonic() - started)
        (out_dir / "generation.json").write_bytes(_encoded(record))
    except Exception as error:
        record.update(status="trace_repair_invalid", identity_stable=False,
                      load={"ok": False, "gates_run": []},
                      error={"type": type(error).__name__, "reason": "解释修复未通过来源或身份校验"})
        record["elapsed_monotonic_seconds"] = max(0.0, time.monotonic() - started)
        (out_dir / "generation.json").write_bytes(_encoded(record))
        raise
    return record
