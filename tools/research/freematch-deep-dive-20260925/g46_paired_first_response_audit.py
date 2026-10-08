#!/usr/bin/env python3
"""G46：原样复跑 G32 全部开发根，量首个改弃牌是否立即改变他家响应。"""

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

import g13_accounted_panel as accounted
import g41_first_divergence_audit as g41


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g46-paired-first-response-20260927')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(mix: str, root: int, seat: int, arm: str, manifest: dict):
    """只保留全部座位动作；G41 的原样复跑逐桌核对冻结 G32 结算。"""

    outcomes = {}
    original = accounted.drive_match

    async def capture(**kwargs):
        outcome = await original(**kwargs)
        outcomes[kwargs["spec"].match_id] = outcome
        return outcome

    accounted.drive_match = capture
    try:
        stage, own, source_hashes = g41._run(mix=mix, root=root, seat=seat,
                                              arm=arm, manifest=manifest)
    finally:
        accounted.drive_match = original
    if set(outcomes) != {"sitin-stage:" + table_id for table_id in own}:
        raise ValueError("全部座位动作与阶段桌 ID 不一致")
    return stage, own, outcomes, source_hashes


def immediate_response(outcome, decision_id: str, round_no: int) -> tuple[str, int | None]:
    """从焦点弃牌到下一个摸牌窗口，识别是否有人立即吃碰杠或胡。"""

    records = list(outcome.decisions)
    index = next((n for n, item in enumerate(records) if item.decision_id == decision_id), None)
    if index is None:
        raise ValueError("首处分歧决策不在模拟事件")
    if not records[index].action_key.startswith("discard:"):
        raise ValueError("G32 首处分歧不是弃牌")
    for item in records[index + 1:]:
        window = item.window_key
        if window.get("round_no") != round_no:
            return "round_ended", None
        phase = window.get("phase")
        family = item.action_key.split(":", 1)[0]
        if isinstance(phase, str) and phase.startswith("response") and family in ("chi", "peng", "gang", "hu"):
            return family, item.seat
        if phase == "draw":
            return "none", None
    return "round_ended", None


def root_rows(mix: str, root: int, manifest: dict) -> list[dict]:
    """每根四座两桌，逐臂对账后只留首处分歧和完整桌积分。"""

    rows = []
    baseline_arm, candidate_arm = manifest["arms"]
    for seat in range(4):
        baseline, b_own, b_outcomes, b_hashes = replay(mix, root, seat, baseline_arm, manifest)
        candidate, c_own, c_outcomes, c_hashes = replay(mix, root, seat, candidate_arm, manifest)
        for b_table, c_table in zip(baseline["tables"], candidate["tables"]):
            table_id = b_table["table_id"]
            if c_table["table_id"] != table_id:
                raise ValueError("两臂桌 ID 不一致")
            before, after = b_own[table_id], c_own[table_id]
            first = next((index for index in range(min(len(before), len(after)))
                          if g41._identity(before[index]) != g41._identity(after[index])), None)
            if first is None and len(before) != len(after):
                first = min(len(before), len(after))
            base_score = b_table["hand_account"]["focal_table_delta"]
            other_score = c_table["hand_account"]["focal_table_delta"]
            row = {"table_id": table_id, "mix": mix, "root": root, "focal_seat": seat,
                   "baseline_score": base_score, "candidate_score": other_score,
                   "delta": other_score - base_score,
                   "first_divergence_index": first,
                   "frozen_stage_sha256": {"baseline": b_hashes[table_id],
                                           "candidate": c_hashes[table_id]}}
            if first is not None:
                if first >= len(before) or first >= len(after):
                    raise ValueError("首处分歧只有单臂决策，无法比较即时响应")
                b_request, b_plan = before[first]
                c_request, c_plan = after[first]
                if (b_request.window_key != c_request.window_key or
                        g41._decision(before[first])["observation"] !=
                        g41._decision(after[first])["observation"]):
                    raise ValueError("首处分歧不是同一动作前玩家可见观察")
                round_no = b_request.window_key.round_no
                b_response = immediate_response(b_outcomes["sitin-stage:" + table_id],
                                                b_request.decision_id, round_no)
                c_response = immediate_response(c_outcomes["sitin-stage:" + table_id],
                                                c_request.decision_id, round_no)
                row.update(round_no=round_no, trigger_seq=b_request.window_key.trigger_seq,
                           baseline_action=b_plan.candidates[0].action_key,
                           candidate_action=c_plan.candidates[0].action_key,
                           baseline_immediate={"kind": b_response[0], "seat": b_response[1]},
                           candidate_immediate={"kind": c_response[0], "seat": c_response[1]})
            rows.append(row)
    return rows


def main() -> None:
    """已看 G32 根仅作机制诊断；不能再充当独立确认样本。"""

    if OUT.exists():
        raise SystemExit("G46 结果目录已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["panel_seed"] != 2026122703 or manifest["roots_per_mix"] != 12:
        raise ValueError("G32 冻结面板身份漂移")
    rows = []
    for mix in ("H", "M"):
        for root in range(1, 13):
            block = root_rows(mix, root, manifest)
            if len(block) != 8:
                raise ValueError("每根应有四座共八桌")
            rows.extend(block)
            print(json.dumps({"mix": mix, "root": root,
                              "touched": sum(row["first_divergence_index"] is not None for row in block)},
                             ensure_ascii=False), flush=True)
    if len(rows) != 192:
        raise ValueError("每臂共应有 192 张完整桌")
    counts = Counter()
    by_mix = defaultdict(Counter)
    for row in rows:
        mix = row["mix"]
        if row["first_divergence_index"] is None:
            counts["no_first_divergence"] += 1
            by_mix[mix]["no_first_divergence"] += 1
            continue
        counts["touched"] += 1
        by_mix[mix]["touched"] += 1
        b = row["baseline_immediate"]
        c = row["candidate_immediate"]
        class_key = f"{b['kind']}→{c['kind']}"
        counts["response_transition|" + class_key] += 1
        by_mix[mix]["response_transition|" + class_key] += 1
        if b != c:
            counts["immediate_changed"] += 1
            by_mix[mix]["immediate_changed"] += 1
        if row["delta"] > 0:
            direction = "positive"
        elif row["delta"] < 0:
            direction = "negative"
        else:
            direction = "zero"
        counts[f"table_delta_direction|{direction}"] += 1
        by_mix[mix][f"table_delta_direction|{direction}"] += 1
        counts[f"table_delta_direction|{class_key}|{direction}"] += 1
    result = {"schema": "g46-paired-first-response/1",
              "g32_manifest_sha256": sha(_project_file(_PROJECT_ROOT, FROZEN / "manifest.json")),
              "g32_result_sha256": sha(_project_file(_PROJECT_ROOT, FROZEN / "result.json")),
              "script_sha256": sha(Path(__file__)), "rows": rows,
              "counts": dict(sorted(counts.items())),
              "by_mix": {mix: dict(sorted(values.items())) for mix, values in sorted(by_mix.items())},
              "boundary": "旧 G32 开发根、同隐藏起点双臂原样复跑；即时响应可归于首弃差异，完整桌积分是全程政策结果，不能按响应分层推断鸣牌价值。"}
    OUT.mkdir(parents=True, exist_ok=False)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "by_mix": result["by_mix"]}, ensure_ascii=False,
                     indent=2), flush=True)


if __name__ == "__main__":
    main()
