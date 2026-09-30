"""生成VIP联合启发式提案或提示词交接包；不跑桌赛、不准入、不发布。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import (
    OPERATORS, VipEohError, reconcile_vip_eoh_call, run_vip_eoh_generate,
    write_vip_seed_parent,
)


def main() -> int:
    """只解析公开批次及显式后端；私有凭据解析留在预留完成后的传输边界。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operator", choices=(*OPERATORS, "seed", "reconcile"))
    parser.add_argument("--batch", type=Path, required=True, help="冻结五账户预算与实际执行额度JSON")
    parser.add_argument("--out", type=Path, help="新的提案/交接目录，禁止覆盖")
    parser.add_argument("--backend", choices=("emit", "replay", "api"), default="emit")
    parser.add_argument("--parent", type=Path, action="append", default=[], help="有序新版父包目录，可重复参数")
    parser.add_argument("--feedback", type=Path, help="仅开发反馈，不含确认结果")
    parser.add_argument("--reply", type=Path, help="提示词哈希相符的回放封套")
    parser.add_argument("--config", type=Path, help="仅API使用的私有调用配置；不打印内容")
    parser.add_argument("--endpoint", help="API端点配置名")
    parser.add_argument("--model", help="显式请求模型")
    parser.add_argument("--tier", help="私有配置中的模型档位")
    parser.add_argument("--attempt-id", help="仅人工恢复原在途预留")
    parser.add_argument("--review-note", help="人工审核依据；恢复只结算，不重发")
    args = parser.parse_args()
    try:
        if args.operator == "reconcile":
            result = reconcile_vip_eoh_call(args.batch, args.attempt_id or "", review_note=args.review_note or "")
        elif args.operator == "seed":
            if args.out is None:
                parser.error("seed需要--out")
            result = write_vip_seed_parent(args.out, args.batch)
        else:
            if args.out is None:
                parser.error("生成需要--out")
            result = run_vip_eoh_generate(
                batch_file=args.batch, out_dir=args.out, operator=args.operator,
                backend=args.backend, parent_paths=args.parent,
                feedback=args.feedback.read_text(encoding="utf-8") if args.feedback else "",
                reply_file=args.reply, config=args.config, endpoint=args.endpoint,
                model=args.model, tier=args.tier,
            )
    except (VipEohError, OSError, ValueError):
        print(json.dumps({"status": "rejected", "reason": "公开材料、预算或父代校验失败"}, ensure_ascii=False))
        return 2
    # 不输出完整配置、父代源码或回复；完整非秘密证据只在新目录中审阅。
    print(json.dumps({name: result.get(name) for name in (
        "status", "attempt_id", "profile", "source_sha256", "identity_stable")}, ensure_ascii=False))
    return 0 if result.get("status") in ("prompt_emitted", "loaded_not_admitted", "settled") else 1


if __name__ == "__main__":
    raise SystemExit(main())
