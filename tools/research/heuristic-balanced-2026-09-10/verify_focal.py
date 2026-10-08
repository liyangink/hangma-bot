"""对拍三种口径（同一份 dump、同一个脚本、32 根）：池化 / 焦点(perm[0])。

目的：定位 measure_dealer_edge.py（池化 -3.39pp、焦点 -11.40pp）与
measure_mechanism_effect.py（焦点 +11.85pp）在四席全 V2 的对称桌上给出的矛盾。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_dealer_edge import root_run  # noqa: E402

seats = ("weighted_heuristic_v2",) * 4
pooled = collections.Counter()
focal = collections.Counter()
focal_dealer = [0, 0]
draws = [0, 0]
per_root_focal = []
for i in range(32):
    results, hands, labels, _bad = root_run((seats, i, 1360000 + i, "verify-focal"))
    perm_by_match = {}
    for row in results:
        m = row.game_key.game_id if row.game_key is not None else None
        if m is not None:
            perm_by_match[m] = tuple(row.seat_permutation)
    root_focal = collections.Counter()
    for hand in hands:
        m = hand.get("game_id")
        if m not in perm_by_match:
            continue
        f = perm_by_match[m][0]
        dealer = hand.get("dealer_seat")
        winner = hand.get("winner")
        draw = hand.get("is_draw")
        draws[0] += 1 if draw else 0
        draws[1] += 1
        for seat_index in range(4):
            wan = (winner == seat_index) and not draw
            pooled["dh" if seat_index == dealer else "ph"] += 1
            pooled["dw" if seat_index == dealer else "pw"] += 1 if wan else 0
        wan_f = (winner == f) and not draw
        key = "dh" if f == dealer else "ph"
        focal[key] += 1
        focal["dw" if f == dealer else "pw"] += 1 if wan_f else 0
        root_focal[key] += 1
        root_focal["dw" if f == dealer else "pw"] += 1 if wan_f else 0
        focal_dealer[0] += 1 if f == dealer else 0
        focal_dealer[1] += 1
    per_root_focal.append(root_focal)


def show(name, c):
    dr = c["dw"] / c["dh"] if c["dh"] else float("nan")
    pr = c["pw"] / c["ph"] if c["ph"] else float("nan")
    print("%-10s 庄手=%5d 庄胡率=%.4f 闲手=%5d 闲胡率=%.4f 优势=%+.4f" % (
          name, c["dh"], dr, c["ph"], pr, dr - pr))


show("池化", pooled)
show("焦点", focal)
print("焦点座位做庄占比 %.4f（期望 0.25）；全池流局率 %.4f" % (
      focal_dealer[0] / focal_dealer[1], draws[0] / draws[1]))
deltas = []
for c in per_root_focal:
    if c["dh"] and c["ph"]:
        deltas.append(c["dw"] / c["dh"] - c["pw"] / c["ph"])
print("逐根焦点优势：n=%d 均值=%+.4f 最小=%+.4f 最大=%+.4f" % (
      len(deltas), sum(deltas) / len(deltas) if deltas else 0, min(deltas), max(deltas)))

