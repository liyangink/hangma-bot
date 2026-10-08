"""坐隐 3.0：**四分量前后事实矩阵**（生成与核对）。

## 这份矩阵回答什么

第三阶段的搜索对象是**四个规则乘子**组成的价值路径（官方指南 v34 §1.3）：

    总番 = 1 × 分支因子 × 2^动作链次数 ×（4 白板 ×2）×（爆头 ×2）

要让候选按 `Φ(s') − Φ(s)` 计分，四个分量在**动作前**与**动作后**都要有事实。
本工具把「哪个分量、哪一栏、由谁提供、现状如何」写成**可核验**的矩阵：
每一条都指向一个**源码符号**，由 `--check` 逐条解析；符号改名或删除会让检查失败，
矩阵因此不会像散文那样悄悄漂移。

## 三栏的含义（PLAN-REVISION §1.3）

| 栏位 | 含义 | 纪律 |
| --- | --- | --- |
| `before` | **动作前**：当前决策窗口依法可见的状态 | 只来自观察与规则分析 |
| `after_known` | **已知动作后**：确定性动作（弃牌 / 吃 / 碰 / 杠）之后的确定状态 | 由 `hangma` 的转移函数给出 |
| `after_random` | **待随机事件后**：摸牌、杠补或未来成胡之后 | **不得把未知写成确定后态**；确有确定性转移的才登记 |

## 用法

    .venv/bin/python tools/sitin_phase3_facts.py --check      # 只核对，失败退出码 2
    .venv/bin/python tools/sitin_phase3_facts.py --out DIR    # 核对并写 matrix.json / MATRIX.md
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))

SCHEMA = "sitin-phase3-fact-matrix/1"

COMPONENTS: Tuple[Tuple[str, str, str], ...] = (
    ("branch", "分支", "平胡 ×1 / 七对 ×2 / 豪华七对 1—3 组 ×4/×8/×16（log2 0—4）"),
    ("chain", "动作链", "飘与杠每个动作 ×2；打出非飘非杠的牌断链清零"),
    ("four_white", "四白", "胡牌时手留白 + 链内飘出**恰好等于 4** ⇒ ×2（等值条件）"),
    ("baotou", "爆头", "听牌态摸任意一张即胡 ⇒ ×2"),
)

#: 三栏；值是给人读的定义。
PHASES: Tuple[Tuple[str, str], ...] = (
    ("before", "动作前：当前决策窗口依法可见的状态"),
    ("after_known", "已知动作后：弃牌 / 吃 / 碰 / 杠之后的确定状态"),
    ("after_random", "待随机事件后：摸牌、杠补或未来成胡之后"),
)

#: 动作族；`hu` 是终局，不进「动作后」的代理。
ACTION_FAMILIES: Tuple[str, ...] = ("discard", "chi", "peng", "gang", "pass", "hu")

#: 每一条 = 分量 × 栏位 → 事实。
#: `carrier` 是**源码符号**（`模块:属性`），由 --check 实际解析；
#: `status` 取值：ok / added（本批新增）/ unavailable（规则上不可确定）/ unknown（未实现）。
FACTS: Tuple[Dict[str, Any], ...] = (
    # ---- 动作前 ---------------------------------------------------------
    {
        "component": "branch", "phase": "before", "status": "ok",
        "fact": "当前暗牌的两型向听与最优向听（七对路径是否存活、是否更近）",
        "carrier": "hangma_bot.hangma.hand_analysis:analyse_hand",
        "kind": "rule_call",
        "note": "同一函数也是规则层给候选算动作后向听的入口；只有副露数为 0 时七对向听不为空。",
    },
    {
        "component": "chain", "phase": "before", "status": "ok",
        "fact": "本人动作链次数",
        "carrier": "hangma_bot.policy.evaluation_v1:EvaluationContext",
        "kind": "window_state",
        "note": "字段 chain_count；官方 god.chain_count。",
    },
    {
        "component": "chain", "phase": "before", "status": "ok",
        "fact": "链内飘出白板数",
        "carrier": "hangma_bot.policy.evaluation_v1:EvaluationContext",
        "kind": "window_state",
        "note": "字段 chain_piao；**依据不足时为空，空不等于零**。",
    },
    {
        "component": "four_white", "phase": "before", "status": "ok",
        "fact": "动作前本人手留财神张数",
        "carrier": "hangma_bot.policy.evaluation_v1:EvaluationContext",
        "kind": "window_state",
        "note": "字段 wealth_count；四白还须叠加链内飘出张数。",
    },
    {
        "component": "four_white", "phase": "before", "status": "ok",
        "fact": "「四白」等值指示（手留白 + 链内飘出 == 4）",
        "carrier": "hangma_bot.hangma.special_rules:four_white_indicator",
        "kind": "rule_predicate",
        "note": "等值条件，**不是单调量**；任一输入未知返回 None（不填 False）。",
    },
    {
        "component": "baotou", "phase": "before", "status": "ok",
        "fact": "本人当前是否爆头",
        "carrier": "hangma_bot.policy.evaluation_v1:EvaluationContext",
        "kind": "window_state",
        "note": "字段 baotou；运行时以官方 god.baotou 为权威。",
    },
    # ---- 已知动作后 -----------------------------------------------------
    {
        "component": "branch", "phase": "after_known", "status": "ok",
        "fact": "动作后两型向听",
        "carrier": "hangma_bot.hangma.interface:CandidateFacts",
        "kind": "candidate_fact",
        "note": ("字段 standard_shanten_after / seven_pairs_shanten_after；"
                 "**只在 fact_kind=HAND_PROGRESS 时有值**，WIN/不适用/失败为 None。"),
    },
    {
        "component": "chain", "phase": "after_known", "status": "added",
        "fact": "任意本人动作后的（链次数, 链内飘出数）",
        "carrier": "hangma_bot.hangma.progression:chain_after_action",
        "kind": "rule_transition",
        "note": ("本批新增的统一入口：弃牌走 chain_after_discard、杠走 chain_after_gang、"
                 "吃/碰/过不改链；断链结局把两项归零（与原先是否已知无关）。"),
    },
    {
        "component": "four_white", "phase": "after_known", "status": "added",
        "fact": "动作后本人手留财神张数",
        "carrier": "hangma_bot.hangma.progression:wealth_after_action",
        "kind": "rule_transition",
        "note": "本批新增：白不可被吃碰杠 ⇒ 只有打出白板的弃牌会减少。",
    },
    {
        "component": "baotou", "phase": "after_known", "status": "added",
        "fact": "确定性动作后的爆头",
        "carrier": "hangma_bot.hangma.progression:baotou_after_action",
        "kind": "rule_transition",
        "note": ("本批新增（3.0 的**首个阻塞项**）：弃牌用弃后暗牌重算【官方】；"
                 "吃/碰/杠继承动作前状态【实现+用户确认】；胡为终局返回 None。"),
    },
    {
        "component": "baotou", "phase": "after_known", "status": "added",
        "fact": "弃牌后的爆头（弃后暗牌判定）",
        "carrier": "hangma_bot.hangma.progression:baotou_after_discard",
        "kind": "rule_transition",
        "note": "从 _resolve_draw 的内联表达式提为单一规则来源，模拟推进与候选共用。",
    },
    # ---- 待随机事件后 ---------------------------------------------------
    {
        "component": "baotou", "phase": "after_random", "status": "ok",
        "fact": "摸牌 / 杠补后的爆头",
        "carrier": "hangma_bot.hangma.progression:baotou_after_draw",
        "kind": "rule_transition",
        "note": "普通摸牌按**摸前暗牌**重算；杠补 replacement 继承或新进入；来源未知且会改变结果时抛错。",
    },
    {
        "component": "chain", "phase": "after_random", "status": "ok",
        "fact": "杠补牌后的链（杠本身已 +1，补牌不再改变链）",
        "carrier": "hangma_bot.hangma.progression:chain_after_gang",
        "kind": "rule_transition",
        "note": "补牌是摸牌事件，规则上不改变链；链的下一步变化发生在其后的动作窗口。",
    },
    {
        "component": "branch", "phase": "after_random", "status": "unavailable",
        "fact": "未来摸牌后的牌型路径",
        "carrier": None,
        "kind": "unknown",
        "note": ("**规则上不可确定**：具体摸到哪张未知。需要估计时须声明确定性代理"
                 "与信息来源（例如「下一次摸牌直接胡」的可选分值分析），"
                 "**不得把未来成胡写成确定后态**。"),
    },
    {
        "component": "four_white", "phase": "after_random", "status": "unavailable",
        "fact": "未来摸到白板后的手留张数",
        "carrier": None,
        "kind": "unknown",
        "note": "同上：摸到哪张未知；杠补张数已知但牌值未知。",
    },
)

#: 动作族 × 分量 → 已知动作后的**规则结论**（供人读与测试断言）。
ACTION_TABLE: Tuple[Dict[str, Any], ...] = (
    {"family": "discard", "branch": "按弃后手牌重算（候选事实）",
     "chain": "飘（爆头∧白）⇒ +1 且 piao+1；否则断链 ⇒ 两项归零",
     "four_white": "打白 ⇒ 手留 −1（飘时 piao+1，和不变）；否则 piao 归零（和可能减少）",
     "baotou": "用**弃后暗牌**重新判定（可能进入/保持/退出）"},
    {"family": "chi", "branch": "七对路径**永久关闭**（副露）",
     "chain": "不变", "four_white": "不变（白不可被吃）",
     "baotou": "继承动作前状态"},
    {"family": "peng", "branch": "七对路径**永久关闭**（副露）",
     "chain": "不变", "four_white": "不变（白不可被碰）",
     "baotou": "继承动作前状态"},
    {"family": "gang", "branch": "七对路径**永久关闭**；杠本身已使七对不可能",
     "chain": "+1（piao 不变）", "four_white": "手留不变（白不可被杠）",
     "baotou": "继承动作前状态（杠补牌另见 after_random）"},
    {"family": "pass", "branch": "不变", "chain": "不变",
     "four_white": "不变", "baotou": "不变"},
    {"family": "hu", "branch": "终局：实际牌型由结算给出",
     "chain": "终局：实际链由结算给出", "four_white": "终局：实际四白由结算给出",
     "baotou": "终局：实际爆头由结算给出"},
)


def resolve(symbol: str) -> Any:
    """解析 `模块:属性` 形式的源码符号；失败抛 ImportError/AttributeError。"""

    module_name, _, attribute = symbol.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def check() -> List[Dict[str, Any]]:
    """逐条解析 carrier；返回失败清单（空表示全部通过）。"""

    failures: List[Dict[str, Any]] = []
    for item in FACTS:
        symbol = item.get("carrier")
        if symbol is None:
            if item["status"] != "unavailable":
                failures.append({"fact": item["fact"],
                                 "reason": "缺少 carrier 但不是 unavailable"})
            continue
        try:
            resolve(symbol)
        except Exception as exc:                       # noqa: BLE001 —— 报告而非抛出
            failures.append({"fact": item["fact"], "symbol": symbol,
                             "reason": "{0}: {1}".format(type(exc).__name__, exc)})
    return failures


def matrix() -> Dict[str, Any]:
    """完整矩阵（含每个分量的三栏覆盖与缺口）。"""

    gaps = [{"component": item["component"], "phase": item["phase"],
             "fact": item["fact"], "status": item["status"], "note": item["note"]}
            for item in FACTS if item["status"] in ("unknown", "unavailable")]
    return {
        "schema": SCHEMA,
        "components": [{"id": cid, "name": name, "rule": rule}
                       for cid, name, rule in COMPONENTS],
        "phases": [{"id": pid, "meaning": meaning} for pid, meaning in PHASES],
        "action_families": list(ACTION_FAMILIES),
        "facts": [dict(item) for item in FACTS],
        "action_table": [dict(item) for item in ACTION_TABLE],
        "gaps": gaps,
        "gap_summary": {
            "unknown": sorted({g["component"] + "/" + g["phase"]
                               for g in gaps if g["status"] == "unknown"}),
            "unavailable": sorted({g["component"] + "/" + g["phase"]
                                   for g in gaps if g["status"] == "unavailable"}),
        },
        "note": ("矩阵只描述**事实可达性**，不声称四分量划分有效；"
                 "四个分量的非终局代理是工程假设，须由完整桌赛与阶段目标实测。"),
    }


def render_markdown(data: Dict[str, Any]) -> str:
    """人可读矩阵；与 JSON 同源。"""

    lines = [
        "# 坐隐 3.0 四分量前后事实矩阵",
        "",
        "> 由 [tools/sitin_phase3_facts.py](../../tools/sitin_phase3_facts.py) 生成；",
        "> 每条事实都指向一个源码符号，`--check` 逐条解析，符号改名或删除即失败。",
        "> **矩阵只描述事实可达性**，不声称四分量划分有效。",
        "",
        "## 1. 分量 × 栏位",
        "",
        "| 分量 | 栏位 | 事实 | 提供者 | 类型 | 状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in data["facts"]:
        carrier = item["carrier"] or "—"
        lines.append("| {0} | {1} | {2} | `{3}` | {4} | {5} |".format(
            item["component"], item["phase"], item["fact"], carrier,
            item["kind"], item["status"]))
    lines += ["", "## 2. 动作族 × 分量（已知动作后）", "",
              "| 动作族 | 分支 | 链 | 四白 | 爆头 |", "| --- | --- | --- | --- | --- |"]
    for row in data["action_table"]:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            row["family"], row["branch"], row["chain"], row["four_white"], row["baotou"]))
    lines += ["", "## 3. 缺口（**不得用代理悄悄填上**）", "",
              "| 分量 | 栏位 | 事实 | 状态 | 说明 |", "| --- | --- | --- | --- | --- |"]
    for gap in data["gaps"]:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            gap["component"], gap["phase"], gap["fact"], gap["status"],
            gap["note"].replace(chr(10), " ")))
    lines += ["", "## 4. 读完这张矩阵应当得出的两条结论", "",
              "1. **动作后四分量已闭合**：链 / 四白 / 爆头都有 rule_transition，",
              "   分支走 CandidateFacts（动作后两型向听）；",
              "2. **两处永远不可确定**：未来摸牌后的牌型路径与手留白——那是随机事件，",
              "   要估计就必须显式声明代理，不得写成确定后态。", ""]
    return chr(10).join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="坐隐 3.0 四分量前后事实矩阵")
    ap.add_argument("--check", action="store_true", help="只核对每条事实的源码符号")
    ap.add_argument("--out", default=None, help="输出目录（写 matrix.json 与 MATRIX.md）")
    args = ap.parse_args(argv)

    failures = check()
    if args.check:
        for item in failures:
            print("FAIL {0} -> {1}".format(item.get("symbol"), item["reason"]))
        print("核对 {0} 条事实，失败 {1} 条".format(len(FACTS), len(failures)))
        return 2 if failures else 0

    data = matrix()
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "matrix.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
        (out / "MATRIX.md").write_text(render_markdown(data), encoding="utf-8")
        print("已写出 {0}".format(out))
    else:
        print(render_markdown(data))
    for item in failures:
        print("FAIL {0} -> {1}".format(item.get("symbol"), item["reason"]))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
