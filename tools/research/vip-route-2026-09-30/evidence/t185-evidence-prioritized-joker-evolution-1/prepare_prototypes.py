"""建立可解释消融：快路线合并进张与成熟等待增量，不改唯一规则事实。"""

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
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from common import HERE, pin, save


def replace_once(source, before, after):
    """只替换已核的精确旧片段；拒绝漂移后在错误位置打补丁。"""
    assert source.count(before) == 1
    return source.replace(before, after, 1)


def speed(source):
    """同最低向听的普通/七对进张合并计价；更慢备用只消费非重合码。"""
    source = replace_once(source, "    mass = 0.0\n    diversity = 0.0\n    exact = 0\n", '''    fastestshanten = standard[0]
    if seven is not None and seven[0] < fastestshanten:
        fastestshanten = seven[0]
    fastcodes = set()
    if standard[0] == fastestshanten:
        for code in waiting["standard_useful_codes"]:
            fastcodes.add(code)
    if seven is not None and seven[0] == fastestshanten:
        for code in waiting["seven_pairs_useful_codes"]:
            fastcodes.add(code)
    fastsupport = routesupport(fastcodes, codeindex, drawscale, stock)
    fastvalue = fastsupport[0] - FORMCOST * float(max(0, fastestshanten))
    fastextra = max(0.0, fastvalue - main[6])
    fastslots = set()
    for code in fastcodes:
        fastslots.add(codeindex[code])
    # 更慢或自然准备备用排除已在快前沿计过的码，不能重复叠加。
    slowcombined = []
    for entry in combined:
        if entry[0] not in fastslots:
            slowcombined.append(entry)
    combined = slowcombined
    mass = 0.0
    diversity = 0.0
    exact = 0
''')
    source = replace_once(source, "    if option is not None:\n        incremental = max(0.0, option[8] - credit)",
        "    credit = fastextra + 0.25 * credit\n    if option is not None:\n        incremental = max(0.0, option[8] - credit)")
    source = replace_once(source, "    portfolio = (mass, diversity, exact, codecount, uncertain, credit, float(len(baseline)))",
        "    portfolio = (mass, diversity, exact, codecount, uncertain, credit, float(len(baseline)), fastextra, fastestshanten, fastsupport[2])")
    return source


def incremental_wait(source):
    """成熟目标不冒充新增支付；保留出口只是风险抵扣，不再另发收益信用。"""
    source = replace_once(source, "        remote = discount * option[8] - remoteprice - fallback",
        "        additionalneed = float(option[3])\n        incrementaloption = option[8] * additionalneed / (1.0 + additionalneed)\n        remote = discount * incrementaloption - remoteprice - fallback")
    source = replace_once(source, "    carry = NETCARRY * discount * maintained * ordinarycore",
        "    carry = 0.0")
    return source


def main():
    """消融假设不是最佳公式；与跨源负例和完整桌结果共同决定后续提案。"""
    parent = (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()
    variants = {"speed": speed(parent), "incremental_wait": incremental_wait(parent),
                "joint": incremental_wait(speed(parent))}
    out = _project_file(_PROJECT_ROOT, HERE / "prototypes")
    out.mkdir(exist_ok=False)
    for name, source in variants.items():
        source = source.replace('"vip_convex_purpose_single_burden_m1/1"', '"t185_diagnostic_' + name + '/1"')
        ActionValueExecutor(source, max_operations=4800000, max_local_collection_size=8192)
        with (out / (name + ".py")).open("x") as stream:
            stream.write(source)
    save(_project_file(_PROJECT_ROOT, HERE / "PROTOTYPES.json"), {"schema": "t185-explicit-mechanism-prototypes/1",
        "files": {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), *sorted(out.glob("*.py"))]},
        "mechanisms": {"speed": "same-lowest-shanten route union minus already counted ordinary support; slow unused codes quarter credit",
            "incremental_wait": "mature completion prior scaled by additional natural need; exit preservation only reduces exposure; known actual upgrade untouched",
            "joint": "both changes together"},
        "weights_are_unvalidated_hypotheses": True, "not_model_generated_or_admitted": True})
    print({"static_passed": list(variants), "new_model_calls": 0}, flush=True)


if __name__ == "__main__":
    from pathlib import Path
    main()
