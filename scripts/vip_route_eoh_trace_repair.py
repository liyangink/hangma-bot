"""显式创建 VIP 解释格式工程修复身份；不评分、不调用模型或覆盖原包。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohError
from hangma_bot.offline.vip_eoh_trace_repair import repair_vip_trace_codec


def main() -> int:
    """解析已装载模型提案、原执行配置及公开附件；错误拒绝、不自动换源。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True, help="验证原及修后评分身份的同一执行配置")
    parser.add_argument("--source-package", type=Path, required=True, help="当前已装载模型提案，原失败保留")
    parser.add_argument("--out", type=Path, required=True, help="必须不存在的修复包目录")
    parser.add_argument("--execution-evidence", type=Path, action="append", default=[], help="逐字引用原失败等公开原件")
    args = parser.parse_args()
    try:
        record = repair_vip_trace_codec(batch_file=args.batch, source_package=args.source_package,
                                       out_dir=args.out, execution_evidence_files=args.execution_evidence)
    except (VipEohError, ValueError, OSError):
        print(json.dumps({"status": "rejected", "reason": "解释修复来源、格式、身份或新目录校验失败"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": record["status"], "artifact_role": record["artifact_role"],
                      "original_candidate_id": record["provenance"]["source_identity"]["candidate_id"],
                      "candidate_id": record["identity"]["candidate_id"], "repair_id": record["provenance"]["repair_id"],
                      "new_model_calls": 0, "new_score_calls": 0, "new_table_instances": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
