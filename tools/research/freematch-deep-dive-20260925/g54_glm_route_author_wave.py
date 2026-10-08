#!/usr/bin/env python3
"""G54 六张互异任务卡的 GLM 5.3 离线作者调用；不执行作者代码。"""

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

import g51_glm_route_mechanisms as g51


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g54-glm-route-author-wave-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G54-GLM-ROUTE-AUTHOR-WAVE-PREREG-2026-09-27.md')
G52 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g52-g49-shared-horizon-20260927/analysis.json')
G53 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g53-route-competition-reach-20260927/result.json')
G50 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g50-g49-route-forensic-20260927/result.json')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
CARDS = {
    "a_primary_natural_structure": "普通型已领先七对的同向听弃牌：提出当前有效张总量和牌种数以外、能在下一至三个本人可行动窗验证的进张结构量；要明确防止 G11 静态宽面失败复现。",
    "b_pairs_to_ordinary_switch": "七对领先时次级普通型投资：正面处理 G52 的 102 个负控，提出同一时域的七对机会成本和普通型追平条件；不许单凭降低自然缺口改选。",
    "c_multi_white_realization": "多白板用途兑现：区分实持、可用百搭、爆头合法资格、财飘合法链及到达时机；给不读取未来牌墙的当前弃牌比较。",
    "d_opponent_response_survival": "他家响应造成的本人再行动机会差：只用已公开牌河、副露、座位和规则来计算动作特异不确定性；不得把对手暗手或观察到的旧父代响应当备选动作真值。",
    "e_recoverable_route_controller": "跨本人窗口的进入／保持／退出：任何时刻仅从当前 PlayerObservation 重建路线状态，不依赖私有回合计数；保持胡牌和七对保护。",
    "f_late_wall_tempo_value": "墙末合法弃牌的速胡与高番保留：区分当前能胡、下一摸可胡与更远期大牌，遵守末 20 张与抓打圈，不修改胡牌动作本身。",
}
FIELDS = ("status", "mechanism", "visible_inputs", "offline_teacher", "online_proxy",
          "entry_exit", "guard", "novelty", "counterexample", "behavior_probe",
          "time_budget_risk", "reason")


def sha(path: Path) -> str:
    """内容摘要用于证据与作者调用去重，不读取凭据正文。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_for(key: str, card: str, cases: str) -> str:
    """用已核规则和负控约束一张任务卡；不把赛后事实作为在线特征。"""

    return f"""你是杭麻 Bot 的离线算法作者，只返回一个严格 JSON 对象，不调用工具，不编辑文件。任务卡 {key}：{card}

项目目标：改进 R18 v2 的弃牌，使自然面子更快、更广成形，同时保护七对与普通速胡，并使白板有更多合法爆头／财飘兑现机会；最终必须在未见 H/M 对手池、同牌山四座完整桌证明显著净分增益。你现在只提出一条**可机检的机制**，不是声称收益已证明。

经生产规则复核的反例：G49 在 102 个合法独有改选窗全部使普通型自然缺口少一格，但父代七对向听均比普通型低两格；候选普通型向听减一，综合／七对向听均不变，根节点白板实持数均不变。双方第一次本人摸牌即时胡价值 102/102 相同；两次本人摸牌、第一次可自由弃牌的条件胡分，候选 63 负、39 平、0 正。G49 在新 H/M 192 组同墙配对桌的平均 +1.505 分/桌未达 +2 门，净增量约 81% 来自两张最终七对爆头的大正桌，不能把它归因于普通型缺口。G53：318 个自然缺口可下降窗里，普通型只落后七对一格的 16 窗中 14 窗已七对听牌；七对未听且当前综合容量不降、近分的仅 2 窗。G14 普通型已领先七对的 483 个同层自然宽面窗触达 315 桌，但只有 9 窗的备选未增加生产当前普通型有效牌种。G11 静态宽面／风险交换在新 H/M 完整桌合并 −0.568 分/桌。G19 两摸后继正向大多由当前有效牌效解释。G51 两份作者公式因跨不同向听层直接相减当前有效张而停线。

杭麻规则依据官方 v34（仓库 2026-09-15 抓取）：只允许自摸胡；白板为财神，不可吃碰杠胡；爆头由摸前任意物理可得牌可胡的生产规则判定；财飘须已有爆头并合法弃白形成连续链；非圈主抓打摸切，末 20 张留墩。线上只能用当前 PlayerObservation、生产 HangmaRules 合法候选和它们的规则事实，以及依法可见的公开牌计数；绝不可读未来墙、他家暗手、赛后结算或不可恢复的私有状态。公开未见张数包含他家暗手，仅是容量上界，不是牌墙概率。未知字段不能当零。合法保底动作先于新计算存在，只可重排合法弃牌，不可改胡/吃碰杠、规则、适配器、模拟器或评测器。允许较昂贵的离线教师，但在线代理须说明有界代价和当前观察可重建性；高分后可另做效率优化。

