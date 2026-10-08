"""研究目录退出 Git 后，共享合同与本机原件仍可按历史逻辑路径定位。"""

import hashlib
import json

from hangma_bot.adapters.recording.project_storage import project_file


def test_shared_contract_keeps_original_bytes_without_review_directory(tmp_path):
    """新检出只交付合同副本，也能沿用原合同摘要与逻辑身份。"""
    original = "review/route/contract.json"
    shared = tmp_path / "doc/research/contract.json"
    shared.parent.mkdir(parents=True)
    raw = b'{"schema":"fixed/1"}\n'
    shared.write_bytes(raw)
    (shared.parent / "storage-map.json").write_text(json.dumps({"shared_paths": {original: "doc/research/contract.json"}}))
    actual = project_file(tmp_path, original)
    assert not (tmp_path / "review").exists()
    assert actual.read_bytes() == raw
    assert hashlib.sha256(actual.read_bytes()).digest() == hashlib.sha256(raw).digest()


def test_local_data_root_resolves_stored_absolute_parent_path(tmp_path, monkeypatch):
    """旧父代记录的绝对路径无需改字节，数据可在明确配置的本机根读取。"""
    checkout = tmp_path / "checkout"
    data_root = tmp_path / "offline-data"
    checkout.mkdir()
    parent = data_root / "review/parents/generation.json"
    parent.parent.mkdir(parents=True)
    parent.write_text('{"parent":"preserved"}\n')
    monkeypatch.setenv("HANGMA_OFFLINE_DATA_ROOT", str(data_root))
    assert project_file(checkout, checkout / "review/parents/generation.json") == parent
    assert project_file(checkout, parent) == parent


def test_explicit_external_input_is_not_relocated(tmp_path):
    """调用者指定的根外输入保持原位置，缺失数据也不会触发下载。"""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    external = tmp_path / "explicit-input.json"
    assert project_file(checkout, external) == external
