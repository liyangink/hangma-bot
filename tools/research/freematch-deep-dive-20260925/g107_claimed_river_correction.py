#!/usr/bin/env python3
"""G107：先核官方被鸣牌离河口径，再保留原结果并重算 G85/G104。"""

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
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g103_official_route_horizon as g103
import g104_post_root_claim_route as g104
import g85_immediate_post_claim_discard as g85
from hangma_bot.hangma.interface import ValueAnalysisLimits


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g107-claimed-river-correction-20260928')
OLD_G104 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g104-post-root-claim-route-20260928/rows.jsonl.gz')
OLD_G85 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g85-immediate-post-claim-discard-20260928/result.json')


def sha(path: Path) -> str:
    """保存原证据、辅助函数和纠正程序的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def river_removed(pre: dict, post: dict) -> bool:
    """官方后续快照必须恰好从供牌者牌河尾部移走被鸣的同一张牌。"""
    discarder = pre["discarder"]
    before = pre["rivers"][discarder]
    after = post["rivers"][discarder]
    return bool(before and before[-1] == pre["tile"] and before[:-1] == after)


def check_g104_regime() -> int:
    """核对 G104 50 个已发生吃碰的官方前后公开牌河。"""
    import gzip

    with gzip.open(OLD_G104, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    claims = [row for row in rows if row["status"] == "verified"]
    if len(claims) != 50:
        raise ValueError("G104 官方吃碰数漂移")
    games, digest = g103.official_games(g103.selected_roots())
    old = json.loads((_project_file(_PROJECT_ROOT, OLD_G104.parent / "result.json")).read_text(encoding="utf-8"))
    g103_result = json.loads((g103.OUT / "result.json").read_text(encoding="utf-8"))
    if digest != g103_result["official_game_canonical_sha256"]:
        raise ValueError("G104 官方桌源摘要漂移")
    if old["claim_events"] != 60:
        raise ValueError("G104 原始总鸣牌数漂移")
    contexts = {}
    for row in claims:
        game_id = row["game_id"]
        if game_id not in contexts:
            contexts[game_id] = g104.round_contexts(games[game_id])
        _, snapshots = contexts[game_id][row["round_no"]]
        if not river_removed(
            snapshots[row["trigger_discard_seq"]],
            snapshots[row["followup_discard_seq"]],
        ):
            raise ValueError("G104 有吃碰不属于被鸣牌离河口径")
    return len(claims)


def check_g85_regime() -> int:
    """核对 G85 88 个已发生强手吃碰的官方前后公开牌河。"""
    rows = json.loads(OLD_G85.read_text(encoding="utf-8"))["rows"]
    if len(rows) != 88:
        raise ValueError("G85 官方吃碰数漂移")
    by_round: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in rows:
        by_round[(row["game_id"], row["round_no"])].append(row)
    found = set()
    for _, _, _, game_id, doc in g85.load_rooms():
        if game_id not in {row["game_id"] for row in rows}:
            continue
        scores = [0, 0, 0, 0]
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in g85.anatomy.round_blocks(doc):
            targets = by_round.get((game_id, round_no), ())
            if targets:
                snapshots = c31.reconstruct(
                    events, start_hands, scores, metadata[round_no]["dealer"],
                )
                positions = {event["seq"]: index for index, event in enumerate(events)}
                for row in targets:
                    tile, status = g85.official_followup(
                        events, row["discard_seq"], row["seat"], row["accepted_key"],
                    )
                    if status != "matched" or tile != row["actual_followup"]:
                        raise ValueError("G85 官方跟打身份漂移")
                    anchor = positions[row["discard_seq"]]
                    claim = next(
                        index for index in range(anchor + 1, len(events))
                        if events[index]["type"] not in ("pass", "timeout")
                    )
                    following = events[claim + 1]
                    if not river_removed(
                        snapshots[row["discard_seq"]], snapshots[following["seq"]],
                    ):
                        raise ValueError("G85 有吃碰不属于被鸣牌离河口径")
                    found.add((game_id, round_no, row["discard_seq"]))
            ended = next(event for event in events if event["type"] == "round_ended")
            scores = [a + b for a, b in zip(scores, ended["data"]["scores"])]
    if len(found) != 88:
        raise ValueError("G85 官方房间覆盖不完整")
    return len(found)


def compare_g104() -> dict:
    """按同一官方鸣牌键比较修正前后条件胡容量。"""
    import gzip

    def read(path: Path) -> dict[tuple, dict]:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        return {(row["game_id"], row["round_no"], row["claim_seq"]): row
                for row in rows if row["status"] == "verified"}

    old = read(OLD_G104)
    new = read(_project_file(_PROJECT_ROOT, OUT / "g104_corrected" / "rows.jsonl.gz"))
    if len(old) != len(new) or set(old) != set(new):
        raise ValueError("G104 修正前后官方鸣牌键漂移")
    changes = []
    high_entry_changed = 0
    for key in sorted(old):
        before, after = old[key]["entry"], new[key]["entry"]
        if old[key]["followup_action"] != new[key]["followup_action"]:
            raise ValueError("G104 修正前后实际跟打动作漂移")
        if (before["high_capacity"] > 0) != (after["high_capacity"] > 0):
            high_entry_changed += 1
        if before != after:
            changes.append({"key": key, "claim_kind": old[key]["claim_kind"],
                            "before": before, "after": after})
    if high_entry_changed:
        raise ValueError("G104 修正改变高番入口存在性，须重审行动链裁定")
    return {"checked": len(old), "changed_rows": len(changes),
            "high_entry_presence_changed": high_entry_changed, "changes": changes}


def reconcile_g104_routes() -> int:
    """官方 50 次鸣牌的响应分支与修正后跟打逐牌码条件胡必须相同。"""
    import gzip

    with gzip.open(OLD_G104, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if json.loads(line)["status"] == "verified"]
    games, _ = g103.official_games(g103.selected_roots())
    contexts = {}
    limits = ValueAnalysisLimits(max_expansions=8192, max_routes_per_candidate=512)

    def useful_map(routes, followup):
        result = {}
        for route in routes:
            if route.followup_discard != followup:
                continue
            for tile in route.useful_tiles:
                if tile.code in result:
                    raise ValueError("同一次自摸牌码在条件结算中重复")
                result[tile.code] = (
                    route.conditional_settlement.fan, tile.remaining_estimate,
                    route.conditional_settlement.score_delta,
                )
        return result

    for row in rows:
        game_id = row["game_id"]
        if game_id not in contexts:
            contexts[game_id] = g104.round_contexts(games[game_id])
        _, snapshots = contexts[game_id][row["round_no"]]
        observation = c31.build_observation(
            snapshots[row["trigger_discard_seq"]], row["seat"],
            "response_" + row["claim_kind"], game_id, row["round_no"],
        )
        before = c31.RULES.analyze(observation, value_limits=limits)
        claim = next(
            item for item in before.legal_candidates
            if item.action_key == row["accepted_action"]
        )
        post = c31.post_claim_observation(observation, claim.action)
        if post is None:
            raise ValueError("G104 纠正后跟打观察构造失败")
        after = c31.RULES.analyze(post, value_limits=limits)
        discard = next(
            item for item in after.legal_candidates
            if item.action_key == row["followup_action"]
        )
        if claim.value_facts is None or discard.value_facts is None:
            raise ValueError("G104 纠正对账缺条件价值事实")
        followup = row["followup_action"].split(":", 1)[1]
        left = useful_map(claim.value_facts.routes, followup)
        right = useful_map(discard.value_facts.routes, None)
        if left != right:
            raise ValueError(
                f"G104 鸣前分支和鸣后跟打逐牌码不一致：{game_id} "
                f"{row['round_no']} {row['claim_seq']}"
            )
    return len(rows)


def compare_g85() -> dict:
    """按同一强手鸣牌键比较修正前后普通型形状结论。"""
    old = json.loads(OLD_G85.read_text(encoding="utf-8"))
    new = json.loads((_project_file(_PROJECT_ROOT, OUT / "g85_corrected" / "result.json")).read_text(encoding="utf-8"))
    def index(doc: dict) -> dict[tuple, dict]:
        return {(row["game_id"], row["round_no"], row["discard_seq"]): row
                for row in doc["rows"]}
    before, after = index(old), index(new)
    if len(before) != 88 or set(before) != set(after):
        raise ValueError("G85 修正前后官方鸣牌键漂移")
    changes = []
    for key in sorted(before):
        left, right = before[key], after[key]
        for field in ("actual_followup", "parent_best_followup", "legal_followup_count"):
            if left[field] != right[field]:
                raise ValueError("G85 修正前后动作身份或合法分支漂移")
        if left["actual_facts"] != right["actual_facts"] or left["best_facts"] != right["best_facts"]:
            changes.append({"key": key, "before_best": left["best_facts"],
                            "after_best": right["best_facts"],
                            "before_actual": left["actual_facts"],
                            "after_actual": right["actual_facts"]})
    protected = [row for row in new["rows"]
                 if row["actual_followup"] != row["parent_best_followup"]
                 and row["actual_facts"]["known"] and row["best_facts"]["known"]
                 and row["actual_facts"]["standard_shanten"] is not None
                 and row["best_facts"]["standard_shanten"] is not None
                 and row["actual_facts"]["standard_shanten"] <= row["best_facts"]["standard_shanten"]]
    more_codes = sum(row["actual_facts"]["standard_codes"] > row["best_facts"]["standard_codes"]
                     for row in protected)
    more_capacity = sum(row["actual_facts"]["standard_capacity"] > row["best_facts"]["standard_capacity"]
                        for row in protected)
    if len(protected) != 42 or more_codes or more_capacity:
        raise ValueError("G85 普通型向听保护切片结论改变，须重审停线")
    return {"checked": len(before), "changed_rows": len(changes),
            "ordinary_shanten_protected": len(protected),
            "protected_more_codes": more_codes,
            "protected_more_capacity": more_capacity,
            "old_summaries": old["summaries"], "corrected_summaries": new["summaries"],
            "changes": changes}


def main() -> None:
    """验证口径后运行原冻结脚本的纠正版，不覆盖任何旧证据。"""
    existing = (
        {path.relative_to(OUT).as_posix() for path in OUT.rglob("*") if path.is_file()}
        if OUT.exists() else set()
    )
    partial_g104 = {"g104_corrected/result.json", "g104_corrected/rows.jsonl.gz"}
    if existing and existing != partial_g104:
        raise FileExistsError("G107 修正输出已存在，拒绝覆盖")
    g104_count = check_g104_regime()
    g85_count = check_g85_regime()
    OUT.mkdir(parents=True, exist_ok=True)
    original = c31.post_claim_observation

    def corrected(observation, action):
        """已逐事件核准当前平台移走被鸣牌后才启用该分支。"""
        return original(observation, action, remove_claimed_from_river=True)

    c31.post_claim_observation = corrected
    g104.OUT = _project_file(_PROJECT_ROOT, OUT / "g104_corrected")
    g85.OUT = _project_file(_PROJECT_ROOT, OUT / "g85_corrected" / "result.json")
    with redirect_stdout(io.StringIO()):
        if not existing:
            g104.main()
        else:
            resumed = json.loads((g104.OUT / "result.json").read_text(encoding="utf-8"))
            if (resumed["claim_events"] != 60 or
                    resumed["input_sha256"]["c31_reconstruction"] != sha(_project_file(_PROJECT_ROOT, HERE / "c31_action_layer_gap.py"))):
                raise ValueError("G107 既有部分 G104 证据身份不符，拒绝续跑")
        g85.main()
    g104_diff = compare_g104()
    g85_diff = compare_g85()
    reconciled = reconcile_g104_routes()
    result = {
        "schema": "g107-claimed-river-correction/1",
        "boundary": "仅纠正已核准被鸣牌离河的离线跟打观察；不改生产规则或原证据",
        "official_river_removed": {"g104": g104_count, "g85": g85_count},
        "g104_response_vs_corrected_followup_exact": reconciled,
        "input_sha256": {"g104_rows": sha(OLD_G104), "g85_result": sha(OLD_G85),
                         "c31_helper": sha(_project_file(_PROJECT_ROOT, HERE / "c31_action_layer_gap.py")),
                         "script": sha(Path(__file__))},
        "g104": g104_diff, "g85": g85_diff,
    }
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"river_removed": result["official_river_removed"],
                      "g104_exact_route_reconciliation": reconciled,
                      "g104_changed": g104_diff["changed_rows"],
                      "g104_high_presence_changed": g104_diff["high_entry_presence_changed"],
                      "g85_changed": g85_diff["changed_rows"],
                      "g85_corrected_counts": {
                          peer: doc["counts"] for peer, doc in g85_diff["corrected_summaries"].items()
                      }}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
