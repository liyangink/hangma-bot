#!/usr/bin/env python3
"""审计离线工具：validate / inspect / watch / collect-test-room / convert / pack。

只解析参数并调用组合根装配的实际用例（审计增强方案 §6）：

    python scripts/audit_tool.py validate PATH
    python scripts/audit_tool.py inspect PATH --game GAME_ID [--json]
    python scripts/audit_tool.py watch RUNS_ROOT [--json] [--interval 1]
    python scripts/audit_tool.py collect-test-room --runtime-config CONFIG --room ROOM --batch BATCH --out DIR
    python scripts/audit_tool.py convert BUNDLE --out DATASET --source-namespace NS
    python scripts/audit_tool.py pack BUNDLE --out ARCHIVE

- validate：离线审计验证器（recording.validator）；
- inspect：只读查看某场次的决策链（与 watch 共用读取器）；
- watch：轮询审计根，只输出状态变化；--json 输出逐行 JSON；
- collect-test-room：免认证下载测试房间赛后数据（指南 v14 §2.5）到
  bundle 的 official/{download_id}/（先写 .partial，校验后原子改名）；
- convert：bundle → 统一牌谱数据集（offline.replay.build_dataset）；
- pack：封存 bundle 为 tar.gz + .sha256。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
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


def _run_snapshot(run_dir: Path) -> dict:
    """一个 run 目录的只读快照：种类计数、最近提交、数据更新时间。"""

    result = read_records(run_dir)
    counts = {}
    last_outcome = None
    ended = None
    for record in result.records:
        if record.kind is None or record.error is not None:
            continue
        counts[record.kind] = counts.get(record.kind, 0) + 1
        if record.kind == "submission_outcome":
            last_outcome = (record.payload or {}).get("outcome") or (record.payload or {}).get("outcome_type")
        elif record.kind == "decision_ended":
            ended = (record.payload or {}).get("end_reason")
    summary_file = run_dir / "summary.json"
    closed = summary_file.is_file()
    return {
        "run_id": run_dir.name,
        "counts": counts,
        "closed": closed,
        "last_outcome": last_outcome,
        "last_end_reason": ended,
        "issues": len(result.issues),
    }


def _cmd_watch(args: argparse.Namespace) -> int:
    root = Path(args.runs_root)
    interval = args.interval if args.interval and args.interval > 0 else 1
    previous: dict[str, dict] = {}
    try:
        while True:
            runs_dir = root / "runs"
            current: dict[str, dict] = {}
            if runs_dir.is_dir():
                for run_dir in sorted(runs_dir.iterdir()):
                    if run_dir.is_dir():
                        try:
                            current[run_dir.name] = _run_snapshot(run_dir)
                        except OSError:
                            continue
            for run_id in sorted(current):
                snapshot = current[run_id]
                if previous.get(run_id) != snapshot:
                    if args.json:
                        print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
                    else:
                        print("[{}] counts={} closed={} outcome={} end={} issues={}".format(
                            run_id, snapshot["counts"], snapshot["closed"],
                            snapshot["last_outcome"], snapshot["last_end_reason"],
                            snapshot["issues"],
                        ))
            previous = current
            time.sleep(interval)
    except KeyboardInterrupt:
        return EXIT_OK


# ---------------------------------------------------------------------------
# collect-test-room
# ---------------------------------------------------------------------------


def _load_base_url(config_path: Path) -> str:
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("运行配置必须是 JSON 对象")
    base_url = data.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
        raise ValueError("运行配置缺少合法 base_url（http/https）")
    return base_url.rstrip("/")


def _http_get_json(base_url: str, path: str, timeout: float = 30.0):
    """GET JSON；失败抛出可读异常（保留响应原文供诊断）。"""

    request = urllib.request.Request(base_url + path)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            "GET {} -> HTTP {}: {}".format(path, exc.code, body[:300])
        ) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("GET {} -> {}".format(path, exc)) from None


def _write_partial_then_commit(path: Path, text: str) -> None:
    """先写 .partial，JSON 校验通过后原子改名；失败保留诊断不伪造空牌谱。"""

    partial = Path(str(path) + ".partial")
    partial.write_text(text, encoding="utf-8")
    json.loads(text)  # 校验失败保留 .partial 供诊断
    partial.replace(path)


def _cmd_collect_test_room(args: argparse.Namespace) -> int:
    base_url = _load_base_url(Path(args.runtime_config))
    out_dir = Path(args.out)
    download_id = "dl-" + uuid.uuid4().hex
    official_dir = out_dir / "official" / download_id
    official_dir.mkdir(parents=True, exist_ok=True)
    guide_version = None
    try:
        with Path(args.runtime_config).open("r", encoding="utf-8") as handle:
            config = json.load(handle)
            if isinstance(config, dict) and isinstance(config.get("known_guide_version"), int):
                guide_version = config["known_guide_version"]
    except (OSError, json.JSONDecodeError):
        pass
    games_raw = _http_get_json(base_url, "/api/test-rooms/{}/games".format(args.room))
    games_text = json.dumps(games_raw, ensure_ascii=False)
    _write_partial_then_commit(official_dir / "games.json", games_text)
    game_id = None
    if isinstance(games_raw, dict) and isinstance(games_raw.get("games"), list):
        for game in games_raw["games"]:
            if game.get("batch") == args.batch:
                game_id = game.get("game_id")
    try:
        events = _http_get_json(
            base_url,
            "/api/test-rooms/{}/games/{}/events".format(args.room, args.batch),
        )
    except RuntimeError as exc:
        # 403 GAME_NOT_FINISHED / 404：记录事实与诊断，不伪造空牌谱。
        diagnostic = {"error": str(exc)}
        (official_dir / "events.download_error.json").write_text(
            json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("下载失败: {}".format(exc), file=sys.stderr)
        return EXIT_FAILED
    events_text = json.dumps(events, ensure_ascii=False)
    _write_partial_then_commit(official_dir / "events.json", events_text)
    if game_id is None and isinstance(events, dict) and isinstance(events.get("game_id"), str):
        game_id = events["game_id"]
    source = {
        "download_id": download_id,
        "room_id": args.room,
        "batch": args.batch,
        "game_id": game_id,
        "guide_version": guide_version,
        "captured_at_unix_ms": int(time.time() * 1000),
    }
    # 与 games/events 一致：先写 .partial，JSON 校验通过后原子改名。
    _write_partial_then_commit(
        official_dir / "source.json", json.dumps(source, ensure_ascii=False, indent=2)
    )
    print(
        "已采集: room={} batch={} game={} -> {}/official/{}/".format(
            args.room, args.batch, game_id, out_dir, download_id
        )
    )
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
    watch_parser.add_argument("--interval", type=float, default=1.0, help="轮询间隔秒数")

    collect_parser = subparsers.add_parser("collect-test-room", help="下载测试房间赛后数据")
    collect_parser.add_argument("--runtime-config", required=True, help="运行配置 JSON（取 base_url）")
    collect_parser.add_argument("--room", required=True, help="房间 id")
    collect_parser.add_argument("--batch", required=True, type=int, help="批次号")
    collect_parser.add_argument("--out", required=True, help="bundle 根目录")

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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
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
