"""全动作独立策略／价值网络；训练与推理共用，不内置 V2 首选先验。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import nn

from .encoding import MAX_HISTORY
from .key_encoding import KEY_ACTION_DIM, KEY_STATE_DIM
from .sequence_encoding import HISTORY_EVENT_DIM, MAX_CANDIDATES, SequenceInput

SEQUENCE_NETWORK_VERSION = 'visible-sequence-actor-critic-v1'


@dataclass(frozen=True)
class SequencePolicyConfig:
    """共享网络形状；制品必须保存整个配置，不能仅凭模型名称装载。"""

    width: int = 64  # 公开事件及观察摘要的隐藏宽度。
    layers: int = 2  # 顺序注意力层数，每层独立初始化。
    heads: int = 4  # 每层注意力头数，必须整除 width。
    feedforward: int = 256  # 每层前馈中间宽度；无 dropout，便于概率复现。

    def __post_init__(self):
        if (not 1 <= self.layers <= 4 or not 8 <= self.width <= 256
                or self.heads < 1 or self.width % self.heads or not 8 <= self.feedforward <= 1024):
            raise ValueError('独立策略网络配置无效')


@dataclass(frozen=True)
class SequenceBatch:
    """B 个观察的浮点张量；布尔掩码中 True 表示真实输入、False 表示填充。"""

    context: torch.Tensor  # [B,334]，上下文分数仍按旧编码除以 100。
    history: torch.Tensor  # [B,T,14]，T 为本批最长历史，可为 0，不超过 512。
    history_valid: torch.Tensor  # [B,T]；合法输入是连续前缀，支持空历史。
    candidates: torch.Tensor  # [B,K,184]，K 为本批最多候选数，不超过 128。
    candidate_valid: torch.Tensor  # [B,K]；每个观察至少一个真实候选。


def batch_sequence_inputs(inputs: Sequence[SequenceInput], *, device: str = 'cpu') -> SequenceBatch:
    """将公开编码填充成批；只分配张量，不读文件、世界或教师标签。

    顺序保持原 inputs 和各自 action_keys；形状错误抛 ValueError。
    填充候选不代表 Pass，网络必须令其动作概率严格为零。
    """
    if not inputs:
        raise ValueError('输入批次为空')
    for item in inputs:
        if (len(item.context) != KEY_STATE_DIM or len(item.history) > MAX_HISTORY
                or any(len(row) != HISTORY_EVENT_DIM for row in item.history)
                or not 1 <= len(item.candidates) <= MAX_CANDIDATES
                or len(item.action_keys) != len(item.candidates)
                or len(set(item.action_keys)) != len(item.action_keys)
                or any(len(row) != KEY_ACTION_DIM for row in item.candidates)):
            raise ValueError('独立策略输入形状或动作绑定错误')
    b, t, k = len(inputs), max(len(x.history) for x in inputs), max(len(x.candidates) for x in inputs)
    contexts = torch.tensor([x.context for x in inputs], dtype=torch.float32, device=device)
    history = torch.zeros(b, t, HISTORY_EVENT_DIM, device=device)
    actions = torch.zeros(b, k, KEY_ACTION_DIM, device=device)
    history_valid = torch.zeros(b, t, dtype=torch.bool, device=device)
    candidate_valid = torch.zeros(b, k, dtype=torch.bool, device=device)
    for i, item in enumerate(inputs):
        n, m = len(item.history), len(item.candidates)
        if n:
            history[i, :n] = torch.tensor(item.history, dtype=torch.float32, device=device)
        actions[i, :m] = torch.tensor(item.candidates, dtype=torch.float32, device=device)
        history_valid[i, :n] = True
        candidate_valid[i, :m] = True
    return SequenceBatch(contexts, history, history_valid, actions, candidate_valid)


class SequenceActorCritic(nn.Module):
    """仅看可见输入，对全部候选给出独立 logits 和同座位状态价值。

    forward 返回 [B,K] 无量纲偏好及 [B] 价值。填充 logits 为 -inf；
    沿 K 做 softmax 才得到动作概率。价值的奖励终点和缩放由训练制品
    显式声明，行为克隆时尚未训练，不能直接当作桌赛积分或 MeanOutcome。
    不含随机采样、文件读写、规则重算或策略先验；随机选择由调用方负责。
    """

    def __init__(self, config: SequencePolicyConfig = SequencePolicyConfig()):
        super().__init__()
        self.config = config
        self.context_projection = nn.Sequential(nn.Linear(KEY_STATE_DIM, config.width), nn.ReLU())
        self.event_projection = nn.Linear(HISTORY_EVENT_DIM, config.width)
        self.positions = nn.Embedding(MAX_HISTORY + 1, config.width)
        # 不用同一个层对象复制初始化，避免所有注意力层从完全相同的参数出发。
        self.layers = nn.ModuleList(nn.TransformerEncoderLayer(
            config.width, config.heads, config.feedforward, dropout=0.,
            batch_first=True, norm_first=True) for _ in range(config.layers))
        self.normalization = nn.LayerNorm(config.width)
        self.action_projection = nn.Sequential(nn.Linear(KEY_ACTION_DIM, config.width), nn.ReLU())
        self.actor = nn.Sequential(nn.Linear(2 * config.width, config.width), nn.ReLU(), nn.Linear(config.width, 1))
        self.critic = nn.Linear(config.width, 1)

    def forward(self, batch: SequenceBatch) -> tuple[torch.Tensor, torch.Tensor]:
        """严格检查真实输入，忽略填充数值；结构或非有限真实值抛 ValueError。"""
        c, h, hv, a, av = (batch.context, batch.history, batch.history_valid,
                            batch.candidates, batch.candidate_valid)
        if (c.ndim != 2 or c.shape[1] != KEY_STATE_DIM or c.shape[0] == 0
                or h.ndim != 3 or h.shape[0] != c.shape[0] or h.shape[2] != HISTORY_EVENT_DIM
                or h.shape[1] > MAX_HISTORY or hv.shape != h.shape[:2] or hv.dtype != torch.bool
                or a.ndim != 3 or a.shape[0] != c.shape[0] or a.shape[2] != KEY_ACTION_DIM
                or not 1 <= a.shape[1] <= MAX_CANDIDATES or av.shape != a.shape[:2] or av.dtype != torch.bool):
            raise ValueError('独立策略批次形状或掩码无效')
        if (not bool(av.any(dim=1).all()) or bool((hv[:, 1:] & ~hv[:, :-1]).any())
                or not bool(torch.isfinite(c).all()) or not bool(torch.isfinite(h[hv]).all())
                or not bool(torch.isfinite(a[av]).all())):
            raise ValueError('独立策略缺少合法候选、历史非连续或真实输入非有限')
        h = h.masked_fill(~hv.unsqueeze(-1), 0.)
        a = a.masked_fill(~av.unsqueeze(-1), 0.)
        # 摘要 token 始终有效，因此空历史也不会产生全掩码注意力。
        tokens = torch.cat((self.context_projection(c).unsqueeze(1), self.event_projection(h)), dim=1)
        tokens = tokens + self.positions(torch.arange(tokens.shape[1], device=c.device)).unsqueeze(0)
        padding = torch.cat((torch.zeros(c.shape[0], 1, dtype=torch.bool, device=c.device), ~hv), dim=1)
        for layer in self.layers:
            tokens = layer(tokens, src_key_padding_mask=padding)
        state = self.normalization(tokens[:, 0])
        repeated = state.unsqueeze(1).expand(-1, a.shape[1], -1)
        logits = self.actor(torch.cat((repeated, self.action_projection(a)), dim=-1)).squeeze(-1)
        values = self.critic(state).squeeze(-1)
        if not bool(torch.isfinite(logits[av]).all()) or not bool(torch.isfinite(values).all()):
            raise ValueError('独立策略输出非有限')
        return logits.masked_fill(~av, -torch.inf), values
