#!/usr/bin/env python3
"""G79：用冻结自由赛房检验玩家可见牌码事实对他家暗手占用的预测。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import NamedTuple

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
for directory in (HERE, _project_file(_PROJECT_ROOT, ROOT / "review/baotou-anatomy-20260925"), _project_file(_PROJECT_ROOT, ROOT / "src")):
    sys.path.insert(0, str(directory))

import anatomy_lib as anatomy  # noqa: E402
import c31_action_layer_gap as c31  # noqa: E402
import g59_freematch_white_value_audit as g59  # noqa: E402
from extract_room_scores import load_rooms  # noqa: E402


G60 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927/manifest.json')
G9 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G79-TILE-OCCUPANCY-MODEL-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g79-tile-occupancy-transfer-20260928/result.json')
POSITIONS = (1, 4, 7)
FEATURES = ("honor", "terminal", "edge", "unknown_minus_two",
            "opponent_same_river", "own_same_river", "opponent_neighbor_river",
            "opponent_same_suit_melds")
RIDGE = 100.0
REPLICATES = 20_000
RNG_SEED = 20260928


class Window(NamedTuple):
    """一张事前选定的本人弃牌窗；`hidden` 仅是赛后标签。"""

    room: str
    position: int
    features: np.ndarray  # [34, 8]，只来自本人依法可见事实
    unknown: np.ndarray   # [34]，每牌码公开未知实体张数
    hidden: np.ndarray    # [34]，仅离线评测可读取的他家暗手真实占用
    opponent_total: int   # 三家暗手张数，线上可见
    wall_total: int       # 当前公开墙余实体张数


def sha(path: Path) -> str:
    """冻结文件的 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def sigmoid(value: np.ndarray) -> np.ndarray:
    """数值稳定的逻辑概率。"""

    clipped = np.clip(value, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _features(snap: dict, seat: int) -> tuple[np.ndarray, np.ndarray, int, int]:
    """仅由弃牌前本人手牌与四家公开信息产生八维特征。"""

    own = Counter(snap["hands"][seat])
    own[snap["tile"]] += 1  # C31 快照在弃牌后，撤回当前本人弃牌。
    rivers = [list(river) for river in snap["rivers"]]
    if not rivers[seat] or rivers[seat][-1] != snap["tile"]:
        raise ValueError("本人牌河不能撤回本次弃牌")
    rivers[seat].pop()
    own_river = Counter(rivers[seat])
    opponent_river = Counter(
        code for other, river in enumerate(rivers) if other != seat for code in river
    )
    public = Counter(code for river in rivers for code in river)
    meld_suit = Counter()
    for seat_melds in snap["melds"]:
        for meld in seat_melds:
            codes = meld["tiles"]
            public.update(codes)
            if meld["kind"] not in ("chi", "peng", "gang_ming", "gang_an", "gang_bu"):
                raise ValueError("公开副露种类未知")
            if codes and len(codes[0]) == 2 and codes[0][1] in "wbt":
                meld_suit[codes[0][1]] += 1
    opponent_count = sum(sum(hand.values()) for other, hand in enumerate(snap["hands"])
                         if other != seat)
    wall = 136 - sum(sum(hand.values()) for hand in snap["hands"]) - sum(
        len(river) for river in snap["rivers"]
    ) - sum(len(meld["tiles"]) for row in snap["melds"] for meld in row)
    if not 0 <= wall <= 136:
        raise ValueError("官方墙余物理计数非法")

    X = np.zeros((34, len(FEATURES)), dtype=np.float64)
    N = np.empty(34, dtype=np.int16)
    for index, code in enumerate(c31.TILE_ORDER):
        n = 4 - own[code] - public[code]
        if not 0 <= n <= 4:
            raise ValueError("公开未知牌码容量越界")
        N[index] = n
        honor = code == c31.WEALTH or not (len(code) == 2 and code[1] in "wbt")
        X[index, 0] = honor
        X[index, 1] = not honor and code[0] in "19"
        X[index, 2] = not honor and code[0] in "28"
        X[index, 3] = n - 2
        X[index, 4] = min(2, opponent_river[code])
        X[index, 5] = min(2, own_river[code])
        if not honor:
            number, suit = int(code[0]), code[1]
            X[index, 6] = min(4, sum(opponent_river[f"{neighbor}{suit}"]
                                     for neighbor in (number - 1, number + 1)
                                     if 1 <= neighbor <= 9))
            X[index, 7] = min(2, meld_suit[suit])
    H = opponent_count
    if int(N.sum()) != H + wall:
        raise ValueError("公开未知池不等于他家暗手与墙余总量")
    return X, N, H, wall


def _window(snap: dict, room: str, position: int) -> Window:
    """信息白名单构造与赛后标签分离，供训练与外部评分共用。"""

    seat = snap["discarder"]
    X, N, H, wall = _features(snap, seat)
    hidden = Counter()
    for other, hand in enumerate(snap["hands"]):
        if other != seat:
            hidden.update(hand)
    y = np.asarray([hidden[code] for code in c31.TILE_ORDER], dtype=np.int16)
    if int(y.sum()) != H:
        raise ValueError("离线占用标签张数不等于公开三家暗手总张数")
    if np.any(y > N):
        raise ValueError("他家暗手牌码超过公开未知容量")
    return Window(room, position, X, N, y, H, wall)


def _fit(train: list[Window]) -> tuple[np.ndarray, dict]:
    """只在开发房拟合预登记的八参数二项模型，无截距与超参搜索。"""

    X = np.concatenate([w.features for w in train], axis=0)
    n = np.concatenate([w.unknown for w in train]).astype(float)
    y = np.concatenate([w.hidden for w in train]).astype(float)
    offsets = np.concatenate([
        np.full(34, np.log(w.opponent_total / w.wall_total)) for w in train
    ])
    selected = n > 0
    X, n, y, offsets = X[selected], n[selected], y[selected], offsets[selected]
    beta = np.zeros(len(FEATURES), dtype=float)

    def loss(parameters: np.ndarray) -> float:
        z = offsets + X @ parameters
        return float(np.sum(n * np.logaddexp(0.0, z) - y * z)
                     + 0.5 * RIDGE * np.dot(parameters, parameters))

    base_loss = loss(beta)
    for iteration in range(24):
        z = offsets + X @ beta
        q = sigmoid(z)
        gradient = X.T @ (n * q - y) + RIDGE * beta
        curvature = n * q * (1.0 - q)
        hessian = X.T @ (X * curvature[:, None]) + RIDGE * np.eye(len(beta))
        step = np.linalg.solve(hessian, gradient)
        scale = 1.0
        current = loss(beta)
        while scale >= 2 ** -12 and loss(beta - scale * step) > current:
            scale *= 0.5
        if scale < 2 ** -12:
            raise ValueError("开发房 Newton 拟合未能下降")
        beta -= scale * step
        if np.max(np.abs(scale * step)) < 1e-8:
            break
    return beta, {"feature_rows": len(n), "windows": len(train),
                  "base_penalized_binomial_loss": base_loss,
                  "fitted_penalized_binomial_loss": loss(beta),
                  "newton_iterations": iteration + 1}


def _predict(window: Window, beta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """按公开他家暗手总量校准 34 维期望占用，不使用真实牌码标签。"""

    n = window.unknown.astype(float)
    H = window.opponent_total
    base = n * H / (H + window.wall_total)
    logits = np.log(H / window.wall_total) + window.features @ beta
    lower, upper = -35.0, 35.0
    for _ in range(48):
        middle = (lower + upper) / 2.0
        if float(np.dot(n, sigmoid(logits + middle))) < H:
            lower = middle
        else:
            upper = middle
    fitted = n * sigmoid(logits + (lower + upper) / 2.0)
    if abs(float(fitted.sum()) - H) > 1e-6:
        raise ValueError("公开三家暗手总张数校准失败")
    return base, fitted


def _bootstrap(by_room: dict[str, dict]) -> list[float]:
    """房级相关单位重采样，返回新模型减基线的平均每窗平方误差区间。"""

    ordered = sorted(by_room)
    sums = np.asarray([by_room[room]["sse_difference"] for room in ordered])
    counts = np.asarray([by_room[room]["windows"] for room in ordered])
    rng = np.random.default_rng(RNG_SEED)
    picks = rng.integers(0, len(ordered), size=(REPLICATES, len(ordered)))
    samples = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    return [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))]


