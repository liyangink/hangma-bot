"""通过公开手牌结果核验安装缺失、损坏及不兼容制品的启动退路。"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("failure", ["missing", "import_error", "wrong_version", "memory_error"])
def test_unusable_native_module_uses_corrected_python(failure):
    """在隔离解释器里改变模块加载条件，不替换数学求解器本身。"""
    source = Path(__file__).resolve().parents[3] / "src"
    script = r'''
import importlib.abc,json,sys,types
sys.path.insert(0, sys.argv[1])
name = "hangma_bot.hangma._grouped_native"
failure = sys.argv[2]
if failure == "missing":
    sys.modules[name] = None
elif failure == "wrong_version":
    module = types.ModuleType(name)
    module.SEMANTICS_VERSION = "obsolete"
    sys.modules[name] = module
else:
    class BrokenLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path, target=None):
            if fullname == name:
                return importlib.util.spec_from_loader(fullname,self)
        def create_module(self, spec):
            error = MemoryError if failure == "memory_error" else ImportError
            raise error("injected native loading failure")
        def exec_module(self, module):
            raise AssertionError("not reached")
    sys.meta_path.insert(0,BrokenLoader())
from hangma_bot.hangma.hand_analysis import analyse_hand,math_backend_info,win_split
from hangma_bot.kernel.actions import Tile
hand = tuple(Tile(x) for x in ["1w","2w","4b","5b","6b","7t","8t","9t"]+["东"]*4+["白"])
assert analyse_hand(hand,0).standard_shanten == 0
assert win_split(hand+(Tile("3w"),),0).branch == "平胡"
print(json.dumps(math_backend_info()))
'''
    result = subprocess.run([sys.executable, "-I", "-c", script, str(source), failure],
        capture_output=True, text=True, check=True, timeout=15)
    info = json.loads(result.stdout)
    assert info["implementation"] == "python_grouped"
    assert info["fallback_reason"]
    assert info["native_path"] is None
