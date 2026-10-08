#!/usr/bin/env python3
"""机械生成「到达价值（番值加权进张）」候选：只插入一段，其余与冻结父代逐行相同。

机制：父代把 `useful_tiles` 的未见枚数直接求和当作价值（`support`），
即每张有效牌都算 1 分，**完全不区分「摸到它会胡多少番」**。
规则模块其实已经在每张候选上给出 `routes`，每条路线带 `conditional_settlement.fan`
与该路线的成胡有效牌。本候选把进张按番值加权：

    route_mass = Σ_routes Σ_(route.useful_tiles) remaining_estimate × fan
    total += W × route_mass

这是「到达价值」的最窄形式：不改变候选集合、不改变规则、不预测未来摸牌，
只把规则已证事实里的番值接进打分。

插入点：主项 `total = base_floor - 1.0 if unknown else base` 之后。
生成后逐行核对：除插入块外必须与冻结源码逐字节相同。

用法：
    .venv/bin/python make_route_value_candidates.py --weights 0.5,2,8
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
ANCHOR = "        total = base_floor - 1.0 if unknown else base\n"


def frozen_source() -> str:
    spec = importlib.util.spec_from_file_location("frozen_r18_v2", FROZEN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["frozen_r18_v2"] = module
    spec.loader.exec_module(module)
    return module.R18_INTEGRATED_POSITIVE_V2_SOURCE


def block(weight: str) -> str:
    """按父代风格做类型防御；任一事实不可用时该项整点取零，不改其余评分。"""
    body = [
        "        route_mass = 0.0",
        "        route_facts = action.get(\"routes\")",
        "        if route_facts:",
        "            for route_fact in route_facts:",
        "                route_settlement = route_fact.get(\"conditional_settlement\")",
        "                if route_settlement is None:",
        "                    continue",
        "                route_fan = route_settlement.get(\"fan\")",
        "                if route_fan is None or route_fan is True or route_fan is False:",
        "                    continue",
        "                for route_tile in route_fact.get(\"useful_tiles\") or ():",
        "                    route_remaining = route_tile.get(\"remaining_estimate\")",
        "                    if route_remaining is None or route_remaining is True or route_remaining is False:",
        "                        continue",
        "                    route_mass += float(route_remaining) * float(route_fan)",
        "        total += %s * route_mass" % weight,
    ]
    return "\n".join(body) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="0.5,2,8")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.weights.split(","):
        weight = token.strip()
        inserted_block = block(weight)
        candidate = source.replace(ANCHOR, ANCHOR + inserted_block)
        before = source.splitlines()
        after = candidate.splitlines()
        added = len(inserted_block.splitlines())
        assert len(after) - len(before) == added, "插入行数不符"
        index = before.index(ANCHOR.rstrip("\n"))
        assert before[:index + 1] == after[:index + 1], "插入点之前出现差异"
        assert before[index + 1:] == after[index + 1 + added:], "插入点之后出现差异"
        assert all(line.startswith("        ") for line in after[index + 1:index + 1 + added])
        name = "OPTY-R18-C06-ROUTEVALUE%s.py" % weight.replace(".", "_")
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s 插入 %d 行，其余逐行相同，语法通过" % (name, added))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())