def main() -> None:
    """冻结切分、重建结果盲特征、拟合开发房并一次性打开外部房误差。"""

    if OUT.exists():
        raise SystemExit("G79 证据已存在，拒绝覆盖")
    g60 = json.loads(G60.read_text(encoding="utf-8"))
    g9 = json.loads(G9.read_text(encoding="utf-8"))
    selected = {room: set(games) for room, games in g60["included"].items()}
    old = {row["room_id"] for row in g9["rooms"]}
    dev, external = set(selected) & old, set(selected) - old
    if len(dev) != 90 or len(external) != 98 or len(selected) != 188:
        raise ValueError("预登记开发/外部分房数漂移")
    windows: dict[str, list[Window]] = {"dev": [], "external": []}
    round_counts = Counter()
    game_seen = set()
    document_digests = []
    for _, room, _, game_id, doc in load_rooms():
        if room not in selected or game_id not in selected[room]:
            continue
        if game_id in game_seen:
            continue
        game_seen.add(game_id)
        document_digests.append((game_id, hashlib.sha256(json.dumps(
            doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()))
        seats = [item.get("user_id") for item in doc.get("seats") or []]
        if len(seats) != 4 or seats.count(g59.US) != 1:
            raise ValueError("冻结官方桌没有唯一我方座位")
        own_seat = seats.index(g59.US)
        metadata = c31.round_metadata(doc)
        group = "dev" if room in dev else "external"
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            if start_hands is None or len(start_hands) != 4:
                raise ValueError("冻结官方局缺完整起手")
            dealer = (metadata.get(round_no) or {}).get("dealer")
            if dealer is None:
                raise ValueError("冻结官方局缺庄位")
            snapshots = c31.reconstruct(events, start_hands, [0, 0, 0, 0], dealer)
            own = [snap for _, snap in sorted(snapshots.items()) if snap["discarder"] == own_seat]
            for position in POSITIONS:
                if len(own) >= position:
                    windows[group].append(_window(own[position - 1], room, position))
            round_counts[group] += 1
        if len(game_seen) % 100 == 0:
            print(json.dumps({"games": len(game_seen), "rounds": dict(round_counts)},
                             ensure_ascii=False), flush=True)
    expected = {game for games in selected.values() for game in games}
    if game_seen != expected or len(game_seen) != 1880 or sum(round_counts.values()) != 15_040:
        raise ValueError("G60 完整桌或单局覆盖漂移")
    if not windows["dev"] or not windows["external"]:
        raise ValueError("预定位置没有可分析的本人弃牌窗")

    beta, fit = _fit(windows["dev"])
    by_room: dict[str, dict] = defaultdict(lambda: {"windows": 0, "baseline_sse": 0.0,
                                                    "model_sse": 0.0, "sse_difference": 0.0})
    by_position: dict[str, dict] = defaultdict(lambda: {"windows": 0, "baseline_sse": 0.0,
                                                        "model_sse": 0.0})
    for window in windows["external"]:
        base, model = _predict(window, beta)
        truth = window.hidden.astype(float)
        baseline_sse = float(np.sum(np.square(truth - base)))
        model_sse = float(np.sum(np.square(truth - model)))
        row = by_room[window.room]
        row["windows"] += 1
        row["baseline_sse"] += baseline_sse
        row["model_sse"] += model_sse
        row["sse_difference"] += model_sse - baseline_sse
        position = by_position[str(window.position)]
        position["windows"] += 1
        position["baseline_sse"] += baseline_sse
        position["model_sse"] += model_sse
    if len(by_room) != 98 or sum(row["windows"] for row in by_room.values()) != len(windows["external"]):
        raise ValueError("外部房结果覆盖不全")
    overall = {key: sum(row[key] for row in by_room.values())
               for key in ("windows", "baseline_sse", "model_sse", "sse_difference")}
    overall["mean_sse_difference_per_window"] = overall["sse_difference"] / overall["windows"]
    interval = _bootstrap(by_room)
    result = {
        "schema": "g79-tile-occupancy-transfer/1", "preregistered": True,
        "source_sha256": {"g60_manifest": sha(G60), "g9_rooms": sha(G9),
                          "prereg": sha(PREREG), "script": sha(Path(__file__)),
                          "official_docs_fingerprint": hashlib.sha256(json.dumps(
                              sorted(document_digests), separators=(",", ":")
                          ).encode()).hexdigest()},
        "split": {"dev_rooms": sorted(dev), "external_rooms": sorted(external),
                  "dev_rounds": round_counts["dev"], "external_rounds": round_counts["external"],
                  "dev_windows": len(windows["dev"]),
                  "external_windows": len(windows["external"])},
        "model": {"features": FEATURES, "ridge": RIDGE,
                  "coefficients": dict(zip(FEATURES, map(float, beta))), "fit": fit},
        "external": {"overall": overall, "by_room": dict(sorted(by_room.items())),
                     "by_position": dict(sorted(by_position.items())),
                     "room_bootstrap_95": interval,
                     "rooms_model_better": sum(row["sse_difference"] < 0 for row in by_room.values()),
                     "rooms_model_worse": sum(row["sse_difference"] > 0 for row in by_room.values()),
                     "pass": overall["mean_sse_difference_per_window"] < 0 and interval[1] < 0},
        "boundary": "三家暗手牌码只用于离线标签；平方误差改善不是动作排序或完整桌收益。"
    }
    OUT.parent.mkdir(parents=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"split": result["split"], "model": result["model"],
                      "external": {key: value for key, value in result["external"].items()
                                   if key != "by_room"}}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
