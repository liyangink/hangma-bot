"""赛后单入口：封存原始证据、生成统一数据集、输出带来源的规则核验制品。

只在离线运行。缺配置、缺历史和官方摘要冲突分别保留，不用新推导覆盖
旧事实；所有新制品按独立 job 保存，旧包/数据集拒绝覆盖。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from hangma_bot.adapters.official.replay import parse_room_document, round_data
from hangma_bot.adapters.recording import validate_run
from hangma_bot.adapters.recording.bundle import create_bundle, pack_bundle, verify_bundle, sha256_file
from hangma_bot.adapters.recording.reader import read_records
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.artifact_store import discover_runs, write_json
from hangma_bot.offline.replay import build_dataset
from hangma_bot.offline.replay_check import check_hand
from hangma_bot.offline.observation_audit import audit_observations
from hangma_bot.simulation.artifacts import compute_rules_hash


def session_status(root: Path) -> dict:
    """只读全部身份的当前统计；尾行问题显式返回，本地延后 Pass 不算提交失败。"""
    runs = []
    for run in discover_runs(root):
        result = read_records(run)
        counts, outcomes, transport, issues = Counter(), Counter(), Counter(), Counter()
        last = None
        closures = complete = 0
        for record in result.records:
            payload = record.payload or {}
            counts[record.kind] += 1
            if record.kind == "decision_input":
                obs = (payload.get("request") or {}).get("observation") or {}
                last = {k: obs.get(k) for k in ("game_id", "round_no", "consumed_seq", "phase")}
                issues.update(obs.get("observation_issues", []))
            if record.kind == "submission_outcome" and payload.get("audit_producer") == "application":
                outcomes[payload.get("outcome", "unknown")] += 1
                if payload.get("reason") == "pass_deferred_until_chi":
                    counts["deferred_pass"] += 1
            if record.kind == "raw_protocol_state":
                transport[str(payload.get("source")) + ":" + str(payload.get("http_status"))] += 1
            if payload.get("history_closure"):
                closures += 1
                complete += payload.get("history_complete") is True
        runs.append({"run_id": run.name, "path": os.path.relpath(run, root), "closed": (run / "summary.json").is_file(),
            "last_observation": last, "decision_inputs": counts["decision_input"], "deferred_pass": counts["deferred_pass"],
            "outcomes": dict(outcomes), "transport": dict(transport), "history_closures": closures,
            "complete_history_closures": complete, "observation_issues": dict(issues), "read_issues": [asdict(x) for x in result.issues]})
    return {"runs": runs, "run_count": len(runs), "all_closed": bool(runs) and all(r["closed"] for r in runs)}


def diagnose_official(path: Path, out: Path, *, ruleset_version: str, rule_config: dict | None = None) -> dict:
    """官方终局事件独立派生诊断行，复用唯一规则；未知配置时不猜计番条件。

    输出 hands.jsonl 为赛后全信息，只能作诊断/教师候选，不能作为学生观察。
    单局结果与累计积分直接复用正式解析器；摘要差异单独展示，不覆盖事件。
    缺墙、缺配置或缺累计积分仍不能变成可用教师候选。
    """
    document = json.loads(path.read_bytes())
    digest = sha256_file(path)
    source_path = path.parent / "source.json"
    source = json.loads(source_path.read_text()) if source_path.exists() else {}
    recorded_config = source.get("rule_config")
    if recorded_config and rule_config and any(recorded_config.get(k) != rule_config.get(k) for k in ("base_score", "you_cai_bi_kao")):
        raise ValueError("显式规则配置与原始来源配置冲突")
    config = rule_config or recorded_config
    if config is not None:
        if type(config.get("base_score")) is not int or config["base_score"] <= 0 or not isinstance(config.get("you_cai_bi_kao"), bool):
            raise ValueError("规则配置需要正整数 base_score 和布尔 you_cai_bi_kao")
        config = {"ruleset_version": ruleset_version, "base_score": config["base_score"], "you_cai_bi_kao": config["you_cai_bi_kao"]}
    parsed = parse_room_document(document)
    rows, checks, conflicts, comparisons = [], [], [], []
    rules = HangmaRules(RuleConfig(**config)) if config else None
    for number in sorted({block.round_no for block in parsed.blocks}):
        row = round_data(parsed, number, file_sha256=digest, json_pointer="")
        terminal = [(event, pointer) for event, pointer in zip(row["events"], row["event_pointers"])
                    if event["type"] == "round_ended"]
        ref = ({"file": "events.json", "sha256": digest, "json_pointer": terminal[0][1],
                "seq": terminal[0][0]["seq"]} if terminal else None)
        comparison = {"round_no": number, **row["result_consistency"]}
        comparisons.append(comparison)
        if comparison["status"] == "conflict":
            conflicts.append({"round_no": number, "reason": "summary_comparison_difference",
                              "checks": comparison["checks"]})
        row.update(replay_schema_version=1, hand_id=f"diagnostic:{digest}:{number}", game_key={"game_id": document["game_id"]},
            rule_config=config, result_source_ref=ref,
            derivation="blocks.round_ended" if terminal else "blocks", information_scope="postgame_full_information")
        check = check_hand(row, rules) if rules else {"status": "not_checked", "issues": [{"code": "missing_rule_config"}]}
        row["teacher_label_candidate"] = (check["status"] == "passed" and row["result_confirmed"]
            and row["coverage"] == "full_history" and row["scores_before"] is not None and row["scores_after"] is not None)
        row["student_observation"] = False
        rows.append(row)
        checks.append({"round_no": number, "source": ref, **check})
    finals = {e["seq"]: e["data"]["final_scores"] for row in rows for e in row["events"] if e["type"] == "game_ended"}
    final = next(iter(finals.values())) if len(finals) == 1 else None
    # summed_scores 保留旧报告键，但仅表示已观察单局的变化之和，不能冒充累计积分。
    known = bool(rows) and all(row["score_delta"] is not None for row in rows)
    summed = [sum(row["score_delta"][seat] for row in rows) for seat in range(4)] if known else None
    start = rows[0]["scores_before"] if rows else None
    final_match = None
    if known and final is not None:
        final_match = ([start[seat] + summed[seat] for seat in range(4)] == final
                       and all(left["scores_after"] == right["scores_before"] for left, right in zip(rows, rows[1:])))
    if final_match is False:
        for row in rows:
            row["teacher_label_candidate"] = False
    report = {"source_sha256": digest, "game_id": document["game_id"], "ruleset_version": ruleset_version, "rule_config": config,
        "origin_conflicts": conflicts, "summary_comparisons": comparisons,
        "rounds": checks, "statuses": dict(Counter(c["status"] for c in checks)),
        "teacher_label_candidates": sum(r["teacher_label_candidate"] for r in rows),
        "final_scores_match": final_match, "summed_scores": summed, "observed_start_scores": start, "final_scores": final,
        "limitations": ["赛后全知数据不可作为学生观察", "诊断派生不覆盖官方原文或正式导入", "候选标签仍需任务级筛选，不自动进入训练"]}
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(path, out / "events.json")
    (out / "hands.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    write_json(out / "rule-check.json", report)
    return report


def finalize_session(root: Path, *, source_namespace: str, ruleset_version: str, rule_config: dict | None = None) -> dict:
    """一个已结束 session → 不可变包、可迁移数据集、规则诊断和报告。

    仅有官方牌谱的历史会话也能处理；缺本地决策保持为空，禁止伪造观察。
    发现任意未关闭 run 则在写出前拒绝。每次重分析创建新 job，永不覆盖旧包。
    """
    root = root.resolve()
    runs = discover_runs(root)
    if any(not (r / "summary.json").is_file() for r in runs):
        raise ValueError("仍有未关闭的 run；请等待收尾后再生成赛后制品")
    download_errors = sorted((root / "official").rglob("download-error.json"))
    incomplete_downloads = [p.parent for p in (root / "official").rglob("download-started.json") if not (p.parent / "source.json").is_file()]
    rejected = {p.parent for p in download_errors} | set(incomplete_downloads)
    official_files = [p for p in sorted((root / "official").rglob("events.json")) if p.parent not in rejected]
    if not runs and not official_files:
        raise ValueError("没有原始 run 或 official/**/events.json")
    if len({r.name for r in runs}) != len(runs):
        raise ValueError("发现重复 run_id，请选择实际运行目录而非副本混合根")
    if any(p.is_symlink() for r in runs for p in r.rglob("*")):
        raise ValueError("运行内含符号链接，拒绝封存")
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    job = root / "postgame" / identifier
    job.mkdir(parents=True, exist_ok=False)
    audit = {r.name: validate_run(r) for r in runs}
    partial = [r.name for r in runs if (r / "imported-layout.json").is_file()]
    write_json(job / "audit-validation.json", audit)
    write_json(job / "observation-status.json", session_status(root))
    official_evidence = [{"file": p.relative_to(root).as_posix(), "sha256": sha256_file(p), "document": json.loads(p.read_bytes())} for p in official_files]
    write_json(job / "observation-checks.json", {r.name: audit_observations(r, ruleset_version=ruleset_version, official=official_evidence) for r in runs})
    with tempfile.TemporaryDirectory(prefix="hangma-postgame-") as temp:
        stage = Path(temp)
        for run in runs:
            # 已关闭输入的临时硬链接只供 copy_bundle 读取；跨卷退回复制。
            def link_or_copy(src, dst):
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
                return dst
            shutil.copytree(run, stage / "runs" / run.name, copy_function=link_or_copy)
        if runs:
            manifest = create_bundle(stage, run_ids=[r.name for r in runs], out_dir=job, bundle_id=identifier)
            bundle = job / "bundles" / manifest.bundle_id
        else:
            # 无本地审计时只建立官方证据包，run_ids 空，绝不生成假 run。
            bundle = job / "bundles" / identifier
            bundle.mkdir(parents=True)
            write_json(bundle / "bundle.json", {"bundle_schema_version": 1, "bundle_id": identifier,
                "created_at_unix_ms": int(datetime.now(timezone.utc).timestamp() * 1000), "run_ids": [],
                "parent_bundle_ids": [], "closed_cleanly_by_run": True, "source_notes": "仅官方原文，无本机决策审计", "files": []})
    unique = {}
    for events in official_files:
        digest = sha256_file(events)
        if digest in unique:
            continue
        unique[digest] = events
        target = bundle / "official" / digest
        target.mkdir(parents=True)
        shutil.copy2(events, target / "events.json")
        document = json.loads(events.read_bytes())
        source = json.loads((events.parent / "source.json").read_text()) if (events.parent / "source.json").exists() else {}
        write_json(target / "source.json", {**source, "download_id": digest, "room_id": source.get("room_id") or document.get("room_id"),
            "game_id": document.get("game_id"), "batch": document.get("batch"), "original_sha256": digest,
            "session_source": events.relative_to(root).as_posix()})
        if (events.parent / "games.json").is_file():
            shutil.copy2(events.parent / "games.json", target / "games.json")
        for reference in ("guide-version.json", "guide.json"):
            if (events.parent / reference).is_file():
                shutil.copy2(events.parent / reference, target / reference)
    # 元数据只复制明确非凭证的公开制品；整个配置目录从不进入证据包。
    if (root / "references").is_dir():
        shutil.copytree(root / "references", bundle / "references")
    for folder in sorted(rejected):
        # 失败响应作为隔离证据封存，不放进正式导入器会扫描的 official/。
        target = bundle / "rejected-downloads" / folder.relative_to(root / "official")
        for name in ("download-started.json", "download-error.json", "events.json", "games.json", "guide-version.json", "guide.json"):
            source = folder / name
            if source.is_file():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target / name)
    # 封存本次离线工具源码，工作区未提交时也可核对具体实现；不复制运行配置。
    package = Path(__file__).resolve().parents[1]
    source_hashes = {}
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package).as_posix()
        target = bundle / "references" / "analysis-source" / "src" / "hangma_bot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        source_hashes[relative] = sha256_file(target)
    rules_hash = compute_rules_hash(bundle / "references" / "analysis-source")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=package, stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=package, stderr=subprocess.DEVNULL, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    provenance = {"ruleset_version": ruleset_version, "rule_config_override": rule_config,
        "producer_commit": commit, "dirty": dirty, "rules_hash": rules_hash, "source_hashes": source_hashes,
        "note": "这是本次离线分析实现；历史线上版本以原始 run manifest 为准"}
    write_json(bundle / "references" / "analysis-provenance.json", provenance)
    packed = pack_bundle(bundle, job / "archives" / (identifier + ".tar.gz"))
    converted = build_dataset(bundle, job, source_namespace=source_namespace, producer_commit=commit, dirty=dirty,
        rules_hash=rules_hash, config={"analysis_ruleset_version": ruleset_version, "rule_config_override": rule_config})
    checks = []
    for digest in unique:
        try:
            check = diagnose_official(bundle / "official" / digest / "events.json", job / "diagnostic" / digest,
                ruleset_version=ruleset_version, rule_config=rule_config)
        except (ValueError, KeyError, TypeError) as exc:
            check = {"source_sha256": digest, "status": "failed", "reason": str(exc)}
        checks.append(check)
    # 不重复导出可被误当训练集的多视角混合原文；学生输入沿用正式 decisions 编码。
    report = {"schema_version": 1, "job_id": identifier, "source_namespace": source_namespace,
        "run_count": len(runs), "official_documents": len(unique), "partial_audit_imports": partial,
        "rejected_downloads": sorted(p.relative_to(root).as_posix() for p in rejected),
        "analysis_provenance": (bundle / "references/analysis-provenance.json").relative_to(job).as_posix(),
        "audit_complete": bool(runs) and not partial and all(r["audit_complete"] for r in audit.values()),
        "bundle": bundle.relative_to(job).as_posix(), "archive": Path(packed["archive"]).relative_to(job).as_posix(),
        "archive_sha256": packed["sha256"], "dataset": Path(converted["dataset_dir"]).relative_to(job).as_posix(),
        "dataset_summary": {k: v for k, v in converted.items() if k != "dataset_dir"}, "official_rule_checks": checks,
        "bundle_verified": verify_bundle(bundle, write_report=False)["ok"]}
    write_json(job / "report.json", report)
    (job / "README.md").write_text("# 赛后制品\n\n"
        f"本次收集 {len(runs)} 个本机运行、{len(unique)} 份官方原文。决策 {converted['decisions_total']} 条，正式单局 {converted['hands_total']} 条。\n\n"
        f"- [机器可读报告](report.json)\n- [审计校验](audit-validation.json)\n- [观察状态](observation-status.json)\n- [事件与状态复核](observation-checks.json)\n"
        f"- [原始证据归档]({report['archive']})\n- [数据集校验]({report['dataset']}/validation.json)\n\n"
        "diagnostic/ 中的 hands.jsonl 是赛后全信息，不可作为学生观察。摘要冲突、缺规则配置、缺牌墙分别记录；诊断成功不代表正式导入成功。\n", encoding="utf-8")
    write_json(root / "latest-postgame.json", {"job": job.relative_to(root).as_posix()})
    return {"job": str(job), **report}
