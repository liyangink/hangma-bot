#!/usr/bin/env python3
"""G37：短任务卡请求单个离线作者机制；保存原答，不执行候选代码。"""

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

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g37-glm-single-author-20260927')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G37-SINGLE-MECHANISM-AUTHOR-PREREG-2026-09-27.md')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


PROMPT = """你是杭麻 Bot 的离线启发式算子作者。只输出一个严格 JSON 对象，不输出 Markdown，不调用工具，不写完整策略源码。允许明确回答 infeasible，但需先认真尝试。任务：给一个**单一短机制**，在冻结 R18 v2 上改善早期持白弃牌后的自然牌成面与多来源进张，目标最终是白板晚些能用于爆头/财飘，同时不能牺牲普通胡或七对的可兑现机会。

官方 v34：只自摸胡；白板为财神，不可吃碰杠胡；爆头由规则模块判断摸前任意物理可得牌可胡；财飘须满足已爆头后弃白的合法链；抓打圈非圈主仅能摸切；牌墙末 20 张留墩。线上只能读 PlayerObservation、当前合法动作及 HangmaRules 对每个动作给的 shanten_after、standard_shanten_after、seven_pairs_shanten_after、useful_tiles、standard_useful_tiles、seven_pairs_useful_tiles，以及官方观察里的本人手牌/副露/公开河/规则状态/remaining_tile_count。逐码有效项包含 code 与 remaining_estimate；它是公开未见上界，不是墙概率。未知字段不能冒充零。公开河与副露有重复记账风险，若需公开牌张数须明确调用生产 count_unseen_tiles，不能自己相加。只重排合法弃牌，胡/碰/吃/杠/结算/提交保持生产行为。白板不预先绑定到某面子。

已知失败：G11 固定风险/宽面交换在 768 张完整桌约 -0.568 分/桌；P28 两步宽度未过收益门；G30 同即时逐码牌效时弃字牌/边张在 384 张完整桌 H 池 -1.844、M 池 +1.417、合并 -0.214 分/桌；G36 近听持一白层里“潜在几何结构总数相同而来源码更多”在 G23 120 对与 G29 78 对中 0 改选。故不要重命名宽度奖金、边张字典键、同牌效下来源数键，也不要只调这些阈值。新机制可考虑更早普通型向听至少 2 的状态，允许有限即时牌效取舍，但必须给出明确普通胡/七对代价保护。公开未见数只能作物理上下界/序数，不能说是墙概率。三摸无对手理想容量与桌赛净分不同；不能保证收益。

输出 JSON 字段严格为 status、name、applicability、inputs、choice_rule、why_distinct、mathematical_check、counterexample、ordinary_hu_and_pairs_guard、worst_case_bound、outcome_blind_reach_gate。status 为 proposed 或 infeasible。各字段用短中文字符串；choice_rule 写可编码的有限步骤、比较方向、并列回退父代，不能发明不存在的生产字段。mathematical_check 给一个小手牌局部构造可手算，若某一关键数值无法从可见输入得到则 status=infeasible 并说明。worst_case_bound 要按最多 14 合法弃牌、34 牌码计，不能枚举未来完整桌。请主动检查方案是否被 R18 当前 -100×综合向听＋公开有效张容量直接支配，或只是 G11/P28/G30/G36 的重复；若是则 status=infeasible。"""


def parse_answer(value: str) -> tuple[bool, str | None]:
    try:
        answer = json.loads(value.strip())
    except json.JSONDecodeError:
        return False, "invalid_json"
    keys = ("status", "name", "applicability", "inputs", "choice_rule", "why_distinct",
            "mathematical_check", "counterexample", "ordinary_hu_and_pairs_guard",
            "worst_case_bound", "outcome_blind_reach_gate")
    if not isinstance(answer, dict) or any(key not in answer or not isinstance(answer[key], str)
                                           for key in keys):
        return False, "missing_or_nonstring_field"
    if answer["status"] not in ("proposed", "infeasible"):
        return False, "invalid_status"
    return True, None


def main() -> None:
    """一次调用，避免重复送同一任务；记录摘要而不保存令牌原文。"""

    OUT.mkdir(parents=True, exist_ok=True)
    prompt_path, answer_path, call_path = (_project_file(_PROJECT_ROOT, OUT / name) for name in
                                           ("prompt.txt", "answer.txt", "call.json"))
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise SystemExit("G37 已有调用产物，拒绝再次调用")
    if not PREREG.exists():
        raise ValueError("G37 预登记缺失")
    prompt_path.write_text(PROMPT, encoding="utf-8")
    argv = ["dsh", "--profile", "headless", "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")), "--patch", str(ROUTE), PROMPT]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g37-glm-") as state_dir:
        try:
            result = subprocess.run(argv, cwd=ROOT, env=dict(os.environ, DSH_HOME=state_dir),
                                    capture_output=True, text=True, timeout=1200, check=False)
            code, answer, diagnostic = result.returncode, result.stdout, result.stderr
            failure = None if code == 0 else "nonzero_exit"
        except subprocess.TimeoutExpired as error:
            code = None
            answer = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else error.stdout or ""
            diagnostic = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else error.stderr or ""
            failure = "timeout_or_uncertain_transport"
    answer_path.write_text(answer, encoding="utf-8")
    valid, parse_error = parse_answer(answer) if code == 0 else (False, "call_failure")
    record = {"schema": "g37-glm-single-author/1", "provider_requested": "zai-coding-cn",
              "model_requested": "glm-5.3", "reasoning_effort_requested": "max",
              "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
              "prompt_sha256": sha(prompt_path), "route_patch_sha256": sha(ROUTE),
              "elapsed_seconds": round(time.monotonic() - started, 3), "exit_code": code,
              "answer_chars": len(answer), "answer_sha256": sha(answer_path),
              "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
              "diagnostic_bytes": len(diagnostic.encode()), "failure_kind": failure,
              "valid_json_contract": valid, "parse_error": parse_error,
              "scope": "offline hypothesis only; no generated code executed or reward accepted"}
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
