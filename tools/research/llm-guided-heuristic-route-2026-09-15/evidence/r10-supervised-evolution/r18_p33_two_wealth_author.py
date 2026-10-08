"""R18 P33：双财神飘后保持爆头候选的单次 GLM 5.3 受控作者调用。"""

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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p33-two-wealth-author-01-20260922')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
TEACHER = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p32-two-wealth-baotou-rare-teacher-01-20260922/result.json')
PROTOCOL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R18-P32-RARE-OPPORTUNITY-EVALUATION-PROTOCOL-2026-09-22.md')
TASK = "P33"
CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "low",
    "maxTokens": 16000,
}
REPAIR_CONFIG = dict(CONFIG)


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
    """只传开发聚合与冻结机制；不读取或序列化 9 个隐藏目标。"""

    teacher = json.loads(TEACHER.read_text(encoding="utf-8"))
    if teacher.get("decision") != "OPEN_P33_LIMITED_AUTHOR":
        raise ValueError("P32 未开放 P33 作者调用")
    if teacher.get("hidden_labels_opened") is not False:
        raise ValueError("P32 隐藏标签必须保持封存")
    aggregate = teacher["aggregate"]
    evidence = {
        "development_natural_roots": teacher["development_states"],
        "public_consistent_world_pairs": teacher["rollouts"],
        "fit_mean_piao_minus_hu": aggregate[
            "fit_mean_piao_minus_hu_current_round_settlement"
        ],
        "fit_bootstrap_95": aggregate["fit_bootstrap_95"],
        "recheck_mean_piao_minus_hu": aggregate[
            "recheck_mean_piao_minus_hu_current_round_settlement"
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
        "mechanical_ok": teacher["mechanical_ok"],
    }
    fixed = """【冻结机制】
1. 父代是完整 P5。保留其全部 V2 公式、三/四财神飘覆盖、补杠严格支配、未知回退和 trace；本次只新增一个双财神覆盖。
2. 先完整计算父代最终 entries。按 score 降序、action_key 升序确定父代首选；只有父代首选恰为 hu 时才允许新覆盖改分。
3. 新覆盖还必须同时满足：准确财神数恰为 2；合法动作中恰有一个 hu；恰有一个 discard:<wealth_god>；该财神弃牌的 baotou_after is True。财神数必须复用父代包含 drawn_tile 的公开计数口径。
4. 全部条件满足时，只把目标财神弃牌提高到父代 hu 最终分数上方 1.0；其他动作最终分数逐点不变。条件不完整、目标不唯一、父代首选不是 hu 或 baotou_after 不是显式 True 时，全部最终 entries 与父代逐点相同。
5. 目标 trace 增加 two_wealth_piao_keeps_baotou_cf/v1，记录 triggered、wealth_count、parent_top_action、hu_score、score_delta 和退化原因；不得删除父代已有 trace。
6. 不得按题号、牌山、座位、手牌字符串、seed 或隐藏信息硬编码；不得修改规则、合同、执行器或评测；不得宣称隐藏通过、总体增强或可发布。"""
    parent = PARENT.read_text(encoding="utf-8")
    return "\n".join([
        "你是杭麻离线启发式作者。监督器已经用自然可达状态和配对反事实冻结机制；",
        "本次只把冻结机制实现为完整受限源码。不要使用工具，不要长篇分析。",
        "",
        fixed,
        "",
        "【作者可见开发证据；没有隐藏目标、题号、手牌或牌山】",
        json.dumps(evidence, ensure_ascii=False, indent=2),
        "",
        "【输出格式】",
        "严格只输出：花括号内一句中文机制；一个 json 围栏，恰含 trigger/changed_branches/expected_direction/counterexample 四个非空短字符串；一个完整 python 围栏。",
        "Python 不得 import；只能有模块 docstring 和 score_actions(view)；在父代上最小修改并返回全部合法动作。",
        "",
        "【冻结 P5 父代完整源码】",
        "```python",
        parent.rstrip("\n"),
        "```",
        "",
        "现在直接交付完整结果。",
    ])


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("R18 P33 作者批已存在；拒绝覆盖")
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
    inputs = (PARENT, TEACHER, PROTOCOL)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r18-p33-two-wealth-author-manifest/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_request_config": CONFIG,
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "inputs": {str(path): sha256(path) for path in inputs},
        "explicitly_excluded": [
            str(_project_file(_PROJECT_ROOT, HERE / "r18-p32-two-wealth-baotou-rare-teacher-01-20260922/targets.json"))
        ],
        "hidden_evaluation_started": False,
        "effect_tables": 0,
        "release_eligible": False,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-p33-two-wealth-author-01",
        "trusted": True,
        "issued_by": "root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权API限额前持续调度zai-coding-cn GLM 5.3；"
            "双财神方向已通过10自然根、320对共同隐藏世界开发门"
        ),
        "max_initial_calls": 1,
        "max_repair_calls": 1,
        "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 16000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只交付冻结双财神覆盖；不得读取隐藏目标、修改规则、确认或发布",
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
        raise SystemExit("P33 回复目录已存在；拒绝重复调用")
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
        kind="r18-p33-two-wealth-author",
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
        "schema": "r18-p33-two-wealth-author-call-usage/1",
        "task": TASK,
        "run_id": item.get("run_id"),
        "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"),
        "observed_config": item.get("request_config"),
        "usage": usage,
        "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("P33 作者通道或用量核验失败")
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
            ActionValueScorer("r18-p33-author", code)
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
        "schema": "r18-p33-two-wealth-author-ingest/1",
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


