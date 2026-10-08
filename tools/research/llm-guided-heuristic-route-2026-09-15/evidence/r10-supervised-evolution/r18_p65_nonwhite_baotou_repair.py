"""R18 P65：GLM 5.3 首答唯一语法错误的受控等价修复。"""

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
TASK = "P65"
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923/generation/candidate.py')
PRECHECK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923/generation/precheck.json')
INGEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923/ingest-summary.json')
CALL_USAGE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923/call-usage.json')
CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "low",
    "maxTokens": 16000,
}


def sha256(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    """返回 UTF-8 文本 SHA-256。"""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def expected_repair(source: str) -> str:
    """只在已定位 if 行冒号前插入一个右括号，并证明修后可编译。"""

    lines = source.splitlines()
    if len(lines) < 768:
        raise ValueError("P65 首答行数不足")
    line = lines[767]
    marker = 'cand.get("action_key") < chosen.get("action_key"))))):'
    if marker not in line or not line.endswith(":"):
        raise ValueError("P65 首答第768行不再是已冻结的唯一语法错误")
    lines[767] = line[:-1] + "):"
    repaired = "\n".join(lines) + "\n"
    compile(repaired, "<r18-p65-expected-repair>", "exec")
    return repaired


def build_prompt(source: str, expected_sha256: str) -> str:
    """构造只允许一个字符插入的修复题面。"""

    precheck = json.loads(PRECHECK.read_text(encoding="utf-8"))
    return "\n".join([
        "这是冻结 P65 首答的唯一一次交付修复。不要使用工具，不要分析效果。",
        "静态检查只报告 AV-SUB-049：第 768 行 if 条件少一个闭合右括号。",
        "唯一允许的变更：在第 768 行末尾冒号之前插入恰好一个 `)`。",
        "除这个单字符插入外，完整源码每个字符都必须保持不变。",
        "修复后完整源码 SHA-256 必须是：" + expected_sha256,
        "不得改算法、trace、注释、空白、换行或输出说明；不得读取复验材料。",
        "",
        "【静态检查原始反馈】",
        json.dumps(precheck, ensure_ascii=False, indent=2),
        "",
        "【输出格式】",
        "严格只输出：花括号内一句中文修复说明；一个 json 围栏，恰含 trigger/changed_branches/expected_direction/counterexample 四个非空短字符串；一个完整 python 围栏。",
        "",
        "【冻结首答完整源码】",
        "```python",
        source.rstrip("\n"),
        "```",
        "",
        "现在只插入指定的一个右括号并交付完整结果。",
    ])


def prepare() -> None:
    """冻结单字符修复及其期望摘要。"""

    if (_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json")).exists():
        raise SystemExit("P65 修复包已存在；拒绝覆盖")
    precheck = json.loads(PRECHECK.read_text(encoding="utf-8"))
    ingest = json.loads(INGEST.read_text(encoding="utf-8"))
    if precheck.get("rule_ids") != ["AV-SUB-049"]:
        raise ValueError("P65 修复只允许唯一 AV-SUB-049")
    if ingest.get("accepted_for_development_preflight") is not False:
        raise ValueError("P65 首答已被接受，不得使用修复额度")
    source = SOURCE.read_text(encoding="utf-8")
    expected = expected_repair(source)
    prompt = build_prompt(source, sha256_text(expected))
    prompt_dir = _project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / TASK)
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    inputs = (SOURCE, PRECHECK, INGEST, CALL_USAGE)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json"), {
        "schema": "r18-p65-nonwhite-baotou-repair-manifest/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "reason": "首答只报告 AV-SUB-049；第768行冒号前缺一个右括号",
        "expected_request_config": CONFIG,
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
        "inputs": {str(path): sha256(path) for path in inputs},
        "expected_repaired_code_sha256": sha256_text(expected),
        "allowed_change": "第768行冒号前插入一个右括号",
        "effect_feedback_used": False,
        "replication_input_used": False,
        "max_repairs": 1,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization-repair01.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-p65-nonwhite-baotou-author-repair01",
        "trusted": True,
        "issued_by": "root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "使用P65冻结授权中的唯一修复额度，只修AV-SUB-049语法错误",
        "max_initial_calls": 0,
        "max_repair_calls": 1,
        "max_total_calls": 1,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 16000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只允许第768行冒号前插入一个右括号；不得读复验目标或改机制",
    })
    print(json.dumps({
        "status": "REPAIR_PREPARED",
        "prompt_chars": len(prompt),
        "expected_code_sha256": sha256_text(expected),
    }, ensure_ascii=False))


def verify() -> tuple[str, str]:
    """核对修复输入、题面和唯一期望源码未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json")).read_text(encoding="utf-8"))
    for path, expected in manifest["inputs"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError("P65 修复输入漂移：" + path)
    prompt = (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts/P65/prompt.txt")).read_text(encoding="utf-8")
    if sha256_text(prompt) != manifest["prompt_sha256"]:
        raise RuntimeError("P65 修复题面漂移")
    expected = expected_repair(SOURCE.read_text(encoding="utf-8"))
    if sha256_text(expected) != manifest["expected_repaired_code_sha256"]:
        raise RuntimeError("P65 期望单字符修复漂移")
    return prompt, expected


def call() -> None:
    """执行唯一一次冻结修复调用并核验模型与用量。"""

    verify()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01")).exists():
        raise SystemExit("P65 修复回复已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(CONFIG)
    report = dispatch.dispatch(
        BATCH,
        [TASK],
        _project_file(_PROJECT_ROOT, BATCH / "replies-repair01"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-repair01.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")),
        timeout_s=1200,
        concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "repair-prompts"),
        kind="r18-p65-nonwhite-baotou-author-repair01",
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
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json"), {
        "schema": "r18-p65-nonwhite-baotou-repair-call-usage/1",
        "task": TASK,
        "run_id": item.get("run_id"),
        "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"),
        "observed_config": item.get("request_config"),
        "usage": usage,
        "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("P65 修复通道或用量核验失败")
    print(json.dumps({"status": "REPAIR_CALLED", "usage": values}, ensure_ascii=False))


def ingest() -> None:
    """只接受与本地冻结单字符修复逐字一致的完整源码。"""

    _prompt, expected = verify()
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")).read_text(encoding="utf-8"))
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01/P65.txt")).read_text(encoding="utf-8")
    parsed = gen.parse_action_value_reply(raw)
    code = parsed.get("code") or ""
    exact = code.rstrip("\n") + "\n" == expected if code else False
    precheck = gen.precheck_action_value_candidate(code) if code else {
        "ok": False, "problems": ["没有源码"],
    }
    load_error = None
    if code and exact and precheck.get("ok") is True:
        try:
            ActionValueScorer("r18-p65-author-repair", code)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    accepted = bool(
        usage.get("ingestable_channel") is True
        and parsed.get("status") == "ok"
        and exact
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
        "schema": "r18-p65-nonwhite-baotou-repair-ingest/1",
        "parse_status": parsed.get("status"),
        "exact_single_character_repair": exact,
        "static_precheck": precheck.get("ok"),
        "load_error": load_error,
        "accepted_for_development_preflight": accepted,
        "code_sha256": sha256_text(code) if code else None,
        "replication_evaluation_started": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "REPAIR_INGESTED", "accepted": accepted,
        "exact_single_character_repair": exact,
        "precheck": precheck.get("ok"), "load_error": load_error,
    }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "call", "ingest"))
    globals()[parser.parse_args().command]()


if __name__ == "__main__":
    main()
