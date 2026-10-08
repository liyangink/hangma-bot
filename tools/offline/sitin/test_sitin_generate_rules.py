"""包 B/C1 同源渲染的回归测试：合同 restricted_subset.rules ↔ 题面渲染 ↔ 预检诊断。

**这份测试要能失败**：它断言的三件事都可能在真实改动下变红——
  ① 执行器的 60 条静态规则必须在合同里逐条有条目；
  ② 每条规则必须按 applies_to 出现在对应题面（生成题与修复题）的渲染里；
  ③ 执行器的每一条拒绝消息必须唯一映射回一个 AV-SUB 编号；
  ④ 题面里的约束句必须**逐字**来自合同（改合同一句 ⇒ 渲染即变，不许第二套文案）。

规则定义的**唯一来源**是 contracts/action-value-v1.json 的 restricted_subset.rules；
探针语料来自 evidence/v4-impl/r9-admission/p25-contract-rules/RULES.json（P25 审计产物，
逐条正/反例 + 消息模板）。语料缺失时相关用例显式 skip，不静默放宽。

运行：

    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_generate_rules.py -q
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

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("sitin_generate", _project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py"))
gen = importlib.util.module_from_spec(_spec)
sys.modules["sitin_generate"] = gen
assert _spec.loader is not None
_spec.loader.exec_module(gen)

REPO = _PROJECT_ROOT
PACKAGE = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package'))
RULES_AUDIT = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-contract-rules/RULES.json'))

#: 合同字节 sha 冻结值（gate-2 计划文件、全部评价/面板身份记录、金例身份键
#: av_contract_sha256 都引用它）。规则目录**不进**这个文件——本常量是防回归闸门：
#: 谁再把目录塞回合同，这条断言就红。
CONTRACT_SHA256_FROZEN = (
    "69ac62bdac371b410af2448d6845003f7d193720c7785c8d3d2dd00d996de5f8")

DOC = '"""probe candidate."""\n'
DEFAULT_SCORE = '    return {"status": "ABSTAIN", "entries": [], "reason": None}\n'


# ------------------------------------------------------------------ 夹具

@pytest.fixture(scope="module")
def contract():
    return gen.load_action_value_contract()[0]


@pytest.fixture(scope="module")
def rules():
    """规则清单来自**兄弟文件**（不进合同身份），不是合同里的键。"""

    return gen.load_action_value_subset_rules()[0]


@pytest.fixture(scope="module")
def audit():
    if not RULES_AUDIT.is_file():
        pytest.skip("P25 规则审计产物缺失：{0}".format(RULES_AUDIT))
    return json.loads(RULES_AUDIT.read_text(encoding="utf-8"))


def build_source(spec: dict) -> str:
    """与 p25-contract-rules/probe.py 同一套探针源码构造（语料同源）。"""

    if "r" in spec:
        return spec["r"]
    out = [DOC, spec.get("m", "")]
    out.extend(spec.get("f", []))
    score = spec.get("s", DEFAULT_SCORE)
    if score is not None:
        out.append("def score_actions(view):\n" + score)
    return "".join(out)


def negative_corpus(audit):
    """(规则编号, 执行器期望消息片段, 反例源码) 三元组清单（合成探针除外）。"""

    corpus = []
    for rule in audit["rules"]:
        neg = rule.get("neg")
        if not neg:
            continue
        corpus.append((rule["id"], rule["expect"], build_source(neg)))
    return corpus


def executor_message(source):
    """按执行器**真实装载路径**取拒绝消息，返回 (消息, 来源)。

    来源 static_check = 生成端预检能拦的规则；来源 load = 只有 ActionValueExecutor
    构造期才拒绝的规则（AV-SUB-057/058：源码类型与字节上限）。两者都是
    StaticCheckError，但预检只跑 static_check，覆盖不到 load 那一层——这属
    预检覆盖面事实，测试如实分开记，不假装预检拦得住。
    """

    from hangma_bot.policy.action_value_executor import (
        ActionValueExecutor, StaticCheckError, static_check)
    try:
        static_check(source)
    except StaticCheckError as exc:
        return str(exc), "static_check"
    if not isinstance(source, str):
        return None, "unreachable"
    try:
        ActionValueExecutor(source)
    except StaticCheckError as exc:
        return str(exc), "load"
    return None, "accepted"


def generation_text():
    payload = gen.render_action_value_task_contract(
        objective_summary="测试目标", panel_boundary="测试面板", prompt_role="I1")
    return gen.build_action_value_prompt(gen.OPERATOR_I1, payload).text


REPAIR_MATERIALS = "【材料一：候选源码（夹具）】\n\n【任务】修复该缺陷。"


def repair_text():
    return gen.build_action_value_repair_prompt(REPAIR_MATERIALS).text


# ------------------------------------------------- ① 合同逐条有条目

def test_sibling_file_declares_all_sixty_rules(rules, audit):
    declared = json.loads(
        (_project_file(_PROJECT_ROOT, REPO / gen.AV_SUBSET_RULES_RELPATH)).read_text(encoding="utf-8"))["rules"]
    assert len(declared) == 60, len(declared)
    assert len(rules) == 60
    ids = [rule["id"] for rule in rules]
    assert ids == ["AV-SUB-{0:03d}".format(n) for n in range(1, 61)], ids
    assert len(set(ids)) == 60
    # 与 P25 审计的 60 条规则逐条对齐（编号即审计编号，不得漂移）。
    assert ids == [rule["id"] for rule in audit["rules"]]


def test_contract_bytes_are_frozen_and_carry_no_rules_directory(contract):
    """规则目录**不进合同**：合同字节 sha 必须还是冻结值，且 restricted_subset 无 rules 键。

    为什么这条必须存在：合同 sha 是冻结评价身份的一部分（gate-2 计划文件与全部
    评价/面板身份记录都引用它）；把候选可见的规则目录塞回合同会让已签收的关口二链
    身份无谓失效。改评分语义时才允许动这个文件。
    """

    contract_path = _project_file(_PROJECT_ROOT, REPO / gen.AV_CONTRACT_RELPATH)
    assert gen.sha256_file(contract_path) == CONTRACT_SHA256_FROZEN
    assert "rules" not in contract["restricted_subset"]
    assert "rules_note" not in contract["restricted_subset"]
    # 规则目录在兄弟文件里，且路径常量指向它。
    assert (_project_file(_PROJECT_ROOT, REPO / gen.AV_SUBSET_RULES_RELPATH)).is_file()
    assert gen.AV_SUBSET_RULES_RELPATH != gen.AV_CONTRACT_RELPATH


def test_payload_records_the_sibling_rules_identity(rules):
    """规则目录的 sha 进 payload 身份（提示词血缘），但不进合同 sha256。"""

    payload = gen.render_action_value_task_contract(
        objective_summary="x", panel_boundary="y", prompt_role="z")
    source = payload["subset_rules_source"]
    assert source["path"] == str(gen.AV_SUBSET_RULES_RELPATH)
    assert source["sha256"] == gen.load_action_value_subset_rules()[1]
    assert payload["contract_sha256"] == CONTRACT_SHA256_FROZEN


def test_rule_entries_are_well_formed(rules):
    for rule in rules:
        assert rule["statement"].strip(), rule["id"]
        assert rule["applies_to"], rule["id"]
        assert set(rule["applies_to"]) <= set(gen.AV_SUBSET_RULE_TARGETS), rule["id"]
        assert isinstance(rule["reachable"], bool), rule["id"]
        re.compile(rule["message_pattern"])


def test_original_forbidden_ten_items_are_untouched(contract, rules):
    forbidden = contract["restricted_subset"]["forbidden"]
    assert len(forbidden) == 10, forbidden
    assert forbidden[0] == "while 循环"
    assert "生成器与 yield" in forbidden
    # rules 是 forbidden 的下位展开：实现某条禁项的规则必须点名是哪一条。
    # （forbidden_item 只在**兄弟文件原文**里；normalize_subset_rules 只搬运渲染/匹配
    #   需要的五个字段，因此这里读原文而不是读规范化结果。）
    raw_rules = json.loads(
        (_project_file(_PROJECT_ROOT, REPO / gen.AV_SUBSET_RULES_RELPATH)).read_text(encoding="utf-8"))["rules"]
    items = {entry["forbidden_item"] for entry in raw_rules}
    items.discard(None)
    assert items, "至少要有规则显式标出对应哪条禁项"
    assert items <= set(forbidden)


# ------------------------------------------------- ② 每条按 applies_to 出现在题面

@pytest.mark.parametrize("target", sorted(gen.AV_SUBSET_RULE_TARGETS))
def test_every_rule_is_rendered_for_its_target(rules, target):
    text = generation_text() if target == "generation" else repair_text()
    for rule in rules:
        if target not in rule["applies_to"]:
            continue
        assert rule["id"] in text, (target, rule["id"])
        assert rule["statement"] in text, (target, rule["id"])


def test_generation_and_repair_render_the_same_source(rules):
    """两类题面渲染的是同一份定义：规则集合逐条相同，只有题类过滤不同。"""

    gen_text, rep_text = generation_text(), repair_text()
    for rule in rules:
        assert rule["id"] in gen_text, rule["id"]
        assert rule["id"] in rep_text, rule["id"]
    assert "AV-SUB-007" in gen_text and "AV-SUB-007" in rep_text


def test_all_sixty_rules_appear_in_both_task_kinds(rules):
    """执行器对生成题与修复题跑同一份静态检查 ⇒ 60 条两类都适用、都要出现。"""

    for rule in rules:
        assert set(rule["applies_to"]) == {"generation", "repair"}, rule["id"]


# ------------------------------------------------- ③ 拒绝消息唯一映射回编号

def test_every_executor_rejection_maps_to_exactly_one_rule(rules, audit):
    """执行器每条拒绝消息（按真实装载路径取）唯一映射回一个 AV-SUB 编号。"""

    corpus = negative_corpus(audit)
    assert len(corpus) >= 50, len(corpus)
    seen = set()
    for rule_id, expect, source in corpus:
        message, origin = executor_message(source)
        assert message is not None, (rule_id, origin)
        assert expect in message, (rule_id, message)
        assert gen.match_subset_rule_ids(message) == [rule_id], (
            rule_id, origin, message)
        seen.add(origin)
    assert seen == {"static_check", "load"}, seen


def test_precheck_binds_rule_ids_for_every_static_check_rejection(rules, audit):
    """生成端/修复端预检：static_check 拦下的每条拒绝都带上唯一编号。"""

    checked = 0
    for rule_id, expect, source in negative_corpus(audit):
        _message, origin = executor_message(source)
        if origin != "static_check":
            continue          # 装载期规则（057/058）不经过预检，见下一个用例
        precheck = gen.precheck_action_value_candidate(source)
        assert precheck["ok"] is False, rule_id
        assert precheck["rule_ids"] == [rule_id], (rule_id, precheck["rule_ids"])
        assert precheck["unmapped"] is False, rule_id
        assert expect in precheck["problems"][0], rule_id
        assert precheck["rule_hits"][0]["statement"] in {
            rule["statement"] for rule in rules if rule["id"] == rule_id}
        checked += 1
    # 语料 50 条 = 49 条 static_check 可达 + 1 条装载期（AV-SUB-058）。
    assert checked == 49, checked


def test_precheck_does_not_cover_load_only_rules(rules, audit):
    """预检覆盖面事实：AV-SUB-057/058 只在装载期拒绝，预检放行（**不假装拦得住**）。"""

    load_only = []
    for rule_id, _expect, source in negative_corpus(audit):
        message, origin = executor_message(source)
        if origin == "load":
            load_only.append(rule_id)
            assert gen.precheck_action_value_candidate(source)["ok"] is True
    assert load_only == ["AV-SUB-058"], load_only


def test_mapping_is_unique_across_all_patterns(rules):
    """任何两条规则的正则不得同时命中同一条真实消息（防编号串味）。"""

    corpus = [rule["message_pattern"] for rule in rules]
    assert len(set(corpus)) == len(corpus)


def test_precheck_keeps_the_executor_message_verbatim(contract):
    """诊断绑编号不得改写判据：problems[0] 必须是执行器原话。"""

    from hangma_bot.policy.action_value_executor import StaticCheckError, static_check
    source = build_source({"s": "    return str(1)\n"})
    with pytest.raises(StaticCheckError) as excinfo:
        static_check(source)
    precheck = gen.precheck_action_value_candidate(source)
    assert precheck["problems"] == [str(excinfo.value)]
    assert precheck["rule_ids"] == ["AV-SUB-009"]


def test_precheck_reports_unmapped_without_guessing():
    """未知消息（非执行器模板）不得被硬套到某条规则上。"""

    hits = gen.subset_rule_hits("这是一条不存在的执行器消息")
    assert hits == []


def test_precheck_survives_executor_keyerror_fail_closed():
    """AV-SUB-A01：_check_recursion 的 KeyError 不得穿透预检，且照旧判失败。"""

    source = build_source({
        "f": ["def h(view):\n    return 1\n\n"],
        "s": "    def g():\n        return h()\n    return g()\n"})
    precheck = gen.precheck_action_value_candidate(source)
    assert precheck["ok"] is False
    assert precheck["executor_defect"] == "KeyError"
    assert precheck["unmapped"] is True


# ------------------------------------------------- ④ 同源：改合同 ⇒ 渲染变化

def _mutated_sibling(tmp_path, old: str, new: str) -> Path:
    """把兄弟规则目录里的一句 statement 改成 new（同源测试用；不碰合同）。"""

    raw = (_project_file(_PROJECT_ROOT, REPO / gen.AV_SUBSET_RULES_RELPATH)).read_text(encoding="utf-8")
    assert old in raw
    path = tmp_path / "action-value-restricted-rules-v1.json"
    path.write_text(raw.replace(old, new), encoding="utf-8")
    return path


def test_statement_change_changes_the_rendered_prompt(monkeypatch, tmp_path, rules):
    """同源核心：改规则目录一条 statement ⇒ 两类题面的渲染文本与提示词哈希都变。

    走**完整渲染路径**（load_action_value_subset_rules → payload → 生成题/修复题文本），
    不是只测一个渲染函数：证明不存在"规则目录之外的第二套文案"。
    """

    rule = next(item for item in rules if item["id"] == "AV-SUB-007")
    marker = "改后的一句话（同源测试）"
    mutated_path = _mutated_sibling(tmp_path, rule["statement"],
                                    rule["statement"] + marker)
    mutated_payload = json.loads(mutated_path.read_text(encoding="utf-8"))
    digest = gen.sha256_text(mutated_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        gen, "load_action_value_subset_rules",
        lambda path=None: (gen.normalize_subset_rules(mutated_payload["rules"]), digest))

    payload = gen.render_action_value_task_contract(
        objective_summary="x", panel_boundary="y", prompt_role="z")
    generation = gen.build_action_value_prompt(gen.OPERATOR_I1, payload).text
    repair = gen.build_action_value_repair_prompt("【材料一】夹具").text
    for text in (generation, repair):
        assert rule["statement"] + marker in text
        # 其它规则的 statement 仍在（不是整块替换）。
        other = next(item for item in rules if item["id"] == "AV-SUB-033")
        assert other["statement"] in text

    monkeypatch.undo()
    baseline = gen.build_action_value_prompt(
        gen.OPERATOR_I1,
        gen.render_action_value_task_contract(
            objective_summary="x", panel_boundary="y", prompt_role="z")).text
    assert marker not in baseline
    assert gen.sha256_text(baseline) != gen.sha256_text(generation)


@pytest.mark.parametrize("target", ["generation", "repair"])
def test_rendered_statements_are_verbatim_from_sibling(rules, target):
    """渲染出的每一条约束句必须与规则目录 statement 逐字相同（无第二套文案）。

    生成题与修复题各测一遍：两类题面渲染的是**同一份**兄弟文件。
    """

    text = generation_text() if target == "generation" else repair_text()
    lines = [line for line in text.splitlines() if line.startswith("  - AV-SUB-")]
    rendered = {}
    for line in lines:
        rule_id, _, statement = line[4:].partition("：")
        rendered[rule_id] = statement
    assert rendered == {rule["id"]: rule["statement"] for rule in rules}


def test_missing_rules_block_is_fail_closed():
    """合同缺 rules 时渲染器必须显式报缺（不得静默当成「没有约束」）。"""

    lines = gen.render_restricted_subset_rule_lines([], "generation")
    joined = "\n".join(lines)
    assert "装配缺陷" in joined and "fail-closed" in joined
    with pytest.raises(ValueError):
        gen.normalize_subset_rules([])


# ------------------------------------------------- 重签发前后的红→绿对照

#: 重签发之前的已签发题面所在提交（那时题面里没有规则块）。
#: 用固定提交而不是 HEAD：本对照要能长期复跑，不能被后续提交漂移掉。
PRE_RESIGN_COMMIT = "205529e0"


def prompt_from_git(commit: str, task_id: str):
    """从历史提交里取该题的重签发前题面；取不到返回 None（用例显式 skip）。"""

    import subprocess

    rel = ("review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/"
           "r9-admission/package/prompts/{0}.txt".format(task_id))
    proc = subprocess.run(["git", "show", "{0}:{1}".format(commit, rel)],
                          cwd=str(REPO), capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


def test_pre_resign_t05_lacks_the_rules_block():
    """红对照：**重签发之前**的 T05 题面里没有任何 AV-SUB 编号。"""

    text = prompt_from_git(PRE_RESIGN_COMMIT, "T05")
    if text is None:
        pytest.skip("取不到重签发前的 T05 题面")
    assert "AV-SUB-" not in text


def test_pre_resign_t18_repair_lacks_the_rules_block():
    """红对照：**重签发之前**的 T18（修复题）没有规则块。"""

    text = prompt_from_git(PRE_RESIGN_COMMIT, "T18")
    if text is None:
        pytest.skip("取不到重签发前的 T18 题面")
    assert "AV-SUB-" not in text


def test_resigned_t05_contains_the_rules_block():
    """绿：**重签发之后**的 T05 题面带 60 条编号，且与唯一来源逐条同源。"""

    path = _project_file(_PROJECT_ROOT, PACKAGE / "prompts" / "T05.txt")
    if not path.is_file():
        pytest.skip("已签发题包缺失")
    text = path.read_text(encoding="utf-8")
    ids = set(re.findall(r"AV-SUB-\d{3}", text))
    assert len(ids) == 60, sorted(ids)[:5]
    assert "AV-SUB-007" in ids and "AV-SUB-033" in ids
    assert ids <= set(re.findall(r"AV-SUB-\d{3}", generation_text()))


def test_resigned_t18_repair_contains_the_rules_block():
    """绿：**重签发之后**的 T18（修复题）也带规则块，且材料逐字仍在开头。"""

    path = _project_file(_PROJECT_ROOT, PACKAGE / "prompts" / "T18.txt")
    if not path.is_file():
        pytest.skip("已签发题包缺失")
    signed = path.read_text(encoding="utf-8")
    ids = set(re.findall(r"AV-SUB-\d{3}", signed))
    assert len(ids) == 60, sorted(ids)[:5]
    for rule_id in ("AV-SUB-007", "AV-SUB-009", "AV-SUB-033", "AV-SUB-011"):
        assert rule_id in ids
    before = prompt_from_git(PRE_RESIGN_COMMIT, "T18")
    if before is not None:
        # 材料正文（重签发前题面去掉尾部条款）必须逐字仍是新题面的前缀。
        stripped = before.strip().split("\n【输出格式")[0].strip()
        # 卡面瘦身后【本次目标与修改点】**置顶**，材料块不再位于题面开头 ⇒
        # 断言从"以材料开头"改为"材料块逐字仍在新题面里"（设计变更，不是放宽）。
        assert stripped[:80] in signed
        assert len(signed) > len(before)
        assert "AV-SUB-" not in before
    repaired = gen.build_action_value_repair_prompt(before or signed).text
    assert "AV-SUB-007" in repaired and "AV-SUB-033" in repaired
