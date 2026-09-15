"""检查规则数学后端是不是**该用原生内核却在静默跑纯 Python 回退**。

**为什么需要它**：`hatch_build.py` 的原生构建钩子在 `auto` 模式下匹配不到或不执行时
只打一句警告就回落纯 Python，**不报错、不中断**。于是"装的时候少做了一步"可以长期
不被发现——2026-09-16 实测：本机 venv 自 09-05 建立，而 C 内核与预编译制品 09-07 才入库，
中间**没有重装**，环境就一直跑纯 Python，每桌 CPU 9.01 秒 vs 启用内核 1.84 秒（4.9 倍）。
性能差异只在跑几千桌时才显形，平时看不出来，而项目的历史吞吐常数因此被误判作废。

**判据**：`prebuilt/hangma/selection.py` 的匹配规则（与安装期**同一份**定义）+ 运行时元数据。
只有"本机存在完全匹配的预编译件、却在跑回退"才判失败——那属漏装；本机确实没有匹配制品
（平台/解释器不符，或数学源码已改而制品未更新）属正常退路，只提示原因。

**用法**：`python scripts/check_native_backend.py [--json]`；退出码 0 通过、1 漏装。
装完新环境、换机器、以及开跑长篇离线评估之前都应跑一次。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def _load_selection():
    """按路径加载共享匹配模块（与 hatch_build.py 用的是同一份定义）。"""

    path = ROOT / "prebuilt" / "hangma" / "selection.py"
    spec = importlib.util.spec_from_file_location("hangma_prebuilt_selection", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_report() -> dict:
    """汇总"本机是否有可用预编译件"与"运行时实际后端"，并给出判定。"""

    sys.path.insert(0, str(ROOT / "src"))
    from hangma_bot.simulation.artifacts import hand_math_runtime_metadata

    selection = _load_selection()
    prebuilt = selection.select_prebuilt(ROOT)
    runtime = hand_math_runtime_metadata()
    verdict = selection.evaluate_backend(runtime, prebuilt)
    return {
        "runtime": runtime,
        "usable_prebuilt": None if prebuilt is None else str(prebuilt[0].relative_to(ROOT)),
        "usable_prebuilt_tag": None if prebuilt is None else prebuilt[1],
        "verdict": verdict["verdict"],
        "ok": verdict["ok"],
        "detail": verdict["detail"],
        "fix": verdict["fix"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查规则数学后端是否为漏装的原生内核")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出，便于机器消费")
    args = parser.parse_args(argv)
    report = collect_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        runtime = report["runtime"]
        print("规则数学后端：" + str(runtime.get("implementation"))
              + " | 语义版本：" + str(runtime.get("semantics_version"))
              + " | 回退原因：" + str(runtime.get("fallback_reason")))
        print("本机可用预编译件：" + str(report["usable_prebuilt"]))
        print("判定：" + report["verdict"] + " —— " + report["detail"])
        if report["fix"]:
            print("修复：" + report["fix"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
