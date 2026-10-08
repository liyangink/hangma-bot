"""R18 P65：立即胡与非财神建爆头候选的单次 GLM 5.3 受控作者调用。"""

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
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROOT = _PROJECT_ROOT
for path in (
    _project_file(_PROJECT_ROOT, ROOT / "src"),
    _project_file(_PROJECT_ROOT, ROUTE / "tools"),
    _project_file(_PROJECT_ROOT, ADMISSION / "p25-headless"),
    _project_file(_PROJECT_ROOT, ADMISSION / "p25-dev-cards"),
    HERE,
):
    sys.path.insert(0, str(path))

import criterion  # noqa: E402
import dispatch_headless as dispatch  # noqa: E402
import sitin_generate as gen  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p45-integrated-positive-parent-01-20260922/candidate.py')
TEACHER = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p64-nonwhite-baotou-development-teacher-01-20260923/result.json')
EXPOSURE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p63-nonwhite-baotou-natural-exposure-01-20260923/result.json')
TASK = "P65"
CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "low",
    "maxTokens": 16000,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build_prompt() -> str:
    """只传开发聚合与冻结机制；不读取或序列化 16 个复验目标。"""

    teacher = json.loads(TEACHER.read_text(encoding="utf-8"))
    exposure = json.loads(EXPOSURE.read_text(encoding="utf-8"))
    if teacher.get("decision") != "OPEN_P65_LIMITED_AUTHOR":
        raise ValueError("P64 未开放 P65 作者调用")
    if teacher.get("replication_labels_opened") is not False:
        raise ValueError("P64 复验标签必须保持封存")
    if exposure.get("replication_labels_opened") is not False:
        raise ValueError("P63 复验标签必须保持封存")
    aggregate = teacher["aggregate"]
    evidence = {
        "natural_exposure_tables": exposure["tables"],
        "natural_independent_roots": exposure["independent_roots"],
        "natural_raw_eligible_windows": exposure["raw_eligible_windows"],
        "development_natural_roots": teacher["development_states"],
        "public_consistent_world_pairs": teacher["rollouts"],
        "fit_mean_baotou_minus_hu": aggregate[
            "fit_mean_baotou_minus_hu_current_round_settlement"
        ],
        "fit_bootstrap_95": aggregate["fit_bootstrap_95"],
        "recheck_mean_baotou_minus_hu": aggregate[
            "recheck_mean_baotou_minus_hu_current_round_settlement"
        ],
        "recheck_bootstrap_95": aggregate["recheck_bootstrap_95"],
        "recheck_positive_zero_negative_states": [
            aggregate["recheck_positive_states"],
            aggregate["recheck_zero_states"],
            aggregate["recheck_negative_states"],
        ],
        "minimum_leave_one_root_out_mean": aggregate[
            "minimum_recheck_leave_one_source_root_out_mean"
        ],
        "recheck_mean_by_mix": aggregate["recheck_mean_by_mix"],
        "mechanical_ok": teacher["mechanical_ok"],
    }
    fixed = """【冻结机制】
1. 父代是完整 P47。保留其全部 V2 公式、三/四财神飘、补杠严格支配、庄家起手七对、双财神飘保爆头、未知回退和 trace；本次只新增一个“立即胡 vs 非财神建爆头”覆盖。
2. 先完整计算父代最终 entries。按 score 降序、action_key 升序确定父代首选；只有父代首选恰为 hu 时才允许新覆盖改分。
3. 若父代任一 entry 的 trace 中 `r18_opportunity_overlay`、`r18_gang_dominance_overlay`、`r18_seven_pairs_value_overlay`、`two_wealth_piao_keeps_baotou_cf` 任一映射显式 `triggered is True`，本覆盖必须整批回退，不与既有专项争夺。
4. hu 动作必须唯一且带完整 `immediate_settlement.fan`。目标只允许非财神 discard，并同时满足：`baotou_after is True`、`shanten_after == 0`、`value_coverage == "complete"`、routes 非空；每条 route 的 `conditions.baotou is True`、`conditional_settlement.fan` 严格大于当前 hu fan、`conditional_settlement.self_delta` 为有限数，且 useful_tiles 中每个 `remaining_estimate` 是已知非负有限数。任一所需字段未知或矛盾时整批回退父代，不填零。
5. 对每个合格动作精确计算 `score_capacity = Σ remaining_estimate × self_delta` 与 `support_remaining = Σ remaining_estimate`。按 score_capacity 降序、support_remaining 降序、最小条件 fan 降序、action_key 升序选唯一目标。容量只是确定性选择键，不宣称概率或期望收益。
6. 全部条件满足时，只把目标动作提高到父代 hu 最终分数上方 1.0；其他动作最终分数逐点不变。任何条件不成立时，全部最终 entries 与父代逐点相同。
7. 所有 entry 的 trace 增加 `hu_vs_nonwealth_baotou_cf` 映射；至少记录 version=`hu_vs_nonwealth_baotou_cf/v1`、triggered、parent_top_action、hu_fan、target_action、score_capacity、support_remaining、min_route_fan、score_delta 和 degrade_reason；不得删除父代已有 trace。
8. 不得按题号、牌山、座位、手牌字符串、seed 或隐藏信息硬编码；不得修改规则、合同、执行器或评测；不得宣称复验通过、总体增强或可发布。"""
    parent = PARENT.read_text(encoding="utf-8")
    return "\n".join([
        "你是杭麻离线启发式作者。监督器已经用自然可达状态和配对反事实冻结机制；",
        "本次只把冻结机制实现为完整受限源码。不要使用工具，不要长篇分析。",
        "",
        fixed,
        "",
        "【作者可见开发证据；没有复验目标、题号、手牌或牌山】",
        json.dumps(evidence, ensure_ascii=False, indent=2),
        "",
        "【输出格式】",
        "严格只输出：花括号内一句中文机制；一个 json 围栏，恰含 trigger/changed_branches/expected_direction/counterexample 四个非空短字符串；一个完整 python 围栏。",
        "Python 不得 import；只能有模块 docstring 和 score_actions(view)；在父代上最小修改并返回全部合法动作。",
        "",
        "【冻结 P47 父代完整源码】",
        "```python",
        parent.rstrip("\n"),
        "```",
        "",
        "现在直接交付完整结果。",
    ])


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("R18 P65 作者批已存在；拒绝覆盖")
    prompt = build_prompt()
    prompt_dir = _project_file(_PROJECT_ROOT, BATCH / "prompts" / TASK)
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    settings = """llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 16000

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: low
"""
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    inputs = (PARENT, TEACHER, EXPOSURE)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r18-p65-nonwhite-baotou-author-manifest/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_request_config": CONFIG,
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "inputs": {str(path): sha256(path) for path in inputs},
        "explicitly_excluded": [
            str(_project_file(_PROJECT_ROOT, HERE / "r18-p64-nonwhite-baotou-development-teacher-01-20260923/targets.json"))
        ],
        "replication_evaluation_started": False,
        "effect_tables": 0,
        "release_eligible": False,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-p65-nonwhite-baotou-author-01",
        "trusted": True,
        "issued_by": "root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权API限额前持续调度zai-coding-cn GLM 5.3；"
            "非财神建爆头方向已通过60自然根暴露和16根×32共同隐藏世界开发门"
        ),
        "max_initial_calls": 1,
        "max_repair_calls": 1,
        "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 16000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只交付冻结非财神建爆头覆盖；不得读取复验目标、修改规则、确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({
        "status": "PREPARED", "task": TASK, "prompt_chars": len(prompt),
    }, ensure_ascii=False))


