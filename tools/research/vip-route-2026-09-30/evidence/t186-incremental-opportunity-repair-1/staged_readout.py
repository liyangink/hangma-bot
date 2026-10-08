"""T186阶段只读：复用已核评分收据与分账，完整阶段结束后才读分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import ast
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from t185_prepare_confirmation import background_priority, postprocess_lock
import t185_close_development as original
from readout_compat import copied_readout
from four_worker_campaign import validate


def account_reader():
    """只将原结算身份前缀改为T186；算术、阈值、完整桌和守恒检查不变。"""
    tree = ast.parse(Path(original.__file__).read_text())
    function = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "account"))
    class Prefix(ast.NodeTransformer):
        count = 0
        def visit_Constant(self, node):
            if node.value == "t185-development:":
                self.count += 1
                return ast.copy_location(ast.Constant("t186-development:"), node)
            return node
    transform = Prefix()
    function = transform.visit(function)
    original.require(transform.count == 1, "结算身份前缀改动不唯一")
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    context = dict(original.__dict__)
    exec(compile(module, str(Path(__file__)), "exec"), context)
    return context["account"]


def read_stage(plan_path):
    """检查原阶段终态、资源、全评分、对手及同物理牌山；不重构或重评分。"""
    background_priority()
    plan, plan_pin, lanes = validate(plan_path)
    directory = Path(plan["dispatch_directory"])
    ended = json.loads((directory / "CLOSED.json").read_text())
    original.require(ended["complete"] and ended["resources_released"] and
        ended["worker_returncodes"] == [0] * 4 and ended["plan_pin"] == plan_pin and
        ended["actual_table_calls"] == plan["planned_table_instances"] and
        ended["completed_ordinals"] == list(range(plan["planned_table_instances"])), "阶段未完整结束")
    compat = copied_readout(original)
    compat["frozen"](plan)
    read_account = account_reader()
    tables, walls, initials = [], {}, {}
    files = {str(p): pin(p) for p in (Path(__file__), directory / "CLOSED.json", Path(plan_path))}
    for task in plan["tasks"]:
        index, rotation, arm = (task[k] for k in ("root", "rotation", "arm"))
        d = Path(plan["output_directory"]) / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm}"
        start, closure, pairing = (d / n for n in ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json"))
        c = json.loads(closure.read_text())
        original.require(c["complete"] and c["source_stable"] and c["failure"] is None and
            c["plan_pin"] == plan_pin and c["rotation"] == rotation and
            c["root"] == plan["roots"][index - 1], "原桌终态或身份不同")
        original.require(c["outcome"]["status"] == "complete" and c["outcome"]["completed_hands"] == plan["rounds"] and
            all(type(v) is int and v == 0 for v in c["outcome"]["runtime_counts"].values()), "原桌有运行故障")
        evidence = original.TableEvidence(index, rotation, arm, d, pin(start), pin(closure), pin(pairing))
        audit, capture_files = compat["score_receipts"](evidence, c, plan)
        files.update(capture_files)
        account, final = read_account(c["settlements"], rotation, plan["roots"][index - 1]["root_id"])
        original.require(final == c["outcome"]["final_scores"] and account["net"] == final[rotation], "完整桌积分不对账")
        original.require(len(c["pairing_proofs"]) == plan["rounds"], "物理牌山证明缺失")
        for n, proof in enumerate(c["pairing_proofs"], 1):
            original.require(proof["round_no"] == n and proof["export_matches_frozen_sampler"] and
                proof["teacher_only_not_policy_input"] and
                walls.setdefault((index, n), proof["physical_wall_sha256"]) == proof["physical_wall_sha256"],
                "父子或换座物理牌山不同")
            if n == 1:
                original.require(proof["dealer_seat"] == 0 and
                    initials.setdefault(index, proof["actual_initial_sha256"]) == proof["actual_initial_sha256"], "初庄或起手不同")
        for p in (start, closure, pairing, d / "focal-decisions.jsonl.gz", d / "views.jsonl.gz"):
            files[str(p)] = pin(p)
        tables.append({"root": index, "rotation": rotation, "arm": arm, "account": account,
                       "final_scores_0_1_2_3": final, "audit": audit})
    compat["frozen"](plan)
    original.require(all(pin(Path(p)) == h for p, h in files.items()), "阶段读回期间原件漂移")
    result = {"complete": True, "files": files, "plan_pin": plan_pin, "tables": tables,
        "actual_tables": len(tables), "actual_focal_score_calls": sum(t["audit"]["actual_score_calls"] for t in tables),
        "actual_cpu_workers": 4, "source_stable": True, "all_original_deadline_or_online_admissions": False,
        "exploratory_development_only": True, "new_scores_worlds_tables_models_HTTP": 0}
    save(directory / "READOUT-CLOSED.json", result)
    print(json.dumps({k: result[k] for k in ("complete", "actual_tables", "actual_focal_score_calls", "actual_cpu_workers")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    with postprocess_lock("t186_completed_stage_readout"):
        read_stage(args.plan)
