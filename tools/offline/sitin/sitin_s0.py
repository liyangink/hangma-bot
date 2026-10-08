#!/usr/bin/env python3
"""坐隐 1.5：S0 量具性质验证。

四项性质（README §6.4 重写版 / 审查 R-3）：
  P1 同输入可复现      —— 同一逻辑实验重复运行，结果逐字节一致
  P2 基线对自身        —— 同一实现、不同 policy_id，配对差恒为 0
  P3 等价候选为零      —— 行为等价的两个声明，配对差恒为 0
  P4 大差异可检出      —— 已知差异的对照能被分辨（本步用既有 probe 作方向性检查）

**P1/P2/P3 是"必须为真"的性质；P4 只作方向性检查，不设生死阈值。**
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
import importlib.util
import json
import math
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sitin_power", _project_file(_PROJECT_ROOT, _HERE / "sitin_power.py"))
sitin = importlib.util.module_from_spec(_spec)
sys.modules["sitin_power"] = sitin
assert _spec.loader is not None
_spec.loader.exec_module(sitin)


def _results(path: Path) -> list:
    return sitin._load_rows(path)


def _canonical(rows: list) -> list:
    """只保留与策略行为有关的字段。

    **必须剔除 match_id**：MatchSpec.match_id 是本地实验标识，含
    match_id_prefix，两次运行的该字段本就应当不同；把它纳入比较会把
    "能复现"误判成"不能复现"。

    **必须保留 scenario_id**：洗牌由 (scenario_id, seed, round_no) 派生
    （simulation/shuffle.py 的 deal-v1），scenario_id 是**决定牌山的输入**，
    不是纯标签。两次运行只有在 scenario_id 与 seed 都相同时才应有相同牌山。
    """

    keep = ("scenario_id", "pair_id", "policy_ids_by_seat", "seat_permutation",
            "scores_before", "scores_after", "status", "completed_hands",
            "source_kind", "evaluation_schema_version")
    out = []
    for row in rows:
        item = {k: row.get(k) for k in keep}
        gk = row.get("game_key")
        raw_id = gk.get("game_id") if isinstance(gk, dict) else gk
        # 去掉 match_id 前缀，只留 <scenario_id>:<perm>:<arm>
        item["position_key"] = (raw_id.split(":", 1)[1]
                                if isinstance(raw_id, str) and ":" in raw_id else raw_id)
        out.append(item)
    out.sort(key=lambda x: (str(x["scenario_id"]), str(x["pair_id"]), str(x["position_key"])))
    return out


def check_reproducible(run_a: Path, run_b: Path) -> dict:
    a, b = _canonical(_results(run_a)), _canonical(_results(run_b))
    return {"name": "P1 同输入可复现", "status": "PASS" if a == b else "FAIL", "pass": a == b,
            "detail": "两侧各 {0} 行；规范化后{1}一致".format(
                len(a), "" if a == b else "**不**")}


def check_self_pair(results: Path, baseline: str, challenger: str) -> dict:
    pairs, excl = sitin.collect_root_pairs(
        _results(results), baseline_policy_id=baseline, challenger_policy_id=challenger)
    if excl:
        return {"name": "P2 基线对自身", "status": "FAIL", "pass": False,
                "detail": "排除项：{0}".format(excl[:2])}
    deltas = {p.delta for p in pairs}
    return {"name": "P2 基线对自身", "status": "PASS" if deltas == {0} else "FAIL",
            "pass": deltas == {0},
            "detail": "{0} 个配对，差值集合 {1}".format(len(pairs), sorted(deltas))}


def check_equivalent_zero(results: Path, baseline: str, challenger: str) -> dict:
    """P3：两个声明装配**同一实现**时，配对差必须恒为 0。

    本步的 self 组即此构造（weighted_heuristic_v2 对 weighted_heuristic_v2，
    仅 policy_id 不同）。若不为 0，说明评分路径带有非确定源。
    """

    result = check_self_pair(results, baseline, challenger)
    result["name"] = "P3 等价候选为零"
    return result


# P4 的预登记判据：合成对照已知真实效应，要求区间把真实值包住且排除零。
# 这条判据在**看结果之前**写定，避免"事后挑一个能过的例子"。
P4_SYNTHETIC_EFFECT = 20.0
P4_SYNTHETIC_SD = 30.0
P4_SYNTHETIC_N = 32


def check_p4_statistical_path() -> dict:
    """P4 的子检查：**统计路径**本身是否正确（合成对照）。

    用合成数据（已知真实效应 20、根级 sd 30、32 根）检验
    "配对差均值 + 根组聚类区间"能否把真实值包住并排除零。

    **这只证明公式没错，不证明评测链能分辨真实效应**；因此它只是 P4 的子项，
    真正的 P4 由 check_p4_real_chain 在**真实评测链**上判定（见
    P4-PREREGISTRATION.md）。
    """

    import random
    rng = random.Random(20260915)
    samples = [P4_SYNTHETIC_EFFECT + rng.gauss(0.0, P4_SYNTHETIC_SD)
               for _ in range(P4_SYNTHETIC_N)]
    mean = sum(samples) / len(samples)
    var = sum((x - mean) ** 2 for x in samples) / (len(samples) - 1)
    sd = math.sqrt(var)
    half = 1.9599639845 * sd / math.sqrt(len(samples))
    lo, hi = mean - half, mean + half
    synthetic_ok = (lo <= P4_SYNTHETIC_EFFECT <= hi) and lo > 0
    # 负对照：真实效应为 0 时，同一判据**不应**声称检出
    zero = [rng.gauss(0.0, P4_SYNTHETIC_SD) for _ in range(P4_SYNTHETIC_N)]
    zmean = sum(zero) / len(zero)
    zsd = math.sqrt(sum((x - zmean) ** 2 for x in zero) / (len(zero) - 1))
    zhalf = 1.9599639845 * zsd / math.sqrt(len(zero))
    negative_control_ok = (zmean - zhalf) <= 0
    stat_ok = synthetic_ok and negative_control_ok
    return {
        "name": "P4 大差异可检出",
        "status": "NOT_EXECUTED",
        "statistical_path_ok": stat_ok,
        "detail": (
            "统计路径（合成对照）：真实效应 {0}、sd {1}、{2} 根 → 区间 [{3:.2f}, {4:.2f}]，"
            "包住真实值={5}、排除零={6}；零效应负对照未误报={7}。"
            "**真实评测链上的大差异对照尚未构造**，故本项不判 PASS。".format(
                P4_SYNTHETIC_EFFECT, P4_SYNTHETIC_SD, P4_SYNTHETIC_N,
                lo, hi, synthetic_ok, lo > 0, negative_control_ok)),
    }


# --- P4 真实评测链对照（判据见 P4-PREREGISTRATION.md，写于看结果之前） --------

P4_MIN_ROOTS_WORSE = 12      # R4：16 根中至少 12 根上对照更差
P4_BOOTSTRAP_RESAMPLES = 10000
P4_BOOTSTRAP_SEED = 2029


def _root_bootstrap_ci(values: Sequence[float], alpha: float = 0.05):
    """根组层聚类 Bootstrap 区间：**重采样单位是根组**（不是桌、不是换座）。

    与 evaluation_statistics.py 的口径一致；这里用百分位法，
    固定随机种子以保证可复现。
    """

    import random

    rng = random.Random(P4_BOOTSTRAP_SEED)
    n = len(values)
    means = []
    for _ in range(P4_BOOTSTRAP_RESAMPLES):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo = means[int((alpha / 2.0) * P4_BOOTSTRAP_RESAMPLES)]
    hi = means[min(int((1.0 - alpha / 2.0) * P4_BOOTSTRAP_RESAMPLES),
                   P4_BOOTSTRAP_RESAMPLES - 1)]
    return lo, hi


def check_p4_real_chain(results_path: Path, experiment_path: Path) -> dict:
    """P4 主项：**真实评测链**上的大差异对照必须被检出。

    对照的"更差"由构造保证（shanten_step 取负 ⇒ 奖励更高向听），方向事先确定；
    **幅度事先不知道、也没有独立测量**，故本项证明"大差异可检出"，
    不能反过来声称测准了某个已知幅度。

    四项预登记判据（R1 方向 / R2 检出 / R3 大而非仅可检出 / R4 尺度无关旁证）
    见 evidence/1.5-s0/P4-PREREGISTRATION.md，**在看结果之前写定**。
    """

    if not results_path.is_file():
        return {
            "name": "P4 大差异可检出",
            "status": "NOT_EXECUTED",
            "statistical_path_ok": check_p4_statistical_path()["statistical_path_ok"],
            "detail": "真实评测链对照的产物不存在：{0}；先跑 P4-experiment.json".format(
                results_path),
        }
    import json as _json

    experiment = _json.loads(experiment_path.read_text(encoding="utf-8"))
    baseline_id = experiment["baseline_policy"]["policy_id"]
    challenger_id = experiment["challenger_policy"]["policy_id"]
    # load_seed_map 返回 {"kind":…, "seeds":{scenario_id: seed}}——**取 ["seeds"]**。
    # 初版直接用了整个返回值，导致每根的 seed 静默变成 None（根组身份未校验），
    # 而口径看起来完全正常。这类"静默未知"正是 P1 踩过的坑，故此处显式守卫。
    loaded = sitin.load_seed_map(experiment_path)
    seed_map = loaded.get("seeds") if isinstance(loaded, dict) else None
    declared = len(_json.loads(experiment_path.read_text(encoding="utf-8")).get("seeds", ()) or ())
    if declared and not seed_map:
        raise ValueError(
            "实验文件声明了 {0} 个 seed，但解析出的映射为空——根组身份会静默未知，"
            "拒绝输出".format(declared))
    rows = _results(results_path)
    pairs, exclusions = sitin.collect_root_pairs(
        rows, baseline_policy_id=baseline_id, challenger_policy_id=challenger_id,
        seed_map=seed_map)
    per_root = sitin.aggregate_by_root(pairs)
    values = [item.mean_delta for item in per_root]
    n = len(values)
    if n < 2:
        return {"name": "P4 大差异可检出", "status": "FAIL",
                "detail": "根组数不足（{0}），无法判定".format(n)}
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    sd = math.sqrt(var)
    mde = sitin.minimum_detectable_effect(sd, n)
    lo, hi = _root_bootstrap_ci(values)
    half_width = (hi - lo) / 2.0
    worse = sum(1 for x in values if x < 0)

    r1 = mean < 0
    r2 = not (lo <= 0.0 <= hi)
    # R3a：预登记写法（|Δ| > 区间半宽）。
    # **已记录的设计缺陷**：该条件与 R2 实质等价——Bootstrap 百分位区间
    # 对称时，"区间不含 0" 与 "|Δ| > 半宽" 是同一件事，故它**不提供额外约束**。
    # 预登记里写的"（等价：|Δ| > MDE）"是**错的**：半宽用 z=1.96，
    # MDE 用 z=1.96+0.84=2.80，两者相差 1.43 倍。
    r3 = abs(mean) > half_width
    # R3b：事后补强的严格版本——效应必须超过本批 **MDE**（更严，只可能压低通过率，
    # 不会凭空制造 PASS）。见 P4-RESULTS.md §3。
    r3b = abs(mean) > mde
    r4 = worse >= P4_MIN_ROOTS_WORSE
    ok = r1 and r2 and r3 and r3b and r4
    # 方向若反了（对照被检出为更好），是评测链方向有系统性错误，必须停下排查。
    reversed_direction = mean > 0 and r2
    return {
        "name": "P4 大差异可检出",
        "status": "PASS" if ok else "FAIL",
        "criteria": {
            "R1 方向为负": {"pass": r1, "mean_delta": round(mean, 4)},
            "R2 区间排除零": {"pass": r2, "ci95": [round(lo, 4), round(hi, 4)]},
            "R3a 效应大于区间半宽（预登记；与 R2 实质等价）": {
                "pass": r3, "abs_mean": round(abs(mean), 4),
                "half_width": round(half_width, 4)},
            "R3b 效应大于 MDE（事后补强，更严格）": {
                "pass": r3b, "abs_mean": round(abs(mean), 4), "mde": round(mde, 4)},
            "R4 多数根组上更差": {"pass": r4, "roots_worse": worse, "roots_total": n,
                                    "required": P4_MIN_ROOTS_WORSE},
        },
        "roots": n,
        "exclusions": len(exclusions),
        "seeds_known": sorted({item.seed for item in per_root}) != [None],
        "reversed_direction_alarm": reversed_direction,
        "detail": (
            "真实评测链对照：{0} 根、排除 {1} 项；根级均值 {2:.4f}、sd {3:.4f}、"
            "Bootstrap 95% 区间 [{4:.4f}, {5:.4f}]、MDE {6:.4f}；"
            "对照在 {7}/{8} 个根组上更差。判据全部通过={9}"
            "（含事后补强的 |Δ|>MDE）。".format(
                n, len(exclusions), mean, sd, lo, hi, mde, worse, n, ok)),
    }


def main() -> int:
    root = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[3] / "runs/bench-sitin-1.5")
    base = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[3] / "runs/probe-scale-20260915")
    checks = [
        # 正确对照：相同 scenario_id 与 seed，只改 match_id_prefix。
        # 若拿不同 scenario_id 的两次运行比较，会因洗牌输入不同而必然不一致。
        check_reproducible(root / "rep1b/out/results.jsonl", root / "rep2b/out/results.jsonl"),
        check_self_pair(root / "self/out/results.jsonl", "v2_baseline", "v2_challenger"),
        check_equivalent_zero(root / "self/out/results.jsonl", "v2_baseline", "v2_challenger"),
    ]
    # ---- P4 大差异可检出 ----
    # 初版只判断 "sd_root is not None"，等于没检查：交替 −1/+1 的 16 根
    # （均值 0、sd≈1.03）也会通过。现改为三态，并要求**预先写明的判据**。
    checks.append(check_p4_real_chain(
        _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[3] / "runs/sitin-1.5-P4/out/results.jsonl"),
        _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[1] / "evidence/1.5-s0/P4-experiment.json"),
    ))

    print("坐隐 1.5 S0 量具性质验证")
    print()
    passed = sum(1 for x in checks if x["status"] == "PASS")
    not_executed = [x for x in checks if x["status"] == "NOT_EXECUTED"]
    failed = [x for x in checks if x["status"] == "FAIL"]
    for item in checks:
        print("[{0}] {1}\n      {2}".format(item["status"], item["name"], item["detail"]))
    print()
    ok = not failed and not not_executed
    if ok:
        print("结论：全项通过（{0} 项）".format(passed))
    elif failed:
        print("结论：**存在未通过项**（{0} 项失败，{1} 项未执行）".format(
            len(failed), len(not_executed)))
    else:
        print("结论：**尚不能判定通过**——{0} 项未执行：{1}".format(
            len(not_executed), "、".join(x["name"] for x in not_executed)))
    out = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[1] / "evidence/1.5-s0")
    out.mkdir(parents=True, exist_ok=True)
    (out / "s0.json").write_text(json.dumps(
        {"schema": "sitin-s0/2", "checks": checks, "all_pass": ok,
         "not_executed_count": len(not_executed), "failed_count": len(failed)},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

