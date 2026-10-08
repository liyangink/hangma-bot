"""离线候选执行配置：白名单额度、身份参数和研究资格，禁止隐式提高默认额度。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from typing import Any, Mapping
from hangma_bot.policy.action_value_executor import MAX_COUNTED_OPERATIONS

SCHEMA = "sitin-candidate-execution-profile/1"
DEFAULT_NAME = "default-100k-v1"
RESEARCH_NAME = "research-200k-v1"


def resolve(value: Any = None) -> dict[str, Any]:
    """规范化默认或显式研究配置；仅接受已登记版本，不按输入自动翻倍。

    max_operations为单次评分的计数上限，不是时间、费用或实际操作数。
    research_only=True只允许离线研发；它不签发准入或部署许可。
    """
    name = (DEFAULT_NAME if value is None else value if isinstance(value, str)
            else value.get("name") if isinstance(value, Mapping) else None)
    if name not in (DEFAULT_NAME, RESEARCH_NAME):
        raise ValueError("未知候选执行配置，必须显式登记默认或有界研究版本")
    profile = {"schema": SCHEMA, "name": name,
               "max_operations": MAX_COUNTED_OPERATIONS if name == DEFAULT_NAME else 200_000,
               "research_only": name == RESEARCH_NAME}
    if MAX_COUNTED_OPERATIONS != 100_000:
        raise ValueError("默认执行额度已变化，必须先升版研究配置")
    if isinstance(value, Mapping):
        if set(value) != set(profile) or any(type(value[key]) is not type(expected) or value[key] != expected
                                            for key, expected in profile.items()):
            raise ValueError("候选执行配置字段缺失、类型错误或内容与登记版本不符")
    return profile


def from_authorization(authorization: Mapping[str, Any] | None) -> dict[str, Any]:
    """只读取本批显式额度声明；授权真实性和费用仍由原有授权/账本入口验证。"""
    return resolve((authorization or {}).get("candidate_execution_profile"))


def identity_params(params: Mapping[str, Any], profile: Any = None) -> dict[str, Any]:
    """给现有身份参数加入非默认实际额度，默认身份形状保持兼容。"""
    selected = resolve(profile)
    result = dict(params)
    if "candidate_execution_profile" in result:
        require_same(result["candidate_execution_profile"], selected)
    if "candidate_max_operations" in result:
        value = result["candidate_max_operations"]
        if type(value) is not int or value != selected["max_operations"]:
            raise ValueError("身份参数额度与所选执行配置不符")
    if selected["research_only"]:
        result["candidate_max_operations"] = selected["max_operations"]
        result["candidate_execution_profile"] = selected
    return result


def require_same(actual: Any, expected: Any) -> dict[str, Any]:
    """恢复或复用时拒绝错额度记录；缺声明只兼容默认配置，不猜测研究身份。"""
    selected = resolve(expected)
    if resolve(actual) != selected:
        raise ValueError("候选执行配置漂移，不能复用不同额度的准入或成绩")
    return selected


def verify_table(table: Mapping[str, Any], *, profile: Any, candidate_seat: int | None) -> None:
    """核对自然桌或条件续打桌的实际装配额度；不把声明当成运行证明。

    candidate_seat是候选所在物理座位，基线臂用None；当前面板的其他座位
    必须是固定非评分对手。调用方须由冻结赛程独立求出该座位。
    """
    import sitin_execution_audit as audit

    selected = resolve(profile)
    if candidate_seat is not None and (type(candidate_seat) is not int or not 0 <= candidate_seat < 4):
        raise ValueError("候选物理座位越界")
    raw = audit.verify_table(table)
    binding = table.get("policy_execution_binding")
    if binding is not None:
        limits = binding["max_operations_by_seat"]
    else:
        versions = table["result"]["versions"]
        limits = []
        for seat in range(4):
            value = versions.get("natural_seat_max_operations:{0}".format(seat))
            if value is not None and (not isinstance(value, str) or not value.isascii()
                                      or not value.isdigit() or value != str(int(value))):
                raise ValueError("自然桌实际评分额度格式错误")
            limits.append(None if value is None else int(value))
    for seat, (policy_id, limit) in enumerate(zip(raw["policy_ids_by_seat"], limits)):
        scoring = policy_id.startswith("action_value_v1:")
        if seat == candidate_seat:
            if not scoring or type(limit) is not int or limit != selected["max_operations"]:
                raise ValueError("候选实际评分额度或物理座位与冻结配置不符")
        elif scoring or limit is not None:
            raise ValueError("对手座位出现未声明的评分策略或额度")
