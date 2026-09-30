"""启动 VIP 独立联合启发式的严格离线机械桌赛。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from hangma_bot.offline.vip_heuristic_smoke import run_vip_smoke
from hangma_bot.policy.route_vip_heuristic import VIP_ROUTE_HEURISTIC_SEED_SOURCE


async def main() -> int:
    """只解析研究配置并装配离线运行；不接入网络或线上比赛。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="新的证据目录，禁止覆盖")
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=8, help="运行时完整桌计划局数")
    parser.add_argument("--source", type=Path, help="受限 score_actions 候选源码；默认人工种子")
    args = parser.parse_args()
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE if args.source is None else args.source.read_text(encoding="utf-8")
    result = await run_vip_smoke(args.out, start_seed=args.start_seed, seeds=args.seeds, rounds=args.rounds, source=source)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "mechanical_smoke_pass" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
