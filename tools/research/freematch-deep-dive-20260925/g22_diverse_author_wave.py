#!/usr/bin/env python3
"""G22 离线 GLM 作者广覆盖波次；只生成答卷，不接入线上策略。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g22-diverse-author-wave-20260927')
CHANNEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
ROUTE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-route-author-20260927/route.patch.yml')

COMMON = """你是杭麻 Bot 的离线算法作者。只用中文输出一个可核验的候选机制；不调用工具、不修改文件。算法在线只能读 PlayerObservation 和生产 HangmaRules 给出的合法动作与规则数值，不能读他家暗手或未来牌墙；只重排合法弃牌，不改胡、杠、吃碰规则。摸打窗3秒、响应窗1秒；当前 R18 v2 已可稳定参赛，目标是新根 H/M 同牌山四座完整桌相对它提高至少2分/桌，两池同号且独立确认。只有完整桌可证明净收益。

官方杭麻 v34 的关键事实：只自摸胡；白板是财神，不可吃碰杠胡；抓打圈非圈主只能摸切；末20张留墩。每码四张。他家已明碰三张且我持第四张时，他家不能在我弃第四张时补杠；补杠需要他本人摸到第四张，明杠需他暗手三张再接他家弃牌。普通型和七对、爆头和财飘都需按生产规则计算，不能自行改写。

已失败/不充分的路线：直接加普通有效牌种数、弃孤字阈值、固定风险与宽度交换、两摸宽度奖金、白板预先绑某张、未核实的胡法质量乘数、单隐藏世界教师。G19 表面二摸新信号大多已有当前有效容量或普通牌种优势。G21 在当前普通/综合逐牌向量全同且七对三摸不可达的219对里，131对仅第三摸理想化容量分叉，123正/8负；这不是完整桌收益，三摸动态规划 p95 约3.38秒不能原样上线。公开未见数包含对手暗手，不可当真实牌墙概率。G10/G11/P28 的历史失败不能被仅改名重试。

