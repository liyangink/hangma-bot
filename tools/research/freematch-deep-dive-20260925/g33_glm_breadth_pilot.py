#!/usr/bin/env python3
"""G33：按 16 张机制卡独立调用离线 GLM 5.3，保留原答而不执行代码。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g33-glm-breadth-pilot-20260927')
G32 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927/analysis.json')
TRACE_A = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g33-first-divergence-20260927/result-detailed.json')
TRACE_B = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g33-first-divergence-20260927/contrast.json')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
CARDS = {
    "a01_disjoint_natural": "自然成面：同样即时有效牌时，互不复用手牌的自然面子完工路线能否区别两次以上摸打的韧性。",
    "a02_wait_diversity": "自然成面：牌码容量相同但进张来源集中度不同，如何避免把公开未见张数当作牌墙概率。",
    "a03_route_bottleneck": "自然成面：将牌/搭子共享牌的瓶颈，要求按物理四张上限和重叠手牌去重。",
    "a04_early_discard": "自然成面：同分早巡弃字牌、边张、中张的机会成本；G30 单一边张键在 H/M 异号。",
    "b01_single_white": "白板路线：持一白时先用自然牌成面、后巡保白可爆头的可见必要条件及普通胡代价。",
    "b02_multiple_white": "白板路线：持两白及以上时，合法爆头后财飘链的进入、退出和普通胡机会成本。",
    "b03_pairs_standard": "白板路线：普通型与七对可能分叉，不能把白板固定配在某一对子或假设七对必优。",
    "b04_baotou_exit": "白板路线：自然成面为何可能提升真实爆头机会，如何在他家先胡前及时退出追大牌。",
    "c01_public_claim": "时间风险：弃牌对下家吃/他家碰杠的公开合法响应影响；不能假定避鸣总有利。",
    "c02_opp_race": "时间风险：只用他家公开河和副露作竞速背景，必须形成同窗口动作特异差值。",
    "c03_wall_timing": "时间风险：抓打圈与末 20 张留墩改变未来本人摸牌可达性，不把理想三摸作净分。",
    "c04_score_stage": "时间风险：庄家/积分/阶段排名怎样调节早胡与守白，但不能直接臆造他家暗牌。",
    "d01_plain_hu_guard": "保护状态：自然宽度奖励如何保护即时普通胡，G11/P28 的宽度方案已负收益。",
    "d02_regime_exit": "保护状态：当可见牌形已失去高番路线，怎样有明确证据地退出而不在窄面停留。",
    "d03_memory_rebuild": "保护状态：跨本人动作窗路线身份如何由合法公开历史重建，缺历史时安全降级。",
    "d04_novelty_control": "保护状态：构造与 G10/G11/P28/G30 行为指纹不同的受限弃牌算子及负对照。",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def examples() -> str:
    """只摘开发重放的同观察首处分歧；不提供赛后牌墙或逐局结算标签。"""

    rows = json.loads(TRACE_A.read_text(encoding="utf-8"))["rows"]
    rows += json.loads(TRACE_B.read_text(encoding="utf-8"))["rows"]
    selected = []
    for row in rows:
        difference = row["first_divergence"]
        if difference["kind"] != "same_observation_different_action":
            continue
        left, right = difference["baseline"], difference["candidate"]
        keys = (left["selected_action_key"], right["selected_action_key"])
        selected.append({"case": row["target"], "round_no": left["round_no"],
                         "hand": left["my_hand"], "drawn_tile": left["drawn_tile"],
                         "parent_action": keys[0], "g30_action": keys[1],
                         "progress": {key: left["legal_progress"][key] for key in keys}})
    if len(selected) != 5:
        raise ValueError("G33 开发首处分歧例数漂移")
    return json.dumps(selected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def prompt_for(key: str, card: str, cases: str) -> str:
    return f"""你是杭麻 Bot 的离线启发算子作者。只输出严格 JSON 对象，不加 Markdown，不调用工具。任务卡 {key}：{card}

目标：在冻结 R18 v2 上找到**两种结构不同**、可由同一动作前可见状态计算的受限弃牌改选机制，而不是同公式换两个阈值。可以诚实标记某个机制不可行，但应先尝试提出能被具体反例证伪的机制。输出 hypotheses 数组，恰好两个对象，每个包含 name、mechanism、applicability、visible_inputs、bounded_pseudocode、worst_case_operations、rule_counterexample、old_behavior_difference、negative_control、falsification_gate、ordinary_hu_cost_guard。不要输出完整 R18 代码。

已核规则：官方杭麻 v34 只自摸胡，白板是财神，白板本身不可吃碰杠胡；抓打圈非圈主只能摸切，末 20 张留墩。爆头由生产规则判断“摸前任意物理可得牌可胡”，财飘需已爆头后弃白形成合法链。只重排生产 HangmaRules 已给的合法弃牌；不能修改胡、吃碰杠、结算、动作提交或规则。线上只读 PlayerObservation、合法动作和生产给出的向听/逐码有效牌、公开河/副露/积分、真实公开历史；不能读他家暗手、未来牌墙或赛后信息。未知事实不能当零。每码最多四张，公开未见数量不是墙内概率。最坏操作量必须可核，不依赖枚举所有未来整桌路径。

