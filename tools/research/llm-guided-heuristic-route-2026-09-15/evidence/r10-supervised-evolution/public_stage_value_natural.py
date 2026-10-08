"""R12-SV1：采集完整阶段的小局公开边界并检验低容量阶段价值模型。"""

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
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/public-stage-value-natural-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R12-PUBLIC-STAGE-VALUE-EVOLUTION-PLAN-2026-09-21.md')
REAUDIT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/R12-SV0-FAILURE-REAUDIT-2026-09-21.md')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEEDS = (2026092450, 2026092451, 2026092452, 2026092453)
MIXES = ("H", "M")
ROOTS = (1, 2)
SEATS = (0, 1, 2, 3)
TABLES_PER_STAGE = 2
MAX_TABLES = len(PANEL_SEEDS) * len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_STAGE
RIDGE_LAMBDAS = (0.1, 1.0, 10.0)
TREE_SPECS = ((1, 32), (2, 32), (3, 32))


def digest(value: bytes | Path) -> str:
    """返回字节或文件的 SHA-256。"""

    data = value.read_bytes() if isinstance(value, Path) else value
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    """返回规范 JSON 摘要，不把 Python 对象身份带入证据。"""

    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode())


def _put(features: dict[str, float], name: str, value: Any) -> None:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("非有限公开特征：" + name)
    features[name] = number


def _one_hot(features: dict[str, float], prefix: str, value: Any,
             choices: Iterable[Any]) -> None:
    matched = False
    for choice in choices:
        hit = value == choice
        _put(features, f"{prefix}.{choice}", hit)
        matched = matched or hit
    _put(features, prefix + ".other", not matched)


def _optional(features: dict[str, float], prefix: str, value: Any) -> None:
    known = value is not None
    _put(features, prefix + ".known", known)
    if known:
        _put(features, prefix + ".value", value)


def _tile(features: dict[str, float], prefix: str, value: Any) -> None:
    known = value is not None
    _put(features, prefix + ".known", known)
    if known:
        _put(features, f"{prefix}.tile.{CANONICAL_TILE_INDEX[value.code]}", 1)


def _relative(seat: int, focal: int) -> int:
    return (int(seat) - int(focal)) % 4