请输出恰好一个机制；若无法给出可核验机制就明确写“暂无可编码种子”。依次写：①因果链和适用牌形；②只用可见输入与生产规则的精确伪代码及最坏操作界，禁用任意自造官方结算；③一组明确完整手牌/副露/已出牌条件的区分例，数值若未本地验证必须标“待本地核验”；④与现有当前有效容量、牌种数、两摸宽度、风险交换在数学和选牌行为上的非等价反例；⑤会损害普通胡或七对的负控；⑥冻结轨迹上最低触达完整桌数、旧动作重合与新根验证门，什么结果立即停线。不要编造胜率或分数。不要假设所有好形都能到下一次本人摸牌。
"""

CARDS = {
    "a1_completion_diversity": "机制族A／算子1：考虑多条自然面子完成路线之间的牌码重叠及公开支持，寻找当前一/二摸同值但三摸分叉的廉价可计算代理。避免把路线条数或最宽牌种重命名成价值。请特别检查同一张进张是否被多条路线重复计数。",
    "a2_route_robustness": "机制族A／算子2：从最脆弱自然面子路线或必需的瓶颈牌码出发构造候选。它必须在已有即时有效张容量、牌种数和路线条数相同的牌形中仍可能区分动作。说明公开支持不等于墙概率，并给出弃白/抓打圈反例。",
    "b1_baotou_head": "机制族B／算子1：早中巡一白场景，自然成面优先保留白板作爆头时，怎样估计将牌/剩余面子的路线交换价？不能提前绑白板配哪张，更不能以白板张数常数作特征。先验证普通胡机会成本。",
    "b2_multiwhite_piao": "机制族B／算子2：两白或更多时，怎样仅在有真实可达的财飘条件与足够自然面子进度时，给后巡保白增加动作特异信号？必须明确牌墙留墩、本人可能摸不到、七对和快速普通胡的机会成本。",
    "c1_standard_pairs_fork": "机制族C／算子1：普通型与七对在早巡的可选路线如何定价，避免因一时白板作对子而打掉自然连接牌？机制必须允许观测更新后退出七对路线，并能解释用户四白局中保孤西的潜在反例，不把该单局当金标签。",
    "c2_partial_shape": "机制族C／算子2：针对孤张字牌、单吊、夹张相对双搭/浮牌的选择，在未知牌墙且公开未见总量接近时构造离散自然牌块形状量具。需证明不是单纯牌种数、当前有效张容量、两摸宽度或固定弃字牌奖励。",
    "d1_opponent_race": "机制族D／算子1：本人自然路线需要多摸才兑现时，利用他家当前公开副露、可见弃牌与墙余估计失去摸牌机会的动作特异风险。不得从他家暗手或未验证的公开占用预测训练出确定概率；不能复用G11固定风险交换。",
    "d2_tempo_local": "机制族D／算子2：本人同一动作窗不同弃牌可能影响他家合法响应，从而改变下一次本人摸牌到达时机。找一个符合牌张守恒、吃碰杠合法性的公开局面和方向，若没有足量触发就主动判停。不得再提出‘明碰三张者等我打第四张补杠’。",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def one(key: str, card: str) -> dict[str, object]:
    """单卡运行，隔离 dsh 状态，保留调用与答卷摘要，不暴露供应商诊断。"""

    prompt = COMMON + "\n本次独有任务卡：" + card + "\n"
    prompt_path = _project_file(_PROJECT_ROOT, OUT / f"{key}.prompt.txt")
    answer_path = _project_file(_PROJECT_ROOT, OUT / f"{key}.answer.txt")
    record_path = _project_file(_PROJECT_ROOT, OUT / f"{key}.call.json")
    if answer_path.exists() or record_path.exists():
        return {"key": key, "skipped": "existing_record_or_answer"}
    prompt_path.write_text(prompt, encoding="utf-8")
    argv = ["dsh", "--profile", "headless", "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "credentials.patch.yml")),
            "--patch", str(_project_file(_PROJECT_ROOT, CHANNEL / "no-tools-eval.patch.yml")), "--patch", str(ROUTE), prompt]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"g22-{key}-") as state_dir:
        try:
            result = subprocess.run(argv, cwd=ROOT,
                                    env=dict(os.environ, DSH_HOME=state_dir),
                                    capture_output=True, text=True, timeout=1200, check=False)
            code, answer, diagnostic = result.returncode, result.stdout, result.stderr
            failure = None if code == 0 else "nonzero_exit"
        except subprocess.TimeoutExpired as error:
            code = None
            answer = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else error.stdout or ""
            diagnostic = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else error.stderr or ""
            failure = "timeout_or_uncertain_transport"
    answer_path.write_text(answer, encoding="utf-8")
    record = {"schema": "g22-diverse-author-call/1", "key": key,
              "provider_requested": "zai-coding-cn", "model_requested": "glm-5.3",
              "reasoning_effort_requested": "max", "prompt_sha256": digest(prompt.encode()),
              "route_patch_sha256": digest(ROUTE.read_bytes()),
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "exit_code": code, "answer_chars": len(answer),
              "answer_sha256": digest(answer.encode()),
              "diagnostic_sha256": digest(diagnostic.encode()),
              "diagnostic_bytes": len(diagnostic.encode()),
              "failure_kind": failure, "usable_answer": code == 0 and bool(answer.strip()),
              "scope": "offline hypothesis only; no rule, mathematics or whole-table effect accepted"}
    record_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    """以四族八卡做受控多样性搜索；失败不自动重试。"""

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "g22-diverse-author-manifest/1", "base_commit": "9f12f7d11",
                "model": "zai-coding-cn/glm-5.3 max", "concurrency": 3,
                "cards": CARDS, "common_prompt_sha256": digest(COMMON.encode())}
    (_project_file(_PROJECT_ROOT, OUT / "manifest.json")).write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(one, key, card): key for key, card in CARDS.items()}
        for future in as_completed(futures):
            print(json.dumps(future.result(), ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
