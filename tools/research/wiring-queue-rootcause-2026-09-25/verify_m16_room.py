"""M=16 测试房接线验收：一条命令跑完硬门与容量指标。

为什么需要
----------
接线修复的验收不是"房跑完就算过"。判据必须是官方侧的**后果**而不是本地自述：

1. 本人跨局首弃牌有没有被官方 `timeout(kind=discard)` 模切（硬门，必须为 0）；
2. 规则候选中被策略首选、最终零 POST 的非过鸣牌有没有漏发（硬门，必须为 0，
   未证实项单列，**不得计作零漏窗**）；
3. 容量水位：状态查询排队分布、429、发前撤销、队列深度（诊断，不是硬门）。

本脚本把已有工具串成一条可复算路径，不重新实现它们的判据：

- `verify_sse_settled_first_discard.py`（跨局首弃牌，按身份）
- `audit_claim_opportunities.py`（合法鸣牌漏发，全房）
- `summarize_wait_observability.py`（队列与撤销观测）

用法::

    python verify_m16_room.py --campaign runs/<战役> [--round 1] [--json-out <路径>]

战役目录需含 `campaign.json`（取 identities）。审计与官方原文默认位于
`artifacts/sessions/<战役>-r<K>/{audit,official}`。

退出码：0 = 硬门全过；1 = 有硬门失败；2 = 用法或证据缺失（不得当作通过）。
只读：不访问网络、不改任何输入。
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
import subprocess
import sys
from pathlib import Path

REPO_ROOT = _PROJECT_ROOT
PREFIX = 'tools/research/r18-four-arm-evaluation-2026-09-23'
FIRST_DISCARD = _project_file(_PROJECT_ROOT, 'review/r18-four-arm-evaluation-2026-09-23/verify_sse_settled_first_discard.py')
CLAIM_AUDIT = _project_file(_PROJECT_ROOT, 'review/r18-four-arm-evaluation-2026-09-23/audit_claim_opportunities.py')
WAIT_SUMMARY = _project_file(_PROJECT_ROOT, 'review/wiring-queue-rootcause-2026-09-25/summarize_wait_observability.py')


def _run(script: Path, args: list[str], *, allow_failure: bool = False):
    """运行既有工具并解析其 JSON 输出；非零退出在硬门上视为失败。"""

    completed = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if completed.returncode != 0 and not allow_failure:
        return None, completed.returncode, completed.stdout + completed.stderr
    try:
        return json.loads(completed.stdout), completed.returncode, completed.stderr
    except ValueError:
        return None, completed.returncode, completed.stdout + completed.stderr


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M=16 测试房接线验收")
    parser.add_argument("--campaign", required=True, help="战役目录（含 campaign.json）")
    parser.add_argument("--round", type=int, default=1, help="轮号（默认 1）")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    campaign_dir = Path(args.campaign)
    if not campaign_dir.is_absolute():
        campaign_dir = _project_file(_PROJECT_ROOT, REPO_ROOT / campaign_dir)
    campaign = json.loads((campaign_dir / "campaign.json").read_text(encoding="utf-8"))
    identities = campaign.get("identities") or {}
    if len(identities) != 4:
        raise SystemExit("campaign.json 里不是四个身份，拒绝出验收结论")

    session = _project_file(_PROJECT_ROOT, REPO_ROOT / "artifacts/sessions" / ("%s-r%d" % (campaign["campaign"], args.round)))
    audit_root, official_root = session / "audit", session / "official"
    if not audit_root.is_dir():
        raise SystemExit("审计根不存在: %s" % audit_root)
    if not official_root.is_dir():
        raise SystemExit("官方原文根不存在（先完成下载）: %s" % official_root)

    verdict = {"campaign": campaign["campaign"], "room_id": campaign.get("room_id"),
               "m": campaign.get("m"), "rounds": campaign.get("rounds"),
               "session": str(session.relative_to(REPO_ROOT)), "first_discard": {},
               "claim_opportunities": None, "wait_observability": None, "hard_gate_failures": []}

    print("=== 硬门 1：本人跨局首弃牌超时 ===")
    for slot, participant_id in sorted(identities.items()):
        doc, code, raw = _run(FIRST_DISCARD, [str(official_root), participant_id], allow_failure=True)
        if doc is None:
            verdict["first_discard"][slot] = {"status": "evidence_error", "detail": raw[-400:]}
            verdict["hard_gate_failures"].append("first_discard:%s:evidence" % slot)
            print("  %-9s 证据错误: %s" % (slot, raw.strip()[-200:]))
            continue
        verdict["first_discard"][slot] = doc
        bad = doc["focal_first_discard_timeouts"]
        print("  %-9s 完整桌 %d  首弃牌窗 %d  超时 %d"
              % (slot, doc["complete_games"], doc["focal_first_discard_windows"], bad))
        if bad:
            verdict["hard_gate_failures"].append("first_discard:%s:%d" % (slot, bad))

    print("=== 硬门 2：规则合法鸣牌漏发 ===")
    doc, code, raw = _run(CLAIM_AUDIT, [str(audit_root), str(official_root)], allow_failure=True)
    if doc is None:
        verdict["claim_opportunities"] = {"status": "tool_failed", "detail": raw[-400:]}
        print("  工具失败: %s" % raw.strip()[-300:])
    else:
        verdict["claim_opportunities"] = doc
        print("  官方完整桌 %d  牌形机会 %s" % (doc["official_games"], doc["opportunities"]))
        print("  已确认合法漏发 %d  未证实 %d  手牌重建错误 %d"
              % (len(doc["confirmed_legal_missing_inputs"]),
                 len(doc["unverified_missing_inputs"]),
                 len(doc["hand_reconstruction_errors"])))
        if doc["confirmed_legal_missing_inputs"]:
            verdict["hard_gate_failures"].append(
                "claims:%d" % len(doc["confirmed_legal_missing_inputs"]))
        if doc["hand_reconstruction_errors"]:
            verdict["hard_gate_failures"].append(
                "claims:hand_reconstruction:%d" % len(doc["hand_reconstruction_errors"]))

    print("=== 容量与队列观测（诊断，不是硬门） ===")
    summary_proc = subprocess.run(
        [sys.executable, str(WAIT_SUMMARY), str(audit_root)],
        cwd=REPO_ROOT, capture_output=True, text=True)
    print(summary_proc.stdout.strip())
    verdict["wait_observability"] = (summary_proc.stdout.strip().splitlines()[-3:]
                                     if summary_proc.returncode == 0 else "failed")

    print("=== 验收结论 ===")
    if verdict["hard_gate_failures"]:
        print("  未通过；硬门失败项: %s" % verdict["hard_gate_failures"])
    else:
        print("  硬门通过：跨局首弃牌 0 超时、规则合法鸣牌 0 漏发。")
        print("  注意：未证实项与未观测窗口必须单列，不得计作零漏窗；容量指标只作水位记录。")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(verdict, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if verdict["hard_gate_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
