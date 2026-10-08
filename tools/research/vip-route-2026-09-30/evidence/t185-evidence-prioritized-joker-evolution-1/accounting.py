"""复用原逐单局分账，物理座位0—3；不从分账建立规则。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
def account(result):
    """单局/续桌积分账，顺序固定物理座位0—3；大牌按至少四番。"""
    a = {"net": 0, "ordinary_hu_income": 0, "large_hu_income": 0, "payments": 0,
         "other_wins": 0, "draws": 0, "own_dealer_net": 0, "own_non_dealer_net": 0}
    for s in result["settlements"]:
        delta = s["score_delta"]
        assert len(delta) == 4 and all(type(v) is int for v in delta) and sum(delta) == 0
        a["net"] += delta[0]
        a["own_dealer_net" if s["dealer_seat"] == 0 else "own_non_dealer_net"] += delta[0]
        if s["is_draw"]:
            assert delta == [0, 0, 0, 0]
            a["draws"] += 1
        elif s["winner_seat"] == 0:
            assert delta[0] > 0
            a["large_hu_income" if s["fan"] >= 4 else "ordinary_hu_income"] += delta[0]
        else:
            assert delta[0] <= 0
            a["payments"] += delta[0]
            a["other_wins"] += 1
    assert a["net"] == result["focal_net_score"] == a["ordinary_hu_income"] + a["large_hu_income"] + a["payments"]
    return a
