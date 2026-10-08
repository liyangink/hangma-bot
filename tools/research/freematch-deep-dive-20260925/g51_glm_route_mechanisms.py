#!/usr/bin/env python3
"""G51：向已授权 GLM 5.3 请求两条离线路线机制假设，记录原答并隔离执行。"""

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


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g51-glm-route-mechanisms-20260927')
G50 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g50-g49-route-forensic-20260927/result.json')
G50_ANALYSIS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g50-g49-route-forensic-20260927/analysis.json')
G49 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-novel-ordinary-route-expansion-20260927/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G51-GLM-ROUTE-MECHANISMS-PREREG-2026-09-27.md')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
CARDS = {
    "a_dual_route_exit": "构造普通型与七对两条逐码路线的同窗弃牌比较及后续退出规则。不能只比较向听、有效张总数、自然缺口或手留白数；要求当前可见事实就能重算、七对机会不能被普通型改进暗中牺牲。",
    "b_timing_guard": "构造动作特异的普通速胡/高番等待时机保护。要区分两张合法弃牌可能给他家吃碰和自己后续自摸的机会；公开未见数只作上界，不能当牌墙概率或他家暗手预测真值。不能重复 G11 固定风险/宽度交换。",
}
FIELDS = ("status", "name", "mechanism", "visible_inputs", "formula", "entry_exit",
          "difference_from_g49", "ordinary_hu_and_pairs_guard", "counterexample",
          "bounded_operations", "outcome_blind_gate")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _examples() -> str:
    """把四张已看开发桌压成事实卡；后续和桌分明确标为赛后诊断。"""

    frozen = json.loads(G50.read_text(encoding="utf-8"))
    wanted = (("M", 5, 3), ("M", 9, 0), ("H", 12, 0), ("M", 11, 3))
    rows = {(row["mix"], row["root"], row["seat_group"]): row for row in frozen["rows"]}
    if not all(key in rows for key in wanted):
        raise ValueError("G51 G50 正反例身份漂移")
    cases = []
    for key in wanted:
        row = rows[key]
        first = {}
        next_one = {}
        for name, dest in (("first", first), ("next", next_one)):
            for arm in ("baseline", "candidate"):
                source = row[f"{name}_{arm}"] if name == "first" else row[f"{arm}_next_two"][0]
                dest[arm] = {field: source[field] for field in
                             ("choice", "standard_shanten_after", "seven_pairs_shanten_after",
                              "combined_shanten_after", "natural_standard_need_after", "white_after")}
                if name == "next":
                    dest[arm]["drawn_tile"] = source["drawn_tile"]
        cases.append({"case": f"{key[0]}-{key[1]}-{key[2]}",
                      "first_visible_facts": first,
                      "post_action_diagnostic_not_online": {
                          "next": next_one, "same_intervening_actions": row["same_intervening_actions"],
                          "candidate_first_hand_result": row["candidate_hand_result"]["details"],
                          "table_delta": row["table_delta"]}})
    return json.dumps(cases, ensure_ascii=False, separators=(",", ":"))


