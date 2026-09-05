"""证据包打包/核验/展开测试（方案 §4）。

验收：打包转到新路径仍可读取并核验所有哈希；拒绝绝对路径/穿越/链接/
同名覆盖；篡改与缺失如实报告；封存后不可追加（打包时重算清单）。
"""

from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

import pytest

from hangma_bot.adapters.recording.bundle import (
    create_bundle,
    extract_bundle,
    pack_bundle,
    verify_bundle,
)


def _make_closed_run(root: Path, run_id: str = "run-1") -> Path:
    run = root / "runs" / run_id / "participants" / "p1"
    run.mkdir(parents=True)
    (run / "decisions.jsonl").write_text(
        json.dumps({"schema_version": 1, "kind": "run_manifest",
                    "context": {"run_id": run_id, "tournament_id": "t", "participant_id": "p1"},
                    "wall_time_unix_ms": 1, "monotonic_ns": 1, "payload": {}})
        + chr(10),
        encoding="utf-8",
    )
    (root / "runs" / run_id / "summary.json").write_text("{}", encoding="utf-8")
    return run


def test_create_verify_pack_extract_round_trip(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    manifest = create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")
    assert manifest.closed_cleanly_by_run is True
    bundle_dir = tmp_path / "out" / "bundles" / manifest.bundle_id
    report = verify_bundle(bundle_dir)
    assert report["ok"] is True
    assert (bundle_dir / "validation.json").is_file()

    packed = pack_bundle(bundle_dir, tmp_path / "b.tar.gz")
    assert (tmp_path / "b.tar.gz.sha256").is_file()

    extracted = extract_bundle(tmp_path / "b.tar.gz", tmp_path / "dest")
    assert extracted["verification"]["ok"] is True
    # 转到新路径后所有哈希仍可核验。
    assert extracted["extracted_to"].startswith(str(tmp_path / "dest"))


def test_tampered_file_is_reported(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    manifest = create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")
    bundle_dir = tmp_path / "out" / "bundles" / manifest.bundle_id
    target = bundle_dir / "runs" / "run-1" / "summary.json"
    target.write_text("tampered", encoding="utf-8")
    report = verify_bundle(bundle_dir, write_report=False)
    assert report["ok"] is False
    assert report["mismatched"]


def test_missing_file_is_reported(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    manifest = create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")
    bundle_dir = tmp_path / "out" / "bundles" / manifest.bundle_id
    (bundle_dir / "runs" / "run-1" / "participants" / "p1" / "decisions.jsonl").unlink()
    report = verify_bundle(bundle_dir, write_report=False)
    assert report["ok"] is False
    assert report["missing"]


def test_unclosed_run_marks_not_cleanly_closed(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    (root / "runs" / "run-1" / "summary.json").unlink()
    manifest = create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")
    assert manifest.closed_cleanly_by_run is False
    assert "未关闭" in manifest.source_notes


def test_symlink_refused(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    link = root / "runs" / "run-1" / "evil.json"
    os.symlink("/etc/hosts", link)
    with pytest.raises(ValueError):
        create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")


def test_existing_bundle_dir_refused(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    manifest = create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")
    with pytest.raises(FileExistsError):
        create_bundle(
            root,
            run_ids=["run-1"],
            out_dir=tmp_path / "out",
            bundle_id=manifest.bundle_id,
        )


def test_extract_rejects_archive_with_traversal(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("bundle-1/../../escape.txt")
        payload = b"evil"
        import io

        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError):
        extract_bundle(archive, tmp_path / "dest")


def test_extract_requires_archive_sha_match(tmp_path):
    root = tmp_path / "audit"
    root.mkdir()
    _make_closed_run(root)
    manifest = create_bundle(root, run_ids=["run-1"], out_dir=tmp_path / "out")
    bundle_dir = tmp_path / "out" / "bundles" / manifest.bundle_id
    pack_bundle(bundle_dir, tmp_path / "b.tar.gz")
    sha = tmp_path / "b.tar.gz.sha256"
    sha.write_text("00" * 32 + "  b.tar.gz" + chr(10), encoding="utf-8")
    with pytest.raises(ValueError):
        extract_bundle(tmp_path / "b.tar.gz", tmp_path / "dest")
