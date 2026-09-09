#!/usr/bin/env python3
"""把最新排行榜快照打标到本地牌谱对手池，生成训练可消费的对手标注。

输入：
1. datasets/leaderboard/snapshots/<ts>/，由 scripts/fetch_leaderboard.py 产生；
2. --records 牌谱根目录（可重复给出）：默认训练池 datasets/derived/auto-match-rooms-20260908；
   兼容两种布局——训练池 official/<房>/official/dl-*/events.json(.gz) 与
   会话目录 official/dl-*/events.json(.gz)。

打标策略（只做正向标签；当日/当周实时榜滚动快，凌晨切期后为空会造成"强手误标
非在榜"，因此不进入标签）：
- 总榜（period=all）top：rank ≤16 → 「总榜16强」，17..32 → 「总榜32强」；
- period=today 响应的 prev.top（昨日榜）→ 「昨日榜前4」；
- period=week 响应的 prev.top（上周榜）→ 「上周榜前4」；
- best-game / huge-win top 行（若官方返回 user_id 字段）→
  「单场分榜32强」/「胡大牌榜32强」；行无 user_id 时该榜自动跳过并在输出里提示；
- today.top / week.top 只写入 detail 供参考（键 today_top / week_top），不生成标签。

产物（--out，默认 datasets/leaderboard/）：
- opponent-tags.json：user_id → {name, tags, detail}，附快照血缘；名字优先取榜单行
  的官方昵称，缺省回退本地牌谱昵称；
- game-annotations.jsonl：每场一行
  {game_id, room_id, batch, source, seats: [{seat, user_id, name, is_me, tags}], strong_opponent_count}。
  训练侧用 hands 行的 game_key.game_id 与本文件 game_id 关联（hands 行本身不含
  user_id，牌谱 events.json 的 seats 才是座位→身份映射的唯一来源）。

退出码：0 正常；2 找不到快照或牌谱；3 硬错误（参数/数据形状）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_ROOT = SCRIPT_ROOT / "datasets" / "leaderboard" / "snapshots"
DEFAULT_RECORDS = SCRIPT_ROOT / "datasets" / "derived" / "auto-match-rooms-20260908"
DEFAULT_OUT = SCRIPT_ROOT / "datasets" / "leaderboard"
DEFAULT_MY_USER_ID = "u_13495c3d79c8"  # 与 watchdog_cycle.ME 一致：全局自由赛身份

# 标签展示顺序（强→弱）
TAG_ORDER = {"总榜16强": 0, "总榜32强": 1, "昨日榜前4": 2, "上周榜前4": 3,
             "单场分榜32强": 4, "胡大牌榜32强": 5}
PERIOD_FILES = {"all": "leaderboard-all.json", "today": "leaderboard-today.json",
                "week": "leaderboard-week.json"}
BOARD_FILES = {"best-game": ("leaderboard-best-game.json", "单场分榜32强"),
               "huge-win": ("leaderboard-huge-win.json", "胡大牌榜32强")}
RECORD_GLOBS = ("official/*/official/dl-*/events.json", "official/*/official/dl-*/events.json.gz",
                "official/dl-*/events.json", "official/dl-*/events.json.gz")


def find_row_arrays(obj, path: str = "$"):
    """递归找出“元素为含 user_id 字典的数组”，返回 [(json_pointer 风格路径, rows)]。

    官方榜单响应的精确形状尚未实捕（首次人工授权后由本函数输出的解释路径顺带核对），
    因此不写死键名：任何位置出现的 user_id 行数组都会被发现，再按路径尾部语义归类。
    """
    found = []
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj) and any("user_id" in x for x in obj):
            found.append((path, obj))
        for i, item in enumerate(obj):
            found.extend(find_row_arrays(item, f"{path}[{i}]"))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            found.extend(find_row_arrays(value, f"{path}.{key}"))
    return found


def rows_for(rows_found, suffix: str):
    """按路径尾缀取行数组（如 .top / .prev.top）；未命中时返回空列表。"""
    out = []
    for path, rows in rows_found:
        if path.endswith(suffix):
            out.extend(rows)
    return out


def sort_tags(tags) -> list:
    return sorted(set(tags), key=lambda t: TAG_ORDER.get(t, 99))


def load_json_any(path: Path):
    """读明文或 gzip JSON；文件不存在返回 None。"""
    if not path.is_file():
        return None
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def build_tags(snap_dir: Path) -> dict:
    """从快照构建 {user_id: {name, tags, detail}}；只产生稳定窗口正向标签。"""
    tags: dict = {}

    def ensure(uid: str) -> dict:
        return tags.setdefault(uid, {"name": None, "tags": [], "detail": {}})

    interpreted = []   # (文件, 路径, 行数) 解释轨迹，供首捕核对形状
    skipped = []       # 发现了数组但没用的路径（如 today.top）

    for period, fname in PERIOD_FILES.items():
        doc = load_json_any(snap_dir / fname)
        if doc is None:
            continue
        found = find_row_arrays(doc)
        for path, rows in found:
            interpreted.append((fname, path, len(rows)))
        # 当前窗口 top：只有 all 进标签；today/week 只进 detail 参考
        for row in rows_for(found, ".top"):
            uid = row.get("user_id")
            if not uid:
                continue
            entry = ensure(uid)
            entry["name"] = row.get("name") or entry["name"]
            detail = {"rank": row.get("rank"), "score": row.get("score"),
                      "rooms": row.get("rooms"), "firsts": row.get("firsts")}
            if period == "all":
                entry["detail"]["all_top"] = detail
                rank = row.get("rank")
                if isinstance(rank, int):
                    if rank <= 16:
                        entry["tags"].append("总榜16强")
                    elif rank <= 32:
                        entry["tags"].append("总榜32强")
            else:
                entry["detail"][f"{period}_top"] = detail
                skipped.append((fname, path))
        # 上一期前四（v27 prev 键）：稳定历史窗口，进标签
        prev_tag = {"today": "昨日榜前4", "week": "上周榜前4"}.get(period)
        if prev_tag:
            for row in rows_for(found, ".prev.top"):
                uid = row.get("user_id")
                if not uid:
                    continue
                entry = ensure(uid)
                entry["name"] = row.get("name") or entry["name"]
                entry["tags"].append(prev_tag)
                entry["detail"][f"{period}_prev_top"] = {
                    "rank": row.get("rank"), "score": row.get("score")}

    for board, (fname, tag) in BOARD_FILES.items():
        doc = load_json_any(snap_dir / fname)
        if doc is None:
            continue
        found = find_row_arrays(doc)
        if not found:
            print(f"提示：{fname} 未发现含 user_id 的行（官方行结构待首捕核对），跳过 {tag}")
            continue
        for path, rows in found:
            interpreted.append((fname, path, len(rows)))
            for row in rows:
                uid = row.get("user_id")
                if not uid:
                    continue
                entry = ensure(uid)
                entry["name"] = row.get("name") or entry["name"]
                entry["tags"].append(tag)
                entry["detail"][board] = {
                    k: row.get(k) for k in ("score", "detail", "count",
                                            "room_id", "game_id", "wins") if k in row}

    for entry in tags.values():
        entry["tags"] = sort_tags(entry["tags"])
    build_tags.last_interpreted = interpreted
    build_tags.last_skipped = skipped
    return tags


def scan_records(roots) -> tuple[dict, dict]:
    """扫描牌谱，返回 ({game_id: 记录}, {user_id: 本地昵称})。game_id 去重取先见。"""
    games: dict = {}
    local_names: dict = {}
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            print(f"警告：牌谱目录不存在，跳过：{root}")
            continue
        for pattern in RECORD_GLOBS:
            for path in sorted(root.glob(pattern)):
                try:
                    doc = load_json_any(path)
                except (OSError, json.JSONDecodeError, gzip.BadGzipFile) as exc:
                    print(f"警告：牌谱解析失败，跳过 {path}：{exc}")
                    continue
                game_id = doc.get("game_id")
                if not game_id or game_id in games:
                    continue
                seats = [{"seat": i, "user_id": s.get("user_id"), "name": s.get("name")}
                         for i, s in enumerate(doc.get("seats") or [])]
                for s in seats:
                    if s["user_id"] and s["name"] and s["user_id"] not in local_names:
                        local_names[s["user_id"]] = s["name"]
                games[game_id] = {
                    "game_id": game_id,
                    "room_id": doc.get("room_id"),
                    "batch": doc.get("batch"),
                    "source": str(path.relative_to(SCRIPT_ROOT))
                    if path.is_relative_to(SCRIPT_ROOT) else str(path),
                    "seats": seats,
                }
    return games, local_names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", help="快照目录（默认取 snapshots/ 下最新一个）")
    parser.add_argument("--records", action="append", default=[],
                        help="牌谱根目录，可重复（默认训练池 datasets/derived/auto-match-rooms-20260908）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="产物输出目录")
    parser.add_argument("--my-user-id", default=DEFAULT_MY_USER_ID, help="我方 user_id（不参与对手统计）")
    args = parser.parse_args(argv)

    snap_dir = Path(args.snapshot) if args.snapshot else None
    if snap_dir is None:
        if not DEFAULT_SNAPSHOT_ROOT.is_dir():
            print(f"无任何快照：先运行 .venv/bin/python3 scripts/fetch_leaderboard.py（需门户登录态）")
            return 2
        dirs = sorted(d for d in DEFAULT_SNAPSHOT_ROOT.iterdir() if d.is_dir())
        if not dirs:
            print("snapshots/ 下没有快照目录")
            return 2
        snap_dir = dirs[-1]
    if not (snap_dir / "snapshot.json").is_file():
        print(f"!! 快照目录缺少 snapshot.json：{snap_dir}")
        return 2

    meta = json.loads((snap_dir / "snapshot.json").read_text(encoding="utf-8"))
    records = args.records or [str(DEFAULT_RECORDS)]
    games, local_names = scan_records(records)
    if not games:
        print(f"!! 未扫到任何牌谱（roots={records}）")
        return 2

    tags = build_tags(snap_dir)
    for uid, entry in tags.items():
        entry["name"] = entry["name"] or local_names.get(uid)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    opponent_tags = {
        "generated_at_unix_ms": int(time.time() * 1000),
        "snapshot_dir": str(snap_dir.relative_to(SCRIPT_ROOT)) if snap_dir.is_relative_to(SCRIPT_ROOT) else str(snap_dir),
        "as_of_captured_at_unix_ms": meta.get("captured_at_unix_ms"),
        "guide_version": meta.get("guide_version"),
        "my_user_id": args.my_user_id,
        "tag_policy": "正向标签：总榜all top32(≤16另标16强) + today.prev/week.prev 前四；"
                      "当日/当周实时榜只入 detail 不入标签（防切期空榜误标）",
        "tags": tags,
    }
    (out_dir / "opponent-tags.json").write_text(
        json.dumps(opponent_tags, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")

    annotated = 0
    tag_game_counts: dict = {}
    with (out_dir / "game-annotations.jsonl").open("w", encoding="utf-8") as fh:
        for game_id in sorted(games):
            game = games[game_id]
            strong = 0
            for seat in game["seats"]:
                uid = seat.get("user_id")
                seat_tags = tags.get(uid, {}).get("tags", []) if uid else []
                seat["tags"] = seat_tags
                seat["is_me"] = uid == args.my_user_id
                if seat_tags and not seat["is_me"]:
                    strong += 1
                for t in seat_tags:
                    tag_game_counts[t] = tag_game_counts.get(t, 0) + 1
            game["strong_opponent_count"] = strong
            if strong:
                annotated += 1
            fh.write(json.dumps(game, ensure_ascii=False) + chr(10))

    print(f"快照：{snap_dir.name}（captured {meta.get('captured_at_unix_ms')}，"
          f"guide v{meta.get('guide_version')}），解释路径 "
          f"{len(build_tags.last_interpreted)} 组")
    for fname, path, n in build_tags.last_interpreted[:12]:
        print(f"  {fname} {path}：{n} 行")
    tagged_users = {u for u, e in tags.items() if e["tags"]}
    print(f"榜单标签用户 {len(tagged_users)} 个：")
    for uid in sorted(tagged_users, key=lambda u: (TAG_ORDER.get(tags[u]['tags'][0], 99), u)):
        entry = tags[uid]
        print(f"  {uid} {entry['name'] or '(无名)'}：{'、'.join(entry['tags'])}")
    if build_tags.last_skipped:
        print(f"参考未打标（滚动窗口）：{len(build_tags.last_skipped)} 组路径（today/week 实时榜）")
    print(f"牌谱 {len(games)} 场，其中 {annotated} 场含榜上对手"
          f"（{annotated * 100.0 / len(games):.1f}%）；"
          + "、".join(f"{t}×{tag_game_counts[t]}" for t in sort_tags(tag_game_counts)))
    print(f"产物：{out_dir / 'opponent-tags.json'}、{out_dir / 'game-annotations.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
