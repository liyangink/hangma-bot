"""冻结三种人工作机制对照；它们不是LLM提案，也没有强度或准入信用。"""

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
import ast
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent


def replace_once(source, before, after):
    """只改变声明的机制位置；找不到唯一位置拒绝生成，不静默套错父代。"""
    assert source.count(before) == 1
    return source.replace(before, after)


def main():
    """统一当前深度1身份和480万操作预算，保存实际源码及改变点。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json"))
    parent = (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()
    expected = json.loads((_project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json")).read_text())
    assert batch.identity(parent) == expected["identity"]
    natural = replace_once(parent,
        '    standard = actualroute(structure["standard_shanten"],\n',
        '    naturalcredit = 0.0\n'
        '    if structure["whites_held"] == 0:\n'
        '        whitecapacity = stock[codeindex["白"]][0]\n'
        '        naturalcredit = (PREPBUDGET * prep[3] * drawscale * pressure\n'
        '                         * whitecapacity / (TARGETMASSREF + whitecapacity))\n'
        '    standard = actualroute(structure["standard_shanten"],\n')
    natural = replace_once(natural,
        '                           0.0)\n    seven = None',
        '                           naturalcredit)\n    seven = None')
    pay = replace_once(parent,
        '    return PAYCAP * amount / (PAYREF + abs(amount))',
        '    return (0.5 * PAYCAP * amount / (PAYREF + abs(amount))\n'
        '            + 0.5 * PAYCAP * amount / PAYREF)')
    pressure = replace_once(parent,
        '    pressure = 1.0 / (1.0 + OPPDECAY * float(opponents))',
        '    mostmelds = max([len(melds) for otherseat, melds in enumerate(context["melds"])\n'
        '                     if otherseat != seat])\n'
        '    concentration = max(0.0, float(mostmelds) - float(opponents) / 3.0)\n'
        '    pressure = 1.0 / (1.0 + OPPDECAY * (float(opponents) + concentration))')
    pressure = replace_once(pressure,
        '    codeindex = {code: index for index, code in enumerate(view["tile_order"])}',
        '    risk += OPPRISK * concentration\n'
        '    codeindex = {code: index for index, code in enumerate(view["tile_order"])}')
    specs = (
        ("natural", natural, "零白自然面子准备的有限转换信用",
         "自然准备成熟但普通向听相同的等待态，增加小幅标准路线信用；精确白容量零关闭。",
         "后续摸白并非必然；自然面子奖励可能损害宽普通出口或七对，须续打反驳。"),
        ("pay", pay, "减少已知支付压缩，统一改变当下胡及条件胡尺度",
         "同一paypoints改为饱和项与线性项各半；远端白用途先验和其他费用不调。",
         "排序仍不是期望积分；新尺度可能使高当前胡更早收手，也可能高估少数升级。"),
        ("pressure", pressure, "同副露总数下的集中公开压力对照",
         "在旧总副露压力上按最多副露减均值重标定现有折减与风险；不新增独立风险费。",
         "副露集中未被现有数据证明更危险；门清强手可能更快，须保留负例。"),
    )
    out = _project_file(_PROJECT_ROOT, HERE / "diagnostic-prototypes")
    out.mkdir(exist_ok=False)
    records = []
    for name, source, thought, mechanism, counterexample in specs:
        ast.parse(source)
        ActionValueExecutor(source, max_operations=batch.max_operations,
                            max_local_collection_size=batch.projection_limits.max_nodes)
        path = out / (name + ".py")
        with path.open("x") as stream:
            stream.write(source)
        records.append({"name": name, "source_file": str(path.relative_to(HERE)),
            "source_pin": pin(path), "identity": batch.identity(source),
            "thought": thought, "expected_mechanism": mechanism, "counterexample": counterexample,
            "role": "human_controlled_diagnostic_not_model_proposal",
            "parent_identity": expected["identity"]["candidate_id"],
            "actual_model_calls": 0, "actual_scores": 0, "admitted": False})
    save(_project_file(_PROJECT_ROOT, HERE / "PROTOTYPES-FROZEN.json"), {"schema": "t182-controlled-mechanisms/1",
        "prototypes": records, "parent_identity": expected["identity"],
        "same_rules_depth_executor_budget": True,
        "before_current_new_source_comparison": True,
        "human_controlled_formulas": 3, "actual_model_proposals": 0,
        "files": {str(p.relative_to(HERE)): pin(p) for p in (
            Path(__file__), _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json"))}})
    print(json.dumps({"loaded_controlled_prototypes": 3, "actual_model_calls_scores": 0}))


if __name__ == "__main__":
    main()
