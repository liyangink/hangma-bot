#!/usr/bin/env python3
"""G236：授权 GLM 5.3 在冻结逐窗证据上提出可执行跨巡路线控制器。"""

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

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g236-glm-route-controller-author-20260929')
CHANNEL = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch'))
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')
INPUTS = (
    _project_file(_PROJECT_ROOT, HERE / "G235-ALL-WINDOW-ROUTE-CONFLICT-RESULT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, HERE / "G233-INVERSION-SAME-WORLD-BRANCH-RESULT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, HERE / "G234-THREE-DRAW-ROUTE-DISCRIMINATION-RESULT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, HERE / "G193-EARLY-THREE-SHANTEN-DEVELOPMENT-RESULT-2026-09-29.md"),
    _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/interface.py"),
)
FIELDS = ("status", "mechanism", "entry", "hold", "exit", "selector_code",
          "state_and_recovery", "observable_fields", "negative_controls",
          "behavior_dedup", "runtime_bound", "falsifier", "uncertainty")


def digest(path: Path) -> str:
    """记录内容摘要，不回显授权通道的认证补丁。"""
    return sha256(path.read_bytes()).hexdigest()


def prompt() -> str:
    """限制作者只能提出一个可在生产决策接缝审计的控制器。"""
    return ("你是杭麻 Bot 离线启发式算法作者。用户已授权本项目材料发送到 zai-coding-cn 的 GLM 5.3。只返回一个严格 JSON 对象，不调用工具、不编辑文件、不输出 Markdown。若不能在现有可见字段下提出真正不同且有明确负控的控制器，status 写 infeasible；不要填写貌似完整但无法执行的公式。\n\n"
    "任务：基于 G235 的最新结构证据，提出一条可执行、低延迟的**跨本人行动窗口**自然牌形路线控制器，目标是加快自然面子形成并增加白板后期爆头／财飘选择权，同时保护普通胡、七对和已有高番。最终验收仍是全新 H/M 异质对手池、同牌山四座换位八局完整桌，等权至少 +2 分/桌、两池同正、根级 95% 区间下界 >0，再过规则、1/3 秒窗口及官方接线。现在只求候选，不可声称收益已证明。\n\n"
    "最新事实：G235 与 G223 相同的已看 128 张父代表逐动作/结算恒等，核查 4869 个正常摸打、当前无胡、父代选非白弃牌、普通型一到三向听窗口。严格更宽普通自然进张 H/M 258/253；近端保护后 127/121；基础牌效偏宽但熟牌/领先风格反转 73/65，跨 H/M 8/8 根。同一手牌重复反转 H 8 手/5 根、M 10 手/7 根，通过事前覆盖门。然而只在第二次才改变最多触达 17/128 桌，若要总体 +2 分/桌需约 15.1 分/触达桌；重复前两次是同一弃牌备选仅 H4/8、M3/10。G235 不是收益标签。\n"
    "G233 强制一次更宽改弃同世界完整桌：H 根3 一白一向听，父代弃 1t、备选弃 北，多 1 种/3 张，后来父代在第7个本人摸牌窗口经碰发后胡平胡·财飘·爆头 4 番；备选在某世界只胡平胡；H 根6 一白二向听，父代弃1t、备选弃中，多2种/7张，父代第11个本人摸牌窗口胡七对·爆头；这两根各 -8.375 分/桌。M 根1 一白二向听，父代弃1t、备选弃2b，多1种/2张，备选 +11.188 分/桌。三者都是该手第一次 G235 反转，普通/七对向听均取平，首次两摸或三摸高番值不能区分正负。不能硬编码牌谱ID或以这些后验结果作为线上输入。\n"
    "已失败路径：G168/G171/G193 单纯更宽进张，G193 实际改弃290次/512配对完整桌，H -1.543、M +0.617、合并 -0.463 分/桌；G221 两摸互斥结算分也负；P22 单窗重采样 rollout 与随机臂不可分。不得只修改 river_part=3/style_part=4、固定加宽度奖金、再做三摸穷举，或在赢家牌谱上回填未来结算。\n\n"
    "唯一实现接缝：BotPolicy 包装器在每窗先 await 冻结 R18 v2.choose(request,budget)，此时已有合法保底。`request.observation` 是 PlayerObservation（本人暗手、他家仅张数、公开弃牌副露、墙余、白板、当前积分）；`request.rules.legal_candidates` 含生产 CandidateFacts：standard_shanten_after、seven_pairs_shanten_after、shanten_after、standard_useful_tiles、useful_tiles、baotou_after、可胡／分支事实；`plan.candidates` 含已合法的 action_key、total_score、score_trace.detail 中 base_score/river_part/style_part/risk_units。只可在本窗口重排已有合法动作。当前手牌可用生产 `_build_context(observation).full_hand()` 读取，不允许 WorldState、他家暗手、未来牌墙、赛后分数、网络/文件/时钟。未知事实不补零。不要新增规则求解器，也不要在 1 秒响应窗搜索；仅 3 秒正常摸打窗，额外计算期望 <10ms，最坏 <50ms。\n"
    "若设计跨窗内存，以 `(game_id,round_no,seat)` 隔离；只有已权威确认的本人动作才可更新，重复窗口/序号缺口/重启无历史时回退父代。也可设计完全从当前可见手牌恢复的无内存路线状态。状态必须有进入、保持、退出和失败回退；避免第一次无差别改宽面，也不能只在第二次重复反转改。对一白高番反例与 M 正例必须说明行动前可见的**候选可核特征差异**，若无法区分就承认不确定并设置弃权，而不能声称这三个已经验收。\n\n"
    "只输出 JSON，以下键全部为字符串：status（proposed/infeasible）、mechanism、entry、hold、exit、selector_code（可审查的 Python 函数 `select(request, plan, confirmed_memory) -> tuple[str | None, dict, dict]`；只用上述现成对象及纯算术；代码中注明未知处理；不要导入项目中不存在的字段）、state_and_recovery、observable_fields、negative_controls（包括普通胡和高番保护）、behavior_dedup（说明如何与 G168/G171/G193/G221 逐窗动作去重）、runtime_bound、falsifier、uncertainty。`selector_code` 不是已可信代码；人和本地规则验证后才可运行。")


def main() -> None:
    """一次无工具作者调用，保存原提示、答卷、耗时和输入摘要。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    if args.attempt < 1:
        parser.error("attempt 必须为正整数")
    if not all(path.is_file() for path in INPUTS):
        raise FileNotFoundError("G236 证据输入缺失")
    patches = (_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml"),
               _project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml"), ROUTE)
    if not all(path.is_file() for path in patches):
        raise FileNotFoundError("G236 已授权模型通道配置缺失")
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.attempt == 1 else f"-attempt{args.attempt}"
    prompt_path, answer_path, call_path = (
        _project_file(_PROJECT_ROOT, OUT / f"prompt{suffix}.txt"), _project_file(_PROJECT_ROOT, OUT / f"answer{suffix}.txt"),
        _project_file(_PROJECT_ROOT, OUT / f"call{suffix}.json"))
    if any(path.exists() for path in (prompt_path, answer_path, call_path)):
        raise FileExistsError("G236 作者原件已存在，拒绝重复或覆盖")
    prompt_path.write_text(prompt(), encoding="utf-8")
    argv = ["dsh", "--profile", "headless",
            "--patch", str(patches[0]), "--patch", str(patches[1]),
            "--patch", str(patches[2]), prompt()]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="g236-glm-") as state_dir:
        try:
            proc = subprocess.run(argv, cwd=ROOT,
                                  env=dict(os.environ, DSH_HOME=state_dir),
                                  capture_output=True, text=True,
                                  timeout=1200, check=False)
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
        "schema": "g236-glm-route-controller-author/1",
        "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
        "reasoning_effort_requested": "max",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "exit_code": code, "valid_json_contract": valid,
        "prompt_sha256": digest(prompt_path), "answer_sha256": digest(answer_path),
        "answer_chars": len(answer),
        "diagnostic_sha256": sha256(diagnostic.encode()).hexdigest(),
        "diagnostic_bytes": len(diagnostic.encode()),
        "diagnostic_class": ("transport_connection_error" if
                             "TRANSPORT: Connection error." in diagnostic
                             else "other"),
        "route_patch_sha256": digest(ROUTE),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path)
                         for path in INPUTS},
        "script_sha256": digest(Path(__file__)),
        "scope": "离线作者答卷；不得未经规则、动作覆盖与完整桌检验直接接线",
    }
    call_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                   indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in (
        "exit_code", "valid_json_contract", "elapsed_seconds", "answer_chars")},
        ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
