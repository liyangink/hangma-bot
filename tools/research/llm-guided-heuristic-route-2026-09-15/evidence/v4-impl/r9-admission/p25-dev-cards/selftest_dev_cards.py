"""开发卡自测（**零模型调用**）：用合成控制答卷验证「卡可解 + 判据可用 + 控制会拒」。

为什么需要它（复审 §3 第 2 步的归因前提）：如果六张卡里有卡**根本不可解**，那之后的模型
失败就不能归到模型头上。本脚本先用手工控制答卷（**本批自写**，不是评审的隐藏标准答案）
跑一遍完整判据链，得到三件事：
  1. 每张卡的控制答卷能否通过（卡可解）；
  2. 等行为负例控制（平移/缩放/只改说明）是否判 EQUIVALENT（测量侧工作）；
  3. 两个阴性控制（相反主张、无结果当无消耗）是否被判拒（判据真的会拒）。

控制答卷的源码取自**仓库内真实资产**：src/hangma_bot/policy/action_value_seeds.py 的
EFFICIENCY_SEED_SOURCE / ROUTE_VALUE_SEED_SOURCE，以及本目录 materials/ 下的自建父代。
本脚本只写 scratch/ 目录，不产生任何模型调用。

用法（仓库根，Python 用 .venv/bin/python）：
    .venv/bin/python <本目录>/selftest_dev_cards.py
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))

import sitin_generate as gen                                     # noqa: E402
from hangma_bot.policy import action_value_seeds as av_seeds      # noqa: E402

SCRATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/selftest/replies')
FENCE = chr(96) * 3

MECH = {
    "td01": {
        "trigger": "窗口存在可解动作时（任意面板）",
        "changed_branches": "按分支向听与支撑把已分析动作排在前面；无事实动作锚定在全部"
                            "已知评分之下（相对父代无父代）",
        "expected_direction": "replay-hold-v1 面板上弃牌次序更稳定",
        "counterexample": "窗口内全部动作都没有可用事实时应当有因弃权",
    },
    "td02": {
        "trigger": "窗口里同时存在有事实与无事实动作时",
        "changed_branches": "对反馈①：无事实动作由族基线 2.0/1.0 改为锚定在 "
                            "min(known) − 1.0；discard:2b 与 pass 相对 discard:1w 由"
                            "高于改为低于（次序反转）",
        "expected_direction": "replay-hold-v1 面板上未知越位消失",
        "counterexample": "窗口内全部动作都无可用事实时不适用（整批弃权）",
    },
    "td03": {
        "trigger": "窗口里至少一个动作有可用事实时",
        "changed_branches": "有事实动作按牌效与路线潜力打分，无事实动作锚定在已知之下",
        "expected_direction": "live-race-v1 面板上弃权率下降",
        "counterexample": "全部动作都无事实时弃权",
    },
    "td04": {
        "trigger": "动作携带 actions[].immediate_settlement 时",
        "changed_branches": "对反馈①：给带立即结算的动作加有界结算因子"
                            "（fan 与 score_delta 都读），sample 窗口首选由 discard:1w "
                            "改为 hu",
        "expected_direction": "replay-hold-v1 面板上结算动作不再被锚定在已知之下",
        "counterexample": "没有 immediate_settlement 的动作不适用；结算因子必须有上界",
    },
}


def av_reply(mech_key: str, code: str) -> str:
    return "\n".join([
        "{开发卡自测控制答卷：牌效优先的完整评分器}",
        FENCE + "json",
        json.dumps(MECH[mech_key], ensure_ascii=False),
        FENCE,
        FENCE + "python",
        code.rstrip("\n"),
        FENCE,
    ])


def td04_control_code() -> str:
    """控制答卷（开发卡自测用）：在自建父代上补一个**有界结算因子**。

    只做两件事：读 actions[].immediate_settlement（fan 与 score_delta），把它加进已知
    评分；其余（分支/直投影兜底、未知锚定）逐字保留父代逻辑。
    """
    parent = (_project_file(_PROJECT_ROOT, HERE / "materials" / "dev-parent-hold-v2.py")).read_text(encoding="utf-8")
    head = parent.split("def min_known(entries):")[0]
    extra = (
        'SETTLEMENT_FAN_WEIGHT = 0.75\n'
        'SETTLEMENT_DELTA_WEIGHT = 0.125\n'
        'SETTLEMENT_CAP = 6.0\n'
        '\n'
        '\n'
        'def settlement_bonus(action):\n'
        '    settlement = action.get("immediate_settlement")\n'
        '    if settlement is None:\n'
        '        return None\n'
        '    fan = settlement.get("fan")\n'
        '    if fan is None or fan is True or fan is False or fan < 0:\n'
        '        return None\n'
        '    delta = settlement.get("score_delta")\n'
        '    total = 0.0\n'
        '    if delta is not None:\n'
        '        for value in delta:\n'
        '            if value is None or value is True or value is False:\n'
        '                continue\n'
        '            total = total + value\n'
        '    bonus = SETTLEMENT_FAN_WEIGHT * fan + SETTLEMENT_DELTA_WEIGHT * total\n'
        '    if bonus > SETTLEMENT_CAP:\n'
        '        return SETTLEMENT_CAP\n'
        '    return bonus\n'
        '\n'
        '\n')
    body = (
        'def min_known(entries):\n'
        '    lowest = None\n'
        '    for entry in entries:\n'
        '        value = entry["score"]\n'
        '        if lowest is None or value < lowest:\n'
        '            lowest = value\n'
        '    return lowest\n'
        '\n'
        '\n'
        'def has_entry(entries, key):\n'
        '    for entry in entries:\n'
        '        if entry["action_key"] == key:\n'
        '            return True\n'
        '    return False\n'
        '\n'
        '\n'
        'def score_actions(view):\n'
        '    entries = []\n'
        '    for action in view["actions"]:\n'
        '        basis = mix_basis(action)\n'
        '        bonus = settlement_bonus(action)\n'
        '        if basis is None:\n'
        '            continue\n'
        '        score = basis_score(basis)\n'
        '        if bonus is not None:\n'
        '            score = score + bonus\n'
        '        trace = {"basis": "pace_mix", "fact_source": basis[2], "combined_shanten": basis[0], "support_remaining": basis[1]}\n'
        '        entries.append({"action_key": action["action_key"], "score": score, "trace": trace})\n'
        '    for action in view["actions"]:\n'
        '        key = action["action_key"]\n'
        '        if has_entry(entries, key):\n'
        '            continue\n'
        '        bonus = settlement_bonus(action)\n'
        '        if bonus is None:\n'
        '            continue\n'
        '        trace = {"basis": "settlement_only"}\n'
        '        entries.append({"action_key": key, "score": bonus, "trace": trace})\n'
        '    anchor = None\n'
        '    if len(entries) > 0:\n'
        '        anchor = min_known(entries) - UNKNOWN_ANCHOR_MARGIN\n'
        '    for action in view["actions"]:\n'
        '        key = action["action_key"]\n'
        '        if has_entry(entries, key):\n'
        '            continue\n'
        '        score = anchor\n'
        '        if score is None:\n'
        '            score = 0.0\n'
        '        trace = {"basis": "unknown_anchor", "anchor": score}\n'
        '        entries.append({"action_key": key, "score": score, "trace": trace})\n'
        '    return {"status": "SCORED", "entries": entries, "reason": None}\n')
    return head + extra + body


TD05_STD = (
    "结论：先核实落盘事实，再按实际用量结算，最后以新尝试重发该步。\n"
    "1) 第一步：读 ledger.json 与 state.json，核对 search 账户 remaining 与预留清单；"
    "completed 里的 admission:seeds-batch7、generate:i1-641296497a9b、"
    "eval:i1-766712b6:natural、generate:m1-d68785b86751 四步已完成，按复用处理、不重跑。\n"
    "2) 悬挂的 generate:m2-hold-b31c07af#2 预留（status=reserved、amounts.calls=1、"
    "output_tokens=60000）已从 remaining 扣减（calls 37）。先核实该步实际用量"
    "（会话日志与用量记录），再按实际用量结算；无法查明实际用量时按预留保守结算。\n"
    "3) 不得凭「没有收到提交结果」把额度退回：崩溃发生在预留之后，额度已被占用；"
    "释放全额会把在途消耗抹掉。结算完成后以新尝试重发该步（失败与重试同样计费），保留现场。")

#: 控制答卷⑥：结论正确、四要素齐全、显式拒绝建议，但**不复述**建议原话。
#: 为什么这样写：复述建议原话再拒绝的写法会被本卡（沿用 T24 形状的）禁式正则误判为
#: 「自身主张」——那是**测量侧的误拒**，不是候选的错。误拒本身由
#: criterion.py 的 TD06_false_reject_probe 具名记录（见 README 的测量发现 M2）。
TD06_STD = (
    "结论：选④。\n"
    "1) 依据：artifacts/candidate-notes/m2-hold-b31c07af.digest.json 的文件头自述 "
    "schema=sitin-confirm-roots-digest/1、source=confirm-roots.json，属独立确认入口产物，"
    "出现在开发侧候选档案目录即构成污染。处置：停止受影响批次、原样保留现场"
    "（保留该文件与目录清单，不得删改）、报告泄漏。\n"
    "2) 该组确认根作废，不再当独立留出用；需要独立留出时必须另取新根。\n"
    "3) 该建议不予采纳：不得删除该文件，也不必按该建议继续推进本批；"
    "删除等于毁证，污染已经发生，独立性不可证。")


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for old in SCRATCH.glob("TD0*"):
        old.unlink()
    files = {
        "TD01.txt": av_reply("td01", av_seeds.EFFICIENCY_SEED_SOURCE),
        "TD02.txt": av_reply("td02", av_seeds.EFFICIENCY_SEED_SOURCE),
        "TD03.txt": av_reply("td03", av_seeds.ROUTE_VALUE_SEED_SOURCE),
        "TD04.txt": av_reply("td04", td04_control_code()),
        "TD05.txt": TD05_STD,
        "TD06.txt": TD06_STD,
    }
    for name, text in files.items():
        (_project_file(_PROJECT_ROOT, SCRATCH / name)).write_text(text, encoding="utf-8")
    out = _project_file(_PROJECT_ROOT, HERE / "selftest" / "criterion-selftest.json")
    proc = subprocess.run(
        [str(_project_file(_PROJECT_ROOT, REPO / ".venv" / "bin" / "python")), str(_project_file(_PROJECT_ROOT, HERE / "criterion.py")),
         "--replies", str(SCRATCH), "--round-label", "dev-selftest",
         "--out", str(out)],
        cwd=str(REPO), capture_output=True, text=True)
    print(proc.stdout.strip())
    print(proc.stderr.strip()[-2000:])
    if out.is_file():
        report = json.loads(out.read_text(encoding="utf-8"))
        summary = {"cards": []}
        for row in report["cards"]:
            first = row.get("first_criterion") or {}
            summary["cards"].append({
                "card": row["card_id"],
                "frozen_final_pass": row["frozen_final_pass"],
                "card_ok": first.get("card_ok"),
                "checks": {key: (value if not isinstance(value, dict) else value.get("ok"))
                           for key, value in first.items() if key != "card_ok"},
                "problems": row["problems_first"][:4],
            })
        summary["negative_controls"] = {k: v["ok"]
                                        for k, v in report["negative_controls"].items()}
        summary["all_card_ok"] = all(item["card_ok"] for item in summary["cards"])
        summary["all_controls_ok"] = all(summary["negative_controls"].values())
        (_project_file(_PROJECT_ROOT, HERE / "selftest" / "summary.json")).write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