def prepare_repair() -> None:
    """冻结一次只修复受限语法的作者调用，不提供任何效果或隐藏反馈。"""

    summary_path = _project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")
    precheck_path = _project_file(_PROJECT_ROOT, BATCH / "generation/precheck.json")
    candidate_path = _project_file(_PROJECT_ROOT, BATCH / "generation/candidate.py")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    precheck = json.loads(precheck_path.read_text(encoding="utf-8"))
    if summary.get("accepted_for_development_preflight") is not False:
        raise RuntimeError("首答已可进入开发预检，不得使用修复额度")
    if precheck.get("rule_ids") != ["AV-SUB-008"]:
        raise RuntimeError("修复只允许处理唯一的 AV-SUB-008 静态合同错误")
    if (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts")).exists():
        raise SystemExit("P33 修复题面已存在；拒绝覆盖")
    source = candidate_path.read_text(encoding="utf-8")
    prompt = "\n".join([
        "这是冻结 P33 候选的唯一一次交付修复。不要使用工具，不要分析算法效果。",
        "首答只违反一个受限 Python 合同：AV-SUB-008 禁止下标赋值。",
        "具体违规是 parent_type_by_key[entry.get(\"action_key\")] = entry.get(\"action_type\")。",
        "请删除这个字典写入及其读取，改为只用简单变量和顺序扫描判断父代首选条目的 action_type。",
        "除解决这一个静态错误所必需的最小改动外，完整源码必须保持首答语义：",
        "双财神覆盖触发域、+1.0 改分、P5 父代全部公式、未知回退、已有覆盖和 trace 均不得改变。",
        "不得加入 import、效果结论、隐藏信息、题号、seed、牌山或手牌硬编码。",
        "",
        "【静态检查器原始反馈】",
        json.dumps(precheck, ensure_ascii=False, indent=2),
        "",
        "【输出格式】",
        "严格只输出：花括号内一句中文修复说明；一个 json 围栏，恰含 trigger/changed_branches/expected_direction/counterexample 四个非空短字符串；一个完整 python 围栏。",
        "Python 只能有模块 docstring 和 score_actions(view)，必须返回全部合法动作。",
        "",
        "【首答完整源码】",
        "```python",
        source.rstrip("\n"),
        "```",
        "",
        "现在直接交付修复后的完整源码。",
    ])
    target = _project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / TASK)
    target.mkdir(parents=True)
    (target / "prompt.txt").write_text(prompt, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml")).write_text(
        (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).read_text(encoding="utf-8"), encoding="utf-8"
    )
    (_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    inputs = (summary_path, precheck_path, candidate_path)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json"), {
        "schema": "r18-p33-two-wealth-author-repair-manifest/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "reason": "首答仅违反 AV-SUB-008：禁止下标赋值",
        "expected_request_config": REPAIR_CONFIG,
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "inputs": {str(path): sha256(path) for path in inputs},
        "effect_feedback_used": False,
        "hidden_input_used": False,
        "max_repairs": 1,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization-repair01.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-p33-two-wealth-author-repair01",
        "trusted": True,
        "issued_by": "root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "使用 P33 冻结授权中的唯一一次修复额度，只修 AV-SUB-008",
        "max_initial_calls": 0,
        "max_repair_calls": 1,
        "max_total_calls": 1,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 16000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只修首答静态合同错误；不得读隐藏目标、改算法机制、确认或发布",
    })
    print(json.dumps({
        "status": "REPAIR_PREPARED", "task": TASK, "prompt_chars": len(prompt),
    }, ensure_ascii=False))


