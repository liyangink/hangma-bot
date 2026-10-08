"""汇总测试房抓打圈决策证据；流式复用审计读取器，不访问网络、不计算积分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/piao-window-alignment-2026-09-08'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter
import json
from pathlib import Path

from hangma_bot.adapters.recording.reader import iter_records
from hangma_bot.adapters.recording.schema import canonical_outcome
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.catch_play import analyze_catch_play


def is_claim(key):
    """只识别响应认领动作；暗杠和补杠另属摸牌动作。"""
    return key.startswith(("chi:", "peng:", "gang:exposed:"))


def summarize(root):
    """按完整关联键归并窗口、修订和尝试，双层提交记录只计一次。

    只统计本地确实捕获的窗口，不能据零窗口推断平台禁止动作。
    accepted 是提交接口明确接受，最终执行还需与官方赛后事件核对。
    """
    root = Path(root)
    decisions = {}
    issues = []
    observed_whites = set()
    for record in iter_records(root):
        location = {"file": record.relative_path, "line": record.line_no}
        if record.error:
            issues.append({**location, "issue": record.error})
            continue
        if record.kind not in ("decision_input", "submission_intent", "submission_outcome"):
            continue
        context = record.context or {}
        if not context.get("decision_id"):
            issues.append({**location, "issue": "缺 decision_id，不能归并"})
            continue
        identity = tuple(context.get(key) for key in (
            "run_id", "participant_id", "stage_attempt_id", "game_id", "round_no", "decision_id",
        ))
        entry = decisions.setdefault(identity, {"revisions": {}, "attempts": {}})
        payload = record.payload or {}
        if record.kind == "decision_input":
            try:
                request = decision_request_from_json(payload["request"])
                observation = request.observation
                circle = analyze_catch_play(observation)
            except (KeyError, ValueError, TypeError) as error:
                issues.append({**location, "issue": "决策输入无法解码: " + type(error).__name__})
                continue
            for event in observation.public_history:
                if event.kind == "tile_discarded" and event.tiles == (observation.rule_state.wealth_god,):
                    observed_whites.add((observation.game_id, observation.round_no, event.seq))
            role = (
                "inactive" if not circle.active else "unknown" if circle.owner_seat is None
                else "owner" if circle.owner_seat == observation.seat else "other"
            )
            keys = [candidate.action_key for candidate in request.rules.legal_candidates]
            entry["revisions"][payload["plan_revision"]] = {
                "source": location, "phase": observation.phase, "seat": observation.seat,
                "catch_play": observation.rule_state.catch_play, "circle_role": role,
                "baotou_before": observation.rule_state.baotou,
                "chain_count_before": observation.rule_state.chain_count,
                "owner_seat": circle.owner_seat, "started_seq": circle.started_seq,
                "owner_proof": circle.source, "consumed_seq": observation.consumed_seq,
                "responding_seats": list(observation.responding_seats),
                "claim_keys": [key for key in keys if is_claim(key)],
                "white_candidate": "discard:" + observation.rule_state.wealth_god.code in keys,
            }
        else:
            attempt_no = context.get("attempt_no")
            if not isinstance(attempt_no, int):
                issues.append({**location, "issue": "提交记录缺 attempt_no"})
                continue
            attempt = entry["attempts"].setdefault(attempt_no, {
                "keys": set(), "outcomes": set(), "official_codes": set(), "sources": [],
                "revision": None,
            })
            attempt["sources"].append(location)
            if payload.get("action_key"):
                attempt["keys"].add(payload["action_key"])
            if payload.get("plan_revision") is not None:
                attempt["revision"] = payload["plan_revision"]
            value = payload.get("outcome") or payload.get("outcome_type")
            if value:
                attempt["outcomes"].add(canonical_outcome(value))
            if payload.get("official_code"):
                attempt["official_codes"].add(payload["official_code"])

    # 生产适配器不拥有 stage_attempt_id；它的提交记录该字段为空。
    # 只能以其余完整关联键唯一命中应用层决策后归并，不能把 None 当成第二次动作。
    stage_index = {}
    for identity, entry in decisions.items():
        if identity[2] is not None and entry["revisions"]:
            key = identity[:2] + identity[3:]
            stage_index.setdefault(key, []).append(identity)
    for identity, entry in list(decisions.items()):
        if identity[2] is not None or entry["revisions"]:
            continue
        matches = stage_index.get(identity[:2] + identity[3:], [])
        if len(matches) != 1:
            continue  # 缺失或多义仍在下方报告，绝不猜阶段。
        target = decisions[matches[0]]
        for number, source in entry["attempts"].items():
            if number not in target["attempts"]:
                target["attempts"][number] = source
                continue
            dest = target["attempts"][number]
            for key in ("keys", "outcomes", "official_codes"):
                dest[key].update(source[key])
            dest["sources"].extend(source["sources"])
            if dest["revision"] is None:
                dest["revision"] = source["revision"]
            elif source["revision"] is not None and dest["revision"] != source["revision"]:
                dest["revision"] = None
                issues.append({"decision_id": identity[-1], "attempt_no": number, "issue": "双层记录 plan_revision 冲突"})
        del decisions[identity]

    counts = Counter()
    cases = []
    for identity, entry in decisions.items():
        revisions = entry["revisions"]
        if not revisions:
            issues.append({"decision_id": identity[-1], "issue": "提交缺对应决策输入"})
            continue
        counts["decision_windows"] += 1
        # 一次窗口的多次刷新只计一次存在性，不把重试当新增权限机会。
        for category in {f"{r['circle_role']}:{r['phase']}" for r in revisions.values()}:
            counts["observed_windows:" + category] += 1
        if any(r["white_candidate"] for r in revisions.values()):
            counts["windows_with_legal_white"] += 1
        for role in {r["circle_role"] for r in revisions.values() if r["claim_keys"]}:
            counts[f"windows_with_claim_candidates:{role}"] += 1
        for number, attempt in entry["attempts"].items():
            revision = revisions.get(attempt["revision"])
            if revision is None:
                issues.append({"decision_id": identity[-1], "attempt_no": number, "issue": "尝试缺匹配 plan_revision"})
                continue
            if len(attempt["keys"]) != 1 or len(attempt["outcomes"]) > 1:
                issues.append({"decision_id": identity[-1], "attempt_no": number, "issue": "同一次尝试的动作或结果冲突"})
                continue
            key = next(iter(attempt["keys"]))
            outcome = next(iter(attempt["outcomes"]), "missing_outcome")
            counts["attempt_outcomes:" + outcome] += 1
            if key == "discard:白":
                counts["white_attempts:" + outcome] += 1
                counts[f"white_attempts:baotou_{str(revision['baotou_before']).lower()}:{outcome}"] += 1
            if is_claim(key):
                role = revision["circle_role"]
                counts[f"claim_attempts:{role}:{outcome}"] += 1
                cases.append({
                    "run_id": identity[0], "participant_id": identity[1], "game_id": identity[3],
                    "stage_attempt_id": identity[2],
                    "round_no": identity[4], "decision_id": identity[5], "attempt_no": number,
                    "action_key": key, "outcome": outcome,
                    "official_codes": sorted(attempt["official_codes"]),
                    "window": revision, "submission_sources": attempt["sources"],
                })
    return {
        "scope": "测试房窗口与提交接口证据；不是策略强度评估，也不以零观测证明禁令",
        "audit_root": str(root.resolve()), "counts": dict(sorted(counts.items())),
        "observed_white_events_lower_bound": len(observed_whites),
        "claim_cases": cases, "read_or_link_issues": issues,
        "evidence_limits": [
            "窗口统计只覆盖实际捕获的决策输入；没有开窗样本不等于规则禁止",
            "圈主由当前规则解析公开证据；unknown 单列，不计作非圈主",
            "同一动作的应用层和适配器层结果归并；冲突单列，不算成功",
            "accepted 还需核对赛后官方 chi/peng/gang 事件及后续圈状态",
            "主动普通弃白不保证构成财飘；普通圈与实际财飘须分开验证",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.audit_root.is_dir():
        parser.error("audit_root 必须是已存在的本次审计目录")
    report = summarize(args.audit_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"counts": report["counts"], "issues": len(report["read_or_link_issues"]),
                      "observed_white_events_lower_bound": report["observed_white_events_lower_bound"],
                      "output": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
