#!/usr/bin/env python3
"""测试房对比战役守护：开房 → 按整轮续打 → 赛后处理 → 增量落库。

唤醒协议（2026-09-14 与用户约定）
--------------------------------
本脚本**不做睡眠轮询**。一次 round 子命令恰好打一个整轮
（M 场 × Rounds 单局），随后立即走完「下载官方牌谱 → postgame →
提升到 datasets/derived/ → 增量落库 → 打印摘要」然后退出。
调用方（Lead Agent）把 round 当后台任务挂起；任务结束时收到的完成
通知**就是**「整轮唤醒」——收到通知后立刻再挂起下一个 round，然后
并行做局势分析。房间空闲 timeout_min 分钟会自动 close，因此续打必须
在分析之前先挂起。

为什么必须「打完一个整轮就立刻下载」
------------------------------------
GET /api/test-rooms/{id}/games/{batch}/events 只返回**最新一轮**的批次
数据（官方指南 v1 测试房数据 API）。只要开打下一轮，上一轮的官方牌谱就
再也取不到了。逐轮下载是硬约束，不是优化。

路径约定
--------
- 战役运行态（gitignored）：runs/<campaign>/
- 逐轮审计会话：artifacts/sessions/<campaign>-r<K>/
- 提升后的对比数据池：datasets/derived/<pool>/{hands,manifests,validations,official}
- Token：runs/<campaign>/tokens/<slot>.token（0600，不打印、不入库）

退出码：0 = 本子命令全部步骤成功；1 = 有步骤失败（摘要仍会打印，便于
在唤醒时判断是否需要人工介入）；2 = 用法/前置条件错误。
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# 门户会话 Cookie 只用于「建房」这一步（测试房创建是门户 API）。
PORTAL_COOKIE = REPO_ROOT / ".private" / "portal-session" / "cookie.txt"
PY = REPO_ROOT / ".venv" / "bin" / "python"
DB_PATH = REPO_ROOT / "datamart" / "hangma-eval.db"
STRATEGY_MAP = REPO_ROOT / "datamart" / "strategy-map.json"

BASE_URL = "https://10.240.169.190:18080"
INSECURE_HOSTS = ["10.240.169.190"]
SOURCE_NAMESPACE = "hangma-official"

# 本战役的四条对比臂：等胡（V2+等胡）是当前验证过的最强启发式基线，
# 另外三条是 2026-09-14 部署的序列策略网络候选（同一 V2+等胡 基线 + 网络重排）。
DEFAULT_ARMS = {
    "qinglong": "v2_hu_upgrade_v1",
    "baihu": "sequence_model_2048_projected_v1",
    "zhuque": "sequence_model_4096_direct_v1",
    "xuanwu": "sequence_model_4096_projected_v1",
}
SLOT_ORDER = ("qinglong", "baihu", "zhuque", "xuanwu")
# 建房规则必须落在 _test_room_upgrade_rules 的适用范围内（BaseScore=1、
# YouCaiBiKao=false），否则候选身份会在报名前直接终止。
ROOM_RULES = {"base_score": 1, "you_cai_bi_kao": False}


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------


def _known_guide_version() -> int:
    """取本机已审查的指南版本，避免这里写死的数字与代码漂移。"""

    from hangma_bot.adapters.official.dto import KNOWN_GUIDE_VERSION

    return int(KNOWN_GUIDE_VERSION)


def log(message: str) -> None:
    """带本地时间的进度行；只打非敏感信息。"""

    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message), flush=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict) -> None:
    """原子写：先写同目录临时文件再 replace，中断不会留下半截 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temp.replace(path)


def _display(path: Path) -> str:
    """日志里优先显示相对仓库根的路径；仓外路径原样显示，绝不因相对化而抛错。"""

    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def campaign_dir(args) -> Path:
    path = Path(args.campaign)
    return path if path.is_absolute() else REPO_ROOT / path


def load_campaign(args) -> dict:
    path = campaign_dir(args) / "campaign.json"
    if not path.is_file():
        raise SystemExit("找不到战役文件 %s；先跑 open" % path)
    return read_json(path)


