"""构造单变量诊断源码；不冒充LLM输出，不改线上策略或冻结原件。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor


def main():
    """逐项验证替换唯一及执行器准入，先封存112次评分预算。"""
    assert not (_project_file(_PROJECT_ROOT, HERE / "PROBE-PREPARATION.json")).exists()
    source = (_project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-explore-model-output/candidate.py")).read_text()
    needle = """    mass = 0.0
    diversity = 0.0
    exact = 0
    codecount = 0
    uncertain = 0
    if preparationoccupied == 0 and prep[0] > 0 and prep[2] > 0:"""
    replacement = """    paidfollowers = set()
    if followercredit > 0.0 and seven is not None:
        for code in waiting["standard_useful_codes"]:
            if code not in leadset and stock[codeindex[code]][0] > 0.0:
                paidfollowers.add(code)
        for code in waiting["seven_pairs_useful_codes"]:
            if code not in leadset and stock[codeindex[code]][0] > 0.0:
                paidfollowers.add(code)
    duplicatewidth = 0
    mass = 0.0
    diversity = 0.0
    exact = 0
    codecount = 0
    uncertain = 0
    if preparationoccupied == 0 and prep[0] > 0 and prep[2] > 0:"""
    assert source.count(needle) == 1
    instrument = source.replace(needle, replacement)
    old = """            if code not in credited and stock[slot][0] > 0.0:
                cell = stock[slot]"""
    new = """            if code not in credited and stock[slot][0] > 0.0:
                if code in paidfollowers:
                    duplicatewidth += 1
                cell = stock[slot]"""
    assert instrument.count(old) == 1
    instrument = instrument.replace(old, new)
    old = "                 float(len(credited)), followercredit)"
    assert instrument.count(old) == 1
    instrument = instrument.replace(
        old, "                 float(len(credited)), followercredit, duplicatewidth)"
    )
    deduplicated = instrument.replace(
        "    duplicatewidth = 0\n    mass = 0.0",
        "    for code in paidfollowers:\n        credited.add(code)\n"
        "    duplicatewidth = 0\n    mass = 0.0",
    )
    old = "                if retained > 1 or need > 0:"
    assert instrument.count(old) == 1
    new = (
        "                if retained > 1 or need > 0 or "
        "(retained == 1 and need == 0 and prep[0] == 0):"
    )
    opened = instrument.replace(old, new)
    combined = deduplicated.replace(old, new)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-BATCH.json"))
    probes = []
    for name, code, purpose in [
        ("I", instrument, "只追加重复码诊断；分值须与原C逐根精确"),
        ("D", deduplicated, "只消除跟随路线与自然准备重复信用"),
        ("E", opened, "只放开自然准备完成的成熟单白新白机会通道"),
        ("DE", combined, "组合两项；其余常数不变"),
    ]:
        path = _project_file(_PROJECT_ROOT, HERE / f"probe-{name}.py")
        assert not path.exists()
        ActionValueExecutor(
            code,
            max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes,
        )
        path.write_text(code)
        probes.append(
            {
                "name": name,
                "source_file": str(path),
                "identity": batch.identity(code),
                "purpose": purpose,
                "model_output": False,
                "admission": False,
            }
        )
    paths = [
        Path(__file__),
        _project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-explore-model-output/candidate.py"),
        _project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICES.jsonl.gz"),
        _project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICE-CLOSED.json"),
    ] + [Path(p["source_file"]) for p in probes]
    save(
        _project_file(_PROJECT_ROOT, HERE / "PROBE-PREPARATION.json"),
        {
            "complete": True,
            "probes": probes,
            "files": {str(p): pin(p) for p in paths},
            "cases": 14,
            "planned_actual_scores": 112,
            "repeats": 2,
            "manual_diagnostic_not_EOH_author": True,
            "actual_new_scores_worlds_models_HTTP": 0,
        },
    )
    print(json.dumps({"prepared": True, "probes": 4, "planned_actual_scores": 112}))


if __name__ == "__main__":
    main()
