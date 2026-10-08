"""以首个机械合格提案为m1父代，补成熟胡/等增量，首旧式反馈仍保留。"""

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
    """调用前绑定首代真实资格与新首摸负例；不把作者声明当成绩。"""
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert all(pin(Path(p)) == h for p, h in preparation["files"].items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in preparation["source_manifest"].items())
    parent_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-speed-model-output")
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parents = load_vip_parents([parent_path], batch)
    qualification_file = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-speed-model-output-qualification/CLOSURE.json")
    gate = json.loads(qualification_file.read_text())
    supplement_file = _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-supplement/CLOSURE.json")
    supplement = json.loads(supplement_file.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["identity"] == parents[0]["identity"] and gate["actual_completed_views"] == 115
    assert supplement["complete"] and supplement["source_stable"]
    # 完整旧材料是公开开发摘要；本次算子及正式谱系明确覆盖原i1准备说明。
    feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-FEEDBACK.txt")).read_text()
    changed = [{k: r[k] for k in ("label", "classes", "parent_first", "candidate_first", "parent_normalized_gap", "child_normalized_gap")}
               for r in gate["rows"] if r["meaningful_first_changed"]]
    anchor = next(r for r in gate["rows"] if r["label"] == "anchor:mature-baotou-current-hu")
    addition = {"actual_operator_this_call": "m1", "actual_formal_parent": parents[0]["identity"],
        "strength_baseline_still_current_S02": True,
        "first_author_actual_mechanical": {"views": 115, "scores": 230, "meaningful_changes": gate["meaningful_changed_windows"],
            "changed_rows": changed, "new_official_opening_changes": gate["new_official_opening_changes"], "strength_not_measured": True},
        "mature_hu_anchor_first_author_still_not_fixed": {"first": anchor["candidate_first"], "all_first_author_entries": anchor["entries"]},
        "new_room_first_draw_countercheck": {"windows": 20, "independent_rooms": 2, "all_prototype_changes": supplement["summary"],
            "selection": "固定第25/26批每桌首摸，不按终局结果；没有新确认或未来墙"},
        "source_review": "首代保留S02 huoffer的大部分完成通道，仅将NETCARRY由0.25改0.20；用途由2.5/6/13/26上调3/7/14/28。凸用途不是新机制，S02已有。首代当前成熟两番Hu仍弃4饼，因此不得声称已修延胡。",
        "requested_change": "继承当前正式父代的同速前沿修正，聚焦已可Hu时的真实支付增量与追加需求，去除成熟现有爆头价值再次计入remote/carry的问题。不要只是增大胡权重或把全可胡强制止胡；保留已知便宜升档、仍能听牌的财飘/补杠、真正多白后续机会；未知资格、墙余、庄闲和公开竞争统一折价。允许改整个联合公式，但每项改动说明依据。",
        "contrast": "m1的parent_differences必须精确列当前唯一父代ID；S02旧源码只是比较参考，不是第二正式父代。现示例标签只用于离线说明，源码禁止按牌局ID/期待动作特判。"}
    feedback += "\n本次新闭合反馈与正式算子声明（覆盖旧准备包i1说明）：\n" + json.dumps(addition, ensure_ascii=False, allow_nan=False)
    out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-model-output")
    assert not out.exists()
    packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
    with (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-M1-FEEDBACK.txt")).open("x") as stream:
        stream.write(feedback)
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-START.json"), {"operator": "m1", "parent_paths": [str(parent_path)],
        "formal_parent_identity": parents[0]["identity"], "files": {str(p): pin(p) for p in (Path(__file__),
            _project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"),
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-M1-FEEDBACK.txt"), qualification_file, supplement_file,
            parent_path / "candidate.py", parent_path / "generation.json")},
        "prompt_utf8_bytes_not_precise_tokens": len(packet.text.encode()),
        "actual_previous_calls": 1, "maximum_total_calls": 4, "retry": False,
        "new_original_tables_or_confirmations": 0})
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out,
        operator="m1", backend="api", parent_paths=[parent_path], feedback=feedback,
        config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"), endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"))
    print({k: result.get(k) for k in ("status", "identity_stable", "attempt_id", "operator_actual", "error")}, flush=True)
    if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
