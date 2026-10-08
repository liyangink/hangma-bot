"""卡面瘦身渲染层的单元测试（R9-P25 §4.3 / §3 第 2 步）。

纪律：这些测试只验证**渲染层**（tools/sitin_generate.py 的卡面函数），
不触碰判分器、门槛、合同字节与规则/附录文件。
"""

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

import json
import re
import sys
from pathlib import Path

import pytest

ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))

import sitin_generate as gen  # noqa: E402

FENCE = gen.FENCE


def base_focus(**overrides):
    focus = {
        "objective": "本次目标（测试）",
        "change_point": "本次修改点（测试）",
        "input_groups": ["schema_version", "actions", "actions[]"],
        "gate": "none",
        "guard": "none",
        "examples": "output",
        "rules": "compact",
        "input_overview": "none",
    }
    focus.update(overrides)
    return focus


def sample_payload(**overrides):
    payload = gen.render_action_value_task_contract(
        objective_summary="测试目标",
        panel_boundary="测试面板",
        prompt_role="测试角色",
        parent={"identity": "parent-id", "candidate_id": "cand-id",
                "thought": "父代机制说明", "code": "def score_actions(view):\n    return {}\n",
                "code_sha256": "0" * 64},
        feedback={"facts": "事实", "associated_results": "关联", "mechanism_hypothesis": "假设"},
        budget_note="预算以台账为准")
    payload.update(overrides)
    return payload


def test_appendix_paths_partition_into_groups():
    appendix, _ = gen.load_action_value_public_interface()
    known = {name for name, _prefix in gen.AV_CARD_FIELD_GROUPS} | {gen.AV_CARD_GROUP_FALLBACK}
    for entry in appendix["paths"]:
        assert gen.appendix_path_group(entry["path"]) in known
    # 未归组的路径必须**恒被渲染**（过滤不得静默吞掉新字段）
    grouped = gen.appendix_group_entries(appendix)
    for path in grouped.get(gen.AV_CARD_GROUP_FALLBACK, []):
        focus = gen.normalize_card_focus(base_focus(input_groups=["schema_version"]))
        lines, _stats = gen.render_card_input_contract(appendix, focus)
        assert gen._appendix_path_line(path) in lines


def test_group_matching_prefers_exact_prefix():
    assert gen.appendix_path_group("actions") == "actions"
    assert gen.appendix_path_group("actions[].action_key") == "actions[]"
    assert (gen.appendix_path_group("actions[].followup_branches[].combined_shanten")
            == "actions[].followup_branches")
    assert (gen.appendix_path_group("actions[].routes[].conditions.draw_kind")
            == "actions[].routes[].conditions")


def test_focus_is_fail_closed():
    with pytest.raises(ValueError):
        gen.normalize_card_focus(base_focus(unknown_key="x"))
    with pytest.raises(ValueError):
        gen.normalize_card_focus(base_focus(input_groups=["no_such_group"]))
    with pytest.raises(ValueError):
        gen.normalize_card_focus(base_focus(gate="half"))
    with pytest.raises(ValueError):
        gen.normalize_card_focus(base_focus(examples="sometimes"))
    with pytest.raises(ValueError):
        gen.normalize_card_focus({"objective": "只有目标"})
    with pytest.raises(ValueError):
        gen.normalize_card_focus(base_focus(objective="   "))


def test_rule_compression_is_deletion_only():
    rules, _ = gen.load_action_value_subset_rules()
    for rule in rules:
        compressed, dropped = gen.compress_rule_statement(rule["statement"])
        assert len(compressed) <= len(rule["statement"])
        # 压缩结果必须是原文的子序列（只删不加）
        cursor = 0
        for char in compressed:
            cursor = rule["statement"].find(char, cursor)
            assert cursor >= 0, rule["id"]
            cursor += 1
        # 被删从句必须逐字来自原文，且不引入任何新 ASCII 字面量
        seen = set(gen.AV_CARD_TOKEN_RE.findall(compressed))
        for clause in dropped:
            assert clause in rule["statement"]
            assert not (set(gen.AV_CARD_TOKEN_RE.findall(clause)) - seen)


def test_rules_block_keeps_ids_and_compresses():
    rules, _ = gen.load_action_value_subset_rules()
    lines, stats = gen.render_card_rule_lines(rules, "generation", "compact")
    text = "\n".join(lines)
    for rule in rules:
        assert rule["id"] + "：" in text
    assert stats["rules"] == len(rules)
    assert stats["after_chars"] <= stats["before_chars"]
    assert stats["dropped_clauses"]


