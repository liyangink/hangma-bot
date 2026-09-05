"""评估结果行（MatchResult）、结果文件读写与产物 manifest。

本模块是评估线（parallel-v1）的结果文件层，只做数据与结构，不做统计推断：
- 「MatchResult」严格按共同契约 §7 定义：一行是一个统计单位的结果
  （完整桌赛、阶段或赛事 seed），不是单次决策的统计行；mock 来源永不进入
  强度结论。
- results.jsonl 的读写与结构校验；complete 一致性等语义校验单列函数，
  供汇总与报告调用，避免把"结构合法"误报成"可作强度证据"。
- 「EvaluationManifest」按契约 §4.2 固定字段生成；评估产物把
  replay_schema_version 换成 evaluation_schema_version。
- 身份哈希（hand_id / split_group_id）与 rules_hash 是本线按契约
  §4.1/§4.2 的消费实现，算法以 contract-vectors.json 为唯一验收依据。
  跨线唯一落点由主审集成时裁定（建议 kernel 或 offline 共享模块），
  集成后本文件可改为 re-export；见 handoffs/evaluation.md。

信息权限：本模块不读取 WorldState 字段，不实现任何规则算法。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple, Union

from hangma_bot.kernel.config import TournamentConfig
from hangma_bot.kernel.serialization import (
    tournament_config_from_json,
    tournament_config_to_json,
)

# 评估结果线格式版本；破坏性变更（删键、改含义、改单位、改信息权限）必须递增。
EVALUATION_SCHEMA_VERSION = 1
# manifest 线格式版本；固定字段见契约 §4.2。
MANIFEST_SCHEMA_VERSION = 1
# 本批共享契约标识（parallel-v1.json）。
CONTRACT_ID = "parallel-v1"
# 模拟产物的固定来源命名空间（契约 §4.1：模拟使用单独名称，不是 Token/主机名/分支）。
SIMULATION_SOURCE_NAMESPACE = "hangma-simulation"

# 合法来源种类；mock 只用于编排验证，永不进入强度结论（契约 §7）。
SOURCE_KINDS = (
    "simulation",
    "test_room",
    "auto_match",
    "test_tournament",
    "mock",
)
# 结果状态；blocked/超步数/异常一律不是 complete，也不能合成流局。
RESULT_STATUSES = ("complete", "partial", "void", "error")

SEAT_COUNT = 4

# 结果 JSON 值域：文件内只允许有限数值与基础容器（契约 §4.2）。
ResultJson = Union[None, bool, int, float, str, List["ResultJson"], Dict[str, "ResultJson"]]


# ---------------------------------------------------------------------------
# 身份哈希（契约 §4.1；本线消费实现，落点由主审集成时裁定）
# ---------------------------------------------------------------------------


def identity_digest(parts: list) -> str:
    """按契约 §4.1 的编码与摘要算法对 JSON 数组取 SHA-256 全量十六进制。

    编码固定：UTF-8、ensure_ascii=False、separators=(",", ":")、
    allow_nan=False。任何平台实现必须逐字节一致，不得改键序或编码参数。
    """
    payload = json.dumps(
        parts, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_identity_str(value: object, field_name: str) -> str:
    """身份字段必须是原样保留的非空字符串，不做 strip/大小写改写。"""
    if not isinstance(value, str) or not value:
        raise ValueError("{0} 必须是非空字符串且原样保留，得到 {1!r}".format(field_name, value))
    return value


def _require_round_no(value: object) -> int:
    """单局号必须是排除 bool 的正整数；牌谱缺失时不得猜测。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            "round_no 必须是排除 bool 的正整数，得到 {0!r}；牌谱缺失时不得猜测".format(value)
        )
    return value


