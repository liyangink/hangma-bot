"""闭合条件负例后修订等待增量；仅使用公开开发事实和分账反馈。"""

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
    """第三次m1；不读旧完整桌中途分，不发送隐藏世界或新确认牌墙。"""
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert all(pin(Path(p)) == h for p, h in preparation["files"].items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in preparation["source_manifest"].items())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-model-output")
    parents = load_vip_parents([parent_path], batch)
    gate_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-model-output-qualification/CLOSURE.json")
    causal_path = _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-CLOSED.json")
    gate, causal = (json.loads(p.read_text()) for p in (gate_path, causal_path))
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["identity"] == parents[0]["identity"] and gate["actual_completed_views"] == 115
    assert causal["complete"] and causal["counts"]["single_hand_dispatched"] == 24
    assert all(pin(Path(p)) == h for p, h in causal["files"].items())
    comparisons = [{k: row[k] for k in ("target", "case", "sample", "A", "B", "C", "B_minus_A", "C_minus_A", "C_minus_B")}
                   for row in causal["comparisons"]]
    addition = {
        "actual_operator_this_call": "m1", "actual_formal_parent": parents[0]["identity"],
        "baseline_still_frozen_S02": True,
        "mechanical": {"views": 115, "scores": 230, "changes": 8, "new_official_first_draw_changes": 0},
        "closed_conditional_ABC_feedback": comparisons,
        "sample_semantics": causal["sampler_interpretation"],
        "negative_public_sequence": {
            "case": "supplement:004:05", "own_hand": ["6b", "5w", "4w", "9w", "7w", "8w", "6b", "6b", "6w", "白"],
            "own_draw": "1b", "own_meld": ["5t", "6t", "7t"], "own_seat": 0, "dealer_seat": 3,
            "A_observed_sequence": "弃1饼保持听牌；下次本人摸到白，弃白财飘；再摸2万胡四番净+40。B/C在起点两番净+20止胡。其余三个相容样本都是净+20。",
            "interpretation": "真实追加白板可带来升档，不能因为自然need=0把远端增量硬归零；四样本不是平台概率或预期收益估计。"
        },
        "source_review": "正式父代的huoffer使用need/(1+need)以及普通向听剩余/(1+剩余)削remote/carry；这只是过硬代理。自然面子成熟与白板用途仍可升级不是一回事。仍须去掉成熟结构的重复奖励，不是恢复原S02全部常量。",
        "requested_change": "保留同速进张前沿机制，重做已可Hu时等待价值。只为当前支付以上的追加用途/实际已知升档计信用，成熟现有价值不可再奖励；对未来白、财飘、杠链采用有墙余与公开竞争折价的平滑追加价值，明确未知与追加动作成本。不要把自然need=0等同不存在增量，不要将所有成熟Hu强制停止。以可依法读取的公开容量和形状区分追加路径；公开容量不是真实牌墙概率。也不要因这一条成功追大负例规定必须等。不同来源正负例必须一起解释，先解决增量含义再调数值。",
        "validation": "原115公开窗重复机械检查，加全闭合条件续打；只有之后独立完整桌才能授增强。可保留当前Hu与等待有条件的改选，但禁止按ID/牌型期待动作硬编码。不得读取任何隐藏世界、新确认种子或终局文件。",
        "fees": "这是本批第三次实际调用，最多四次，不自动重试。"
    }
    feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-FEEDBACK.txt")).read_text()
    feedback += "\n第三提案闭合负例与正式谱系声明（覆盖原i1说明）：\n" + json.dumps(addition, ensure_ascii=False, allow_nan=False)
    feedback_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-M1-FEEDBACK.txt")
    with feedback_path.open("x") as stream:
        stream.write(feedback)
    out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-model-output")
    assert not out.exists()
    packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-START.json"), {
        "operator": "m1", "formal_parent_identity": parents[0]["identity"],
        "files": {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), feedback_path, gate_path, causal_path,
            parent_path / "candidate.py", parent_path / "generation.json")},
        "prompt_utf8_bytes_not_precise_tokens": len(packet.text.encode()),
        "previous_actual_calls": 2, "maximum_total_calls": 4, "retry": False,
        "hidden_world_or_new_confirmation_input": False, "new_full_tables_at_start": 0})
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out, operator="m1", backend="api",
        parent_paths=[parent_path], feedback=feedback, config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"),
        endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"))
    print({k: result.get(k) for k in ("status", "identity_stable", "attempt_id", "operator_actual", "error")}, flush=True)
    if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
