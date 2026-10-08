#!/usr/bin/env python3
"""G163：基于新开发证据向已授权 GLM 5.3 请求一条可否证的跨行动机制。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g163-multi-route-author-20260928')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
INPUTS = (
    _project_file(_PROJECT_ROOT, HERE / "G159-WHITE-RESERVE-PRODUCTION-COUNT-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G160-MULTI-ACTION-VALUE-SOURCE-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G161-MULTI-ACTION-DEVELOPMENT-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G162-SEVEN-PAIRS-ROUTE-COST-AUDIT-2026-09-28.md"),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt() -> str:
    """只索取一条新的动作前可计算机制，不向作者开放锁定结果。"""
    return """你是杭麻 Bot 的离线算法作者。只返回一个严格 JSON 对象，不调用工具、不编辑文件、不声称收益已证明。请给一个可以在现有 R18 v2 已选出合法保底后重排合法弃牌的**新机制**；若信息不足则 status=infeasible，并指出一个最短可证伪测量。不是写研究综述。

目标：让自然面子更快形成、进张来源更广，最终提高普通速胡与白板爆头/财飘的整桌净分。官方杭麻只能自摸；白板是财神，胡型和抓打圈只以生产 HangmaRules 为准。线上仅能用当前 PlayerObservation（本人手牌、公开牌河/副露/事件、墙余、座位、桌分、规则状态）及生产合法动作事实（普通型/七对/综合向听、逐码有效牌及公开未见容量、当前一摸条件胡型/结算）。公开未见容量包含他家暗手，非墙内概率。不得读未来墙、对手暗手、赛后分数或不可恢复的私有路线状态；未知事实弃权、已有合法胡和普通胡/七对出口须保护。

刚完成的新 H/M 父代表结果：91 房旧静态全保白「独有」入口按生产公开计数由 42 收缩为 1；一步全保白自然向量在一白一向听入口完全重述当前普通型非白有效牌。另有 49 个新根开发窗，严格更宽普通进张备选各在 33 个同世界中只改首弃、后续回 R18 v2。H 窗口均值 +0.341，M −0.321，根级区间都跨零。M/一白备选普通一番收入 +0.827、高番收入 −1.186；双方首次普通听牌时手留白板 309/327 对相同。M 池全部 25 窗七对向听相同，七对当前公开容量差也不稳定解释结果。25 个机制锁定窗未打开。

已失败或等价：全局提高一步宽度/牌种奖金 G11、G58A；理想化两摸 G67/G68、三摸 G43；七对向听/容量硬闸；简单取消熟牌奖励 G88；直接以后验墙内有效张重排 G81；一白普通听牌容量奖金 G150；局部高番机会存在性 G114；旧 G14 Q1 静态路线。不要给这些换权重或改名。GLM 上轮提案的两摸爆头前驱重复 G140，也失败。不要凭 G161 的 M/一白小组事后写阈值。

输出 JSON 字符串字段全部提供：status（proposed/infeasible）、mechanism（中文一句）、observable_feature（精确定义动作前每个弃牌如何计算，写字段和数学或伪码）、decision_rule（触发、保护、退出与未知弃权）、why_action_specific（在当前普通/七对向听和有效张向量相同的两个弃牌上仍可能不同的具体来源，若不可能直说）、non_equivalence（为何不等同上述失败表示）、runtime_bound（最坏复杂度及缓存）、falsifier（什么可见行为/规则/完整桌结果立即停线）、next_test（只用开发根先测什么，何时才可开锁定根）、reason（最可能失败的反例）。不输出策略收益预测；最终必须新 H/M 同牌山四座完整桌合并至少 +2 分/桌、根级 95% 下界>0、双池同号，并过时限/规则/官方门。"""


def main() -> None:
    """一次 GLM max 作者调用，原文和用量元信息留证，不执行答文。"""
    OUT.mkdir(parents=True, exist_ok=True)
    prompt_path = _project_file(_PROJECT_ROOT, OUT / "prompt.txt")
    answer_path = _project_file(_PROJECT_ROOT, OUT / "answer.txt")
    call_path = _project_file(_PROJECT_ROOT, OUT / "call.json")
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G163 作者调用产物已存在，拒绝重复发送")
    if not all(path.exists() for path in INPUTS):
        raise FileNotFoundError("G163 输入证据不全")
    prompt_path.write_text(prompt(), encoding="utf-8")
    argv = ["dsh", "--profile", "headless",
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")),
            "--patch", str(ROUTE), prompt()]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g163-glm-") as state_dir:
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
    required = ("status", "mechanism", "observable_feature", "decision_rule",
                "why_action_specific", "non_equivalence", "runtime_bound",
                "falsifier", "next_test", "reason")
    try:
        parsed = json.loads(answer)
        valid = (isinstance(parsed, dict)
                 and parsed.get("status") in ("proposed", "infeasible")
                 and all(isinstance(parsed.get(name), str) for name in required))
    except json.JSONDecodeError:
        valid = False
    record = {
        "schema": "g163-multi-route-author/1",
        "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
        "reasoning_effort_requested": "max",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "exit_code": code, "valid_json_contract": valid,
        "prompt_sha256": sha(prompt_path), "answer_sha256": sha(answer_path),
        "answer_chars": len(answer),
        "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
        "diagnostic_bytes": len(diagnostic.encode()),
        "route_patch_sha256": sha(ROUTE),
        "input_sha256": {str(path.relative_to(ROOT)): sha(path)
                         for path in INPUTS},
        "script_sha256": sha(Path(__file__)),
        "scope": "离线作者建议；不得直接执行或把自报优势当收益证据",
    }
    call_path.write_text(json.dumps(record, ensure_ascii=False,
                                    sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: record[name] for name in (
        "exit_code", "valid_json_contract", "elapsed_seconds", "answer_chars")},
        ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