def portal_cookie() -> str:
    """读门户会话 Cookie 并只返回请求头值；任何日志都不得打印它。"""

    if not PORTAL_COOKIE.is_file():
        raise SystemExit("缺少门户会话 Cookie：%s" % PORTAL_COOKIE)
    raw = PORTAL_COOKIE.read_text(encoding="utf-8").strip()
    return raw if "=" in raw else "session=" + raw


def _public_config(campaign: dict) -> dict:
    return {"base_url": campaign.get("base_url", BASE_URL),
            "insecure_hosts": list(INSECURE_HOSTS)}


def _release_id_for_strategy(strategy: str) -> str | None:
    """获批 R18 候选的真实网络配置必须绑定当前发布包摘要。"""
    from hangma_bot.bootstrap import (
        R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
        R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
    )

    return {
        R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY: R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY: R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
    }.get(strategy)


def _runtime_config(root: Path, round_no: int, campaign: dict) -> tuple:
    """生成本轮 run_test_room.py 的房间配置与审计会话目录。

    每轮一个独立会话：赛后处理的输入必须只属于本轮，否则 postgame 会把上一轮
    已封存的 run 再封存一次（新 job、永不覆盖，但报告会混轮）。
    """

    session = REPO_ROOT / "artifacts" / "sessions" / ("%s-r%d" % (root.name, round_no))
    tokens = root / "tokens"
    config = {
        "mode": "test_room",
        "base_url": campaign["base_url"],
        "expected_tournament_id": campaign["room_id"],
        "known_guide_version": campaign["known_guide_version"],
        "audit_root": str(session / "audit"),
        "strategy": campaign["arms"][SLOT_ORDER[0]],
        "insecure_hosts": list(INSECURE_HOSTS),
        "sse_enabled": False,
        "identities": [],
        # 允许两次有界重启：致命协议错误在无人值守的长轮里必须能被消化，
        # 但重启后仍由权威 /api/me 与 seq=0 快照恢复，复用的是协议而不是内存判断。
        "restart": {"max_restarts": 2, "base_delay_seconds": 2.0, "factor": 2.0,
                    "max_delay_seconds": 20.0, "finished_restart_delay_seconds": 2.0},
    }
    for slot in SLOT_ORDER:
        strategy = campaign["arms"][slot]
        identity = {"slot": slot, "token_file": str(tokens / (slot + ".token")),
                    "strategy": strategy}
        release_id = _release_id_for_strategy(strategy)
        if release_id is not None:
            identity["expected_policy_release_id"] = release_id
        config["identities"].append(identity)
    return config, session


# ---------------------------------------------------------------------------
# open：建房
# ---------------------------------------------------------------------------


def _create_room(m: int, rounds: int, timeout_min: int) -> dict:
    """经门户 API 建一个测试房；返回原始响应（含四令牌，调用方负责落盘）。"""

    import httpx

    payload = {
        "m": m,
        "rounds": rounds,
        "base_score": ROOM_RULES["base_score"],
        "you_cai_bi_kao": ROOM_RULES["you_cai_bi_kao"],
        "peng_timeout_sec": 1,
        "chi_timeout_sec": 1,
        "discard_timeout_sec": 3,
        "timeout_min": timeout_min,
    }
    with httpx.Client(verify=False, timeout=40.0, headers={"Cookie": portal_cookie()}) as client:
        response = client.post(BASE_URL + "/portal/api/test-rooms", json=payload)
        if response.status_code != 200:
            raise SystemExit("建房失败 HTTP %s：%s" % (response.status_code, response.text[:300]))
        doc = response.json()
    if not doc.get("room_id") or len(doc.get("players") or []) != 4:
        raise SystemExit("建房响应不含 room_id 或 4 个玩家")
    return doc


