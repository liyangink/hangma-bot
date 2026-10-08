"""R18 三财神飘候选的单次 GLM 5.3 受控作者调用。"""

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
for path in (
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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922')
PARENT = (
    _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/generations/P4/normalized-v2/candidate.py')
)
BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-bank-01-20260922')
DEVELOPMENT_SCORE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-bank-01-20260922/development-parent-score.json')
COUNTERFACTUAL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-wealth-gap-counterfactual-01-20260922/result.json')
TASK = "P3"
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
    """只传递开发聚合与反事实摘要；不读取或序列化 hidden。"""

    development = json.loads(DEVELOPMENT_SCORE.read_text(encoding="utf-8"))
    counterfactual = json.loads(COUNTERFACTUAL.read_text(encoding="utf-8"))
    dev = development["strata"]["three_wealth_piao"]
    cf = counterfactual["strata"]["three_wealth_piao"]
    if cf["status"] != "SUPPORTED_ALL_SHAPES":
        raise ValueError("三财神飘配对反事实没有逐手牌通过")
    parent = PARENT.read_text(encoding="utf-8")
    evidence = {
        "development": {
            "cases": dev["cases"],
            "current_parent_optimal": dev["parent_optimal"],
            "mean_parent_regret": dev["mean_parent_regret"],
            "parent_changed_from_v2": dev["changed"],
        },
        "paired_counterfactual": {
            "shapes": cf["shape_count"],
            "worlds_per_shape": 32,
            "pairs": cf["shape_count"] * 32,
            "directions": cf["directions"],
            "mean_of_shape_means": cf["mean_of_shape_means"],
            "nonpositive_pairs": cf["nonpositive_pairs"],
            "shape_mean_range": [96.0, 204.0],
        },
        "negative_directions": {
            "three_wealth_keep": counterfactual["strata"]["three_wealth_keep"],
            "four_wealth_keep": counterfactual["strata"]["four_wealth_keep"],
        },
    }
    fixed = """【冻结机制】
1. 父代是已通过隐藏题与完整桌安全预检的 P4。完整保留父代全部 V2 公式、四财神飘触发域、1.50 比率和未知回退；只新增一个三财神飘覆盖。
2. 新覆盖只在当前存在合法 hu、rule_state.baotou is True、准确财神数恰为 3 时考虑。目标只能是 discard:<wealth_god>；不得触碰非财神弃牌、三财神保财、四财神保财、杠、吃碰、过或无胡窗口。
3. 目标弃牌必须有 chain 家族 route_status="witnessed" 且 progress="advance"；value_coverage="complete"、value_issues 是已知空序列；所有使用路线必须 followup_discard is None、shanten == 0、support="conditional_witness"，结算、牌码和 remaining_estimate 全部完整、有限且不重复。
4. 复用父代公开未知池与 continue_proxy 定义。新覆盖的 required_ratio 固定为 1.75；只有 continue_proxy >= immediate_hu_value * 1.75 才把目标弃牌提升到父代最终 hu 分上方 1 分。
5. 任何事实不完整、比率不足或目标不唯一时，逐动作分数与父代完全相同。四财神仍只走父代 P4，不得被新覆盖改分。
6. 目标条目 trace 增加 three_wealth_piao_cf_supported/v1，记录触发、财神数、立即胡、条件代理、1.75 阈值、实际比率、改分与退化原因。继续声明代理不是完整牌局期望。
7. 不得按题号、手牌、摸牌、seed 或隐藏信息硬编码；不得宣称通过、增强或可发布。"""
    return "\n".join([
        "你是杭麻离线启发式作者。算法与阈值已由监督器按开发题和配对反事实冻结；",
        "本次任务只把冻结机制实现为完整短源码。不要使用工具，不要长篇分析。",
        "",
        fixed,
        "",
        "【作者可见证据（无题号、手牌、摸牌或 hidden）】",
        json.dumps(evidence, ensure_ascii=False, indent=2),
        "",
        "【输出格式】",
        "严格只输出：花括号内一句中文机制；一个 json 围栏，恰含 trigger/changed_branches/expected_direction/counterexample 四个非空短字符串；一个完整 python 围栏。",
        "Python 不得 import；只能有模块 docstring 和 score_actions(view)；在父代上最小修改并返回全部合法动作。",
        "",
        "【冻结 P4 父代完整源码】",
        "```python",
        parent.rstrip("\n"),
        "```",
        "",
        "现在直接交付完整结果。",
    ])


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("R18 P3 作者批已存在；拒绝覆盖")
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
    inputs = (PARENT, DEVELOPMENT_SCORE, COUNTERFACTUAL, _project_file(_PROJECT_ROOT, BANK / "manifest.json"))
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r18-p3-author-manifest/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_request_config": CONFIG,
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "inputs": {str(path): sha256(path) for path in inputs},
        "explicitly_excluded": [str(_project_file(_PROJECT_ROOT, BANK / "hidden.json"))],
        "fixed_ratio": 1.75,
        "hidden_evaluation_started": False,
        "effect_tables": 0,
        "release_eligible": False,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-p3-author-01",
        "trusted": True,
        "issued_by": "root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "用户授权 zai-coding-cn GLM 5.3 在 API 限额前由 root 持续调度；三财神飘方向已通过 192 对反事实",
        "max_initial_calls": 1,
        "max_repair_calls": 1,
        "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 16000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只交付冻结三财神飘覆盖；不得读取隐藏题、修改规则、确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({
        "status": "PREPARED", "task": TASK, "prompt_chars": len(prompt)
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
        raise SystemExit("P3 回复目录已存在；拒绝重复调用")
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
        kind="r18-p3-author",
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
        "schema": "r18-p3-author-call-usage/1",
        "task": TASK,
        "run_id": item.get("run_id"),
        "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"),
        "observed_config": item.get("request_config"),
        "usage": usage,
        "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("P3 作者通道或用量核验失败")
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
            ActionValueScorer("r18-p3-author", code)
        except Exception as exc:  # noqa: BLE001 - 保留作者实际装载错误
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
        "schema": "r18-p3-author-ingest/1",
        "parse_status": parsed.get("status"),
        "static_precheck": precheck.get("ok"),
        "load_error": load_error,
        "accepted_for_development_preflight": accepted,
        "code_sha256": sha256_text(code) if code else None,
        "hidden_evaluation_started": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "INGESTED", "accepted": accepted,
        "precheck": precheck.get("ok"), "load_error": load_error,
    }, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "ingest"))
    args = parser.parse_args()
    globals()[args.operation]()
