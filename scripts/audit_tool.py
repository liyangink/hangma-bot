#!/usr/bin/env python3
"""审计与赛后工具统一入口，操作说明见 doc/operations.md。

watch / inspect / validate 只读本机证据；collect-test-room 下载官方原文；
postgame 封存并生成数据集、规则和观察诊断；pack / unpack 校验迁移；
import-history / migrate-runs 整理旧制品。退出成功不等于所有检查通过。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, Sequence


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_import_path()

from hangma_bot.adapters.recording import validate_run  # noqa: E402
from hangma_bot.adapters.recording.bundle import pack_bundle  # noqa: E402
from hangma_bot.adapters.recording.reader import read_records  # noqa: E402
from hangma_bot.offline.replay import build_dataset  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _cmd_validate(args: argparse.Namespace) -> int:
    report = validate_run(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK if report["audit_complete"] else EXIT_FAILED


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def _decision_summary(records_by_game):
    """把某场次的记录折叠成 (participant, decision) 级摘要。"""

    decisions = {}
    for record in records_by_game:
        context = record.context or {}
        pid = context.get("participant_id")
        did = context.get("decision_id")
        if not isinstance(pid, str) or not isinstance(did, str):
            continue
        entry = decisions.setdefault(
            (pid, did),
            {"participant_id": pid, "decision_id": did, "plan_revisions": [], "validations": [], "attempts": [], "end_reason": None, "window": None, "hand": None},
        )
        payload = record.payload or {}
        kind = record.kind
        if kind == "decision_input":
            entry["plan_revisions"].append(payload.get("plan_revision"))
            request = payload.get("request") or {}
            observation = request.get("observation") or {}
            entry["window"] = payload.get("window")
            entry["hand"] = {
                "my_hand": observation.get("my_hand"),
                "drawn_tile": observation.get("drawn_tile"),
            }
        elif kind == "candidate_validated":
            entry["validations"].append(
                {
                    "action_key": payload.get("action_key"),
                    "legal": payload.get("legal"),
                    "reason": payload.get("reason"),
                }
            )
        elif kind == "submission_intent":
            entry["attempts"].append(
                {
                    "attempt_no": context.get("attempt_no"),
                    "action_key": payload.get("action_key"),
                    "plan_revision": payload.get("plan_revision"),
                    "outcome": None,
                }
            )
        elif kind == "submission_outcome":
            for attempt in entry["attempts"]:
                if attempt["attempt_no"] == context.get("attempt_no") and attempt["outcome"] is None:
                    attempt["outcome"] = payload.get("outcome") or payload.get("outcome_type")
                    attempt["official_code"] = payload.get("official_code")
                    break
        elif kind == "decision_ended":
            entry["end_reason"] = payload.get("end_reason")
    return list(decisions.values())


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = read_records(args.path)
    records = [
        record
        for record in result.records
        if record.kind is not None
        and record.error is None
        and record.context is not None
        and record.context.get("game_id") == args.game
    ]
    summaries = _decision_summary(records)
    issues = [{"file": i.relative_path, "line_no": i.line_no, "issue": i.issue} for i in result.issues]
    if args.json:
        document = {
            "path": str(args.path),
            "game_id": args.game,
            "decisions": summaries,
            "files": list(result.files),
            "issues": issues,
        }
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return EXIT_OK
    print("game:", args.game, "| decisions:", len(summaries), "| files:", len(result.files))
    if issues:
        print("读取问题:", json.dumps(issues, ensure_ascii=False))
    for entry in sorted(summaries, key=lambda item: (item["participant_id"], item["decision_id"])):
        print(
            "[{}] {} revision={} end={} attempts={} validations={} hand={}".format(
                entry["participant_id"],
                entry["decision_id"],
                entry["plan_revisions"],
                entry["end_reason"],
                len(entry["attempts"]),
                len(entry["validations"]),
                (entry.get("hand") or {}).get("my_hand"),
            )
        )
        for attempt in entry["attempts"]:
            print(
                "    attempt {} {} -> {}".format(
                    attempt["attempt_no"], attempt["action_key"], attempt["outcome"]
                )
            )
    return EXIT_OK


# ---------------------------------------------------------------------------
# watch
# ---------------------------------------------------------------------------


def _cmd_watch(args: argparse.Namespace) -> int:
    from hangma_bot.offline.postgame import session_status
    previous = None
    try:
        while True:
            current = session_status(Path(args.runs_root))
            if current != previous or args.once:
                print(json.dumps(current, ensure_ascii=False, indent=None if args.json else 2), flush=True)
            previous = current
            if args.once or (args.until_closed and current["all_closed"]):
                return EXIT_OK
            time.sleep(max(.5, args.interval))
    except KeyboardInterrupt:
        return EXIT_OK


# ---------------------------------------------------------------------------
# collect-test-room
# ---------------------------------------------------------------------------


def _cmd_collect_test_room(args: argparse.Namespace) -> int:
    from hangma_bot.bootstrap import build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    config = json.loads(Path(args.runtime_config).read_text())
    with build_public_archive_client(config) as client:
        result = collect_test_room(client, args.room, args.batch, Path(args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK


def _cmd_postgame(args: argparse.Namespace) -> int:
    from hangma_bot.bootstrap import DEFAULT_RULESET_VERSION, build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    from hangma_bot.offline.postgame import finalize_session
    if args.download:
        if not args.runtime_config or not args.room or args.batch is None:
            raise ValueError("--download 需要 --runtime-config、--room 和 --batch")
        with build_public_archive_client(json.loads(Path(args.runtime_config).read_text())) as client:
            collect_test_room(client, args.room, args.batch, Path(args.session))
    config = json.loads(Path(args.rule_config).read_text()) if args.rule_config else None
    result = finalize_session(Path(args.session), source_namespace=args.source_namespace,
        ruleset_version=args.ruleset_version or DEFAULT_RULESET_VERSION, rule_config=config)
    print(json.dumps({k: result[k] for k in ("job", "run_count", "official_documents", "audit_complete", "bundle_verified")}, ensure_ascii=False, indent=2))
    print("数据用途与未检查项：" + str(Path(result["job"]) / "report.json"))
    return EXIT_OK


# ---------------------------------------------------------------------------
# convert / pack
# ---------------------------------------------------------------------------


def _cmd_convert(args: argparse.Namespace) -> int:
    namespace = getattr(args, "source_namespace", None)
    if not namespace:
        print("convert 必须提供 --source-namespace（部署配置中的逻辑平台实例名）", file=sys.stderr)
        return EXIT_USAGE
    report = build_dataset(
        args.bundle,
        args.out,
        source_namespace=namespace,
        producer_commit=getattr(args, "producer_commit", None),
        rules_hash=getattr(args, "rules_hash", None),
        guide_version=getattr(args, "guide_version", None),
        guide_captured_at=getattr(args, "guide_captured_at", None),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK


def _cmd_pack(args: argparse.Namespace) -> int:
    report = pack_bundle(args.bundle, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_tool.py",
        description="审计离线工具：验证、查看、监控、采集、转换与打包",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="验证一次运行的审计目录")
    validate_parser.add_argument("path", help="runs/{run_id} 目录路径")

    inspect_parser = subparsers.add_parser("inspect", help="查看某场次的决策链")
    inspect_parser.add_argument("path", help="run 目录路径")
    inspect_parser.add_argument("--game", required=True, help="官方 game_id")
    inspect_parser.add_argument("--json", action="store_true", help="输出 JSON")

    watch_parser = subparsers.add_parser("watch", help="监控审计根的状态变化")
    watch_parser.add_argument("runs_root", help="审计根目录（含 runs/）")
    watch_parser.add_argument("--json", action="store_true", help="逐行 JSON 输出")
    watch_parser.add_argument("--interval", type=float, default=5.0, help="轮询间隔秒数")

    watch_parser.add_argument("--once", action="store_true", help="只读一次状态后退出")
    watch_parser.add_argument("--until-closed", action="store_true", help="所有已发现运行关闭后退出")

    collect_parser = subparsers.add_parser("collect-test-room", help="下载测试房间赛后数据")
    collect_parser.add_argument("--runtime-config", required=True, help="运行配置 JSON（取 base_url）")
    collect_parser.add_argument("--room", required=True, help="房间 id")
    collect_parser.add_argument("--batch", required=True, type=int, help="批次号")
    collect_parser.add_argument("--out", required=True, help="session 目录；原文写入其 official/ 子目录")

    convert_parser = subparsers.add_parser("convert", help="bundle → 统一牌谱数据集")
    convert_parser.add_argument("bundle", help="bundle 目录")
    convert_parser.add_argument("--out", required=True, help="数据集输出根目录")
    convert_parser.add_argument("--source-namespace", help="逻辑平台实例名（如 hangma-official）")
    convert_parser.add_argument("--producer-commit", help="生产者提交号")
    convert_parser.add_argument("--rules-hash", help="规则源文件清单哈希")
    convert_parser.add_argument("--guide-version", type=int, help="官方指南版本")
    convert_parser.add_argument("--guide-captured-at", help="指南来源采集日期 YYYY-MM-DD")

    pack_parser = subparsers.add_parser("pack", help="封存 bundle 为 tar.gz + .sha256")
    pack_parser.add_argument("bundle", help="bundle 目录")
    pack_parser.add_argument("--out", required=True, help="归档输出路径")

    post = subparsers.add_parser("postgame", help="下载（可选）并生成证据包、数据集和规则诊断")
    post.add_argument("session", help="含 audit/ 或 slot-*/runs/ 和 official/ 的会话目录")
    post.add_argument("--source-namespace", default="hangma-official")
    post.add_argument("--ruleset-version", help="本次重分析的规则版本；默认当前实现版本")
    post.add_argument("--rule-config", help="JSON：base_score 与 you_cai_bi_kao；缺失时不猜历史配置")
    post.add_argument("--download", action="store_true")
    post.add_argument("--runtime-config")
    post.add_argument("--room")
    post.add_argument("--batch", type=int)
    migrate = subparsers.add_parser("migrate-runs", help="关闭旧运行后迁入规范根，保留兼容路径")
    migrate.add_argument("--legacy", default="runs")
    migrate.add_argument("--artifacts", default="artifacts")
    history = subparsers.add_parser("import-history", help="按原文哈希归并历史官方牌谱")
    history.add_argument("sources", nargs="+", type=Path)
    history.add_argument("--out", type=Path, default=Path("artifacts/sessions/history"))
    unpack = subparsers.add_parser("unpack", help="核验归档并安全解包到新目录")
    unpack.add_argument("archive")
    unpack.add_argument("--out", required=True)
    catalog = subparsers.add_parser("catalog", help="更新全部会话的相对路径索引")
    catalog.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            from hangma_bot.offline.artifact_store import catalog_sessions
            result = catalog_sessions(args.artifacts)
            print(json.dumps({"sessions": len(result["sessions"]), "catalog": str(args.artifacts / "catalog.json")}, ensure_ascii=False))
            return EXIT_OK
        if args.command == "postgame":
            return _cmd_postgame(args)
        if args.command == "migrate-runs":
            from hangma_bot.offline.artifact_store import migrate_runs
            print(json.dumps(migrate_runs(args.legacy, args.artifacts), ensure_ascii=False))
            return EXIT_OK
        if args.command == "import-history":
            from hangma_bot.offline.artifact_store import import_official_history
            result = import_official_history(args.sources, args.out, project_root=Path.cwd().resolve())
            print(json.dumps({"unique_documents": result["unique_documents"], "source_copies": result["source_copies"],
                "partial_runs": len(result["partial_audit_runs"]), "errors": result["errors"], "report": str(args.out / "history-import.json")}, ensure_ascii=False))
            return EXIT_OK
        if args.command == "unpack":
            from hangma_bot.adapters.recording.bundle import extract_bundle
            print(json.dumps(extract_bundle(args.archive, args.out), ensure_ascii=False))
            return EXIT_OK
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
        if args.command == "watch":
            return _cmd_watch(args)
        if args.command == "collect-test-room":
            return _cmd_collect_test_room(args)
        if args.command == "convert":
            return _cmd_convert(args)
        if args.command == "pack":
            return _cmd_pack(args)
    except (ValueError, OSError, FileNotFoundError) as exc:
        print("错误: {}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        return EXIT_FAILED
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