def cmd_open(args) -> int:
    root = campaign_dir(args)
    if (root / "campaign.json").is_file() and not args.force:
        campaign = read_json(root / "campaign.json")
        log("战役已存在（room=%s，已完成 %d 轮）；要换房请加 --force"
            % (campaign["room_id"], campaign["rounds_done"]))
        _print_arms(campaign)
        return 0

    arms = dict(DEFAULT_ARMS)
    if args.arms:
        arms = {}
        for item in args.arms.split(","):
            slot, _, strategy = item.partition("=")
            if slot not in SLOT_ORDER or not strategy:
                raise SystemExit("--arms 格式为 slot=strategy，slot 取 " + "/".join(SLOT_ORDER))
            arms[slot] = strategy
        if sorted(arms) != sorted(SLOT_ORDER):
            raise SystemExit("--arms 必须给满四个槽位")

    log("建房 m=%d rounds=%d timeout_min=%d" % (args.m, args.rounds, args.timeout_min))
    doc = _create_room(args.m, args.rounds, args.timeout_min)
    room_id = doc["room_id"]
    tokens_dir = root / "tokens"
    tokens_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tokens_dir, 0o700)
    for slot, player in zip(SLOT_ORDER, doc["players"]):
        path = tokens_dir / (slot + ".token")
        path.write_text(player["token"].strip() + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    campaign = {
        "schema": "testroom-campaign-v1",
        "campaign": root.name,
        "room_id": room_id,
        "base_url": BASE_URL,
        "known_guide_version": _known_guide_version(),
        "m": args.m,
        "rounds": args.rounds,
        "timeout_min": args.timeout_min,
        "target_rounds": args.target_rounds,
        "pool": args.pool or root.name,
        "rules": dict(ROOM_RULES),
        "arms": arms,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rounds_done": 0,
        "rounds_log": [],
        "identities": {},
    }
    write_json(root / "campaign.json", campaign)
    log("room_id=%s；每轮 %d 场 × %d 单局 = %d 单局"
        % (room_id, args.m, args.rounds, args.m * args.rounds))
    log("战役目标 %d 轮 = %d 单局" % (args.target_rounds, args.target_rounds * args.m * args.rounds))
    _print_arms(campaign)

    campaign["identities"] = resolve_identities(root)
    write_json(root / "campaign.json", campaign)
    for slot in SLOT_ORDER:
        log("身份 %-9s %-34s %s" % (slot, arms[slot], campaign["identities"].get(slot) or "(取不到)"))
    if not args.no_attribute:
        changed = _register_identities(campaign)
        log("strategy-map.json 写入 %d 条策略归因" % len(changed))
    log("下一步：python scripts/test_room_campaign_watchdog.py preflight --campaign " + root.name)
    return 0


def resolve_identities(root: Path) -> dict:
    """逐个令牌取 /api/me 的 user_id：座位级策略归因靠它，取不到就不能落库。"""

    import asyncio

    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig

    async def resolve() -> dict:
        found = {}
        for slot in SLOT_ORDER:
            token = (root / "tokens" / (slot + ".token")).read_text(encoding="utf-8").strip()
            transport = OfficialTransport(
                token, TransportConfig(base_url=BASE_URL, insecure_hosts=frozenset(INSECURE_HOSTS)))
            try:
                found[slot] = json.loads((await transport.request("GET", "/api/me")).text).get("user_id")
            finally:
                await transport.aclose()
        return found

    return asyncio.run(resolve())


def _register_identities(campaign: dict) -> list:
    """把四个身份写进 datamart/strategy-map.json 的 identities 块。

    座位级策略归因只认这张表（build.py 座位循环）。四个槽位的策略在整个战役里
    固定不轮换：官方每个场次都会重新随机换座位，座位偏差在 M 场内已被随机化，
    静态映射反而让归因可审计。
    """

    identities = (read_json(STRATEGY_MAP).get("identities") or {})
    text = STRATEGY_MAP.read_text(encoding="utf-8")
    anchor = '"identities": {\n'
    if anchor not in text:
        raise SystemExit("strategy-map.json 结构变化：找不到 identities 块")
    changed = []
    for slot in SLOT_ORDER:
        user_id = campaign["identities"].get(slot)
        strategy = campaign["arms"][slot]
        if not user_id or identities.get(user_id) == strategy:
            continue
        text = text.replace(anchor, anchor + '    "%s": "%s",\n' % (user_id, strategy), 1)
        changed.append((user_id, strategy))
    if changed:
        STRATEGY_MAP.write_text(text, encoding="utf-8")
    return changed


def _print_arms(campaign: dict) -> None:
    log("对比臂：")
    for slot in SLOT_ORDER:
        user_id = (campaign.get("identities") or {}).get(slot) or "-"
        log("  %-9s %-34s %s" % (slot, campaign["arms"][slot], user_id))


# ---------------------------------------------------------------------------
# preflight：不联网地装配四个策略
# ---------------------------------------------------------------------------


def cmd_preflight(args) -> int:
    """逐个策略走一遍组合根装配：模型装载、规则适用范围、保底动作。

    这一步在真正开打之前跑完，可以把「模型装载失败 / 规则不匹配」这类启动期
    错误挡在房间之外——否则四个身份里任意一个起不来，整个房间开不了赛，而
    房间已经建好了。
    """

    campaign = load_campaign(args)
    from hangma_bot.bootstrap import RuntimeConfig, RuntimeMode, TokenKind, build_runtime

    scratch = campaign_dir(args) / "preflight-audit"
    failed = 0
    for slot in SLOT_ORDER:
        strategy = campaign["arms"][slot]
        config = RuntimeConfig(
            mode=RuntimeMode.TEST_ROOM,
            base_url=campaign["base_url"],
            expected_tournament_id=campaign["room_id"],
            known_guide_version=campaign["known_guide_version"],
            token="preflight-not-a-real-token",
            token_kind=TokenKind.TEST,
            audit_root=scratch / slot,
            strategy=strategy,
            expected_policy_release_id=_release_id_for_strategy(strategy),
            slot=slot,
            insecure_hosts=frozenset(INSECURE_HOSTS),
        )
        try:
            started = time.monotonic()
            runtime = build_runtime(config)
            log("%-9s %-34s OK  %s 装配 %.2fs"
                % (slot, strategy, type(runtime.policy).__name__, time.monotonic() - started))
        except Exception as error:  # noqa: BLE001 - 预检要把任何装配失败都报出来
            failed += 1
            log("%-9s %-34s 失败 %s: %s" % (slot, strategy, type(error).__name__, error))
    shutil.rmtree(scratch, ignore_errors=True)
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# round：打一个整轮并做完赛后处理
# ---------------------------------------------------------------------------


def _finished_batches(campaign: dict, round_no: int) -> list:
    """列出官方 games.json 中属于第 round_no 轮且已完赛的批次号。"""

    with _archive_client(campaign) as client:
        response = client.get("/api/test-rooms/%s/games" % campaign["room_id"])
        if response.status_code != 200:
            log("games.json HTTP %s：%s" % (response.status_code, response.text[:200]))
            return []
        doc = response.json()
    batches = sorted({int(game["batch"]) for game in doc.get("games") or []
                      if int(game.get("round") or 0) == round_no and game.get("status") == "finished"})
    log("官方 games.json：房间 status=%s，第 %d 轮完赛批次 %s"
        % (doc.get("status"), round_no, batches))
    return batches


def _archive_client(campaign: dict):
    from hangma_bot.bootstrap import build_public_archive_client

    return build_public_archive_client(_public_config(campaign))


def _download_round(campaign: dict, round_no: int, session: Path, batches: list | None = None,
                    attempts: int = 3) -> tuple:
    """下载本轮全部批次到会话 official/dl-*；返回 (成功数, 失败批次)。

    官方测试房数据 API 是每房间 5/s，且 collect_test_room 每批次要发 4 个请求。
    逐批次连发会瞬时超限（实测 10 个批次整片 429），因此批次之间留间隔、单批次
    失败按 1.5s/3s 退避重试；这里的等待是有界协议退避，不是轮询。
    """

    from hangma_bot.adapters.official.archive_download import collect_test_room

    if batches is None:
        batches = _finished_batches(campaign, round_no)
    ok, failed = 0, []
    with _archive_client(campaign) as client:
        for index, batch in enumerate(batches):
            for attempt in range(1, attempts + 1):
                try:
                    result = collect_test_room(client, campaign["room_id"], batch, session)
                    ok += 1
                    log("下载批次 %d → %s" % (batch, Path(result["directory"]).name))
                    break
                except Exception as error:  # noqa: BLE001 - 单批次失败不阻断其余批次
                    if attempt == attempts:
                        failed.append(batch)
                        log("下载批次 %d 连续 %d 次失败：%s" % (batch, attempts, error))
                    else:
                        delay = 1.5 * attempt
                        log("下载批次 %d 第 %d 次失败（%s），%.1fs 后重试" % (batch, attempt, error, delay))
                        time.sleep(delay)
            if index + 1 < len(batches) and not failed:
                time.sleep(0.3)
    return ok, failed


def _promote(campaign: dict, round_no: int, session: Path, job: Path) -> dict:
    """把 postgame 产物提升为可入库的对比数据池分片。

    只写 datasets/derived/<pool>/（库的唯一主源）：hands/*.gz 是按轮追加的
    不可变分片；validations/<room>.audit.json 按 run_id 合并（同房多轮会产生
    多个 run）；manifests/<room>.json 覆盖为最新（全战役同规则，且 build.py
    只按文件名 stem 取房号，所以必须叫 <room>.json）。
    """

    pool = REPO_ROOT / "datasets" / "derived" / campaign["pool"]
    room = campaign["room_id"]
    (pool / "hands").mkdir(parents=True, exist_ok=True)
    (pool / "manifests").mkdir(parents=True, exist_ok=True)
    (pool / "validations").mkdir(parents=True, exist_ok=True)

    children = sorted(path for path in (job / "derived").iterdir() if path.is_dir())
    if len(children) != 1:
        raise SystemExit("postgame 数据集目录不是恰好一个：%s" % children)
    dataset = children[0]

    rows = 0
    shard = pool / "hands" / ("%s-r%d.hands.jsonl.gz" % (room, round_no))
    with gzip.open(shard, "wt", encoding="utf-8") as out:
        for line in (dataset / "hands.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.write(line + "\n")
                rows += 1

    shutil.copy2(dataset / "manifest.json", pool / "manifests" / ("%s.json" % room))

    audit_path = pool / "validations" / ("%s.audit.json" % room)
    merged = read_json(audit_path) if audit_path.is_file() else {}
    fresh = read_json(job / "audit-validation.json")
    merged.update(fresh)
    write_json(audit_path, merged)

    official_src = session / "official"
    if official_src.is_dir():
        official_dst = pool / "official" / room / "official"
        official_dst.mkdir(parents=True, exist_ok=True)
        for folder in sorted(path for path in official_src.iterdir() if path.is_dir()):
            target = official_dst / folder.name
            if not target.exists():
                shutil.copytree(folder, target)

    return {"hands_shard": shard.name, "hands_rows": rows, "runs_merged": len(fresh)}


def _degradation_summary(session: Path) -> list:
    """按槽位统计本轮降级原因：这是「模型到底跑没跑」的唯一硬指标。

    序列策略在观察历史不完整、规则降级或预算耗尽时会明确回退到保底基线并在
    plan.degraded_reasons 里留痕（sequence_model_policy.py 第 90 行起）。若不看这一栏，
    「三条模型臂与基线打平」会被误读成「模型不更强」，而真实原因是模型根本没执行。
    """

    import collections

    rows = []
    for slot_dir in sorted((session / "audit").glob("slot-*")):
        counter = collections.Counter()
        plans = 0
        degraded_decisions = 0
        for path in slot_dir.glob("**/decisions.jsonl"):
            for line in path.open(encoding="utf-8", errors="replace"):
                if '"decision_planned"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = record.get("payload") or {}
                if not payload.get("candidates"):
                    continue
                plans += 1
                reasons = list(payload.get("degraded_reasons") or [])
                if reasons:
                    degraded_decisions += 1
                for reason in reasons:
                    counter[str(reason).split(":")[0] if str(reason).startswith("sequence_model") else str(reason)[:24]] += 1
        if plans:
            rows.append({"slot": slot_dir.name[len("slot-"):], "plans": plans,
                         "degraded": degraded_decisions,
                         "degraded_rate": round(100.0 * degraded_decisions / plans, 2),
                         "reasons": dict(counter.most_common(4))})
    return rows


def _ingest() -> dict:
    """增量落库；保留 build.py 摘要尾部行便于在唤醒时核对。"""

    result = subprocess.run([str(PY), "datamart/build.py"], cwd=str(REPO_ROOT),
                            capture_output=True, text=True)
    tail = [line for line in result.stderr.strip().splitlines() if line.strip()][-6:]
    return {"exit_code": result.returncode, "tail": tail, "stdout": result.stdout.strip()[-800:]}


def _arm_stats(tournament_key: str) -> list:
    """按臂汇总单局座位事实；这是唤醒时第一眼要看的表。"""

    if not DB_PATH.is_file():
        return []
    query = """
        SELECT s.strategy_key AS strategy,
               COUNT(*) AS seats,
               COUNT(DISTINCT h.game_id) AS games,
               SUM(s.is_winner) AS wins,
               SUM(CASE WHEN s.is_local_first = 1 THEN 1 ELSE 0 END) AS firsts,
               SUM(s.score_delta) AS net,
               AVG(s.score_delta) AS avg_net,
               SUM(CASE WHEN s.is_dealer = 1 THEN 1 ELSE 0 END) AS dealer_hands,
               SUM(CASE WHEN s.is_dealer = 1 AND s.is_winner = 1 THEN 1 ELSE 0 END) AS dealer_wins
        FROM fact_hand_seat s JOIN fact_hand h ON h.hand_key = s.hand_key
        WHERE h.tournament_key = ? AND s.is_self = 1
        GROUP BY s.strategy_key ORDER BY net DESC
    """
    connection = sqlite3.connect(str(DB_PATH))
    try:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, (tournament_key,))]
    finally:
        connection.close()


