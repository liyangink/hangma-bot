"""通过安装钩子的公开入口验证免编译复用和错误制品隔离。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def package(tmp_path, monkeypatch):
    """构造有明确兼容范围和源码摘要的安装包，不依赖本机架构。"""
    pytest.importorskip("hatchling")
    path = Path(__file__).resolve().parents[2] / "hatch_build.py"
    spec = importlib.util.spec_from_file_location("prebuilt_install_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "project"
    source = root / "src/hangma_bot/hangma/_grouped_native.c"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"current C source")
    python_source = source.with_name("_standard_python.py")
    python_source.write_bytes(b"current Python semantics")
    artifact = root / "prebuilt/hangma/cp311-macosx_11_0_arm64/_grouped_native.cpython-311-darwin.so"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"prebuilt artifact")
    item = {"path": artifact.relative_to(root / "prebuilt/hangma").as_posix(),
        "platform": "darwin", "architecture": "arm64", "python_implementation": "cpython",
        "python_version": [3, 11], "soabi": "cpython-311-darwin",
        "extension_suffix": ".cpython-311-darwin.so", "minimum_macos": [11, 0],
        "binary_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "sources": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, python_source)}}
    manifest = root / "prebuilt/hangma/manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "artifacts": [item]}))
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin",
        implementation=SimpleNamespace(name="cpython"), version_info=(3, 11, 15)))
    monkeypatch.setattr(module, "sysconfig", SimpleNamespace(get_config_var=lambda key:
        {"SOABI": "cpython-311-darwin", "EXT_SUFFIX": ".cpython-311-darwin.so"}.get(key)))
    monkeypatch.setattr(module, "platform", SimpleNamespace(machine=lambda: "arm64", mac_ver=lambda: ("26.0", (), "")))
    for name in ("CC", "CFLAGS", "LDFLAGS", "ARCHFLAGS", "MACOSX_DEPLOYMENT_TARGET", "_PYTHON_HOST_PLATFORM"):
        monkeypatch.delenv(name, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("匹配制品时不能启动编译器")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    app = SimpleNamespace(display_warning=lambda message: None, display_info=lambda message: None)
    hook = module.CustomBuildHook(str(root), {}, None, None, str(tmp_path / "wheel"), "wheel", app)
    return SimpleNamespace(module=module, hook=hook, root=root, artifact=artifact,
        source=source, manifest=manifest, item=item)


@pytest.mark.parametrize("mode", ["auto", "required", "prebuilt"])
@pytest.mark.parametrize("version", ["standard", "editable"])
def test_matching_prebuilt_does_not_invoke_compiler(package, monkeypatch, mode, version):
    """兼容机器的普通/开发安装均复制已验证制品，无需编译器或头文件。"""
    monkeypatch.setenv("HANGMA_NATIVE", mode)
    data = {"force_include": {}}
    package.hook.initialize(version, data)
    assert data["pure_python"] is False
    assert data["tag"] == "cp311-cp311-macosx_11_0_arm64"
    if version == "editable":
        destination = package.source.with_name(package.artifact.name)
        assert destination.read_bytes() == package.artifact.read_bytes()
    else:
        assert list(data["force_include"].values()) == ["hangma_bot/hangma/" + package.artifact.name]
    package.hook.finalize(version, data, "unused")


@pytest.mark.parametrize("reason", ["platform", "architecture", "python", "abi", "macos",
    "source", "binary", "missing_source", "missing_artifact", "manifest_version", "manifest_json", "escaped_path"])
def test_invalid_prebuilt_is_rejected_and_old_editable_artifact_removed(package, monkeypatch, reason):
    """预编译专用安装不能悄悄复用不兼容/过期制品，也不能偷偷编译。"""
    item = package.item
    document = {"schema_version": 1, "artifacts": [item]}
    if reason == "platform":
        item["platform"] = "linux"
    elif reason == "architecture":
        item["architecture"] = "x86_64"
    elif reason == "python":
        item["python_version"] = [3, 12]
    elif reason == "abi":
        item["soabi"] = "cpython-311d-darwin"
    elif reason == "macos":
        item["minimum_macos"] = [27, 0]
    elif reason == "source":
        package.source.write_bytes(b"changed C source")
    elif reason == "binary":
        package.artifact.write_bytes(b"damaged binary")
    elif reason == "missing_source":
        item["sources"].pop("src/hangma_bot/hangma/_standard_python.py")
    elif reason == "missing_artifact":
        package.artifact.unlink()
    elif reason == "manifest_version":
        document["schema_version"] = 999
    elif reason == "escaped_path":
        outside = package.root.parent / package.artifact.name
        outside.write_bytes(package.artifact.read_bytes())
        item["path"] = "../../../" + outside.name
    package.manifest.write_text("invalid-json" if reason == "manifest_json" else json.dumps(document))
    destination = package.source.with_name(package.artifact.name)
    destination.write_bytes(b"stale editable binary")
    monkeypatch.setenv("HANGMA_NATIVE", "prebuilt")
    with pytest.raises(RuntimeError, match="没有与当前平台、Python 和源码匹配"):
        package.hook.initialize("editable", {"force_include": {}})
    assert not destination.exists()


@pytest.mark.parametrize("trigger", ["changed_source", "custom_compiler"])
def test_auto_install_compiles_when_prebuilt_cannot_be_used(package, monkeypatch, trigger):
    """源码变化或显式编译配置使预编译失效，沿用原有源码构建路径。"""
    monkeypatch.setenv("HANGMA_NATIVE", "auto")
    if trigger == "changed_source":
        package.source.write_bytes(b"new source requiring new binary")
    else:
        monkeypatch.setenv("CC", "custom-compiler")
    include = package.root / "include"
    include.mkdir()
    (include / "Python.h").write_text("// test header")
    package.module.sysconfig.get_paths = lambda: {"include": str(include)}
    calls = []

    def compile_artifact(command, **kwargs):
        calls.append(command)
        Path(command[command.index("-o") + 1]).write_bytes(b"fresh compiled binary")

    monkeypatch.setattr(package.module.subprocess, "run", compile_artifact)
    data = {"force_include": {}}
    package.hook.initialize("standard", data)
    assert len(calls) == 1
    if trigger == "custom_compiler":
        assert calls[0][0] == "custom-compiler"
    assert Path(next(iter(data["force_include"]))).read_bytes() == b"fresh compiled binary"
    assert data["infer_tag"] is True
    package.hook.finalize("standard", data, "unused")


def test_prebuilt_only_install_ignores_unavailable_compiler(package, monkeypatch):
    """要求免编译时，即使系统编译器不可用也能成功复用兼容制品。"""
    monkeypatch.setenv("HANGMA_NATIVE", "prebuilt")
    monkeypatch.setenv("CC", "/no-compiler")
    package.hook.initialize("editable", {"force_include": {}})
    assert package.source.with_name(package.artifact.name).read_bytes() == package.artifact.read_bytes()


def test_pure_python_install_removes_previous_native_artifact(package, monkeypatch):
    """显式纯 Python 安装不因仓库携带预编译库而留下旧开发扩展。"""
    destination = package.source.with_name(package.artifact.name)
    destination.write_bytes(b"previous native artifact")
    monkeypatch.setenv("HANGMA_NATIVE", "off")
    package.hook.initialize("editable", {"force_include": {}})
    assert not destination.exists()