def verify_repair() -> str:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json")).read_text(encoding="utf-8"))
    for path, expected in manifest["inputs"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError("修复输入漂移：" + path)
    prompt = (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / TASK / "prompt.txt")).read_text(
        encoding="utf-8"
    )
    if sha256_text(prompt) != manifest["prompt_sha256"]:
        raise RuntimeError("修复提示词漂移")
    return prompt


def call_repair() -> None:
    """执行唯一一次冻结静态合同修复并核验真实请求参数与用量。"""

    verify_repair()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01")).exists():
        raise SystemExit("P33 修复回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(REPAIR_CONFIG)
    report = dispatch.dispatch(
        BATCH,
        [TASK],
        _project_file(_PROJECT_ROOT, BATCH / "replies-repair01"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-repair01.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")),
        timeout_s=1200,
        concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "repair-prompts"),
        kind="r18-p33-two-wealth-author-repair01",
    )
    item = report["calls"][0]
    usage = criterion.usage_of(item.get("run_id"))
    values = usage.get("usage") or {}
    clean = (
        item.get("exit_code") == 0
        and item.get("protocol_ok") is True
        and item.get("request_config") == REPAIR_CONFIG
        and usage.get("source_status") == "OK"
        and isinstance(values.get("inputTokens"), int)
        and isinstance(values.get("outputTokens"), int)
        and values["inputTokens"] <= 65536
        and values["outputTokens"] <= 16000
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json"), {
        "schema": "r18-p33-two-wealth-author-repair-call-usage/1",
        "task": TASK,
        "run_id": item.get("run_id"),
        "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"),
        "observed_config": item.get("request_config"),
        "usage": usage,
        "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("P33 修复通道或用量核验失败")
    print(json.dumps({"status": "REPAIR_CALLED", "usage": values}, ensure_ascii=False))


def ingest_repair() -> None:
    """解析修复源码并执行同一静态白名单与受限装载预检。"""

    verify_repair()
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")).read_text(encoding="utf-8"))
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01" / (TASK + ".txt"))).read_text(encoding="utf-8")
    parsed = gen.parse_action_value_reply(raw)
    code = parsed.get("code") or ""
    precheck = gen.precheck_action_value_candidate(code) if code else {
        "ok": False, "problems": ["没有源码"],
    }
    load_error = None
    if code and precheck.get("ok") is True:
        try:
            ActionValueScorer("r18-p33-author-repair", code)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    accepted = (
        usage.get("ingestable_channel") is True
        and parsed.get("status") == "ok"
        and precheck.get("ok") is True
        and load_error is None
    )
    target = _project_file(_PROJECT_ROOT, BATCH / "generation-repair01")
    target.mkdir(parents=True, exist_ok=True)
    (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
    if code:
        (target / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
    write_json(target / "parsed.json", {
        key: value for key, value in parsed.items() if key != "code"
    } | ({"code_sha256": sha256_text(code)} if code else {}))
    write_json(target / "precheck.json", precheck)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-ingest-summary.json"), {
        "schema": "r18-p33-two-wealth-author-repair-ingest/1",
        "parse_status": parsed.get("status"),
        "static_precheck": precheck.get("ok"),
        "load_error": load_error,
        "accepted_for_development_preflight": accepted,
        "code_sha256": sha256_text(code) if code else None,
        "hidden_evaluation_started": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "REPAIR_INGESTED", "accepted": accepted,
        "precheck": precheck.get("ok"), "load_error": load_error,
    }, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=(
        "prepare", "call", "ingest", "prepare_repair", "call_repair",
        "ingest_repair",
    ))
    args = parser.parse_args()
    globals()[args.operation]()
