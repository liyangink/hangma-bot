"""把训练工作区的序列策略终点导出为仓库内自包含部署包。

用法（仓库根目录执行，输出目录必须不存在）：

    .venv/bin/python scripts/export_sequence_model.py \
        --source artifacts/model-outcomes-v1/evaluations/portable-policy-scale-4352-v1/consumer \
        --destination prebuilt/sequence-policy-models

每个候选导出 "候选/manifest.json" 与 "候选/model.pt"。导出会重新装载
权重并重算参数身份，因此部署包不依赖训练工作区、训练配方或完整世界。本脚本
不改变训练产物，也不写入任何线上默认值。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hangma_bot.learning.sequence_model_artifact import (  # noqa: E402
    POLICY_PARAMETER_COUNT,
    SEQUENCE_MODEL_SCHEMA,
    parameter_id,
)
from hangma_bot.learning.sequence_encoding import (  # noqa: E402
    SEQUENCE_ACTION_VERSION,
    SEQUENCE_FEATURE_VERSION,
)
from hangma_bot.learning.sequence_policy import (  # noqa: E402
    SEQUENCE_NETWORK_VERSION,
    SequenceActorCritic,
    SequencePolicyConfig,
)

# 候选表：部署包名 → (规模, 方向)。与 bootstrap._SEQUENCE_MODEL_STRATEGIES 的
# 取值一一对应；新增候选必须同时更新两处。
CANDIDATES = {
    "2048-projected": (2048, "projected"),
    "4096-direct": (4096, "direct"),
    "4096-projected": (4096, "projected"),
}


def sha256(path: Path) -> str:
    """文件字节摘要；用于绑定实际分发的权重。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluation_evidence(source: Path, roots: int) -> dict:
    """收集已封存的候选对 V2 开发比较，只作审计说明，不参与装载判定。"""

    path = source / str(roots) / "tables" / "report.json"
    if not path.exists():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    return {"development_comparisons": report.get("comparisons", {}),
            "development_tables": report.get("tables"),
            "development_roots": report.get("pools", {}).get("rich", {}).get("net", {}).get("roots"),
            "report_id": report.get("plan_id")}


def export_one(candidate: str, roots: int, direction: str, source: Path, recipe: dict,
               out: Path) -> dict:
    """导出单个候选并复核权重身份；任一步不符即抛错，不留半成品。"""

    runtime = source / str(roots) / "training" / "runtime"
    artifact = json.loads((runtime / "artifact.json").read_text(encoding="utf-8"))
    method = artifact["method"]["method"]
    # 冻结方法本身不保存规则配置，用生成配方补齐并逐项交叉核对，避免凭常量填写。
    if (recipe["rules_hash"] != method["rules_hash"] or recipe["source_hash"] != method["source_hash"]
            or recipe["parent_identity"] != method["parent_identity"] or recipe["release_gate"]):
        raise ValueError("生成配方与冻结方法身份不一致：" + candidate)
    if (artifact["schema"] != "portable-policy-endpoints-v1" or not artifact["training_complete"]
            or artifact["training_roots"] != roots or roots not in method["training_roots"]
            or method["phase"] == "engineering" or artifact["release_gate"] or method["release_gate"]):
        raise ValueError("训练终点不是可导出的正式完整终点：" + candidate)
    endpoint = artifact["models"][direction]
    weight = runtime / (direction + ".pt")
    if sha256(weight) != endpoint["checkpoint_sha256"]:
        raise ValueError("权重文件字节与训练清单不符：" + candidate)
    payload = torch.load(weight, map_location="cpu", weights_only=True)
    config = SequencePolicyConfig(**method["network_config"])
    network = SequenceActorCritic(config).eval()
    network.load_state_dict(payload["model"], strict=True)
    if sum(p.numel() for p in network.parameters()) != POLICY_PARAMETER_COUNT:
        raise ValueError("参数量与固定策略容量不符：" + candidate)
    if parameter_id(network) != endpoint["parameter_id"]:
        raise ValueError("重算参数身份与训练清单不符：" + candidate)
    destination = out / candidate
    destination.mkdir(parents=True)
    torch.save(payload, destination / "model.pt")
    manifest = {
        "schema": SEQUENCE_MODEL_SCHEMA,
        "candidate": candidate,
        "direction": direction,
        "training_roots": roots,
        "steps": payload["steps"],
        "parameter_id": endpoint["parameter_id"],
        "checkpoint_sha256": sha256(destination / "model.pt"),
        "network_version": SEQUENCE_NETWORK_VERSION,
        "feature_version": SEQUENCE_FEATURE_VERSION,
        "action_version": SEQUENCE_ACTION_VERSION,
        "rule_config": dict(recipe["rule_config"]),
        "training_rules_hash": method["rules_hash"],
        "training_method_id": hashlib.sha256(json.dumps(
            method, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "release_gate": False,
        "evidence": {
            "network_config": dict(method["network_config"]),
            "training_source_hash": method["source_hash"],
            "parent_identity": method["parent_identity"],
            "training_plan_id": artifact["training_plan_id"],
            "student_binding_id": artifact["student_binding_id"],
            "deployment_note": (
                "未证明优于或不劣于 V2：正式开发比较的同时区间全部跨零。"
                "本包用于真实环境实测取数，不是已验证的强度提升。"
            ),
            **evaluation_evidence(source, roots),
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True,
                        help="训练消费者根目录，其下为 <规模>/training/runtime")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True, help="冻结生成配方 recipe.json")
    parser.add_argument("--only", action="append", default=None)
    arguments = parser.parse_args()
    if arguments.destination.exists():
        raise SystemExit("拒绝覆盖已有部署目录：" + str(arguments.destination))
    arguments.destination.mkdir(parents=True)
    recipe = json.loads(arguments.recipe.read_text(encoding="utf-8"))
    names = arguments.only or sorted(CANDIDATES)
    for name in names:
        roots, direction = CANDIDATES[name]
        manifest = export_one(name, roots, direction, arguments.source, recipe, arguments.destination)
        print("导出 {0}：roots={1} steps={2} parameter_id={3}".format(
            name, manifest["training_roots"], manifest["steps"], manifest["parameter_id"][:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