def _print_stats(rows: list) -> None:
    if not rows:
        log("库里还没有该房间的座位行（归因或落库未生效）")
        return
    log("%-34s %6s %6s %8s %8s %9s %8s %8s" %
        ("策略", "局数", "胡牌", "胡率%", "一位%", "净分", "局均", "庄胜%"))
    for row in rows:
        hands = row["seats"] or 0
        log("%-34s %6d %6d %8.2f %8.2f %9d %8.2f %8.1f" % (
            row["strategy"], hands, row["wins"] or 0,
            100.0 * (row["wins"] or 0) / hands if hands else 0.0,
            100.0 * (row["firsts"] or 0) / hands if hands else 0.0,
            row["net"] or 0, row["avg_net"] or 0.0,
            100.0 * (row["dealer_wins"] or 0) / (row["dealer_hands"] or 1),
        ))


def _run_round_process(config_path: Path, log_path: Path, timeout_sec: int) -> tuple:
    """跑一轮 run_test_room.py --once；超时按进程组整棵杀掉。"""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            [str(PY), "scripts/run_test_room.py", "--config", str(config_path), "--once"],
            cwd=str(REPO_ROOT), stdout=stream, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = process.wait(timeout=timeout_sec)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                code = process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                code = process.wait()
            timed_out = True
    return code, round(time.monotonic() - started, 1), timed_out