def verify() -> str:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    for path, expected in manifest["inputs"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError("作者输入漂移：" + path)
    prompt = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / TASK / "prompt.txt")).read_text(encoding="utf-8")
    if sha256_text(prompt) != manifest["prompt_sha256"]:
        raise RuntimeError("作者提示词漂移")
    return prompt


def call() -> None:
    verify()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies")).exists():
        raise SystemExit("P65 回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(CONFIG)
    report = dispatch.dispatch(
        BATCH,
        [TASK],
        _project_file(_PROJECT_ROOT, BATCH / "replies"),
        _project_file(_PROJECT_ROOT, BATCH / "plan.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")),
        timeout_s=1200,
        concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"),
        kind="r18-p65-nonwhite-baotou-author",
    )
    item = report["calls"][0]
    usage = criterion.usage_of(item.get("run_id"))
    values = usage.get("usage") or {}
    clean = (
        item.get("exit_code") == 0
        and item.get("protocol_ok") is True
        and item.get("request_config") == CONFIG
        and usage.get("source_status") == "OK"
        and isinstance(values.get("inputTokens"), int)
        and isinstance(values.get("outputTokens"), int)
        and values["inputTokens"] <= 65536
        and values["outputTokens"] <= 16000
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage.json"), {
        "schema": "r18-p65-nonwhite-baotou-author-call-usage/1",
        "task": TASK,
        "run_id": item.get("run_id"),
        "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"),
        "observed_config": item.get("request_config"),
        "usage": usage,
        "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("P65 作者通道或用量核验失败")
    print(json.dumps({"status": "CALLED", "usage": values}, ensure_ascii=False))


def ingest() -> None:
    verify()
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage.json")).read_text(encoding="utf-8"))
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies" / (TASK + ".txt"))).read_text(encoding="utf-8")
    parsed = gen.parse_action_value_reply(raw)
    code = parsed.get("code") or ""
    precheck = gen.precheck_action_value_candidate(code) if code else {
        "ok": False, "problems": ["没有源码"],
    }
    load_error = None
    if code and precheck.get("ok") is True:
        try:
            ActionValueScorer("r18-p65-author", code)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    accepted = (
        usage.get("ingestable_channel") is True
        and parsed.get("status") == "ok"
        and precheck.get("ok") is True
        and load_error is None
    )
    target = _project_file(_PROJECT_ROOT, BATCH / "generation")
    target.mkdir(parents=True, exist_ok=True)
    (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
    if code:
        (target / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
    write_json(target / "parsed.json", {
        key: value for key, value in parsed.items() if key != "code"
    } | ({"code_sha256": sha256_text(code)} if code else {}))
    write_json(target / "precheck.json", precheck)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r18-p65-nonwhite-baotou-author-ingest/1",
        "parse_status": parsed.get("status"),
        "static_precheck": precheck.get("ok"),
        "load_error": load_error,
        "accepted_for_development_preflight": accepted,
        "code_sha256": sha256_text(code) if code else None,
        "replication_evaluation_started": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "INGESTED", "accepted": accepted,
        "precheck": precheck.get("ok"), "load_error": load_error,
    }, ensure_ascii=False))



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "call", "ingest"))
    command = parser.parse_args().command
    globals()[command]()


if __name__ == "__main__":
    main()
