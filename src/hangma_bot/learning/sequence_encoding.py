"""独立策略的可见输入；复用既有编码，不读取教师排序或完整世界。"""
from __future__ import annotations

from dataclasses import dataclass

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX
from hangma_bot.kernel.observation import PlayerObservation
from .encoding import MAX_HISTORY, compact_feature_indices, encode_observation
from .key_encoding import KEY_ACTION_VERSION, _encode_key_candidate_with_counts

SEQUENCE_FEATURE_VERSION = 'visible-key-public-sequence-v1'
SEQUENCE_ACTION_VERSION = KEY_ACTION_VERSION
SEQUENCE_INPUT_CONTRACT_VERSION = 'official-snapshot-events-v1'
HISTORY_EVENT_DIM = 14
MAX_CANDIDATES = 128


@dataclass(frozen=True)
class SequenceInput:
    """一次动作窗口的纯值输入；座位均已旋转为本人、下家、对家、上家。"""

    context: tuple[float, ...]  # 334 维既有可见摘要，含当前摸牌身份。
    history: tuple[tuple[float, ...], ...]  # 实际已收可见事件，按序排列，每行14维；快照前可不连续，无填充。
    candidates: tuple[tuple[float, ...], ...]  # K×184，全部提供的合法候选，不按教师筛选。
    action_keys: tuple[str, ...]  # 与候选一一对应的规范排序键，仅用于绑定输出，不输入网络。


def encode_sequence_input(
    observation: PlayerObservation, candidates: tuple[RuleCandidate, ...],
) -> SequenceInput:
    """编码权威当前牌面、已收可见事件和全动作候选；无副作用。

    复用 visible-flat-v1 的 14 维事件行及 key 编码的 334/184 维。
    事件中的牌码、枚举仍是既有数值编码，不宣称是新类别嵌入。
    官方v34 §2.1以快照及后续连续增量为准；快照以前未归档的事件正常
    保留为记录覆盖信息，不是输入异常。快照之后断序、非法事件顺序、
    有观察问题、超容量、空候选或重复键抛 ValueError。
    特征数值与维度不变，输入准入版本单独记录，兼容原部署权重。
    这里不判定动作合法性；输入候选必须由唯一 hangma 规则模块产生。
    """
    if observation.observation_issues:
        raise ValueError('独立策略观察存在未解决的问题')
    consumed = observation.consumed_seq
    if consumed is None:
        consumed = observation.snapshot_seq  # 旧观察只声明了快照基线。
    previous = None
    next_incremental = observation.snapshot_seq + 1
    for event in observation.public_history:
        if event.seq > consumed or (previous is not None and event.seq <= previous):
            raise ValueError('可见事件顺序或已消费水位矛盾')
        if event.seq > observation.snapshot_seq:
            if event.seq != next_incremental:
                raise ValueError('快照之后的增量尚未连续同步')
            next_incremental += 1
        previous = event.seq
    if next_incremental != consumed + 1:
        raise ValueError('快照之后的增量尚未连续同步')
    if not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError('候选数量为空或超过编码容量')
    ordered = tuple(sorted(candidates, key=lambda candidate: candidate.action_key))
    keys = tuple(candidate.action_key for candidate in ordered)
    if len(set(keys)) != len(keys):
        raise ValueError('候选动作键重复')
    full = encode_observation(observation)
    drawn = [0.] * 34
    if observation.drawn_tile is not None:
        drawn[CANONICAL_TILE_INDEX[observation.drawn_tile.code]] = 1.
    context = tuple(full[i] for i in compact_feature_indices())
    # 暗牌计数已包含当前摸牌；同一窗口的全部候选共享本次归一化结果。
    counts = tuple(round(value * 4) for value in context[33:67])
    context += (float(observation.drawn_tile is not None),) + tuple(drawn)
    # 完整编码的末段固定为 MAX_HISTORY 个事件；只移除确定的尾部填充。
    events = full[-MAX_HISTORY * HISTORY_EVENT_DIM:]
    history = tuple(tuple(events[i:i + HISTORY_EVENT_DIM])
                    for i in range(0, len(observation.public_history) * HISTORY_EVENT_DIM,
                                   HISTORY_EVENT_DIM))
    return SequenceInput(context, history,
                         tuple(_encode_key_candidate_with_counts(observation, c, counts)
                               for c in ordered), keys)
