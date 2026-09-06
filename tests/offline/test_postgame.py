"""常规制品用例：四身份发现、原文不可变、缺史隔离和迁移后可读取。"""
import json
import shutil
from pathlib import Path

import pytest

from hangma_bot.adapters.recording.bundle import extract_bundle, verify_bundle
from hangma_bot.offline.artifact_store import catalog_sessions, discover_runs, import_official_history, migrate_runs
from hangma_bot.offline.postgame import diagnose_official, finalize_session, session_status

FIXTURE = Path(__file__).parents[1] / "fixtures/hangma/archived-rooms/t_6c121bfda7e8_b0.json"


def run_at(root, name="run-1", closed=True):
    path = root / "runs" / name
    (path / "participants/p1").mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps({"schema_version": 1, "kind": "run_manifest", "context": {"run_id": name}, "payload": {}}))
    if closed:
        (path / "summary.json").write_text("{}")
    return path


def official_at(root):
    folder = root / "official/dl-one"
    folder.mkdir(parents=True)
    shutil.copy2(FIXTURE, folder / "events.json")
    return folder / "events.json"


def test_discovers_four_identities_but_not_sealed_or_staging_copies(tmp_path):
    expected = [run_at(tmp_path / "audit" / f"slot-{n}", f"run-{n}") for n in range(4)]
    run_at(tmp_path / "bundles/old", "run-copy")
    run_at(tmp_path / "combined", "run-copy")
    run_at(tmp_path / "postgame/job/bundles/new", "run-copy")
    assert discover_runs(tmp_path) == sorted(expected)
    assert session_status(tmp_path)["run_count"] == 4
    assert session_status(tmp_path)["all_closed"]


def test_deferred_pass_is_separate_from_http_submission(tmp_path):
    run = run_at(tmp_path)
    row = {"schema_version": 1, "kind": "submission_outcome", "context": {}, "payload": {
        "audit_producer": "application", "outcome": "SubmitNotSent", "reason": "pass_deferred_until_chi"}}
    (run / "participants/p1/decisions.jsonl").write_text(json.dumps(row) + "\n")
    status = session_status(tmp_path)["runs"][0]
    assert status["deferred_pass"] == 1
    assert status["transport"] == {}


def test_active_session_rejected_before_creating_output(tmp_path):
    run_at(tmp_path, closed=False)
    with pytest.raises(ValueError, match="未关闭"):
        finalize_session(tmp_path, source_namespace="test", ruleset_version="test")
    assert not (tmp_path / "postgame").exists()


def test_official_only_produces_bundle_dataset_diagnostics_and_portable_paths(tmp_path):
    session = tmp_path / "session"
    source = official_at(session)
    original = source.read_bytes()
    report = finalize_session(session, source_namespace="test", ruleset_version="test")
    job = Path(report["job"])
    assert report["run_count"] == 0
    assert report["dataset_summary"]["decisions_total"] == 0
    assert report["dataset_summary"]["hands_total"] == 1
    assert report["official_rule_checks"][0]["rule_config"] is None
    assert report["official_rule_checks"][0]["teacher_label_candidates"] == 0
    assert not Path(report["archive"]).is_absolute()
    moved = tmp_path / "another-machine"
    shutil.copytree(job, moved)
    assert verify_bundle(moved / report["bundle"], write_report=False)["ok"]
    extracted = extract_bundle(moved / report["archive"], tmp_path / "unpacked")
    assert extracted["verification"]["ok"]
    assert source.read_bytes() == original
    assert (job / report["dataset"] / "decisions.jsonl").is_file()
    catalog = catalog_sessions(tmp_path)
    assert len(catalog["sessions"]) == 1
    assert not Path(catalog["sessions"][0]["report"]).is_absolute()


def test_repeat_postgame_creates_new_job_and_preserves_old_archive(tmp_path):
    official_at(tmp_path)
    first = finalize_session(tmp_path, source_namespace="test", ruleset_version="test")
    archive = Path(first["job"]) / first["archive"]
    before = archive.read_bytes()
    second = finalize_session(tmp_path, source_namespace="test", ruleset_version="test")
    assert first["job"] != second["job"]
    assert archive.read_bytes() == before


def test_summary_conflict_stays_diagnostic_and_not_a_teacher_label(tmp_path):
    source = official_at(tmp_path)
    data = json.loads(source.read_text())
    data["rounds"][0]["winner"] = 99
    source.write_text(json.dumps(data))
    report = diagnose_official(source, tmp_path / "diagnosis", ruleset_version="test",
        rule_config={"base_score": 1, "you_cai_bi_kao": False})
    assert report["origin_conflicts"]
    assert report["teacher_label_candidates"] == 0
    assert json.loads(source.read_text())["rounds"][0]["winner"] == 99


