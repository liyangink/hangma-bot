"""R18 P40b：双财神候选相对 P5 的全新完整桌独立确认。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p36_two_wealth_table_safety as p36  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40b-two-wealth-table-confirmation-01-20260922')
P39 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922')
PACKAGE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922/candidate-package.json')
CONFIRMATION_CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922/confirmation-contract.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922/candidate.py')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
DIRECTED_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40a-two-wealth-directed-confirmation-01-20260922/result.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026102213
MIXES = ("H", "M")
ROOTS = tuple(range(1, 65))
SEATS = (0, 1, 2, 3)
ARMS = ("parent", "candidate")
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
PLANNED_TABLES = SOURCE_UNITS * len(ARMS) * 2
LIMITS = ValueAnalysisLimits()
WORKERS = 8
NONINFERIORITY_MARGIN = -1.0
MIN_TRIGGERED_REQUESTS = 2


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON；只在离线证据目录产生副作用。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def configure_p36() -> None:
    """把既有完整桌执行器绑定到 P40b 的已冻结身份和默认发布配置。"""

    p36.OUT = OUT
    p36.CONTRACT = CONTRACT
    p36.CANDIDATE = CANDIDATE
    p36.PARENT = PARENT
    p36.HIDDEN_RESULT = DIRECTED_RESULT
    p36.PANEL_SEED = PANEL_SEED
    p36.MIXES = MIXES
    p36.ROOTS = ROOTS
    p36.SEATS = SEATS
    p36.ARMS = ARMS
    p36.SOURCE_UNITS = SOURCE_UNITS
    p36.PLANNED_TABLES = PLANNED_TABLES
    p36.LIMITS = LIMITS
    p36.NONINFERIORITY_MARGIN = NONINFERIORITY_MARGIN
    p36.MIN_TRIGGERED_REQUESTS = MIN_TRIGGERED_REQUESTS
    # P36 的分析器会重新枚举来源并按来源定位阶段文件；两者必须同时替换，
    # 否则可能误读 P36 的旧命名空间或在分析时找不到 P40b 证据。
    p36.sources = sources
    p36.stage_path = stage_path


def sources() -> list[dict[str, Any]]:
    """冻结 H/M 各 64 根、四焦点座位的 512 个配对来源单元。"""

    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"{mix}:p40b:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def stage_path(arm: str, source: Mapping[str, Any]) -> Path:
    """返回一个臂、一个来源单元的阶段结果路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "stages" / (
        arm + "-" + str(source["source_id"]).replace(":", "-") + ".json"
    ))


def execute_stage(arm: str, source: Mapping[str, Any]) -> dict[str, Any]:
    """子进程内重绑常量后复用 P36 的生产同源完整阶段执行。"""

    configure_p36()
    return p36.execute_stage(arm, source)


def prepare() -> None:
    """在执行前冻结候选、确认合同、来源和更严格的完整桌门。"""

    if OUT.exists():
        raise SystemExit("P40b 目录已存在；拒绝覆盖")
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    directed = json.loads(DIRECTED_RESULT.read_text(encoding="utf-8"))
    confirmation = json.loads(CONFIRMATION_CONTRACT.read_text(encoding="utf-8"))
    table_contract = confirmation["fresh_full_table_confirmation"]
    if package.get("status") != "FROZEN_FOR_INDEPENDENT_CONFIRMATION":
        raise ValueError("P39 候选未冻结")
    if directed.get("status") != "PASS_P40A_DIRECTED_CONFIRMATION":
        raise ValueError("P40a 定向独立确认没有通过")
    if digest(CANDIDATE) != package.get("candidate_sha256"):
        raise ValueError("P39 候选源码漂移")
    expected = {
        "roots_per_mix": len(ROOTS),
        "focal_seats": list(SEATS),
        "expected_source_units": SOURCE_UNITS,
        "expected_tables": PLANNED_TABLES,
        "tables_per_stage": 2,
    }
    for key, value in expected.items():
        if table_contract.get(key) != value:
            raise ValueError("P39 完整桌确认合同不匹配：" + key)
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "stages")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p40b-two-wealth-table-confirmation-01",
        accounts={"tables_full": PLANNED_TABLES, "confirm_reserved": SOURCE_UNITS},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P39确认候选冻结且P40a全新自然根定向确认通过",
        "scope": (
            "H/M各64根、四焦点座位、候选/P5两臂、每阶段两桌；"
            "默认ValueAnalysisLimits同墙换座完整桌独立确认"
        ),
        "max_model_calls": 0,
        "confirmation_roots": SOURCE_UNITS,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p40b-table-confirmation-sources/1",
        "sources": sources(),
    })
    tracked = [
        Path(__file__), Path(p36.__file__), Path(natural.__file__),
        PACKAGE, CONFIRMATION_CONTRACT, CANDIDATE, PARENT, DIRECTED_RESULT,
        CONTRACT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p40b-two-wealth-table-confirmation-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "candidate_id": package["candidate_id"],
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
        "parent_path": str(PARENT),
        "parent_sha256": digest(PARENT),
        "hidden_result_path": str(DIRECTED_RESULT),
        "hidden_result_sha256": digest(DIRECTED_RESULT),
        "package_sha256": digest(PACKAGE),
        "confirmation_contract_sha256": digest(CONFIRMATION_CONTRACT),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS,
        "arms": list(ARMS),
        "tables_per_stage": 2,
        "planned_tables": PLANNED_TABLES,
        "workers": WORKERS,
        "value_analysis_limits": {
            "max_expansions": LIMITS.max_expansions,
            "max_routes_per_candidate": LIMITS.max_routes_per_candidate,
        },
        "source_relation": "候选冻结且P40a通过后的全新panel_seed；不复用任何开发、隐藏或P36桌赛来源",
        "gate": {
            "all_tables_complete": True,
            "zero_internal_failures": True,
            "all_candidate_requests_action_value_scored": True,
            "candidate_request_errors": 0,
            "two_wealth_triggered_requests": ">=2",
            "confirmation_pass": "配对阶段积分均值>=0且来源单元bootstrap 95%下界>-1",
            "material_degradation": "配对阶段积分均值<=-1且bootstrap 95%上界<0",
        },
        "bootstrap_replicates": p36.BOOTSTRAP_REPLICATES,
        "noninferiority_margin_stage_points": NONINFERIORITY_MARGIN,
        "minimum_triggered_requests": MIN_TRIGGERED_REQUESTS,
        "confirmation_eligible": True,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "P40B_PREPARED",
        "source_units": SOURCE_UNITS,
        "planned_tables": PLANNED_TABLES,
    }, ensure_ascii=False, indent=2))


