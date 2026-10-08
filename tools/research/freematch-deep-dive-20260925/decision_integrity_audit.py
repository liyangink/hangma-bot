#!/usr/bin/env python3
"""主审：全量运行完整性审计（106 份 decisions.jsonl，只做流式计数）。

注意：`decision_planned.returned_plan` 是**一个 Decision 对象（dict）**，
计划在 `returned_plan["candidates"]`，rank 1 为首选。
"""
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

import collections
import glob
import json
from concurrent.futures import ProcessPoolExecutor

PATTERNS = [
    "artifacts/sessions/**/participants/u_13495c3d79c8/decisions.jsonl",
    "datasets/derived/**/participants/u_13495c3d79c8/decisions.jsonl",
]


def pct(vals, p):
    if not vals:
        return float("nan")
    s = sorted(vals)
    k = int((len(s) - 1) * p)
    return s[k]


def scan(path):
    c = collections.Counter()
    lat_rule, lat_policy = [], []
    degrade = collections.Counter()
    strategies = collections.Counter()
    top_by_window = {}
    try:
        with open(path, "r", errors="ignore") as fh:
            for line in fh:
                if '"kind"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    c["bad_json"] += 1
                    continue
                k = d.get("kind")
                pay = d.get("payload")
                if not isinstance(pay, dict):
                    continue
                w = pay.get("window") if isinstance(pay.get("window"), dict) else None
                kk = None
                if w is not None:
                    kk = (w.get("game_id"), w.get("round_no"), w.get("trigger_seq"), w.get("phase"))
                if k == "decision_input":
                    c["input"] += 1
                    lat_rule.append(float(pay.get("rule_elapsed_ms") or 0.0))
                elif k == "decision_planned":
                    c["planned"] += 1
                    lat_policy.append(float(pay.get("policy_elapsed_ms") or 0.0))
                    for r in (pay.get("degraded_reasons") or []):
                        s = str(r)
                        degrade[s[:60]] += 1
                        if "评分完成" in s:
                            strategies[s.split(":")[-1].replace(" 评分完成", "").strip()] += 1
                    rp = pay.get("returned_plan")
                    cands = rp.get("candidates") if isinstance(rp, dict) else None
                    if not cands:
                        c["plan_empty"] += 1
                        ph = (w or {}).get("phase")
                        strat = None
                        for r in (pay.get("degraded_reasons") or []):
                            s = str(r)
                            if "评分完成" in s:
                                strat = s.split(":")[-1].replace(" 评分完成", "").strip()
                        c["empty_%s|%s" % (strat, ph)] += 1
                    elif kk is not None:
                        best = None
                        for e in cands:
                            if not isinstance(e, dict):
                                continue
                            r = e.get("rank")
                            if r is None:
                                continue
                            if best is None or float(r) < float(best[0]):
                                best = (r, e.get("action_key"))
                        if best is not None:
                            top_by_window[kk] = best[1]
                elif k == "candidate_validated":
                    c["validated"] += 1
                    if pay.get("legal") is not True:
                        c["illegal"] += 1
                elif k == "decision_ended":
                    c["ended"] += 1
                    ph = (w or {}).get("phase")
                    c["end_%s|%s" % (ph, pay.get("end_reason"))] += 1
                elif k == "submission_intent":
                    c["intent"] += 1
                    c["intent_emergency"] += 1 if pay.get("is_emergency") else 0
                    if kk is not None:
                        want = top_by_window.get(kk)
                        got = pay.get("action_key")
                        if want is not None:
                            if want == got:
                                c["submit_matches_rank1"] += 1
                            else:
                                c["submit_differs_rank1"] += 1
                                c["diff_%s|%s" % (want, got)] += 1
                elif k == "submission_outcome":
                    c["outcome"] += 1
                    c["out_" + str(pay.get("outcome_type"))] += 1
    except Exception as exc:
        c["file_error_" + type(exc).__name__] += 1
    return c, lat_rule, lat_policy, degrade, strategies


def main() -> int:
    files = []
    for pat in PATTERNS:
        files.extend(glob.glob(pat, recursive=True))
    files = sorted(set(files))
    print("文件数 %d" % len(files), flush=True)
    total = collections.Counter()
    rule, policy = [], []
    degrade = collections.Counter()
    strategies = collections.Counter()
    with ProcessPoolExecutor(max_workers=6) as ex:
        for i, (c, lr, lp, dg, st) in enumerate(ex.map(scan, files, chunksize=4)):
            total.update(c)
            rule.extend(lr)
            policy.extend(lp)
            degrade.update(dg)
            strategies.update(st)
            if (i + 1) % 20 == 0:
                print("  已扫 %d/%d，累计 input=%d planned=%d intended=%d"
                      % (i + 1, len(files), total["input"], total["planned"], total["intent"]), flush=True)
    print()
    print("## 策略身份（来自 degraded_reasons）")
    for k, v in strategies.most_common():
        print("- %-40s %d" % (k, v))
    print()
    print("## 核心计数")
    for k in ("input", "planned", "plan_empty", "validated", "illegal", "ended", "intent", "intent_emergency",
              "submit_matches_rank1", "submit_differs_rank1", "outcome"):
        if total[k]:
            print("- %-24s %d" % (k, total[k]))
    print()
    print("## plan_empty 按 策略 × phase")
    for k, v in sorted(total.items()):
        if k.startswith("empty_"):
            print("- %-56s %d" % (k[6:], v))
    print()
    print("## end_reason × phase")
    for k, v in sorted(total.items()):
        if k.startswith("end_"):
            print("- %-40s %d" % (k[4:], v))
    print()
    print("## submission_outcome.type")
    for k, v in sorted(total.items()):
        if k.startswith("out_"):
            print("- %-40s %d" % (k[4:], v))
    print()
    print("## 提交与计划首选不一致的前 10 种")
    diffs = [(k, v) for k, v in total.items() if k.startswith("diff_")]
    for k, v in sorted(diffs, key=lambda kv: -kv[1])[:10]:
        print("- %-56s %d" % (k[5:], v))
    print()
    print("## 延迟（ms）")
    for label, vals in (("rule_elapsed_ms", rule), ("policy_elapsed_ms", policy)):
        if vals:
            print("- %-18s n=%d p50=%.2f p90=%.2f p99=%.2f max=%.2f"
                  % (label, len(vals), pct(vals, .5), pct(vals, .9), pct(vals, .99), max(vals)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())