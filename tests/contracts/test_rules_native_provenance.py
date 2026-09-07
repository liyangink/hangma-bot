"""原生规则源和实际加载制品分别留证，避免 C 变化绕过规则指纹。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from hangma_bot.simulation.artifacts import compute_rules_hash, hand_math_runtime_metadata


def test_rule_source_hash_covers_c_headers_and_ignores_generated_binary(tmp_path):
    """C/头文件改变必须换规则源哈希，编译产物与时间戳不混入源口径。"""
    directory = tmp_path / "src/hangma_bot/hangma"
    directory.mkdir(parents=True)
    (directory / "math.py").write_text("VERSION = 'grouped'\n")
    c_source = directory / "math.c"
    c_source.write_text("int value = 1;\n")
    first = compute_rules_hash(tmp_path)
    c_source.write_text("int value = 2;\n")
    second = compute_rules_hash(tmp_path)
    assert first != second
    header = directory / "math.h"
    header.write_text("#define RULE_VERSION 1\n")
    third = compute_rules_hash(tmp_path)
    assert second != third
    (directory / "math.so").write_bytes(b"different build, same source")
    c_source.touch()
    assert compute_rules_hash(tmp_path) == third


def test_loaded_math_artifact_is_recorded_separately():
    """公开诊断中的加载路径与启动元数据中的制品摘要一一对应。"""
    from hangma_bot.hangma.hand_analysis import math_backend_info

    info = math_backend_info()
    metadata = hand_math_runtime_metadata()
    assert metadata["implementation"] == info["implementation"]
    assert metadata["semantics_version"] == "hangma-standard-grouped-v1"
    if info["native_path"] is None:
        assert metadata["native_sha256"] is None
    else:
        assert metadata["native_sha256"] == hashlib.sha256(Path(info["native_path"]).read_bytes()).hexdigest()
    assert "native_path" not in metadata
