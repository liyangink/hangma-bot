"""唯一组合根：把六个模块组装成可运行、可降级、可审计的单个参赛身份。

设计边界（根 AGENTS.md 第 5 节、架构图第 3 节）：

- 本文件是全仓唯一允许创建具体 HTTP 客户端、规则实例、策略、记录器与
  运行时的地方；业务模块禁止在内部创建这些具体实现或全局单例。
- 每次调用 :func:`build_runtime` 得到的 :class:`AssembledRuntime` 恰好对应
  一个 Token（一个身份）：其官方赛事会话与最多 ``config.M`` 个场次共享
  同一传输与限速器，审计目录按 ``runs/{run_id}`` 隔离；测试房间用四个
  进程各组装一个实例（见 ``scripts/run_test_room.py``）。
- Token 原文只进入 ``OfficialTransport`` 构造参数；任何导出类型的 repr、
  日志与审计路径都不得包含 Token。
- 可降级：规则/策略/审计任一环节失败都不阻断动作保底路径（由各模块
  自身保证），本文件只负责把生产实现接在一起，不注入任何业务逻辑。

组装产物关系（箭头为调用方向）：

```text
build_runtime(RuntimeConfig)
  ├─ JsonlAuditSink(audit_root, run_id)          # 审计磁盘副作用
  ├─ OfficialTournamentSession(token, ...)       # 官方赛事/场次端口实现
  ├─ _IdentityAwareSession(inner)                # 初始化后发现身份并更新审计上下文
  ├─ BotPolicy（weighted_heuristic / safe_fallback）
  └─ ParticipantRuntime(session, policy, sink, target)
```

Token 与模式核对（scripts 验收）：``token_kind`` 与 ``mode`` 必须匹配，
测试身份不得以正式赛事模式启动，正式身份不得以测试模式启动；
错配在组装期即拒绝，不建立任何网络连接。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, FrozenSet, Mapping, Optional
from urllib.parse import urlsplit

from hangma_bot.adapters.official import (
    OfficialAutoMatchSession,
    OfficialTournamentSession,
    TransportConfig,
)
from hangma_bot.adapters.official.scheduler import DEFAULT_STATE_ARRIVAL_GUARD_SEC
from hangma_bot.adapters.official.deadline_clock import DEADLINE_CLOCK_VERSION
from hangma_bot.adapters.recording import JsonlAuditSink
from hangma_bot.application.auto_match_runtime import AutoMatchRuntime, AutoMatchSettings
from hangma_bot.application.contracts import (
    AuditContext,
    GameSessionPort,
    RuntimeMode,
    RuntimeTarget,
    SessionBootstrap,
    TournamentSessionPort,
)
from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.application.ids import IdGenerator, PrefixedUuidIds
from hangma_bot.application.participant_runtime import ParticipantRuntime
from hangma_bot.application.tournament_supervisor import SupervisionPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.interface import BotPolicy, DecisionRequest
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy
from hangma_bot.policy.heuristic_v1 import ReliableHeuristicPolicyV1
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.balanced_shadow import V2BalancedShadowPolicy
from hangma_bot.policy.hu_upgrade_calibration import (
    RISK_CELLS, RISK_RULESET_VERSION, RISK_VERSION, SAFETY_MARGIN,
)

from hangma_bot.policy.white_discard_guard import WhiteDiscardGuardPolicy
from hangma_bot.policy.catch_play_probe import CatchPlayProbePolicy
from hangma_bot.policy.legacy_pass import LegacyWeightedHeuristicPolicy, LegacyClaimIfLegalPolicy
from hangma_bot.application.audit_codec import (
    decision_budget_from_json,
    decision_request_from_json,
)
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from hangma_bot.simulation.artifacts import compute_rules_hash, hand_math_runtime_metadata

if TYPE_CHECKING:
    from hangma_bot.kernel.outcomes import HandOutcomeObjective, OutcomeModelVersion
    from hangma_bot.learning.outcome_model import OutcomePredictor
    from hangma_bot.policy.outcome_policy import OutcomePolicy

DEFAULT_STRATEGY = "weighted_heuristic"

# 本地规则语义版本（非官方字段）；进入官方会话的审计 manifest 与启动核对
# 清单，用于区分「平台指南版本」与「本地规则引擎语义版本」。
DEFAULT_RULESET_VERSION = "hangma-mvp-v10-public-counts"


def build_outcome_policy(
    *, baseline: BotPolicy, predictor: OutcomePredictor | None,
    expected_version: OutcomeModelVersion,
    rule_config: RuleConfig, rules_source_hash: str,
    objective: Callable[[DecisionRequest], HandOutcomeObjective],
    monotonic: Callable[[], float] = time.monotonic,
) -> OutcomePolicy:
    """显式组装离线/候选结果策略，不增加线上默认枚举或自动加载制品。

    baseline 是完整可靠基线；predictor 是 OutcomeQuery 到 OutcomeBatch 的
    异步函数或 None；objective 从 DecisionRequest 的可见事实生成单局目标。
    expected_version 固定本批模型适用条件；rule_config/rules_source_hash 必须
    来自实际运行规则，不能复制模型声明。monotonic 返回单调时钟秒。
    后续模型装载在组合根完成，policy 不访问模型文件。
    """
    from hangma_bot.policy.outcome_policy import OutcomePolicy
    from hangma_bot.kernel.outcome_codec import rules_context_key

    return OutcomePolicy(baseline=baseline, fallback=SafeFallbackPolicy(), predictor=predictor,
                         expected_version=expected_version, objective=objective, monotonic=monotonic,
                         runtime_rules_hash=rules_context_key(rule_config, rules_source_hash))

# 策略名 → 工厂；只有存在两个真实实现时才保留接缝（根 AGENTS.md 第 5 节）。
# claim_if_legal 仅用于官方测试房验收（配置项选择），默认策略不变。
_STRATEGY_FACTORIES: Mapping[str, Callable[[], BotPolicy]] = {
    "weighted_heuristic": lambda: LegacyWeightedHeuristicPolicy(),
    "weighted_heuristic_v1": lambda: ReliableHeuristicPolicyV1(),
    "weighted_heuristic_v2": lambda: ComparableHeuristicPolicyV2(),
    "v2_hu_upgrade_v1": lambda: V2HuUpgradePolicy(
        risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
    ),
    # 已淘汰的实验臂（Tier-B 概率档 / 庄位权重 v1+v2 / 一摸价值层叠加 / 风险表 v3
    # / "等胡 x 护白"组合）已于 2026-09-11 移出可用策略清单。它们分别被证明为
    # **显著负**、**显著负**、**无增益**、**结构性空操作**、**结构性空操作**；
    # 证据见 review/heuristic-balanced-2026-09-10/README.md 与 PLAN.md 的方向表。
    # 研究记录保留在 review/，但不再作为可配置策略暴露。
    "v2_balanced_shadow_v1": lambda: V2BalancedShadowPolicy(
        baseline=V2HuUpgradePolicy(
            risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
        ),
    ),

    # 注：weighted_heuristic_v2_white_guard 保留。2026-09-11 实测证明它在 V2 与
    # Tier-A 上都是**零行为差异**（各 256 桌、符号检验 0 正/0 负/256 平），但它
    # 已被 21 处非 review 引用（测试、脚本、对手池）使用，移除会波及其它工作线；
    # 作为可选项保留，但在策略目录中标注为"已证明不改变任何决策"。
    "weighted_heuristic_v2_white_guard": lambda: WhiteDiscardGuardPolicy(ComparableHeuristicPolicyV2()),
    "safe_fallback": lambda: SafeFallbackPolicy(),
    "claim_if_legal": lambda: LegacyClaimIfLegalPolicy(),
    "catch_play_probe": lambda: CatchPlayProbePolicy(ComparableHeuristicPolicyV2()),
}

# 序列策略网络候选：策略名 → 部署包子目录名。基线固定为完整 V2（与训练时的
# "完整 V2" 对手同源），因此这些候选与 V2 的差别只来自网络排序本身。
# 【发布前须知】三个候选都尚未证明优于或不劣于 V2：正式开发比较的八项同时区间
# 全部跨零（混合池点估计 +1.28 ～ +2.86 分/桌）。它们用于真实环境实测取数，
# 不是已验证的强度提升；默认策略仍是 DEFAULT_STRATEGY，必须显式配置才会启用。
_SEQUENCE_MODEL_STRATEGIES: Mapping[str, str] = {
    "sequence_model_2048_projected_v1": "2048-projected",
    "sequence_model_4096_direct_v1": "4096-direct",
    "sequence_model_4096_projected_v1": "4096-projected",
}

# 全部可配置策略名的唯一来源。启动脚本（run_test_room.py 等）与 RuntimeConfig
# 校验都必须引用本常量，不得各自维护副本——否则会出现"组合根已支持、启动器
# 白名单却拒绝"的静默漂移（2026-09-14 序列模型接入即发生过一次）。
AVAILABLE_STRATEGIES: tuple[str, ...] = tuple(_STRATEGY_FACTORIES) + tuple(_SEQUENCE_MODEL_STRATEGIES)

# 默认部署包根目录；可用 RuntimeConfig.sequence_model_dir 覆盖。相对路径按
# 仓库根解析，模型权重随仓库分发，不从训练工作区读取。
SEQUENCE_MODEL_DIRNAME = "prebuilt/sequence-policy-models"

# 需要启用条件分值规则增强的策略。序列网络输入含 13 维条件分值，训练时按
# ValueAnalysisLimits() 生成；关闭增强会让这些维度退化为零，构成训练/服务偏移，
# 因此这些策略必须与实际运行规则同一口径，并在校准范围外直接拒绝启动。
_VALUE_ANALYSIS_STRATEGIES = (
    "v2_hu_upgrade_v1", "v2_balanced_shadow_v1",
) + tuple(_SEQUENCE_MODEL_STRATEGIES)


def _sequence_model_policy(config, monotonic: Callable[[], float] = time.monotonic) -> BotPolicy:
    """装载一个序列策略网络候选；装载失败即启动失败，不静默降级成另一个策略。

    先建立完整 V2 基线与紧急保底，再注入网络。制品声明的规则配置必须与
    实际运行配置逐项相等，否则装载期就拒绝——这比运行期回退更早暴露错配。
    """
    from dataclasses import asdict

    from hangma_bot.learning.sequence_model_artifact import load_sequence_model
    from hangma_bot.policy.sequence_model_policy import SequenceModelPolicy

    root = config.sequence_model_dir
    if root is None:
        root = _REPO_ROOT / SEQUENCE_MODEL_DIRNAME
    directory = Path(root) / _SEQUENCE_MODEL_STRATEGIES[config.strategy]
    network, artifact = load_sequence_model(directory)
    runtime_rules = RuleConfig(DEFAULT_RULESET_VERSION, 1, False)
    if asdict(runtime_rules) != artifact.rule_config:
        raise ValueError("序列策略制品声明的规则配置与本机运行规则不一致")
    baseline = V2HuUpgradePolicy(
        risk_cells=RISK_CELLS, risk_version=RISK_VERSION, safety_margin=SAFETY_MARGIN,
    )
    return SequenceModelPolicy(baseline=baseline, fallback=SafeFallbackPolicy(), network=network,
                               artifact=artifact, runtime_rules=runtime_rules, monotonic=monotonic)


def _build_policy(config, monotonic: Callable[[], float] = time.monotonic) -> BotPolicy:
    """按运行配置构造策略；模型类候选走显式装载，其余走原工厂表。"""

    if config.strategy in _SEQUENCE_MODEL_STRATEGIES:
        return _sequence_model_policy(config, monotonic)
    return _STRATEGY_FACTORIES[config.strategy]()


class TokenKind(str, Enum):
    """Token 用途类别；与 RuntimeMode 交叉核对，防止测试/正式身份混接。"""

    TEST = "test"
    OFFICIAL = "official"


# 允许的模式组合；正式赛事只能用正式 Token，测试房间/测试赛事只能用测试 Token。
# AUTO_MATCH（自动匹配）仅用于全局 Token 的新入口；不把全局 Token 放行到旧赛事流程
# （旧流程作用域检查由对应会话实现执行）。
_MODE_TOKEN_KIND: Mapping[RuntimeMode, TokenKind] = {
    RuntimeMode.TEST_ROOM: TokenKind.TEST,
    RuntimeMode.TEST_TOURNAMENT: TokenKind.TEST,
    RuntimeMode.OFFICIAL_TOURNAMENT: TokenKind.OFFICIAL,
    RuntimeMode.AUTO_MATCH: TokenKind.OFFICIAL,
}


def _require_bool(value: object, field_name: str) -> bool:
    """严格布尔校验：拒绝字符串 "true"/"false" 等隐式转换形态。"""

    if not isinstance(value, bool):
        raise ValueError("{0} 必须是布尔，得到 {1!r}".format(field_name, value))
    return value


def _require_non_empty_str(value: object, field_name: str) -> str:
    """非空字符串校验；与 kernel 的校验口径一致，错误在组装期暴露。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("{0} 必须是非空字符串，得到 {1!r}".format(field_name, value))
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    """正整数校验；bool 是 int 子类，必须显式排除。"""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("{0} 必须是正整数，得到 {1!r}".format(field_name, value))
    return value


