"""多根机会层冻结必须保留缺证据根，并只用行动前事实选比较臂。"""

import gzip
import json
from pathlib import Path

import pytest

from scripts.vip_p3_multi_opportunity_freeze import freeze


_SELECTION = Path("review/vip-route-2026-09-30/evidence/"
                  "p3-multi-opportunity-20260930/selection-4101-4400.json.gz")


def test_freeze_keeps_all_selected_roots_and_model_gaps():
    """31 个自然种子按根聚类；四个模型缺事实不得从抽样框消失。"""

    frozen = freeze(_SELECTION)
    roots = frozen["roots"]
    assert len(roots) == 36
    assert len({row["seed"] for row in roots}) == 31
    assert sum(row["roles"]["anchored"] is None for row in roots) == 4
    assert sum(row["roles"]["anchored"] not in (None, row["roles"]["r18"])
               for row in roots) == 13
    assert sum("first_highfan_witness" in row["tags"] for row in roots) == 7
    assert all(row["roles"]["r18"] in row["forced_first_actions"] for row in roots)
    assert all(row["worlds_per_root"] == (32 if "first_highfan_witness" in
               row["tags"] else 16) for row in roots)


def test_freeze_rejects_changed_pre_outcome_model_choice(tmp_path):
    """即使新首选合法，冻结包也不能悄悄改掉扫描时锁定的选择。"""

    selection = json.loads(gzip.decompress(_SELECTION.read_bytes()))
    row = next(item for item in selection["selected_roots"]
               if item["anchored_first_action_key"] is not None)
    row["anchored_first_action_key"] = next(
        key for key in row["legal_action_keys"]
        if key != row["anchored_first_action_key"])
    changed = tmp_path / "selection.json"
    changed.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="冻结模型首选"):
        freeze(changed)
