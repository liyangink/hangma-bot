"""多父代窗口交叉的冻结真实请求行为与接线验收。"""
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
import asyncio
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE, _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import cross_specialist_policy as candidate  # noqa: E402
import followup_quality_checks as parent_checks  # noqa: E402
import followup_quality_policy as followup_parent  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921')
PARENT_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/followup-quality-prototype-20260920/manifest.json')
ROUTE_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/configurations/r2-cfg-02/candidate.py')
V2_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
MODES = (
    "v2", "followup_discard", "route_all", "route_draw_only",
    "route_claim_only", "cross_followup_claim",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit("多父代交叉目录已存在；拒绝覆盖")
    parent = json.loads(PARENT_MANIFEST.read_text(encoding="utf-8"))
    guard.verify(parent["runtime"])
    inputs = parent["behavior_inputs"]
    if len(inputs) < 50:
        raise ValueError("真实请求语料不足")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "r10-cross-specialist-preflight/1",
        "created_at_utc": batch.search.utc_now(),
        "hypothesis": (
            "后继质量父代只处理摸牌弃牌，条件路线父代只处理chi/peng响应，"
            "可保留两类专长并避免同一奖励跨动作族传播。"
        ),
        "parents": {
            "v2": {"path": str(V2_SOURCE), "sha256": digest(V2_SOURCE)},
            "followup_quality": {
                "path": str(Path(followup_parent.__file__)),
                "sha256": digest(Path(followup_parent.__file__)),
                "manifest": str(PARENT_MANIFEST),
                "manifest_sha256": digest(PARENT_MANIFEST),
            },
            "route_fixed_bonus": {"path": str(ROUTE_SOURCE), "sha256": digest(ROUTE_SOURCE)},
        },
        "modes": list(MODES),
        "behavior_inputs": inputs,
        "rule_config": parent["rule_config"],
        "runtime": guard.capture(source_paths=[Path(__file__), Path(candidate.__file__),
                                                 Path(followup_parent.__file__), ROUTE_SOURCE]),
        "effect_tables": 0,
        "selection_eligible": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED", "requests": len(inputs),
                      "modes": list(MODES)}, ensure_ascii=False))


def verify(plan: dict) -> None:
    guard.verify(plan["runtime"])
    for item in plan["parents"].values():
        if digest(Path(item["path"])) != item["sha256"]:
            raise ValueError("父代摘要漂移：" + item["path"])
        if "manifest" in item and digest(Path(item["manifest"])) != item["manifest_sha256"]:
            raise ValueError("父代清单摘要漂移")
    for name, expected in plan["behavior_inputs"].items():
        if digest(Path(name)) != expected:
            raise ValueError("行为输入摘要漂移：" + name)


async def check() -> None:
    if (_project_file(_PROJECT_ROOT, OUT / "checks.json")).exists():
        raise SystemExit("多父代交叉验收已存在；拒绝覆盖")
    plan = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    verify(plan)
    config = RuleConfig(**plan["rule_config"])
    route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
    identity = digest(ROUTE_SOURCE)[:16]
    policies = {
        mode: candidate.CrossSpecialistPolicy(
            config, lambda: 0.0, mode=mode, route_source=route_source,
            identity=identity, value_limits=ValueAnalysisLimits(),
        )
        for mode in MODES
    }
    budget = DecisionBudget(1.0, 2.0, 3.0)
    counts = {mode: Counter() for mode in MODES}
    records = []
    for name in sorted(plan["behavior_inputs"]):
        raw = json.loads(Path(name).read_text(encoding="utf-8"))
        request = parent_checks.b.behavior.decision_request_from_json(raw["request"])
        outputs = {}
        audits = {}
        for mode, policy in policies.items():
            result = await policy.choose(request, budget)
            outputs[mode] = result
            audit = dict(policy.audit[-1])
            audits[mode] = audit
            counts[mode][audit["status"]] += 1
            counts[mode]["changed"] += int(audit["changed"])
            expected_keys = {
                item.action_key for item in request.rules.legal_candidates
                if item.action_key not in {rejected.action_key for rejected in request.rejected_attempts}
            }
            actual_keys = {item.action_key for item in result.candidates}
            if not actual_keys <= expected_keys:
                raise ValueError("策略输出了非规则合法动作")
            if [item.rank for item in result.candidates] != list(range(1, len(result.candidates) + 1)):
                raise ValueError("候选rank不连续")
        baseline = outputs["v2"]
        if audits["v2"]["status"] != "NOT_APPLICABLE":
            raise ValueError("V2控制审计异常")
        phase = request.observation.phase
        if phase == "draw":
            if asdict(outputs["cross_followup_claim"]) != asdict(outputs["followup_discard"]):
                raise ValueError("交叉策略摸牌窗口未精确继承后继质量父代")
            if asdict(outputs["route_claim_only"]) != asdict(baseline):
                raise ValueError("吃碰专长污染摸牌窗口")
        elif phase in candidate.CLAIM_PHASES:
            if asdict(outputs["cross_followup_claim"]) != asdict(outputs["route_claim_only"]):
                raise ValueError("交叉策略吃碰窗口未精确继承路线父代")
            if asdict(outputs["followup_discard"]) != asdict(baseline):
                raise ValueError("弃牌专长污染吃碰窗口")
        else:
            if asdict(outputs["cross_followup_claim"]) != asdict(baseline):
                raise ValueError("交叉策略污染未声明动作窗口")
        records.append({
            "input": name,
            "phase": phase,
            "preferred": {
                mode: (output.candidates[0].action_key if output.candidates else None)
                for mode, output in outputs.items()
            },
            "audits": audits,
        })
    for mode in MODES:
        if counts[mode]["ERROR_FALLBACK"] or counts[mode]["FACT_FALLBACK"] or counts[mode]["COST_FALLBACK"]:
            raise ValueError("真实请求预检出现父代回退：" + mode)
    verify(plan)
    write_json(_project_file(_PROJECT_ROOT, OUT / "behavior-records.json"), records)
    write_json(_project_file(_PROJECT_ROOT, OUT / "checks.json"), {
        "schema": "r10-cross-specialist-checks/1",
        "status": "PASS_OFFLINE_BEHAVIOR_ONLY",
        "requests": len(records),
        "modes": {mode: dict(counts[mode]) for mode in MODES},
        "dispatch_inheritance": {
            "draw": "cross == followup_discard; route_claim_only == V2",
            "response_chi/peng": "cross == route_claim_only; followup_discard == V2",
            "other": "cross == V2",
        },
        "effect_tables": 0,
        "selection_eligible": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "checks.json")).read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else asyncio.run(check())