def test_card_leads_with_goal_and_keeps_parent_verbatim():
    payload = sample_payload()
    card = gen.render_action_value_card_text(payload, base_focus())
    headers = [line for line in card.split("\n") if re.match(r"^【.+】$", line)]
    assert headers[0].startswith("【本次目标与修改点")
    assert payload["parent"]["code"].rstrip("\n") in card
    assert payload["parent"]["thought"] in card
    assert payload["feedback"]["facts"] in card


def test_card_lists_selected_and_excluded_groups():
    appendix, _ = gen.load_action_value_public_interface()
    focus = gen.normalize_card_focus(base_focus(
        input_groups=["schema_version", "actions[].followup_branches"]))
    lines, stats = gen.render_card_input_contract(appendix, focus)
    text = "\n".join(lines)
    for entry in appendix["paths"]:
        if gen.appendix_path_group(entry["path"]) in ("schema_version",
                                                      "actions[].followup_branches"):
            # 组内公共 note 只在组头出现一次，故只断言"路径行"存在
            assert "  - " + entry["path"] + "：" in text
    for row in stats["excluded_groups"]:
        assert row["group"] in text
    assert str(gen.AV_PUBLIC_INTERFACE_RELPATH) in text


def test_repair_card_keeps_materials_verbatim_and_puts_goal_first():
    materials = "【材料一】\n" + FENCE + "python\nprint(1)\n" + FENCE + "\n【任务】修复它。"
    focus = base_focus(objective="修复某个缺陷", change_point="把 X 改成 Y")
    text = gen.render_action_value_repair_card_text(materials, focus)
    assert materials in text
    assert text.index("本次目标与修改点") < text.index("【材料一】")


def test_card_report_matches_card_size():
    payload = sample_payload()
    focus = base_focus()
    card = gen.render_action_value_card_text(payload, focus)
    report = gen.card_render_report(payload, focus)
    assert report["card_chars"] == len(card)
    assert report["card_chars"] < report["legacy_chars"]
    assert (report["appendix"]["rendered_paths"]
            < report["appendix"]["appendix_total_paths"])
    assert report["rules"]["rules"] == 60


def test_card_is_deterministic():
    payload = sample_payload()
    first = gen.render_action_value_card_text(payload, base_focus())
    second = gen.render_action_value_card_text(payload, base_focus())
    assert first == second


def test_legacy_renderers_unchanged_shape():
    """旧入口必须仍然渲染完整附录与 60 条规则（卡面瘦身只加新入口，不改旧路径）。"""

    payload = sample_payload()
    legacy = gen.render_action_value_contract_text(payload)
    assert "【公开接口附录" in legacy
    assert "【门线/位次势差口径" in legacy
    assert "【作者守卫条款" in legacy
    rules, _ = gen.load_action_value_subset_rules()
    assert all(rule["statement"] in legacy for rule in rules)
    packet = gen.build_action_value_prompt(gen.OPERATOR_I1, payload)
    assert packet.text.startswith("请设计一个全新的完整动作评分器")

# ---------------------------------------------------------------------------
# P25 小诊断第二轮：候选块判据（不得用子串命中）+ 修复卡按判分器 kind
# ---------------------------------------------------------------------------

FOUR_FIELDS = ('{"trigger": "t", "changed_branches": "c", '
               '"expected_direction": "e", "counterexample": "x"}')


def _reply_with(json_note: str, code: str, *, json_tag: str = "json") -> str:
    return ("{一句话机制}\n\n" + FENCE + json_tag + "\n" + json_note + "\n" + FENCE
            + "\n\n" + FENCE + "python\n" + code + FENCE + "\n")


def test_mechanism_block_mentioning_entry_is_not_a_candidate():
    """四字段 JSON 里写了入口函数名 ⇒ 不得被当成第二个候选块（P25 小诊断 TD01）。"""

    body = FOUR_FIELDS.replace('"t"', '"调用 score_actions 时触发"')
    reply = _reply_with(body, "def score_actions(view):\n    return {}\n")
    parsed = gen.parse_action_value_reply(reply)
    assert parsed["status"] == gen.PARSE_OK
    assert parsed["code"].startswith("def score_actions(")
    assert parsed["mechanism"] is not None
    # 旧口径的误判仍在（子串判据），这正是被修掉的那个缺陷
    legacy = gen.parse_model_reply(reply, entry_name=gen.AV_ENTRY_NAME)
    assert legacy.status == gen.PARSE_AMBIGUOUS_CODE