def test_history_deduplicates_bytes_and_keeps_all_provenance_and_real_config(tmp_path):
    one, two = official_at(tmp_path / "one"), official_at(tmp_path / "two")
    (tmp_path / "one/meta.json").write_text(json.dumps({"room_config": {"BaseScore": 1, "YouCaiBiKao": False}}))
    out = tmp_path / "artifacts/history"
    result = import_official_history([tmp_path / "one", tmp_path / "two"], out, project_root=tmp_path)
    assert result["unique_documents"] == 1 and result["source_copies"] == 2
    stored = next((out / "official").glob("*/source.json"))
    assert json.loads(stored.read_text())["rule_config"]["you_cai_bi_kao"] is False
    assert one.read_bytes() == two.read_bytes()
    again = import_official_history([tmp_path / "one", tmp_path / "two"], out, project_root=tmp_path)
    assert again["unique_documents"] == 1


def test_migration_is_idempotent_and_keeps_old_links_working(tmp_path):
    legacy = tmp_path / "runs"
    run = run_at(legacy / "session")
    contents = (run / "manifest.json").read_bytes()
    assert migrate_runs(legacy, tmp_path / "artifacts")["status"] == "migrated"
    assert legacy.is_symlink() and (run / "manifest.json").read_bytes() == contents
    assert migrate_runs(legacy, tmp_path / "artifacts")["status"] == "already_migrated"


def test_migration_refuses_an_open_run(tmp_path):
    run_at(tmp_path / "runs", closed=False)
    with pytest.raises(ValueError, match="未关闭"):
        migrate_runs(tmp_path / "runs", tmp_path / "artifacts")
    assert not (tmp_path / "artifacts/legacy/runs").exists()


def test_run_symlink_cannot_be_copied_through_the_staging_directory(tmp_path):
    run = run_at(tmp_path)
    (run / "participants/p1/private").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="链接"):
        finalize_session(tmp_path, source_namespace="test", ruleset_version="test")


def test_history_config_conflict_is_not_silently_overwritten(tmp_path):
    official_at(tmp_path / "one")
    official_at(tmp_path / "two")
    for name, enabled in (("one", False), ("two", True)):
        (tmp_path / name / "meta.json").write_text(json.dumps({"room_config": {"BaseScore": 1, "YouCaiBiKao": enabled}}))
    with pytest.raises(ValueError, match="配置冲突"):
        import_official_history([tmp_path / "one", tmp_path / "two"], tmp_path / "out", project_root=tmp_path)


def test_partial_audit_layout_restored_without_inventing_raw(tmp_path):
    source = tmp_path / "old/bot-audit/slot-A/run-old"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text(json.dumps({"context": {"run_id": "run-old", "participant_id": "p1"}}))
    (source / "summary.json").write_text("{}")
    raw = b'{"schema_version":1,"kind":"decision_ended","context":{},"payload":{}}\n'
    (source / "decisions.jsonl").write_bytes(raw)
    out = tmp_path / "new"
    result = import_official_history([tmp_path / "old"], out, project_root=tmp_path)
    imported = discover_runs(out)[0]
    assert result["partial_audit_runs"][0]["missing_raw"] is True
    assert not (imported / "participants/p1/raw").exists()
    assert (imported / "participants/p1/decisions.jsonl").read_bytes() == raw
    assert (source / "decisions.jsonl").read_bytes() == raw


def test_failed_download_is_excluded_even_when_events_were_received(tmp_path):
    good = official_at(tmp_path)
    bad = tmp_path / "official/failed"
    bad.mkdir()
    shutil.copy2(good, bad / "events.json")
    (bad / "download-error.json").write_text('{"reason":"wrong_room"}')
    report = finalize_session(tmp_path, source_namespace="test", ruleset_version="test")
    assert report["official_documents"] == 1
    assert report["rejected_downloads"] == ["official/failed"]


def test_per_source_metadata_survives_formal_conversion(tmp_path):
    events = official_at(tmp_path)
    (events.parent / "source.json").write_text(json.dumps({"guide_version": 18, "captured_at": "2026-09-06T12:34:56+00:00",
        "rule_config": {"ruleset_version": "test", "base_score": 1, "you_cai_bi_kao": False}}))
    report = finalize_session(tmp_path, source_namespace="test", ruleset_version="test")
    job = Path(report["job"])
    hand = json.loads((job / report["dataset"] / "hands.jsonl").read_text().splitlines()[0])
    assert hand["guide_version"] == 18
    assert hand["guide_captured_at"] == "2026-09-06"
    assert hand["rule_config"]["you_cai_bi_kao"] is False
    provenance = json.loads((job / report["bundle"] / "references/analysis-provenance.json").read_text())
    assert provenance["rules_hash"] and provenance["source_hashes"]["offline/postgame.py"]
