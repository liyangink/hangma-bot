"""应用层端口与跨模块消息；具体官方 DTO 不得进入本文件。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping, Optional, Protocol, Tuple, Union

from hangma_bot.kernel.actions import Action, WindowKey, action_key as canonical_action_key
from hangma_bot.kernel.config import TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext, PlayerObservation


class RuntimeMode(str, Enum):
    """用于防止测试身份和正式身份混接。"""

    TEST_ROOM = "test_room"
    TEST_TOURNAMENT = "test_tournament"
    OFFICIAL_TOURNAMENT = "official_tournament"
    AUTO_MATCH = "auto_match"


@dataclass(frozen=True)
class RuntimeTarget:
    """启动时必须核对的运行目标；不包含 Token 原文。

    AUTO_MATCH 模式下 ``expected_tournament_id`` 允许为空字符串，表示尚未
    发现目标自动房（由显式 POST /api/match 入席后发现并回填）；非空表示
    只恢复该已知自动房、不创建新房。其他模式仍必须指定非空目标。
    """

    mode: RuntimeMode
    expected_tournament_id: str
    known_guide_version: int

    def __post_init__(self) -> None:
        if not self.expected_tournament_id and self.mode is not RuntimeMode.AUTO_MATCH:
            raise ValueError(
                "非 AUTO_MATCH 模式必须指定非空 expected_tournament_id；"
                "只有 AUTO_MATCH 允许空值表示尚未发现自动房"
            )


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
    # 以下两个是自动匹配（AUTO_MATCH）初始化停止的专用终态（parallel-v1 受控扩展）：
    MATCHING_UNAVAILABLE = "matching_unavailable"  # 暂不可匹配，或入席结果不确定且恢复证据不足
    CAPACITY_LIMIT = "capacity_limit"  # 资源/声明上限不符（如 MATCH_LIMIT_REACHED）；不误标淘汰或鉴权失败


@dataclass(frozen=True)
class ParticipantTerminal:
    """当前 Token 对应身份的终态。"""

    reason: ParticipantTerminalReason
    last_snapshot: Optional[TournamentSnapshot]
    detail: str


@dataclass(frozen=True)
class SessionBootstrap:
    """版本、身份、目标和规则发现结果。

    旧三种模式的初始化本身不报名或到位；AUTO_MATCH 模式（parallel-v1
    受控例外）的 OfficialAutoMatchSession 在目标为空且已确认无已有自动房
    归属时，允许一次显式 POST /api/match 入席。无论哪种模式，成功返回的
    ``tournament_id``/``participant_id`` 必须是已核实的非空事实：自动房以
    经确认的 room_id 作为 ``tournament_id`` 值，不得存放空占位或假造
    官方 ID。
    """

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
    expires_at_monotonic: Optional[float] = None  # 本机单调时钟秒；缺少可对齐的官方截止时为空
    deadline_is_estimated: bool = True  # True 表示仅有本地估计；不得冒充官方剩余时间

    def __post_init__(self) -> None:
        if not isfinite(self.received_at_monotonic):
            raise ValueError("窗口接收时间必须是有限单调时钟秒数")
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("动作窗口持续时间必须为正数")
        if self.expires_at_monotonic is not None and not isfinite(self.expires_at_monotonic):
            raise ValueError("动作窗口截止必须是有限单调时钟秒数")
        if not isinstance(self.deadline_is_estimated, bool):
            raise ValueError("截止估计标记必须是布尔值")
        if not self.deadline_is_estimated and self.expires_at_monotonic is None:
            raise ValueError("官方明确截止不得为空")
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
    HTTP_REQUEST = "http_request"  # 每次真实 HTTP 调用开始/终结；正文另存原始事件，以 request_id 对账
    DECISION_PLANNED = "decision_planned"
    # audit-plus-v1 增强种类（2026-09-05 并行契约登记，方案 §3.2）：完整
    # 决策输入、提交前复核与决策终结证据。生产方为 application 层，payload
    # 带 capture_profile=audit-plus-v1（词表见 application/audit_codec.py）。
    DECISION_INPUT = "decision_input"
    CANDIDATE_VALIDATED = "candidate_validated"
    DECISION_ENDED = "decision_ended"
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


# 适配器层 SUBMISSION_OUTCOME 的规范 reason 值（wv6 契约钉死）：POST 在途
# 被取消（task.cancel）时官方适配器以 SubmitAmbiguous + 本 reason 落审计，
# 记录器验证器据此豁免"每个实际发出的 POST 必须有响应原文"的对账
# （响应是否到达不可知、无原文可录）。game.py 生产与 validator.py 消费
# 必须引用同一常量：任一侧漂移即对账契约违约（回归测试锁定）。
SUBMISSION_CANCELLED_IN_FLIGHT = "submit_cancelled_in_flight"


class GameSessionPort(Protocol):
    """一个 ``game_id`` 的权威窗口、同步恢复与串行动作提交接缝。"""

    async def next_item(self) -> GameItem:
        """返回下一动作窗口、场次终局或分类故障；支持异步取消。

        取消完成后、aclose 前可以换一个消费者继续串行读取，用于只读
        终局收集；同一时刻不得有两个消费者。
        """

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
