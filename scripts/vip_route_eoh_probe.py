"""构建VIP开发行为面板或运行候选窗口探针；不调用模型、不跑桌赛。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_probe import build_vip_eoh_panel, run_vip_eoh_probe
from hangma_bot.offline.vip_eoh_input_sources import build_public_input_panel
from hangma_bot.offline.vip_eoh_probe_v2 import run_public_input_probe


def main() -> int:
    """只解析公开文件路径和冻结摘要，调用离线模块并显示有限结果。"""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="按行动前分层构建开发面板")
    build.add_argument("--audit", type=Path, default=REPO_ROOT / "review/vip-route-2026-09-30/evidence/t2-final-guarded-complete-tables-202")
    build.add_argument("--manifest-sha256", required=True)
    build.add_argument("--decisions-sha256", required=True)
    build.add_argument("--per-stratum", type=int, default=1)
    build.add_argument("--max-windows", type=int, default=64, help="默认64，可扩至128以覆盖较多行动前分层；不是全部场景证明")
    run = commands.add_parser("run", help="共享冻结视图探测有序父包及候选包")
    run.add_argument("--panel", type=Path, required=True)
    run.add_argument("--batch", type=Path, required=True)
    run.add_argument("--parent", type=Path, action="append", default=[])
    run.add_argument("--candidate", type=Path, action="append", required=True)
    build_v2 = commands.add_parser("build-v2", help="严格显式真实来源构建独立/2开发面板")
    build_v2.add_argument("--source-spec", type=Path, action="append", required=True)
    build_v2.add_argument("--source-sha256", action="append", required=True)
    build_v2.add_argument("--per-stratum", type=int, required=True)
    build_v2.add_argument("--max-windows", type=int, required=True)
    build_v2.add_argument("--max-windows-per-source-root", type=int, required=True)
    run_v2 = commands.add_parser("run-v2", help="显式/2探针计划；实际全DTO保存后逐包评分")
    run_v2.add_argument("--panel", type=Path, required=True)
    run_v2.add_argument("--batch", type=Path, required=True)
    run_v2.add_argument("--plan", type=Path, required=True)
    run_v2.add_argument("--parent", type=Path, action="append", default=[])
    run_v2.add_argument("--candidate", type=Path, action="append", required=True)
    for command in (build, run, build_v2, run_v2):
        command.add_argument("--out", type=Path, required=True, help="新目录，禁止覆盖")
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_vip_eoh_panel(args.audit, args.out, manifest_sha256=args.manifest_sha256,
                decisions_sha256=args.decisions_sha256, per_stratum=args.per_stratum, max_windows=args.max_windows)
        elif args.command == "build-v2":
            if len(args.source_spec) != len(args.source_sha256):
                raise ValueError("source-spec与source-sha256须逐项对应")
            result = build_public_input_panel([{"path": str(p.resolve()), "sha256": digest}
                for p, digest in zip(args.source_spec, args.source_sha256)], args.out,
                limits={"per_stratum": args.per_stratum, "max_windows": args.max_windows,
                        "max_windows_per_source_root": args.max_windows_per_source_root})
        elif args.command == "run-v2":
            result = run_public_input_probe(args.panel, args.batch, args.plan, args.out,
                parent_paths=args.parent, candidate_paths=args.candidate)
        else:
            result = run_vip_eoh_probe(args.panel, args.batch, args.out,
                parent_paths=args.parent, candidate_paths=args.candidate)
    except (OSError, ValueError, KeyError):
        print(json.dumps({"status": "rejected", "reason": "公开输入、冻结摘要或目录校验失败"}, ensure_ascii=False))
        return 2
    print(json.dumps({key: result.get(key) for key in (
        "status", "window_count", "planned_package_windows", "scored_package_windows",
        "unfinished_package_windows", "identity_stable", "development_only", "admitted")}, ensure_ascii=False))
    return 0 if args.command in ("build", "build-v2") or result["status"] == "probe_complete_not_admitted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
