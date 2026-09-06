"""续跑固定验收批次并汇总；使用隔离子进程，不占用官方 Token。

输入为本目录冻结配置，输出为用户指定的新根目录或已有检查点目录。
遇到中断子目录明确失败，不自动覆盖；所有 32 组成功后才输出总报告。
"""

import argparse
from copy import deepcopy
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from run_seed import HERE, ROOT, verify_freeze, write_json


def main():
    """最多四个本地 CPU 进程，逐组保留日志并拒绝混合生产源码版本。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    verify_freeze()
    args.out.mkdir(parents=True, exist_ok=True)
    full_experiment = json.loads((HERE / "experiment.json").read_text())

    def run_one(index):
        out = args.out / f"seed-{index:02d}"
        if not (out / "completed.json").is_file():
            with (args.out / f"seed-{index:02d}.log").open("a") as log:
                subprocess.run([
                    sys.executable, str(HERE / "run_seed.py"), "--seed-index", str(index),
                    "--out", str(out),
                ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        verify_freeze()
        expected = deepcopy(full_experiment)
        expected["seeds"] = [full_experiment["seeds"][index]]
        if json.loads((out / "experiment.json").read_text()) != expected:
            raise RuntimeError(f"检查点配置与冻结实验不符：{out}")
        if json.loads((out / "completed.json").read_text())["seed_index"] != index:
            raise RuntimeError(f"检查点根组索引不符：{out}")
        comparison = json.loads((out / "comparison.json").read_text())
        print(f"根组 {index:02d} 完成：{comparison['counts']}", flush=True)
        return out

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        dirs = list(pool.map(run_one, range(32)))

    counts = Counter()
    results = []
    diagnostics = []
    shard_manifests = []
    for out in dirs:
        counts.update(json.loads((out / "comparison.json").read_text())["counts"])
        results.extend((out / "results.jsonl").read_text().splitlines())
        diagnostics.extend((out / "decisions.jsonl").read_text().splitlines())
        shard_manifests.append({
            "directory": out.name,
            "manifest": json.loads((out / "manifest.json").read_text()),
            "file_sha256": {
                f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                for f in sorted(out.glob("*.json*"))
            },
        })
    (args.out / "results.jsonl").write_text("\n".join(results) + "\n")
    (args.out / "decisions.jsonl").write_text("\n".join(diagnostics) + ("\n" if diagnostics else ""))
    write_json(args.out / "comparison.json", {"counts": dict(counts), "scenario_count": len(dirs)})
    write_json(args.out / "shards.json", shard_manifests)
    subprocess.run([
        sys.executable, str(ROOT / "scripts/evaluate.py"), "summarize", str(args.out / "results.jsonl"),
        "--baseline", "weighted_heuristic", "--challenger", "weighted_heuristic_v1",
        "--n-resamples", "2000", "--seed", "20260906", "--out", str(args.out),
    ], cwd=ROOT, check=True)
    print(f"全部 32 个根组已汇总：{args.out}", flush=True)


if __name__ == "__main__":
    main()
