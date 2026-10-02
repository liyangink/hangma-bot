"""海选开发对手：正常 V0 与自动胡／右端弃牌的局部行为代理。

只排序唯一规则源已给出的合法动作，不制造网络超时或服务端等待。
官方依据是仓库指南 v34 快照的「超时兜底」（2026-10-02读取）；
右端按本地玩家观察中的实体牌顺序解释，不能宣称复现服务器隐藏排序。
对手强弱比例是用户专家情景，具体比例及 V0 强弱尚非实测平台分布。
本模块只供离线装配，生产 bootstrap 不导入它。
"""
from __future__ import annotations

import hashlib
import math
import random
import json
from dataclasses import asdict
from typing import Callable
from typing import Mapping, Sequence

from hangma_bot.kernel.actions import Discard, Hu, Pass, action_key
from hangma_bot.policy.interface import DecisionBudget, DecisionPlan, DecisionRequest, RankedCandidate, ScorePart
from hangma_bot.policy.legacy_pass import LegacyWeightedHeuristicPolicy
from hangma_bot.policy.weights import DEFAULT_WEIGHTS
from .evaluate import PolicyDeclaration
from .scoring_sources import source_manifest
from .vip_route_development import build_vip_development_runtime

QUALIFIER_OPPONENT_VERSION = "qualifier-visible-opponents/1"


class AutomaticLikePolicy:
    """合法胡优先；响应过；本人行动弃观察中最右实体牌。

    缺失期望合法动作时显式失败，不能偷偷换成有牌效的保底策略。
    其余合法动作保留在计划中；拒绝过滤后仍只在当前合法集合内排名。
    """

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """只读公开请求，返回完整合法排名；无时钟、I/O或完整世界副作用。"""
        rejected = {item.action_key for item in request.rejected_attempts}
        candidates = tuple(c for c in request.rules.legal_candidates if c.action_key not in rejected)
        if len({c.action_key for c in candidates}) != len(candidates) or any(
            c.action_key != action_key(c.action) for c in candidates
        ):
            raise ValueError("自动行为代理收到重复或不一致的合法动作键")
        if not candidates:
            raise ValueError("自动行为代理没有可用合法动作")
        hu = next((c for c in candidates if isinstance(c.action, Hu)), None)
        observation = request.observation
        if hu is not None:
            preferred, reason = hu, "当前规则已确认可胡，自动胡"
        elif observation.phase in ("response_peng", "response_chi"):
            preferred = next((c for c in candidates if isinstance(c.action, Pass)), None)
            reason = "响应不鸣牌，直接过；不模拟服务端固定等待"
        else:
            waiting_size = 13 - 3 * len(observation.melds[observation.seat])
            if len(observation.my_hand) == waiting_size and observation.drawn_tile is not None:
                rightmost = observation.drawn_tile
            elif len(observation.my_hand) == waiting_size + 1:
                rightmost = observation.my_hand[-1]
            else:
                raise ValueError("自动行为代理缺少可解释的本人弃牌实体顺序")
            preferred = next((c for c in candidates if isinstance(c.action, Discard)
                              and c.action.tile == rightmost), None)
            reason = "按公开观察右端弃牌，包括右端白板；不作牌效保护"
        if preferred is None:
            raise ValueError("自动行为代理期望动作不在剩余合法集合中")
        ordered = (preferred,) + tuple(sorted((c for c in candidates if c is not preferred),
                                             key=lambda c: c.action_key))
        emergency = request.rules.emergency_candidate
        return DecisionPlan(request.decision_id, request.window_key, observation.snapshot_seq,
            len(request.rejected_attempts) + 1,
            tuple(RankedCandidate(c.action, c.action_key, i + 1, 1.0 if i == 0 else 0.0,
                (ScorePart("自动行为代理优先", 1.0 if i == 0 else 0.0),), (reason,),
                emergency is not None and c.action_key == emergency.action_key)
                for i, c in enumerate(ordered)), ())


def freeze_qualifier_compositions(roots: Sequence[Mapping], weak_fraction: float) -> list[dict]:
    """开桌前按母根抽三个逻辑对手；同一随机数用于比例敏感性与 A/C 配对。

    weak_fraction 为整个抽样情景的弱对手概率，不保证每桌过半。
    弱对手等分为正常 V0 与自动行为代理；余者为注册 R18。
    输入只含未执行的母根标识和 seed，不访问或生成牌山。
    """
    if type(weak_fraction) not in (int, float) or not math.isfinite(weak_fraction) or not 0 <= weak_fraction <= 1:
        raise ValueError("弱对手比例须为0到1有限数，不接受布尔")
    if not roots or len({r["root_id"] for r in roots}) != len(roots):
        raise ValueError("母根不能为空或重复")
    result = []
    for root in roots:
        if type(root["seed"]) is not int or root["seed"] < 0 or type(root["root_id"]) is not str or not root["root_id"]:
            raise ValueError("母根标识或seed不合法")
        # 与模拟洗牌分离的命名空间；牌山不会因对手比例变化而重新抽取。
        material = f"{QUALIFIER_OPPONENT_VERSION}:{root['root_id']}:{root['seed']}".encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(material).digest(), "big"))
        draws = [rng.random() for _ in range(3)]
        types = ["automatic_like" if u < weak_fraction / 2 else
                 "normal_v0" if u < weak_fraction else "r18" for u in draws]
        result.append({"root_id": root["root_id"], "seed": root["seed"],
                       "weak_fraction_setting": weak_fraction, "draw_uniforms": draws,
                       "opponent_types_logical_1_2_3": types,
                       "actual_weak_count": sum(t != "r18" for t in types),
                       "paired_A_C_same_composition": True})
    return result


def build_qualifier_runtime(generation_batch, candidate_source: str, opponent_types: Sequence[str],
                            *, clock: Callable[[], float] = lambda: 800.0):
    """显式装配每母根三个对手及注册 A/VIP C；每逻辑席位独立实例。

    normal_v0 使用组合根同款旧过牌兼容视图及冻结默认权重。
    身份记录源码闭包、参数与行为版本；既有 H/M 工具和线上装配不变。
    """
    if len(opponent_types) != 3 or any(t not in ("automatic_like", "normal_v0", "r18") for t in opponent_types):
        raise ValueError("须显式声明三个已知类型的海选对手")
    runtime = build_vip_development_runtime(generation_batch, candidate_source, clock=clock)
    manifest = source_manifest(("hangma_bot.offline.qualifier_opponents",))
    for i, kind in enumerate(opponent_types, 1):
        label = f"Q{i}"
        if kind == "r18":
            original = runtime.declarations[f"H{i}"]
            runtime.declarations[label] = original
            runtime.policy_metadata[label] = dict(runtime.policy_metadata[f"H{i}"], qualifier_type=kind)
            continue
        metadata = {"type": kind, "behavior_version": QUALIFIER_OPPONENT_VERSION,
                    "source_manifest": manifest, "params": asdict(DEFAULT_WEIGHTS) if kind == "normal_v0" else {},
                    "scope": "offline_behavior_proxy_not_observed_platform_strength_or_latency"}
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        policy_id = f"{label}:{kind}:{digest}"
        runtime.declarations[label] = PolicyDeclaration(policy_id, "qualifier_" + kind,
            tuple(sorted(asdict(DEFAULT_WEIGHTS).items())) if kind == "normal_v0" else ())
        runtime.policies_by_id[policy_id] = (LegacyWeightedHeuristicPolicy(monotonic=clock)
            if kind == "normal_v0" else AutomaticLikePolicy())
        runtime.policy_metadata[label] = dict(metadata, policy_id=policy_id)
    return runtime