def hand_id(source_namespace: str, tournament_id: str, game_id: str, round_no: int) -> str:
    """从权威场次身份生成跨机器稳定单局标识，不包含本地 run/attempt。

    将四项按给定顺序编码为 JSON 数组：ensure_ascii=False、
    separators=(',', ':')、allow_nan=False，再取 UTF-8 SHA-256 全长十六进制，
    前缀 hand-。前三项是非空字符串且不做 strip/大小写改写；round_no 是
    排除 bool 的正整数，牌谱缺失时不得猜测；错误输入抛 ValueError。
    （契约 §4.1 冻结语义；本函数是本线消费实现，唯一验收依据是
    contract-vectors.json 的 identity_cases。）
    """
    fields = (
        _require_identity_str(source_namespace, "source_namespace"),
        _require_identity_str(tournament_id, "tournament_id"),
        _require_identity_str(game_id, "game_id"),
        _require_round_no(round_no),
    )
    return "hand-" + identity_digest(list(fields))


def split_group_id(fields: list) -> str:
    """按契约 §4.1 生成数据划分组标识（前缀 split-）。

    官方取 [source_namespace, tournament_id]，模拟取
    [source_namespace, scenario_id]；键序固定，分组不包含策略版本。
    """
    if len(fields) != 2:
        raise ValueError("split_group_id 必须恰好两个字段，得到 {0} 项".format(len(fields)))
    cleaned = [_require_identity_str(item, "split 字段") for item in fields]
    return "split-" + identity_digest(cleaned)


def compute_rules_hash(repo_root: Path) -> str:
    """按契约 §4.2 计算规则源文件清单的稳定哈希（无前缀全量十六进制）。

    范围为 src/hangma_bot/hangma 下全部 .py 文件，按仓库相对 POSIX 路径
    排序，将 [path, 文件字节 SHA-256] 数组按 §4.1 编码再哈希；规则
    配置另存，不混入源文件 hash。跨机器复制不受 mtime 影响。
    """
    rules_dir = repo_root / "src" / "hangma_bot" / "hangma"
    entries = []
    for path in sorted(rules_dir.glob("*.py")):
        relative = path.relative_to(repo_root).as_posix()
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append([relative, file_hash])
    if not entries:
        raise ValueError("规则源文件清单为空: {0}".format(rules_dir))
    return identity_digest(entries)


# ---------------------------------------------------------------------------
# MatchResult：一行 = 一个统计单位的结果（契约 §7）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GameKey:
    """来源场次身份；键名与 index.jsonl 术语一致（契约 §5.2）。"""

    source_namespace: str  # 部署配置中的逻辑平台实例名；模拟固定 hangma-simulation
    tournament_id: str  # 测试房间取响应 room_id；模拟取 MatchSpec.scenario_id
    game_id: str  # 完整官方 game_id 原样；模拟取 MatchSpec.match_id

    def __post_init__(self) -> None:
        for field_name in ("source_namespace", "tournament_id", "game_id"):
            _require_identity_str(getattr(self, field_name), "GameKey." + field_name)


