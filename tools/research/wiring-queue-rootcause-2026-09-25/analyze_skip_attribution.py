"""归因 SSE 帧为什么没有被跳过规则接受（F2 前置分析）。

背景
----
跳过规则只返回真/假；被拒的帧直接发一次权威快照，审计里原本只留下这一次请求。
2026-09-25 起，帧落到发快照那条路径时会额外落一条 `sse_frame_not_skipped` 审计，
记录判定所依赖的输入。本脚本用它**离线复现**各条跳过规则的前提，把每帧归到一个
可操作的原因码上——因为"快照不够新""本周期有鸣牌兴趣""周期身份对不上"三者的
修法与风险完全不同。

归因规则（按 `OfficialGameSession._sse_or_boundary_wait` 中四条跳过的实际前提）

顺序判定，取第一个成立的原因：

1. `filter_inactive`     —— 本场已停用推断性跳过（`_sse_filter_active` 为假）。
2. `gate_in_flight` / `gate_blocked` —— 动作门正在提交或已封锁同窗。
3. `offset_unsupported`  —— `seq_delta` 不在任何规则支持的偏移上。
4. `freshness`           —— `base_seq != last_seq`（快照落后；两条 timeout 规则都要求相等）。
5. `cycle_unknown`       —— 周期身份未知（`response_cycle_key` 为 None）。
6. `cycle_mismatch`      —— 周期身份的触发弃牌 seq 与 `base_seq` 不等。
7. `claim_interest`      —— 本周期对我方有鸣牌兴趣（保守侧，规则会拒跳）。
8. `deep_condition`      —— 简单前提全过，仍被更深的条件（快照/历史事件细节）挡住。

`deep_condition` 是**剩余项**，不是"未知"：它表示在现有观测下无法再细分，需要更细的
审计才能进一步归因。**不得把它当作"没有原因"。**

用法::

    python analyze_skip_attribution.py <audit_root> [--json-out 路径]

只读审计，不访问网络、不改输入。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/wiring-queue-rootcause-2026-09-25'

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
from collections import Counter, defaultdict
from pathlib import Path


def iter_games(audit_root: Path):
    """产出每个参与者目录下的 games/*.jsonl，两种布局都支持。"""

    seen: set[Path] = set()
    for pattern in ("slot-*/runs/*/participants/*/games/*.jsonl",
                    "runs/*/participants/*/games/*.jsonl"):
        for path in sorted(audit_root.glob(pattern)):
            if path not in seen:
                seen.add(path)
                yield path


# 每条跳过规则只对特定 seq 偏移生效：own_discard_echo 管 +1、peng timeout 管 +3、
# chi timeout 管 +2。归因必须先按偏移路由到对应规则，否则会把"根本没有规则覆盖这个
# 偏移"误报成"快照落后"——这正是第一次跑出来 77% freshness 的原因（其中 78% 其实是
# 只覆盖单个事件的 +1 帧）。
_RULE_BY_DELTA = {1: "own_discard_echo", 3: "peng_timeout", 2: "chi_timeout"}


def classify(row: dict) -> str:
    """把一条 `sse_frame_not_skipped` 记录归到一个原因码。

    顺序：先按偏移路由到能覆盖它的规则；没有规则覆盖就报 `no_rule_for_offset`，
    不再往下判"新鲜度"——那是另一条规则的前提，对不上偏移的帧没有意义。
    """

    if not row.get("filter_active", True):
        return "filter_inactive"
    rule = _RULE_BY_DELTA.get(row.get("seq_delta"))
    if rule is None:
        return "no_rule_for_offset"
    if row.get("gate_in_flight") or row.get("gate_blocked"):
        return "gate_busy"
    if rule == "own_discard_echo":
        # 该规则只认"我方已提交弃牌、等待回显"这一刻；没有待回显就不可能跳过。
        if row.get("expected_own_discard_seq") is None:
            return "no_pending_own_discard"
        if row.get("base_seq") != row.get("last_seq"):
            return "freshness"
        if row.get("expected_own_discard_seq") != row.get("observed_seq"):
            return "echo_seq_mismatch"
        return "deep_condition"
    # peng_timeout / chi_timeout 都有"base_seq 必须等于已消费水位"这条前提。
    if row.get("base_seq") != row.get("last_seq"):
        return "freshness"
    cycle = row.get("cycle")
    if cycle is None:
        return "cycle_unknown"
    if cycle[1] != row.get("base_seq"):
        return "cycle_mismatch"
    if row.get("claim_interest"):
        return "claim_interest"
    return "deep_condition"


def analyze(audit_root: Path) -> dict:
    overall = Counter()
    by_delta = defaultdict(Counter)
    by_phase = defaultdict(Counter)
    delta_hist = Counter()
    examples = defaultdict(list)
    skipped_seq_deltas = Counter()
    for path in iter_games(audit_root):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = record.get("payload") or {}
                if not payload.get("sse_frame_not_skipped"):
                    continue
                reason = classify(payload)
                overall[reason] += 1
                delta_hist[payload.get("seq_delta")] += 1
                by_delta[payload.get("seq_delta")][reason] += 1
                by_phase[payload.get("snapshot_phase")][reason] += 1
                if len(examples[reason]) < 3:
                    examples[reason].append({
                        "observed_seq": payload.get("observed_seq"),
                        "seq_delta": payload.get("seq_delta"),
                        "last_seq": payload.get("last_seq"),
                        "phase": payload.get("snapshot_phase"),
                        "claim_interest": payload.get("claim_interest"),
                    })
    total = sum(overall.values())
    return {
        "audit_root": str(audit_root),
        "frames_not_skipped": total,
        "reason_counts": dict(overall.most_common()),
        "reason_share": {k: round(v / total, 4) for k, v in overall.most_common()} if total else {},
        "seq_delta_histogram": dict(sorted(delta_hist.items(), key=lambda kv: (kv[0] is None, kv[0]))),
        "by_seq_delta": {str(k): dict(v.most_common()) for k, v in sorted(by_delta.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        "by_phase": {str(k): dict(v.most_common()) for k, v in by_phase.items()},
        "examples": {k: v for k, v in examples.items()},
    }


def render(summary: dict) -> str:
    lines = ["审计根: " + summary["audit_root"],
             "未跳过的帧: %d" % summary["frames_not_skipped"], ""]
    lines.append("== 原因码分布 ==")
    for reason, count in summary["reason_counts"].items():
        lines.append("  %-20s %6d  (%.1f%%)"
                     % (reason, count, 100.0 * summary["reason_share"][reason]))
    lines.append("")
    lines.append("== seq_delta 直方图 ==")
    for delta, count in summary["seq_delta_histogram"].items():
        lines.append("  delta=%-5s %6d" % (delta, count))
    lines.append("")
    lines.append("== delta x 原因 ==")
    for delta, counts in summary["by_seq_delta"].items():
        lines.append("  delta=%-5s %s" % (delta, counts))
    lines.append("")
    lines.append("== 阶段 x 原因 ==")
    for phase, counts in summary["by_phase"].items():
        lines.append("  %-16s %s" % (phase, counts))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="归因 SSE 帧未被跳过的原因")
    parser.add_argument("audit_root", help="审计根")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)
    root = Path(args.audit_root)
    if not root.is_dir():
        raise SystemExit("审计根不存在: " + str(root))
    summary = analyze(root)
    print(render(summary))
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if summary["frames_not_skipped"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
