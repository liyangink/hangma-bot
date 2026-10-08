"""最短自然完成组合的一张公开损失压力测试金例。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/offline'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925")))

from g14_natural_second_discard_distribution import _capacity
from g14_route_support_loss_probe import _route_support
from g14_route_support_loss_fast import route_support_fast


def test_completion_route_survives_one_public_loss_only_on_supported_arm():
    hand = Counter("1b 2b 3b 4b 5b 6b 7b 8b 9b 东 东 1w 5w 9w".split())
    public = Counter({**{f"{i}b": 3 for i in range(1, 10)}, "东": 2,
                      **{f"{i}w": amount for i, amount in
                         enumerate((2, 1, 2, 4, 3, 4, 4, 1, 2), 1)}})
    scores = {}
    for discarded in ("1w", "9w"):
        after = hand.copy()
        after[discarded] -= 1
        action = "discard:" + discarded
        scores[discarded] = _route_support(
            after, 0, _capacity(after, public, Counter(), action))
    assert (scores["1w"]["natural_need"], scores["1w"]["routes"],
            scores["1w"]["q1"]) == (2, 0, 0)
    assert (scores["9w"]["natural_need"], scores["9w"]["routes"],
            scores["9w"]["q1"]) == (2, 1, 1)
    assert scores["9w"]["route_examples"] == [["2w", "3w"]]


def test_pruned_route_enumerator_matches_brute_gold_example():
    hand = Counter("1b 2b 3b 4b 5b 6b 7b 8b 9b 东 东 1w 5w 9w".split())
    public = Counter({**{f"{i}b": 3 for i in range(1, 10)}, "东": 2,
                      **{f"{i}w": amount for i, amount in
                         enumerate((2, 1, 2, 4, 3, 4, 4, 1, 2), 1)}})
    for discarded in ("1w", "9w"):
        after = hand.copy()
        after[discarded] -= 1
        capacity = _capacity(after, public, Counter(), "discard:" + discarded)
        brute = _route_support(after, 0, capacity)
        fast = route_support_fast(after, 0, capacity)
        assert (fast["natural_need"], fast["routes"], fast["q1"],
                fast["route_examples"]) == (
                    brute["natural_need"], brute["routes"], brute["q1"],
                    brute["route_examples"])
        assert fast["tested_states"] < brute["tested_multisets"]
