#!/usr/bin/env python3
"""G207：用精确包装器合同请 GLM 提出广覆盖跨窗口路线机制。"""

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

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g207-glm-broad-route-author-20260929')
CHANNEL = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch'))
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
INPUTS = (
    _project_file(_PROJECT_ROOT, HERE / "G69-G71-SAME-ROOM-ROUTE-CHAIN-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G94-CUMULATIVE-FREE-DATA-REAUDIT-AND-NEXT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G98-G96-TWO-DRAW-ROUTE-CHECK-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G177-G171-JOINT-LEGAL-ROUTE-PILOT-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G205-GLM-MULTIWHITE-AUTHOR-REVIEW-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, HERE / "G206-COVERAGE-PIVOT-AUDIT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/action_value.py"),
    _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/interface.py"),
)
FIELDS = ("status", "mechanism", "decision_rule", "available_fields",
          "memory_and_recovery", "distinct_from_closed", "example_predictions",
          "ordinary_highfan_tradeoff", "execution_bound", "behavior_gate",
          "full_table_gate", "falsifier", "uncertainty")


def digest(path: Path) -> str:
    """保存原字节摘要；不打印或保存认证补丁内容。"""

    return sha256(path.read_bytes()).hexdigest()


def prompt() -> str:
    """明确评分器限制、包装器可用事实和已否证的旧机制。"""

    return """你是杭麻 Bot 的离线启发式算法作者。只返回一个严格 JSON 对象，不调用工具、不执行代码、不编辑文件。证据不足以提出真正新机制时，status 必须写 infeasible；不要用愿景代替算法。

任务：给出**一条**可证伪的广覆盖弃牌策略机制，目标是改善弃牌后自然成面、加快进入可胡入口，同时保住普通胡并提高白板可用于爆头/财飘的真实机会。冻结 R18 v2 是唯一基线，尚无新策略获准发布。最终必须在新 H/M 异质对手池、同牌山、四座换位的全部完整桌证明净分至少 +2/桌、根级 95% 下界>0、两池同号，并过规则、时限、接线门。

已确认的证据边界：
- G206：多白近听冲突仅 27/909 桌；两权重条件值明显且高番不退仅 4 桌，不能作为单独主入口。强手更广普通进张动作分歧横跨 179/310 桌，但历史强手动作不是收益标签。
- G94：349 个强手严格更广码数和容量的动作里，235 个无白；冻结父代基础牌效 349/349 支持更宽动作，却常被熟牌、风险、桌分风格项反转。G88 简单去熟牌奖励提高模仿率却在 H/M 整桌亏分。
- G69：玄武同房首次一摸胡入口 750 对我方 686，二番以上入口 110 对 62；同状态单窗强手动作基本不产生独有立即入口，差距更可能经过多次本人行动。腾蛇高番兑现更强但入口差小。这是不同手牌的观察差，不是因果收益。
- G98/G99/G177：现有两摸树在多数一向听冲突不能区分，分别优化普通/七对/高番可能拼接不同后继弃牌；同一合法叶五轴 Pareto 在 12 个旧失败窗几乎总不可比。不能把这两种量具直接当新的效用函数。
- G168/G171/G193 的静态扩大一步进张或加保护都未在完整桌稳定增益；G205 提案因假设不存在的基线评分字段、在受限函数里调用规则/时钟、数值阈值自相矛盾而拒绝。

**可实现接缝只选一种，不得混用：**
A. 现有受限 `score_actions(view)`：只能读取 `view` 内 `visible_state` 与合法动作的 action_key/action_type、综合/普通/七对向听、各逐码公开容量、即时胡与路线、baotou_after、family_progress；不能 import、读时钟/磁盘/网络、调用 HangmaRules、读取 R18 基线分或 risk_units、维护跨窗口记忆。若选 A，必须给完全无状态纯算术且与旧宽度/七对/P28 行为实质不同的算式。
B. 离线研究用 `BotPolicy` 包装器：先调用冻结 R18 v2 得 `DecisionPlan`，然后可读取当前 `DecisionRequest.observation`、`request.rules.legal_candidates[*].facts`、全部 `RankedCandidate.total_score/score_trace`，仅重排已经合法的候选。可维护按 `(game_id,round_no,seat)` 隔离的有限内存，但必须能由当前玩家可见观察加已确认本人历史恢复；重复窗口、序号缺口、进程重启或动作未获确认时回退父代。首次候选不得依赖上一时刻尚未存在的意图。不能在 1 秒响应窗做后继搜索；当前目标只考虑 3 秒正常摸打窗。不得在包装器额外读取隐藏世界、真实未来或网络；若需要新增生产规则事实，明确写 infeasible 和具体字段/上界，别自行重写胡牌/向听规则。

目标是**不同于 G168/G171/G193/G88/P28** 的动作决策结构，不能只改宽度、熟牌或风险的固定权重或阈值。若提出跨窗状态，必须定义进入、保持、退出、失败回退，且说明为何整桌从首到尾执行可能优于单窗标签。请尤其解释：两动作同向听、备选普通进张更广时，什么时候不应改（高番/七对/弃熟牌风险），什么时候应改；不能把公开未见容量当真实牌墙概率。

只输出 JSON；以下键都必须是字符串：status（proposed/infeasible）、mechanism、decision_rule（含确定性排序、阈值来源及未知处理）、available_fields（逐字段注明 A/B 接缝和代码字段名）、memory_and_recovery、distinct_from_closed（逐条对 G168/G171/G193/G88/P28，给可机检的动作去重条件）、example_predictions（给普通宽面正例与高番损失负例、白板有无各一，不硬编码牌谱 ID；不能无法得知还声称确定预测）、ordinary_highfan_tradeoff（同一路线的机会成本，不把不同叶价值相加）、execution_bound（候选数、牌码数、操作复杂度和 3 秒窗最坏时间设计）、behavior_gate（旧 91 房结果盲触达/精确旧动作重合/普通胡保护如何审计）、full_table_gate（未见 H/M 根四座同墙完整桌与独立确认）、falsifier（何时停线）、uncertainty。提出候选不等于已经证明增益。"""


def main() -> None:
    """单次无工具调用；保留原答、耗时及来源摘要供复核。"""

    if not all(path.is_file() for path in INPUTS):
        raise FileNotFoundError("G207 来源证据缺失")
    patches = (_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml"),
               _project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml"), ROUTE)
    if not all(path.is_file() for path in patches):
        raise FileNotFoundError("G207 已授权模型通道配置缺失")
    OUT.mkdir(parents=True, exist_ok=True)
    prompt_path = _project_file(_PROJECT_ROOT, OUT / "prompt.txt")
    answer_path = _project_file(_PROJECT_ROOT, OUT / "answer.txt")
    call_path = _project_file(_PROJECT_ROOT, OUT / "call.json")
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G207 原提示或答卷存在，拒绝重复请求")
    prompt_path.write_text(prompt(), encoding="utf-8")
    argv = ["dsh", "--profile", "headless",
            "--patch", str(patches[0]), "--patch", str(patches[1]),
            "--patch", str(patches[2]), prompt()]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g207-glm-") as state_dir:
        try:
            proc = subprocess.run(argv, cwd=ROOT,
                                  env=dict(os.environ, DSH_HOME=state_dir),
                                  capture_output=True, text=True, timeout=1200,
                                  check=False)
            code, answer, diagnostic = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as error:
            code = None
            answer = (error.stdout.decode("utf-8", "replace")
                      if isinstance(error.stdout, bytes) else error.stdout or "")
            diagnostic = (error.stderr.decode("utf-8", "replace")
                          if isinstance(error.stderr, bytes) else error.stderr or "")
    answer_path.write_text(answer, encoding="utf-8")
    try:
        parsed = json.loads(answer)
        valid = (isinstance(parsed, dict)
                 and parsed.get("status") in ("proposed", "infeasible")
                 and all(isinstance(parsed.get(name), str) for name in FIELDS))
    except json.JSONDecodeError:
        valid = False
    record = {
        "schema": "g207-glm-broad-route-author/1",
        "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
        "reasoning_effort_requested": "max",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "exit_code": code, "valid_json_contract": valid,
        "prompt_sha256": digest(prompt_path), "answer_sha256": digest(answer_path),
        "answer_chars": len(answer),
        "diagnostic_sha256": sha256(diagnostic.encode()).hexdigest(),
        "diagnostic_bytes": len(diagnostic.encode()),
        "route_patch_sha256": digest(ROUTE),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path)
                         for path in INPUTS},
        "script_sha256": digest(Path(__file__)),
        "scope": "离线作者文本；须独立检验数学、合同与行为，禁止直接上线",
    }
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                   indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in (
        "exit_code", "valid_json_contract", "elapsed_seconds", "answer_chars")},
        ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
