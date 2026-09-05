"""官方指南同步脚本纯函数测试：抓取解析、落盘/跳过、基线对比与退出码。

只验证脚本的纯函数路径（get_raw 注入假响应、输出目录指向 tmp_path），
不发起任何网络连接（官方真实路径由手动执行 scripts/sync_official_guide.py 验收）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location("hangma_scripts_" + name, SCRIPTS_DIR / name)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # dataclass 注解求值需要模块已注册
    spec.loader.exec_module(module)
    return module


sync = _load_script("sync_official_guide.py")


def _version_doc(version: int, changes) -> str:
    return json.dumps(
        {
            "version": version,
            "updated_at": "2026-09-06",
            "changes": changes,
        },
        ensure_ascii=False,
    )


def _text_doc(content: str, version: int) -> str:
    return json.dumps(
        {"version": version, "updated_at": "2026-09-06", "format": "text", "content": content},
        ensure_ascii=False,
    )


CHANGES = [
    {
        "version": 16,
        "date": "2026-09-06",
        "type": "breaking",
        "summary": "示例 breaking",
        "detail": "",
    },
    {
        "version": 15,
        "date": "2026-09-06",
        "type": "added",
        "summary": "示例 added",
        "detail": "",
    },
    {
        "version": 14,
        "date": "2026-09-05",
        "type": "added",
        "summary": "guide 全文端点",
        "detail": "",
    },
]


def _fake_get_raw(version: int = 16, content: str = "一、对战规则", changes=CHANGES):
    def get_raw(path: str) -> str:
        if path == sync.GUIDE_VERSION_PATH:
            return _version_doc(version, changes)
        if path == sync.GUIDE_TEXT_PATH:
            return _text_doc(content, version)
        raise AssertionError("未预期的路径: " + path)

    return get_raw


def test_fetch_guide_parses_snapshot() -> None:
    snapshot = sync.fetch_guide(_fake_get_raw())
    assert snapshot.version == 16
    assert snapshot.updated_at == "2026-09-06"
    assert len(snapshot.changes) == 3
    assert snapshot.content == "一、对战规则"
    assert '"format": "text"' in snapshot.envelope_raw


def test_fetch_guide_warns_on_version_mismatch(capsys) -> None:
    def get_raw(path: str) -> str:
        if path == sync.GUIDE_VERSION_PATH:
            return _version_doc(16, CHANGES)
        return _text_doc("正文", 15)  # 全文版本落后，官方声明同源

    snapshot = sync.fetch_guide(get_raw)
    assert snapshot.version == 16
    assert "版本 16 与 guide 全文版本 15 不一致" in capsys.readouterr().out


def test_fetch_guide_rejects_bad_shape() -> None:
    # 非法 JSON 是 JSONDecodeError（ValueError 子类，main 按同步失败处理）
    with pytest.raises(ValueError):
        sync.fetch_guide(lambda path: "not-json")
    with pytest.raises(sync.SyncError):
        sync.fetch_guide(
            lambda path: _version_doc(16, CHANGES) if path == sync.GUIDE_VERSION_PATH else "{}"
        )


def test_sync_guide_writes_then_skips(tmp_path: Path) -> None:
    snapshot = sync.fetch_guide(_fake_get_raw())
    result = sync.sync_guide(snapshot, known_version=14, out_dir=tmp_path)
    assert result.version == 16
    assert result.new_changes == tuple(CHANGES[:2])  # v16 breaking + v15 added
    assert result.has_new_breaking is True
    names = {p.name for p in result.written}
    assert names == {
        "official-guide-version-v16.json",
        "official-guide-v16.txt",
        "official-guide-v16-content.txt",
    }
    version_doc = json.loads((tmp_path / "official-guide-version-v16.json").read_text(encoding="utf-8"))
    assert version_doc["version"] == 16
    assert (tmp_path / "official-guide-v16-content.txt").read_text(encoding="utf-8") == "一、对战规则"

    # 内容一致时全部跳过，不再改写
    again = sync.sync_guide(snapshot, known_version=14, out_dir=tmp_path)
    assert again.written == ()
    assert len(again.skipped) == 3


def test_sync_guide_without_known_lists_all_changes(tmp_path: Path) -> None:
    snapshot = sync.fetch_guide(_fake_get_raw())
    result = sync.sync_guide(snapshot, known_version=None, out_dir=tmp_path)
    assert result.new_changes == tuple(CHANGES)


def test_known_guide_version_from_source(tmp_path: Path) -> None:
    # 真实源码路径能读出已审查基线（正值整数即可，具体值随审查进度变化）
    assert isinstance(sync.known_guide_version_from_source(), int)
    stub = tmp_path / "dto_stub.py"
    stub.write_text(
        "# 注释\nKNOWN_GUIDE_VERSION = 7  # 已审查指南版本\n",
        encoding="utf-8",
    )
    assert sync.known_guide_version_from_source(stub) == 7


def test_render_summary_flags_breaking(tmp_path: Path) -> None:
    snapshot = sync.fetch_guide(_fake_get_raw())
    result = sync.sync_guide(snapshot, known_version=14, out_dir=tmp_path)
    text = sync.render_summary(snapshot, 14, result)
    assert "服务器指南 v16" in text
    assert "本地已审查基线：v14" in text
    assert "BREAKING" in text and "示例 breaking" in text
    assert "请人工核对" in text


def test_main_exit_codes(tmp_path: Path, capsys) -> None:
    # 无 breaking 新增：退出码 0
    get_raw = _fake_get_raw(version=15, changes=CHANGES[1:])
    assert (
        sync.main(
            ["--out-dir", str(tmp_path), "--known-version", "15"],
            get_raw=get_raw,
        )
        == 0
    )
    # 基线之后有 breaking 且 --fail-on-breaking：退出码 3
    get_raw = _fake_get_raw(version=16)
    assert (
        sync.main(
            ["--out-dir", str(tmp_path), "--known-version", "14", "--fail-on-breaking"],
            get_raw=get_raw,
        )
        == 3
    )
    # 抓取失败：退出码 4
    def broken(_path: str) -> str:
        raise sync.SyncError("网络不可达")

    assert sync.main(["--out-dir", str(tmp_path)], get_raw=broken) == 4
    assert "同步失败" in capsys.readouterr().err