@dataclass(frozen=True)
class RuntimeConfig:
    """单个身份启动所需的全部配置；Token 已解析为原文，仅存在于本值对象内。

    ``repr`` 固定掩码 Token；任何日志、异常或审计路径都不得打印本对象之外
    的 Token 副本。字段：

    - ``mode``：运行模式，与 ``token_kind`` 交叉核对；
    - ``base_url``：官方平台基址（http/https），仅对该主机白名单可关闭 TLS 校验；
    - ``expected_tournament_id``：目标赛事；初始化时与平台事实核对；
      AUTO_MATCH 模式允许为空字符串（尚未发现自动房，由显式 match 入席发现），
      非空表示只恢复该已知自动房；其他模式必须非空；
    - ``known_guide_version``：本地已适配的官方指南版本下限；
    - ``token``：敏感凭证；只进入官方传输的认证头；
    - ``token_kind``：Token 用途类别（test/official）；
    - ``audit_root``：审计根目录（其下生成 runs/{run_id}/...）；
    - ``strategy``：策略名，取值见 ``_STRATEGY_FACTORIES`` 与
      ``_SEQUENCE_MODEL_STRATEGIES``（后者需要仓库内或显式指定的模型部署包）；
    - ``sequence_model_dir``：序列策略网络部署包根目录；仅模型类策略使用，
    - ``insecure_hosts``：允许关闭 TLS 校验的官方内网主机白名单（默认空）；
    - ``slot``：可选身份槽位标签（测试房间 A—D），只用于日志定位；
    - ``audit_raw_gzip``：原始事件（RAW_PROTOCOL_STATE）gzip 分段落盘开关
      （F-08；默认关——普通盘位无需压缩，长期/多赛事运行建议开启）；
    - ``audit_raw_rotate_bytes``：gzip 单段未压缩字节上限（默认 32MB，
      只分段不丢弃；仅 audit_raw_gzip=True 时生效）。
    """

    mode: RuntimeMode
    base_url: str
    expected_tournament_id: str
    known_guide_version: int
    token: str
    token_kind: TokenKind
    audit_root: Path
    strategy: str = DEFAULT_STRATEGY
    insecure_hosts: FrozenSet[str] = frozenset()
    slot: Optional[str] = None
    audit_raw_gzip: bool = False
    audit_raw_rotate_bytes: int = 32 * 1024 * 1024
    # 序列策略网络部署包根目录；仅 ``strategy`` 取 ``_SEQUENCE_MODEL_STRATEGIES``
    # 的键时使用。None 表示取仓库内 ``prebuilt/sequence-policy-models``。
    sequence_model_dir: Optional[Path] = None
    # SSE 帧驱动开关（2026-09-05 接入，默认关）：开启后各场次在长轮询之外
    # 兼容旧配置；生产组合根固定使用 state，实际生效值写入运行清单。
    sse_enabled: bool = False
    # 部署配置中的逻辑平台实例名（契约 §4.1）：同一官方平台跨地址/节点
    # 保持相同，进入审计 RUN_MANIFEST 与统一牌谱身份；不是 Token、主机名
    # 或 Git 分支。默认 hangma-official，按部署覆盖。
    source_namespace: str = "hangma-official"

    def __post_init__(self) -> None:
        if not isinstance(self.mode, RuntimeMode):
            raise ValueError("mode 必须是 RuntimeMode 枚举值，得到 {0!r}".format(self.mode))
        _require_non_empty_str(self.base_url, "RuntimeConfig.base_url")
        scheme = urlsplit(self.base_url).scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError("base_url 必须以 http:// 或 https:// 开头，得到 {0!r}".format(self.base_url))
        if self.mode is not RuntimeMode.AUTO_MATCH:
            _require_non_empty_str(self.expected_tournament_id, "RuntimeConfig.expected_tournament_id")
        _require_positive_int(self.known_guide_version, "RuntimeConfig.known_guide_version")
        _require_non_empty_str(self.token, "RuntimeConfig.token")
        if not isinstance(self.token_kind, TokenKind):
            raise ValueError("token_kind 必须是 TokenKind 枚举值，得到 {0!r}".format(self.token_kind))
        if _MODE_TOKEN_KIND[self.mode] is not self.token_kind:
            raise ValueError(
                "模式与 Token 类别不匹配：mode={0} 要求 token_kind={1}，得到 {2}；"
                "测试身份不得以正式赛事模式启动，正式身份不得以测试模式启动".format(
                    self.mode.value, _MODE_TOKEN_KIND[self.mode].value, self.token_kind.value
                )
            )
        if not isinstance(self.audit_root, Path):
            raise ValueError("audit_root 必须是 Path，得到 {0!r}".format(self.audit_root))
        _require_non_empty_str(self.strategy, "RuntimeConfig.strategy")
        if self.strategy not in AVAILABLE_STRATEGIES:
            raise ValueError(
                "未知策略名 {0!r}；可用：{1}".format(
                    self.strategy, " / ".join(sorted(AVAILABLE_STRATEGIES))
                )
            )
        # 2026-09-11 接线变更：v2_hu_upgrade_v1（Tier-A）**解除模式限制**，
        # 现在四种模式（test_room / test_tournament / official_tournament / auto_match）
        # 均可显式选择。依据是它已通过本地门禁的全部五项判据——完整桌赛净分正、
        # 按根聚类 95% 区间下界为正（+4.586 [2.784, 6.388]，256 根）、精确二项符号检验
        # 显著（56/6，p<1e-4）、第一名比例不退化、时限与降级计数全 0。
        #
        # 【发布前须知】本地门禁不能替代官方测试赛事门禁。真实房 2 对 2 配对 A/B
        # 功效不足（−9.30 [−27.65, +9.05]，每场配对差 sd 29.6），强对手池重跑
        # +1.945 [−0.445, +4.219] 不显著。对外部对手的预期收益应按 +2 量级估计，
        # 不要按 +4.586 的对照读数外推。证据见 review/heuristic-balanced-2026-09-10/。
        #
        # 注意：放开的是**可选性**，默认值仍是 DEFAULT_STRATEGY（V0）；要用它必须在
        # 运行配置里显式写 "strategy": "v2_hu_upgrade_v1"。
        if self.strategy == "v2_balanced_shadow_v1" and self.mode not in (RuntimeMode.TEST_ROOM, RuntimeMode.AUTO_MATCH):
            raise ValueError("v2_balanced_shadow_v1 仅供研究/影子运行：它只追加路线审计理由、不改变动作顺序，不得用于正式赛事")

        if self.strategy == "catch_play_probe" and self.mode is not RuntimeMode.TEST_ROOM:
            raise ValueError("catch_play_probe 仅允许 mode=test_room；它主动弃白用于规则验证")
        if not isinstance(self.insecure_hosts, frozenset):
            raise ValueError("insecure_hosts 必须是 frozenset，得到 {0!r}".format(self.insecure_hosts))
        if self.slot is not None:
            _require_non_empty_str(self.slot, "RuntimeConfig.slot")
        if not isinstance(self.sse_enabled, bool):
            raise ValueError("RuntimeConfig.sse_enabled 必须是布尔值，得到 {0!r}".format(self.sse_enabled))
        _require_non_empty_str(self.source_namespace, "RuntimeConfig.source_namespace")
        if not isinstance(self.audit_raw_gzip, bool):
            raise ValueError("audit_raw_gzip 必须是布尔，得到 {0!r}".format(self.audit_raw_gzip))
        _require_positive_int(self.audit_raw_rotate_bytes, "RuntimeConfig.audit_raw_rotate_bytes")
        if self.sequence_model_dir is not None and not isinstance(self.sequence_model_dir, Path):
            raise ValueError("RuntimeConfig.sequence_model_dir 必须是 Path 或 None")

    def __repr__(self) -> str:
        """掩码 Token 的结构化描述；可用于日志，不泄漏凭证。"""

        return (
            "RuntimeConfig(mode={mode!r}, base_url={url!r}, expected_tournament_id={tid!r}, "
            "known_guide_version={guide!r}, token=<redacted>, token_kind={kind!r}, "
            "audit_root={root!r}, strategy={strategy!r}, slot={slot!r}, audit_raw_gzip={gzip!r}, audit_raw_rotate_bytes={rotate!r})"
        ).format(
            mode=self.mode.value,
            url=self.base_url,
            tid=self.expected_tournament_id,
            guide=self.known_guide_version,
            kind=self.token_kind.value,
            root=str(self.audit_root),
            strategy=self.strategy,
            slot=self.slot,
            gzip=self.audit_raw_gzip,
            rotate=self.audit_raw_rotate_bytes,
        )