def public_features(request: Any) -> dict[str, float]:
    """把一个合法 `DecisionRequest` 投影成固定语义的玩家可见数值特征。

    来源根、面板种子、H/M 标签、场次标识、他家暗手、牌墙和终局标签不在
    本函数参数或返回值中。座位相关量统一转成相对焦点座位，避免绝对座位身份。
    """

    observation = request.observation
    competition = request.competition
    features: dict[str, float] = {}
    focal = int(observation.seat)
    _one_hot(features, "phase", observation.phase,
             ("draw", "response_peng", "response_chi"))
    _put(features, "progress.round_no", observation.round_no)
    _put(features, "progress.snapshot_seq", observation.snapshot_seq)
    _one_hot(features, "seat.dealer_relative",
             _relative(observation.dealer_seat, focal), range(4))
    _one_hot(features, "seat.turn_relative",
             _relative(observation.turn_seat, focal), range(4))
    for seat in observation.responding_seats:
        _put(features, f"responding.relative.{_relative(seat, focal)}", 1)

    hand_counts = Counter(CANONICAL_TILE_INDEX[tile.code] for tile in observation.my_hand)
    for tile_index in range(34):
        _put(features, f"hand.tile.{tile_index}", hand_counts.get(tile_index, 0))
    _tile(features, "drawn", observation.drawn_tile)
    for relative_seat in range(4):
        absolute = (focal + relative_seat) % 4
        _put(features, f"hand_count.relative.{relative_seat}", observation.hand_counts[absolute])
        _put(features, f"score.relative.{relative_seat}", observation.scores[absolute])
        river = observation.discards[absolute]
        _put(features, f"discard.relative.{relative_seat}.length", len(river))
        counts = Counter(CANONICAL_TILE_INDEX[tile.code] for tile in river)
        for tile_index, count in counts.items():
            _put(features, f"discard.relative.{relative_seat}.tile.{tile_index}", count)
        for offset, tile in enumerate(reversed(river[-2:]), start=1):
            _put(features, f"discard.relative.{relative_seat}.recent{offset}.tile."
                          f"{CANONICAL_TILE_INDEX[tile.code]}", 1)
        melds = observation.melds[absolute]
        _put(features, f"meld.relative.{relative_seat}.count", len(melds))
        for meld in melds:
            key = f"meld.relative.{relative_seat}.kind.{meld.kind}"
            _put(features, key, features.get(key, 0.0) + 1.0)
            for tile in meld.tiles:
                key = (f"meld.relative.{relative_seat}.tile."
                       f"{CANONICAL_TILE_INDEX[tile.code]}")
                _put(features, key, features.get(key, 0.0) + 1.0)

    _optional(features, "wall_remaining", observation.remaining_tile_count)
    _put(features, "rule.baotou", observation.rule_state.baotou)
    _put(features, "rule.chain_count", observation.rule_state.chain_count)
    _put(features, "rule.catch_play", observation.rule_state.catch_play)
    owner = observation.rule_state.catch_play_owner_seat
    _optional(features, "rule.catch_owner_relative",
              None if owner is None else _relative(owner, focal))
    _optional(features, "rule.chain_piao", observation.chain_piao)
    _optional(features, "rule.gang_draw", observation.gang_draw)
    _put(features, "history.complete", observation.history_complete)
    _put(features, "history.length", len(observation.public_history))
    for event in observation.public_history:
        relative = "none" if event.seat is None else str(_relative(event.seat, focal))
        key = f"history.kind.{event.kind}.seat.{relative}"
        _put(features, key, features.get(key, 0.0) + 1.0)
    for offset, event in enumerate(reversed(observation.public_history[-6:]), start=1):
        _put(features, f"history.recent{offset}.kind.{event.kind}", 1)
        if event.seat is not None:
            _put(features, f"history.recent{offset}.seat.{_relative(event.seat, focal)}", 1)

    _optional(features, "competition.stage_no", competition.stage_no)
    _optional(features, "competition.stage_total", competition.stage_total)
    _optional(features, "competition.participant_rank", competition.participant_rank)
    focal_entry = next((item for item in competition.ranking
                        if item.participant_id == natural.FOCAL_PARTICIPANT), None)
    if focal_entry is None:
        raise ValueError("阶段价值采集缺少焦点公开排名项")
    _put(features, "competition.focal_prior_score", focal_entry.total_score)
    _put(features, "competition.focal_prior_place_points", focal_entry.place_points)
    score_gaps = sorted(float(item.total_score - focal_entry.total_score)
                        for item in competition.ranking)
    place_gaps = sorted(float(item.place_points - focal_entry.place_points)
                        for item in competition.ranking)
    for index, value in enumerate(score_gaps):
        _put(features, f"competition.sorted_score_gap.{index}", value)
    for index, value in enumerate(place_gaps):
        _put(features, f"competition.sorted_place_gap.{index}", value)
    current_public = focal_entry.total_score + observation.scores[focal]
    _put(features, "public.current_stage_score", current_public)
    _put(features, "public.current_table_score", observation.scores[focal])

    candidates = request.rules.legal_candidates
    _put(features, "rules.candidate_count", len(candidates))
    shanten_values: list[int] = []
    support_values: list[int] = []
    for candidate in candidates:
        action_kind = type(candidate.action).__name__.lower()
        key = "rules.action." + action_kind
        _put(features, key, features.get(key, 0.0) + 1.0)
        facts = candidate.facts
        if facts is None:
            _put(features, "rules.facts.missing", features.get("rules.facts.missing", 0) + 1)
            continue
        _put(features, "rules.facts.kind." + facts.fact_kind.value,
             features.get("rules.facts.kind." + facts.fact_kind.value, 0) + 1)
        if facts.shanten_after is not None:
            shanten_values.append(int(facts.shanten_after))
        if facts.useful_tiles:
            support_values.append(sum(tile.remaining_estimate for tile in facts.useful_tiles))
        for family in facts.family_progress:
            key = f"rules.family.{family.family.value}.progress.{family.progress.value}"
            _put(features, key, features.get(key, 0.0) + 1.0)
            key = f"rules.family.{family.family.value}.status.{family.route_status.value}"
            _put(features, key, features.get(key, 0.0) + 1.0)
    _put(features, "rules.shanten.known_count", len(shanten_values))
    if shanten_values:
        _put(features, "rules.shanten.min", min(shanten_values))
        _put(features, "rules.shanten.max", max(shanten_values))
    _put(features, "rules.support.known_count", len(support_values))
    if support_values:
        _put(features, "rules.support.max", max(support_values))
        _put(features, "rules.support.mean", statistics.fmean(support_values))
    _put(features, "rules.completeness.complete", request.rules.completeness.value == "complete")
    _put(features, "rules.issue_count", len(request.rules.issues))
    return dict(sorted(features.items()))


