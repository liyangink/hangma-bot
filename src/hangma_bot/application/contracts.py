"""应用层端口与跨模块消息；具体官方 DTO 不得进入本文件。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Protocol, Tuple, Union

from hangma_bot.kernel.actions import Action, WindowKey, action_key as canonical_action_key
from hangma_bot.kernel.config import TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext, PlayerObservation


class RuntimeMode(str, Enum):
    """用于防止测试身份和正式身份混接。"""

    TEST_ROOM = "test_room"
    TEST_TOURNAMENT = "test_tournament"
    OFFICIAL_TOURNAMENT = "official_tournament"


@dataclass(frozen=True)
class RuntimeTarget:
    """启动时必须核对的运行目标；不包含 Token 原文。"""

    mode: RuntimeMode
    expected_tournament_id: str
    known_guide_version: int


@dataclass(frozen=True)
class GuideVersion:
    """启动或阶段边界观察到的官方指南版本。"""

    version: int
    updated_at: str
    has_unknown_breaking_change: bool


class TournamentStatus(str, Enum):
    """官方顶层赛事状态的内部规范值。"""

    REGISTERING = "registering"
    RUNNING = "running"
    STAGE_DONE = "stage_done"
    STAGE_OPEN = "stage_open"
    FINISHED = "finished"
    CLOSED = "closed"
    VOID = "void"


@dataclass(frozen=True)
class StageIdentity:
    """一次赛事观察中的阶段引用，用于拒绝陈旧的到位命令。"""

    stage_no: Optional[int]
    observed_revision: int  # 当前会话内单调增加；不是官方字段，也不跨进程持久化


@dataclass(frozen=True)
class TournamentSnapshot:
    """应用层观察到的一次权威赛事事实。"""

    tournament_id: str
    participant_id: str  # 脱敏身份，不是 Token
    status: TournamentStatus
    stage: StageIdentity
    stage_role: Optional[str]
    stage_total: Optional[int]
    stage_crashed: bool
    qualified: Optional[bool]
    qualify_role: Optional[str]
    active_games: Tuple[str, ...]
    my_games: Tuple[str, ...]
    competition: CompetitionContext
    observed_at_unix_ms: int


class ParticipantTerminalReason(str, Enum):
    """单个身份停止运行的原因；不都代表赛事已经终止。"""

    ELIMINATED = "eliminated"
    TOURNAMENT_FINISHED = "tournament_finished"
    TOURNAMENT_CLOSED = "tournament_closed"
    TOURNAMENT_VOID = "tournament_void"
    AUTHENTICATION_FAILED = "authentication_failed"
    INCOMPATIBLE_GUIDE = "incompatible_guide"
    TARGET_MISMATCH = "target_mismatch"
    FATAL_PROTOCOL_ERROR = "fatal_protocol_error"


@dataclass(frozen=True)
class ParticipantTerminal:
    """当前 Token 对应身份的终态。"""

    reason: ParticipantTerminalReason
    last_snapshot: Optional[TournamentSnapshot]
    detail: str


@dataclass(frozen=True)
class SessionBootstrap:
    """版本、身份、目标和规则发现结果；初始化本身不报名或到位。"""

    guide: GuideVersion
    participant_id: str
    tournament_id: str
    config: TournamentConfig
    initial_snapshot: TournamentSnapshot


InitializeOutcome = Union[SessionBootstrap, ParticipantTerminal]


class OperationStatus(str, Enum):
    """报名或到位的可分类结果。"""

    ACCEPTED = "accepted"
    ALREADY_DONE = "already_done"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RegistrationResult:
    """报名结果；``official_code`` 仅保存非敏感错误码。"""

    status: OperationStatus
    official_code: Optional[str] = None


@dataclass(frozen=True)
class ReadyResult:
    """阶段到位结果；名单外拒绝由应用层转换为正常淘汰。"""

    status: OperationStatus
    official_code: Optional[str] = None


RegistrationOutcome = Union[RegistrationResult, ParticipantTerminal]
ReadyOutcome = Union[ReadyResult, ParticipantTerminal]


@dataclass(frozen=True)
class ObservedActionWindow:
    """官方会话交给应用层的规范动作窗口，不包含本地合法候选。"""

    observation: PlayerObservation
    window_key: WindowKey
    authoritative_seq: int
    received_at_monotonic: float  # 本机单调时钟秒数
    timeout_seconds: float  # 官方配置的窗口持续秒数

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("动作窗口持续时间必须为正数")
        if self.authoritative_seq != self.observation.snapshot_seq:
            raise ValueError("窗口权威序号必须与玩家观察一致")
        if (
            self.window_key.game_id != self.observation.game_id
            or self.window_key.round_no != self.observation.round_no
            or self.window_key.seat != self.observation.seat
        ):
            raise ValueError("窗口键必须与玩家观察属于同一场、单局和座位")


@dataclass(frozen=True)
class GameFinished:
    """一个官方场次的权威终局。"""

    game_id: str
    final_scores: Tuple[int, int, int, int]  # 固定按座位 0—3
    authoritative_seq: int


@dataclass(frozen=True)
class GameFailed:
    """会话无法继续的分类故障；可恢复故障由应用层重新发现该场。"""

    game_id: str
    recoverable: bool
    reason: str


GameItem = Union[ObservedActionWindow, GameFinished, GameFailed]


@dataclass(frozen=True)
class ActionAttempt:
    """应用层交给官方适配器的一次动作尝试。"""

    decision_id: str
    attempt_no: int
    plan_revision: int
    window_key: WindowKey
    based_on_authoritative_seq: int
    action: Action
    action_key: str
    latest_send_at_monotonic: float  # 超过此单调时间不得发出 POST

    def __post_init__(self) -> None:
        if self.attempt_no <= 0 or self.plan_revision <= 0:
            raise ValueError("动作尝试序号和计划版本必须从 1 开始")
        if self.action_key != canonical_action_key(self.action):
            raise ValueError("action_key 必须与规范动作一致")


@dataclass(frozen=True)
class SubmitAccepted:
    """官方已经明确接收动作。"""

    official_code: Optional[str]
    authoritative_seq: Optional[int]


@dataclass(frozen=True)
class SubmitRejectedRetryable:
    """官方明确未执行动作，刷新后同一窗口仍需要我方行动。"""

    official_code: str
    rejected_action_key: str
    refreshed_window: ObservedActionWindow


@dataclass(frozen=True)
class SubmitRejectedClosed:
    """官方明确未执行动作，但刷新后原窗口已经关闭。"""

    official_code: str
    latest_authoritative_seq: int


@dataclass(frozen=True)
class SubmitRejectedNoRefresh:
    """官方明确未执行动作且 POST 已发出，但没有取得权威刷新。

    语义（2026-09-04 集成阶段裁定，批准 contract-change-request 方案 A）：

    - 动作 POST 已实际发出（审计 sent_attempts 计数 +1）；
    - 官方已明确该动作未执行（如 POST 429，或 409 后刷新失败/不可用——
      409 本身已确认未执行）；
    - 没有取得可用于重新规划的权威刷新；
    - 应用层必须终结原窗口，不得在同一窗口追加提交；
    - 不得记作 ``SubmitNotSent``（未发 POST）、``SubmitAmbiguous``
      （结果不确定）或 ``SubmitRejectedClosed``（权威确认关闭）。
    """

    official_code: str
    rejected_action_key: str
    latest_local_seq: int  # 刷新失败时本地已确认的最后权威序号；不是刷新结果
    reason: str


@dataclass(frozen=True)
class SubmitAmbiguous:
    """无法确认动作是否执行；相同窗口禁止追加动作。"""

    recovery_id: str
    reason: str


@dataclass(frozen=True)
class SubmitNotSent:
    """因截止时间、窗口失效或动作门拒绝而没有发出 POST。"""

    reason: str


@dataclass(frozen=True)
class SubmitFatal:
    """认证、授权或协议错误使当前身份无法继续安全提交。"""

    official_code: Optional[str]
    reason: str


SubmitOutcome = Union[
    SubmitAccepted,
    SubmitRejectedRetryable,
    SubmitRejectedClosed,
    SubmitRejectedNoRefresh,
    SubmitAmbiguous,
    SubmitNotSent,
    SubmitFatal,
]


class AuditKind(str, Enum):
    """第一阶段必须保存的审计事件种类。"""

    RUN_MANIFEST = "run_manifest"
    LIFECYCLE_CHANGED = "lifecycle_changed"
    AUTHORITATIVE_STATE = "authoritative_state"
    RAW_PROTOCOL_STATE = "raw_protocol_state"
    DECISION_PLANNED = "decision_planned"
    SUBMISSION_INTENT = "submission_intent"
    SUBMISSION_OUTCOME = "submission_outcome"
    PROTOCOL_RECOVERED = "protocol_recovered"
    GAME_FINISHED = "game_finished"
    PARTICIPANT_FINISHED = "participant_finished"


@dataclass(frozen=True)
class AuditContext:
    """审计关联键；无对应层级时字段允许为空。"""

    run_id: str
    tournament_id: str
    participant_id: str
    stage_attempt_id: Optional[str] = None
    game_id: Optional[str] = None
    round_no: Optional[int] = None
    trigger_seq: Optional[int] = None
    decision_id: Optional[str] = None
    attempt_no: Optional[int] = None


@dataclass(frozen=True)
class AuditRecord:
    """已脱敏审计信封；``payload`` 仅含 JSON 值并符合对应版本化结构。"""

    schema_version: int
    kind: AuditKind
    context: AuditContext
    wall_time_unix_ms: int
    monotonic_ns: int
    payload: Mapping[str, object]


@dataclass(frozen=True)
class AuditReceipt:
    """非阻塞入队结果；失败不得向动作路径抛异常。"""

    queued: bool
    audit_degraded: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class AuditSummary:
    """关闭记录器时返回的覆盖统计。"""

    written: int
    dropped_low_priority: int
    missing_high_priority: int
    serialization_failures: int
    audit_degraded: bool


class GameSessionPort(Protocol):
    """一个 ``game_id`` 的权威窗口、同步恢复与串行动作提交接缝。"""

    async def next_item(self) -> GameItem:
        """返回下一动作窗口、场次终局或分类故障；支持异步取消。"""

        ...

    async def submit(self, attempt: ActionAttempt) -> SubmitOutcome:
        """最多保持一个在途 POST；结果类型决定是否允许重新规划。"""

        ...

    async def aclose(self, reason: str) -> None:
        """取消最长 30 秒的挂起轮询，但不关闭同 Token 的共享传输。"""

        ...


class TournamentSessionPort(Protocol):
    """一个 Token 对应的跨阶段赛事会话接缝。"""

    async def initialize(self, target: RuntimeTarget) -> InitializeOutcome:
        """发现版本、身份、目标和配置；没有报名或到位副作用。"""

        ...

    async def register(self) -> RegistrationOutcome:
        """执行幂等报名。"""

        ...

    async def ready(self, expected_stage: StageIdentity) -> ReadyOutcome:
        """执行指定阶段的幂等到位；调用方决定是否应当调用。"""

        ...

    async def next_update(self) -> Union[TournamentSnapshot, ParticipantTerminal]:
        """等待赛事事实变化；``active_games`` 为空不是终态。"""

        ...

    def open_game(self, game_id: str) -> GameSessionPort:
        """创建共享当前 Token 传输和限速器的单场会话。"""

        ...

    async def aclose(self) -> None:
        """取消所有挂起请求并释放当前 Token 的连接池。"""

        ...


class AuditSink(Protocol):
    """接收已脱敏审计事件的非阻塞接缝。"""

    def emit(self, record: AuditRecord) -> AuditReceipt:
        """同步快照后立即入队且不抛异常；高优先级丢失必须标记降级。"""

        ...

    async def aclose(self, timeout_seconds: float) -> AuditSummary:
        """在限定秒数内尽力刷新并返回写入与丢失统计。"""

        ...
