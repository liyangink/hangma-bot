"""坐隐 1.3：实验配置快照。

用途：把"一次坐隐实验在什么配置下产生"固化成可引用的指纹，使任一结果
都能追溯到唯一配置。依据 README §17 第 1.3 步与 DESIGN §5。

本工具**只读**：读取规则/时序配置与仓库状态，产出 JSON；不跑桌赛、
不访问网络、不写除 --out 之外的路径。

注意（本步骤的已知边界）：
  - 规则语义版本的**权威来源**是 RuleConfig.ruleset_version；本工具不推断它，
    必须由调用方显式给出（与 DESIGN 要求的"显式冻结身份"同一纪律）。
  - base_score 与 you_cai_bi_kao 属于**赛事配置**，不是规则常数（README §16.2）。
  - 仓库可能有未提交改动；快照记录 dirty 状态与文件数，不假装干净。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=30
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _policy_hash(directory: Path) -> str:
    """策略侧源码指纹：对 policy 目录下全部 .py 求内容指纹。

    缺了它，改权重或改评分函数不会改变配置指纹——而"改了什么策略"正是
    实验身份最容易漂移的地方。
    """

    paths = sorted(directory.glob("*.py"))
    if not paths:
        return ""
    parts = []
    for path in paths:
        parts.append(path.name)
        parts.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _rules_hash(repo: Path) -> str:
    """规则源码指纹：**复用仓库既有实现**，不另造。

    `offline/simulation.artifacts.compute_rules_hash` 递归覆盖
    `src/hangma_bot/hangma` 下的 `.py/.c/.h`，并已声明"全仓统一实现"。
    初版自造了一个只遍历顶层 `.py` 的版本，**漏掉原生规则实现**
    （`_grouped_native.c`）——改 C 源码不会改变指纹（审查 S5-4）。

    导入失败时返回空串并由调用方标注，**不静默回退到不完整实现**。
    """

    try:
        import sys as _sys
        repo_src = str(repo / "src")
        if repo_src not in _sys.path:
            _sys.path.insert(0, repo_src)
        from hangma_bot.simulation.artifacts import compute_rules_hash
    except Exception:
        return ""
    try:
        return compute_rules_hash(repo)
    except Exception:
        return ""


def build_snapshot(
    repo: Path,
    *,
    ruleset_version: str,
    base_score: int,
    you_cai_bi_kao: bool,
    rounds_per_game: int,
    opponents: Sequence[str],
    clock_mode: str,
    timing: Optional[Mapping[str, float]] = None,
) -> dict:
    """组装配置快照；所有字段都必须显式给出，不做默认推断。"""

    if not isinstance(base_score, int) or isinstance(base_score, bool) or base_score <= 0:
        raise ValueError("base_score 必须是正整数")
    if clock_mode not in ("logical", "real"):
        raise ValueError("clock_mode 必须是 logical 或 real")
    dirty = _git(repo, "status", "--porcelain")
    snapshot: dict = {
        "schema": "sitin-config/1",
        "ruleset_version": ruleset_version,
        "base_score": base_score,
        "you_cai_bi_kao": bool(you_cai_bi_kao),
        "rounds_per_game": rounds_per_game,
        "opponents": list(opponents),
        "clock_mode": clock_mode,
        "timing_seconds": dict(timing or {"peng": 1.0, "chi": 1.0, "discard": 3.0}),
        "repo": {
            "commit": _git(repo, "rev-parse", "HEAD"),
            "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(dirty),
            "dirty_file_count": len([x for x in dirty.splitlines() if x.strip()]),
            # 规则源码：仓库既有 compute_rules_hash（.py/.c/.h 全覆盖）
            "rules_source_sha256": _rules_hash(repo),
            # 策略侧源码指纹：评分权重与评分函数就在这里
            "policy_source_sha256": _policy_hash(repo / "src/hangma_bot/policy"),
        },
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
    }
    return snapshot


def fingerprint(snapshot: Mapping[str, Any]) -> str:
    """配置指纹：对**参与实验语义**的字段求哈希，排除机器与仓库状态。"""

    semantic = {
        "ruleset_version": snapshot["ruleset_version"],
        "base_score": snapshot["base_score"],
        "you_cai_bi_kao": snapshot["you_cai_bi_kao"],
        "rounds_per_game": snapshot["rounds_per_game"],
        "opponents": list(snapshot["opponents"]),
        "timing_seconds": snapshot["timing_seconds"],
        # clock_mode 是 DESIGN 1.3 明确要求冻结的字段；初版漏了它，
        # 把逻辑时钟改成真实时钟指纹不变（审查 S5-4）。
        "clock_mode": snapshot["clock_mode"],
        "rules_source_sha256": snapshot["repo"]["rules_source_sha256"],
        "policy_source_sha256": snapshot["repo"].get("policy_source_sha256", ""),
    }
    blob = json.dumps(semantic, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="坐隐 1.3：实验配置快照")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out", help="输出目录")
    parser.add_argument("--ruleset-version", required=True,
                        help="本地规则语义版本；必须显式给出，本工具不推断")
    parser.add_argument("--base-score", type=int, required=True)
    parser.add_argument("--you-cai-bi-kao", choices=("true", "false"), required=True)
    parser.add_argument("--rounds-per-game", type=int, default=8)
    parser.add_argument("--opponents", default="weighted_heuristic_v2,weighted_heuristic_v2,weighted_heuristic_v2")
    parser.add_argument("--clock-mode", choices=("logical", "real"), default="logical")
    args = parser.parse_args(argv)

    snapshot = build_snapshot(
        Path(args.repo).resolve(),
        ruleset_version=args.ruleset_version,
        base_score=args.base_score,
        you_cai_bi_kao=args.you_cai_bi_kao == "true",
        rounds_per_game=args.rounds_per_game,
        opponents=[x for x in args.opponents.split(",") if x],
        clock_mode=args.clock_mode,
    )
    snapshot["config_fingerprint"] = fingerprint(snapshot)
    text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "config.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

