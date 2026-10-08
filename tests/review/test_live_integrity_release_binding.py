"""自由赛完整性审计：历史与当前受控发布包均通过，伪造身份须失败。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/review'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from datetime import datetime
import json
from pathlib import Path
import sys

import pytest


REVIEW = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] / "review/freematch-deep-dive-20260925")
if str(REVIEW) not in sys.path:
    sys.path.insert(0, str(REVIEW))

import live_integrity_audit as audit  # noqa: E402


OLD_ID = "e82f904c2c1fb70beea3f195110c8b2db0648971ed3eaa9bfcbed1b6543de486"
CURRENT_ID = "61cab4b539efb401f46aab2fd9f79cc85ce5653d64d1b9a72ffb3048eeb884c7"


def _read(tmp_path, release_id: str, **changes):
    """构造一次真实 manifest JSON 往返，覆盖 tuple 到 list 的序列化边界。"""
    release = dict(audit.CONTROLLED_RELEASE_BINDINGS[release_id])
    release.update(changes)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"payload": {
        "policy_release": release,
        "policy_version": "r18_integrated_positive_v2",
        "ruleset_version": "hangma-mvp-v10-public-counts",
    }}), encoding="utf-8")
    return audit.read_manifest(path)


@pytest.mark.parametrize("release_id", [OLD_ID, CURRENT_ID])
def test_historical_and_current_frozen_r18_bindings_are_accepted(tmp_path, release_id):
    """旧审计器把合法的当前 61cab 包误报为漂移，历史 e82f 也需保持有效。"""
    assert release_id in audit.CONTROLLED_RELEASE_BINDINGS
    assert audit.verify_manifest_release(_read(tmp_path, release_id)) is None


def test_unknown_release_id_and_changed_payload_are_rejected(tmp_path):
    """不能只看策略名或自报包 ID；同 ID 下改候选/规则摘要仍是漂移。"""
    unknown = _read(tmp_path, CURRENT_ID, release_package_id="0" * 64)
    assert "ID 不属于受控" in audit.verify_manifest_release(unknown)

    candidate_drift = _read(tmp_path, CURRENT_ID, candidate_source_sha256="0" * 64)
    assert "candidate_source_sha256" in audit.verify_manifest_release(candidate_drift)

    rules_drift = _read(tmp_path, CURRENT_ID, rules_source_hash="0" * 64)
    assert "rules_source_hash" in audit.verify_manifest_release(rules_drift)


def test_outer_strategy_and_ruleset_must_match_controlled_release(tmp_path):
    manifest = _read(tmp_path, CURRENT_ID)
    manifest["policy_version"] = "another_strategy"
    assert "策略版本" in audit.verify_manifest_release(manifest)
    manifest["policy_version"] = "r18_integrated_positive_v2"
    manifest["ruleset_version"] = "another_ruleset"
    assert "规则语义版本" in audit.verify_manifest_release(manifest)


def test_report_verdict_uses_binding_verifier(tmp_path):
    """核验结论层也使用新判据，避免验证函数正确却仍按旧 ID 报错。"""
    room = {
        "room_id": "test-room", "started_at": "2026-09-29 16:00:00",
        "session_log": "session-20260929-160000.log",
        "room_subtotal": 0, "games": [],
    }
    official = {
        "games": [], "my_total_from_rounds": 0, "my_total_from_final_scores": 0,
        "final_scores_agree": 0, "final_scores_games": 0,
    }
    current = _read(tmp_path, CURRENT_ID)
    report = audit.build_report([room], {"test-room": {
        "manifest": current, "official": official,
    }}, datetime(2026, 9, 29, 16))
    assert report["verdict"]["defects"] == []

    current["policy_release"]["candidate_source_sha256"] = "0" * 64
    report = audit.build_report([room], {"test-room": {
        "manifest": current, "official": official,
    }}, datetime(2026, 9, 29, 16))
    assert any("发布包与受控绑定不一致" in item
               for item in report["verdict"]["defects"])
