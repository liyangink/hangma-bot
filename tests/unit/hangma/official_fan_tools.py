"""按完整请求读封存官方回执；同请求v35优先，未复核者保留v23版本事实。"""

from functools import lru_cache
import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/official/v23/fan-calc"
CURRENT_DIR = Path(__file__).resolve().parents[2] / "fixtures/official/v35/fan-calc-branch-baotou"


def request_key(request: dict) -> str:
    """归一化默认参数和摸前手牌顺序；摸牌与链参数仍属于请求身份。"""
    value = dict(request)
    value["hand"] = sorted(value["hand"])
    value.setdefault("chain", {"count": 0, "piao": 0})
    value.setdefault("base", 1)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@lru_cache(maxsize=1)
def _responses() -> dict:
    rows = [json.loads(line) for line in (FIXTURE_DIR / "cases.jsonl").read_text().splitlines()]
    rows += [json.loads(line) for line in (CURRENT_DIR / "cases.jsonl").read_text().splitlines()]
    return {request_key(row["request"]): row["response"] for row in rows if row["http_status"] == 200}


def current_response(request: dict) -> dict:
    """返回同请求最新封存响应；v23来源不代表2026-10-06已重新核验。"""
    return _responses()[request_key(request)]


@lru_cache(maxsize=1)
def _current_overrides() -> dict:
    rows = [json.loads(line) for line in (CURRENT_DIR / "cases.jsonl").read_text().splitlines()]
    return {request_key(row["request"]): row["response"] for row in rows if row["http_status"] == 200}


def current_override(request: dict, recorded_response: dict) -> dict:
    """只用精确同请求v35回执覆盖独立历史oracle；缺复核保留原版本事实。"""
    return _current_overrides().get(request_key(request), recorded_response)
