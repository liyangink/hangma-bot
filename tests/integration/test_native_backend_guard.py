"""规则数学后端"漏装"判定的回归（原生内核已入库却跑纯 Python 回退）。

**为什么要有这条测试**：2026-09-16 实测到一次真实漏装——venv 比 C 内核早两天建立、
之后从未重装，环境长期跑纯 Python，每桌 CPU 与启用内核相差 4.9 倍，而回退是**静默**的
（只打警告、不报错）。本测试锁住三件事：判定能区分"漏装"与"正常退路"、修复命令在场、
以及**匹配规则只有一处定义**（防止"安装期判据"与"检查期判据"漂移）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FALLBACK = {"implementation": "python", "semantics_version": None,
            "fallback_reason": "no native module", "native_sha256": None}
NATIVE = {"implementation": "c_grouped", "semantics_version": "hangma-standard-grouped-v1",
          "fallback_reason": None, "native_sha256": "deadbeef"}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def selection():
    return _load("hangma_prebuilt_selection_test",
                 ROOT / "prebuilt" / "hangma" / "selection.py")


@pytest.fixture(scope="module")
def checker():
    return _load("check_native_backend_test", ROOT / "scripts" / "check_native_backend.py")


def test_native_backend_passes(selection):
    verdict = selection.evaluate_backend(NATIVE, (Path("/x/_grouped_native.so"), "cp311"))
    assert verdict["ok"] is True
    assert verdict["verdict"] == "native"
    assert verdict["fix"] is None


def test_fallback_without_usable_prebuilt_is_legitimate(selection):
    """本机确实没有匹配制品时，纯 Python 回退不算问题，只提示原因。"""

    verdict = selection.evaluate_backend(FALLBACK, None)
    assert verdict["ok"] is True
    assert verdict["verdict"] == "fallback_without_prebuilt"
    assert verdict["fix"] is None


def test_fallback_with_usable_prebuilt_is_reported_as_missing_install(selection):
    """**漏装**：完全匹配的预编译件就在盘上，却在跑回退 ⇒ 必须失败并给修复命令。"""

    verdict = selection.evaluate_backend(FALLBACK, (Path("/x/_grouped_native.so"), "cp311"))
    assert verdict["ok"] is False
    assert verdict["verdict"] == "fallback_with_usable_prebuilt"
    assert verdict["fix"] and "pip install" in verdict["fix"]
    assert "_grouped_native.so" in verdict["detail"]


def test_unavailable_runtime_is_treated_as_fallback_not_success(selection):
    """运行时元数据读不到时不能被当成"已加载原生"，否则检查会静默放过漏装。"""

    verdict = selection.evaluate_backend({"implementation": "unavailable"}, (Path("/x/a.so"), "tag"))
    assert verdict["ok"] is False
    assert verdict["verdict"] == "fallback_with_usable_prebuilt"


def test_prebuilt_matching_has_a_single_definition():
    """匹配规则只允许有一处定义：构建期与检查期必须共用同一份模块。"""

    hatch = (ROOT / "hatch_build.py").read_text(encoding="utf-8")
    assert "def select_prebuilt" not in hatch, "构建钩子内又出现了一份本地定义"
    assert "prebuilt" in hatch and "selection.py" in hatch
    checker_text = (ROOT / "scripts" / "check_native_backend.py").read_text(encoding="utf-8")
    assert "selection.py" in checker_text
    assert "def evaluate_backend" not in checker_text, "检查脚本不应另写一套判定"


def test_checker_reports_json_contract(checker):
    """检查入口的 JSON 契约：机器消费需要的字段必须在场且可序列化。"""

    report = checker.collect_report()
    for key in ("runtime", "usable_prebuilt", "verdict", "ok", "detail", "fix"):
        assert key in report
    assert report["verdict"] in {"native", "fallback_without_prebuilt", "fallback_with_usable_prebuilt"}
    assert isinstance(checker.main(["--json"]), int)


def test_this_checkout_is_not_a_missing_install(checker):
    """**把漏装变成跑测试时就会失败的硬错误**。

    `ok` 在"本机确实没有匹配制品"时仍为真（正常退路），只有"有匹配件却没装上"才为假
    ——因此这条断言在任何平台上都成立，且换机器后第一次跑测试就会被拦住，
    不必依赖谁记得去手工检查。
    """

    report = checker.collect_report()
    assert report["ok"] is True, (
        "规则数学后端疑似漏装：" + report["detail"] + " | 修复：" + str(report["fix"]))