def _existing_runs(session: Path) -> list:
    """列出会话里已有的审计 run 目录（含未闭合的）。"""

    return sorted({path.parent for path in (session / "audit").glob("slot-*/runs/*/manifest.json")})


def _guard_fresh_session(session: Path, round_no: int, *, force: bool) -> int:
    """拒绝把新批次打进一个已经有 run 的会话。

    中断或暂停之后 campaign.json 的 rounds_done 不会前进，下一次 round 会算出同一个
    轮号和同一个会话目录。若直接开打，两轮身份进程的审计会落进同一个会话，postgame
    会把它们封进同一份数据集——看起来像一轮，实际混了两轮。这里显式拒绝，并给出
    三条明确出路：重做赛后、换下一轮、或显式确认重打。
    """

    runs = _existing_runs(session)
    if not runs or force:
        return 0
    closed = [run for run in runs if (run / "summary.json").is_file()]
    state = ("已闭合 %d 个" % len(closed)) if len(closed) == len(runs) else ("有 %d 个未闭合" % (len(runs) - len(closed)))
    log("会话 %s 已有第 %d 轮的 %d 个 run（%s），拒绝重复开打。"
        % (_display(session), round_no, len(runs), state))
    log("  重做赛后并落库：--skip-run ｜ 直接开下一轮：--round %d ｜ 确实要重打本轮：--force-run"
        % (round_no + 1))
    return 2


