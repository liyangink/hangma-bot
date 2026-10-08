"""冻结最多六次作者预算与三种机制任务；不发送请求，不伪装旧包为新父代。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main():
    """现工程闭包变更后采用合法i1参考基线；所有强度比较仍固定原S02。"""
    comparison = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json")).read_text())
    assert comparison["complete"] and comparison["source_stable"]
    batch_data = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json")).read_text())
    batch_data["batch_id"] = "t182-six-author-joint-mechanisms-20261004"
    batch_data["budgets"] = {"model_calls": 6, "input_tokens": 6 * 1048576,
                             "output_tokens": 6 * 65536, "table_instances": 0,
                             "wall_clock_seconds": 6 * 900}
    batch_data["input_bound"] = {"kind": "verified_model_input_limit", "model": "glm-5.3",
        "max_input_tokens": 1048576, "evidence": {"sources": [
            "https://docs.z.ai/guides/llm/glm-5.3", "https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3"],
            "verified_on": "2026-10-04", "interpretation":
            "官方1M上下文、128K输出；整上下文按二进制上取整预留输入，实际输出上限65536，不把UTF8字节当精确token数"}}
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), batch_data)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent_source = (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()
    assert batch.identity(parent_source) == json.loads((_project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json")).read_text())["identity"]
    samples = ["fresh:001:01", "fresh:004:07", "official:2:242", "official:5:982", "official:7:1177"]
    cases = {c["label"]: c for c in comparison["cases"]}
    rows = {r["label"]: r for r in comparison["rows"]}
    by_digest = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/views.jsonl.gz"), "rt") as stream:
        for line in stream:
            record = json.loads(line)
            by_digest[record["view_sha256"]] = record["view"]
    examples = []
    for label in samples:
        case, row = cases[label], rows[label]
        dto = by_digest[row["view_sha256"]]
        # 摘要只含现窗口合法动作的直接根；更深图按完整合同实现，不把摘要冒充全输入。
        keys = {a["node_key"] for a in dto["actions"]}
        examples.append({"label": label, "scope": "partial_public_development_feedback_not_full_runtime_DTO",
            "observation": case["observation"], "full_view_sha256": row["view_sha256"],
            "visible_state": dto["visible_state"], "tile_order": dto["tile_order"],
            "all_actions": dto["actions"], "direct_root_nodes": [n for n in dto["nodes"] if n["node_key"] in keys],
            "all_parent_scores": row["scores"]["parent"]["entries"],
            "prototype_scores": {n: row["scores"][n]["entries"] for n in ("natural", "pay", "pressure")}})
    directions = {
        "natural": "重点提出自然成形、未来白板转换和进张多样性的联合新机制。零白自然已成形与缺自然张应有可解释区别；多白时降低面子依赖白的代价，同时保住普通出口。不能仅叠一个太小、根间近似共同平移的奖励；不得把缺张下界叫预计摸数或公开容量叫墙概率。",
        "pay": "重点提出当前真实支付、保持听牌的便宜升级、已有链追加收益与远端用途的统一尺度取舍。半线性支付原型在临界题由等转立即胡，未证明更好；不要机械增加追大权重，须同时处理当前Hu机会成本及断链/回落。",
        "joint": "提出与前两者不同的联合交互机制：自然准备代价、后继推进宽度、白板用途、当前可靠出口和公开竞争压力。不能按对手名字/历史画像/赛事压力分流；副露集中更危险未被证明，作为不确定参数而不是既定事实。"
    }
    base_feedback = {"fixed_comparison_baseline": batch.identity(parent_source),
        "source_role": "原S02字节精确参考，当前工程依赖/限深不同于其历史生成包；i1无正式父代，不能伪称m1继承或搬用旧成绩",
        "reference_source": parent_source,
        "observed_diagnosis": {"new_mother_sources": 8, "new_complete_tables": 8, "new_complete_hands": 64,
            "panel_mother_sources": 12, "panel_windows": 63, "actual_full_scores": 252,
            "fresh_selected_windows": 54, "fresh_first_changes_all_three_prototypes": 0,
            "all_panel_changes": comparison["changed_windows"],
            "interpretation": "小改动多有数值变化但少动作变化；不是已证实无改进空间，也不是强度结论",
            "causal_status_at_preparation": "尚未闭合；作者实际调用前须另冻结最新因果反馈"},
        "examples": examples,
        "scope": "仅公开开发事实，无确认来源、隐藏世界或未来墙；同源窗口不计独立证据",
        "rules": "杭麻只能自摸；白板、爆头、财飘、杠链资格只读唯一规则事实，不自行实现规则。全合法根统一排名，条件后继保留unknown。",
        "requested_behavior": "完整联合策略，显著可解释的相关动作变化；保留过度等待/晚巡/没有自然出口的反例；不能把生成声明当成绩"}
    prompt_sizes = {}
    for name, direction in directions.items():
        feedback = json.dumps({**base_feedback, "mechanism_task": direction}, ensure_ascii=False, allow_nan=False)
        with (_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{name}-BASE-FEEDBACK.txt")).open("x") as stream:
            stream.write(feedback)
        packet, _ = build_vip_eoh_prompt(batch, "i1", [], feedback)
        prompt_sizes[name] = len(packet.text.encode())
        with (_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{name}-BASE-PROMPT.txt")).open("x") as stream:
            stream.write(packet.text)
    files = [_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json"),
        _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json"),
        _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/views.jsonl.gz"), _project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py"), Path(__file__)]
    files += [_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{n}-BASE-FEEDBACK.txt") for n in directions]
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), {"files": {str(p): pin(p) for p in files},
        "source_manifest": json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())["source_manifest"],
        "directions": list(directions), "maximum_actual_calls": 6, "initial_operator": "i1",
        "fixed_comparison_baseline": batch.identity(parent_source), "new_model_calls": 0,
        "actual_request_enhancement": {"thinking": {"type": "enabled"}, "reasoning_effort": "max"},
        "prompt_utf8_bytes_not_exact_tokens": prompt_sizes,
        "call_precondition": "完整机械和因果诊断闭合/未知说明冻结，加入反馈；每次一次请求，失败计入六槽，不自动重发"})
    print({"prepared": True, "model_calls": 0, "prompt_bytes": prompt_sizes})


if __name__ == "__main__":
    main()