研发事实：R18 v2 基础分主要是 −100×综合向听＋公开有效张容量，并有杭麻白板/胡法、风险和积分覆盖。G30 在持一白、同标准与综合逐码有效牌、父代分差≤3 时按“先弃字牌/边张”改选，冻结官方父代轨迹 608 个合法改选、触达 351/909 桌；G31 的 64 桌小批 +1.375 分/桌，但全新 G32 384 桌合并 −0.214，H −1.844、M +1.417，未过开发门。G11 固定风险/宽面交换、P28 两步宽度已未过收益门。下列仅为 G32 开发根中两臂首处分歧的本人可见牌例，**没有给你收益标签**，不得猜答案：
{cases}

每个机制须说明为何不会退化为 G30 的边张字典序键、G11/P28 的宽度奖金或即时向听换常数。对一个牌例给可复算的方向，也给会判错的反例；不能声称牌例的后续积分由首弃牌单独造成。新候选先过 v34 规则、数学/字段、独有可达行为与 1/3 秒时限，再用全新 H/M 同墙四座完整桌验净分。无需声称一定提升。JSON 顶层仅有 task_id 和 hypotheses，task_id 必须为 {key}。"""


def parse_answer(answer: str, key: str) -> tuple[bool, str | None, int]:
    """仅检查机器合同，不把 JSON 合法当算子有效。"""

    try:
        value = json.loads(answer.strip())
    except json.JSONDecodeError:
        return False, "invalid_json", 0
    if not isinstance(value, dict) or value.get("task_id") != key:
        return False, "invalid_task_id", 0
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) != 2:
        return False, "invalid_hypothesis_count", 0
    fields = ("name", "mechanism", "applicability", "visible_inputs",
              "bounded_pseudocode", "worst_case_operations", "rule_counterexample",
              "old_behavior_difference", "negative_control", "falsification_gate",
              "ordinary_hu_cost_guard")
    if any(not isinstance(item, dict) or any(field not in item for field in fields)
           for item in hypotheses):
        return False, "missing_hypothesis_field", 0
    return True, None, len(hypotheses)


def one(key: str, card: str, cases: str) -> dict:
    """独立状态调用并保留原文；传输故障与算法答卷分开。"""

    prompt = prompt_for(key, card, cases)
    prompt_path = _project_file(_PROJECT_ROOT, OUT / f"{key}.prompt.txt")
    answer_path = _project_file(_PROJECT_ROOT, OUT / f"{key}.answer.txt")
    record_path = _project_file(_PROJECT_ROOT, OUT / f"{key}.call.json")
    if any(path.exists() for path in (prompt_path, answer_path, record_path)):
        return {"key": key, "skipped": "existing_artifact"}
    prompt_path.write_text(prompt, encoding="utf-8")
    argv = ["dsh", "--profile", "headless", "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")), "--patch", str(ROUTE), prompt]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"g33-{key}-") as state_dir:
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
    parsed, parse_error, count = parse_answer(answer, key) if code == 0 else (False, "call_failure", 0)
    record = {"schema": "g33-glm-call/1", "key": key,
              "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
              "reasoning_effort_requested": "max", "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
              "route_patch_sha256": sha(ROUTE),
              "elapsed_seconds": round(time.monotonic() - started, 3), "exit_code": code,
              "answer_chars": len(answer), "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
              "diagnostic_sha256": hashlib.sha256(diagnostic.encode()).hexdigest(),
              "diagnostic_bytes": len(diagnostic.encode()), "failure_kind": failure,
              "valid_json_contract": parsed, "parse_error": parse_error,
              "hypotheses_count": count,
              "scope": "offline author hypotheses only; no generated code executed or score accepted"}
    record_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return record


def main() -> None:
    """先冻结 16 卡身份，再最多三并发完成作者调用。"""

    OUT.mkdir(parents=True, exist_ok=True)
    cases = examples()
    manifest = {"schema": "g33-glm-manifest/1", "model": "zai-coding-cn/glm-5.3 max",
                "concurrency": 3, "cards": CARDS, "g32_analysis_sha256": sha(G32),
                "trace_source_sha256": [sha(TRACE_A), sha(TRACE_B)],
                "example_block_sha256": hashlib.sha256(cases.encode()).hexdigest(),
                "script_sha256": sha(Path(__file__))}
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != encoded:
        raise ValueError("G33 任务清单或输入身份漂移")
    manifest_path.write_text(encoded, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(one, key, card, cases): key for key, card in CARDS.items()}
        for future in as_completed(futures):
            print(json.dumps(future.result(), ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
