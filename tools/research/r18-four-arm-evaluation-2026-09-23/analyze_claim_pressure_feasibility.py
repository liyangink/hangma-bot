"""只读 R18 自由赛审计，核对公开副露压力下的合法鸣牌与过牌事实。"""

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
from collections import Counter, defaultdict
import json
from pathlib import Path


ROOT = _PROJECT_ROOT
DEFAULT_AUDIT = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-auto-match-campaign-20260923/audit")
POLICY = "r18_integrated_positive_v2"
RELEASE_ID = "e82f904c2c1fb70beea3f195110c8b2db0648971ed3eaa9bfcbed1b6543de486"


def _request_summary(request: dict) -> dict | None:
    """从玩家可见观察和规则候选提取必要字段，不读取赛后暗手。"""

    observation = request["observation"]
    if observation["phase"] not in ("response_chi", "response_peng"):
        return None
    legal = {row["action_key"]: row["facts"] for row in request["rules"]["legal_candidates"]}
    claims = {key: fact for key, fact in legal.items()
              if key.startswith(("chi:", "peng:"))}
    if not claims:
        return None
    seat = observation["seat"]
    melds = observation["melds"]
    wealth = observation["rule_state"]["wealth_god"]
    return {
        "phase": observation["phase"],
        "game_id": observation["game_id"],
        "round_no": observation["round_no"],
        "wealth_count": observation["my_hand"].count(wealth),
        "own_meld_count": len(melds[seat]),
        "max_opponent_meld_count": max(len(row) for other, row in enumerate(melds)
                                        if other != seat),
        "pass_fact": legal.get("pass"),
        "claim_facts": claims,
    }


def analyze(audit_root: Path) -> dict:
    """逐决策匹配输入与计划；一个单局的多次响应不能当独立样本。"""

    counts: dict[str, Counter] = defaultdict(Counter)
    hands: dict[str, set[tuple[str, int]]] = defaultdict(set)
    rooms: dict[str, set[str]] = defaultdict(set)
    runs = 0
    for manifest_path in sorted(audit_root.glob("runs/*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["payload"]
        if manifest.get("policy_version") != POLICY:
            continue
        if (manifest.get("policy_release") or {}).get("release_package_id") != RELEASE_ID:
            raise ValueError("R18 v2 发布包身份不一致: " + str(manifest_path))
        runs += 1
        decisions_paths = list(manifest_path.parent.glob("participants/u_*/decisions.jsonl"))
        if len(decisions_paths) != 1:
            raise ValueError("R18 决策审计身份不唯一: " + str(manifest_path.parent))
        inputs: dict[tuple[str, int], dict | None] = {}
        for line in decisions_paths[0].open(encoding="utf-8"):
            row = json.loads(line)
            payload = row.get("payload") or {}
            if row.get("kind") == "decision_input":
                request = payload["request"]
                key = (request["decision_id"], len(request.get("rejected_attempts") or []) + 1)
                if key in inputs:
                    raise ValueError("决策输入重复: " + str(key))
                inputs[key] = _request_summary(request)
                continue
            if row.get("kind") != "decision_planned":
                continue
            plan = payload.get("returned_plan") or {}
            if not plan.get("candidates"):
                continue
            key = (plan["decision_id"], plan["revision"])
            if key not in inputs:
                raise ValueError("决策计划缺输入: " + str(key))
            summary = inputs.pop(key)
            if summary is None:
                continue
            pressure = "opponent_melds_ge2" if summary["max_opponent_meld_count"] >= 2 \
                else "opponent_melds_lt2"
            top = plan["candidates"][0]["action_key"]
            category = "selected_pass" if top == "pass" else "selected_chi_peng" \
                if top.startswith(("chi:", "peng:")) else "selected_gang" \
                if top.startswith("gang:") else "selected_other"
            base = counts[pressure]
            base["legal_claim_windows"] += 1
            base[category] += 1
            phase_key = pressure + "/" + summary["phase"]
            counts[phase_key]["legal_claim_windows"] += 1
            counts[phase_key][category] += 1
            if category != "selected_pass":
                continue
            pass_fact = summary["pass_fact"] or {}
            seven = pass_fact.get("seven_pairs_shanten_after")
            p84_base = (summary["own_meld_count"] == 0
                        and summary["wealth_count"] >= 2
                        and type(seven) is int and seven <= 1)
            if p84_base:
                base["pass_excluded_p84_base"] += 1
                continue
            base["pass_outside_p84_base"] += 1
            standard = pass_fact.get("standard_shanten_after")
            combined = pass_fact.get("shanten_after")
            if (pass_fact.get("completeness") != "complete"
                    or type(standard) is not int or type(combined) is not int):
                base["pass_facts_incomplete"] += 1
                continue
            claims = [fact for fact in summary["claim_facts"].values()
                      if fact.get("completeness") == "complete"
                      and type(fact.get("standard_shanten_after")) is int
                      and type(fact.get("shanten_after")) is int
                      and fact.get("best_followup_discard") is not None]
            if not claims:
                base["claim_facts_incomplete"] += 1
                continue
            improving = [fact for fact in claims
                         if fact["standard_shanten_after"] < standard]
            if not improving:
                base["no_standard_improving_claim"] += 1
                continue
            base["standard_improving_claim_windows"] += 1
            strongest = min(fact["shanten_after"] for fact in improving)
            relation = "combined_improves" if strongest < combined else \
                "combined_same" if strongest == combined else "combined_worsens"
            base[relation] += 1
            hand = (summary["game_id"], summary["round_no"])
            room = summary["game_id"].split("_r1_b", 1)[0]
            hands[pressure].add(hand)
            rooms[pressure].add(room)
            hands[pressure + "/" + relation].add(hand)
            rooms[pressure + "/" + relation].add(room)
    if runs != 7:
        raise ValueError("冻结 R18 v2 自由赛运行数不是七: " + str(runs))
    return {
        "schema": "r18-claim-pressure-feasibility/1",
        "policy_version": POLICY,
        "release_package_id": RELEASE_ID,
        "r18_runs": runs,
        "audit_root": str(audit_root),
        "counts": {name: dict(value) for name, value in sorted(counts.items())},
        "distinct_hands": {name: len(value) for name, value in sorted(hands.items())},
        "distinct_rooms": {name: len(value) for name, value in sorted(rooms.items())},
        "p84_exclusion": "own_meld_count=0 AND wealth_count>=2 AND pass.seven_pairs_shanten_after<=1",
        "limits": "窗口相关；只核对可见事实与实见首选，不估计强制鸣牌收益。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    body = analyze(args.audit_root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
