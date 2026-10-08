"""T200 离线作者薄入口：复用现有 EoH 合同、执行器、额度账和 GLM 传输。

本工具只生成研究父包和提案；不评分、不跑桌、不读取线上 Token，
不修改当前策略。API 失败记账，不自动重发；算子生成不授准入。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t200-eoh-fast-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = _PROJECT_ROOT
STAGE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))


def pin(path: Path) -> dict:
    """声明非凭据文件的字节指纹；不输出内容。"""
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save_new(path: Path, value: dict) -> None:
    """新原件独占创建；不覆盖旧失败或费用。"""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def prepare() -> None:
    """冻结首批八作者调用上限，采用当前规则的真实 P0 参考；0评分。"""
    from hangma_bot.offline.vip_eoh_generate import (
        VipEohBatch, load_vip_parents, VIP_EOH_GENERATION_SCHEMA, VIP_EOH_PROFILE,
    )
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND
    from hangma_bot.policy.vip_s03_frozen_source import VIP_S03_SOURCE
    from hangma_bot.policy.vip_s03_rulefix_p0_identity import VIP_S03_RULEFIX_P0_IDENTITY

    STAGE.mkdir(parents=True, exist_ok=True)
    batch_path = _project_file(_PROJECT_ROOT, STAGE / "AUTHOR-BATCH-001.json")
    historical = _project_file(_PROJECT_ROOT, ROOT / "review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1/AUTHOR-BATCH.json")
    batch_value = json.loads(historical.read_text())
    batch_value.update(batch_id="t200-eoh-population-author-batch-001")
    batch_value["budgets"] = {
        "model_calls": 8, "input_tokens": 8 * 1048576,
        "output_tokens": 8 * 65536, "table_instances": 0,
        "wall_clock_seconds": 8 * 900,
    }
    save_new(batch_path, batch_value)
    batch = VipEohBatch.read(batch_path)
    identity = batch.identity(VIP_S03_SOURCE)
    if identity != VIP_S03_RULEFIX_P0_IDENTITY:
        raise ValueError("当前规则／核心／原公式没有精确绑定已发布P0")
    ActionValueExecutor(VIP_S03_SOURCE, max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    parent = _project_file(_PROJECT_ROOT, STAGE / "parents/p0-reference")
    parent.mkdir(parents=True, exist_ok=False)
    (parent / "candidate.py").write_text(VIP_S03_SOURCE)
    record = {
        "schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND,
        "artifact_role": "candidate_proposal", "status": "loaded_not_admitted",
        "source_origin": "adopted_published_P0_refreeze",
        "identity": identity, "identity_stable": True,
        "source_sha256": identity["source_sha256"],
        "thought": "当前已发布P0的原S03公式，作为新开发参考，不继承旧世界成绩。",
        "mechanism": None, "is_model_output": False,
        "operator_requested": None, "operator_actual": None, "parents": [],
        "load": {"ok": True, "method": "ActionValueExecutor_constructor", "gates_run": []},
        "admission": {"eligible": False, "gates_run": []},
        "publication": {"published": False},
        "provenance": {
            "published_strategy": "vip_s03_rulefix_p0_free_v1",
            "P0_module_pin": pin(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/vip_s03_rulefix_p0_identity.py")),
            "source_module_pin": pin(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/vip_s03_frozen_source.py")),
            "author_calls": 0, "score_calls": 0,
            "old_effect_metrics_inherited": False,
        },
    }
    save_new(parent / "generation.json", record)
    loaded = load_vip_parents([parent], batch)
    save_new(_project_file(_PROJECT_ROOT, STAGE / "PREPARED.json"), {
        "batch_pin": pin(batch_path), "parent_id": loaded[0]["identity"]["candidate_id"],
        "parent_source_pin": pin(parent / "candidate.py"), "author_runner_pin": pin(Path(__file__)),
        "rules_scores_World_tables_API": 0,
        "no_new_model_output_claim": True, "current_rules_identity_exact": True,
    })
    print(json.dumps({"status": "prepared", "parent_id": identity["candidate_id"], "model_calls": 0}))


def call(args) -> int:
    """发起一次显式作者槽；只接受本阶段新输出及已冻结完整父包。"""
    from hangma_bot.offline.vip_eoh_generate import run_vip_eoh_generate

    out = args.out.resolve()
    if not out.is_relative_to(STAGE.resolve()) or out.exists():
        raise ValueError("作者输出须为T200私有阶段的新目录")
    transport_path = _project_file(_PROJECT_ROOT, ROOT / "review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1/glm_max_transport.py")
    spec = importlib.util.spec_from_file_location("_t200_existing_glm_max", transport_path)
    maximum = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maximum)
    result = run_vip_eoh_generate(
        batch_file=args.batch, out_dir=out,
        operator=args.operator, backend=args.backend, parent_paths=args.parent,
        feedback=args.feedback.read_text(), config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"),
        endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=maximum.make_factory(out / "ACTUAL-REASONING-REQUEST.json") if args.backend == "api" else None,
    )
    print(json.dumps({key: result.get(key) for key in (
        "status", "attempt_id", "operator_actual", "source_sha256", "identity_stable",
    )}, ensure_ascii=False))
    return 0 if result.get("status") in ("prompt_emitted", "loaded_not_admitted") else 1


def main() -> int:
    """prepare不读凭据；call的凭据仍只在既有原子预留后读取。"""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    author = sub.add_parser("call")
    author.add_argument("--operator", choices=("i1", "e1", "e2", "m1", "m2"), required=True)
    author.add_argument("--parent", type=Path, action="append", default=[])
    author.add_argument("--feedback", type=Path, required=True)
    author.add_argument("--out", type=Path, required=True)
    author.add_argument("--backend", choices=("emit", "api"), default="emit")
    author.add_argument("--batch", type=Path, default=_project_file(_PROJECT_ROOT, STAGE / "AUTHOR-BATCH-001.json"))
    args = parser.parse_args()
    return (prepare() or 0) if args.command == "prepare" else call(args)


if __name__ == "__main__":
    raise SystemExit(main())
