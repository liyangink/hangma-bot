#!/usr/bin/env python3
"""G148：向授权的 GLM 5.3 请求一个可否证的一白跨窗口路线机制。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g148-one-white-route-author-20260928')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
INPUTS = (
    _project_file(_PROJECT_ROOT, HERE / "G145-FREE-EXPOSURE-AND-TENPAI-ENTRY-REVIEW-2026-09-28.md"),
    _project_file(_PROJECT_ROOT, HERE / "evidence/g146-first-baotou-wait-capacity-20260928/result.json"),
    _project_file(_PROJECT_ROOT, HERE / "evidence/g147-one-white-first-ready-wait-20260928/result.json"),
    _project_file(_PROJECT_ROOT, HERE / "G140-G142-PLAIN-BAOTOU-PRECURSOR-AND-FREE-DATA-REVIEW-2026-09-28.md"),
)


def sha(path: Path) -> str:
    """记录作者输入与产物的原始字节摘要，不读取密钥内容。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt() -> str:
    """只开放受限评分组件的思想，要求旧机制去重与停线条件。"""
    return """你是杭麻 Bot 的离线启发式算法作者。只返回一个严格 JSON 对象，不调用工具、不编辑文件。请提出一条具体、可执行、可证伪的弃牌排序机制；如果现有可见事实不足，status 写 infeasible。

研究目标：让自然面子更快成形，改善普通胡抢先和一白状态下后续普通型爆头机会，最后以完整桌净积分相对冻结 R18 v2 赢分。官方杭麻只能自摸；白板为财神，爆头与财飘必须经生产 HangmaRules 合法判定；非圈主抓打摸切、末 20 张留墩。线上只许读取当前 PlayerObservation 和生产合法动作事实；公开未见数含他家暗手，是容量上界，绝非真实牌墙概率。禁止未来墙、他家暗手、赛后结果、不可重建的私有路线状态。不得改规则、动作族、评测器、官方适配器；只允许在已有合法保底的 score_actions(view) 里重排合法弃牌。即时胡和已有普通胡/七对路线须保护，未知事实弃权。

新证据：220 房官方自由赛的高值差主要是普通型爆头。31 间可逐窗重建强手同房中，玄武正常摸打窗口 8219 对我方 8342，首次普通型爆头机会单局 88 对 31；腾蛇窗口 9719 对 9800，机会 74 对 46。玄武首次机会中 74/88 在上一正常摸打时已是普通型零向听，我方 29/31；前后白板及副露数均不变且维持零向听的是 43 对 14。首次一白普通胡入口的公开等待容量均值玄武 13.38、我方 12.94；腾蛇 13.32、我方 13.23。已出现爆头机会的我方 77 个首次窗口全部选择了同窗最大爆头容量。首次一白普通胡入口中，玄武实际与 R18 父代弃牌不同时 23 次普通胡等待容量更大、4 次更小；腾蛇是 21 次更大、19 次更小。强手与我方不是同手牌随机对照，不能把强手动作/赛后成功当最优标签。

必须避开已失败路线：G140 从 63 个结果盲强手/父代分歧窗枚举两摸普通型爆头前驱，只有 2 窗有与旧一步宽度不同且保普通胡/七对的信号；G11 静态宽面/风险交换整桌亏分；G88 简单取消熟牌奖励 H/M 异号；G131 普通型影子宽度 H/M 异号；G49 自然缺口改善主要投资落后七对两格的次级路线，扩样未过 +2；G81 公开占用模型直接改弃牌排序两池亏分。不要把这些换系数、换名称再提一次，也不要写末窗爆头固定奖金。

允许使用的动作前字段：visible_state 里的本人手牌、已公开牌河/副露、墙余、座位、庄位、当前桌分和规则状态；每个合法弃牌的综合/普通型/七对向听、对应有效牌码及公开容量，以及下一次本人普通摸牌的生产条件路线与结算明细。不能假设已经有“未来两次完整轨迹概率”字段。若需要精确额外规则计算，请写出输入、输出和最坏复杂度，并说明怎样在生产 HangmaRules 中复用而不复制规则。

输出 JSON 字符串字段必须全有：status（proposed 或 infeasible）、mechanism（中文一句）、formula（可逐合法弃牌实现的公式或精确伪码）、action_specific_novelty（解释在当前向听与逐码有效张向量相同的两动作上如何可能不同；若不能，诚实说明）、ordinary_and_seven_pairs_guard、visible_inputs、behavior_probe（在全新 R18 父代表结果盲验证独有合法改选、至少两个本人窗口与旧失败动作去重）、falsifier（明确覆盖/数学/普通胡或完整桌净分哪一关失败即停）、runtime_bound、reason。所有字段都是字符串，不得声称已经证明增分。最终 H/M 两池四座同墙完整桌新根至少 +2 分/桌、根级 95% 区间下界大于零、双池同正，才可能发布。"""


def main() -> None:
    """一次作者调用，保存原答与用量边界，不执行模型生成的代码。"""
    OUT.mkdir(parents=True, exist_ok=True)
    prompt_path = _project_file(_PROJECT_ROOT, OUT / "prompt.txt")
    answer_path = _project_file(_PROJECT_ROOT, OUT / "answer.txt")
    call_path = _project_file(_PROJECT_ROOT, OUT / "call.json")
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G148 作者调用产物已存在，拒绝重复发送")
    if not all(path.exists() for path in INPUTS):
        raise FileNotFoundError("G148 输入证据不全")
    prompt_path.write_text(prompt(), encoding="utf-8")
    argv = ["dsh", "--profile", "headless",
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")),
            "--patch", str(ROUTE), prompt()]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g148-glm-") as state_dir:
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
    required = ("status", "mechanism", "formula", "action_specific_novelty",
                "ordinary_and_seven_pairs_guard", "visible_inputs", "behavior_probe",
                "falsifier", "runtime_bound", "reason")
    try:
        parsed = json.loads(answer)
        valid = (isinstance(parsed, dict)
                 and parsed.get("status") in ("proposed", "infeasible")
                 and all(isinstance(parsed.get(name), str) for name in required))
    except json.JSONDecodeError:
        valid = False
    record = {
        "schema": "g148-one-white-route-author/1",
        "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
        "reasoning_effort_requested": "max", "elapsed_seconds": round(
            time.monotonic() - started, 3),
        "exit_code": code, "valid_json_contract": valid,
        "prompt_sha256": sha(prompt_path), "answer_sha256": sha(answer_path),
        "answer_chars": len(answer),
        "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
        "diagnostic_bytes": len(diagnostic.encode()),
        "route_patch_sha256": sha(ROUTE),
        "input_sha256": {str(path.relative_to(ROOT)): sha(path)
                         for path in INPUTS},
        "script_sha256": sha(Path(__file__)),
        "scope": "离线作者文本；不得直接执行或把其自报收益当证据",
    }
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
                         + "\n", encoding="utf-8")
    print(json.dumps({name: record[name] for name in (
        "exit_code", "valid_json_contract", "elapsed_seconds", "answer_chars")},
        ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
