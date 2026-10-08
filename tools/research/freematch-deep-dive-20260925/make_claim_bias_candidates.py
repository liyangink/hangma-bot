#!/usr/bin/env python3
"""机械生成「鸣牌倾向」候选：只改父代的碰/吃常数，其余逐行相同。

动机（观察性，非因果）：43 房 / 3,425 局的榜上强手画像显示，
榜上选手鸣牌 1.184 次/局、其他对手 1.155 次/局，**我方只有 1.052 次/局**。

父代对鸣牌定价几乎是零成本：`peng = -6.0`、`chi = -10.0`，
而一个向听步长值 100。所以这两个常数**只在「鸣了与不鸣向听相同」时才起作用**，
也就是只在同一向听层内的排序上起作用。

本脚本把这两个常数改成给定值，测「鸣牌倾向」这条轴的行为可达性。
这是本会话唯一没测过的动作族常数。

用法：
    .venv/bin/python make_claim_bias_candidates.py --settings "0:0,20:10,60:30"
    （格式 碰值:吃值）
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
PENG_OLD = "                fixed = -6.0\n"
CHI_OLD = "                fixed = -10.0\n"


def frozen_source() -> str:
    spec = importlib.util.spec_from_file_location("frozen_r18_v2", FROZEN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["frozen_r18_v2"] = module
    spec.loader.exec_module(module)
    return module.R18_INTEGRATED_POSITIVE_V2_SOURCE


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default="0:0,20:10,60:30")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(PENG_OLD) == 1, "碰常数模板出现 %d 次" % source.count(PENG_OLD)
    assert source.count(CHI_OLD) == 1, "吃常数模板出现 %d 次" % source.count(CHI_OLD)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.settings.split(","):
        peng, chi = (part.strip() for part in token.split(":"))
        candidate = source
        candidate = candidate.replace(PENG_OLD, "                fixed = %s\n" % peng)
        candidate = candidate.replace(CHI_OLD, "                fixed = %s\n" % chi)
        before = source.splitlines()
        after = candidate.splitlines()
        diff = [i for i in range(len(before)) if before[i] != after[i]]
        assert len(diff) == 2, "差异行应为 2，实际 %d" % len(diff)
        name = "OPTY-R18-C08-CLAIM%s_%s.py" % (peng.replace(".", "_"), chi.replace(".", "_"))
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s 差异 %d 行（碰=%s 吃=%s），语法通过" % (name, len(diff), peng, chi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())