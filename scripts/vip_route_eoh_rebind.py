"""提高已有 VIP 提案的研究操作额度；保留原作者账，不评分、不调用模型。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohError
from hangma_bot.offline.vip_eoh_rebind import rebind_vip_research_budget


def main() -> int:
    """仅解析公开材料路径；目标批次除提高max_operations及batch_id外须相同。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-batch", type=Path, required=True, help="验证原执行身份的公开批次，可能不同于原作者批次")
    parser.add_argument("--source-package", type=Path, required=True, help="当前已装载提案或可递归核验的研究重绑定包")
    parser.add_argument("--target-batch", type=Path, required=True, help="仅提高操作额度及改变审计batch_id的新公开配置")
    parser.add_argument("--out", type=Path, required=True, help="必须不存在的新研究包目录")
    parser.add_argument("--execution-evidence", type=Path, action="append", default=[], help="显式引用原执行失败等公开证据，逐字快照")
    args = parser.parse_args()
    try:
        record = rebind_vip_research_budget(
            source_batch_file=args.source_batch, source_package=args.source_package,
            target_batch_file=args.target_batch, out_dir=args.out,
            execution_evidence_files=args.execution_evidence,
        )
    except (VipEohError, ValueError, OSError):
        print(json.dumps({"status": "rejected", "reason": "研究重绑定来源、配置、身份或新目录校验失败"}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": record["status"], "artifact_role": record["artifact_role"],
                      "source_candidate_id": record["provenance"]["source_identity"]["candidate_id"],
                      "candidate_id": record["identity"]["candidate_id"],
                      "max_operations": record["identity"]["params"]["max_operations"],
                      "new_model_calls": 0, "new_table_instances": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