def prompt_for(key: str, card: str, cases: str) -> str:
    return f"""你是杭麻 Bot 的离线算法作者。只输出一个严格 JSON 对象；不调用工具，不写完整源码。任务卡 {key}：{card}

事实：R18 v2 评分以综合向听和当前有效张为骨架。G49 已经在合法胡不可用、弃后持白、七对未听的摸打窗，将综合向听不退、七对不退、普通型向听及全留白自然缺口各减 1、父代评分差不超过 10 的合法非白弃牌放到首位；若旧 G10 无综合有效张损失入口存在则弃权。G49 官方历史轨迹有 102 个独有改选；新 H/M 192 组配对完整桌中实际改选 34 次，H +0.479、M +2.531、合并 +1.505 分/桌，低于 +2 继续门。23 张触达桌中 13 张变分；16 张首弃后他家动作序列和下一次真实摸牌相同，其中 13 张下一弃普通型自然缺口仍较低，但 16 张手留白数都相同，整桌 8 正、2 负、6 平。两张最大正分最终七对爆头，两个严格同路径负例的自然缺口同样较低。自然缺口改善不等于白板用途/整桌净分改善。

官方 v34：只能自摸胡；白板是财神，不可吃碰杠胡；爆头由生产规则按摸前物理可得牌判断；财飘需已有爆头状态并弃白走合法链；抓打圈非圈主只能摸切，末 20 张留墩。线上只允许读取 PlayerObservation、生产 HangmaRules 的合法候选与 shanten_after / standard_shanten_after / seven_pairs_shanten_after、useful_tiles / standard_useful_tiles / seven_pairs_useful_tiles 的逐码公开剩余估计，以及生产 count_unseen_tiles。公开未见包含他家暗手，不是墙概率。未知不能按零。保底合法动作先于任何计算存在；只许重排合法弃牌，不改胡/吃碰杠、规则、网络、模拟器或结算。每次调用最多 14 个弃牌、34 种牌码；不要提出完整未来牌墙枚举或不可恢复私有状态。

四个已看开发例，仅供构思和反证；first_visible_facts 可由当前规则重算，post_action_diagnostic_not_online 的下一牌/结算绝不可作为在线特征：{cases}

请提出**一个**与 G49、G10、G11 风险宽度、P28 两步宽度、G30 边张键、G43 理想三摸不同的有限机制；若当前输入不能提供可靠可编码新量，就诚实回答 status=infeasible。输出 JSON 的全部字段均为短中文字符串：{', '.join(FIELDS)}。status 只能 proposed 或 infeasible。formula 给明确每张牌码怎样计、比较方向、并列回退 R18，不能只写“综合考虑”；entry_exit 必须可由当前观察重建。counterexample 要说明何时自然缺口较低却应拒绝 G49 改选。bounded_operations 给最坏 14×34 量级，outcome_blind_gate 给旧官方轨迹上与 G49 不同的动作及普通胡/七对保护测试，不得把四个已看分数当准入证据。"""


def parse_answer(answer: str) -> tuple[bool, str | None]:
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
    """每卡一次禁工具调用，原答只落项目证据，不执行任何候选代码。"""

    prompt = prompt_for(key, card, cases)
    prompt_path, answer_path, call_path = (_project_file(_PROJECT_ROOT, OUT / f"{key}.{suffix}")
                                           for suffix in ("prompt.txt", "answer.txt", "call.json"))
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G51 已有逐卡调用产物，拒绝重复发送：" + key)
    prompt_path.write_text(prompt, encoding="utf-8")
    argv = ["dsh", "--profile", "headless", "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")), "--patch", str(ROUTE), prompt]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"g51-{key}-") as state_dir:
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
    record = {"schema": "g51-glm-route-mechanism-call/1", "key": key,
              "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
              "reasoning_effort_requested": "max", "prompt_sha256": sha(prompt_path),
              "answer_sha256": sha(answer_path), "answer_chars": len(answer),
              "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
              "route_patch_sha256": sha(ROUTE),
              "g50_result_sha256": sha(G50), "g50_analysis_sha256": sha(G50_ANALYSIS),
              "g49_result_sha256": sha(G49),
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "exit_code": code, "failure_kind": failure,
              "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
              "diagnostic_bytes": len(diagnostic.encode()),
              "valid_json_contract": valid, "parse_error": parse_error,
              "scope": "离线文本假设，不执行生成代码或接纳任何桌分"}
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    return record


def main() -> None:
    """冻结来源与两张卡；并发只影响墙钟，不共享作者会话。"""

    if not PREREG.exists() or not G50_ANALYSIS.exists():
        raise ValueError("G51 预登记或 G50 证据缺失")
    OUT.mkdir(parents=True, exist_ok=True)
    cases = _examples()
    manifest = {"schema": "g51-glm-route-mechanisms/1",
                "provider": "zai-coding-cn", "model": "glm-5.3", "reasoning_effort": "max",
                "max_author_calls": 2, "concurrency": 2,
                "cards": CARDS, "case_sha256": hashlib.sha256(cases.encode()).hexdigest(),
                "g50_result_sha256": sha(G50), "g50_analysis_sha256": sha(G50_ANALYSIS),
                "g49_result_sha256": sha(G49), "prereg_sha256": sha(PREREG),
                "script_sha256": sha(Path(__file__))}
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != serialized:
        raise ValueError("G51 任务清单或来源摘要漂移")
    manifest_path.write_text(serialized, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(one, key, card, cases): key for key, card in CARDS.items()}
        for future in as_completed(futures):
            record = future.result()
            print(json.dumps({key: record[key] for key in
                              ("key", "exit_code", "failure_kind", "elapsed_seconds",
                               "answer_chars", "valid_json_contract", "parse_error")},
                             ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
