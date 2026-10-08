"""第四槽只修真实追加白板用途；不把条件负例当必须等待的答案。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt, load_vip_parents, run_vip_eoh_generate
from glm_max_transport import make_factory
from common import HERE, ROOT, pin, save


def main():
    """真实第三代m1；采用全部闭合正负反馈，不读取自然桌中途成绩。"""
    prepared = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert all(pin(Path(p)) == h for p, h in prepared["files"].items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in prepared["source_manifest"].items())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-model-output")
    parents = load_vip_parents([package], batch)
    gate_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-model-output-qualification/CLOSURE.json")
    causal_path = _project_file(_PROJECT_ROOT, HERE / "WAIT-REVISION-CAUSAL-CLOSED.json")
    gate, causal = (json.loads(p.read_text()) for p in (gate_path, causal_path))
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["identity"] == parents[0]["identity"] and gate["actual_completed_views"] == 115
    assert causal["complete"] and causal["counts"]["single_hand_dispatched"] == 24
    assert all(pin(Path(p)) == h for p, h in causal["files"].items())
    previous = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-model-output-qualification/CLOSURE.json")).read_text())
    same_first = sum(a["candidate_first"] == b["candidate_first"] for a, b in zip(previous["rows"], gate["rows"]))
    assert same_first == 115
    contrast = []
    for label in ("supplement:004:05", "fresh:005:04", "anchor:mature-baotou-current-hu"):
        row = next(r for r in gate["rows"] if r["label"] == label)
        contrast.append({"label": label, "first": row["candidate_first"],
                         "top_two": sorted(row["entries"], key=lambda e: -e["score"])[:2]})
    addition = {
        "actual_operator_this_call": "m1", "actual_formal_parent": parents[0]["identity"],
        "baseline_still_S02": True, "third_mechanical": {"views": 115, "scores": 230, "same_first_as_actual_parent": same_first},
        "contrast_current_outputs": contrast, "closed_same_sample_feedback": causal["comparisons"],
        "sampler_boundary": causal["sampler_interpretation"],
        "mechanism_review": "第三代pendingacts与incrementmass只是将现有option[8]的价值再折价；成熟单白k1的purpose本来描述已保留的一白用途，而现在Hu已得到该爆头价值。不能因为terminal_draw=1就将现有用途改称新增收益。新增白、再飘、再胡是更远的至少两次本人摸牌与实际弃白转换，不是当前k1前驱的一个终点摸牌。第三代虽允许need=0非零remote，但115窗没有任何对真父的首选变化，原四番负例也仍少20。",
        "request": "保留同速路线前沿，以真实新增用途差重写胡与等：已知下一摸支付仍用同码包络的point-anchor；更远白路用当前自然成形/保白量与追加白后的用途或支付增量的有界代理，追加白未得到前需公开容量、墙余、额外动作与竞争折价。即使natural_need=0也可能有增量，但不能再给当前已经Hu到的爆头重复信用。可将新增白用途差作为新联合公式项；未知未来资格、抓打、他家先胡仍必须明确未知。不得虚构规则结果或确定胡大，不要仅改常量、把全部成熟Hu强制等/胡。",
        "public_contrasts": [
            {"label": "supplement:004:05", "white_held": 1, "white_capacity": 3, "evidence": "exact", "wall": 45,
             "focal": 0, "dealer": 3, "meld_counts_physical_0_1_2_3": [1, 1, 0, 1], "natural_need": 0,
             "outcomes": "四相容样本中三组都是+20，一组S02再白/财飘/再胡+40，三代都立即+20。不是25%平台概率，也不要求此窗必等。"},
            {"label": "anchor:mature-baotou-current-hu", "white_held": 1, "white_capacity": 3, "evidence": "exact", "wall": 52,
             "focal": 2, "dealer": 0, "meld_counts_physical_0_1_2_3": [0, 1, 3, 2], "natural_need": 0,
             "outcomes": "实际S02继续后庄家先胡；只是延胡风险诊断，不是完整EV答案。"},
            {"label": "fresh:005:04", "white_held": 1, "white_capacity": 3, "evidence": "exact", "wall": 64,
             "focal": 0, "dealer": 0, "meld_counts_physical_0_1_2_3": [2, 0, 1, 0], "natural_need": 0,
             "outcomes": "四样本Hu与S02继续都+48。不能宣布止胡收益或等待收益。"}
        ],
        "capacity_boundary": "exact零可证耗尽；conservative为保守下界，零仍可相容，不能按精确零删除。改善码与白码不能重复计库存。本115窗未见白在目标改善码里，但仍应按定义去重。第三代容量死路归零的文案也不成立：TARGETGATEBASE=0.5使质量门有底；应准确写明未知或非零底的作用。",
        "acceptance": "先过原115窗；需解释新机制且有对真实父代的相关首选变化，不以该单例的+40作唯一答案。之后固定自然32来源四换座及独立128来源确认，允许普通损失被大牌净收入覆盖。",
        "fees": "这是初批第四且最后一槽；失败也计槽，禁止自动重试。"
    }
    feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-M1-FEEDBACK.txt")).read_text()
    feedback += "\n第四槽真实闭合反馈与增量定义（覆盖先前要求中不准确的代理）：\n" + json.dumps(addition, ensure_ascii=False, allow_nan=False)
    feedback_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-white-increment-M1-FEEDBACK.txt")
    with feedback_path.open("x") as stream:
        stream.write(feedback)
    out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-white-increment-model-output")
    assert not out.exists()
    packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-white-increment-START.json"), {"operator": "m1", "formal_parent_identity": parents[0]["identity"],
        "files": {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), feedback_path, gate_path, causal_path,
            package / "candidate.py", package / "generation.json")},
        "prompt_utf8_bytes_not_precise_tokens": len(packet.text.encode()), "previous_actual_calls": 3,
        "maximum_total_calls": 4, "retry": False, "new_natural_tables_or_hidden_input": 0})
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out, operator="m1", backend="api",
        parent_paths=[package], feedback=feedback, config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"),
        endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"))
    print({k: result.get(k) for k in ("status", "identity_stable", "attempt_id", "operator_actual", "error")}, flush=True)
    if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