四个已看开发例仅用于反证。first_visible_facts 可在当前动作前重算；post_action_diagnostic_not_online 的后续牌、他家行动和桌分绝不可作为在线输入：{cases}

若该卡在这些可见输入下没有新信号，诚实返回 status=infeasible；不要把重新命名的向听、当前有效张、自然宽度或固定风险加权冒充机制。若可行，返回 status=proposed，并以简短中文填写全部字段：{', '.join(FIELDS)}。online_proxy 必须给出明确的逐合法弃牌计算、比较方向、并列时回退父代；offline_teacher 说明如何用生产规则的同一未来时域核对普通型、七对和白板用途并标注他家先胡截尾；entry_exit 必须重启后从当前观察重建；guard 明确即时胡、七对听牌和普通速胡保护；counterexample 给本卡会拒绝的具体 G49 或 G11 型反例；behavior_probe 说明结果盲官方轨迹中怎样证明与 G49/G11/P28 不同的合法动作与足量桌覆盖。time_budget_risk 给最坏规模和性能后续验证。reason 不得引用作者自评为证据。所有字段必须是字符串，status 只能 proposed 或 infeasible。"""


def parse_answer(answer: str) -> tuple[bool, str | None]:
    """只验收文本合同；不执行或信任作者自报的规则与收益。"""

    try:
        value = json.loads(answer.strip())
    except json.JSONDecodeError:
        return False, "invalid_json"
    if not isinstance(value, dict) or any(not isinstance(value.get(field), str) for field in FIELDS):
        return False, "missing_or_nonstring_field"
    if value["status"] not in ("proposed", "infeasible"):
        return False, "invalid_status"
    return True, None


def one(key: str, card: str, cases: str) -> dict:
    """一张卡只调用一次；不确定响应写失败记录，不自动重试。"""

    prompt = prompt_for(key, card, cases)
    prompt_path, answer_path, call_path = (_project_file(_PROJECT_ROOT, OUT / f"{key}.{suffix}")
                                           for suffix in ("prompt.txt", "answer.txt", "call.json"))
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G54 作者卡已有产物，拒绝重复调用：" + key)
    prompt_path.write_text(prompt, encoding="utf-8")
    argv = ["dsh", "--profile", "headless", "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")), "--patch", str(ROUTE), prompt]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"g54-{key}-") as state_dir:
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
    record = {"schema": "g54-glm-route-author-call/1", "key": key,
              "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
              "reasoning_effort_requested": "max", "prompt_sha256": sha(prompt_path),
              "answer_sha256": sha(answer_path), "answer_chars": len(answer),
              "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
              "route_patch_sha256": sha(ROUTE), "g52_analysis_sha256": sha(G52),
              "g53_result_sha256": sha(G53), "g50_result_sha256": sha(G50),
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "exit_code": code, "failure_kind": failure,
              "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
              "diagnostic_bytes": len(diagnostic.encode()),
              "valid_json_contract": valid, "parse_error": parse_error,
              "scope": "离线文本机制，不执行作者代码或采纳作者收益主张"}
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    return record


def main() -> None:
    """冻结六张卡与来源摘要，并行仅缩短墙钟，不共享会话。"""

    if not all(path.exists() for path in (PREREG, G52, G53, G50, ROUTE)):
        raise ValueError("G54 预登记、规则或负控证据缺失")
    cases = g51._examples()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "g54-glm-route-author-wave/1", "provider": "zai-coding-cn",
                "model": "glm-5.3", "reasoning_effort": "max", "max_author_calls": 6,
                "concurrency": 2, "cards": CARDS,
                "case_sha256": hashlib.sha256(cases.encode()).hexdigest(),
                "g50_result_sha256": sha(G50), "g52_analysis_sha256": sha(G52),
                "g53_result_sha256": sha(G53), "prereg_sha256": sha(PREREG),
                "script_sha256": sha(Path(__file__))}
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != serialized:
        raise ValueError("G54 作者任务或来源摘要漂移")
    manifest_path.write_text(serialized, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(one, key, card, cases): key for key, card in CARDS.items()}
        for future in as_completed(futures):
            record = future.result()
            print(json.dumps({name: record[name] for name in
                              ("key", "exit_code", "failure_kind", "elapsed_seconds",
                               "answer_chars", "valid_json_contract", "parse_error")},
                             ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
