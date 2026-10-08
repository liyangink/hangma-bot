"""用真实事件链估算可收紧鸣牌兴趣预过滤的请求上界。

只输出聚合数与静态删除请求后的到达峰值。静态删除并不会重放后续事件
或服务器计时，不能作为实网性能收益；原始牌谱与手牌不写入结果。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

from hangma_bot.adapters.official.claim_interest import discard_interesting
from hangma_bot.adapters.official.dto import parse_snapshot
from hangma_bot.adapters.official.projector import observation
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.config import RuleConfig


def exact_chi_pair(tile: str, hand: list[str]) -> bool:
    """只用于审计：手牌超集含一副完整吃搭时才认为可能吃。"""
    if not isinstance(tile, str) or len(tile) != 2 or tile[1] not in "wbt" or tile[0] not in "123456789":
        return False
    number = int(tile[0])
    held = set(hand)
    return any(
        1 <= low <= 7 and all(
            "{0}{1}".format(n, tile[1]) in held
            for n in (low, low + 1, low + 2) if n != number
        )
        for low in (number - 2, number - 1, number)
    )


def rolling_counts(times: list[float]) -> list[int]:
    pending: deque[float] = deque()
    counts = []
    for now in sorted(times):
        while pending and pending[0] <= now - 1.05:
            pending.popleft()
        pending.append(now)
        counts.append(len(pending))
    return counts


def p95(values: list[int]) -> int | None:
    if not values:
        return None
    values = sorted(values)
    return values[(95 * len(values) + 99) // 100 - 1]


def _read_requests(run: Path) -> dict[str, list[dict]]:
    by_game: dict[str, list[dict]] = defaultdict(list)
    for path in (run / "participants").glob("*/raw/t_*.jsonl"):
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                payload = row.get("payload") or {}
                if not str(payload.get("endpoint") or "").endswith("/state"):
                    continue
                timing = payload.get("request_timing") or {}
                queued = timing.get("queued_at_monotonic")
                if not isinstance(queued, (float, int)):
                    continue
                try:
                    raw = json.loads(payload.get("raw") or "{}")
                except (TypeError, ValueError):
                    raw = {}
                by_game[path.stem].append({
                    "queued": queued, "status": payload.get("http_status"),
                    "seq_requested": payload.get("seq_requested"),
                    "raw": raw,
                })
    for rows in by_game.values():
        rows.sort(key=lambda item: item["queued"])
    return by_game


def analyze_slot(run: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text())["payload"]
    rules = HangmaRules(RuleConfig(
        manifest["ruleset_version"], manifest["base_score"],
        bool(manifest["you_cai_bi_kao"])))
    by_game = _read_requests(run)
    counts = Counter()
    all_times = []
    discard_saved = set()
    chi_saved = set()
    for game, rows in by_game.items():
        all_times.extend(item["queued"] for item in rows)
        previous_snapshot = None
        own_draws: list[str] | None = []
        last_discard = None
        for index, current in enumerate(rows[:-1]):
            raw = current["raw"]
            if raw.get("snapshot"):
                previous_snapshot = raw["snapshot"]
                own_draws = []
            events = raw.get("events") or ()
            for event in events:
                if event.get("type") == "round_ended":
                    last_discard = None
                elif event.get("type") == "tile_discarded":
                    last_discard = event
                elif (previous_snapshot and event.get("type") == "tile_drawn"
                      and event.get("seat") == previous_snapshot.get("seat")):
                    if event.get("tile") and own_draws is not None:
                        own_draws.append(event["tile"])
                    else:
                        own_draws = None
            following = rows[index + 1]
            snapshot = following["raw"].get("snapshot") or {}
            if (not events or following["status"] != 200
                    or following["seq_requested"] != 0 or not snapshot):
                continue
            types = {event.get("type") for event in events}
            if previous_snapshot is None or own_draws is None:
                counts["unproven_prestate"] += 1
                continue
            me = previous_snapshot.get("seat")
            if not isinstance(me, int):
                counts["unproven_prestate"] += 1
                continue
            hand = list(previous_snapshot.get("my_hand") or ())
            if previous_snapshot.get("drawn_tile"):
                hand.append(previous_snapshot["drawn_tile"])
            hand.extend(own_draws)
            protected = bool((previous_snapshot.get("god") or {}).get("catch_play"))
            if len(events) == 1 and types == {"tile_discarded"}:
                counts["single_discard_to_snapshot"] += 1
                event = events[0]
                if following["raw"].get("seq") != event.get("seq"):
                    counts["discard_snapshot_advanced"] += 1
                    continue
                counts["same_seq_discard_snapshot"] += 1
                source, tile = event.get("seat"), event.get("tile")
                if not isinstance(source, int) or not isinstance(tile, str):
                    continue
                old = discard_interesting(
                    my_seat=me, discarder_seat=source, tile_code=tile,
                    hand_codes=hand)
                proposed = (hand.count(tile) >= 2 or
                            (source == (me - 1) % 4 and exact_chi_pair(tile, hand)))
                forced = (protected or tile == "白" or
                          (event.get("data") or {}).get("catch_play") is True)
                if old and not proposed and not forced:
                    counts["discard_filter_candidate"] += 1
                    analysis = rules.analyze(observation(parse_snapshot(
                        snapshot, following["raw"]["seq"]), (), game))
                    if analysis.issues or any(c.action_key != "pass" for c in analysis.legal_candidates):
                        counts["discard_candidate_counterexample"] += 1
                    else:
                        discard_saved.add((game, index + 1))
            if types == {"timeout"} and snapshot.get("phase") == "response_chi":
                counts["timeout_to_chi_snapshot"] += 1
                if following["raw"].get("seq") != max(
                    (event.get("seq", -1) for event in events), default=-1
                ):
                    counts["chi_snapshot_advanced"] += 1
                    continue  # 后续事件可能已改变窗口，不能用该快照反证当前标记
                if (last_discard is None or
                        snapshot.get("last_discard") != last_discard.get("tile")):
                    counts["chi_unproven_trigger"] += 1
                    continue
                source, tile = last_discard.get("seat"), last_discard.get("tile")
                if not isinstance(source, int) or not isinstance(tile, str):
                    continue
                old = discard_interesting(
                    my_seat=me, discarder_seat=source, tile_code=tile,
                    hand_codes=hand)
                proposed = source == (me - 1) % 4 and exact_chi_pair(tile, hand)
                if old and not proposed and not protected:
                    counts["chi_filter_conditional_candidate"] += 1
                    analysis = rules.analyze(observation(parse_snapshot(
                        snapshot, following["raw"]["seq"]), (), game))
                    if analysis.issues or any(c.action_key != "pass" for c in analysis.legal_candidates):
                        counts["chi_candidate_counterexample"] += 1
                    else:
                        chi_saved.add((game, index + 1))
    removed = discard_saved | chi_saved
    kept = [item["queued"] for game, rows in by_game.items()
            for index, item in enumerate(rows) if (game, index) not in removed]
    before = rolling_counts(all_times)
    after = rolling_counts(kept)
    return {
        "requests": len(all_times), "counts": dict(counts),
        "strict_discard_candidate": len(discard_saved),
        "conditional_chi_candidate": len(chi_saved),
        "static_counterfactual": {
            "removed": len(removed),
            "rolling_1_05s_p95_before": p95(before),
            "rolling_1_05s_p95_after": p95(after),
            "rolling_1_05s_peak_before": max(before),
            "rolling_1_05s_peak_after": max(after),
            "arrivals_above_16_before": sum(n > 16 for n in before),
            "arrivals_above_16_after": sum(n > 16 for n in after),
        },
    }


def analyze(root: Path) -> dict:
    result = {}
    for slot in sorted(root.glob("slot-*")):
        runs = list((slot / "runs").glob("run-*"))
        if runs:
            run = max(runs, key=lambda path: path.stat().st_mtime_ns)
            result[slot.name] = analyze_slot(run)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(analyze(args.audit_root), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
