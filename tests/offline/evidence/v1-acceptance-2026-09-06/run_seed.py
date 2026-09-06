"""V1 开发验收的可重现实验脚本；仅用于本目录，不是生产接口。

调用原评估 CLI 的完整桌赛路径；只在装配处包裹策略做同输入比较。
实际返回原策略计划；旁路结果绝不替换动作。只接受逻辑时钟，不测时限。
每次只跑一个预先冻结的根组，独立目录落盘；已有目录拒绝覆盖。
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import evaluate as cli
from hangma_bot.application.audit_codec import (
    decision_budget_to_json,
    decision_plan_to_json,
    decision_request_to_json,
)


def write_json(path, value):
    """写入本次实验独占目录，保留可读中文；不包含凭据。"""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def verify_freeze():
    """拒绝在配置或生产源码改变后继续同一批实验，不混合版本。"""
    frozen = json.loads((HERE / "freeze.json").read_text())
    expected = dict(frozen["source_sha256"])
    expected[str((HERE / "experiment.json").relative_to(ROOT))] = frozen["experiment_sha256"]
    for name, digest in expected.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"冻结文件已变化：{name}")


class ComparedPolicy:
    """用同一玩家输入检查 V0/V1；不读取模拟完整世界，不改变原计划。"""

    def __init__(self, actual, peer, clock, counts, differences):
        self.actual = actual
        self.peer = peer
        self.clock = clock
        self.counts = counts
        self.differences = differences
        self.policy_id = actual.policy_id

    async def choose(self, request, budget):
        """返回实际策略的原计划；旁路失败单独记录，不改变实际策略异常语义。"""
        origin = self.clock()  # 当前进程逻辑单调时钟秒值，不能当 Unix 时间。
        plans = {}
        errors = {}
        actual_error = None
        for label, policy in (("actual", self.actual), ("peer", self.peer)):
            try:
                plans[label] = await policy.choose(request, budget)
            except Exception as exc:
                errors[label] = f"{type(exc).__name__}: {exc}"
                if label == "actual":
                    actual_error = exc
        self.counts["compared_requests"] += 1
        self.counts[f"phase:{request.window_key.phase.value}"] += 1
        self.counts[f"actual_policy:{self.policy_id}"] += 1
        for candidate in request.rules.legal_candidates:
            kind = "missing" if candidate.facts is None else candidate.facts.fact_kind.value
            self.counts[f"candidate_fact:{kind}"] += 1
        for label in errors:
            self.counts[f"{label}_errors"] += 1

        # 比较动作顺序和数值，理由文案与计划标识不属于正常行为退步。
        def signature(plan):
            return tuple((c.action_key, c.total_score) for c in plan.candidates)

        different = bool(errors) or signature(plans["actual"]) != signature(plans["peer"])
        if different:
            self.counts["plan_differences"] += 1
            if not errors:
                top = lambda p: p.candidates[0].action_key if p.candidates else None
                self.counts["top_action_differences"] += int(top(plans["actual"]) != top(plans["peer"]))
            row = {
                "replay_schema_version": 1,
                "hand_id": f"{request.window_key.game_id}:{request.window_key.round_no}",
                "decision_id": request.decision_id,
                "request": decision_request_to_json(request),
                "budget": decision_budget_to_json(budget),
                "budget_origin_monotonic": origin,
                "actual_policy_id": self.policy_id,
                "peer_policy_id": self.peer.policy_id,
                "plans": {k: decision_plan_to_json(v) for k, v in plans.items()},
                "errors": errors,
            }
            self.differences.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.differences.flush()
        if actual_error is not None:
            raise actual_error
        return plans["actual"]


def main():
    """执行一个根组的八个桌赛；输出 CLI 产物、分歧输入和比较覆盖计数。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-index", type=int, required=True, choices=range(32))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    verify_freeze()
    experiment = json.loads((HERE / "experiment.json").read_text())
    if experiment["clock_mode"] != "logical":
        raise ValueError("旁路比较只用于逻辑时钟实验")
    experiment["seeds"] = [experiment["seeds"][args.seed_index]]
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / "experiment.json", experiment)
    counts = Counter()
    original_factory = cli.build_policy
    declarations = {
        d["policy_id"]: cli.PolicyDeclaration.from_mapping(d, "policy")
        for d in (experiment["baseline_policy"], experiment["challenger_policy"])
    }
    ids = list(declarations)
    started = time.monotonic()  # 主机单调时钟只测整批耗时，不进入策略预算。
    with (args.out / "decisions.jsonl").open("x") as differences:
        def factory(declaration, monotonic):
            actual = original_factory(declaration, monotonic)
            if declaration.policy_id not in declarations:
                return actual
            peer_id = ids[1] if declaration.policy_id == ids[0] else ids[0]
            peer = original_factory(declarations[peer_id], monotonic)
            return ComparedPolicy(actual, peer, monotonic, counts, differences)

        # 实验局部装配：复用实际 CLI 和策略工厂，进程退出即恢复。
        cli.build_policy = factory
        try:
            cli.main(["matches", "--experiment", str(args.out / "experiment.json"), "--out", str(args.out)])
        finally:
            cli.build_policy = original_factory
            write_json(args.out / "comparison.json", {
                "counts": dict(counts),
                "elapsed_seconds": time.monotonic() - started,
                "note": "比较覆盖两条轨迹的待测座位；不是独立统计样本；仅保存分歧请求，不是完整训练牌谱。",
            })
    verify_freeze()
    write_json(args.out / "completed.json", {"seed_index": args.seed_index, "source_freeze_verified": True})


if __name__ == "__main__":
    main()
