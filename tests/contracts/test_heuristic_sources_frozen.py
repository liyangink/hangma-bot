"""旧策略的源码冻结契约；新版本不得通过改共享旧文件漂移实验对照。"""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
V0 = json.loads((ROOT / "doc/implementation/baselines/heuristic-v0.json").read_text())["files"]
V1_FREEZE = json.loads((ROOT / "tests/offline/evidence/v1-acceptance-2026-09-06/freeze.json").read_text())["source_sha256"]
FROZEN = dict(V0)
FROZEN.update({name: V1_FREEZE[name] for name in (
    "src/hangma_bot/policy/heuristic_v1.py",
    "src/hangma_bot/policy/evaluation_v1.py",
    "src/hangma_bot/policy/weights_v1.py",
)})


@pytest.mark.parametrize("name,digest", sorted(FROZEN.items()))
def test_frozen_heuristic_source_is_unchanged(name, digest):
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
