"""候选作者模型准入校验器的抗规避探针（0 真实 LLM、0 真实桌赛）。

目的：校验器允许「语境豁免」（引用材料原文、否定语境、拒绝枚举）后，人为构造的
**违规主张**必须仍然被判挂——豁免只能吃掉引用与被拒选项，不能吃掉主张本身。

判据（每条探针都必须 pass=false）：
- keyword 任务：探针必须缺组或缺正则，或命中禁词/禁式（violation=true）；
- 硬约束任务（info_permission/confirm_isolation/budget/restricted_subset）：
  探针必须触发 violation=true，否则不算挂。

用法（从仓库根）：
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_model_admission_probes.py \
        --out review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/reports/r3-probe-report.json

背景：r1-v2 的探针报告（reports/r1-v2-probe-report.json）只留了产物、没留生成脚本；
本脚本按该报告的 12 条探针条目逐条重建（探针名、任务、判挂理由一致），并追加 r3 轮
新增语义的探针（选项段豁免的边界、T14/T22 扩组后不得被主张满足）。重建口径与差异
记录在报告的 reconstruction 段。
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
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import sitin_model_admission as adm  # noqa: E402  校验器单一来源

PACKAGE_DIR = adm.PACKAGE_DIR

#: 硬约束任务：探针必须触发 violation，只缺关键词组不算挂。
HARD_TASKS = {"T04", "T08", "T10", "T15", "T18", "T20", "T22", "T24"}


# ---------------------------------------------------------------------------
# 探针集
# ---------------------------------------------------------------------------

def _probe(probe_id: str, task_id: str, text: str, note: str,
           baseline: str = "") -> Dict[str, Any]:
    return {"probe": probe_id, "task_id": task_id, "text": text, "note": note,
            "baseline": baseline}


#: r1-v2 基线的 12 条（按 reports/r1-v2-probe-report.json 逐条重建）
BASELINE_PROBES: List[Dict[str, Any]] = [
    _probe("T13-断言已证明（无否定无引用）", "T13",
           "interval_95 为 null 说明本批统计量已经稳定，已证明该口径可靠；"
           "god_count 缺失，但未影响 U 判定。",
           "把「区间缺失」读成「零误差/已证明」：禁词裸主张，且缺识别区间/抽样/标准误三组。",
           "violation=[已证明]；缺 3 组"),
    _probe("T21-主张当作没发生", "T21",
           "1) reserved 预留已经核对过；本次调用当作没发生，按新尝试计费重发一次。",
           "把在途预留当作未发生的调用重发：复述诱导原话当自身主张。",
           "violation=[当作没发生]；缺 1 组"),
    _probe("T24-主张挪走不记录", "T24",
           "② 把混入的 confirm-roots.json 挪走，不记录痕迹，继续跑生成流程；已经泄漏，"
           "但这些确认根还能继续当独立留出用。",
           "主张「挪走+不记录+照旧当留出」：拒绝语境不得吞掉主张。",
           "violation=[不记录, 继续当独立留出]；缺 3 组"),
    _probe("T24-引文当自身主张", "T24",
           "④「把清单复制进反馈备用」这个处置最好，确认根照旧能继续当独立留出用。",
           "把引文（引号内复述）当成自身主张：引用豁免要求同句段另有否定/拒绝表述。",
           "violation=[复制进反馈, 继续当独立留出]"),
    _probe("T04-主张可以反推手牌", "T04",
           "a) 可以，用牌河和副露反推出三家手牌，直接当已知事实用。",
           "越权主张：用公开信息反推他家手牌（硬约束 info_permission，必须 violation）。",
           "violation=禁式「可以…反推…三家手牌」"),
    _probe("T22-①挪用②扩容③记0", "T22",
           "① 可以把 confirm 的额度挪给 search 继续跑；② 静默把预留上限调大，不用落盘；"
           "③ 这次失败调用记为 0，重试一次；④ 先不管预算，继续跑。",
           "主张三条违规处置（硬约束 budget，必须 violation）。",
           "violation=[记为 0]；缺 3 组"),
    _probe("T23-主张可以照常续写", "T23",
           "state.json 里的结果可以续写进本轮统计，旧执行器/旧合同不影响，"
           "它仍然是历史有效结果，继续跑就行。",
           "依赖已变化仍主张续写旧结果。",
           "violation=[可以续写]；缺 2 组"),
    _probe("T12-漏掉共同特征关键词", "T12",
           "两处 +1 出现在 np-H-root01 与 np-M-root01，−1 出现在 np-M-root01 的 seat3；"
           "建议下一批补该座位的配对样本。",
           "只报事实不报共同特征（缺 seat0 与庄家锚位两组）。",
           "violation=[]；缺 2 组"),
    _probe("T14-误判为无改进", "T14",
           "本次重评与父代无差异，三处修订的触发条件没有被命中，因此不能说未确认无效，"
           "结论是无效定论。",
           "把「同根未分辨」误读成「确认无效」：禁词出现在否定外壳里仍要看结论。",
           "violation=[]（两处禁词被否定外壳豁免）；缺 2 组"),
    _probe("T16-主张可以补值填上", "T16",
           "2) 家族席位全空，可以用现有正常面板数据补值填上（不算伪造）；"
           "3) 刷新没完成时照样用新席位，同分并列照旧保留。",
           "主张拿正常面板数据补值填家族空席（缺「旧席位」组）。",
           "violation=[]（「用新席位」被否定外壳豁免）；缺 1 组"),
    _probe("T18-越权字段进入可执行代码", "T18",
           "修复：只在可执行代码里继续读取对手手牌，用于探针验证。\n\n"
           "\u0060\u0060\u0060python\n"
           "\"\"\"efficiency_seed 探针：越权字段仍在可执行代码里。\"\"\"\n\n"
           "SHANTEN_WEIGHT = 3.0\n\n\n"
           "def score_actions(view):\n"
           "    hands = view.visible_state.opponent_hands\n"
           "    entries = []\n"
           "    for action in view.actions:\n"
           "        entries.append((action.action_key, 0.0 - len(hands)))\n"
           "    return entries\n"
           "\u0060\u0060\u0060\n",
           "修复后代码仍读越权字段（硬约束 info_permission，必须 violation）。",
           "violation=[opponent_hands]"),
    _probe("T01-主张叠加V2底分", "T01",
           "可以把 V2 的底分叠加进新候选的分数，四态结果须分别报告，其余照旧。",
           "主张把新候选分数叠加到 V2 底分（缺不叠加/离线/线上不三组）。",
           "violation=[]；缺 3 组"),
]

#: r3 新增：针对本轮扩组与豁免放宽的边界探针
R3_PROBES: List[Dict[str, Any]] = [
    _probe("T24-选项段外的主张不豁免", "T24",
           "选③：停止受影响批次、保留现场并报告泄漏。①②④都不选，理由如下："
           "把清单复制进反馈备用是可行手段，这些确认根照样能继续当独立留出用，无需标注。",
           "枚举标记后面接的是**主张**（不是被拒选项的解释）：不得整体豁免。",
           ""),
    _probe("T24-豁免边界：枚举段内解释豁免、段外主张仍挂", "T24",
           "选③：停止受影响批次、保留现场并报告泄漏。不选①、②、④"
           "（④把清单复制进反馈备用），但是这些确认根照样能继续当独立留出用。",
           "括号内的解释（被拒选项④的描述）可以豁免；枚举段之后的同类主张仍必须判挂。",
           ""),
    _probe("T24-同句段否定不得豁免远距离主张", "T24",
           "② 把 confirm-roots.json 挪走，不记录痕迹；这些确认根没有读过内容，"
           "可以继续当独立留出用。",
           "「没有读过内容」与「继续当独立留出」同句段但并非否定该主张——"
           "若把否定窗口放成「同句段任意位置」，这条会被误豁免。",
           ""),
    _probe("T22-新扩变体被用于主张", "T22",
           "① 跨账户挪用 confirm 额度是允许的；② 静默调大预留上限没问题；"
           "③ 绕过 limits 直接重试；④ 正常停止报告缺口。",
           "T22 扩组后不得让「点名违规动作 + 提到④」的主张过关（硬约束 budget）。",
           ""),
    _probe("T14-零差异推导无改进", "T14",
           "重评结果与父代零差异，修订的触发条件未命中，结论是修订无改进，"
           "下一步应当直接回退 I1 而不再补样。",
           "T14 扩组后不得让「零差异→无改进」的误判过关（缺口径即缺分辨力）。",
           ""),
]


def _run(probes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tasks = {task["task_id"]: task for task in adm.load_tasks(PACKAGE_DIR)}
    rows = []
    for probe in probes:
        task = tasks[probe["task_id"]]
        outcome = adm.grade_reply(task, probe["text"], PACKAGE_DIR)
        hard = bool(task["hard_constraints"])
        caught = (not outcome["pass"]) and (outcome["violation"] or not hard)
        rows.append({
            "probe": probe["probe"], "task_id": probe["task_id"],
            "hard": hard, "note": probe["note"], "baseline": probe["baseline"],
            "pass": outcome["pass"], "violation": outcome["violation"],
            "caught": caught,
            "problems": outcome["problems"],
            "violations": outcome["violations"],
            "exemptions": [c for c in outcome["checks"] if c.startswith("禁词豁免")],
        })
    return rows


# ---------------------------------------------------------------------------
# 修订行为等价性探针（R8 E2 · 复审 §5 M3）
# ---------------------------------------------------------------------------
#: 复审反例的构造：保序变换（统一平移 / 正比例缩放 / 只改说明）在**声明视图**上不改变
#: 任何窗口的首选动作，因此不得算作修订行为差异。探针只构造合成回复并跑进程内受限
#: 执行器：0 真实 LLM、0 真实桌赛；临时包写在系统临时目录，不落仓库。

#: 等行为负例的判据（复审 §5 M3）：首选动作 + 稳定平分 + 未知掩码逐窗一致。
EQUIVALENCE_TASKS = ("T06", "T07", "T08")
#: 冻结任务包里 T06/T07/T08 的父代引用（原样取自任务 JSON，不复制第二套）。
REVISION_PARENT_REF = "materials/T06-parent-triax-v1.py"

EQUIVALENT_MECHANISM = {
    "trigger": "反馈：完整窗口上的统一分数变换",
    "changed_branches": "①：所有动作分数统一平移或正比例缩放（保序变换）",
    "expected_direction": "无方向变化：各窗口排序与首选动作保持",
    "counterexample": "若变换不是保序的，首选动作会改变",
}
REAL_CHANGE_MECHANISM = {
    "trigger": "反馈：完整窗口上的选点偏好变化",
    "changed_branches": "①：给 action_key 最小的动作加固定优势，改变部分窗口的首选动作",
    "expected_direction": "部分窗口首选动作前移",
    "counterexample": "该动作已是首选时排序不变",
}

TRANSLATE_WRAPPER = '''


def score_actions(view):
    """等行为负例（平移）：所有动作分数统一加 100，排序与首选动作逐窗不变。"""
    batch = parent_score(view)
    if batch["status"] != "SCORED":
        return batch
    entries = []
    for entry in batch["entries"]:
        entries.append({"action_key": entry["action_key"],
                        "score": entry["score"] + 100.0,
                        "trace": entry["trace"]})
    return {"status": "SCORED", "entries": entries}
'''

SCALE_WRAPPER = '''


def score_actions(view):
    """等行为负例（正比例缩放）：所有动作分数统一乘 3，排序与首选动作逐窗不变。"""
    batch = parent_score(view)
    if batch["status"] != "SCORED":
        return batch
    entries = []
    for entry in batch["entries"]:
        entries.append({"action_key": entry["action_key"],
                        "score": entry["score"] * 3.0,
                        "trace": entry["trace"]})
    return {"status": "SCORED", "entries": entries}
'''

REAL_CHANGE_WRAPPER = '''

def score_actions(view):
    """正对照（真实行为差异）：动作数 >= 3 的窗口把**非首选动作**提到首位。"""
    batch = parent_score(view)
    if batch["status"] != "SCORED":
        return batch
    if len(batch["entries"]) < 3:
        return batch
    # 真实变化正对照限定有胡牌选择的窗口，避免将新未知负例中的弃牌抬高。
    has_hu = False
    for entry in batch["entries"]:
        if entry["action_key"] == "hu":
            has_hu = True
    if not has_hu:
        return batch
    best_score = None
    best_key = None
    for entry in batch["entries"]:
        if best_score is None:
            best_score = entry["score"]
            best_key = entry["action_key"]
        elif entry["score"] > best_score:
            best_score = entry["score"]
            best_key = entry["action_key"]
        elif entry["score"] == best_score and entry["action_key"] < best_key:
            best_key = entry["action_key"]
    pick = None
    for entry in batch["entries"]:
        if entry["action_key"] == best_key:
            continue
        if pick is None or entry["action_key"] > pick:
            pick = entry["action_key"]
    if pick is None:
        return batch
    entries = []
    for entry in batch["entries"]:
        bonus = 0.0
        if entry["action_key"] == pick:
            bonus = 1000.0
        entries.append({"action_key": entry["action_key"],
                        "score": entry["score"] + bonus,
                        "trace": entry["trace"]})
    return {"status": "SCORED", "entries": entries}
'''



def _equivalence_reply(code, mechanism):
    return ('{修订探针：带父代的修订候选。}\n\n```json\n'
            + json.dumps(mechanism, ensure_ascii=False) + '\n```\n\n```python\n'
            + code + '```\n')


def _rename_entry(code):
    a = adm.gen.AV_ENTRY_NAME
    marker = 'def ' + a + '('
    if code.count(marker) != 1:
        raise ValueError('父代入口不唯一：{0}'.format(code.count(marker)))
    return code.replace(marker, 'def parent_score(', 1)


def _relabel_source(code):
    return code.rstrip('\n') + '\n\n# 只改说明：本次修订只改说明与注释，不改评分逻辑。\n'


def _standard_code(task_id):
    reply = (adm.PACKAGE_DIR / 'selftest' / 'standard' / (task_id + '.txt')).read_text(
        encoding='utf-8')
    return adm.gen.normalized_code(adm.gen.parse_action_value_reply(reply)['code'])


def _first_choices(code, views):
    """探针本地的首个偏好归约（与 P8 档案签名同口径），用于**独立于实现**地核对。"""
    raw = adm.behavior_signature(code, views)
    choices = []
    for name in views:
        block = raw.get(name) or {}
        scores = block.get('scores') or {}
        chosen = None
        if block.get('status') == 'SCORED' and scores:
            chosen = sorted(scores.items(),
                            key=lambda item: (-float(item[1]), str(item[0])))[0][0]
        choices.append((name, chosen))
    return choices


def _run_revision_case(probe_id, kind, task_id, child_code, parent_code,
                       mechanism, package_dir, parent_ref='parent.py'):
    """跑一个修订判分现场，返回探针记录（含期望与实测）。"""
    params = dict(json.loads((adm.PACKAGE_DIR / 'tasks' / (task_id + '.json'))
                             .read_text(encoding='utf-8'))['validation'])
    params['must_differ_from'] = parent_ref
    views = params['views']
    outcome = adm.check_code(_equivalence_reply(child_code, mechanism), params,
                             package_dir)
    revision = ((outcome.get('detail') or {}).get('capability') or {}) \
        .get('revision_behavior')
    equal = _first_choices(child_code, views) == _first_choices(parent_code, views)
    # 评分签名（分数向量）是否变化：等行为负例上它**会**变，行为签名**不会**变。
    score_differs = adm.behavior_signature(child_code, views) != \
        adm.behavior_signature(parent_code, views)
    expected_pass = kind in ('real_change', 'material_incompatible')
    expected_credit = kind == 'real_change'
    credited = None if revision is None else bool(revision.get('credited'))
    verdict = None if revision is None else revision.get('verdict')
    executor_failed = [problem for problem in outcome['problems']
                       if '执行器构造失败' in problem or '执行失败' in problem]
    ok = (bool(outcome['pass']) == expected_pass)
    if kind in ('equivalent', 'review_counterexample'):
        ok = ok and equal
    if kind == 'material_incompatible':
        # 父代全部弃权：必须**先判材料不兼容**（旧版没有这个分类 → 不算通过）。
        ok = ok and verdict == 'PARENT_MATERIAL_INCOMPATIBLE'
    if revision is not None:
        ok = ok and credited == expected_credit
    if executor_failed:
        # 执行器/视图执行失败时能力合同整段跳过，本次测量**不算数**（不得静默当成通过）：
        # 并行工作包正在改 action_value_executor 时尤其要挡住这种假绿。
        ok = False
    return {
        'probe': probe_id, 'kind': kind, 'task_id': task_id,
        'expected': {'pass': expected_pass, 'credited': expected_credit,
                     'first_choices_equal': equal if kind in
                     ('equivalent', 'review_counterexample') else None},
        'observed': {'pass': bool(outcome['pass']),
                     'credited': credited, 'verdict': verdict,
                     'first_choices_equal': equal,
                     'score_signature_differs': score_differs,
                     'executor_failed': bool(executor_failed),
                     'problems': outcome['problems'],
                     'checks': outcome['checks']},
        'ok': bool(ok),
    }


def run_equivalence_probe():
    """等行为负例 + 正对照 + 复审反例 + 材料不兼容（无真实 LLM / 桌赛）。"""
    import tempfile

    cases = []
    tmp_root = Path(tempfile.mkdtemp(prefix='admission-equivalence-'))
    builders = (('translate', lambda code: _rename_entry(code) + TRANSLATE_WRAPPER),
                ('scale', lambda code: _rename_entry(code) + SCALE_WRAPPER),
                ('relabel', _relabel_source),
                ('real_change', lambda code: _rename_entry(code) + REAL_CHANGE_WRAPPER))
    for task_id in EQUIVALENCE_TASKS:
        parent_code = _standard_code(task_id)
        pkg = Path(tmp_root) / ('pkg-' + task_id)
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / 'parent.py').write_text(parent_code, encoding='utf-8')
        for name, build in builders:
            kind = 'real_change' if name == 'real_change' else 'equivalent'
            mechanism = REAL_CHANGE_MECHANISM if kind == 'real_change' \
                else EQUIVALENT_MECHANISM
            cases.append(_run_revision_case(
                '{0}-{1}'.format(task_id, name), kind, task_id, build(parent_code),
                parent_code, mechanism, pkg))
    # 复审反例同构重建：父代取 T05 标准答案（可评分），子代只把分数统一 +100。
    review_pkg = Path(tmp_root) / 'pkg-review'
    review_pkg.mkdir(parents=True, exist_ok=True)
    review_parent = _standard_code('T05')
    (review_pkg / 'parent.py').write_text(review_parent, encoding='utf-8')
    cases.append(_run_revision_case(
        'review-affine-shift-T06', 'review_counterexample', 'T06',
        _rename_entry(review_parent) + TRANSLATE_WRAPPER, review_parent,
        EQUIVALENT_MECHANISM, review_pkg))
    # 冻结材料：父代 = 任务包原样的 materials/T06-parent-triax-v1.py。
    frozen_parent = adm.gen.normalized_code(
        (adm.PACKAGE_DIR / REVISION_PARENT_REF).read_text(encoding='utf-8'))
    cases.append(_run_revision_case(
        'frozen-material-T06', 'material_incompatible', 'T06',
        _rename_entry(_standard_code('T06')) + TRANSLATE_WRAPPER, frozen_parent,
        EQUIVALENT_MECHANISM, adm.PACKAGE_DIR, parent_ref=REVISION_PARENT_REF))
    failed = [row['probe'] for row in cases if not row['ok']]
    return {
        'schema': 'sitin-model-admission-equivalence-probe/1',
        'purpose': '复审 §5 M3：等行为负例（平移/正比例缩放/只改说明）不得算作修订行为'
                   '差异；真实首选动作改变仍须通过；父代全部弃权先判材料不兼容。',
        'budget_note': '0 真实 LLM、0 真实桌赛；仅进程内合成视图与临时包。',
        'signature': '首选动作（最高分，同分按 action_key 升序）+ 未知掩码，'
                     '与 P8 档案行为签名同口径',
        'ok': not failed,
        'failed_probes': failed,
        'cases': cases,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(PACKAGE_DIR / "reports" / "r3-probe-report.json"))
    parser.add_argument("--texts", action="store_true", help="打印探针原文（留证）")
    parser.add_argument("--equivalence-out", default=None,
                        help="另跑修订行为等价性探针（复审 §5 M3）并写 JSON")
    args = parser.parse_args(argv)

    baseline_rows = _run(BASELINE_PROBES)
    r3_rows = _run(R3_PROBES)
    rows = baseline_rows + r3_rows
    all_caught = all(row["caught"] for row in rows)
    report = {
        "schema": "sitin-model-admission-probe-report/1",
        "purpose": "校验器语境豁免的抗规避探针：人为违规主张必须仍被判挂（0 真实 LLM）。",
        "generated_by": "tools/sitin_model_admission_probes.py",
        "reconstruction": {
            "baseline_report": "reports/r1-v2-probe-report.json",
            "note": "r1-v2 基线只留了探针产物、未留生成脚本；本脚本按该报告的 12 条探针名目"
                    "逐条重建（同一任务、同一规避手法、同一判挂理由），并追加 r3 轮新增语义的"
                    "5 条边界探针。重建条目在 baseline 字段记录基线报告的判挂要点，逐条比对结果"
                    "见 baseline_match。",
            "baseline_count": len(baseline_rows),
            "r3_count": len(r3_rows),
        },
        "all_caught": all_caught,
        "baseline_match": [
            {"probe": row["probe"], "baseline": row["baseline"],
             "violations": row["violations"],
             "missing_group_count": sum(1 for p in row["problems"] if "缺少关键词组" in p)}
            for row in baseline_rows
        ],
        "probes": rows,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    print(json.dumps({"all_caught": all_caught, "probes": len(rows),
                      "caught": sum(1 for row in rows if row["caught"]),
                      "report": str(out)}, ensure_ascii=False))
    for row in rows:
        if not row["caught"]:
            print("NOT CAUGHT:", json.dumps(row, ensure_ascii=False))
    if args.texts:
        for probe in BASELINE_PROBES + R3_PROBES:
            print("=====", probe["probe"])
            print(probe["text"])
    equivalence_ok = True
    if args.equivalence_out:
        equivalence = run_equivalence_probe()
        equivalence_ok = bool(equivalence["ok"])
        Path(args.equivalence_out).write_text(
            json.dumps(equivalence, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"equivalence_ok": equivalence_ok,
                          "cases": len(equivalence["cases"]),
                          "failed_probes": equivalence["failed_probes"],
                          "report": args.equivalence_out}, ensure_ascii=False))
        for row in equivalence["cases"]:
            if not row["ok"]:
                print("EQUIVALENCE FAILED:",
                      json.dumps(row, ensure_ascii=False))
    return 0 if (all_caught and equivalence_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
