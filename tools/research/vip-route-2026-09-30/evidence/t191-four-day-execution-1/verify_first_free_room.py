"""只读首新自由赛原件，补真实配置下的规则检查，不触网或重新评分。

旧后台未知规则的报告保持不动；新诊断明确绑定本房真实响应和本次规则源码。
只允许指定自然闭合首房，一次性写出，不提供续赛、终止或重试接口。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.postgame import diagnose_official
from hangma_bot.simulation.artifacts import compute_rules_hash


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t191-live-batch-001-free")
ROOM = "a_173f9ef528bf"
RUN = "run-a0fd93da89884de28acec6a9031aae75"


def load(path):
    """读取指定已闭合原件，不修正历史值。"""
    return json.loads(path.read_text())


def pin(path):
    """相对仓库路径、原字节大小和摘要，用于可迁移核验。"""
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """独占写新证据，UTC墙上时钟只用于标记核验时点。"""
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    """核自然终态、配置、官方结算与规则；所有未知项保留。"""
    batch = _project_file(_PROJECT_ROOT, HERE / "batch-001")
    assert load(batch / "FREE-CHILD-TERMINAL.json")["actual_exit_code"] == 0
    assert load(batch / "POSTPROCESS-CLOSED.json")["failures"] == []
    analysis = load(batch / "SUMMARY.json")
    assert analysis["room_ids"] == [ROOM]
    assert analysis["postgame_bundle_verified"] and analysis["postgame_audit_complete"]
    run = _project_file(_PROJECT_ROOT, SESSION / "audit/runs" / RUN)
    manifest = load(run / "manifest.json")["payload"]
    assert manifest["policy_release"]["release_package_id"] == (
        "3bc912f5e52a71c6978dff9dc06fdf26c9cac9f7bdd4f06b3c95e749382f267a")
    config_rows = []
    for path in sorted(run.glob("participants/*/raw/global*.gz")):
        with gzip.open(path, "rt") as stream:
            for line_number, line in enumerate(stream, 1):
                row = json.loads(line)
                payload = row["payload"]
                if payload.get("endpoint") not in (
                        "POST /api/match", "GET /api/tournaments/" + ROOM):
                    continue
                if payload.get("http_status") != 200:
                    continue
                raw = payload.get("raw")
                document = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(document, dict) or "config" not in document:
                    continue
                cfg = document["config"]
                if config_rows:
                    assert cfg == config_rows[0]["config"]
                    continue
                config_rows.append({"source": pin(path), "line": line_number,
                    "endpoint": payload["endpoint"], "config": cfg})
    assert config_rows
    cfg = config_rows[0]["config"]
    assert (cfg["M"], cfg["Rounds"], cfg["BaseScore"], cfg["YouCaiBiKao"]) == (10, 8, 1, False)
    assert manifest["base_score"] == cfg["BaseScore"]
    assert manifest["you_cai_bi_kao"] is cfg["YouCaiBiKao"]
    out = _project_file(_PROJECT_ROOT, HERE / "first-free-room-rule-check")
    out.mkdir(exist_ok=False)
    rule_config = {"base_score": cfg["BaseScore"], "you_cai_bi_kao": cfg["YouCaiBiKao"]}
    save(out / "ACTUAL-CONFIG.json", {"schema": "t191-first-free-rule-config/1",
        "source": config_rows, "run_manifest": pin(run / "manifest.json"),
        "rule_config": rule_config, "ruleset_version": manifest["ruleset_version"],
        "current_rules_source_hash": compute_rules_hash(ROOT)})
    statuses, issue_codes, own_timeout = Counter(), Counter(), Counter()
    own_seats = {t["game_id"]: next(iter(t["seat_arm_map"])) for t in analysis["tables"]}
    rows = []
    for path in sorted(SESSION.glob("official/dl-*/events.json")):
        doc = load(path)
        gid = doc["game_id"]
        if gid not in own_seats:
            continue
        expected = analysis["official_source_sha256"][gid]
        assert pin(path)["sha256"] == expected
        # 同桌重复下载必须同摘要；不重复计单局和超时。
        if any(r["game_id"] == gid for r in rows):
            continue
        report = diagnose_official(path, out / gid,
            ruleset_version=manifest["ruleset_version"], rule_config=rule_config)
        statuses.update(report["statuses"])
        for item in report["rounds"]:
            issue_codes.update(i["code"] for i in item.get("issues", []))
        assert report["final_scores_match"] is True
        seat = int(own_seats[gid])
        for block in doc["blocks"]:
            for event in block["events"]:
                if event["type"] == "timeout" and event.get("seat") == seat:
                    own_timeout[event.get("data", {}).get("kind", "unknown")] += 1
        rows.append({"game_id": gid, "own_seat": seat,
            "official_original": pin(path), "rule_check": pin(out / gid / "rule-check.json"),
            "statuses": report["statuses"], "final_scores_match": True})
    assert len(rows) == 10 and sum(statuses.values()) == 80
    audit = analysis["audit"][0]
    compute = analysis["terminals"][0]["decision_compute"]
    assert compute["closed"] is True
    assert all(compute[k] == 0 for k in ("owned", "pending", "active", "ready",
        "live_processes", "current", "bound_games", "releasing_games",
        "transport_inflight", "late_reap_inflight", "late_reap_threads_alive",
        "transport_threads_alive"))
    assert not audit["full_plan_legal_key_mismatches"]
    failures = audit["failed_plans"]
    value = {"schema": "t191-first-new-free-closed-readback/1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN, "room_id": ROOM, "unique_tables": 10, "unique_hands": 80,
        "natural_exit_code": 0, "resources_zero": True, "decision_compute": compute,
        "postgame_audit_complete": True, "postgame_bundle_verified": True,
        "plan_count": audit["plans"], "complete_plans": audit["complete_plans"],
        "complete_legal_outputs": audit["complete_legal_outputs"],
        "complete_plan_legal_key_mismatches": audit["full_plan_legal_key_mismatches"],
        "missing_full_score": len(failures),
        "missing_full_score_with_choice": sum(len(f["input"]["legal"]) > 1 for f in failures),
        "zero_attempt_windows_unclassified": len(analysis["zero_attempt_windows_unclassified"]),
        "own_official_timeout_by_kind": dict(own_timeout),
        "http_categories": audit["http_categories"],
        "rule_statuses_explicit_actual_config": dict(statuses),
        "rule_issue_codes_explicit_actual_config": dict(issue_codes),
        "actual_config_original": pin(out / "ACTUAL-CONFIG.json"),
        "rules_rows": rows, "accounts": analysis["mutually_exclusive_accounts"],
        "source_pins": [pin(batch / n) for n in (
            "FREE-CHILD-TERMINAL.json", "RUN-CLOSED.json", "POSTPROCESS-CLOSED.json", "SUMMARY.json")],
        "full_score_gate_granted": False, "formal_release": False, "strength_admission": False,
        "limitations": ["首房非随机对照，不授算法增强", "后台原unknown规则报告保留，新规则检查单独补证",
            "原审计长路径键脱敏合并限制仍保留，以完整冻结来源侧件核身份",
            "响应零尝试未逐窗判定丢失动作机会，不把响应timeout都称弃牌超时",
            "不授实际官方测试赛事门"]}
    save(_project_file(_PROJECT_ROOT, HERE / "FIRST-FREE-ROOM-CLOSED.json"), value)
    print(json.dumps({k: value[k] for k in ("unique_tables", "unique_hands",
        "own_official_timeout_by_kind", "rule_statuses_explicit_actual_config",
        "rule_issue_codes_explicit_actual_config", "complete_plans", "missing_full_score",
        "missing_full_score_with_choice")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
