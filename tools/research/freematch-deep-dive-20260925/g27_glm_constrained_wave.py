#!/usr/bin/env python3
"""G27：按冻结开发牌例并行调用离线 GLM 作者，不执行模型产出的代码。"""

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
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from hangma_bot.hangma.internal_types import codes_from_counts


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g27-glm-constrained-wave-20260927')
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
CARDS = {
    "a01_disjoint_blocks": "A族：互不重叠自然牌块的可行完成路线。不要把共用同一张手牌的数条搭子累加。",
    "a02_completion_diversity": "A族：同样有效进张下，几条不同自然面子路线的第三次本人摸牌弹性。不要等同于路线条数。",
    "a03_bottleneck_overlap": "A族：路线需求牌码的重叠和公开上界瓶颈。每码四张，公开未知数不是牌墙概率。",
    "a04_pair_head_exchange": "A族：将牌候选与顺刻面子的可交换性。不能把白板预先绑定到将牌。",
    "a05_natural_dwell": "A族：自然搭子在下一次本人摸打后能否继续保持两条以上改良路径，要求在线可限时。",
    "b01_one_white_reserve": "B族：一白的自然成面速度与后巡白板利用共同定价；本波 G26 下一摸打爆头全零，不得声称已有爆头收益。",
    "b02_multi_white_option": "B族：多白的真实机会值，财飘必须已有爆头状态后弃白形成合法链，不得由白数直接发奖。",
    "b03_standard_pairs_fork": "B族：普通型与七对的路线分叉及退出条件；白板可补对子，不能以白板当作固定将。",
    "b04_fast_hu_cost": "B族：为自然牌形牺牲快速普通胡的机会成本；保持相同当前逐牌有效向量时仍须有动作特异信号。",
    "c01_opponent_race": "C族：自然路线兑现前可能先被他家胡；只用可见观察，不能推断确知他家暗手。",
    "c02_catch_play": "C族：抓打圈、末20张留墩造成的后继摸牌可达性；不把理想三摸容量当实际桌赛概率。",
    "c03_public_response": "C族：弃牌影响他家吃碰的动作特异时机；必须逐一排除合法吃碰杠，不能把避开叫牌假设成单调增益。",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def examples() -> tuple[str, str]:
    """G23 已存在的开发房正负各六例，留出房对作者不可见。"""

    path = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if source["rows_sha256"] != sha(path.read_bytes()):
        raise ValueError("G23 教师来源摘要漂移")
    positives, negatives = [], []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (row["split"] != "development" or row["white_after"] != 1 or
                    row["delta_2"] != 0 or row["delta_3"] == 0):
                continue
            group = positives if row["delta_3"] > 0 else negatives
            group.append(row)
    ordered = []
    for group in (positives, negatives):
        group.sort(key=lambda row: sha((row["game_id"] + ":" + str(row["trigger_seq"])).encode()))
        if len(group) < 6:
            raise ValueError("G27 开发房样本正负例不足六个")
        ordered.extend(group[:6])
    lines = []
    for index, row in enumerate(ordered, 1):
        parent = ",".join(codes_from_counts(tuple(row["parent"]["counts34"])))
        alternative = ",".join(codes_from_counts(tuple(row["alternative"]["counts34"])))
        lines.append(f"E{index:02d}: 本人副露数={row['meld_count']}, 父代弃{row['parent_action'].split(':')[1]}后=[{parent}], "
                     f"备选弃{row['alternative_action'].split(':')[1]}后=[{alternative}], "
                     f"两摸相同, 三摸理想容量方向={'备选优' if row['delta_3'] > 0 else '父代优'}。")
    return "\n".join(lines), sha(path.read_bytes())


def prompt_for(key: str, card: str, cases: str) -> str:
    return f"""你是杭麻 Bot 的离线算子作者，只输出一个严格 JSON 对象，不加 markdown，不调用工具。任务卡 {key}: {card}

约束：线上只可读取 PlayerObservation、本人工牌、全场公开牌和生产 HangmaRules 已算的合法动作、向听、逐牌有效张；不能读他家暗手、未来牌墙或赛后信息。只重排合法弃牌，绝不改胡/吃碰杠/结算。官方 v34 只自摸胡；白板是财神，不可吃碰杠胡；抓打圈非圈主只能摸切；末20张留墩。爆头为摸前任意物理可得牌均可胡，财飘须有爆头状态并弃白的合法动作链。生产 any_tile_win 可判静态爆头，不能发明不存在的线上接口。

证据：G23 未按潜在连接择优的 184 个同当前普通/综合逐码牌效动作对，三摸理想容量备选优74、父代优77、同33；两摸相同181对。G24 单个自然路线容量代理在一白留出房仅3对3错。G25 禁止后继弃白后持白样本的三摸容量完全不变。G26 这批严格样本下一摸打的生产静态爆头机会父/备均零。G10/G11/P28 已试过静态宽度、固定风险与两步宽度，不能改名重复；候选必须能在当前逐码牌效相同条件下区分行为。下列是仅供构思的开发房例子，三摸是无他家干预的理想教师，不是桌赛收益：
{cases}

输出 JSON 键严格包含 name、mechanism、applicability、visible_inputs、score_pseudocode、worst_case_operations、rules_counterexample、old_behavior_difference、negative_control、falsification_gate。伪代码须说明每个循环上界和不超过3秒摸打窗的理由；若不能给出可实现且不退化为现有牌效的机制，把 mechanism 写成“暂无可编码种子”并诚实说明。不得声称这12例或三摸教师能证明净分。"""


def parse_answer(answer: str) -> tuple[bool, str | None]:
    try:
        value = json.loads(answer.strip())
    except json.JSONDecodeError:
        return False, "invalid_json"
    fields = ("name", "mechanism", "applicability", "visible_inputs", "score_pseudocode",
              "worst_case_operations", "rules_counterexample", "old_behavior_difference",
              "negative_control", "falsification_gate")
    if not isinstance(value, dict) or any(key not in value for key in fields):
        return False, "missing_required_field"
    return True, None


def one(key: str, card: str, cases: str) -> dict:
    """单卡隔离调用、留完整原答与摘要，不执行其伪代码。"""

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
    with tempfile.TemporaryDirectory(prefix=f"g27-{key}-") as state_dir:
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
    parsed, parse_error = parse_answer(answer) if code == 0 else (False, "call_failure")
    record = {"schema": "g27-glm-call/1", "key": key,
              "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
              "reasoning_effort_requested": "max", "prompt_sha256": sha(prompt.encode()),
              "route_patch_sha256": sha(ROUTE.read_bytes()),
              "elapsed_seconds": round(time.monotonic() - started, 3), "exit_code": code,
              "answer_chars": len(answer), "answer_sha256": sha(answer.encode()),
              "diagnostic_sha256": sha(diagnostic.encode()), "diagnostic_bytes": len(diagnostic.encode()),
              "failure_kind": failure, "valid_json_contract": parsed, "parse_error": parse_error,
              "scope": "offline author hypothesis only; no generated code executed or score accepted"}
    record_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return record


def main() -> None:
    """12 张任务卡最多三并发；只写生成与解析记录。"""

    OUT.mkdir(parents=True, exist_ok=True)
    cases, source_sha = examples()
    manifest = {"schema": "g27-glm-manifest/1", "model": "zai-coding-cn/glm-5.3 max",
                "concurrency": 3, "cards": CARDS, "g23_rows_sha256": source_sha,
                "example_block_sha256": sha(cases.encode()), "script_sha256": sha(Path(__file__).read_bytes())}
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != serialized:
        raise ValueError("G27 任务清单或脚本身份漂移")
    manifest_path.write_text(serialized, encoding="utf-8")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(one, key, card, cases): key for key, card in CARDS.items()}
        for future in as_completed(futures):
            print(json.dumps(future.result(), ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