def verify() -> dict[str, Any]:
    """核对候选、合同、P40a 结果、来源与运行实现没有漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "directed": (manifest["hidden_result_sha256"], digest(DIRECTED_RESULT)),
        "package": (manifest["package_sha256"], digest(PACKAGE)),
        "confirmation_contract": (
            manifest["confirmation_contract_sha256"], digest(CONFIRMATION_CONTRACT)
        ),
        "table_contract": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError("P40b " + label + " 漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P40b 来源清单漂移")
    return manifest


def run() -> None:
    """并行执行 512 个来源单元的候选/P5同墙完整阶段。"""

    manifest = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source in sources():
        for arm in ARMS:
            path = stage_path(arm, source)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if row.get("stage", {}).get("status") != "complete":
                    raise ValueError("既有 P40b 阶段不完整：" + str(path))
                completed_tables += len(row["stage"].get("tables") or [])
            else:
                pending.append((arm, source))
    reservation = ledger.reserve(
        step_id="r18:p40b:table-confirmation",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="P39双财神候选相对P5的全新默认配置完整桌独立确认",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_stage, arm, source): (arm, source)
                for arm, source in pending
            }
            for future in concurrent.futures.as_completed(futures):
                arm, source = futures[future]
                row = None
                try:
                    row = future.result()
                    count = len(row.get("stage", {}).get("tables") or [])
                    executed += count
                    if row["stage"]["status"] != "complete" or count != 2:
                        raise RuntimeError(row["stage"].get("error") or "阶段不完整")
                    write_json(stage_path(arm, source), row)
                    completed_tables += count
                    if completed_tables % 128 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "arm": arm,
                        "source_id": source["source_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按本次返回完整桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json"))
    actual = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["stage"].get("tables") or [])
        for path in files
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p40b-table-confirmation-run/1",
        "stage_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != SOURCE_UNITS * len(ARMS):
        raise RuntimeError("P40b 完整桌确认执行不完整")


def analyze() -> None:
    """复用 P36 配对统计后，改写为 P40b 独立确认语义。"""

    verify()
    configure_p36()
    p36.analyze()
    raw_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    shutil.copyfile(raw_path, _project_file(_PROJECT_ROOT, OUT / "p36-analysis.json"))
    passed = bool(raw["gate_checks"]["research_safety_pass"])
    result = dict(raw)
    result.update({
        "schema": "r18-p40b-two-wealth-table-confirmation-result/1",
        "status": (
            "PASS_P40B_TABLE_CONFIRMATION"
            if passed else "FAIL_P40B_TABLE_CONFIRMATION"
        ),
        "candidate_id": json.loads(PACKAGE.read_text(encoding="utf-8"))["candidate_id"],
        "confirmation_gate_passed": passed,
        "natural_trigger_interpretation": (
            "P40a以全新自然根确认双财神机制收益；P40b以另一全新seed和默认"
            "ValueAnalysisLimits确认常规完整桌非劣、真实触发和运行可靠性"
        ),
        "strength_claim": False,
        "strength_interpretation": (
            "双财神机会能力已独立确认；完整桌仅确认非劣，不声称总体显著优胜"
        ),
        "confirmation_eligible": passed,
        "release_eligible": False,
        "next": (
            "执行全链并发时限/恢复门与发布审核；真实赛事注册仍关闭"
            if passed else
            "关闭当前候选发布推进，保持活动研究父代并保留P40a专长证据"
        ),
    })
    write_json(raw_path, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    globals()[parser.parse_args().operation]()
