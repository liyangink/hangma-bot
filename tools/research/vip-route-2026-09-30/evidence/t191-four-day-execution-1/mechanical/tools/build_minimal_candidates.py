"""在原S02上排他生成两个单项工程修复；不伪造作者生成记录。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/mechanical/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import difflib
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.vip_s02_frozen_source import VIP_S02_SOURCE

HERE = Path(__file__).resolve().parents[2]


def pin(path):
    """实际文件摘要与字节数；非评分或发布资格。"""
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def save(path, value):
    """排他新建，旧尝试原件不覆盖。"""
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def constants(source):
    """逐项比较模块级常数，阻止无关权重漂移。"""
    return {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(source).body
            if isinstance(n, ast.Assign)}


def main():
    """红结果已发生之后，构造最小源码、精确diff与真实身份。"""
    red = _project_file(_PROJECT_ROOT, HERE / "mechanical/red-s02/CLOSED.json")
    assert json.loads(red.read_text())["complete"]
    red_summary = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanical/red-s02/MECHANISM-SUMMARY.json")).read_text())
    assert red_summary["red_capable_checks"] == {"same_speed_union_paid": False, "mature_base_carry_zero": False}
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"))
    source = (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()
    assert source == VIP_S02_SOURCE
    helper = '''def speedfront(waiting):
    """同最小向听普通/七对的物理码去重并集；仅供基础推进支持。

    只重组已有合法公开有效码，不重算向听、不声明胡牌资格；后续两家族
    同速时消费同一个已付支持，不能再在目标最大值后另加一份并集信用。
    """
    structure = waiting["structure"]
    minimum = structure["standard_shanten"]
    seven = structure["seven_pairs_shanten"]
    if seven is not None and seven < minimum:
        minimum = seven
    codes = []
    seen = set()
    if structure["standard_shanten"] == minimum:
        for code in waiting["standard_useful_codes"]:
            if code not in seen:
                seen.add(code)
                codes.append(code)
    if seven is not None and seven == minimum:
        for code in waiting["seven_pairs_useful_codes"]:
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return minimum, tuple(codes)


'''
    speed = source.replace('def jointwait(waiting, standard, seven, prep, local, codeindex, room, drawscale,',
        helper + 'def jointwait(waiting, standard, seven, frontcodes, prep, local, codeindex, room, drawscale,', 1)
    speed = speed.replace('    whites = waiting["structure"]["whites_held"]\n',
        '    if seven is not None and seven[0] == standard[0]:\n'
        '        maincodes = frontcodes\n'
        '    whites = waiting["structure"]["whites_held"]\n', 1)
    speed = speed.replace('    prep = prepvalue(waiting)\n',
        '    prep = prepvalue(waiting)\n'
        '    minimum, frontcodes = speedfront(waiting)\n'
        '    standardcodes = waiting["standard_useful_codes"]\n'
        '    sevencodes = waiting["seven_pairs_useful_codes"]\n'
        '    if structure["standard_shanten"] == minimum:\n'
        '        standardcodes = frontcodes\n'
        '    if structure["seven_pairs_shanten"] == minimum:\n'
        '        sevencodes = frontcodes\n', 1)
    speed = speed.replace('routesupport(waiting["standard_useful_codes"], codeindex, drawscale, stock),',
        'routesupport(standardcodes, codeindex, drawscale, stock),', 1)
    speed = speed.replace('routesupport(waiting["seven_pairs_useful_codes"], codeindex, drawscale, stock),',
        'routesupport(sevencodes, codeindex, drawscale, stock),', 1)
    speed = speed.replace('jointwait(waiting, standard, seven, prep, local, codeindex,',
        'jointwait(waiting, standard, seven, frontcodes, prep, local, codeindex,', 1)
    needle = '    carry = NETCARRY * discount * maintained * ordinarycore\n'
    assert source.count(needle) == 1
    wait = source.replace(needle, needle +
        '    # 当前胡锚已支付成熟普通结构；保留其出口不构成额外等待收益。\n'
        '    # 不按自然目标need归零：直接支付差及白用途/追加行动option仍独立保留。\n'
        '    if main[0] <= 0:\n'
        '        carry = 0.0\n', 1)
    assert constants(source) == constants(speed) == constants(wait)
    proposals = [
        ("speed", speed, "同最小向听普通/七对联合有效牌作为两路线已付基础支持；目标max前消费并集，备用排除已付并集。",
            "T185 speedfront集合思想；未继承参数、备用系数或旧成绩。"),
        ("wait", wait, "只将已成熟普通结构(main[0]<=0)的carry置零；当前胡、下一摸支付差、远目标白用途与追加行动负担保留原S02。",
            "Astra§4及T189 a408重复继续信用；T185成熟白用途正控制独立报告，不硬定必等。"),
    ]
    for name, candidate, change, origin in proposals:
        out = _project_file(_PROJECT_ROOT, HERE / "candidates" / name)
        out.mkdir(parents=True, exist_ok=False)
        path = out / "source.py"
        with path.open("x") as stream:
            stream.write(candidate)
        with (out / "exact.diff").open("x") as stream:
            stream.write("".join(difflib.unified_diff(source.splitlines(True), candidate.splitlines(True),
                fromfile="T110-S02:parent-source.py", tofile="T191:" + name + "/source.py")))
        executor = ActionValueExecutor(candidate, max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes)
        assert executor.source == candidate
        save(out / "ENGINEERING-PROPOSAL.json", {
            "schema": "t191-human-engineering-proposal/1", "implementation_type": "human_implementation",
            "name": "S02+" + name, "source_path": str(path), "source_pin": pin(path),
            "identity": batch.identity(candidate), "parent_identity": batch.identity(source),
            "parent_source_pin": pin(_project_file(_PROJECT_ROOT, HERE / "parent-source.py")), "batch_pin": pin(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json")),
            "exact_diff_pin": pin(out / "exact.diff"), "change": change, "origin": origin,
            "all_module_constants_unchanged": True, "static_restricted_executor_accepted": True,
            "model_calls": 0, "generation_record": None, "old_results_inherited": False,
            "mechanical_complete": False, "strength_or_deadline_or_online_admission": False,
            "red_result_pin": pin(red), "builder_pin": pin(Path(__file__)),
        })
    print(json.dumps({"created": [p[0] for p in proposals], "all_constants_unchanged": True}))


if __name__ == "__main__":
    main()
