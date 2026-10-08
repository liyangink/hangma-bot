"""对 R18 实见弃胡分歧，核对当时确定结算与同局官方真实结算。"""

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
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = _PROJECT_ROOT


def _audit_windows(audit_root: Path, targets: set[tuple[str, int, int]]) -> dict:
    """只读冻结 R18 v2 审计；用完整窗口键索引输入及计划。"""

    found = defaultdict(lambda: {"inputs": [], "plans": []})
    paths = sorted(audit_root.glob("slot-*/runs/*/participants/u_*/decisions.jsonl"))
    paths.extend(sorted(audit_root.glob("runs/*/participants/u_*/decisions.jsonl")))
    for path in paths:
        manifest = json.loads((path.parents[2] / "manifest.json").read_text(encoding="utf-8"))
        if manifest["payload"].get("policy_version") != "r18_integrated_positive_v2":
            continue
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            if row.get("kind") not in ("decision_input", "decision_planned"):
                continue
            payload = row.get("payload") or {}
            if row["kind"] == "decision_input":
                request = payload["request"]
                window = request["window_key"]
                item = "inputs"
                value = request
            else:
                window = payload["window"]
                item = "plans"
                value = payload["returned_plan"]
            key = (window["game_id"], window["round_no"], window["trigger_seq"])
            if key in targets:
                found[key][item].append(value)
    for key in targets:
        if len(found[key]["inputs"]) != 1 or len(found[key]["plans"]) != 1:
            raise ValueError("R18 审计窗口缺失或重复: " + str(key))
    return found


def _official_rounds(official_root: Path, game_ids: set[str]) -> dict:
    """核验官方原文 SHA 和完整桌身份，提取目标单局结算事件。"""

    found = {}
    for path in official_root.glob("dl-*/events.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        game_id = doc["game_id"]
        if game_id not in game_ids:
            continue
        source = json.loads(path.with_name("source.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source["original_sha256"] or doc.get("status") != "finished":
            raise ValueError("官方原文摘要或终态异常: " + str(path))
        if game_id in found:
            raise ValueError("同一官方桌赛重复: " + game_id)
        ended = {}
        for block in doc["blocks"]:
            if block.get("truncated"):
                raise ValueError("官方事件截断: " + game_id)
            for event in block["events"]:
                if event["type"] == "round_ended":
                    no = event["data"]["round_no"]
                    if no in ended:
                        raise ValueError("同一单局重复结算: " + game_id)
                    ended[no] = event
        if sorted(ended) != list(range(1, 9)):
            raise ValueError("非完整八局桌赛: " + game_id)
        found[game_id] = {"events": ended, "sha256": digest}
    if set(found) != game_ids:
        raise ValueError("目标官方桌赛缺失: " + str(sorted(game_ids - set(found))))
    return found


def analyze_case(audit_root: Path, official_root: Path, diff_report: Path) -> dict:
    """只比较当时确定的立即胡与实际同局结果，不推断整桌反事实。"""

    diff = json.loads(diff_report.read_text(encoding="utf-8"))
    relative = str(audit_root.relative_to(ROOT))
    matched = [room for room in diff["rooms"] if room["audit_root"] == relative]
    if len(matched) != 1:
        raise ValueError("重放报告中缺少唯一审计根: " + relative)
    arm = matched[0]["observed_arms"]["r18_integrated_positive_v2"]
    examples = arm["difference_examples"]
    if arm["counts"].get("different_top", 0) != len(examples):
        raise ValueError("重放样本截断；不能遗漏分歧")
    if any(item["r18_top"] == "hu" or item["huup_top"] != "hu" for item in examples):
        raise ValueError("输入包含非 R18 弃胡分歧")
    keys = {(x["game_id"], x["round_no"], x["trigger_seq"]) for x in examples}
    if len(keys) != len(examples):
        raise ValueError("重放分歧窗口重复")
    audits = _audit_windows(audit_root, keys)
    official = _official_rounds(official_root, {x["game_id"] for x in examples})
    cases = []
    for item in examples:
        game_id, round_no, seq = item["game_id"], item["round_no"], item["trigger_seq"]
        audit = audits[(game_id, round_no, seq)]
        request, plan = audit["inputs"][0], audit["plans"][0]
        if plan["candidates"][0]["action_key"] != item["r18_top"]:
            raise ValueError("审计首选与重放报告不符: " + game_id)
        hu = [x for x in request["rules"]["legal_candidates"] if x["action_key"] == "hu"]
        if len(hu) != 1:
            raise ValueError("合法胡候选不唯一: " + game_id)
        settlement = hu[0]["value_facts"]["immediate_settlement"]
        if settlement is None:
            raise ValueError("合法胡缺少确定结算: " + game_id)
        seat = request["observation"]["seat"]
        actual = official[game_id]["events"][round_no]
        detail = plan["candidates"][0].get("score_trace", {}).get("detail", {})
        overlays = [name for name, value in detail.items()
                    if isinstance(value, dict) and value.get("triggered") is True]
        cases.append({"game_id": game_id, "round_no": round_no, "trigger_seq": seq,
                      "seat": seat, "r18_action": item["r18_top"],
                      "immediate_hu_fan": settlement["fan"],
                      "immediate_hu_points": settlement["score_delta"][seat],
                      "actual_points": actual["data"]["scores"][seat],
                      "actual_winner_is_self": actual["seat"] == seat and not actual["data"]["draw"],
                      "actual_minus_immediate": actual["data"]["scores"][seat]
                      - settlement["score_delta"][seat],
                      "triggered_overlays": overlays,
                      "official_events_sha256": official[game_id]["sha256"]})
    distinct_hands = {(x["game_id"], x["round_no"]) for x in cases}
    return {"audit_root": relative, "official_root": str(official_root.relative_to(ROOT)),
            "difference_report": str(diff_report.relative_to(ROOT)),
            "windows": len(cases), "distinct_hands": len(distinct_hands), "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=Path, action="append", required=True)
    parser.add_argument("--official-root", type=Path, action="append", required=True)
    parser.add_argument("--difference-report", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sizes = {len(args.audit_root), len(args.official_root), len(args.difference_report)}
    if len(sizes) != 1:
        parser.error("三种路径必须逐项一一对应")
    cases = [analyze_case(a.resolve(), o.resolve(), d.resolve()) for a, o, d in
             zip(args.audit_root, args.official_root, args.difference_report)]
    result = {"schema": "r18-real-hu-deferral-observation/1", "cases": cases,
              "limitation": "实际续打结果与当时立即胡确定结算仅为同局描述；改变动作会改变后续牌墙和整桌轨迹，不能视为随机试验或独立窗口样本。"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
