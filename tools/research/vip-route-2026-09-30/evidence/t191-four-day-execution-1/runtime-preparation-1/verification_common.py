"""T191新公式验证接缝；只复用原公开输入，不复用旧候选的准入记录。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import importlib.util
import json
import fcntl
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from types import FunctionType

from prepare_runtime_inputs import HERE, PLAN, PRIOR, ROOT, STAGE, pin, require, save
from confirmation_gate import read_accepted_confirmation
from common import canonical
import t185_close_development as dev

INPUTS = _project_file(_PROJECT_ROOT, HERE / "VALIDATION-INPUTS.json")
TOOLS = _project_file(_PROJECT_ROOT, HERE / "VALIDATION-TOOLS-CHECKED.json")
_ORIGINAL = None
HISTORICAL_SOURCE_REBINDINGS = {}


def digest(value):
    """有限JSON规范摘要；用于公开输入及完整计划比较。"""
    return hashlib.sha256(canonical(value)).hexdigest()


def check_files(files):
    """检查冻结实际字节；未知不能视为通过。"""
    require(all(pin(Path(p)) == expected for p, expected in files.items()), "验证输入字节漂移")


def original_module():
    """只读取T185原请求解码器；其旧确认、编译、准入函数不会被调用。"""
    global _ORIGINAL
    if _ORIGINAL is None:
        path = PRIOR / "candidate_verification_common.py"
        spec = importlib.util.spec_from_file_location("_t191_original_request_decoder", path)
        require(spec.name not in sys.modules, "原请求解码器模块名被占用")
        module = importlib.util.module_from_spec(spec)
        # dataclass的推迟类型注解通过sys.modules查定义模块，须在执行类定义前注册。
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _ORIGINAL = module
    return _ORIGINAL


def original_cases():
    """复用原39请求和原三段截止；不重造观察，不挑成绩或扩实际时限。"""
    original = original_module().original_cases
    context = dict(original.__globals__)
    context["check_files"] = historical_input_files
    return FunctionType(original.__code__, context, original.__name__, original.__defaults__, original.__closure__)()


def historical_input_files(files):
    """只重绑定已知27bae合法备用代码变化；原审计、预算、解码器不得漂移。

    原请求文件不是旧策略实现的资格记录。旧route_vip源码SHA作为历史事实保留，
    当前字节必须逐项等于本轮182来源冻结，其他任意变化仍拒绝。
    """
    result = {}
    allowed = "src/hangma_bot/policy/route_vip_heuristic.py"
    prior_policy = {"bytes": 37065, "sha256": "ec92ece74a2c44fa3cff31824bc51bca1abb4db63e98552a634cd9b739a26da0"}
    plan = json.loads(PLAN.read_text())
    for name, expected in files.items():
        actual = pin(Path(name))
        if actual != expected:
            require(Path(name).resolve() == _project_file(_PROJECT_ROOT, ROOT / allowed) and expected == prior_policy and
                actual == plan["source_manifest"][allowed], "原输入或未知来源漂移:" + name)
            HISTORICAL_SOURCE_REBINDINGS[name] = {"prior": expected, "current": actual,
                "known_commit": "27bae0066163e6be0cdfeed7c68e962334899c60",
                "reason": "仅已完成的明确拒绝后合法备用增补；新候选参考使用当前代码，不沿用旧评分"}
        result[name] = actual
    return result


def resource_zero(snapshot):
    """复用生产计算服务12资源项的严格自然终态判断。"""
    return original_module().resource_zero(snapshot)


@contextmanager
def research_slots(count=1):
    """真实持有共用研究槽；纯等价占1槽，十进程时限实验独占4槽。"""
    from common import OLD
    from evaluation_sharding import resource_slot_paths
    require(type(count) is int and 1 <= count <= 4, "研究槽数量非法")
    locks = []
    try:
        for path in resource_slot_paths(OLD, 4)[:count]:
            handle = path.open("r+")
            locks.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        for handle in reversed(locks):
            handle.close()


def public_cases():
    """按公开观察与窗口键去重后的输入面板；同案例重复不冒称额外覆盖。"""
    frozen, _ = dev.read(INPUTS)
    check_files(frozen["input_files"])
    return frozen["public_cases"]


def planned_scores():
    """真实等价评分额度：每图双实现双重复、4耗尽、39请求双实现。"""
    frozen, _ = dev.read(INPUTS)
    return frozen["planned_equivalence_score_attempts"]


def make_policy(batch, source, compiled=None):
    """使用生产同型策略和确认批次预算；不注册线上策略或创建网络客户端。"""
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    return RouteVipHeuristicPolicy(batch.rule_config, source=source, max_operations=batch.max_operations,
        projection_limits=batch.projection_limits, compiled_runtime=compiled)


def validated_candidate():
    """完整独立强度及实际编译闭合后才取得本轮公式，未结束时评分前拒绝。"""
    from build_candidate_native import load_checked_runtime, OUT
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    plan, _, evidence = read_accepted_confirmation()
    checked, checked_pin = dev.read(TOOLS)
    require(checked["complete"] is True and checked["new_scores_compilations_worlds_tables_HTTP_models_compute_workers"] == 0,
        "验证工具准备未过")
    check_files(checked["files"])
    arm = plan["candidates"][0]
    batch_path = PLAN.with_name("EXECUTION-BATCH.json")
    batch = VipEohBatch.read(batch_path)
    require(batch.identity(Path(arm["source_file"]).read_text()) == arm["identity"], "公式身份与确认不同")
    native, native_pin = dev.read(OUT / "BUILD-PLAN.json")
    closed, closed_pin = dev.read(OUT / "BUILD-CLOSED.json")
    require(native["candidate_identity"] == arm["identity"] and native["confirmation_evidence_files"] == evidence and
        closed["candidate_identity"] == arm["identity"] and closed["build_plan_pin"] == native_pin,
        "实际编译未绑定本轮确认")
    runtime = load_checked_runtime()
    files = {**checked["files"], **evidence, str(TOOLS): checked_pin, str(batch_path): pin(batch_path),
        str(OUT / "BUILD-PLAN.json"): native_pin, str(OUT / "BUILD-CLOSED.json"): closed_pin,
        **native["build_input_files"], closed["binary_path"]: closed["binary_pin"]}
    return batch, arm, runtime, files


@dataclass(frozen=True)
class ConfirmedCandidateFactory:
    """可spawn的离线工厂；只携公开源码路径和身份，不含Token或完整世界。"""
    source_file: str  # 仅在计算进程启动期读取的已确认公式路径。
    candidate_id: str  # 本轮唯一候选身份。
    execution_id: str  # 本轮编译计划与实际二进制的摘要。

    def __call__(self):
        """启动时验签小型编译输入；动作窗口不读取确认大原件。"""
        from build_candidate_native import load_checked_runtime, OUT
        from hangma_bot.application.decision_compute import PreparedDecisionPolicy
        from hangma_bot.offline.vip_eoh_generate import VipEohBatch
        native, _ = dev.read(OUT / "BUILD-PLAN.json")
        identity = native["candidate_identity"]
        require(identity["candidate_id"] == self.candidate_id and
            native["build_input_files"].get(self.source_file) == pin(Path(self.source_file)) and
            pin(Path(self.source_file))["sha256"] == identity["source_sha256"], "工厂实际公式身份漂移")
        runtime = load_checked_runtime()
        require(runtime.execution_id == self.execution_id, "工厂执行身份漂移")
        batch = VipEohBatch.read(PLAN.with_name("EXECUTION-BATCH.json"))
        params = {"max_operations": batch.max_operations, "max_local_collection_size": batch.projection_limits.max_nodes,
            "projection_limits": asdict(batch.projection_limits), "route_limits": asdict(batch.route_limits),
            "rule_config": asdict(batch.rule_config)}
        require(params == identity["params"], "工厂框架预算不同")
        return PreparedDecisionPolicy(make_policy(batch, Path(self.source_file).read_text(), runtime), runtime.execution_id)
