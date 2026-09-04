"""kernel 包依赖方向守卫：不得依赖业务或基础设施模块。"""

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

# 仓库根目录（tests/unit/kernel/test_boundaries.py 向上四级）。
_REPO_ROOT = Path(__file__).resolve().parents[3]

# 在干净子进程中执行的导入闭包检查：无论本测试进程此前导入过什么，
# 子进程的 sys.modules 都从零开始，差分结果只反映 kernel 自身的导入。
_PROBE_CODE = textwrap.dedent(
    """
    import json
    import sys

    import hangma_bot.kernel.actions  # noqa: F401
    import hangma_bot.kernel.config  # noqa: F401
    import hangma_bot.kernel.observation  # noqa: F401
    import hangma_bot.kernel.serialization  # noqa: F401

    banned_prefixes = (
        "hangma_bot.hangma",
        "hangma_bot.policy",
        "hangma_bot.application",
        "hangma_bot.adapters",
        "httpx",
    )
    loaded = sorted(
        module
        for module in sys.modules
        for prefix in banned_prefixes
        if module == prefix or module.startswith(prefix + ".")
    )
    print(json.dumps(loaded))
    """
)


class KernelBoundaryTests(unittest.TestCase):
    """AGENTS.md 第 5 节：kernel 只保存稳定值对象，不依赖业务模块。"""

    def test_kernel_import_closure_is_clean(self) -> None:
        """干净子进程中导入 kernel 全部子模块，不得加载业务模块或 HTTP 客户端。

        早期版本基于本进程 `sys.modules` 差分：unittest discover 会先收集
        （即导入）全部测试模块，kernel 子模块往往已被导入，差分为空导致
        守卫空转；同进程先跑业务模块测试又会反向误报。子进程方案两种
        场景下都给出真实结论。
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = str(_REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-B", "-c", _PROBE_CODE],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            env=env,
        )
        self.assertEqual(
            result.returncode,
            0,
            "kernel 导入探针子进程失败：{0}".format(result.stderr.strip()),
        )
        self.assertEqual(
            json.loads(result.stdout.strip()),
            [],
            "kernel 导入闭包混入了业务或基础设施模块",
        )


if __name__ == "__main__":
    unittest.main()
