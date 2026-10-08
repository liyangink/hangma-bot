"""R18 P39：冻结双财神活动父代的独立确认候选包。"""

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
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p35_two_wealth_hidden_admission as p35  # noqa: E402
import r18_p36_two_wealth_table_safety as p36  # noqa: E402
import r18_p37_two_wealth_active_parent as p37  # noqa: E402
import sitin_gates as gates  # noqa: E402
from hangma_bot.bootstrap import (  # noqa: E402
    AVAILABLE_STRATEGIES,
    DEFAULT_RULESET_VERSION,
)
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import (  # noqa: E402
    VALUE_ANALYSIS_SEMANTICS_VERSION,
)
from hangma_bot.policy.research_candidates import (  # noqa: E402
    R18_TWO_WEALTH_BAOTOU_V1_NAME,
    R18_TWO_WEALTH_BAOTOU_V1_SHA256,
    R18_TWO_WEALTH_BAOTOU_V1_SOURCE,
    build_research_candidate_scorer,
)
from hangma_bot.simulation.artifacts import (  # noqa: E402
    GUIDE_CAPTURED_AT,
    GUIDE_VERSION,
    compute_rules_hash,
    hand_math_runtime_metadata,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922')
P38 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p38-integrated-parent-preflight-01-20260922')
STRATEGY = "action_value:r18_two_wealth_baotou_v1"
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json')


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


def freeze() -> None:
    """绑定源码、合同、执行器、规则、依赖、前序证据与确认门槛。"""

    if OUT.exists():
        raise SystemExit("P39 确认候选目录已存在；拒绝覆盖")
    p35_result = json.loads((p35.OUT / "result.json").read_text(encoding="utf-8"))
    p36_result = json.loads((p36.OUT / "result.json").read_text(encoding="utf-8"))
    p37_parent = json.loads(
        (p37.OUT / "active-parent.json").read_text(encoding="utf-8")
    )
    p38_result = json.loads((_project_file(_PROJECT_ROOT, P38 / "result.json")).read_text(encoding="utf-8"))
    prerequisite_checks = {
        "p35_hidden_gate_passed": p35_result.get("gate_passed") is True,
        "p36_research_safety_passed": (
            p36_result.get("status") == "PASS_R18_P36_RESEARCH_SAFETY"
        ),
        "p37_active_research_parent": (
            p37_parent.get("active_research_parent") is True
        ),
        "p38_package_integration_passed": (
            p38_result.get("status") == "PASS_P38_PACKAGE_INTEGRATION"
        ),
        "package_digest_matches": (
            hashlib.sha256(R18_TWO_WEALTH_BAOTOU_V1_SOURCE.encode("utf-8")).hexdigest()
            == R18_TWO_WEALTH_BAOTOU_V1_SHA256
        ),
        "network_registry_remains_closed": STRATEGY not in AVAILABLE_STRATEGIES,
    }
    if not all(prerequisite_checks.values()):
        raise ValueError("P39 前置条件失败：" + repr(prerequisite_checks))

    scorer = build_research_candidate_scorer(R18_TWO_WEALTH_BAOTOU_V1_NAME)
    identity = gates.av_identity_binding(R18_TWO_WEALTH_BAOTOU_V1_SOURCE)
    if identity["candidate_source_sha256"] != R18_TWO_WEALTH_BAOTOU_V1_SHA256:
        raise ValueError("P39 身份绑定的源码摘要不等于规范化候选")
    if scorer.max_operations != 100_000:
        raise ValueError("P39 确认候选不是默认 100,000 operations 配置")

    OUT.mkdir(parents=True)
    candidate_path = _project_file(_PROJECT_ROOT, OUT / "candidate.py")
    candidate_path.write_text(R18_TWO_WEALTH_BAOTOU_V1_SOURCE, encoding="utf-8")
    if digest(candidate_path) != R18_TWO_WEALTH_BAOTOU_V1_SHA256:
        raise ValueError("P39 复制后的候选源码摘要漂移")

    confirmation_contract = {
        "schema": "r18-p39-two-wealth-confirmation-contract/1",
        "candidate_id": identity["candidate_id"],
        "candidate_sha256": R18_TWO_WEALTH_BAOTOU_V1_SHA256,
        "family": "two_wealth.piao_keeps_baotou",
        "one_shot": True,
        "development_and_hidden_roots_forbidden": True,
        "directed_natural_confirmation": {
            "source": "全新 P5 自然轨迹；行动前公开谓词首次命中；每来源根最多一个状态",
            "minimum_independent_roots": 8,
            "minimum_roots_by_mix": {"H": 4, "M": 4},
            "hidden_worlds_per_root": 32,
            "arms": ["P5 immediate hu", "candidate discard wealth then P5"],
            "primary_metric": "当前局焦点结算差（候选减 P5）",
            "pass": {
                "mechanical_success": "全部",
                "candidate_action_matches_frozen_intervention": "全部",
                "bootstrap_95_lower": "> 0",
                "positive_roots": ">= 7/8",
                "minimum_leave_one_root_out_mean": "> 0",
            },
        },
        "fresh_full_table_confirmation": {
            "mixes": ["H", "M"],
            "roots_per_mix": 64,
            "focal_seats": [0, 1, 2, 3],
            "tables_per_stage": 2,
            "arms": ["candidate", "P5"],
            "expected_source_units": 512,
            "expected_tables": 2048,
            "pass": {
                "all_tables_complete": True,
                "all_candidate_requests_scored": True,
                "action_value_failures": 0,
                "natural_target_triggers": ">= 2",
                "paired_stage_score_delta_mean": ">= 0",
                "source_unit_bootstrap_95_lower": "> -1.0",
                "material_degradation": False,
            },
        },
        "failure_policy": (
            "任一确认门失败即保持活动研究父代但关闭发布推进；不得打开逐例结果后"
            "修改同一候选再复用本确认集"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "identity-binding.json"), identity)
    write_json(_project_file(_PROJECT_ROOT, OUT / "confirmation-contract.json"), confirmation_contract)
    candidate_package = {
        "schema": "r18-p39-two-wealth-confirmation-candidate/1",
        "status": "FROZEN_FOR_INDEPENDENT_CONFIRMATION",
        "candidate_name": R18_TWO_WEALTH_BAOTOU_V1_NAME,
        "offline_strategy": STRATEGY,
        "candidate_id": identity["candidate_id"],
        "candidate_sha256": R18_TWO_WEALTH_BAOTOU_V1_SHA256,
        "execution_profile": {
            "name": "default-100k-v1",
            "max_operations": scorer.max_operations,
        },
        "value_analysis_limits": asdict(ValueAnalysisLimits()),
        "value_analysis_semantics_version": VALUE_ANALYSIS_SEMANTICS_VERSION,
        "rules": {
            "ruleset_version": DEFAULT_RULESET_VERSION,
            "rules_source_sha256": compute_rules_hash(ROOT),
            "official_guide_version": GUIDE_VERSION,
            "official_guide_captured_at": GUIDE_CAPTURED_AT,
            "hand_math_runtime": hand_math_runtime_metadata(),
        },
        "prerequisite_checks": prerequisite_checks,
        "evidence": {
            "p35_hidden_result_sha256": digest(p35.OUT / "result.json"),
            "p36_table_safety_result_sha256": digest(p36.OUT / "result.json"),
            "p37_equivalence_sha256": digest(p37.OUT / "equivalence.json"),
            "p38_integration_result_sha256": digest(_project_file(_PROJECT_ROOT, P38 / "result.json")),
        },
        "confirmation_eligible": True,
        "release_eligible": False,
        "network_registry_exposed": False,
        "next": "按 confirmation-contract 一次性执行全新定向自然确认与完整桌确认",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "candidate-package.json"), candidate_package)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p39-two-wealth-confirmation-candidate-manifest/1",
        "script_sha256": digest(Path(__file__)),
        "candidate_sha256": digest(candidate_path),
        "contract_sha256": digest(CONTRACT),
        "identity_binding_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "identity-binding.json")),
        "confirmation_contract_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "confirmation-contract.json")),
        "candidate_package_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "candidate-package.json")),
        "confirmation_eligible": True,
        "release_eligible": False,
    })
    print(json.dumps(candidate_package, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze",))
    globals()[parser.parse_args().operation]()
