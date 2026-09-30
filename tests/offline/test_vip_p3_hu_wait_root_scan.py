"""当前胡选根只依赖行动前观察，并可复现冻结开发根身份。"""

import json
from pathlib import Path

from scripts.vip_p3_hu_wait_root_scan import scan


def test_frozen_seed_root_reappears_without_outcome_fields():
    frozen_path = (Path(__file__).resolve().parents[2] /
                   "review/vip-route-2026-09-30/evidence/"
                   "p3-hu-wait-teacher-20260930/dev-scan.json")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    expected = next(row for row in frozen["selected_roots"] if row["seed"] == 2209)
    actual = scan(start_seed=2209, seeds=1)
    assert actual["counts"]["seed_selected"] == 1
    assert actual["selected_roots"][0] == expected
    assert not ({"terminal", "future_wall", "other_hands"} &
                set(actual["selected_roots"][0]))
