"""用已准入 GLM 5.3 对吃碰反事实门控失败做一次 ReEvo 式离线反思。"""

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
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
for path in (_project_file(_PROJECT_ROOT, ADMISSION / "p25-headless"), _project_file(_PROJECT_ROOT, ADMISSION / "p25-dev-cards"), HERE):
    sys.path.insert(0, str(path))

import criterion  # noqa: E402
import dispatch_headless as dispatch  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-reflection-01-20260921')
VALIDATION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-new-source-03-20260921/result.json')
STUMP = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-stump-01-20260921/result.json')
LITERATURE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/LITERATURE-REAUDIT-2026-09-20.md')
EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 4096,
}


def sha256(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    """写入稳定 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prompt() -> str:
    """构造只要求诊断和可证伪实验的短提示。"""

    facts = {
        "problem": "杭麻离线启发式：V2在响应窗口过牌，路线父代改成具体chi/peng；需要只用PlayerObservation与HangmaRules公开事实判断何时鸣牌",
        "rules": [
            "杭麻只能自摸；财神白板不参与吃碰杠；吃最多2摊；抓打圈等状态只按规则模块事实",
            "学生/线上候选禁止WorldState、未来牌墙、他家暗手；教师可在离线完整世界结算标签",
            "最终目标是完整阶段group_advance_v1；阶段积分差仅作辅助信用，不替代发布指标",
        ],
        "route_parent_new_source": {
            "tables": 2048,
            "mean_delta": -0.01171875,
            "H": 0.001953125,
            "M": -0.025390625,
            "changes": 707,
            "pass_to_claim_share": 0.983,
            "execution_failures": 0,
        },
        "counterfactual_teacher": {
            "mechanism": "同一自然世界快照强制pass vs具体claim，随后都恢复V2并续打完整剩余阶段",
            "development_samples": 32,
            "development_primary_signs": {"positive": 4, "zero": 25, "negative": 3},
            "development_aux_signs": {"positive": 11, "zero": 12, "negative": 9},
            "new_validation_samples": 16,
            "new_validation_aux_signs": {"positive": 4, "nonpositive": 12},
            "new_validation_always_claim_aux_mean": -4.5625,
        },
        "failed_models": [
            "24训练/8验证的ridge在route_raw、support_delta、wall、chi/peng等特征上退化为总鸣；验证辅助均值-5",
            "32根开发留一选择route_raw<=-0.1807547：LOO balanced_accuracy=0.654、辅助均值+0.406、主均值+0.031",
            "冻结单桩在全新16根：claim_count=2、balanced_accuracy=0.417、辅助均值-1.625、主均值-0.0625，关闭",
            "事后检查22个单特征桩在该新来源没有一个取得正辅助均值；观测到route_raw、支持量、吃碰比例等分布漂移",
        ],
        "literature_constraints": [
            "Suphx：动作类型分解、look-ahead facts、global reward prediction解决粗奖励信用；但其规则和隐藏信息模型不可直接搬到杭麻",
            "Mxplainer/Tjong：目标先行/动作后置、参数校准可借；动作模仿准确率不是赛事效果",
            "EoH/ReEvo：多父代、外部评价、硬预算；其便宜实例规模不可照搬随机麻将桌赛",
        ],
    }
    schema = {
        "primary_diagnosis": "hidden_state_variance|feature_insufficiency|endpoint_mismatch|selection_optimism|mixed",
        "evidence_chain": ["最多5条，只引用输入事实"],
        "recommended_next": "larger_natural_dataset|information_set_resampling|short_horizon_value_target|abandon_claim_route|hybrid",
        "experiment": {
            "hypothesis": "可证伪句",
            "teacher_label": "精确定义",
            "observable_features": ["最多10个，必须来自公开观察/规则事实"],
            "sample_design": "来源隔离、数量级与为何足够/如何校准",
            "model_family": "低自由度且可审计",
            "success_gate": ["不得把代理指标当赛事强度"],
            "stop_gate": ["何时关闭方向"],
            "estimated_cost_class": "low|medium|high",
        },
        "alternative_if_falsified": "一个明确备选",
        "hangma_rule_checks": ["逐条核对的杭麻特性"],
        "claims_not_supported": ["明确不能保证什么"],
    }
    return "\n".join([
        "你是离线麻将启发式演化的反思者。不要写代码，不要泛泛建议，不排名模型。",
        "基于给定事实和文献约束，裁定失败机制并选择下一项最小、可证伪、能推进到可用候选的实验。",
        "不能建议把隐藏世界特征送入线上；若建议信息集重采样，必须说明它只用于教师标签且如何避免规则偏移。",
        "输出严格JSON，不要Markdown或额外文字。",
        "【事实】",
        json.dumps(facts, ensure_ascii=False, indent=2),
        "【输出schema】",
        json.dumps(schema, ensure_ascii=False, indent=2),
    ])


def prepare() -> None:
    """冻结一次反思调用。"""

    if BATCH.exists():
        raise SystemExit("反思批已存在；拒绝覆盖")
    BATCH.mkdir(parents=True)
    task = _project_file(_PROJECT_ROOT, BATCH / "prompts/reflection")
    task.mkdir(parents=True)
    text = prompt()
    (task / "prompt.txt").write_text(text, encoding="utf-8")
    settings = """llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 4096

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: high
"""
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-claim-gate-reflection/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_model": EXPECTED_CONFIG,
        "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "inputs": {
            "validation": {"path": str(VALIDATION), "sha256": sha256(VALIDATION)},
            "stump": {"path": str(STUMP), "sha256": sha256(STUMP)},
            "literature": {"path": str(LITERATURE), "sha256": sha256(LITERATURE)},
        },
        "max_calls": 1,
        "effect_tables": 0,
        "strength_claim": False,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r10-claim-gate-reflection-20260921",
        "trusted": True,
        "issued_by": "Codex root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "用户授权zai-coding-cn GLM5.3并要求受挫时回顾参考文献；本次只做一次ReEvo式失败反思",
        "max_initial_calls": 1,
        "max_repair_calls": 0,
        "max_total_calls": 1,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 4096},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "诊断与下一实验建议；不得确认、发布或修改规则",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED_REFLECTION"}, ensure_ascii=False))


def call() -> None:
    """执行一次 GLM 5.3 反思并核对调用身份。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    text = (_project_file(_PROJECT_ROOT, BATCH / "prompts/reflection/prompt.txt")).read_text(encoding="utf-8")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != manifest["prompt_sha256"]:
        raise ValueError("反思提示摘要漂移")
    for item in manifest["inputs"].values():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError("反思输入摘要漂移")
    replies = _project_file(_PROJECT_ROOT, BATCH / "replies")
    if replies.exists():
        raise SystemExit("反思回复已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, ["reflection"], replies, _project_file(_PROJECT_ROOT, BATCH / "plan.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=900, concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="claim-gate-reflection",
    )
    item = report["calls"][0]
    usage = criterion.usage_of(item.get("run_id"))
    clean = (
        item.get("exit_code") == 0 and item.get("protocol_ok") is True
        and item.get("request_config") == EXPECTED_CONFIG
        and usage.get("source_status") == "OK"
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage.json"), {
        "schema": "r10-claim-gate-reflection-usage/1",
        "run_id": item.get("run_id"),
        "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"),
        "observed_config": item.get("request_config"),
        "usage": usage,
        "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("反思调用身份或用量核对失败")
    print(json.dumps({"status": "CALLED_REFLECTION", "usage": usage}, ensure_ascii=False))


def ingest() -> None:
    """解析严格 JSON 回复并保留原文摘要。"""

    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage.json")).read_text(encoding="utf-8"))
    if usage["ingestable_channel"] is not True:
        raise ValueError("反思回复通道不可摄入")
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies/reflection.txt")).read_text(encoding="utf-8").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    payload = json.loads(raw)
    required = {
        "primary_diagnosis", "evidence_chain", "recommended_next", "experiment",
        "alternative_if_falsified", "hangma_rule_checks", "claims_not_supported",
    }
    if set(payload) != required:
        raise ValueError("反思输出键不符合冻结schema")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingested.json"), {
        "schema": "r10-claim-gate-reflection-ingested/1",
        "reply_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "reflection": payload,
        "advisory_only": True,
        "strength_claim": False,
    })
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "ingest"))
    args = parser.parse_args()
    globals()[args.operation]()
