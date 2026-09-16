"""运行级规则事实的**读取**入口：把「有财必拷响」等开关从记录里读出来。

为什么是**运行级**而不是逐决策字段（Lead 2026-09-16 追问的缺口）
================================================================
``you_cai_bi_kao` 是官方 ``/api/rules` 公布的**赛事/运行级常量**：同一次运行的每一条
决策都相同。应用层已经在 ``RUN_MANIFEST``（``runs/{run_id}/manifest.json``）里把它落盘
（``payload.you_cai_bi_kao``，另含 ``ruleset_version`` / ``base_score`` / ``max_games`` /
``rounds_per_game``），所以**不需要、也不应该在每条决策记录里重复一个常量**；
决策记录行自带 ``run_id``，离线按 ``run_id`` 连接该清单即可。

**不许用默认值冒充已接线**：缺失、旧形态或损坏一律返回 ``None``（未知 ≠ False）；
本模块不做规则判断，也不把"没有记录"读成"开关关闭"。

已实测（2026-09-16，见证据 ``evidence/3.6d-corpus/raw/run-facts.json``）
- 决策行里**没有**该字段（``request`` / ``observation`` 都不带）；
- 本地留存的 100 份 ``manifest.json`` 中 98 份在场，取值**全为 ``False``**，
  **没有任何真实 ``true`` 样本**；另 2 份是旧形态（只有 ``ruleset_version``）；
- 按 ``run_id`` 连接成功的决策行 161,680 / 359,262（45.0%），其余会话的审计目录未随本仓留存。

因此：**在 derived 语料上，评分上下文里的 ``you_cai_bi_kao` 只能是"未知"，除非调用方
显式连接运行清单**；门控类 ``gate.you_cai_bi_kao` 在这些窗口上不可判定——这是记录事实，
不得用 ``False`` 顶替。让"每条决策都带该事实"需要改 ``DecisionRequest``/``audit_codec``
（application/kernel 范围）或让 ``offline/replay.py` 把运行清单事实并入派生行，均不在本包可写范围。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

#: RUN_MANIFEST 在运行审计目录下的固定相对路径（记录器按"单对象、后写覆盖"维护）。
MANIFEST_RELATIVE = "manifest.json"

#: 本模块读取的运行级事实键（与 ``participant_runtime`` 落盘的键一一对应）。
FACT_KEYS = ("you_cai_bi_kao", "ruleset_version", "base_score", "max_games", "rounds_per_game")


@dataclass(frozen=True)
class RunRuleFacts:
    """一次运行的规则事实；未知一律为 None（**不得读成 False/0**）。"""

    you_cai_bi_kao: Optional[bool] = None  # 官方 YouCaiBiKao 开关；None = 记录不存在或不可读
    ruleset_version: Optional[str] = None  # 本地规则语义版本
    base_score: Optional[int] = None  # 底分（分）
    max_games: Optional[int] = None  # 每场桌赛局数上限
    rounds_per_game: Optional[int] = None  # 每桌赛局数
    source: Optional[str] = None  # 记录文件路径（可追溯）
    reason: Optional[str] = None  # 不可读/缺字段原因；可读时为 None

    @property
    def known(self) -> bool:
        """是否读到了「有财必拷响」开关本身（False 是合法已知值）。"""

        return self.you_cai_bi_kao is not None


def manifest_path(audit_root: Path, run_id: str) -> Path:
    """运行清单路径：``<audit_root>/runs/<run_id>/manifest.json``。"""

    return Path(audit_root) / "runs" / run_id / MANIFEST_RELATIVE


def read_run_facts(path: Path) -> RunRuleFacts:
    """读取一份运行清单（审计信封或裸 payload）；失败返回只带原因的未知事实。

    接受两种形态：记录器的 JSONL 行（``{"payload": {...}}``）与裸 payload 字典
    （测试与离线工具常用）。**任何异常都不抛给调用方**，只把原因写进 ``reason``。
    """

    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 读取失败必须降级为未知，不能抛给决策/审计路径
        return RunRuleFacts(source=str(path), reason="清单不可读：{0}: {1}".format(
            type(exc).__name__, exc))
    payload: Mapping[str, object]
    if isinstance(data, Mapping) and isinstance(data.get("payload"), Mapping):
        payload = data["payload"]  # type: ignore[assignment]
    elif isinstance(data, Mapping):
        payload = data
    else:
        return RunRuleFacts(source=str(path), reason="清单不是 JSON 对象")
    raw = payload.get("you_cai_bi_kao")
    if raw is None:
        return RunRuleFacts(
            ruleset_version=_optional_str(payload.get("ruleset_version")),
            source=str(path),
            reason="清单缺少 you_cai_bi_kao（旧形态或未记录）",
        )
    if not isinstance(raw, bool):
        return RunRuleFacts(
            ruleset_version=_optional_str(payload.get("ruleset_version")),
            source=str(path),
            reason="you_cai_bi_kao 不是布尔值：{0!r}".format(raw),
        )
    return RunRuleFacts(
        you_cai_bi_kao=raw,
        ruleset_version=_optional_str(payload.get("ruleset_version")),
        base_score=_optional_int(payload.get("base_score")),
        max_games=_optional_int(payload.get("max_games")),
        rounds_per_game=_optional_int(payload.get("rounds_per_game")),
        source=str(path),
    )


def read_facts_for_run(audit_root: Path, run_id: str) -> RunRuleFacts:
    """按 ``run_id`` 读取运行清单；文件不在场时明确报告"未随仓留存"。"""

    path = manifest_path(audit_root, run_id)
    if not path.is_file():
        return RunRuleFacts(source=str(path), reason="运行清单不在场（会话审计目录未留存？）")
    return read_run_facts(path)


def _optional_str(value: object) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _optional_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
