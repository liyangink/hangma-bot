"""编译临时目录与 checkout 跨设备时，仍能原子发布可编辑安装制品。"""
from __future__ import annotations

import errno
import importlib.util
import os
from pathlib import Path

import pytest


def test_native_artifact_can_be_published_across_filesystems(tmp_path, monkeypatch):
    """模拟跨设备 rename 的真实约束，避免部署到 /tmp tmpfs 时安装失败。"""
    pytest.importorskip("hatchling")
    path = Path(__file__).resolve().parents[2] / "hatch_build.py"
    spec = importlib.util.spec_from_file_location("hangma_build_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_dir = tmp_path / "compiler-device"
    target_dir = tmp_path / "checkout-device"
    source_dir.mkdir()
    target_dir.mkdir()
    source = source_dir / "compiled.so"
    destination = target_dir / "installed.so"
    source.write_bytes(b"new-native-artifact")
    destination.write_bytes(b"old-native-artifact")
    actual_replace = os.replace

    def same_filesystem_replace(before, after):
        if Path(before).parent != Path(after).parent:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return actual_replace(before, after)

    monkeypatch.setattr(os, "replace", same_filesystem_replace)
    module.publish_extension(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert list(target_dir.iterdir()) == [destination]
