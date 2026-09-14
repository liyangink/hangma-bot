"""序列策略网络的线上包装：部署包复核、排序语义与全路径降级。

测试只通过公开接口验证行为：制品装载是 learning 的公开函数，决策是
BotPolicy.choose。权重与网络需要可选依赖 torch，未安装时整模块跳过。
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import shutil
import time

import pytest

torch = pytest.importorskip("torch")

from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.learning.sequence_encoding import encode_sequence_input
from hangma_bot.learning.sequence_model_artifact import (
    SEQUENCE_MODEL_SCHEMA,
    SequenceModelArtifact,
    load_sequence_model,
)
from hangma_bot.learning.sequence_policy import batch_sequence_inputs
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy
from hangma_bot.policy.sequence_model_policy import SequenceModelPolicy

from . import support

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "prebuilt" / "sequence-policy-models"
RULESET = "hangma-mvp-v10-public-counts"


class _CountingNetwork:
    """记录调用次数的替身；只实现包装真正使用的前向接口。"""

    def __init__(self, *, fails: bool = False):
        self.calls = 0
        self.fails = fails

    def eval(self):
        return self

    def __call__(self, batch):
        self.calls += 1
        if self.fails:
            raise RuntimeError("stub failure")
        return torch.zeros((1, batch.candidate_valid.shape[1]), dtype=torch.float32), None


def _artifact(**overrides) -> SequenceModelArtifact:
    """构造最小可用制品元数据；默认与测试规则配置一致。"""

    fields = dict(
        candidate="test", direction="projected", training_roots=8, steps=16,
        parameter_id="0" * 64, checkpoint_sha256="0" * 64,
        network_version="visible-sequence-actor-critic-v1",
        feature_version="visible-key-public-sequence-v1",
        action_version="candidate-visible-relations-conditional-value-v2",
        rule_config={"ruleset_version": RULESET, "base_score": 1, "you_cai_bi_kao": False},
        training_rules_hash="0" * 64, training_method_id="0" * 64, release_gate=False, evidence={},
    )
    fields.update(overrides)
    return SequenceModelArtifact(**fields)


def _request(*, ruleset: str = RULESET,
             keep=("discard:1b", "discard:2b", "discard:3b", "discard:5t"),
             completeness: RuleCompleteness = RuleCompleteness.COMPLETE):
    """用真实规则引擎构造请求，并只保留指定的已存在候选键。"""

    observation = support.make_observation(
        my_hand=tuple(Tile(code) for code in
                      ("1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b", "1t", "2t", "3t", "4t")),
        drawn_tile=Tile("5t"),
        # 线上完整窗口的公开历史从已知起点保存；重连缺史时编码器会拒绝，见降级测试。
        history_complete=True,
    )
    analysis = support.rules_from_engine(observation)
    keys = [c.action_key for c in analysis.legal_candidates if c.action_key in keep]
    assert len(keys) == len(keep), "夹具候选键与实际规则候选不一致：" + repr(
        [c.action_key for c in analysis.legal_candidates])
    analysis = support.keep_keys(analysis, keys)
    analysis = replace(analysis, ruleset_version=ruleset, completeness=completeness)
    return support.make_request(observation, analysis)


def _policy(network, *, artifact=None, ruleset: str = RULESET) -> SequenceModelPolicy:
    """基线必须是能覆盖全部合法候选的完整策略；保底只提供紧急候选。"""

    return SequenceModelPolicy(
        baseline=ComparableHeuristicPolicyV2(), fallback=SafeFallbackPolicy(),
        network=network, artifact=artifact or _artifact(),
        runtime_rules=RuleConfig(ruleset, 1, False), monotonic=lambda: 0.0,
    )


def _budget():
    """用真实单调时钟给出的远期预算；基线策略不注入时钟，故不能用常量截止。"""

    now = time.monotonic()
    return support.make_budget(enhancement=now + 30.0, fallback=now + 60.0, latest=now + 90.0)


def _choose(policy, request, budget=None):
    return asyncio.run(policy.choose(request, budget or _budget()))


def test_deployment_packages_load_and_match_training_identity():
    """仓库内三个部署包必须逐字节自洽，且参数身份可从权重重算。"""

    names = sorted(p.name for p in PACKAGE_ROOT.iterdir() if p.is_dir())
    assert names == ["2048-projected", "4096-direct", "4096-projected"]
    for name in names:
        network, artifact = load_sequence_model(PACKAGE_ROOT / name)
        manifest = json.loads((PACKAGE_ROOT / name / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == SEQUENCE_MODEL_SCHEMA
        assert artifact.candidate == name and artifact.steps > 0 and artifact.training_roots > 0
        assert artifact.rule_config["ruleset_version"] == RULESET
        assert artifact.release_gate is False
        assert sum(p.numel() for p in network.parameters()) == 175554


def test_policy_ranks_every_legal_candidate_by_model_logits():
    """正常路径：全部合法候选按模型打分重排，且计划保留原候选集合。"""

    network, artifact = load_sequence_model(PACKAGE_ROOT / "4096-projected")
    request = _request()
    policy = _policy(network, artifact=artifact)
    plan = _choose(policy, request)
    assert plan.degraded_reasons == ()
    keys = {c.action_key for c in request.rules.legal_candidates}
    assert {c.action_key for c in plan.candidates} == keys
    assert [c.rank for c in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    encoded = encode_sequence_input(request.observation, request.rules.legal_candidates)
    with torch.inference_mode():
        logits, _ = network(batch_sequence_inputs((encoded,)))
    scores = dict(zip(encoded.action_keys, (float(v) for v in logits[0, :len(encoded.action_keys)]),
                      strict=True))
    expected = sorted(keys, key=lambda key: (-scores[key], key))
    assert [c.action_key for c in plan.candidates] == expected
    assert all(c.score_parts[0].name == "sequence_model_logit" for c in plan.candidates)
    assert [c.action_key for c in _choose(policy, request).candidates] == expected


def test_budget_exhausted_returns_fallback_without_running_model():
    """预算已耗尽时直接返回保底，且不调用网络。"""

    network = _CountingNetwork()
    request = _request()
    policy = SequenceModelPolicy(baseline=ComparableHeuristicPolicyV2(), fallback=SafeFallbackPolicy(),
                                 network=network, artifact=_artifact(),
                                 runtime_rules=RuleConfig(RULESET, 1, False), monotonic=lambda: 10.0)
    plan = _choose(policy, request, support.make_budget(enhancement=5.0))
    assert plan.degraded_reasons[-1] == "sequence_model:budget_exhausted"
    assert network.calls == 0


def test_degraded_rules_and_version_mismatch_restore_baseline():
    """规则不完整或版本不符时恢复基线，不把模型输出用于排序。"""

    for request in (_request(completeness=RuleCompleteness.DEGRADED), _request(ruleset="other-rules")):
        network = _CountingNetwork()
        plan = _choose(_policy(network), request)
        assert plan.degraded_reasons[-1] == "sequence_model:model_or_rules_unavailable"
        assert network.calls == 0


def test_artifact_rule_config_mismatch_restores_baseline():
    """制品声明的规则配置与运行时不同：不得把该模型用于决策。"""

    network = _CountingNetwork()
    artifact = _artifact(rule_config={"ruleset_version": RULESET, "base_score": 2, "you_cai_bi_kao": False})
    plan = _choose(_policy(network, artifact=artifact), _request())
    assert plan.degraded_reasons[-1] == "sequence_model:model_or_rules_unavailable"
    assert network.calls == 0


def test_single_candidate_window_does_not_run_network():
    """唯一合法候选是强制动作：不运行网络，也不改变任何评分。"""

    network = _CountingNetwork()
    plan = _choose(_policy(network), _request(keep=("discard:5t",)))
    assert plan.degraded_reasons == ()
    assert network.calls == 0


def test_incomplete_history_restores_baseline():
    """重连缺史时公开历史不完整：不得用该模型决策，原因单独可审计。"""

    network = _CountingNetwork()
    policy = _policy(network)
    request = _request()
    request = replace(request, observation=replace(request.observation, history_complete=False))
    plan = _choose(policy, request)
    assert plan.degraded_reasons[-1] == "sequence_model:incomplete_history"
    assert network.calls == 0


def test_model_failure_falls_back_with_structured_reason():
    """网络异常不得中断决策：恢复基线并写入稳定原因。"""

    plan = _choose(_policy(_CountingNetwork(fails=True)), _request())
    assert plan.degraded_reasons[-1] == "sequence_model:model_error"


def test_tampered_weight_bytes_are_rejected(tmp_path):
    """权重字节被改动必须拒绝装载，不允许带伤上线。"""

    source = PACKAGE_ROOT / "4096-projected"
    target = tmp_path / "tampered"
    shutil.copytree(source, target)
    weight = target / "model.pt"
    payload = bytearray(weight.read_bytes())
    payload[-1] ^= 0x01
    weight.write_bytes(bytes(payload))
    with pytest.raises(ValueError):
        load_sequence_model(target)


def test_composition_root_accepts_registered_model_strategies(tmp_path):
    """组合根必须能按策略名装载三个部署包；未知策略名仍然拒绝。"""

    from hangma_bot import bootstrap
    from hangma_bot.bootstrap import RuntimeConfig, RuntimeMode, TokenKind

    def config(name):
        return RuntimeConfig(
            mode=RuntimeMode.TEST_ROOM, base_url="http://127.0.0.1:1", expected_tournament_id="t1",
            known_guide_version=1, token="t", token_kind=TokenKind.TEST, audit_root=tmp_path,
            strategy=name,
        )

    for name in ("sequence_model_2048_projected_v1", "sequence_model_4096_direct_v1",
                 "sequence_model_4096_projected_v1"):
        policy = bootstrap._build_policy(config(name))
        assert isinstance(policy, SequenceModelPolicy)
        assert policy.model_id.startswith(bootstrap._SEQUENCE_MODEL_STRATEGIES[name])
    with pytest.raises(ValueError):
        config("sequence_model_unknown_v1")


def test_unexpected_member_is_rejected(tmp_path):
    """部署包出现未声明成员必须拒绝，防止夹带训练数据或完整世界。"""

    target = tmp_path / "extra"
    shutil.copytree(PACKAGE_ROOT / "2048-projected", target)
    (target / "cases.jsonl.gz").write_bytes(b"x")
    with pytest.raises(ValueError):
        load_sequence_model(target)
