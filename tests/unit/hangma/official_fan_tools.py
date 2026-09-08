"""按完整请求读取 v23 官方响应；历史文件保持原样，测试不访问网络。"""

from functools import lru_cache
import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/official/v23/fan-calc"


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
    return {request_key(row["request"]): row["response"] for row in rows if row["http_status"] == 200}


def current_response(request: dict) -> dict:
    """返回同一请求的当前官方金例；缺失时报错，禁止退回旧版本期望值。"""
    return _responses()[request_key(request)]
