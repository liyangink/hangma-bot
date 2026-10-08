#!/usr/bin/env python3
"""G205：一次受限 GLM 5.3 离线作者提案，原答不可直接执行。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g205-glm-multiwhite-author-20260929')
CHANNEL = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch'))
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
INPUTS = (
    _project_file(_PROJECT_ROOT, HERE / "G203-FUTURE-CATCH-PLAY-REACH-RESULT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, HERE / "G204-MULTIWHITE-TWO-ACTION-CLAIM-RESULT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, HERE / "evidence/g204-multiwhite-two-action-claim-20260929/result.json"),
    _project_file(_PROJECT_ROOT, HERE / "G171-PARETO-WIDTH-DEVELOPMENT-RESULT-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "G193-EARLY-THREE-SHANTEN-DEVELOPMENT-RESULT-2026-09-29.md"),
)
FIELDS = ("status", "mechanism", "formula", "visible_inputs", "novelty",
          "ordinary_and_seven_guard", "negative_controls", "runtime_bound",
          "behavior_probe", "falsifier", "uncertainty")


def digest(path: Path) -> str:
    """仅存文档与产物的 SHA-256，不回显认证补丁原文。"""

    return sha256(path.read_bytes()).hexdigest()


def prompt() -> str:
    """给作者可否证的正反结构事实，限制为纯评分接缝。"""

    return """你是杭麻 Bot 的离线启发式算法作者。只返回一个严格 JSON 对象；不调用工具、不执行代码、不编辑文件。若证据不足以给出能超越静态宽度的具体机制，status 写 infeasible，并诚实说明所需行动前事实。

任务：提出**一条**可在现有合法弃牌的 score_actions(view) 纯评分接缝中实现的轻量排序机制，解决“弃牌后自然有效进张面过窄，面子迟迟不自然成形，白板无法留作爆头／财飘”，但必须保护普通胡、七对及风险。目标是对冻结 R18 v2 在未见牌山、换座位、异质 H/M 对手池的完整桌净积分显著增益；本提示没有提供这种增益证据。

已核规则：杭麻只自摸，白板为财神；普通型/七对、爆头、财飘、抓打限制及结算必须由生产 HangmaRules 决定。在线只读当前 PlayerObservation 与生产合法动作事实。每个动作已有普通型/综合/七对向听、逐码有效牌与公开未见容量、即时条件胡路线、当前弃牌风险等。公开未见容量包括他家暗手，绝不是墙内抽取概率。未知事实弃权；现有合法保底、即时胡、动作期限 1 秒/3 秒和发布包边界不得改动。不得用未来牌墙、他家暗手、赛后事实或任意“强手会弃某牌”的神谕。

发展证据：G203 对 91 间官方父代房核得 29 个多白近听双弃牌窗/25 房，备选与父代同普通/综合/七对向听、保留白板且自然普通型有效码更宽至少 1 种、公开容量多至少 3 张，七对容量不退。后续第 1/2/3 次本人正常摸牌自由到达为 29/19/14；第三摸前本人成胡 12、他家先胡 3；11/29 有本人吃碰杠。G204 在全部 29 窗用生产规则算两次本人摸牌可胡或弃胡续行，并独立探针吃碰全部合法跟打。备选两摸条件总胡分在第二摸到达权重 1.0/0.5 均为 18 正，较保守 0.5 时高番仅 3 正/21 平/5 负；局部高番鸣牌机会备选独有 3 窗，父代独有 2 窗。它们都不是赛事概率，且两摸值与局部鸣牌机会不能相加。

三个作者入口的反例约束：
1. a_906902b7c7f1：备选第一摸直接可胡公开容量多 7，权重 0.5 的总胡分 +2.428 但高番差为 0；另有一项备选独有高番吃牌机会。不能把它说成已经证明追大牌更强。
2. a_9f5d90ba56ec：第一摸可胡容量多 2，权重 0.5 的总分及高番均约 +1.523；弃胡续行分支只在权重 1.0 与父代不同。不能把 1.0 当真实存活率。
3. a_d539acd906b5 三白窗：两臂第一摸胡容量相同；权重 0.5 总分仅 +0.073、普通 +0.075、高番 −0.002，同时备选独有两个假设上家弃牌时的高番吃牌机会。不能把这两个机会当抵消高番损失的概率收益。
负控：a_f9a057a58973 也有备选独有高番鸣牌机会，但两摸总分持平；a_0beadd7c20ec 两摸总分为正而高番下降；a_a2dd84116fa9 高番上升但总分下降。全部 29 窗中还有 26 窗未过作者入口。旧 G168/G171/G193 已证明静态加宽、即时保护或换阈值不能稳定转化成 H/M 完整桌增益；G106 单独局部鸣牌机会也不是到达概率。不得换名复述它们。

仅输出 JSON；以下键全部必须是字符串：status（proposed 或 infeasible）、mechanism（中文一句）、formula（精确可实现伪码，定义所有阈值/归一化/缺证行为）、visible_inputs（逐字段来源）、novelty（在同普通/七对向听和同逐码一步有效张向量的两个动作上，如何给出不同排序；若做不到说清楚）、ordinary_and_seven_guard（如何守住普通速胡与七对，不只说“不退”）、negative_controls（对上面正例及至少三个负控分别预测偏好和原因；不得因看过这些例子逐窗硬编码）、runtime_bound（动作数、牌码数和最坏计算复杂度，说明生产规则复用）、behavior_probe（新结果盲父代表上如何核合法改选、旧失败行为去重和低成本）、falsifier（什么覆盖/数学/桌赛结果立即停线）、uncertainty（哪些概率不可从当前证据推得）。提案只是机制假设，不能自称已证明增分。"""


def main() -> None:
    """一次已授权禁工具调用；保存原答、耗时与不可逆诊断摘要。"""

    if not all(path.is_file() for path in INPUTS):
        raise FileNotFoundError("G205 作者证据缺失")
    if not all(path.is_file() for path in (
            _project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml"), _project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml"),
            ROUTE)):
        raise FileNotFoundError("G205 已授权无工具模型通道缺失")
    OUT.mkdir(parents=True, exist_ok=True)
    prompt_path = _project_file(_PROJECT_ROOT, OUT / "prompt.txt")
    answer_path = _project_file(_PROJECT_ROOT, OUT / "answer.txt")
    call_path = _project_file(_PROJECT_ROOT, OUT / "call.json")
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G205 原提示或答卷已存在，拒绝重复请求")
    prompt_path.write_text(prompt(), encoding="utf-8")
    argv = ["dsh", "--profile", "headless",
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")),
            "--patch", str(ROUTE), prompt()]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g205-glm-") as state_dir:
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
        "schema": "g205-glm-multiwhite-author/1",
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
        "scope": "离线作者文本；不得直接执行或把其自报收益当证据",
    }
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                   indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in (
        "exit_code", "valid_json_contract", "elapsed_seconds", "answer_chars")},
        ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
