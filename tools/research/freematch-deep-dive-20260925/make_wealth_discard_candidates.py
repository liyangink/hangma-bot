#!/usr/bin/env python3
"""机械生成「弃财神惩罚」候选：只改 `wealth_discard_part`，其余逐行相同。

动机（观察性）：43 房 3,425 局的榜上强手画像显示，榜上选手**弃财神 0.0105 次/局**，
而我方只有 **0.002 次/局（5 倍差）**；同时我方爆头占胡 15.0% vs 榜上 29.5%。

父代对打财神定价 −60 分，而一个向听步长值 100——所以它几乎从不主动打财神
（全样本 370 局只打了 7 次）。**这个常数是本会话唯一没测过的修饰项。**

用法：
    .venv/bin/python make_wealth_discard_candidates.py --values "-20,0,40"
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
FROZEN = _project_file(_PROJECT_ROOT, ROOT / "src" / "hangma_bot" / "policy" / "r18_integrated_positive_v2.py")
ANCHOR = "                wealth_discard_part = -60.0\n"


def frozen_source() -> str:
    spec = importlib.util.spec_from_file_location("frozen_r18_v2", FROZEN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["frozen_r18_v2"] = module
    spec.loader.exec_module(module)
    return module.R18_INTEGRATED_POSITIVE_V2_SOURCE


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--values", default="-20,0,40")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(ANCHOR) == 1, "锚点出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.values.split(","):
        value = token.strip()
        candidate = source.replace(ANCHOR, "                wealth_discard_part = %s\n" % value)
        before = source.splitlines()
        after = candidate.splitlines()
        diff = [i for i in range(len(before)) if before[i] != after[i]]
        assert len(diff) == 1, "差异行应为 1，实际 %d" % len(diff)
        name = "OPTY-R18-C10-WDISC%s.py" % value.replace("-", "m").replace(".", "_")
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s 差异 1 行（wealth_discard_part=%s），语法通过" % (name, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())