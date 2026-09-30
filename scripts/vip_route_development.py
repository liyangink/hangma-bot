"""执行公开预登记的VIP完整桌开发比较；不调用模型、不确认或发布候选。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from hangma_bot.offline.vip_route_development import run_vip_route_development


def main() -> int:
    """只解析公开批次和新输出目录，调用独立离线入口并显示有限状态。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True, help="公开冻结种子、候选摘要及预算JSON")
    parser.add_argument("--out", type=Path, required=True, help="不存在的新目录，禁止覆盖或自动续批")
    args = parser.parse_args()
    try:
        result = asyncio.run(run_vip_route_development(args.batch, args.out))
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "rejected", "reason": "公开冻结材料、预算或目录校验失败"}, ensure_ascii=False))
        return 2
    print(json.dumps({key: result.get(key) for key in (
        "status", "identity_stable", "planned_table_instances", "charged_table_instances",
        "development_only", "confirmation_claim", "published")}, ensure_ascii=False))
    return 0 if result["status"] == "development_complete_not_confirmed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