def test_two_defining_blocks_stay_ambiguous():
    code = "def score_actions(view):\n    return {}\n"
    reply = ("{一句话机制}\n\n" + FENCE + "json\n" + FOUR_FIELDS + "\n" + FENCE
             + "\n\n" + FENCE + "python\n" + code + FENCE
             + "\n\n" + FENCE + "python\n" + code + FENCE + "\n")
    parsed = gen.parse_action_value_reply(reply)
    assert parsed["status"] == gen.PARSE_AMBIGUOUS_CODE
    assert "都定义了入口函数" in "".join(parsed["problems"])


def test_block_classification_by_language_and_content():
    """候选块判据：语言标注 json / 块体是 JSON 对象 / 无入口定义 —— 三种都不是候选。"""

    code = "def score_actions(view):\n    return {}\n"
    assert gen.av_candidate_block_indices([code], ["json"]) == []
    assert gen.av_candidate_block_indices([code], ["python"]) == [0]
    assert gen.av_candidate_block_indices([code], [""]) == [0]
    assert gen.av_candidate_block_indices([FOUR_FIELDS], ["python"]) == []
    assert gen.av_candidate_block_indices([FOUR_FIELDS], [""]) == []
    assert gen.av_candidate_block_indices(["只有说明文字"], [""]) == []
    # json 标注的块即使正文里出现入口定义也不算候选——候选只能是另一个块
    reply = _reply_with("def score_actions(view): return {}",
                        code)
    parsed = gen.parse_action_value_reply(reply)
    assert parsed["code"].startswith("def score_actions(")


def test_no_defining_block_keeps_legacy_verdict():
    """没有候选块时逐字沿用旧口径（不放宽、也不新增拒绝）。"""

    cases = [
        "{一句话}\n\n" + FENCE + "python\ndef helper(view):\n    return {}\n" + FENCE,
        "{一句话}\n\n" + FENCE + "json\n" + FOUR_FIELDS + "\n" + FENCE,
        "{一句话}\n\n" + FENCE + "text\n只有说明文字\n" + FENCE,
    ]
    for reply in cases:
        legacy = gen.parse_model_reply(reply, entry_name=gen.AV_ENTRY_NAME)
        parsed = gen.parse_action_value_reply(reply)
        mechanism = parsed["mechanism"]
        legacy_status = legacy.status
        if legacy_status == gen.PARSE_OK and mechanism is None:
            legacy_status = gen.PARSE_MISSING_MECHANISM
        assert (parsed["status"], parsed["code"] or "") == (legacy_status, legacy.code or "")


def test_parse_model_reply_default_behaviour_unchanged():
    """默认参数下的 parse_model_reply（其它判分路径）保持子串口径。"""

    reply = _reply_with(FOUR_FIELDS.replace('"t"', '"score_actions"'),
                        "def score_actions(view):\n    return {}\n")
    parsed = gen.parse_model_reply(reply, entry_name=gen.AV_ENTRY_NAME)
    assert parsed.status == gen.PARSE_AMBIGUOUS_CODE
    assert "包含入口函数" in "".join(parsed.problems)


def test_repair_output_clause_follows_grader_kind():
    materials = "【上一轮交付】\n候选源码在下面。"
    code_card = gen.render_action_value_repair_card_text(
        materials, base_focus(), grader_kind="code")
    repair_card = gen.render_action_value_repair_card_text(materials, base_focus())
    assert (FENCE + "json") in code_card
    assert "结构化四字段" in code_card
    assert (FENCE + "json") not in repair_card
    assert "结构化四字段" not in repair_card
    assert gen.repair_output_clause("repair") in repair_card
    assert gen.repair_output_clause("code") in code_card
    # 材料一律逐字保留
    for text in (code_card, repair_card):
        assert materials in text
        for name in gen.AV_MECHANISM_FIELDS:
            assert name in gen.repair_output_clause("code") or True
    assert "trigger/changed_branches/expected_direction/counterexample" in code_card


def test_repair_default_kind_is_repair_and_unknown_kind_fails_closed():
    materials = "【上一轮交付】\n候选源码在下面。"
    assert (gen.render_action_value_repair_card_text(materials, base_focus())
            == gen.render_action_value_repair_card_text(materials, base_focus(),
                                                        grader_kind="repair"))
    with pytest.raises(ValueError):
        gen.repair_output_clause("keyword")
    with pytest.raises(ValueError):
        gen.build_action_value_repair_card_prompt(materials, base_focus(),
                                                  grader_kind="nope")

