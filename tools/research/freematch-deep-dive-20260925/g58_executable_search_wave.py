#!/usr/bin/env python3
"""G58 四张 GLM 5.3 可执行纯策略作者卡；只保存答卷，不执行作者代码。"""

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

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import g54_glm_route_author_wave as prior


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g58-executable-search-wave-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G58-EXECUTABLE-SEARCH-WAVE-PREREG-2026-09-27.md')
INPUTS = {
    "g11_failure": _project_file(_PROJECT_ROOT, HERE / "G11-SHAPE-RISK-DEVELOPMENT-CLOSED-2026-09-27.md"),
    "g49_expansion": _project_file(_PROJECT_ROOT, HERE / "G49-NOVEL-ORDINARY-ROUTE-EXPANSION-RESULT-2026-09-27.md"),
    "g56_switch": _project_file(_PROJECT_ROOT, HERE / "G56-ROUTE-SWITCH-REACH-RESULT-2026-09-27.md"),
    "g57_tie": _project_file(_PROJECT_ROOT, HERE / "G57-ROUTE-TIE-ENTRY-RESULT-2026-09-27.md"),
    "frozen_parent": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
}
CARDS = {
    "a_contextual_width": "比较当前有效张面与父代风险／牌河／风格评分的冲突。G11 无条件近分摸切更宽在 H/M 全程桌赛为负。提出不同的可见情境条件；不能把 G11 代码换一个阈值重提。",
    "b_white_route_tradeoff": "比较同一动作窗保留白板、普通型和七对型路线的条件机会。G49 次级普通型投资短时域无正胡分，G56/G57 上一领先路线租约几乎无入口；不要使用不可恢复的路线记忆。",
    "c_support_robustness": "同向听、当前公开有效张容量接近时比较逐牌进张分布。P13/G6/G11 的单纯牌种数奖励失败；提出可从当前逐牌支持表计算且在失败反例中弃权的动作条件选择。",
    "d_tempo_dealer": "用当前墙余、庄位、可见他家副露和当前合法弃牌事实，在速胡与保留白板间作条件取舍。只能自摸，末20张留墩；不能把剩余本人摸牌数或他家先胡概率算成确定值。",
}
FIELDS = ("status", "mechanism", "program", "guard", "counterexample", "reason")


def sha(path: Path) -> str:
    """只绑定输入字节；凭据文件只绑定路径外部既有路由，不读取正文。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_for(name: str, task: str) -> str:
    """给作者一个能直接机检的纯函数接口与已知失败边界。"""

    return f"""你是杭麻 Bot 的离线启发式程序作者。只返回一个严格 JSON 对象；不调用工具，不修改文件，不引用未验证的未来事实。任务卡 {name}：{task}

目标：生成一份**可执行、结构独特**的研究策略，在已冻结 R18 v2 对每个合法弃牌评分之后，选择是否用另一合法弃牌替换首选。最终是否有用只由新 H/M 对手池、同牌山四座完整桌净分判定。模型不要声称已证明收益。

唯一允许的函数签名：
def choose(ctx, options):
    ...
    return None  # 或返回 options 中另一个弃牌的 key 字符串

运行器进入函数前已有父代完整合法计划，且已经保证这是正常本人摸牌窗、父代首选是弃牌、没有当前合法立即胡。`options` 是本窗已经评分的**所有合法弃牌**，每个 dict 严格包含：
- key: "discard:牌码"；score: 父代评分 float；is_parent: bool；
- combined/ordinary/seven: 生产规则动作后综合／普通型／七对型向听 int 或 None；
- support/ordinary_support/seven_support: 列表 `{{"tile":牌码,"remaining":0..4}}` 或 None，均为当前公开未见物理容量，**不是牌墙摸牌概率**；
- white_after: 弃后本人实持白板数 int；baotou_after: 生产规则动作后爆头 bool 或 None。
`ctx` 仅含当前 `PlayerObservation` 可恢复值：white_count、own_melds、wall_remaining、dealer（我方是否庄家）、table_rank（1..4）、opponent_melds（三个公开副露组数）、drawn_tile。字段可为 None，未知必须直接 `return None`，不能按零。不得读取 `ctx/options` 以外的变量。

程序只能用纯 Python 的局部变量、if、for、基本数值／列表／字典运算与 len/sum/min/max/any/all/sorted/abs/range；不准 import、定义别的函数或类、属性访问、文件／网络／时间、eval/exec、递归、全局可变状态或私有下划线方法。循环仅能遍历 `options` 及其中的支持表，最多 14 个弃牌×34 个牌种；无返回备选时回退父代。不得产生胡、鸣牌、杠或改变规则事实。程序必须防止 None、bool 冒充数字和跨向听层直接比较有效张总数。