def _stage_spec(panel_seed: int, mix: str, root: int, focal_seat: int) -> dict[str, Any]:
    return {"panel_seed": panel_seed, "mix": mix, "root_index": root,
            "focal_seat": focal_seat,
            "stage_id": f"s{panel_seed}:{mix}:r{root:02d}:seat{focal_seat}"}


def _all_specs() -> list[dict[str, Any]]:
    return [_stage_spec(seed, mix, root, seat) for seed in PANEL_SEEDS
            for mix in MIXES for root in ROOTS for seat in SEATS]


def _run_one(spec: Mapping[str, Any]) -> dict[str, Any]:
    """在独立进程执行一个稳定 V2 完整阶段并保留每小局首个焦点请求。"""

    contract = json.loads(CONTRACT.read_text())
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(spec["mix"]), root_index=int(spec["root_index"]),
        focal_seat=int(spec["focal_seat"]), panel_seed=int(spec["panel_seed"]))
    first_by_round: dict[tuple[str, int], dict[str, Any]] = {}

    def observe(request: Any) -> None:
        key = (str(request.observation.game_id), int(request.observation.round_no))
        if key in first_by_round:
            return
        encoded = decision_request_to_json(request)
        entry = next(item for item in request.competition.ranking
                     if item.participant_id == natural.FOCAL_PARTICIPANT)
        first_by_round[key] = {
            "table_id": request.observation.game_id,
            "round_no": int(request.observation.round_no),
            "phase": request.observation.phase,
            "snapshot_seq": int(request.observation.snapshot_seq),
            "request_sha256": canonical_digest(encoded),
            "features": public_features(request),
            "current_table_score": int(request.observation.scores[request.observation.seat]),
            "prior_stage_score": int(entry.total_score),
            "current_public_stage_score": int(
                entry.total_score + request.observation.scores[request.observation.seat]),
        }

    result = natural.run_arm_stage(
        arm="baseline", plans=plans, candidate_scorer=None,
        opponent_policies=contract["panel"]["opponent_scenarios"][str(spec["mix"])]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits(), decision_observer=observe)
    if result.get("status") != "complete" or not result.get("usable"):
        raise RuntimeError(f"阶段 {spec['stage_id']} 执行失败：{result.get('error')}")
    table_meta: dict[str, tuple[int, int]] = {}
    for table_no, (plan, table) in enumerate(zip(plans, result["tables"]), start=1):
        focal_physical_seat = tuple(plan.seats()).index(natural.FOCAL_PARTICIPANT)
        table_meta[str(plan.match_id)] = (
            table_no, int(table["scores_by_seat"][focal_physical_seat]))
    rows = []
    for key in sorted(first_by_round):
        row = first_by_round[key]
        table_no, final_table_score = table_meta[row["table_id"]]
        row.update({
            "stage_id": spec["stage_id"], "panel_seed": int(spec["panel_seed"]),
            "mix": str(spec["mix"]), "root_index": int(spec["root_index"]),
            "focal_seat": int(spec["focal_seat"]), "table_no": table_no,
            "final_table_score": final_table_score,
            "final_stage_score": int(result["focal_stage_score"]),
            "remaining_table_score": final_table_score - row["current_table_score"],
            "remaining_stage_score": int(result["focal_stage_score"])
                                     - row["current_public_stage_score"],
            "u_low": float(result["u_low"]), "u_high": float(result["u_high"]),
        })
        rows.append(row)
    return {
        "spec": dict(spec), "plans_sha256": canonical_digest([plan.to_json() for plan in plans]),
        "result": result, "rows": rows,
    }