def _optional_path(value: object, field_name: str) -> Optional[Path]:
    """把可空配置项转成 Path；None/缺省保持 None，其他类型明确拒绝。"""

    if value is None:
        return None
    return Path(_require_non_empty_str(value, field_name))


_CONFIG_FIELDS = frozenset({
    "mode",
    "base_url",
    "expected_tournament_id",
    "known_guide_version",
    "token",
    "token_env",
    "token_kind",
    "audit_root",
    "strategy",
    "insecure_hosts",
    "slot",
    "sse_enabled",
    "audit_raw_gzip",
    "audit_raw_rotate_bytes",
    "source_namespace",
    "sequence_model_dir",
})


def runtime_config_from_mapping(
    data: Mapping[str, object],
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> RuntimeConfig:
    """把运行配置映射（JSON 解析结果）转成已校验的 :class:`RuntimeConfig`。

    敏感凭证二选一：

    - ``token``：内联 Token 原文（适合私有运行配置文件，注意权限）；
    - ``token_env``：环境变量名，运行时从 ``environ``（缺省 ``os.environ``）读取，
      适合测试房间四进程编排（Token 只经环境变量传给子进程，不落盘）。

    未知键一律拒绝：启动配置是安全边界，拼写错误必须在组装期暴露，
    而不是静默忽略后带着错配目标开赛。
    """

    if not isinstance(data, Mapping):
        raise ValueError("运行配置必须是 JSON 对象")
    unknown = sorted(set(data) - _CONFIG_FIELDS)
    if unknown:
        raise ValueError("运行配置包含未知字段: {0}".format(", ".join(unknown)))
    env = os.environ if environ is None else environ

    mode_value = data.get("mode")
    try:
        mode = RuntimeMode(mode_value)
    except (ValueError, TypeError):
        raise ValueError("未知运行模式 {0!r}；可用：{1}".format(
            mode_value, ", ".join(item.value for item in RuntimeMode))) from None

    kind_value = data.get("token_kind")
    try:
        token_kind = TokenKind(kind_value)
    except (ValueError, TypeError):
        raise ValueError("未知 Token 类别 {0!r}；可用：test/official".format(kind_value)) from None

    inline_token = data.get("token")
    token_env = data.get("token_env")
    if inline_token is not None and token_env is not None:
        raise ValueError("token 与 token_env 只能二选一")
    if inline_token is not None:
        token = _require_non_empty_str(inline_token, "token")
    elif token_env is not None:
        env_name = _require_non_empty_str(token_env, "token_env")
        token = env.get(env_name)
        if not token or not token.strip():
            raise ValueError(
                "环境变量 {0} 未提供非空 Token；Token 原文不进入错误文本".format(env_name)
            )
    else:
        raise ValueError("运行配置必须提供 token 或 token_env 之一")

    audit_root_value = data.get("audit_root")
    audit_root = Path(_require_non_empty_str(audit_root_value, "audit_root"))
    hosts = data.get("insecure_hosts", [])
    if not isinstance(hosts, (list, tuple, frozenset, set)):
        raise ValueError("insecure_hosts 必须是数组")
    insecure_hosts = frozenset(_require_non_empty_str(item, "insecure_hosts 元素") for item in hosts)

    # AUTO_MATCH 允许缺省/空目标（尚未发现自动房）；提供了值则必须是非空字符串
    # （非空 = 只恢复该已知自动房）。其他模式必须提供非空目标。
    expected_tid_value = data.get("expected_tournament_id")
    if mode is RuntimeMode.AUTO_MATCH and expected_tid_value in (None, ""):
        expected_tournament_id = ""
    else:
        expected_tournament_id = _require_non_empty_str(
            expected_tid_value, "expected_tournament_id"
        )

    return RuntimeConfig(
        mode=mode,
        base_url=_require_non_empty_str(data.get("base_url"), "base_url"),
        expected_tournament_id=expected_tournament_id,
        known_guide_version=_require_positive_int(
            data.get("known_guide_version"), "known_guide_version"
        ),
        token=token,
        token_kind=token_kind,
        audit_root=audit_root,
        strategy=str(data.get("strategy", DEFAULT_STRATEGY)),
        insecure_hosts=insecure_hosts,
        slot=data.get("slot"),
        audit_raw_gzip=_require_bool(data.get("audit_raw_gzip", False), "audit_raw_gzip"),
        sse_enabled=_require_bool(data.get("sse_enabled", False), "sse_enabled"),
        audit_raw_rotate_bytes=_require_positive_int(
            data.get("audit_raw_rotate_bytes", 32 * 1024 * 1024),
            "audit_raw_rotate_bytes",
        ),
        source_namespace=_require_non_empty_str(
            data.get("source_namespace", "hangma-official"), "source_namespace"
        ),
        # 仅模型类策略使用；缺省 None 表示取仓库内预置部署包目录。
        sequence_model_dir=_optional_path(data.get("sequence_model_dir"), "sequence_model_dir"),
    )


class _AuditContextProvider:
    """官方适配器审计信封的上下文提供者；身份在初始化后发现。

    适配器在 initialize 期间即可发射审计（如指南版本观察），此时
    participant_id 尚不可知，按契约（接口协议第 7 节）以 "unknown" 占位；
    初始化成功返回 :class:`SessionBootstrap` 后由装配胶水更新真实身份，
    此后的记录都进入该身份的隔离目录。
    """

    def __init__(self, run_id: str, tournament_id: str) -> None:
        self._run_id = run_id
        # AUTO_MATCH 发现模式允许空目标（尚未发现自动房）：身份发现前的
        # 审计记录以 "unknown" 占位（与 participant_id 同一约定），避免
        # 验证器把空 tournament_id 判为信封不完整（审计线校验规则）。
        self._tournament_id = tournament_id or "unknown"
        self._participant_id = "unknown"

    def set_identity(self, tournament_id: str, participant_id: str) -> None:
        """初始化发现身份后更新；只调用一次（组合根内部使用）。"""

        self._tournament_id = tournament_id
        self._participant_id = participant_id

    @property
    def participant_id(self) -> Optional[str]:
        """已发现的脱敏身份；尚未发现时为 None（占位 "unknown" 不对外）。"""

        return None if self._participant_id == "unknown" else self._participant_id

    def context(self) -> AuditContext:
        """构造适配器层的审计上下文；不含 stage_attempt_id（适配器契约）。"""

        return AuditContext(
            run_id=self._run_id,
            tournament_id=self._tournament_id,
            participant_id=self._participant_id,
        )


class _FixedRunIds:
    """返回组合根预生成的 run_id，其余标识照常委托生产实现。

    为什么需要：审计目录 ``runs/{run_id}`` 在 sink 构造时就要确定，
    而 ParticipantRuntime 在 run() 时才生成 run_id；预生成并固定二者
    保证运行时使用的 run_id 与磁盘目录一致。
    """

    def __init__(self, delegate: IdGenerator, run_id: str) -> None:
        self._delegate = delegate
        self._run_id = run_id

    def new_run_id(self) -> str:
        return self._run_id

    def new_decision_id(self, window_key) -> str:
        return self._delegate.new_decision_id(window_key)

    def new_stage_attempt_id(self, stage_no) -> str:
        return self._delegate.new_stage_attempt_id(stage_no)


class _IdentityAwareSession:
    """协议级透明包装：初始化发现身份后更新审计上下文提供者。

    这是组合根内部的装配胶水，不改变任何端口语义：initialize 之外的
    所有调用原样转发。官方适配器按契约不得生成 stage_attempt_id，
    因此上下文只更新 run_id / tournament_id / participant_id。
    """

    def __init__(self, inner: TournamentSessionPort, provider: _AuditContextProvider) -> None:
        self._inner = inner
        self._provider = provider

    async def initialize(self, target: RuntimeTarget):
        result = await self._inner.initialize(target)
        if isinstance(result, SessionBootstrap):
            self._provider.set_identity(result.tournament_id, result.participant_id)
        return result

    async def register(self):
        return await self._inner.register()

    async def ready(self, expected_stage):
        return await self._inner.ready(expected_stage)

    async def next_update(self):
        return await self._inner.next_update()

    def open_game(self, game_id: str) -> GameSessionPort:
        return self._inner.open_game(game_id)

    def participant_id(self) -> Optional[str]:
        """初始化后发现的脱敏身份；未发现时为 None（供启动清单打印）。"""

        return self._provider.participant_id

    async def aclose(self) -> None:
        await self._inner.aclose()


@dataclass
class AssembledRuntime:
    """一次组装完成的单身份运行单元；只暴露可安全打印的状态。

    - ``run()``：运行到参赛者终态（委托 ParticipantRuntime，出口统一
      关闭会话并尽力冲刷审计）；
    - ``audit_degraded`` / ``last_audit_summary``：审计链的诚实降级状态，
      动作路径失败不影响其可审计性判定。
    """

    config: RuntimeConfig
    run_id: str
    sink: JsonlAuditSink
    session: TournamentSessionPort
    policy: BotPolicy
    runtime: ParticipantRuntime

    async def run(self):
        """运行到当前身份的参赛者终态；返回值类型见应用层契约。"""

        return await self.runtime.run()

    @property
    def audit_degraded(self) -> bool:
        return self.runtime.audit_degraded

    @property
    def last_audit_summary(self):
        return self.runtime.last_audit_summary

    @property
    def participant_id(self) -> Optional[str]:
        """初始化后发现的脱敏身份；尚未发现时为 None（供启动清单打印）。"""

        getter = getattr(self.session, "participant_id", None)
        return getter() if callable(getter) else None


def _test_room_upgrade_rules(config: RuleConfig) -> HangmaRules:
    """按平台实际配置核对校准范围；不匹配时在报名/到位之前终止候选身份。

    这是实验适用范围，绝不是把 YouCaiBiKao 固定成规则；其他策略仍按
    官方返回的开关运行。风险表来自 BaseScore=1、关闭必拷的 v10 独立模拟校准。
    """

    if (config.base_score != 1 or config.you_cai_bi_kao or
            config.ruleset_version != RISK_RULESET_VERSION):
        raise ValueError(
            "V2 实验策略测试范围要求 BaseScore=1、YouCaiBiKao=false、"
            "ruleset_version=" + RISK_RULESET_VERSION
        )
    return HangmaRules(config)


def build_runtime(
    config: RuntimeConfig,
    *,
    session_factory: Optional[Callable[[], TournamentSessionPort]] = None,
    policy_factory: Optional[Callable[[], BotPolicy]] = None,
) -> AssembledRuntime:
    """按配置组装一个单身份运行时；这是全仓唯一的组装入口。

    ``session_factory`` / ``policy_factory`` 仅用于集成测试注入 Fake 端口
    （不连平台验证生命周期与审计）；生产脚本不得传这两个参数。
    缺省组装官方会话、按 ``config.strategy`` 选择策略。
    """

    if not isinstance(config, RuntimeConfig):
        raise TypeError("config 必须是 RuntimeConfig")

    ids_source: IdGenerator = PrefixedUuidIds()
    run_id = ids_source.new_run_id()
    fixed_ids = _FixedRunIds(ids_source, run_id)

    # F-08：原始事件 gzip 分段按配置透传（默认关；笔记 E5 接线落地）
    sink = JsonlAuditSink(
        config.audit_root,
        run_id,
        raw_gzip=config.audit_raw_gzip,
        raw_rotate_bytes=config.audit_raw_rotate_bytes,
    )
    provider = _AuditContextProvider(run_id, config.expected_tournament_id)
    clock = SystemClock()

    if session_factory is None:
        inner: TournamentSessionPort = OfficialTournamentSession(
            token=config.token,
            transport_config=TransportConfig(
                base_url=config.base_url,
                insecure_hosts=config.insecure_hosts,
            ),
            monotonic_clock=clock.now,
            wall_clock_unix_ms=clock.unix_ms,
            audit=sink,
            audit_context=provider.context,
            ruleset_version=DEFAULT_RULESET_VERSION,
            # 官方 SSE 可选；观察完整性修复期仅运行 state 与阶段边界查询。
            sse_enabled=False,
            sse_budget=None,
        )
    else:
        inner = session_factory()
    session = _IdentityAwareSession(inner, provider)

    if policy_factory is not None:
        policy = policy_factory()
    else:
        policy = _build_policy(config)

    # audit-plus-v1 版本事实（契约 §4.2）：代码提交/脏状态、策略版本与
    # 生效权重、本地规则语义版本；缺省取不到为 null，不冒充已提交代码。
    git_commit, git_dirty = _git_state()
    budget_policy = BudgetPolicy()
    manifest_extra: Mapping[str, object] = {
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "policy_version": config.strategy,
        "policy_weights": _effective_weights_snapshot(policy),
        "ruleset_version": DEFAULT_RULESET_VERSION,
        "hand_math": hand_math_runtime_metadata(),
        "official_sync_mode": "state",
        "sse_requested": config.sse_enabled,
        "sse_effective": False,
        "budget_policy_version": "fixed-post-reserve-v1",
        "post_network_reserve_sec": budget_policy.post_reserve_seconds,
        "state_arrival_guard_sec": DEFAULT_STATE_ARRIVAL_GUARD_SEC,
        "state_scheduler_version": "send-boundary-guard-v1",
        "deadline_clock_version": DEADLINE_CLOCK_VERSION,
    }
    runtime = ParticipantRuntime(
        session=session,
        policy=policy,
        audit_sink=sink,
        target=RuntimeTarget(
            mode=config.mode,
            expected_tournament_id=config.expected_tournament_id,
            known_guide_version=config.known_guide_version,
        ),
        rules_factory=(_test_room_upgrade_rules if config.strategy in _VALUE_ANALYSIS_STRATEGIES else HangmaRules),
        value_limits=(ValueAnalysisLimits() if config.strategy in _VALUE_ANALYSIS_STRATEGIES else None),
        clock=clock,
        ids=fixed_ids,
        budget_policy=budget_policy,
        supervision=SupervisionPolicy(),
        source_namespace=config.source_namespace,
        manifest_extra=manifest_extra,
    )
    return AssembledRuntime(
        config=config,
        run_id=run_id,
        sink=sink,
        session=session,
        policy=policy,
        runtime=runtime,
    )


@dataclass
class AssembledAutoMatchRuntime:
    """一次 AUTO_MATCH 自动房运行的组装单元；字段语义与 AssembledRuntime 一致。

    - ``run()``：运行一次自动房操作到参赛者终态（委托 AutoMatchRuntime，
      出口统一关闭会话并限时冲刷审计）；
    - ``audit_degraded`` / ``last_audit_summary`` / ``participant_id``：
      与 AssembledRuntime 同名同义，供启动脚本与守护打印核对清单。
    """

    config: RuntimeConfig
    settings: AutoMatchSettings
    run_id: str
    sink: JsonlAuditSink
    session: TournamentSessionPort
    policy: BotPolicy
    runtime: AutoMatchRuntime

    async def run(self):
        """运行一次自动房操作；返回值类型见应用层契约。"""

        return await self.runtime.run()

    @property
    def audit_degraded(self) -> bool:
        return self.runtime.audit_degraded

    @property
    def last_audit_summary(self):
        return self.runtime.last_audit_summary

    @property
    def participant_id(self) -> Optional[str]:
        """初始化后发现的脱敏身份；尚未发现时为 None（供启动清单打印）。"""

        getter = getattr(self.session, "participant_id", None)
        return getter() if callable(getter) else None


def build_auto_match_runtime(
    config: RuntimeConfig,
    settings: AutoMatchSettings,
    *,
    session_factory: Optional[Callable[[], TournamentSessionPort]] = None,
    policy_factory: Optional[Callable[[], BotPolicy]] = None,
) -> AssembledAutoMatchRuntime:
    """装配一次 AUTO_MATCH 自动房运行（一个进程一个全局 Token，默认单会话）。

    注入顺序与 :func:`build_runtime` 一致：固定 run_id → JsonlAuditSink →
    _AuditContextProvider（身份发现前占位，initialize 成功后由
    _IdentityAwareSession 回填 user_id/room_id）→ OfficialAutoMatchSession
    （同一 Token 的 transport/scheduler；settings 提供声明上限与
    match 重试参数）→ 策略工厂 → AutoMatchRuntime。

    本函数只服务 mode=AUTO_MATCH；旧三种模式请使用 :func:`build_runtime`。
    ``session_factory`` / ``policy_factory`` 仅用于集成测试注入 Fake。
    """

    if not isinstance(config, RuntimeConfig):
        raise TypeError("config 必须是 RuntimeConfig")
    if config.mode is not RuntimeMode.AUTO_MATCH:
        raise ValueError(
            "build_auto_match_runtime 只服务 mode=auto_match，得到 {0!r}".format(config.mode.value)
        )

    ids_source: IdGenerator = PrefixedUuidIds()
    run_id = ids_source.new_run_id()
    fixed_ids = _FixedRunIds(ids_source, run_id)

    # F-08：原始事件 gzip 分段按配置透传（与 build_runtime 同口径）
    sink = JsonlAuditSink(
        config.audit_root,
        run_id,
        raw_gzip=config.audit_raw_gzip,
        raw_rotate_bytes=config.audit_raw_rotate_bytes,
    )
    provider = _AuditContextProvider(run_id, config.expected_tournament_id)
    clock = SystemClock()

    if session_factory is None:
        inner: TournamentSessionPort = OfficialAutoMatchSession(
            token=config.token,
            transport_config=TransportConfig(
                base_url=config.base_url,
                insecure_hosts=config.insecure_hosts,
            ),
            monotonic_clock=clock.now,
            wall_clock_unix_ms=clock.unix_ms,
            audit=sink,
            audit_context=provider.context,
            ruleset_version=DEFAULT_RULESET_VERSION,
            sse_enabled=False,
            sse_budget=None,
            # 自动匹配操作参数（运行配置注入；不是官方字段）
            declared_max_games=settings.declared_max_games,
            declared_rounds=settings.declared_rounds,
            match_min_interval_sec=settings.match_min_interval_sec,
            match_max_attempts=settings.match_max_attempts,
            match_busy_wait_cap_sec=settings.match_busy_wait_cap_sec,
            room_poll_interval_sec=settings.room_poll_interval_sec,
        )
    else:
        inner = session_factory()
    session = _IdentityAwareSession(inner, provider)

    if policy_factory is not None:
        policy = policy_factory()
    else:
        policy = _build_policy(config)

    # 与 build_runtime 同一口径的版本事实注入（audit-plus-v1 RUN_MANIFEST）。
    git_commit, git_dirty = _git_state()
    budget_policy = BudgetPolicy()
    manifest_extra: Mapping[str, object] = {
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "policy_version": config.strategy,
        "policy_weights": _effective_weights_snapshot(policy),
        "ruleset_version": DEFAULT_RULESET_VERSION,
        "hand_math": hand_math_runtime_metadata(),
        "official_sync_mode": "state",
        "sse_requested": config.sse_enabled,
        "sse_effective": False,
        "budget_policy_version": "fixed-post-reserve-v1",
        "post_network_reserve_sec": budget_policy.post_reserve_seconds,
        "state_arrival_guard_sec": DEFAULT_STATE_ARRIVAL_GUARD_SEC,
        "state_scheduler_version": "send-boundary-guard-v1",
        "deadline_clock_version": DEADLINE_CLOCK_VERSION,
    }
    runtime = AutoMatchRuntime(
        session=session,
        policy=policy,
        audit_sink=sink,
        target=RuntimeTarget(
            mode=config.mode,
            expected_tournament_id=config.expected_tournament_id,
            known_guide_version=config.known_guide_version,
        ),
        settings=settings,
        rules_factory=HangmaRules,
        value_limits=(ValueAnalysisLimits() if config.strategy in _VALUE_ANALYSIS_STRATEGIES else None),
        value_rules_scope=(RuleConfig(RISK_RULESET_VERSION, 1, False)
                           if config.strategy in _VALUE_ANALYSIS_STRATEGIES else None),
        clock=clock,
        ids=fixed_ids,
        budget_policy=budget_policy,
        supervision=SupervisionPolicy(),
        manifest_extra=manifest_extra,
    )
    return AssembledAutoMatchRuntime(
        config=config,
        settings=settings,
        run_id=run_id,
        sink=sink,
        session=session,
        policy=policy,
        runtime=runtime,
    )


# ---------------------------------------------------------------------------
# 评估线装配钩子（parallel-v1 C1/S-E 集成；2026-09-05）
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def build_public_archive_client(config: Mapping):
    """离线免认证采集客户端；仅对配置中明确列出的目标主机关闭 TLS 校验。

    不加载 Token，不跟随重定向，不使用隐式代理；调用方负责 with 关闭连接。
    """
    import httpx
    from urllib.parse import urlsplit

    base = str(config.get("base_url", ""))
    parsed = urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("采集配置需要不含凭证的 HTTP(S) base_url")
    verify = parsed.hostname not in config.get("insecure_hosts", [])
    return httpx.Client(base_url=base, verify=verify, trust_env=False, follow_redirects=False, timeout=30)


def _git_state() -> Tuple[Optional[str], Optional[bool]]:
    """组装期代码版本事实（HEAD 提交与工作树 dirty）；取不到为 None。"""

    import subprocess

    try:
        commit = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    try:
        status = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        dirty = bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        dirty = None
    return (commit or None), dirty


def _effective_weights_snapshot(policy: object) -> Optional[Mapping[str, object]]:
    """策略生效权重快照（类声明字段的当前值）；无权重参数的策略返回 None。

    审计制品必须记录「生效」参数而非仅声明值：声明为空时实际使用的是
    类默认权重，不落盘会破坏事后复现（E3 诊断教训 2026-09-06）。
    """

    if isinstance(policy, (WhiteDiscardGuardPolicy, CatchPlayProbePolicy)):
        return _effective_weights_snapshot(policy.base_policy)
    weights = getattr(policy, "_weights", None)
    if weights is None:
        return None
    cls = type(weights)
    snapshot = {
        name: getattr(weights, name)
        for name, value in vars(cls).items()
        if not name.startswith("_") and not callable(value)
    }
    if isinstance(policy, V2HuUpgradePolicy):
        snapshot.update(
            base_policy="weighted_heuristic_v2", upgrade_weight=policy._upgrade_weight,
            risk_version=policy._risk_version, safety_margin=policy._safety_margin,
            risk_cells=[dict(vars(cell)) for cell in policy._risk_cells],
        )
    return snapshot


def build_decision_codec() -> Mapping[str, Callable]:
    """评估线 decisions 命令的生产解码入口（审计 C1 codec 注入）。

    返回 {"decode_request", "decode_budget"}：decode_request 还原完整
    DecisionRequest；decode_budget 只恢复原预算三值（第二参数
    budget_origin_monotonic 由评估器单独用于截止时间平移，本钩子
    不延长任何截止时间）。
    """

    def decode_budget(payload: object, budget_origin_monotonic: float) -> object:
        # 原点平移由评估器 translate_budget 以 budget_origin_monotonic 为
        # 基准执行；本钩子只恢复 DecisionBudget 原值。
        return decision_budget_from_json(payload)

    return {
        "decode_request": decision_request_from_json,
        "decode_budget": decode_budget,
    }


def build_evaluation_runtime(kind: str, experiment) -> Optional[Mapping]:
    """评估线 matches 命令的真实运行时装配（E3：接真实 SimulationEngine）。

    只实现 kind="matches"：返回真实引擎与 MatchSpec/SimulationChoice
    值对象工厂；策略由评估脚本按实验声明的权重自行构建（不从本机
    默认配置继承未知权重），保底与紧急动作仍在评估器内按同一规则源
    准备。kind="decisions" 返回 None，脚本走显式装配回退。
    """
    if kind != "matches":
        return None
    rules = HangmaRules(experiment.tournament_config.rules)
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_REPO_ROOT))

    def spec_factory(**kwargs):
        # 评估器传入的 initial_scores 是列表；MatchSpec 契约要求座位向量元组。
        kwargs["initial_scores"] = tuple(kwargs["initial_scores"])
        return MatchSpec(**kwargs)

    return {
        "engine": engine,
        "spec_factory": spec_factory,
        "choice_factory": SimulationChoice,
    }


__all__ = [
    "AssembledAutoMatchRuntime",
    "AssembledRuntime",
    "DEFAULT_RULESET_VERSION",
    "DEFAULT_STRATEGY",
    "RuntimeConfig",
    "TokenKind",
    "build_auto_match_runtime",
    "build_decision_codec",
    "build_evaluation_runtime",
    "build_runtime",
    "runtime_config_from_mapping",
]