def cmd_round(args) -> int:
    root = campaign_dir(args)
    campaign = load_campaign(args)
    round_no = args.round or (campaign["rounds_done"] + 1)
    config, session = _runtime_config(root, round_no, campaign)
    guard = _guard_fresh_session(session, round_no, force=args.force_run or args.skip_run)
    if guard:
        return guard
    config_path = root / ("room-r%d.json" % round_no)
    write_json(config_path, config)
    write_json(root / "room.json", config)

    summary = {"round": round_no, "session": _display(session),
               "started_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "room_id": campaign["room_id"]}
    log("第 %d 轮开始：m=%d rounds=%d 会话=%s"
        % (round_no, campaign["m"], campaign["rounds"], session.name))

    failures = []
    if args.skip_run:
        log("--skip-run：复用会话里已有的审计 run")
        code, elapsed, timed_out = 0, 0.0, False
    else:
        code, elapsed, timed_out = _run_round_process(
            config_path, root / "logs" / ("round-%d.run.log" % round_no), args.timeout_sec)
        log("身份进程退出码=%s 用时=%.1fs%s" % (code, elapsed, "（超时已杀）" if timed_out else ""))
    summary.update({"run_exit_code": code, "run_seconds": elapsed, "run_timed_out": timed_out})
    if code != 0:
        failures.append("身份进程退出码 %s" % code)

    batches = [] if args.skip_download else _finished_batches(campaign, round_no)
    if args.skip_download:
        log("--skip-download：跳过牌谱下载")
        ok, failed = 0, []
    else:
        ok, failed = _download_round(campaign, round_no, session, batches=batches)
    summary.update({"batches_expected": len(batches), "batches_ok": ok, "batches_failed": failed})
    if failed:
        failures.append("下载失败批次 %s（该轮牌谱已取不到，下一轮会覆盖）" % failed)

    job = None
    try:
        from hangma_bot.bootstrap import DEFAULT_RULESET_VERSION
        from hangma_bot.offline.postgame import finalize_session

        job = finalize_session(session, source_namespace=SOURCE_NAMESPACE,
                               ruleset_version=DEFAULT_RULESET_VERSION,
                               rule_config={"base_score": ROOM_RULES["base_score"],
                                            "you_cai_bi_kao": ROOM_RULES["you_cai_bi_kao"]})
        log("postgame 完成：%s" % Path(job["job"]).name)
        summary["postgame_job"] = _display(Path(job["job"]))
        summary["postgame_runs"] = job["run_count"]
        summary["postgame_official"] = job["official_documents"]
        summary["audit_complete"] = job["audit_complete"]
    except Exception as error:  # noqa: BLE001 - 赛后失败要连原因一起留给唤醒
        failures.append("postgame 失败：%s: %s" % (type(error).__name__, error))
        log(failures[-1])

    if job is not None:
        try:
            summary["promoted"] = _promote(campaign, round_no, session, Path(job["job"]))
            log("数据池分片写入 %s" % summary["promoted"]["hands_shard"])
        except Exception as error:  # noqa: BLE001
            failures.append("提升数据池失败：%s: %s" % (type(error).__name__, error))
            log(failures[-1])

    summary["degradation"] = _degradation_summary(session)
    log("—— 本轮策略执行健康（降级 = 回退到基线）——")
    for row in summary["degradation"]:
        log("  %-9s 决策 %-5d 降级 %-5d (%.1f%%)  原因 %s"
            % (row["slot"], row["plans"], row["degraded"], row["degraded_rate"],
               row["reasons"]))

    ingest = _ingest()
    summary["ingest"] = ingest
    log("落库 exit=%s %s" % (ingest["exit_code"], " / ".join(ingest["tail"][-2:])))

    stats = _arm_stats(campaign["room_id"])
    summary["stats"] = stats
    log("—— 本战役库内累计（按策略，座位行）——")
    _print_stats(stats)

    summary["finished_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    summary["failures"] = failures
    write_json(root / ("summary-r%d.json" % round_no), summary)

    campaign["rounds_done"] = max(campaign["rounds_done"], round_no)
    campaign.setdefault("rounds_log", []).append(
        {key: summary[key] for key in ("round", "run_exit_code", "run_seconds", "batches_ok",
                                       "postgame_runs", "failures", "finished_at")})
    write_json(root / "campaign.json", campaign)

    log("第 %d 轮完成%s；累计 %d/%d 轮"
        % (round_no, "（%d 项失败）" % len(failures) if failures else "",
           campaign["rounds_done"], campaign["target_rounds"]))
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# status：只读进度
# ---------------------------------------------------------------------------


def cmd_status(args) -> int:
    campaign = load_campaign(args)
    if campaign.get("paused"):
        log("已暂停：%s（%s）" % (campaign["paused"].get("reason", ""), campaign["paused"].get("at", "")))
    per_round = campaign["m"] * campaign["rounds"]
    log("战役 %s 房间 %s：%d/%d 轮，每轮 %d 场 × %d 单局 = %d 单局"
        % (campaign["campaign"], campaign["room_id"], campaign["rounds_done"],
           campaign["target_rounds"], campaign["m"], campaign["rounds"], per_round))
    log("目标 %d 单局，已完成约 %d" % (campaign["target_rounds"] * per_round,
                                      campaign["rounds_done"] * per_round))
    _print_arms(campaign)
    log("—— 库内累计 ——")
    _print_stats(_arm_stats(campaign["room_id"]))
    pool = REPO_ROOT / "datasets" / "derived" / campaign["pool"]
    if pool.is_dir():
        log("数据池 %s：%d 个分片"
            % (campaign["pool"], len(sorted((pool / "hands").glob("*.gz")))))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="test_room_campaign_watchdog.py",
        description="官方测试房多策略对比战役守护（整轮粒度，不睡眠轮询）")
    sub = parser.add_subparsers(dest="command", required=True)

    open_parser = sub.add_parser("open", help="建测试房、落盘令牌与战役记录")
    open_parser.add_argument("--campaign", required=True, help="战役目录（相对仓库根或绝对路径）")
    open_parser.add_argument("--m", type=int, default=10, help="每身份同时场数（默认 10）")
    open_parser.add_argument("--rounds", type=int, default=16, help="每场单局数（默认 16）")
    open_parser.add_argument("--timeout-min", type=int, default=30, help="房间空闲自动关闭分钟数（默认 30）")
    open_parser.add_argument("--target-rounds", type=int, default=4, help="战役目标整轮数（默认 4 = 640 单局）")
    open_parser.add_argument("--pool", default=None, help="datasets/derived 下的数据池名（默认同战役名）")
    open_parser.add_argument("--arms", default=None, help="覆盖对比臂，形如 slot=strategy,slot=strategy")
    open_parser.add_argument("--no-attribute", action="store_true", help="不写 strategy-map.json")
    open_parser.add_argument("--force", action="store_true", help="战役已存在时重新建房")
    open_parser.set_defaults(func=cmd_open)

    preflight_parser = sub.add_parser("preflight", help="不联网装配四个策略，验证模型与规则范围")
    preflight_parser.add_argument("--campaign", required=True)
    preflight_parser.set_defaults(func=cmd_preflight)

    round_parser = sub.add_parser("round", help="打一个整轮并完成下载/赛后/提升/落库")
    round_parser.add_argument("--campaign", required=True)
    round_parser.add_argument("--round", type=int, default=None, help="指定轮号（默认下一轮）")
    round_parser.add_argument("--timeout-sec", type=int, default=5400, help="身份进程总时限（默认 90 分钟）")
    round_parser.add_argument("--skip-run", action="store_true", help="复用已有审计 run（只重做赛后）")
    round_parser.add_argument("--force-run", action="store_true",
                              help="同会话已有 run 时仍开打新批次（默认拒绝，防止两轮混进一份数据集）")
    round_parser.add_argument("--skip-download", action="store_true", help="跳过牌谱下载")
    round_parser.set_defaults(func=cmd_round)

    status_parser = sub.add_parser("status", help="只读打印战役进度与库内累计")
    status_parser.add_argument("--campaign", required=True)
    status_parser.set_defaults(func=cmd_status)
    return parser


def main(argv=None) -> int:
    arguments = build_arg_parser().parse_args(argv)
    return arguments.func(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