def source_paths() -> list[Path]:
    return [Path(__file__), PLAN, REAUDIT, CONTRACT, Path(natural.__file__)]


def prepare() -> None:
    """冻结 64 个完整阶段、公开特征、模型族与继续门。"""

    if OUT.exists():
        raise SystemExit("SV1 输出目录已存在，拒绝覆盖")
    contract = json.loads(CONTRACT.read_text())
    if int(contract["group"]["tables_per_group"]) != TABLES_PER_STAGE:
        raise ValueError("SV1 预算只适用于每阶段两桌")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r12-sv1-natural-stage-value-01",
        accounts={"tables_full": MAX_TABLES}, issued_by="lead",
        issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    authorization.update({
        "issuance_basis": "用户取消旧目标并授权按文献复盘后的新目标持续推进",
        "scope": "稳定V2完整自然阶段语料；4新面板种子×H/M×2根×4座位×2桌；不确认不发布",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r12-public-stage-value-natural/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "failure_reaudit": str(REAUDIT), "failure_reaudit_sha256": digest(REAUDIT),
        "contract": str(CONTRACT), "contract_sha256": digest(CONTRACT),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seeds": list(PANEL_SEEDS), "mixes": list(MIXES),
        "root_indices": list(ROOTS), "focal_seats": list(SEATS),
        "stage_count": len(_all_specs()), "tables_per_stage": TABLES_PER_STAGE,
        "max_full_tables": MAX_TABLES, "workers": 4,
        "policy": natural.BASELINE_FOCAL_POLICY,
        "sampling_unit": "完整阶段来源；同一来源全部小局边界整组留出",
        "boundary": "每桌每小局焦点策略收到的第一个合法DecisionRequest；不是精确发牌时刻",
        "feature_policy": "仅PlayerObservation、CompetitionContext与HangmaRules公开事实；座位相对化；H/M和来源身份不入模",
        "targets": ["final_stage_score", "remaining_stage_score",
                    "final_table_score", "remaining_table_score", "u_interval"],
        "outer_validation": "leave-one-panel-seed-out；内层在其余panel_seed整组选择模型",
        "public_baseline": "当前公开阶段积分 + 训练折内按桌序和小局早中晚分层的平均剩余积分",
        "models": {"ridge_lambdas": list(RIDGE_LAMBDAS),
                   "tree_depth_min_leaf": [list(item) for item in TREE_SPECS]},
        "continue_gate": {
            "rmse_reduction_vs_public_baseline_min": 0.05,
            "pooled_spearman_min": 0.15,
            "layer_spearman_min": 0.0,
            "heldout_seeds_nonworse_min": 3,
            "coverage": "全部table_no 1..2 × round_no 1..8位置至少出现一次且机械审计全绿",
        },
        "model_math": "稀疏坐标下降岭回归（不惩罚截距）与受限平方误差树",
        "model_calls": 0,
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": MAX_TABLES}).save()
    print(json.dumps({"status": "PREPARED_R12_SV1", "stages": len(_all_specs()),
                      "max_tables": MAX_TABLES}, ensure_ascii=False))


def verify_inputs(manifest: Mapping[str, Any]) -> None:
    """执行前核对冻结脚本、计划、复盘和合同。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (("plan", "plan_sha256"),
                              ("failure_reaudit", "failure_reaudit_sha256"),
                              ("contract", "contract_sha256")):
        if digest(Path(str(manifest[path_key]))) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")
    if manifest["panel_seeds"] != list(PANEL_SEEDS) or manifest["root_indices"] != list(ROOTS):
        raise ValueError("SV1 来源清单漂移")


def collect() -> None:
    """并行执行全部阶段，失败同样计费且不覆盖部分证据。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "dataset.json")).exists():
        raise SystemExit("SV1 数据集已存在，拒绝覆盖")
    stage_dir = _project_file(_PROJECT_ROOT, OUT / "stages")
    stage_dir.mkdir(exist_ok=True)
    ledger = batch.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": MAX_TABLES})
    reservation = ledger.reserve(
        step_id="r12-sv1-natural-corpus", account="tables_full", amount=MAX_TABLES,
        note="64个稳定V2完整阶段，一次性冻结采集")
    completed: list[dict[str, Any]] = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_run_one, spec): spec for spec in _all_specs()}
            for future in concurrent.futures.as_completed(futures):
                spec = futures[future]
                record = future.result()
                completed.append(record)
                safe_name = str(spec["stage_id"]).replace(":", "-") + ".json"
                batch.write(stage_dir / safe_name, record)
                print(json.dumps({"completed": len(completed), "total": len(futures),
                                  "stage_id": spec["stage_id"],
                                  "boundaries": len(record["rows"])}, ensure_ascii=False),
                      flush=True)
    except Exception:
        ledger.settle(reservation, usage_unknown=True,
                      note="采集中断；按全部预留桌数保守计费")
        raise
    rows = [row for record in completed for row in record["rows"]]
    stages = [{"stage_id": record["spec"]["stage_id"],
               "panel_seed": record["spec"]["panel_seed"],
               "mix": record["spec"]["mix"],
               "root_index": record["spec"]["root_index"],
               "focal_seat": record["spec"]["focal_seat"],
               "plans_sha256": record["plans_sha256"],
               "focal_stage_score": record["result"]["focal_stage_score"],
               "u_low": record["result"]["u_low"], "u_high": record["result"]["u_high"],
               "boundary_count": len(record["rows"])}
              for record in completed]
    stages.sort(key=lambda item: item["stage_id"])
    rows.sort(key=lambda item: (item["stage_id"], item["table_no"], item["round_no"]))
    dataset = {"schema": "r12-public-stage-value-natural-dataset/1",
               "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
               "stage_count": len(stages), "table_count": MAX_TABLES,
               "boundary_count": len(rows), "stages": stages, "rows": rows}
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), dataset)
    ledger.settle(reservation, actual=MAX_TABLES,
                  note=f"完成{len(stages)}阶段、{len(rows)}个小局首决策边界")
    print(json.dumps({"status": "COLLECTED_R12_SV1", "stages": len(stages),
                      "tables": MAX_TABLES, "boundaries": len(rows)}, ensure_ascii=False))


