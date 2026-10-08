"""先核三处权威快照的胡牌资格；不冒称恢复了原完整评分输入或实际评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import ctypes
from contextlib import nullcontext
import fcntl
import gzip
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from hangma_bot.adapters.official.dto import parse_snapshot
from hangma_bot.adapters.official.projector import observation
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import WinDescription
from hangma_bot.hangma.observation_rules import enrich_observation
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_to_json

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
TARGETS = (
    ("t179-batch-001-free", "run-4107962142a04b55aeef919f9384a8c5",
     "a_a8c4f4e461ce_r1_b7_t0", ((2, 242), (5, 982))),
    ("t179-batch-004-free", "run-27a24743b8cd43b6b3cc9715dace89fd",
     "a_94793050830e_r1_b0_t0", ((7, 1177),)),
)
MAX_READ = 16 * 1024 * 1024


def digest(raw):
    """明确字节摘要，不替代原记录或数学一致性检验。"""
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    """新产物独占创建；失败不覆盖历史提取失败或父代证据。"""
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def main(bounded_light=False):
    """重型路径持公共锁；显式轻量档只做三快照基本规则，不构图/评分/模拟。"""
    os.nice(15)
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.setiopolicy_np(0, 0, 3) == 0  # IOPOL_TYPE_DISK/SCOPE_PROCESS/THROTTLE。
    manifest = json.loads((_project_file(_PROJECT_ROOT, HERE / "SOURCE-MANIFEST.json")).read_text())
    files = dict(manifest)
    for relative in ("src/hangma_bot/adapters/official/dto.py",
                     "src/hangma_bot/adapters/official/projector.py"):
        files[relative] = {"sha256": digest((_project_file(_PROJECT_ROOT, ROOT / relative)).read_bytes())}
    assert all(digest((_project_file(_PROJECT_ROOT, ROOT / p)).read_bytes()) == v["sha256"] for p, v in files.items())
    target = _project_file(_PROJECT_ROOT, HERE / "SNAPSHOT-HU-QUALIFICATION.json")
    assert not target.exists()
    result = {"schema": "t182-snapshot-hu-qualification/1", "cases": [],
        "scope": "snapshot legal Hu/current settlement only; original whole score/input not recovered",
        "source_manifest_sha256": digest((_project_file(_PROJECT_ROOT, HERE / "SOURCE-MANIFEST.json")).read_bytes()),
        "actual_source_files": files,
        "actual_model_calls": 0, "actual_candidate_score_calls": 0, "actual_worlds_tables": 0,
        "bounded_light_mode": bounded_light, "heavy_postprocess_lock_used": not bounded_light,
        "rules_analyze_attempts": 0, "settlement_attempts": 0, "read_limit_bytes": MAX_READ}
    consumed = 0
    guard = (nullcontext() if bounded_light else
             (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+"))
    with guard as lock:
        if lock is not None:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for session, run, game_id, windows in TARGETS:
            audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / session / "audit/runs" / run)
            raw = (audit / "manifest.json").read_bytes()
            consumed += len(raw)
            config = json.loads(raw)["payload"]
            rule_config = RuleConfig(**{k: config[k] for k in (
                "ruleset_version", "base_score", "you_cai_bi_kao")})
            paths = sorted((audit / "participants/u_13495c3d79c8/raw").glob(game_id + ".*.jsonl.gz"))
            found = {}
            source_pins = []
            for path in paths:
                source_pins.append({"path": str(path.relative_to(ROOT)),
                                    "sha256": digest(path.read_bytes())})
                consumed += path.stat().st_size
                with gzip.open(path, "rb") as stream:
                    for line_no, line in enumerate(stream, 1):
                        consumed += len(line)
                        assert consumed <= MAX_READ
                        row = json.loads(line)
                        context = row.get("context") or {}
                        key = context.get("round_no"), context.get("trigger_seq")
                        if key not in windows or row["payload"].get("source") != "state_response":
                            continue
                        doc = json.loads(row["payload"]["raw"])
                        if doc.get("snapshot") is not None:
                            assert key not in found
                            found[key] = row, doc, str(path.relative_to(ROOT)), line_no
            assert set(found) == set(windows)
            for key in windows:
                row, doc, source, line_no = found[key]
                snapshot = parse_snapshot(doc["snapshot"], top_level_seq=doc["seq"])
                obs = enrich_observation(observation(snapshot, (), game_id))
                assert obs.round_no == key[0] and obs.snapshot_seq == key[1]
                # 零链由权威god确证飘次数0和非杠补；不补造未观测的历史。
                assert obs.rule_state.chain_count == 0 and obs.chain_piao == 0
                assert obs.gang_draw is False and obs.phase == "draw"
                rules = HangmaRules(rule_config)
                result["rules_analyze_attempts"] += 1
                analysis = rules.analyze(obs)
                legal = [c.action_key for c in analysis.legal_candidates]
                settlement = None
                if "hu" in legal:
                    result["settlement_attempts"] += 1
                    settlement = asdict(rules.score(WinDescription(obs, obs.seat)))
                result["cases"].append({"game_id": game_id, "round_no": key[0],
                    "trigger_seq": key[1], "rule_config": asdict(rule_config),
                    "policy_version": config["policy_version"],
                    "snapshot_raw_record": row, "source": source, "line_no": line_no,
                    "source_pins": source_pins, "projected_observation": observation_to_json(obs),
                    "public_history_not_reconstructed": True,
                    "legal_hu": "hu" in legal, "legal_actions": legal,
                    "rules_completeness": analysis.completeness.value,
                    "rules_issues": [asdict(issue) for issue in analysis.issues],
                    "current_hu_settlement": settlement,
                    "original_actual_scores": None,
                    "original_full_input_restored": False})
        assert all(digest((_project_file(_PROJECT_ROOT, ROOT / p)).read_bytes()) == v["sha256"] for p, v in files.items())
        result["read_bytes"] = consumed
        result["complete"] = len(result["cases"]) == 3
        save(target, result)
    print(json.dumps({"complete": result["complete"], "read_bytes": consumed,
        "cases": [{k: c[k] for k in ("game_id", "round_no", "trigger_seq", "legal_hu",
                  "rules_completeness", "current_hu_settlement")} for c in result["cases"]]}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--bounded-light", action="store_true",
                            help="最多16MiB与三次无路线增强的基本规则分析，不做重型任务")
        main(parser.parse_args().bounded_light)
    except BaseException as error:
        path = _project_file(_PROJECT_ROOT, HERE / "SNAPSHOT-HU-FAILURE.json")
        if not path.exists():
            save(path, {"status": "failed", "type": type(error).__name__, "message": str(error)})
        raise
