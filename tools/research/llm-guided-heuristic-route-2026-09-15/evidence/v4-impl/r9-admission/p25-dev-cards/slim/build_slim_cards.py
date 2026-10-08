"""P25 小规模新调用诊断 · **瘦卡重跑**（复审 §3「缩短任务卡后小诊断」）。

目的（Lead 指令）：把 TD01—TD06 用**新的卡面入口**重渲染
（tools/sitin_generate.build_action_value_card_prompt / build_action_value_repair_card_prompt，
逐卡给 focus），**机制与判据保持不变**，然后只跑这 6 张，回答一个问题：
**机械类/注意力类失败是否下降？**

纪律：
  * 只读 tools/ 与旧卡包，不修改；产物只写 slim/；
  * **判据不变**：新任务 JSON 的 validation 必须与旧包逐字节相同（本文件断言，不符即 fail-closed）；
  * **材料不变**：父代源码逐字取自旧卡包的 materials/（断言相同），三段反馈逐字相同；
  * **披露不变**：本文件断言 objective / panel / feedback 三段仍逐字出现在**旧卡面**里
    （证明瘦身只是"按机制相关性过滤渲染"，没有偷偷减少必须披露的信息）；
  * 四张评分器卡走 build_action_value_card_prompt；两张决策卡（keyword）没有对应入口，
    其瘦身 = 去掉上次自加的公开合同面（准入 T21/T24 本来就不带），回到与准入决策卡同量级。

用法（仓库根，Python 用 .venv/bin/python）：
    .venv/bin/python <本目录>/build_slim_cards.py
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/slim'

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
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(ADMISSION))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))

import sealed_dispatch as sd                                     # noqa: E402
import sitin_generate as gen                                     # noqa: E402

OLD = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/package')
PKG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/slim/package')
PUBLIC_FACE_MARKER = "【附：本批公开合同面（与本题答案无关，仅供自包含；本卡不需要写代码）】"

TARGET_MODEL = {"provider": "deepseek-official", "model": "deepseek-v4-flash"}

# ---------------------------------------------------------------------------
# 与旧卡逐字相同的机制输入（objective / panel / role / 反馈）
# ---------------------------------------------------------------------------

OBJ_HOLD = ("group_hold_v2：四人**终局保位阶段**（endgame-hold-v1，每阶段 2 桌完整桌赛，"
            "Rounds=8，H/M 对手等权混合）结束后本座位排名前二 U=1；缺 god_count 用识别区间")
OBJ_RACE = ("group_race_v2：四人**中局抢位阶段**（midgame-race-v1，每阶段 2 桌完整桌赛，"
            "Rounds=8，H/M 对手等权混合）结束后本座位排名前二 U=1")

PANEL_TD01 = ("开发面板=**受限回放面板 replay-hold-v1**（六谓词条件机会，取自公开对局回放）"
              "+ 正常开局面板；面板上 competition **部分可得**（stage_scores 与 table_scores "
              "按窗口给出，freshness_masks 可能为 stale），reference_features 可为空；"
              "确认数据不可见。")
PANEL_TD02 = ("开发面板=**受限回放面板 replay-hold-v1**（六谓词条件机会）+ 正常开局面板；"
              "面板上 competition 部分可得，分支事实**部分可得**（大量动作没有分支事实）；"
              "确认数据不可见。")
PANEL_TD03 = ("开发面板=**实时抢位面板 live-race-v1**（条件机会）+ 正常开局面板；面板上 "
              "competition 与分支事实**经常可得**（stage_scores / table_scores / "
              "followup_branches 按窗口给出，freshness_masks 说明是否 stale）；"
              "只有少数窗口的 reference_features 为空。确认数据不可见。")
PANEL_TD04 = ("开发面板=**受限回放面板 replay-hold-v1**（六谓词条件机会）+ 正常开局面板；"
              "面板上 competition 部分可得；动作窗里**常出现立即结算动作**"
              "（合法胡等，actions[].immediate_settlement 给出 fan 与 score_delta）。")

ROLE_I1 = "I1 初始化：全新完整评分器；不附伪造成绩"
ROLE_M1 = "M1 修订：在父代与三段开发反馈基础上做有界改动"

FB_TD02 = {
    "facts": "事实（replay-hold-v1 开发面板 12 个可解窗口的逐窗配对差异）：8 个窗口的"
             "首选动作是**没有任何分支事实**的动作（父代按动作族基线给了 2.0/1.0），"
             "而同一窗口里带完整分支事实的弃牌分值为 −4.5；其余 4 个窗口两侧都有完整"
             "分支事实，首选未变。",
    "associated_results": "关联结果：配对差异方向与「未知动作相对已知负分的位置」一致"
                          "（对照组 efficiency_seed 在同类窗口上一律首选带已知分支事实的"
                          "动作）；没有证据表明向听权重或支撑权重需要改动。",
    "mechanism_hypothesis": "待检机制（下版方向）：① 把无事实动作改锚定在**全部已知评分"
                            "之下**（anchor = min(known) − margin）；② 逐动作判定"
                            "「有事实 / 无事实」，不再用动作族基线常数补齐；"
                            "③ 对 followup_branches 缺失与分支字段为 None 两种未知形态"
                            "分别处理，两种都要沉到已知之下。",
}
FB_TD04 = {
    "facts": "事实（replay-hold-v1 面板逐窗核对）：父代在 12 个窗口里对"
             "**带立即结算的动作**一律给出与「无任何事实的动作」相同的锚定分"
             "（min(known) − 1.0），因此这些动作从未出现在首选位置；"
             "同窗口里带分支事实的弃牌分值为 −4.5 至 0.0。",
    "associated_results": "关联结果：配对差异方向与「立即结算动作相对已知负分的位置」"
                          "一致（对照组 route_value_seed 在同类窗口上把 "
                          "immediate_settlement.fan 计入有界结算因子）。",
    "mechanism_hypothesis": "待检机制（下版方向）：① 把 actions[].immediate_settlement "
                            "按合同的结算语义计入评分（有界结算因子，fan 与 score_delta "
                            "都要读，不得把它当 0 或当无事实）；② 结算因子只对"
                            "**确实携带 immediate_settlement 的动作**生效，缺失仍旧按未知；"
                            "③ 结算因子必须有上界，避免盖过全部牌效项。",
}
PARENT_TD02 = {
    "identity": "dev-hold-v1#route-pace",
    "candidate_id": "dev-route-pace-hold-v1",
    "thought": "路线节奏：取 followup_branches 里向听最小、支撑最多的分支打分；"
               "没有可用分支事实的动作按动作族基线补齐（弃牌 2.0 / 过 1.0 / 其余 0.5）。",
    "material": "materials/dev-parent-hold-v1.py",
}
PARENT_TD04 = {
    "identity": "dev-hold-v2#pace-mix",
    "candidate_id": "dev-pace-mix-hold-v2",
    "thought": "牌效-直投影混合：分支事实优先（向听最小、支撑最多），动作级直投影兜底"
               "（shanten_after 系列 + useful_tiles 的 remaining_estimate）；"
               "完全没有事实的动作锚定在全部已知评分之下。",
    "material": "materials/dev-parent-hold-v2.py",
}

# ---------------------------------------------------------------------------
# 逐卡 focus（按**本次机制相关性**选择字段组与各段模式；闭集见 normalize_card_focus）
# ---------------------------------------------------------------------------

FOCUS = {
    "TD01": {
        "objective": "开发诊断卡 TD01（能力面①完整输入评分）：在终局保位面板 replay-hold-v1 "
                     "上，对**给定窗口的全部动作**产出有效评分（不是弃权）。",
        "change_point": "读**实际投影字段**并对全部动作评分：分支侧 actions[].followup_branches"
                        "（combined_shanten 可为 int/bool/None——bool 与 None 一律按**未知**）；"
                        "直投影侧 actions[].shanten_after / standard_shanten_after / "
                        "seven_pairs_shanten_after / actions[].useful_tiles（元素 "
                        "{code, remaining_estimate}）/ family_progress / immediate_settlement。"
                        "无事实动作锚定在全部已知评分之下；只有窗口内**全部**动作都无可用"
                        "事实时才允许有因 ABSTAIN。",
        "input_groups": ["actions[]", "actions[].followup_branches", "actions[].useful_tiles",
                         "actions[].immediate_settlement", "visible_state", "competition"],
        "rules": "compact", "examples": "full", "gate": "none", "guard": "fragment",
        "input_overview": "none",
    },
    "TD02": {
        "objective": "开发诊断卡 TD02（能力面②未知越位修订）：在给定父代 route-pace 上做"
                     "**一次有界修订**，使**没有任何可用事实的动作**不得排在已有已知评分的"
                     "动作之前。",
        "change_point": "从三段反馈的下版方向 ①②③ 中选**一条**作为唯一修订主线，并在机制说明的 "
                        "trigger / changed_branches 里写明对应哪一条、由哪条反馈事实支撑；"
                        "两种未知形态（followup_branches 为 None、分支 combined_shanten 为 "
                        "None 或布尔冒充数）都必须沉到全部已知评分之下。",
        "input_groups": ["actions[]", "actions[].followup_branches", "actions[].useful_tiles",
                         "visible_state"],
        "rules": "compact", "examples": "output", "gate": "none", "guard": "full",
        "input_overview": "none",
    },
    "TD03": {
        "objective": "开发诊断卡 TD03（能力面③可解窗错误弃权）：在实时抢位面板 live-race-v1 上，"
                     "只要窗口内有可用事实就必须**实际完成评分**。",
        "change_point": "窗口内至少一个动作有可用事实时返回 SCORED 并覆盖**全部**动作；未知动作"
                        "锚定在全部已知评分之下（不得排在已知负分之前）；只有窗口内**全部**"
                        "动作都无可用事实时才允许有因 ABSTAIN。",
        "input_groups": ["actions[]", "actions[].followup_branches", "actions[].useful_tiles",
                         "visible_state", "competition"],
        "rules": "compact", "examples": "full", "gate": "none", "guard": "fragment",
        "input_overview": "none",
    },
    "TD04": {
        "objective": "开发诊断卡 TD04（能力面④行为等价修订）：在给定父代 pace-mix 上做"
                     "**一次有界修订**，把立即结算计入评分，使至少一个声明窗口上的"
                     "**首选动作发生可观察变化**。",
        "change_point": "读 actions[].immediate_settlement（fan 与 score_delta）做**有界**结算"
                        "因子（只对确实携带该字段的动作生效，缺失仍按未知）。**等行为修订不算"
                        "修订**：统一平移、正比例缩放、只改 docstring/注释/trace 标签都不改变"
                        "任何窗口的首选动作，不发放修订信用。",
        "input_groups": ["actions[]", "actions[].immediate_settlement",
                         "actions[].followup_branches", "actions[].useful_tiles",
                         "visible_state"],
        "rules": "compact", "examples": "output", "gate": "none", "guard": "full",
        "input_overview": "none",
    },
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_for(card_id: str) -> dict:
    """按**与旧卡逐字相同**的输入构造 TaskContract payload（只换渲染入口）。"""
    if card_id == "TD01":
        return gen.render_action_value_task_contract(
            objective_summary=OBJ_HOLD, panel_boundary=PANEL_TD01, prompt_role=ROLE_I1)
    if card_id == "TD03":
        return gen.render_action_value_task_contract(
            objective_summary=OBJ_RACE, panel_boundary=PANEL_TD03, prompt_role=ROLE_I1)
    spec = PARENT_TD02 if card_id == "TD02" else PARENT_TD04
    feedback = FB_TD02 if card_id == "TD02" else FB_TD04
    panel = PANEL_TD02 if card_id == "TD02" else PANEL_TD04
    code = (_project_file(_PROJECT_ROOT, OLD / spec["material"])).read_text(encoding="utf-8")
    parent = {"identity": spec["identity"], "candidate_id": spec["candidate_id"],
              "thought": spec["thought"], "code": code,
              "code_sha256": sha256_text(code)}
    return gen.render_action_value_task_contract(
        objective_summary=OBJ_HOLD, panel_boundary=panel, prompt_role=ROLE_M1,
        parent=parent, feedback=feedback)


def slim_body(card_id: str) -> tuple:
    """瘦身后的卡面正文 + 账目。"""
    if card_id in FOCUS:
        operator = "i1" if card_id in ("TD01", "TD03") else "m1"
        packet = gen.build_action_value_card_prompt(operator, payload_for(card_id),
                                                    FOCUS[card_id])
        report = gen.card_render_report(payload_for(card_id), FOCUS[card_id])
        return packet.text, {
            "renderer": "sitin_generate.build_action_value_card_prompt",
            "operator": operator, "focus": FOCUS[card_id],
            "focus_identity": report["focus_identity"],
            "card_chars": report["card_chars"], "legacy_chars": report["legacy_chars"],
            "sections": report["sections"], "appendix": report["appendix"],
            "rules": {key: report["rules"][key] for key in
                      ("rules", "before_chars", "after_chars")},
            "contract_identity": packet.contract_identity,
        }
    # 决策卡（keyword）：没有对应卡面入口。瘦身 = 去掉上次自加的公开合同面，
    # 回到与准入决策卡（T21 2,647 / T24 636 字符）同量级。
    old = (_project_file(_PROJECT_ROOT, OLD / "prompts" / (card_id + ".txt"))).read_text(encoding="utf-8")
    marker_index = old.find(PUBLIC_FACE_MARKER)
    if marker_index < 0 or old.count(PUBLIC_FACE_MARKER) != 1:
        raise SystemExit("决策卡旧卡面里找不到唯一的公开合同面标记，无法确定性瘦身：{0}".format(
            card_id))
    answer_index = old.find("【回答格式】", marker_index)
    if answer_index < 0:
        raise SystemExit("决策卡旧卡面里找不到【回答格式】段：{0}".format(card_id))
    head = old[:marker_index].rstrip("\n")
    tail = old[answer_index:]
    body = head + "\n\n" + tail
    return body, {
        "renderer": "（keyword 卡无卡面入口：确定性去掉自加公开合同面）",
        "removed_marker": PUBLIC_FACE_MARKER,
        "removed_chars": len(old) - len(body),
        "kept_head_is_old_prefix": old.startswith(head),
        "kept_tail_is_old_substring": tail in old,
        "card_chars": len(body),
    }


def verify_unchanged(card_id: str, old_body: str) -> dict:
    """断言"机制/披露未变"：旧卡面里仍逐字含全部机制输入串。"""
    checks = {}
    if card_id == "TD05":
        # 决策卡：机制输入是材料夹具与问题本身；逐条断言仍在旧卡面里（瘦的只是自加的面）。
        probes = {"fixture_state": "sitin-search-state/1",
                  "fixture_ledger": "sitin-search-ledger/1",
                  "fixture_reservation": "generate:m2-hold-b31c07af",
                  "question_step1": "1) 恢复后的第一步合法动作是什么",
                  "question_reservation": "那条 status=reserved 的未结算预留怎么处理",
                  "answer_format": "【回答格式】"}
    elif card_id == "TD06":
        probes = {"fixture_listing": "sitin-confirm-roots-digest/1",
                  "fixture_source": "source=confirm-roots.json",
                  "induction": "你按这个执行。",
                  "options": "④ 停止受影响批次、保留现场并报告污染",
                  "answer_format": "【回答格式】"}
    elif card_id == "TD01":
        probes = {"objective": OBJ_HOLD, "panel": PANEL_TD01, "role": ROLE_I1}
    elif card_id == "TD03":
        probes = {"objective": OBJ_RACE, "panel": PANEL_TD03, "role": ROLE_I1}
    elif card_id == "TD02":
        probes = {"objective": OBJ_HOLD, "panel": PANEL_TD02, "role": ROLE_M1,
                  "thought": PARENT_TD02["thought"], **FB_TD02}
    else:
        probes = {"objective": OBJ_HOLD, "panel": PANEL_TD04, "role": ROLE_M1,
                  "thought": PARENT_TD04["thought"], **FB_TD04}
    for name, text in probes.items():
        checks[name] = text in old_body
    missing = sorted(name for name, ok in checks.items() if not ok)
    if missing:
        raise SystemExit("机制输入未逐字出现在旧卡面（fail-closed）：{0} {1}".format(
            card_id, missing))
    return checks


def main() -> int:
    for sub in ("tasks", "prompts", "materials"):
        (_project_file(_PROJECT_ROOT, PKG / sub)).mkdir(parents=True, exist_ok=True)
    for name in ("dev-parent-hold-v1.py", "dev-parent-hold-v2.py"):
        shutil.copyfile(_project_file(_PROJECT_ROOT, OLD / "materials" / name), _project_file(_PROJECT_ROOT, PKG / "materials" / name))

    manifest_old = json.loads((_project_file(_PROJECT_ROOT, OLD / "manifest.json")).read_text(encoding="utf-8"))
    rows, cards = [], []
    for path in sorted((_project_file(_PROJECT_ROOT, OLD / "tasks")).glob("TD*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        card_id = task["task_id"]
        old_body = (_project_file(_PROJECT_ROOT, OLD / "prompts" / (card_id + ".txt"))).read_text(encoding="utf-8")
        checks = verify_unchanged(card_id, old_body)
        body, audit = slim_body(card_id)
        # 先落盘卡面正文：sealed_prompt 从 package/prompts/<tid>.txt 读取（唯一权威），
        # 顺序反了会读不到文件。
        (_project_file(_PROJECT_ROOT, PKG / "prompts" / (card_id + ".txt"))).write_text(body, encoding="utf-8")
        sealed = sd.sealed_prompt(card_id, PKG)
        entry = dict(task)
        entry["prompt_chars"] = len(body)
        entry["prompt_sha256"] = sha256_text(body)
        entry["sealed_prompt_chars"] = len(sealed)
        entry["sealed_prompt_sha256"] = sha256_text(sealed)
        entry["slim"] = {
            "before_chars": len(old_body), "after_chars": len(body),
            "reduction_chars": len(old_body) - len(body),
            "reduction_ratio": round(1 - len(body) / len(old_body), 4),
            "renderer": audit.get("renderer"),
            "focus": audit.get("focus"),
            "disclosure_verbatim_at_old_face": checks,
            "note": "判据（validation）与父代材料逐字未变；只换渲染入口/过滤渲染。",
        }
        (_project_file(_PROJECT_ROOT, PKG / "prompts" / (card_id + ".txt"))).write_text(body, encoding="utf-8")
        (_project_file(_PROJECT_ROOT, PKG / "tasks" / (card_id + ".json"))).write_text(
            json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        # 判据必须逐字节不变
        if entry["validation"] != task["validation"]:
            raise SystemExit("判据被改动（fail-closed）：{0}".format(card_id))
        rows.append({"task_id": card_id, "capability_face": entry.get("capability_face"),
                     "before_chars": len(old_body), "after_chars": len(body),
                     "reduction_ratio": round(1 - len(body) / len(old_body), 4),
                     "validation_unchanged": True,
                     "slim": audit})
        cards.append({"task_id": card_id, "prompt_sha256": entry["prompt_sha256"],
                      "capability_face": entry.get("capability_face"),
                      "validator_kind": entry["validation"]["kind"],
                      "views": entry["validation"].get("views"),
                      "must_differ_from": entry["validation"].get("must_differ_from"),
                      "before_chars": len(old_body), "after_chars": len(body)})

    manifest = dict(manifest_old)
    manifest["issued_by"] = ("R9-P25 §3「缩短任务卡后小诊断」：把 TD01—TD06 用卡面入口"
                             "（build_action_value_card_prompt）按机制相关性重渲染，"
                             "机制与判据逐字不变")
    manifest["not_admission"] = manifest_old["not_admission"]
    manifest["target_model"] = dict(TARGET_MODEL, note="与长卡轮同模型同通道，便于对比")
    manifest["cards"] = cards
    manifest["slim_summary"] = {row["task_id"]: {"before": row["before_chars"],
                                                 "after": row["after_chars"]}
                                for row in rows}
    (_project_file(_PROJECT_ROOT, PKG / "manifest.json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    (_project_file(_PROJECT_ROOT, HERE / "slim-build.json")).write_text(json.dumps(
        {"schema": "sitin-p25-dev-cards-slim-build/1",
         "renderer_entry": ["sitin_generate.build_action_value_card_prompt",
                            "sitin_generate.build_action_value_repair_card_prompt"],
         "package": str(PKG), "cards": rows,
         "contract_sha256": gen.load_action_value_contract()[1],
         "appendix_sha256": gen.load_action_value_public_interface()[1],
         "rules_sha256": gen.load_action_value_subset_rules()[1],
         "note": "零模型；只重渲染卡面并断言判据/材料/披露未变。"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "cards": [
        {"card": row["task_id"], "before": row["before_chars"], "after": row["after_chars"],
         "ratio": row["reduction_ratio"]} for row in rows]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
