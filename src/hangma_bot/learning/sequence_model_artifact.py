"""序列策略模型的部署制品：装载、身份复核与不可变元数据。

本模块只读取一个自包含的部署包目录，不依赖训练工作区、训练配方或完整世界。
装载失败一律向上抛错，由组合根决定是否降级；本模块不创建策略、不访问网络。
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Tuple

import torch

from .sequence_policy import (
    SEQUENCE_NETWORK_VERSION,
    SequenceActorCritic,
    SequencePolicyConfig,
)
from .sequence_encoding import SEQUENCE_ACTION_VERSION, SEQUENCE_FEATURE_VERSION

# 部署包模式版本；变更成员集合或字段语义必须升版，不能让旧消费方猜测。
SEQUENCE_MODEL_SCHEMA = "sequence-policy-deployment-v1"

# 部署包允许的成员；缺少或多出成员一律拒绝，避免夹带训练数据或完整世界。
_MEMBERS = ("manifest.json", "model.pt")

# 可见策略路径的参数量；与网络结构、冻结范围共同构成实际容量身份。
POLICY_PARAMETER_COUNT = 175554


def parameter_id(network: torch.nn.Module) -> str:
    """按参数名、形状、类型与字节取摘要；这是权重身份，不是文件摘要。"""

    hashed = hashlib.sha256()
    for name, tensor in sorted(network.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        hashed.update(json.dumps((name, str(value.dtype), list(value.shape))).encode())
        hashed.update(value.numpy().tobytes())
    return hashed.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SequenceModelArtifact:
    """一个已核对的序列策略部署制品；字段全部来自部署包字节。"""

    candidate: str  # 候选名，例如 4096-projected；用于审计与运行清单
    direction: str  # 训练方向 direct / projected；只作身份，不改变推理
    training_roots: int  # 训练所用独立完整牌山数
    steps: int  # 实际完成的优化步数
    parameter_id: str  # 权重身份（对状态字典取摘要）
    checkpoint_sha256: str  # model.pt 的文件字节摘要
    network_version: str  # 网络定义版本
    feature_version: str  # 观察编码版本
    action_version: str  # 动作编码版本
    rule_config: dict  # 训练时的规则配置；运行时必须逐项相等
    training_rules_hash: str  # 训练时规则源文件指纹；行为等价时允许与运行时不同
    training_method_id: str  # 冻结方法全文摘要，用于追溯训练口径
    release_gate: bool  # 训练方声明；本模块不因它为假而拒绝装载，但会记录
    evidence: dict  # 已登记的开发比较与编码等价证据，只作审计

    @property
    def model_id(self) -> str:
        """稳定的模型标识：候选名加权重身份前缀，用于审计关联。"""

        return self.candidate + ":" + self.parameter_id[:16]


def load_sequence_model(directory: Path, *, device: str = "cpu"
                        ) -> Tuple[SequenceActorCritic, SequenceModelArtifact]:
    """装载部署包并复核全部身份；任何不一致都抛错，不返回部分可用对象。

    复核内容：成员集合、清单模式、权重文件字节、实际参数量、参数身份、
    编码版本与本模块编译期常量、以及权重数值有限。
    """

    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    model_path = directory / "model.pt"
    if sorted(p.name for p in directory.iterdir() if p.is_file()) != list(_MEMBERS):
        raise ValueError("部署包成员集合不是 manifest.json 与 model.pt")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != {
        "schema", "candidate", "direction", "training_roots", "steps", "parameter_id",
        "checkpoint_sha256", "network_version", "feature_version", "action_version",
        "rule_config", "training_rules_hash", "training_method_id", "release_gate", "evidence",
    }:
        raise ValueError("部署清单字段集合改变")
    if manifest["schema"] != SEQUENCE_MODEL_SCHEMA:
        raise ValueError("未知部署包模式：{0!r}".format(manifest["schema"]))
    if manifest["network_version"] != SEQUENCE_NETWORK_VERSION:
        raise ValueError("网络定义版本与当前代码不一致")
    if manifest["feature_version"] != SEQUENCE_FEATURE_VERSION:
        raise ValueError("观察编码版本与当前代码不一致")
    if manifest["action_version"] != SEQUENCE_ACTION_VERSION:
        raise ValueError("动作编码版本与当前代码不一致")
    if _sha256(model_path) != manifest["checkpoint_sha256"]:
        raise ValueError("权重文件字节与清单不符")
    payload = torch.load(model_path, map_location="cpu", weights_only=True)
    if set(payload) != {"direction", "training_plan_id", "model", "parameter_id", "steps"}:
        raise ValueError("权重载荷字段集合改变")
    if (payload["direction"] != manifest["direction"]
            or payload["steps"] != manifest["steps"]
            or payload["parameter_id"] != manifest["parameter_id"]):
        raise ValueError("权重载荷的角色、步数或参数身份与清单不符")
    config = SequencePolicyConfig(
        width=manifest["evidence"]["network_config"]["width"],
        layers=manifest["evidence"]["network_config"]["layers"],
        heads=manifest["evidence"]["network_config"]["heads"],
        feedforward=manifest["evidence"]["network_config"]["feedforward"],
    )
    network = SequenceActorCritic(config).to(device).eval()
    network.load_state_dict(payload["model"], strict=True)
    if sum(p.numel() for p in network.parameters()) != POLICY_PARAMETER_COUNT:
        raise ValueError("实际参数量与固定策略容量不符")
    if parameter_id(network) != manifest["parameter_id"]:
        raise ValueError("装载后的参数身份与清单不符")
    if any(not bool(torch.isfinite(value).all()) for value in network.state_dict().values()):
        raise ValueError("权重包含非有限数值")
    artifact = SequenceModelArtifact(
        candidate=manifest["candidate"], direction=manifest["direction"],
        training_roots=manifest["training_roots"], steps=manifest["steps"],
        parameter_id=manifest["parameter_id"], checkpoint_sha256=manifest["checkpoint_sha256"],
        network_version=manifest["network_version"], feature_version=manifest["feature_version"],
        action_version=manifest["action_version"], rule_config=dict(manifest["rule_config"]),
        training_rules_hash=manifest["training_rules_hash"],
        training_method_id=manifest["training_method_id"],
        release_gate=bool(manifest["release_gate"]), evidence=dict(manifest["evidence"]),
    )
    return network, artifact


__all__ = [
    "POLICY_PARAMETER_COUNT",
    "SEQUENCE_MODEL_SCHEMA",
    "SequenceModelArtifact",
    "load_sequence_model",
    "parameter_id",
]