@dataclass(frozen=True)
class RuntimeCounts:
    """一次运行的行内故障计数；缺失指标为 null，不写成 0（契约 §7）。

    - timeouts：动作窗口内策略超预算/超时的次数
    - illegal_choices：策略产出未通过规则复核的选择次数
    - fallbacks：异常/超时按保底规则降级的次数
    - auto_actions：平台代打/自动动作次数（模拟恒为 0 或 null）
    - audit_missing：审计缺失计数（模拟线记录为 0）
    """

    timeouts: Optional[int] = None
    illegal_choices: Optional[int] = None
    fallbacks: Optional[int] = None
    auto_actions: Optional[int] = None
    audit_missing: Optional[int] = None

    def __post_init__(self) -> None:
        for field_name in ("timeouts", "illegal_choices", "fallbacks", "auto_actions", "audit_missing"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(
                    "RuntimeCounts.{0} 必须是非负整数或 null，得到 {1!r}".format(field_name, value)
                )


def _validate_seat_vector(
    value: object, field_name: str, *, allow_negative: bool
) -> Tuple[int, int, int, int]:
    """座位 0—3 四元向量；积分允许负分，计数/座位不允许。"""
    if not isinstance(value, (tuple, list)) or len(value) != SEAT_COUNT:
        raise ValueError("{0} 必须是长度为 4 的座位向量，得到 {1!r}".format(field_name, value))
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError("{0}[{1}] 必须是整数，得到 {2!r}".format(field_name, index, item))
        if not allow_negative and item < 0:
            raise ValueError("{0}[{1}] 不允许负数，得到 {2!r}".format(field_name, index, item))
    return (value[0], value[1], value[2], value[3])


@dataclass(frozen=True)
class MatchResult:
    """一个统计单位的结果行；字段语义见契约 §7。

    - seat_permutation：长度 4 的 0—3 排列，记录逻辑身份到实际座位映射
      （permutation[i] = 逻辑身份 i 的实际座位）。
    - official_ranks：官方排名向量或 null；本地分数排序另标方法，
      不能生成官方名次分。
    - status：complete 只在完整桌赛完成且分数可确认时使用；blocked、
      超步数、异常结束都是 error/partial，不是 complete，也不合成流局。
    """

    evaluation_schema_version: int
    result_id: str  # 唯一结果标识
    source_kind: str  # simulation/test_room/auto_match/test_tournament/mock
    scenario_id: Optional[str]  # 同牌山根组；官方无法控制牌山时为空
    pair_id: Optional[str]  # 成对比较组（同一复式配对）；非配对实验为空
    game_key: Optional[GameKey]
    config: Optional[TournamentConfig]
    policy_ids_by_seat: Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]
    seat_permutation: Tuple[int, int, int, int]
    expected_hands: Optional[int]  # 计划单局数；不足不可当作完整桌赛
    completed_hands: Optional[int]
    scores_before: Optional[Tuple[int, int, int, int]]  # 座位 0—3 桌内积分
    scores_after: Optional[Tuple[int, int, int, int]]  # 未确认结果可空
    official_ranks: Optional[Tuple[int, int, int, int]]
    status: str
    invalid_reasons: Tuple[str, ...]
    runtime_counts: Optional[RuntimeCounts]
    versions: Tuple[Tuple[str, object], ...]  # 契约/规则/策略/模拟器/对手池/发牌版本
    source_refs: Tuple[Mapping[str, object], ...]  # 原始引用；不含 Token 或绝对路径

    def __post_init__(self) -> None:
        if self.evaluation_schema_version != EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                "evaluation_schema_version 必须是 {0}，得到 {1!r}".format(
                    EVALUATION_SCHEMA_VERSION, self.evaluation_schema_version
                )
            )
        _require_identity_str(self.result_id, "MatchResult.result_id")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("source_kind 必须是 {0} 之一，得到 {1!r}".format(SOURCE_KINDS, self.source_kind))
        if self.status not in RESULT_STATUSES:
            raise ValueError("status 必须是 {0} 之一，得到 {1!r}".format(RESULT_STATUSES, self.status))
        if self.scenario_id is not None:
            _require_identity_str(self.scenario_id, "MatchResult.scenario_id")
        if self.pair_id is not None:
            _require_identity_str(self.pair_id, "MatchResult.pair_id")
        if self.game_key is not None and not isinstance(self.game_key, GameKey):
            raise ValueError("game_key 必须是 GameKey 或空")
        if self.config is not None and not isinstance(self.config, TournamentConfig):
            raise ValueError("config 必须是 TournamentConfig 或空")
        if not isinstance(self.policy_ids_by_seat, tuple) or len(self.policy_ids_by_seat) != SEAT_COUNT:
            raise ValueError("policy_ids_by_seat 必须是长度为 4 的元组")
        for index, policy_id in enumerate(self.policy_ids_by_seat):
            if policy_id is not None:
                _require_identity_str(policy_id, "policy_ids_by_seat[{0}]".format(index))
        permutation = _validate_seat_vector(self.seat_permutation, "seat_permutation", allow_negative=False)
        if sorted(permutation) != [0, 1, 2, 3]:
            raise ValueError("seat_permutation 必须是 0—3 的排列，得到 {0!r}".format(self.seat_permutation))
        for field_name in ("expected_hands", "completed_hands"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError("{0} 必须是非负整数或 null，得到 {1!r}".format(field_name, value))
        if self.scores_before is not None:
            object.__setattr__(self, "scores_before", _validate_seat_vector(
                self.scores_before, "scores_before", allow_negative=True))
        if self.scores_after is not None:
            object.__setattr__(self, "scores_after", _validate_seat_vector(
                self.scores_after, "scores_after", allow_negative=True))
        if self.official_ranks is not None:
            ranks = _validate_seat_vector(self.official_ranks, "official_ranks", allow_negative=False)
            for index, rank in enumerate(ranks):
                if rank < 1 or rank > SEAT_COUNT:
                    raise ValueError("official_ranks[{0}] 必须是 1—4 的名次，得到 {1!r}".format(index, rank))
        if self.runtime_counts is not None and not isinstance(self.runtime_counts, RuntimeCounts):
            raise ValueError("runtime_counts 必须是 RuntimeCounts 或空")

    # -- JSON -------------------------------------------------------------

    def to_json(self) -> Dict[str, ResultJson]:
        """输出稳定 JSON 对象；未知扩展字段容忍，本格式只负责本模块字段。"""
        return {
            "evaluation_schema_version": self.evaluation_schema_version,
            "result_id": self.result_id,
            "source_kind": self.source_kind,
            "scenario_id": self.scenario_id,
            "pair_id": self.pair_id,
            "game_key": (
                None
                if self.game_key is None
                else {
                    "source_namespace": self.game_key.source_namespace,
                    "tournament_id": self.game_key.tournament_id,
                    "game_id": self.game_key.game_id,
                }
            ),
            "config": None if self.config is None else tournament_config_to_json(self.config),
            "policy_ids_by_seat": list(self.policy_ids_by_seat),
            "seat_permutation": list(self.seat_permutation),
            "expected_hands": self.expected_hands,
            "completed_hands": self.completed_hands,
            "scores_before": None if self.scores_before is None else list(self.scores_before),
            "scores_after": None if self.scores_after is None else list(self.scores_after),
            "official_ranks": None if self.official_ranks is None else list(self.official_ranks),
            "status": self.status,
            "invalid_reasons": list(self.invalid_reasons),
            "runtime_counts": (
                None
                if self.runtime_counts is None
                else {
                    "timeouts": self.runtime_counts.timeouts,
                    "illegal_choices": self.runtime_counts.illegal_choices,
                    "fallbacks": self.runtime_counts.fallbacks,
                    "auto_actions": self.runtime_counts.auto_actions,
                    "audit_missing": self.runtime_counts.audit_missing,
                }
            ),
            "versions": {key: _json_safe(value) for key, value in self.versions},
            "source_refs": [dict(item) for item in self.source_refs],
        }


def _json_safe(value: object) -> ResultJson:
    """版本字段只允许基础 JSON 值；不允许 NaN/Infinity 流入产物。"""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("版本字段不允许 NaN/Infinity，得到 {0!r}".format(value))
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    raise ValueError("版本字段只允许基础 JSON 值，得到 {0!r}".format(type(value)))


def _need(data: Mapping, key: str) -> object:
    """读取必填键；缺失说明负载不是本模块生成的格式。"""
    if key not in data:
        raise ValueError("MatchResult 缺少必填键 {0!r}".format(key))
    return data[key]


def _seat_vector_from_row(data: Mapping, key: str) -> Tuple[int, int, int, int]:
    raw = _need(data, key)
    if not isinstance(raw, list):
        raise ValueError("{0} 必须是数组".format(key))
    return _validate_seat_vector(raw, key, allow_negative=True)


def match_result_from_json(payload: object) -> MatchResult:
    """把 JSON 对象还原为 MatchResult；结构错误抛 ValueError。

    未知新增键前向兼容（忽略）；未知主版本拒绝转换（契约 §4.2）。
    """
    if not isinstance(payload, Mapping):
        raise ValueError("MatchResult 负载必须是 JSON 对象，得到 {0!r}".format(payload))
    data = dict(payload)

    version = _need(data, "evaluation_schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("evaluation_schema_version 必须是整数，得到 {0!r}".format(version))
    if version != EVALUATION_SCHEMA_VERSION:
        raise ValueError(
            "未知 evaluation_schema_version={0!r}，拒绝转换并保留原文".format(version)
        )

    game_key_raw = data.get("game_key")
    game_key = None
    if game_key_raw is not None:
        if not isinstance(game_key_raw, Mapping):
            raise ValueError("game_key 必须是 JSON 对象或 null")
        game_key = GameKey(
            source_namespace=game_key_raw.get("source_namespace"),
            tournament_id=game_key_raw.get("tournament_id"),
            game_id=game_key_raw.get("game_id"),
        )

    config_raw = data.get("config")
    config = None if config_raw is None else tournament_config_from_json(config_raw)

    runtime_raw = data.get("runtime_counts")
    runtime_counts = None
    if runtime_raw is not None:
        if not isinstance(runtime_raw, Mapping):
            raise ValueError("runtime_counts 必须是 JSON 对象或 null")
        runtime_counts = RuntimeCounts(
            timeouts=runtime_raw.get("timeouts"),
            illegal_choices=runtime_raw.get("illegal_choices"),
            fallbacks=runtime_raw.get("fallbacks"),
            auto_actions=runtime_raw.get("auto_actions"),
            audit_missing=runtime_raw.get("audit_missing"),
        )

    policy_raw = _need(data, "policy_ids_by_seat")
    if not isinstance(policy_raw, list) or len(policy_raw) != SEAT_COUNT:
        raise ValueError("policy_ids_by_seat 必须是长度为 4 的数组")
    permutation_raw = _need(data, "seat_permutation")
    if not isinstance(permutation_raw, list) or len(permutation_raw) != SEAT_COUNT:
        raise ValueError("seat_permutation 必须是长度为 4 的数组")
    invalid_raw = _need(data, "invalid_reasons")
    if not isinstance(invalid_raw, list):
        raise ValueError("invalid_reasons 必须是数组")

    source_refs_raw = data.get("source_refs", [])
    if not isinstance(source_refs_raw, list) or not all(
        isinstance(item, Mapping) for item in source_refs_raw
    ):
        raise ValueError("source_refs 必须是 JSON 对象数组")

    versions_raw = data.get("versions", {})
    if not isinstance(versions_raw, Mapping):
        raise ValueError("versions 必须是 JSON 对象")

    return MatchResult(
        evaluation_schema_version=version,
        result_id=_need(data, "result_id"),
        source_kind=_need(data, "source_kind"),
        scenario_id=data.get("scenario_id"),
        pair_id=data.get("pair_id"),
        game_key=game_key,
        config=config,
        policy_ids_by_seat=(policy_raw[0], policy_raw[1], policy_raw[2], policy_raw[3]),
        seat_permutation=_validate_seat_vector(permutation_raw, "seat_permutation", allow_negative=False),
        expected_hands=data.get("expected_hands"),
        completed_hands=data.get("completed_hands"),
        scores_before=None if data.get("scores_before") is None else _seat_vector_from_row(data, "scores_before"),
        scores_after=None if data.get("scores_after") is None else _seat_vector_from_row(data, "scores_after"),
        official_ranks=None if data.get("official_ranks") is None else _validate_seat_vector(
            _need(data, "official_ranks"), "official_ranks", allow_negative=False
        ) if isinstance(data.get("official_ranks"), list) else None,
        status=_need(data, "status"),
        invalid_reasons=tuple(invalid_raw),
        runtime_counts=runtime_counts,
        versions=tuple(sorted((str(key), value) for key, value in versions_raw.items())),
        source_refs=tuple(dict(item) for item in source_refs_raw),
    )


def check_complete_consistency(result: MatchResult) -> List[str]:
    """语义校验：status=complete 必须真的完成完整桌赛，问题逐条返回。

    - complete 要求 completed_hands 与 expected_hands 均为非空且相等、
      scores_after 非空、invalid_reasons 为空。
    - 不足单局数、分数未确认、blocked/异常都不构成 complete（契约 §7）。
    """
    problems: List[str] = []
    if result.status != "complete":
        return problems
    if result.expected_hands is None:
        problems.append("complete 但 expected_hands 为空")
    if result.completed_hands is None:
        problems.append("complete 但 completed_hands 为空")
    if result.expected_hands is not None and result.completed_hands is not None:
        if result.completed_hands < result.expected_hands:
            problems.append(
                "complete 但 completed_hands={0} < expected_hands={1}".format(
                    result.completed_hands, result.expected_hands
                )
            )
    if result.scores_after is None:
        problems.append("complete 但 scores_after 未确认")
    if result.invalid_reasons:
        problems.append("complete 但 invalid_reasons 非空: {0}".format(result.invalid_reasons))
    return problems


# ---------------------------------------------------------------------------
# results.jsonl 读写与基础汇总
# ---------------------------------------------------------------------------


def write_results_jsonl(path: Path, results: List[MatchResult]) -> None:
    """按稳定键序写出 results.jsonl；同输入输出逐字节一致。"""
    lines = [
        json.dumps(result.to_json(), ensure_ascii=False, sort_keys=True) + "\n"
        for result in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def read_results_jsonl(path: Path) -> List[MatchResult]:
    """读取并校验 results.jsonl；任何一行结构错误抛 ValueError。"""
    results: List[MatchResult] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("results.jsonl 第 {0} 行不是合法 JSON: {1}".format(line_no, error)) from error
        results.append(match_result_from_json(payload))
    return results


def group_by_scenario(results: List[MatchResult]) -> Dict[str, List[MatchResult]]:
    """按 scenario_id 聚类；同一 scenario 不是多个独立样本（契约 §7）。

    无 scenario_id 的行（官方无法控制牌山）归入哨兵键 ""，由调用方决定
    是否进入配对统计——本函数不静默丢弃。
    """
    grouped: Dict[str, List[MatchResult]] = {}
    for result in results:
        key = result.scenario_id if result.scenario_id is not None else ""
        grouped.setdefault(key, []).append(result)
    return grouped


def count_by_status(results: List[MatchResult]) -> Dict[str, int]:
    """按 status 计数；供报告声明样本数/排除数。"""
    counts = {status: 0 for status in RESULT_STATUSES}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def count_by_source_kind(results: List[MatchResult]) -> Dict[str, int]:
    """按 source_kind 计数；mock 与真实来源分开报告。"""
    counts: Dict[str, int] = {}
    for result in results:
        counts[result.source_kind] = counts.get(result.source_kind, 0) + 1
    return counts


def filter_complete(results: List[MatchResult]) -> List[MatchResult]:
    """只保留完整桌赛结果；作废/未知/未完赛不静默删去，数量进报告。"""
    return [result for result in results if result.status == "complete"]


def excluded_summary(results: List[MatchResult]) -> Dict[str, object]:
    """报告排除原因：作废、未完赛、未知分数与 error 各自计数。"""
    excluded: Dict[str, object] = {"void": 0, "partial": 0, "error": 0, "unknown_score": 0, "incomplete": 0}
    for result in results:
        if result.status == "void":
            excluded["void"] = excluded["void"] + 1
        elif result.status == "partial":
            excluded["partial"] = excluded["partial"] + 1
        elif result.status == "error":
            excluded["error"] = excluded["error"] + 1
        if result.status == "complete" and (result.scores_after is None or result.completed_hands is None):
            excluded["unknown_score"] = excluded["unknown_score"] + 1
        if result.status == "complete" and check_complete_consistency(result):
            excluded["incomplete"] = excluded["incomplete"] + 1
    return excluded


# ---------------------------------------------------------------------------
# 产物 manifest（契约 §4.2）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestInput:
    """manifest.inputs 的一项；path 为相对输入包根路径。"""

    path: str
    sha256: str
    bundle_id: Optional[str] = None  # 多个输入包时记录；单包为空

    def __post_init__(self) -> None:
        _require_identity_str(self.path, "ManifestInput.path")
        if not isinstance(self.sha256, str) or len(self.sha256) != 64:
            raise ValueError("ManifestInput.sha256 必须是 64 位十六进制 SHA-256")


@dataclass(frozen=True)
class EvaluationManifest:
    """评估产物 manifest；固定字段见契约 §4.2 派生 manifest 清单。

    评估产物把 replay_schema_version 换成 evaluation_schema_version；
    含评分者的策略版本与完整权重放入 versions（scoring_policies 键）。
    """

    manifest_schema_version: int
    contract_id: str
    evaluation_schema_version: int
    dataset_id: str  # 创建时 UUID；封存后不可变，重生成用新 ID
    created_at_unix_ms: int  # 生成节点墙上时钟 Unix 毫秒
    source_namespace: Optional[str]  # 一个数据集中存在多值时该字段为 null
    producer_commit: Optional[str]
    dirty: Optional[bool]
    inputs: Tuple[ManifestInput, ...]
    rules_hash: Optional[str]
    guide_version: Optional[int]
    guide_captured_at: Optional[str]  # 来源采集日期 YYYY-MM-DD
    config: Optional[TournamentConfig]
    missing_fields: Tuple[str, ...]
    versions: Tuple[Tuple[str, object], ...]  # 其余版本（策略/模拟器/对手池/采样等）

    def __post_init__(self) -> None:
        if self.manifest_schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError("manifest_schema_version 必须是 {0}".format(MANIFEST_SCHEMA_VERSION))
        if self.contract_id != CONTRACT_ID:
            raise ValueError("contract_id 必须是 {0}".format(CONTRACT_ID))
        if self.evaluation_schema_version != EVALUATION_SCHEMA_VERSION:
            raise ValueError("evaluation_schema_version 必须是 {0}".format(EVALUATION_SCHEMA_VERSION))
        _require_identity_str(self.dataset_id, "EvaluationManifest.dataset_id")
        if isinstance(self.created_at_unix_ms, bool) or not isinstance(self.created_at_unix_ms, int) or self.created_at_unix_ms < 0:
            raise ValueError("created_at_unix_ms 必须是非负整数 Unix 毫秒")
        if self.guide_version is not None and (isinstance(self.guide_version, bool) or not isinstance(self.guide_version, int)):
            raise ValueError("guide_version 必须是整数或空")
        if self.guide_captured_at is not None:
            datetime.strptime(self.guide_captured_at, "%Y-%m-%d")
        if self.config is not None and not isinstance(self.config, TournamentConfig):
            raise ValueError("config 必须是 TournamentConfig 或空")
        if self.rules_hash is not None and (not isinstance(self.rules_hash, str) or len(self.rules_hash) != 64):
            raise ValueError("rules_hash 必须是 64 位十六进制 SHA-256 或空")

    def to_json(self) -> Dict[str, ResultJson]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "contract_id": self.contract_id,
            "evaluation_schema_version": self.evaluation_schema_version,
            "dataset_id": self.dataset_id,
            "created_at_unix_ms": self.created_at_unix_ms,
            "source_namespace": self.source_namespace,
            "producer_commit": self.producer_commit,
            "dirty": self.dirty,
            "inputs": [
                {
                    "path": item.path,
                    "sha256": item.sha256,
                    "bundle_id": item.bundle_id,
                }
                for item in self.inputs
            ],
            "rules_hash": self.rules_hash,
            "guide_version": self.guide_version,
            "guide_captured_at": self.guide_captured_at,
            "config": None if self.config is None else tournament_config_to_json(self.config),
            "missing_fields": list(self.missing_fields),
            "versions": {key: _json_safe(value) for key, value in self.versions},
        }


def new_evaluation_manifest(
    *,
    source_namespace: Optional[str],
    producer_commit: Optional[str],
    dirty: Optional[bool],
    inputs: Tuple[ManifestInput, ...] = (),
    rules_hash: Optional[str] = None,
    guide_version: Optional[int] = None,
    guide_captured_at: Optional[str] = None,
    config: Optional[TournamentConfig] = None,
    missing_fields: Tuple[str, ...] = (),
    versions: Tuple[Tuple[str, object], ...] = (),
) -> EvaluationManifest:
    """创建新 manifest；dataset_id 与 created_at_unix_ms 在此生成。

    created_at_unix_ms 是生成节点墙上时钟 Unix 毫秒（不是单调时钟）；
    重生成同数据集必须调用本函数拿新 ID。
    """
    return EvaluationManifest(
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        contract_id=CONTRACT_ID,
        evaluation_schema_version=EVALUATION_SCHEMA_VERSION,
        dataset_id=str(uuid.uuid4()),
        created_at_unix_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        source_namespace=source_namespace,
        producer_commit=producer_commit,
        dirty=dirty,
        inputs=inputs,
        rules_hash=rules_hash,
        guide_version=guide_version,
        guide_captured_at=guide_captured_at,
        config=config,
        missing_fields=missing_fields,
        versions=versions,
    )


def write_manifest(path: Path, manifest: EvaluationManifest) -> None:
    """写出 manifest.json；键序稳定。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_json(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 报告渲染：结构化 report → Markdown
# ---------------------------------------------------------------------------


def render_report_md(report: Mapping[str, object]) -> str:
    """把结构化 report 渲染成 Markdown。

    report 结构：{"title": str, "intro": [str, ...], "sections": [
    {"heading": str, "paragraphs": [str, ...],
     "table": {"columns": [str, ...], "rows": [[cell, ...], ...]}}]}。
    只做渲染，不做统计；数值与结论由调用方生成。
    """
    lines: List[str] = []
    title = report.get("title")
    if isinstance(title, str) and title:
        lines.append("# {0}".format(title))
        lines.append("")
    intro = report.get("intro")
    if isinstance(intro, list):
        for paragraph in intro:
            if isinstance(paragraph, str):
                lines.append(paragraph)
                lines.append("")

    sections = report.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            heading = section.get("heading")
            if isinstance(heading, str) and heading:
                lines.append("## {0}".format(heading))
                lines.append("")
            paragraphs = section.get("paragraphs")
            if isinstance(paragraphs, list):
                for paragraph in paragraphs:
                    if isinstance(paragraph, str):
                        lines.append(paragraph)
                        lines.append("")
            table = section.get("table")
            if isinstance(table, Mapping):
                columns = table.get("columns")
                rows = table.get("rows")
                if isinstance(columns, list) and columns and isinstance(rows, list):
                    lines.append("| {0} |".format(" | ".join(str(item) for item in columns)))
                    lines.append("| {0} |".format(" | ".join("---" for _ in columns)))
                    for row in rows:
                        if isinstance(row, list):
                            cells = ["" if item is None else str(item) for item in row]
                            padded = (cells + [""] * len(columns))[: len(columns)]
                            lines.append("| {0} |".format(" | ".join(padded)))
                    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
