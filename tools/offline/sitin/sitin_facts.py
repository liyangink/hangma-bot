"""坐隐 1.4：候选事实盘点。

用途：回答"某个机制要落地，需要什么动作前的观察事实与动作后的事实；
哪些层已经提供、哪些还没有"，产出对照表供选族决策。依据 README §17 第 1.4 步
与审查 S-4 的三段式（机制 -> 所需事实 -> 已有/缺失）。

**这只是盘点，不是实现**：本工具不读桌赛产物以外的数据、不跑桌赛、不联网。

三层可用事实（以当前源码为准，字段名可在下面 LAYERS 中核对）：

  1. observation —— PlayerObservation / RulePublicState（规则适配器给出的可见观察）
  2. candidate_facts —— RuleCandidate.facts（CandidateFacts，动作后牌效）
  3. base_context —— policy.evaluation_v1.EvaluationContext（基础加权评分能看到什么）
  另：value_facts —— RuleCandidate.value_facts（可选条件结算），**默认关闭**，
       只有显式传 value_limits 才产生（审查 S4-2）。

准入判据（AGENTS.md §3 / DESIGN §14.4）：
  一条机制只有在"所需事实可由规则事实断言"时才允许写进评分骨架；
  否则只能作为待检验假设或诊断维度。
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
import json
import sys
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# 三层事实清单（字段名逐一对照当前源码；改动本表必须同时改源码核对）
# ---------------------------------------------------------------------------

OBSERVATION_FIELDS = {
    "game_id", "seat", "round_no", "snapshot_seq", "phase", "dealer_seat",
    "turn_seat", "responding_seats", "my_hand", "drawn_tile", "discards",
    "melds", "hand_counts", "last_discard", "remaining_tile_count", "scores",
    "rule_state", "public_history", "consumed_seq", "history_complete",
    "chain_piao", "gang_draw", "observation_issues",
}
RULE_STATE_FIELDS = {
    "wealth_god", "baotou", "chain_count", "catch_play", "catch_play_owner_seat",
}
CANDIDATE_FACT_FIELDS = {
    "fact_kind", "shanten_after", "useful_tiles", "best_followup_discard",
    "replacement_draw_unknown", "completeness", "note", "standard_shanten_after",
    "seven_pairs_shanten_after", "standard_useful_tiles", "seven_pairs_useful_tiles",
    "pattern_progress_note",
}
BASE_CONTEXT_FIELDS = {
    "combined_codes", "wealth_code", "safe_codes", "my_seat", "next_seat",
    "next_seat_meld_codes", "dealer_seat", "dealer_meld_codes", "table_rank",
    "catch_play",
}
VALUE_FACT_FIELDS = {"immediate_settlement", "routes", "coverage", "issues"}
# 条件结算位于 ValueRoute 内（每条路线一个），不是 CandidateValueFacts 的直接字段；
# 走 routes 即可拿到，因此不单独列为"缺失事实"。
VALUE_ROUTE_FIELDS = {"conditional_settlement", "shanten", "useful_tiles",
                      "followup_discard", "conditions", "support"}
# 结算对象内部字段：只在 value_facts 存在时可读（immediate_settlement 与
# ValueRoute.conditional_settlement 都是 Settlement）。**已确认可达**：
# hu_upgrade.py 与 value_one_draw.py 正在消费 *.score_delta。
SETTLEMENT_FIELDS = {"fan", "score_delta", "details"}

PRESENT = "present"              # 基础评分上下文直接可读
NEEDS_CONTEXT = "needs_context"  # 字段已在观察里，但**未接入基础评分上下文**
DERIVABLE = "derivable"          # 可从既有事实机械推导（不重算规则、不新增观察）
NEEDS_VALUE_ANALYSIS = "needs_value_analysis"  # 规则可产出，但 value_limits 默认关闭
MISSING = "missing"              # 当前各层都不提供，需新增规则事实或诊断记录


# 动作后事实的判定方式。**字段同名不代表时间点相同**（审查 S5-6）：
#   rule_transition —— 规则状态在候选动作后的变化，须由 hangma 的状态推进给出；
#                      **当前观察里的同名字段不是动作后状态**
#   candidate_fact  —— 规则为候选动作直接算出的动作后事实
#   value_fact      —— 需要显式启用可选分值分析才产生
POST_DETERMINATION = {
    "chain_count": "rule_transition",
    "catch_play": "rule_transition",
    "catch_play_owner_seat": "rule_transition",
    "baotou": "rule_transition",
    "shanten_after": "candidate_fact",
    "useful_tiles": "candidate_fact",
    "best_followup_discard": "candidate_fact",
    "fan": "value_fact",
    "immediate_settlement": "value_fact",
    "routes": "value_fact",
    "score_delta": "value_fact",
}


def _where(name: str) -> str:
    """给出某个事实名落在哪一层；用于对照表。"""

    if name in RULE_STATE_FIELDS:
        return "observation.rule_state"
    if name in OBSERVATION_FIELDS:
        return "observation"
    if name in CANDIDATE_FACT_FIELDS:
        return "candidate_facts"
    if name in BASE_CONTEXT_FIELDS:
        return "base_context"
    if name in VALUE_FACT_FIELDS:
        return "value_facts"
    if name in VALUE_ROUTE_FIELDS:
        return "value_facts.routes[]"
    if name in SETTLEMENT_FIELDS:
        return "value_facts.*.settlement"
    return ""


# ---------------------------------------------------------------------------
# 机制清单：每条给出"机制、动作前需要什么、动作后需要什么"
# ---------------------------------------------------------------------------

MECHANISMS = [
    {
        "id": "M1",
        "name": "番型杠杆 / 留链 vs 收胡",
        "source": "用户经验第 1 点 + README §14.1 M-4",
        "pre": ["chain_count", "baotou", "my_hand", "drawn_tile", "melds"],
        "post": ["fan", "shanten_after", "useful_tiles"],
        "note": "番值在**动作选择之前**即可取得（审核方已用规则公开接口直接验证：启用可选"
                "分值分析后，未执行任何动作即取得当前胡牌 fan 与带番值的条件路线）。限制有三："
                "① value_limits **默认关闭**，须在评估接线显式启用；"
                "② 覆盖范围仅『一次未来摸牌直接胡』，ValueCoverage 可空；"
                "③ 得到的是**条件**番值（条件成立时才成立），**不是**最终实际胡牌结果——"
                "后者仍未知，另列。**不得再用 chain_count/baotou 作粗糙代理替代这一精确事实。**",
    },
    {
        "id": "M2",
        "name": "财神杠杆 / 白板分档 / 四白",
        "source": "用户经验第 2 点 + README §14.1 M-2",
        "pre": ["my_hand", "wealth_god", "baotou", "chain_count"],
        "post": ["fan", "shanten_after"],
        "note": "手留白板张数可机械计数；『是否任意听』必须用 any_tile_win/爆头事实，"
                "不得用 WhitesHeld==4 代替（README §14.1 M-2 反例）。",
    },
    {
        "id": "M3",
        "name": "开圈（打财神）的资源交换",
        "source": "README §15.2/§15.3 E-1",
        "pre": ["catch_play", "catch_play_owner_seat", "my_seat", "chain_count",
                "melds", "remaining_tile_count"],
        "post": ["catch_play", "catch_play_owner_seat"],
        "note": "『本人是否圈主』需 owner_seat==my_seat，"
                "不能只看 catch_play 布尔（README §15.6 第三条）。",
    },
    {
        "id": "M4",
        "name": "鸣牌机会成本 / 吃碰风险",
        "source": "DESIGN §7 第二阶段首选族 + 项目 heuristic-frontier-audit",
        "pre": ["melds", "hand_counts", "discards", "dealer_seat", "my_seat"],
        "post": ["shanten_after", "useful_tiles", "best_followup_discard"],
        "note": "对手手牌进展不可见；只能用公开副露/牌河做代理。",
    },
    {
        "id": "M5",
        "name": "对手强弱自适应（风格）",
        "source": "用户经验第 4 点 + README §14.5 R-3",
        "pre": ["public_history", "discards", "melds"],
        "post": [],
        "note": "不得用身份/榜单标签（不可信）；须用行为画像（鸣牌率/弃牌节奏）。",
    },
    {
        "id": "M6",
        "name": "牌墙寿命（剩余巡数）",
        "source": "README §15.3 E-4",
        "pre": ["remaining_tile_count", "round_no"],
        "post": [],
        "note": "官方 wall_remaining 可能为空；为空时不得假设剩余巡数。",
    },
    {
        "id": "M7",
        "name": "结算价值（条件路线）",
        "source": "README §14.2 + 审查 S4-2",
        "pre": ["my_hand", "melds", "chain_count", "baotou"],
        "post": ["immediate_settlement", "routes"],
        "note": "value_facts 默认关闭（HangmaRules.analyze 的 value_limits=None）；"
                "需在评估接线显式启用才到达候选。",
    },
]


def inspect(symbol: str) -> str:
    """判断一个事实名的可用性。"""

    where = _where(symbol)
    if not where:
        return MISSING
    if where in ("value_facts", "value_facts.routes[]", "value_facts.*.settlement"):
        return NEEDS_VALUE_ANALYSIS
    if where == "candidate_facts":
        return PRESENT
    if where in ("observation", "observation.rule_state"):
        if symbol in BASE_CONTEXT_FIELDS:
            return PRESENT
        if symbol in ("melds", "discards", "my_hand", "drawn_tile", "hand_counts",
                      "public_history", "chain_count", "baotou", "catch_play_owner_seat",
                      "wealth_god", "remaining_tile_count"):
            return NEEDS_CONTEXT
        return DERIVABLE
    return PRESENT


def build_inventory() -> dict:
    rows = []
    for mech in MECHANISMS:
        entry = {"id": mech["id"], "name": mech["name"], "source": mech["source"],
                 "note": mech["note"], "pre": [], "post": []}
        for side in ("pre", "post"):
            for symbol in mech[side]:
                status = inspect(symbol)
                item = {
                    "fact": symbol,
                    "layer": _where(symbol) or None,
                    "status": status,
                }
                if side == "post":
                    # 动作后事实必须写明**判定方式**，否则实现者会误读当前观察里的同名字段
                    item["determination"] = POST_DETERMINATION.get(symbol, "unknown")
                    if item["determination"] == "rule_transition":
                        item["status"] = "needs_rule_transition"
                entry[side].append(item)
        rows.append(entry)
    def collect(status: str) -> list:
        return sorted({item["fact"] for row in rows for side in ("pre", "post")
                       for item in row[side] if item["status"] == status})

    def collect_post(kind: str) -> list:
        return sorted({item["fact"] for row in rows for item in row["post"]
                       if item.get("determination") == kind})
    # 诚实标注：本清单只盘点这 7 个机制所需的事实，**不是对观察层的穷尽覆盖**。
    referenced = {item["fact"] for row in rows for side in ("pre", "post") for item in row[side]}
    uninventoried = sorted((OBSERVATION_FIELDS | RULE_STATE_FIELDS) - referenced)
    return {
        "schema": "sitin-fact-inventory/2",
        "legend": {
            "present": "基础评分上下文（EvaluationContext）直接可读",
            "needs_context": "字段已在观察中，但未接入基础评分上下文——纯接入改动",
            "derivable": "可从既有事实机械推导，不需新增观察",
            "needs_value_analysis": "规则可产出（value_facts），但 value_limits 默认关闭，需在评估接线显式启用",
            "needs_rule_transition": "动作后状态：须由 hangma 的状态推进给出；**当前观察里的同名字段不是动作后状态**",
            "missing": "当前各层都不提供，需要新增规则事实或诊断记录",
        },
        "mechanisms": rows,
        "summary": {
            "unclassified_facts": sorted({
                item["fact"] for row in rows for side in ("pre", "post")
                for item in row[side] if item["layer"] is None
            }),
            "missing_facts": collect(MISSING),
            "needs_context_facts": collect(NEEDS_CONTEXT),
            "derivable_facts": collect(DERIVABLE),
            "needs_value_analysis_facts": collect(NEEDS_VALUE_ANALYSIS),
            "needs_rule_transition_facts": collect("needs_rule_transition"),
            "post_by_determination": {
                "rule_transition": collect_post("rule_transition"),
                "candidate_fact": collect_post("candidate_fact"),
                "value_fact": collect_post("value_fact"),
            },
            "mechanism_count": len(rows),
            "uninventoried_observation_fields": uninventoried,
        },
    }


def render(report: dict) -> str:
    lines = ["# 坐隐 1.4 候选事实盘点", "",
             "| 状态 | 含义 |", "| --- | --- |",
             "| present | 基础评分上下文直接可读 |",
             "| needs_context | 观察里已有、但未接入基础评分上下文（纯接入改动） |",
             "| derivable | 可从既有事实机械推导 |",
             "| needs_value_analysis | 规则可产出，但 value_limits 默认关闭 |",
             "| missing | 各层都不提供，需新增 |", ""]
    for row in report["mechanisms"]:
        lines.append("## {0} {1}".format(row["id"], row["name"]))
        lines.append("")
        lines.append("来源：{0}".format(row["source"]))
        lines.append("")
        lines.append("| 阶段 | 事实 | 所在层 | 状态 | 动作后判定方式 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for side, label in (("pre", "动作前"), ("post", "动作后")):
            for item in row[side]:
                lines.append("| {0} | `{1}` | {2} | **{3}** | {4} |".format(
                    label, item["fact"], item["layer"] or "—", item["status"],
                    item.get("determination", "—")))
        lines.append("")
        lines.append("> " + row["note"])
        lines.append("")
    lines.append("## 汇总")
    lines.append("")
    s = report["summary"]
    lines.append("- **需新增（missing）**：{0}".format("、".join(s["missing_facts"]) or "无"))
    lines.append("- **需接入基础评分上下文（needs_context）**：{0}".format("、".join(s["needs_context_facts"]) or "无"))
    lines.append("- **需显式启用 value_limits（needs_value_analysis）**：{0}".format("、".join(s["needs_value_analysis_facts"]) or "无"))
    lines.append("- **动作后需规则推进给出（needs_rule_transition）**：{0}".format("、".join(s["needs_rule_transition_facts"]) or "无"))
    lines.append("")
    lines.append("  动作后事实按判定方式：规则推进 {0} 项、候选事实 {1} 项、分值分析 {2} 项。".format(
        len(s["post_by_determination"]["rule_transition"]),
        len(s["post_by_determination"]["candidate_fact"]),
        len(s["post_by_determination"]["value_fact"])))
    lines.append("- 可机械推导（derivable）：{0}".format("、".join(s["derivable_facts"]) or "无"))
    lines.append("")
    lines.append("**归属为『各层都不提供』的事实**：{0}".format(
        "、".join(s["unclassified_facts"]) or "无（经核实，fan 可由 value_facts 取到）"))
    lines.append("")
    lines.append("**本清单未覆盖的观察字段（共 {0} 个）**：{1}".format(
        len(s["uninventoried_observation_fields"]),
        "、".join(s["uninventoried_observation_fields"]) or "无"))
    lines.append("")
    lines.append("> 本清单只盘点上列 7 个机制所需的事实，**不是对观察层的穷尽覆盖**；"
                 "改用其他机制族时必须重新盘点。")
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="坐隐 1.4：候选事实盘点")
    parser.add_argument("--out", help="输出目录")
    args = parser.parse_args(argv)
    report = build_inventory()
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        from pathlib import Path
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "inventory.json").write_text(text + "\n", encoding="utf-8")
        (out / "inventory.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