def _bucket(round_no: int) -> str:
    return "early" if round_no <= 3 else ("middle" if round_no <= 6 else "late")


def _fit_public_baseline(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    residuals: dict[str, list[float]] = defaultdict(list)
    all_values = []
    for row in rows:
        value = float(row["final_stage_score"] - row["current_public_stage_score"])
        residuals[f"{row['table_no']}:{_bucket(int(row['round_no']))}"].append(value)
        all_values.append(value)
    model = {key: statistics.fmean(values) for key, values in residuals.items()}
    model["*"] = statistics.fmean(all_values)
    return model


def _public_predict(model: Mapping[str, float], row: Mapping[str, Any]) -> float:
    key = f"{row['table_no']}:{_bucket(int(row['round_no']))}"
    return float(row["current_public_stage_score"]) + float(model.get(key, model["*"]))


@dataclass
class Ridge:
    names: list[str]
    scales: dict[str, float]
    intercept: float
    coefficients: dict[str, float]
    lam: float

    def predict(self, features: Mapping[str, float]) -> float:
        return self.intercept + sum(
            self.coefficients.get(name, 0.0) * float(features.get(name, 0.0))
            / self.scales[name]
            for name in self.names if name in features
        )


def _fit_ridge(rows: Sequence[Mapping[str, Any]], lam: float) -> Ridge:
    """以循环坐标下降求解带不惩罚截距的标准岭回归。

    每列按训练折均方根缩放。稀疏列更新使用
    ``w_j=(x_j·(r+w_j x_j))/(x_j·x_j+lambda)``，随后重算截距；固定
    30 个正反交替扫描使结果与输入顺序无关且可复现。
    """

    names = sorted({name for row in rows for name in row["features"]})
    count = len(rows)
    columns: dict[str, list[tuple[int, float]]] = {}
    scales: dict[str, float] = {}
    for name in names:
        raw = [(index, float(row["features"].get(name, 0.0)))
               for index, row in enumerate(rows) if name in row["features"]]
        mean_square = sum(value * value for _, value in raw) / count
        scale = math.sqrt(mean_square) if mean_square > 1e-12 else 1.0
        scales[name] = scale
        columns[name] = [(index, value / scale) for index, value in raw]
    target = [float(row["remaining_stage_score"]) for row in rows]
    intercept = statistics.fmean(target)
    residual = [value - intercept for value in target]
    coefficients = {name: 0.0 for name in names}
    for scan in range(30):
        order = names if scan % 2 == 0 else reversed(names)
        for name in order:
            column = columns[name]
            old = coefficients[name]
            denominator = sum(value * value for _, value in column) + float(lam)
            numerator = sum(value * (residual[index] + old * value)
                            for index, value in column)
            new = numerator / denominator if denominator else 0.0
            delta = new - old
            if delta:
                for index, value in column:
                    residual[index] -= delta * value
                coefficients[name] = new
        shift = statistics.fmean(residual)
        intercept += shift
        residual = [value - shift for value in residual]
    coefficients = {name: value for name, value in coefficients.items()
                    if abs(value) > 1e-12}
    return Ridge(names, scales, intercept, coefficients, lam)


@dataclass
class TreeNode:
    value: float
    feature: str | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None

    def predict(self, features: Mapping[str, float]) -> float:
        if self.feature is None:
            return self.value
        child = self.left if features.get(self.feature, 0.0) <= float(self.threshold) else self.right
        assert child is not None
        return child.predict(features)


def _fit_tree(rows: Sequence[Mapping[str, Any]], depth: int, min_leaf: int) -> TreeNode:
    names = sorted({name for row in rows for name in row["features"]})
    labels = [float(row["remaining_stage_score"]) for row in rows]

    def build(indices: list[int], level: int) -> TreeNode:
        values = [labels[index] for index in indices]
        node = TreeNode(statistics.fmean(values))
        if level >= depth or len(indices) < 2 * min_leaf:
            return node
        best: tuple[float, str, float, list[int], list[int]] | None = None
        for name in names:
            ordered = sorted((float(rows[index]["features"].get(name, 0.0)), index)
                             for index in indices)
            left_sum = left_sq = 0.0
            total_sum = sum(labels[index] for index in indices)
            total_sq = sum(labels[index] ** 2 for index in indices)
            for position in range(len(ordered) - 1):
                value, index = ordered[position]
                label = labels[index]
                left_sum += label
                left_sq += label * label
                left_count = position + 1
                right_count = len(ordered) - left_count
                next_value = ordered[position + 1][0]
                if left_count < min_leaf or right_count < min_leaf or value == next_value:
                    continue
                right_sum = total_sum - left_sum
                right_sq = total_sq - left_sq
                loss = (left_sq - left_sum * left_sum / left_count
                        + right_sq - right_sum * right_sum / right_count)
                threshold = (value + next_value) / 2.0
                if best is None or (loss, name, threshold) < best[:3]:
                    best = (loss, name, threshold,
                            [item for _, item in ordered[:left_count]],
                            [item for _, item in ordered[left_count:]])
        if best is None:
            return node
        _, node.feature, node.threshold, left, right = best
        node.left, node.right = build(left, level + 1), build(right, level + 1)
        return node

    return build(list(range(len(rows))), 0)


def _specs() -> list[tuple[str, Any]]:
    result = [(f"ridge-l{lam}", ("ridge", lam)) for lam in RIDGE_LAMBDAS]
    result.extend((f"tree-d{depth}-l{leaf}", ("tree", depth, leaf))
                  for depth, leaf in TREE_SPECS)
    return result


def _fit(spec: tuple[Any, ...], rows: Sequence[Mapping[str, Any]]) -> Any:
    return (_fit_ridge(rows, float(spec[1])) if spec[0] == "ridge"
            else _fit_tree(rows, int(spec[1]), int(spec[2])))


def _predict(model: Any, row: Mapping[str, Any]) -> float:
    return float(row["current_public_stage_score"]) + float(model.predict(row["features"]))


def _rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    return math.sqrt(statistics.fmean((a - p) ** 2 for a, p in zip(actual, predicted)))


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        rank = (start + end + 2) / 2.0
        for offset in range(start, end + 1):
            ranks[order[offset]] = rank
        start = end + 1
    return ranks


def _spearman(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if len(actual) < 2:
        return 0.0
    left, right = _ranks(actual), _ranks(predicted)
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left)
                            * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else 0.0


def _select_spec(train: Sequence[Mapping[str, Any]], seeds: Sequence[int]) -> tuple[str, tuple[Any, ...], list[dict]]:
    scores = []
    for name, spec in _specs():
        actual_all, predicted_all, baseline_all = [], [], []
        for held in seeds:
            inner_train = [row for row in train if row["panel_seed"] != held]
            inner_test = [row for row in train if row["panel_seed"] == held]
            model = _fit(spec, inner_train)
            baseline = _fit_public_baseline(inner_train)
            actual_all.extend(float(row["final_stage_score"]) for row in inner_test)
            predicted_all.extend(_predict(model, row) for row in inner_test)
            baseline_all.extend(_public_predict(baseline, row) for row in inner_test)
        rmse = _rmse(actual_all, predicted_all)
        base = _rmse(actual_all, baseline_all)
        scores.append({"model_spec": name, "inner_rmse": rmse,
                       "inner_public_baseline_rmse": base,
                       "inner_rmse_ratio": rmse / base if base else math.inf,
                       "spec": spec})
    scores.sort(key=lambda item: (item["inner_rmse_ratio"], item["model_spec"]))
    winner = scores[0]
    report = [{key: value for key, value in item.items() if key != "spec"} for item in scores]
    return str(winner["model_spec"]), tuple(winner["spec"]), report


def evaluate() -> None:
    """整组嵌套留出，裁定完整自然语料中是否存在可复用阶段价值信号。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("SV1 结果已存在，拒绝覆盖")
    dataset = json.loads((_project_file(_PROJECT_ROOT, OUT / "dataset.json")).read_text())
    if dataset["stage_count"] != len(_all_specs()) or dataset["table_count"] != MAX_TABLES:
        raise ValueError("SV1 数据集阶段/桌数不完整")
    rows = dataset["rows"]
    predictions = []
    folds = []
    for held in PANEL_SEEDS:
        train = [row for row in rows if row["panel_seed"] != held]
        test = [row for row in rows if row["panel_seed"] == held]
        name, spec, inner = _select_spec(train, [seed for seed in PANEL_SEEDS if seed != held])
        model = _fit(spec, train)
        baseline = _fit_public_baseline(train)
        actual = [float(row["final_stage_score"]) for row in test]
        predicted = [_predict(model, row) for row in test]
        baseline_pred = [_public_predict(baseline, row) for row in test]
        for row, value, public in zip(test, predicted, baseline_pred):
            predictions.append({"stage_id": row["stage_id"], "panel_seed": held,
                                "mix": row["mix"], "table_no": row["table_no"],
                                "round_no": row["round_no"], "actual": row["final_stage_score"],
                                "predicted": value, "public_baseline": public,
                                "model_spec": name})
        fold_rmse, fold_base = _rmse(actual, predicted), _rmse(actual, baseline_pred)
        folds.append({"held_panel_seed": held, "selected_model_spec": name,
                      "inner_selection": inner, "test_count": len(test),
                      "test_rmse": fold_rmse, "test_public_baseline_rmse": fold_base,
                      "test_rmse_ratio": fold_rmse / fold_base if fold_base else math.inf,
                      "test_spearman": _spearman(actual, predicted),
                      "nonworse_than_public_baseline": fold_rmse <= fold_base})
    actual = [float(row["actual"]) for row in predictions]
    predicted = [float(row["predicted"]) for row in predictions]
    public = [float(row["public_baseline"]) for row in predictions]
    rmse, public_rmse = _rmse(actual, predicted), _rmse(actual, public)
    layers: dict[str, dict[str, float | int]] = {}
    layer_defs = {
        "mix:H": lambda row: row["mix"] == "H", "mix:M": lambda row: row["mix"] == "M",
        "table:1": lambda row: row["table_no"] == 1, "table:2": lambda row: row["table_no"] == 2,
        "progress:early": lambda row: _bucket(int(row["round_no"])) == "early",
        "progress:middle": lambda row: _bucket(int(row["round_no"])) == "middle",
        "progress:late": lambda row: _bucket(int(row["round_no"])) == "late",
    }
    for name, predicate in layer_defs.items():
        selected = [row for row in predictions if predicate(row)]
        layers[name] = {"count": len(selected),
                        "spearman": _spearman([float(row["actual"]) for row in selected],
                                              [float(row["predicted"]) for row in selected])}
    positions = sorted({(int(row["table_no"]), int(row["round_no"])) for row in rows})
    expected_positions = [(table, round_no) for table in (1, 2) for round_no in range(1, 9)]
    gates = manifest["continue_gate"]
    checks = {
        "rmse_reduction": 1.0 - rmse / public_rmse >= gates["rmse_reduction_vs_public_baseline_min"],
        "pooled_spearman": _spearman(actual, predicted) >= gates["pooled_spearman_min"],
        "all_layer_spearman_nonnegative": all(float(item["spearman"]) >= gates["layer_spearman_min"]
                                                for item in layers.values()),
        "heldout_seeds_nonworse": sum(bool(fold["nonworse_than_public_baseline"])
                                       for fold in folds) >= gates["heldout_seeds_nonworse_min"],
        "coverage": positions == expected_positions,
        "all_stages_complete": dataset["stage_count"] == len(_all_specs()),
    }
    passed = all(checks.values())
    result = {
        "schema": "r12-public-stage-value-natural-result/1",
        "status": ("PASS_R12_SV1_PUBLIC_STAGE_VALUE_FEASIBILITY" if passed
                   else "CLOSE_R12_SV1_NO_GENERALIZABLE_STAGE_VALUE_SIGNAL"),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "counts": {"stages": dataset["stage_count"], "tables": dataset["table_count"],
                   "boundaries": dataset["boundary_count"]},
        "coverage_positions": [list(item) for item in positions],
        "folds": folds,
        "pooled": {"rmse": rmse, "public_baseline_rmse": public_rmse,
                   "rmse_reduction": 1.0 - rmse / public_rmse,
                   "spearman": _spearman(actual, predicted),
                   "heldout_seeds_nonworse": sum(bool(fold["nonworse_than_public_baseline"])
                                                  for fold in folds)},
        "layers": layers, "gate_checks": checks, "predictions": predictions,
        "strength_claim": False, "confirmation_eligible": False,
        "release_eligible": False,
        "next": ("验证短截断价值能否提高候选预算分配效率；仍以完整阶段选择候选"
                 if passed else "按R12§6再次复盘文献、标签方差和杭麻赛事目标；不得在同批加深模型"),
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": result["status"], "pooled": result["pooled"],
                      "gate_checks": checks}, ensure_ascii=False))


def smoke() -> None:
    """执行一个两桌阶段，验证采集器形状；结果只打印，不写冻结目录。"""

    record = _run_one(_stage_spec(PANEL_SEEDS[0], "H", 99, 0))
    positions = sorted({(row["table_no"], row["round_no"]) for row in record["rows"]})
    print(json.dumps({"status": record["result"]["status"],
                      "tables": len(record["result"]["tables"]),
                      "boundaries": len(record["rows"]), "positions": positions},
                     ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("smoke", "prepare", "collect", "evaluate"))
    args = parser.parse_args()
    {"smoke": smoke, "prepare": prepare, "collect": collect, "evaluate": evaluate}[args.command]()


if __name__ == "__main__":
    main()