规则：杭麻只允许自摸胡；白板是财神，财飘和爆头资格由生产规则判定；本人已吃两摊不得再吃、非圈主抓打摸切、最后20张留墩均由规则层处理。此函数不能自行改合法动作。R18 当前基础评分约为 `-100×综合向听+公开有效张容量`，另有风险、牌河、风格和专项覆盖。已知负证据：G11 更广牌种／风险交换改变 1,062 窗、触达 607/909 官方父代桌，但新 H/M 全程桌赛 -0.568 分/桌；G49 自然普通型路线扩批 +1.505，未达 +2 且尾部主导；G56 严格普通型/七对领先反转只有13窗，持续持白受保护近分1窗；G57 持白进入两型持平538窗，但受保护近分仅9窗。P13/G6 的直接牌种奖励及 P28 两步宽度亦已失败。可以组合已有特征产生不同**行为**，不要求发明新数学字段；但不得仅改名复跑失败臂或伪造作者自称的新颖性。

请输出严格 JSON，六个字符串字段：status、mechanism、program、guard、counterexample、reason。status 只能是 proposed 或 infeasible。proposed 时 program 必须是完整 Python `def choose(ctx, options):` 源码字符串，包含至少一个明确 `return None` 弃权路径、一个防守普通胡／七对／白板机会的可机检条件、一个对同窗不同弃牌的比较；只可返回备选 key 或 None。不要 Markdown 代码围栏。counterexample 必须说明具体哪类 G11/G49/G56/G57 负例会被拒绝，不能自称测试过旧窗口。guard 解释未知、合法性及开销。若只有静态宽度或未来不确定量，诚实返回 infeasible，program 给空字符串。
"""


def parse_answer(answer: str) -> tuple[bool, str | None]:
    """只验收答卷结构；不执行模型程序或采纳其收益主张。"""

    try:
        payload = json.loads(answer.strip())
    except json.JSONDecodeError:
        return False, "invalid_json"
    if not isinstance(payload, dict) or any(not isinstance(payload.get(k), str) for k in FIELDS):
        return False, "missing_or_nonstring_field"
    if payload["status"] not in ("proposed", "infeasible"):
        return False, "invalid_status"
    return True, None


def one(name: str, task: str) -> dict:
    """每张卡仅一次受控调用；结果不确定则记录，不自动重试。"""

    prompt = prompt_for(name, task)
    prompt_path, answer_path, call_path = (_project_file(_PROJECT_ROOT, OUT / f"{name}.{suffix}")
                                           for suffix in ("prompt.txt", "answer.txt", "call.json"))
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G58 作者卡已有产物：" + name)
    prompt_path.write_text(prompt, encoding="utf-8")
    argv = ["dsh", "--profile", "headless", "--patch",
            str(prior.CHANNEL / "credentials.patch.yml"), "--patch",
            str(prior.CHANNEL / "no-tools-eval.patch.yml"), "--patch",
            str(prior.ROUTE), prompt]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"g58-{name}-") as state_dir:
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
    record = {
        "schema": "g58-executable-search-call/1", "card": name,
        "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
        "reasoning_effort_requested": "max", "prompt_sha256": sha(prompt_path),
        "answer_sha256": sha(answer_path), "answer_chars": len(answer),
        "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
        "route_patch_sha256": sha(prior.ROUTE),
        "input_sha256": {key: sha(path) for key, path in INPUTS.items()},
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "exit_code": code, "failure_kind": failure,
        "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
        "diagnostic_bytes": len(diagnostic.encode()),
        "valid_json_contract": valid, "parse_error": parse_error,
        "scope": "离线候选程序原文；未执行、未通过规则或整桌收益门",
    }
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    return record


def main() -> None:
    """冻结四卡及所有输入摘要，并发仅缩短墙钟，不共享作者会话。"""

    if not all(path.exists() for path in (PREREG, prior.ROUTE, *INPUTS.values())):
        raise ValueError("G58 作者合同或来源缺失")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "g58-executable-search-wave/1", "provider": "zai-coding-cn",
        "model": "glm-5.3", "reasoning_effort": "max", "max_author_calls": len(CARDS),
        "concurrency": 2, "cards": CARDS,
        "input_sha256": {key: sha(path) for key, path in INPUTS.items()},
        "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
    }
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != serialized:
        raise ValueError("G58 作者任务或输入漂移")
    manifest_path.write_text(serialized, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(one, name, card): name for name, card in CARDS.items()}
        for future in as_completed(futures):
            record = future.result()
            print(json.dumps({key: record[key] for key in
                              ("card", "exit_code", "failure_kind", "elapsed_seconds",
                               "answer_chars", "valid_json_contract", "parse_error")},
                             ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
