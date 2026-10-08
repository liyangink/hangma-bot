"""坐隐 3.1 生成闭环的回归测试（正反格式夹具 + 拒绝路径 + 隔离装载 + 血缘）。

**这份测试要能失败**：解析、静态扫描、隔离装载、回复摄入、父代绑定、预算台账
每一层都配了反例；候选执行不会自己结束时，必须由受监管入口终止
（REVIEW-8 S8-2 的教训在生成端同样成立）。

运行：

    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_generate.py -q
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

import ast
import importlib.util
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("sitin_generate", _project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py"))
gen = importlib.util.module_from_spec(_spec)
sys.modules["sitin_generate"] = gen
assert _spec.loader is not None
_spec.loader.exec_module(gen)

FENCE = gen.FENCE

#: 最小可装载候选（正例底座）。
VALID_CANDIDATE = '''from __future__ import annotations

from typing import Mapping, Tuple

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """测试用最小候选：恒给弃牌 +1.0。"""

    value = float(params.get("value", 1.0))

    def delta(candidate: RuleCandidate, ctx: EvaluationContext,
              candidates: Tuple[RuleCandidate, ...]) -> float:
        del candidate, ctx, candidates
        return value

    spec = AdjustmentSpec(
        name="测试候选", version="test-candidate-v1", thought="测试用机制说明。",
        trigger="恒触发。", scope=("discard",), bound=2.0)
    return HeuristicAdjustment(spec, delta,
                               source_fingerprint_value=source_fingerprint_value,
                               params_json="value={0}".format(value))
'''


def reply_text(code: str, thought: str = "测试机制一句话说明") -> str:
    """按 EoH 统一格式拼一条回复。"""

    return "{" + thought + "}\n\n" + FENCE + "python\n" + code.rstrip("\n") + "\n" + FENCE + "\n"


def write_reply_file(path: Path, *, prompt_sha256: str, reply: str,
                     origin: str = gen.ORIGIN_FIXTURE, **extra) -> Path:
    payload = {"schema": gen.REPLY_FILE_SCHEMA, "origin": origin,
               "prompt_sha256": prompt_sha256, "reply": reply}
    if origin == gen.ORIGIN_FIXTURE:
        payload.update({"author": "测试", "purpose": "回归反例"})
    payload.update(extra)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def contract():
    return gen.default_task_contract()


@pytest.fixture()
def i1_prompt(contract):
    return gen.build_i1_prompt(contract)


# ------------------------------------------------------------------ 合同与提示词

def test_surface_matches_running_source():
    """允许面来自真实类型；源码里存在的字段必须都能解析出来。"""

    check = gen.check_surface()
    assert check["ok"] is True, check["problems"]
    assert "chain_piao" in check["fields"]["ctx"]
    assert "baotou" in check["fields"]["ctx"]
    assert "standard_shanten_after" in check["fields"]["candidate.facts"]


def test_contract_facts_use_source_comments_as_units():
    """单位说明取自源码行内注释：chain_piao 必须带"不等于零"的口径。"""

    facts = {item.expression: item for item in gen.default_task_contract().facts}
    assert "不等于零" in facts["ctx.chain_piao"].unit
    assert "ctx.chain_piao" in facts and "candidate.facts.completeness" in facts


def test_i1_prompt_carries_every_contract_section(i1_prompt):
    text = i1_prompt.text
    for marker in ("【任务】", "【允许读取的事实（只有这些）】", "【函数合同（不得改动）】",
                   "【单位与尺度约定】", "【硬限制（违反即拒绝装载）】",
                   "【必须写清反例（什么时候不该生效）】", "【禁止项】", "【输出格式"):
        assert marker in text, marker
    assert gen.ENTRY_NAME in text
    assert i1_prompt.operator == gen.OPERATOR_I1


def test_prompt_hash_changes_with_contract(contract):
    """合同一改，提示词哈希必变——否则血缘会认为"还是同一次生成"。"""

    import dataclasses

    base = gen.build_i1_prompt(contract)
    mutated = gen.build_i1_prompt(dataclasses.replace(contract, task=contract.task + "（改）"))
    assert base.sha256 != mutated.sha256
    assert gen.build_i1_prompt(contract).sha256 == base.sha256


def test_m1_prompt_binds_parent_identity_and_feedback(contract):
    packet = gen.build_m1_prompt(contract, "父代说明", "def x(): pass", "反馈正文",
                                 parent_identity="genloop|i1|parent")
    assert packet.operator == gen.OPERATOR_M1
    assert packet.parent_identity == "genloop|i1|parent"
    assert "反馈正文" in packet.text
    assert "def x(): pass" in packet.text
    assert packet.feedback_sha256 == gen.sha256_text("反馈正文")


# ------------------------------------------------------------------ 解析

def test_parse_positive_extracts_thought_and_code():
    parsed = gen.parse_model_reply(reply_text(VALID_CANDIDATE))
    assert parsed.status == gen.PARSE_OK
    assert parsed.ok is True
    assert "测试机制一句话说明" in parsed.thought
    assert gen.ENTRY_NAME in parsed.code


def test_parse_rejects_reply_without_thought_even_if_code_has_braces():
    """★ 回归：代码里的 "{0}" 不是机制说明。

    初版在全文里找第一个 {...}，于是这条回复被判成 ok——夹具反例当场暴露。
    """

    reply = "先说结论：我改了弃牌分支。\n\n" + FENCE + "python\n" + VALID_CANDIDATE + \
            FENCE + "\n"
    parsed = gen.parse_model_reply(reply)
    assert parsed.status == gen.PARSE_MISSING_THOUGHT
    assert parsed.code is not None            # 代码仍被提取，但状态不是 ok
    assert any("代码之前" in item for item in parsed.problems)


def test_parse_rejects_missing_code():
    parsed = gen.parse_model_reply("{只有说明，没有代码}")
    assert parsed.status == gen.PARSE_MISSING_CODE
    assert parsed.thought is not None


def test_parse_rejects_ambiguous_multiple_code_blocks():
    reply = "{说明}\n\n" + FENCE + "python\n" + VALID_CANDIDATE + FENCE + "\n\n" + \
            FENCE + "python\n" + VALID_CANDIDATE.replace("test-candidate-v1", "v2") + FENCE + "\n"
    parsed = gen.parse_model_reply(reply)
    assert parsed.status == gen.PARSE_AMBIGUOUS_CODE


def test_parse_rejects_empty():
    assert gen.parse_model_reply("   \n").status == gen.PARSE_EMPTY


def test_parse_accepts_unfenced_code_after_thought():
    parsed = gen.parse_model_reply("{说明}\n\n" + VALID_CANDIDATE)
    assert parsed.status == gen.PARSE_OK
    assert parsed.code.startswith("from __future__")


def test_parse_normalises_crlf():
    parsed = gen.parse_model_reply(reply_text(VALID_CANDIDATE).replace("\n", "\r\n"))
    assert parsed.status == gen.PARSE_OK
    assert "\r" not in parsed.code


# ------------------------------------------------------------------ 静态扫描

def test_scan_accepts_allowed_imports():
    report = gen.scan_generated_code(VALID_CANDIDATE)
    assert report.ok is True, report.problems
    assert report.entry_present is True


@pytest.mark.parametrize("snippet, expected", [
    ("import os\n", "禁止的 import"),
    ("from pathlib import Path\n", "禁止的 import"),
    ("import sys\n", "禁止的 import"),
    ("from . import sibling\n", "禁止相对 import"),
])
def test_scan_rejects_forbidden_imports(snippet, expected):
    report = gen.scan_generated_code(snippet + "\n" + VALID_CANDIDATE)
    assert report.ok is False
    assert any(expected in item for item in report.problems)


def test_scan_rejects_forbidden_calls_and_traces():
    code = VALID_CANDIDATE.replace("    value = float(", "    value = float(eval(")
    assert gen.scan_generated_code(code).ok is False
    assert gen.scan_generated_code(VALID_CANDIDATE + "\nhandle = open('x')\n").ok is False


def test_scan_rejects_missing_entry_and_syntax_error():
    assert gen.scan_generated_code("x = 1\n").ok is False
    assert any("缺少入口函数" in item
               for item in gen.scan_generated_code("x = 1\n").problems)
    broken = gen.scan_generated_code("def f(:\n")
    assert broken.ok is False
    assert any("语法错误" in item for item in broken.problems)


# ------------------------------------------------------------------ 隔离装载

def test_supervised_load_accepts_valid_candidate(tmp_path):
    code_path = tmp_path / "candidate.py"
    code_path.write_text(VALID_CANDIDATE, encoding="utf-8")
    outcome = gen.supervised_load(code_path, {"value": 3.0}, timeout_sec=60)
    assert outcome.ok is True, outcome.reason
    payload = outcome.to_json()
    assert payload["equivalent_to_three_gates"] is False
    assert payload["gates_run"] == []
    assert payload["report"]["probe"]["ok"] is True
    assert payload["report"]["construct"]["with_params"]["spec"]["bound"] == 2.0
    # 身份里必须带 src 段（与生产装载同口径：源码指纹进候选身份）
    assert "+src" in payload["report"]["construct"]["default"]["identity"]
    assert gen.sha256_file(code_path)[:12] in payload["report"]["construct"]["default"]["identity"]


def test_supervised_load_kills_module_level_infinite_loop(tmp_path):
    """★ 生成代码在模块体里死循环：必须由监管方终止，且判 FAIL（不是"证据不足"）。"""

    code_path = tmp_path / "loop.py"
    code_path.write_text("while True:\n    pass\n", encoding="utf-8")
    outcome = gen.supervised_load(code_path, {}, timeout_sec=2)
    assert outcome.ok is False
    assert "超时" in outcome.reason
    assert outcome.execution["timed_out"] is True


def test_supervised_load_reports_import_failure(tmp_path):
    code_path = tmp_path / "boom.py"
    code_path.write_text("raise RuntimeError('模块体故意失败')\n", encoding="utf-8")
    outcome = gen.supervised_load(code_path, {}, timeout_sec=30)
    assert outcome.ok is False
    assert "RuntimeError" in outcome.reason


def test_supervised_load_fails_closed_when_delta_returns_non_numeric(tmp_path):
    """delta 返回字符串：探针必须判 FAIL（不得静默放行一个有缺陷的候选）。"""

    code = VALID_CANDIDATE.replace("        return value", "        return 'oops'")
    code_path = tmp_path / "bad.py"
    code_path.write_text(code, encoding="utf-8")
    outcome = gen.supervised_load(code_path, {}, timeout_sec=30)
    assert outcome.ok is False
    assert "探针失败" in outcome.reason


# ------------------------------------------------------------------ 回复摄入与血缘

def test_reply_envelope_rejects_prompt_hash_mismatch(tmp_path):
    path = write_reply_file(tmp_path / "r.json", prompt_sha256="deadbeef", reply="{x}")
    with pytest.raises(gen.ReplyEnvelopeError) as excinfo:
        gen.load_reply_envelope(path, prompt_sha256="cafebabe")
    assert "提示词哈希不符" in str(excinfo.value)


def test_reply_envelope_rejects_fixture_declaring_a_model(tmp_path):
    path = write_reply_file(tmp_path / "r.json", prompt_sha256="a" * 64, reply="{x}",
                            provider="someone", model="some-model")
    with pytest.raises(gen.ReplyEnvelopeError) as excinfo:
        gen.load_reply_envelope(path, prompt_sha256="a" * 64)
    assert "不得携带 provider/model" in str(excinfo.value)


def test_reply_envelope_rejects_missing_required_fields(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"schema": gen.REPLY_FILE_SCHEMA,
                                "origin": gen.ORIGIN_DELEGATED,
                                "prompt_sha256": "a" * 64, "reply": "{x}"}),
                    encoding="utf-8")
    with pytest.raises(gen.ReplyEnvelopeError) as excinfo:
        gen.load_reply_envelope(path, prompt_sha256="a" * 64)
    assert "缺少必填字段" in str(excinfo.value)


def test_reply_envelope_rejects_unknown_origin_and_schema(tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"schema": "wrong", "origin": "nope", "reply": "x"}),
                    encoding="utf-8")
    with pytest.raises(gen.ReplyEnvelopeError):
        gen.load_reply_envelope(path, prompt_sha256="a" * 64)


def _ingest(tmp_path, contract, reply, *, origin=gen.ORIGIN_FIXTURE, parent=None,
            backend=gen.BACKEND_REPLAY, out_name="out", **extra):
    packet = gen.build_i1_prompt(contract)
    context = gen.prepare_attempt(gen.OPERATOR_I1, contract, None, "")
    reply_file = write_reply_file(tmp_path / "reply.json", prompt_sha256=packet.sha256,
                                  reply=reply, origin=origin, **extra)
    data = gen.load_reply_envelope(reply_file, prompt_sha256=packet.sha256)
    model_reply = gen.ModelReply(text=data["reply"], backend=backend, origin=data["origin"],
                                 provider=data.get("provider"), model=data.get("model"),
                                 captured_at_utc=data.get("captured_at_utc"),
                                 usage={}, delegator=data.get("delegator"))
    out_dir = tmp_path / out_name
    ledger = gen.GenerationBudget(path=out_dir / "budget.json", calls_budget=4)
    ledger.reserve("test")
    record = gen.ingest_reply(context=context, out_dir=out_dir, backend=backend,
                              env={"reply": model_reply, "reply_file": str(reply_file),
                                   # 与 CLI 同口径：非 api 通道没有发生采样，sampling 为 None
                                   "sampling": None, "request_identity": {},
                                   "endpoint_host": None, "credential_source": None,
                                   "tier": None, "model_requested": None},
                              parent=parent, ledger=ledger, params={},
                              load_timeout_sec=60, secrets=(), started_monotonic=0.0)
    return record, out_dir


def test_ingest_writes_full_lineage_and_hard_boundaries(tmp_path, contract):
    record, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    assert record["schema"] == gen.GENERATION_RECORD_SCHEMA
    assert record["parse"]["status"] == gen.PARSE_OK
    assert record["load"]["ok"] is True
    assert record["reply"]["evidence_kind"] == gen.REPLY_FIXTURE
    assert record["reply"]["is_model_output"] is False
    # 三条硬边界必须写进产物本身
    assert record["registration"] == {"registered": False, "auto_publish": False,
                                      "requires_human_review": True, "wrote_to_src": False,
                                      "note": record["registration"]["note"]}
    assert record["admission"]["eligible"] is False
    assert record["admission"]["status"] == "pending_admission"
    assert record["gates_run"] == []
    assert record["load"]["equivalent_to_three_gates"] is False
    # 血缘可追溯：提示词、原始回复、代码都落盘且哈希对得上
    attempt = out_dir / record["attempt_dir"]
    assert gen.sha256_file(attempt / "prompt.txt") == record["prompt"]["sha256"], \
        "落盘的提示词原文必须与 prompt.sha256 逐字节一致"
    assert (attempt / "reply_raw.txt").read_text(encoding="utf-8") == \
        reply_text(VALID_CANDIDATE)
    assert record["reply"]["raw_sha256"] == gen.sha256_text(
        (attempt / "reply_raw.txt").read_text(encoding="utf-8"))
    assert (out_dir / "records.jsonl").is_file()
    assert (out_dir / "budget.json").is_file()


def test_ingest_code_hash_matches_written_file(tmp_path, contract):
    """★ 回归：记录里的 code.sha256 必须等于 candidate.py 的**字节哈希**。

    初版把 parsed.code 的哈希写进记录、却把 rstrip 后的文本写进文件，
    父代核验因此拒绝（与 R8-5「产物与台账对不上」同类）。
    """

    record, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    attempt = out_dir / record["attempt_dir"]
    assert gen.sha256_file(attempt / "candidate.py") == record["code"]["sha256"]
    parsed = json.loads((attempt / "parsed.json").read_text(encoding="utf-8"))
    assert parsed["code_sha256"] == record["code"]["sha256"], "解析产物与记录的代码哈希必须同口径"


def test_ingest_rejected_reply_still_records_and_blocks_admission(tmp_path, contract):
    record, out_dir = _ingest(tmp_path, contract, "{说明}\n\n" + FENCE + "python\nimport os\n"
                              + FENCE + "\n")
    assert record["load"]["ok"] is False
    assert "静态扫描" in record["load"]["reason"]
    assert record["admission"]["eligible"] is False
    assert (out_dir / record["attempt_dir"] / "reply_raw.txt").is_file()


def test_ingest_marks_delegated_reply_as_model_output(tmp_path, contract):
    record, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE),
                        origin=gen.ORIGIN_DELEGATED, provider="p", model="m",
                        captured_at_utc="2026-09-15T00:00:00Z", delegator="lead")
    assert record["reply"]["evidence_kind"] == gen.REPLY_DELEGATED
    assert record["reply"]["is_model_output"] is True
    assert record["model"]["provider"] == "p"


def test_ingest_never_writes_secrets(tmp_path, contract, monkeypatch):
    """凭据明文不得出现在任何产物里（含 budget/records/summary）。"""

    secret = "sk-test-0123456789abcdef"
    monkeypatch.setenv(gen.DEFAULT_API_KEY_ENV, secret)
    record, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    for path in out_dir.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(encoding="utf-8"), path
    assert record["redactions"]["leaks_found"] == []


def test_write_summary_keeps_boundaries(tmp_path, contract):
    _, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    text = gen.write_summary(out_dir)
    assert "pending_admission" in text
    assert "G-0 同级" in text


# ------------------------------------------------------------------ 后端

class _StubHandler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):                                   # noqa: N802 —— 标准库命名
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        type(self).received.append({"path": self.path,
                                    "headers": dict(self.headers),
                                    "body": json.loads(raw)})
        payload = json.dumps({"model": "stub-model",
                              "usage": {"prompt_tokens": 11, "completion_tokens": 22},
                              "choices": [{"message": {"content": "{stub}"},
                                           "finish_reason": "stop"}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):                        # 测试里不要刷屏
        pass


@pytest.fixture()
def stub_server():
    _StubHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{0}/v1".format(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def test_api_backend_requires_credentials(monkeypatch):
    monkeypatch.delenv(gen.DEFAULT_API_KEY_ENV, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(gen.TransportError) as excinfo:
        gen.ApiBackend("https://example.invalid/v1", "m", api_key_env="SITIN_TEST_KEY")
    assert "SITIN_TEST_KEY" in str(excinfo.value)


def test_api_backend_does_a_real_http_round_trip(stub_server, monkeypatch):
    """本地 stub 服务：证明这条路径真的发 HTTP 请求、按 OpenAI 兼容结构取回复。

    **注意口径**：这是**真实 HTTP 往返**，但不是真实模型（stub 不是模型）。
    """

    monkeypatch.setenv("SITIN_TEST_KEY", "sk-abcdef0123456789")
    backend = gen.ApiBackend(stub_server, "stub-model", api_key_env="SITIN_TEST_KEY",
                             sampling=gen.SamplingSpec(temperature=0.2, top_p=0.8,
                                                       max_tokens=123, seed=7))
    reply = backend.complete("提示词原文")
    assert reply.text == "{stub}"
    assert reply.http_status == 200
    assert reply.model == "stub-model"
    assert reply.usage["completion_tokens"] == 22
    assert reply.evidence_kind == gen.REPLY_CAPTURED
    sent = _StubHandler.received[-1]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["body"]["model"] == "stub-model"
    assert sent["body"]["messages"][0]["content"] == "提示词原文"
    assert sent["body"]["temperature"] == 0.2 and sent["body"]["max_tokens"] == 123
    assert sent["headers"]["Authorization"].startswith("Bearer sk-")


def test_api_backend_http_error_is_a_clear_failure(tmp_path, monkeypatch):
    class _Fail(BaseHTTPRequestHandler):
        def do_POST(self):                               # noqa: N802
            self.send_response(500)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"no")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Fail)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("SITIN_TEST_KEY", "sk-abcdef0123456789")
    try:
        backend = gen.ApiBackend("http://127.0.0.1:{0}/v1".format(server.server_address[1]),
                                 "m", api_key_env="SITIN_TEST_KEY")
        with pytest.raises(gen.TransportError) as excinfo:
            backend.complete("x")
        assert "HTTP 500" in str(excinfo.value)
        assert "sk-abcdef0123456789" not in str(excinfo.value)
    finally:
        server.shutdown()
        server.server_close()


def test_api_backend_never_echoes_secret_in_messages():
    secret = "sk-abcdef0123456789"
    backend = gen.ApiBackend("https://example.invalid/v1", "m", api_key=secret)
    try:
        backend.complete("x")
    except gen.TransportError as exc:
        assert secret not in str(exc)


def test_delegate_backend_refuses_to_call_a_model():
    with pytest.raises(gen.TransportError) as excinfo:
        gen.DelegateBackend().complete("x")
    assert "--emit-prompt" in str(excinfo.value)


def test_headless_backend_requires_injected_credentials(tmp_path, monkeypatch):
    """headless 需要把密钥注入子进程；没有密钥必须明确失败，不静默退化到别的通道。"""

    monkeypatch.setattr(gen, "DEFAULT_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv(gen.CONFIG_ENV, raising=False)
    monkeypatch.delenv(gen.KEY_ONLY_ENV, raising=False)
    backend = gen.HeadlessBackend(dsh_bin=str(tmp_path / "nope"), dsh_home=tmp_path / "dsh")
    with pytest.raises(gen.TransportError) as excinfo:
        backend.complete("提示词")
    assert gen.KEY_ONLY_ENV in str(excinfo.value)


#: 假 dsh 脚本：**原样写盘**，因此用 raw 字符串，避免 \n 在测试里被提前解释。
FAKE_DSH = r'''import json, os, pathlib, subprocess, sys
home = pathlib.Path(os.environ["DSH_HOME"])
sess = home / "sessions" / "fake" / "session-test"
sess.mkdir(parents=True, exist_ok=True)
events = [
    {"type": "session", "id": "session-test", "cwd": os.getcwd()},
    {"type": "request/header", "seq": 11, "data": {"header": {"config": {
        "provider": "fake-provider", "model": "fake-model",
        "maxTokens": 256000, "reasoningEffort": "high"}}}},
    # 一个会话可能有多条用量事件（每个 step 一条）⇒ 必须累加
    {"type": "assistant/chunk", "seq": 12, "data": {"chunk": {"type": "usage", "usage": {
        "inputTokens": 100, "outputTokens": 20, "totalTokens": 120,
        "cacheReadTokens": 0, "reasoningTokens": 5}}}},
    {"type": "assistant/chunk", "seq": 13, "data": {"chunk": {"type": "usage", "usage": {
        "inputTokens": 30, "outputTokens": 10, "totalTokens": 40,
        "cacheReadTokens": 0, "reasoningTokens": 2}}}},
]
raw = ("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n").encode()
subprocess.run(["zstd", "-q", "-o", str(sess / "session.jsonl.zstd")], input=raw)
sys.stdout.write(pathlib.Path("@@REPLY_FILE@@").read_text(encoding="utf-8"))
sys.stderr.write("REASONING-ONLY-DO-NOT-PARSE" * 50)
'''


def _fake_dsh(tmp_path, reply: str):
    """造一个假 dsh：stdout 给回复、stderr 给推理过程，并写一份会话痕迹。"""

    script = tmp_path / "fake_dsh.py"
    reply_file = tmp_path / "reply.txt"
    reply_file.write_text(reply, encoding="utf-8")
    # 回复文件路径**写进脚本**：headless 子进程环境是白名单的，
    # 测试不能靠环境变量传参（那正好证明白名单生效）。
    script.write_text(FAKE_DSH.replace("@@REPLY_FILE@@", str(reply_file)), encoding="utf-8")
    wrapper = tmp_path / "fake_dsh"
    wrapper.write_text("#!/bin/sh\nexec {0} {1} \"$@\"\n".format(sys.executable, script),
                       encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper, reply_file


def test_headless_uses_stdout_only_and_observes_model_identity(tmp_path):
    """★ headless 纪律：stdout 当回复、stderr（推理过程）**丢弃**；身份从会话痕迹里读。"""

    wrapper, _reply_file = _fake_dsh(tmp_path, reply_text(VALID_CANDIDATE))
    dsh_home = tmp_path / "dsh-home"
    backend = gen.HeadlessBackend(dsh_bin=str(wrapper), dsh_home=dsh_home,
                                  api_key="sk-fake-000000")
    backend._session_before = backend.session_files()
    reply = backend.complete("提示词原文")
    assert "REASONING-ONLY-DO-NOT-PARSE" not in reply.text, "stderr 不得进入回复"
    assert gen.parse_model_reply(reply.text).status == gen.PARSE_OK
    assert reply.info_boundary == "weak"
    assert reply.observed_config["provider"] == "fake-provider"
    assert reply.observed_config["model"] == "fake-model"
    assert reply.observed_config["reasoningEffort"] == "high"
    assert reply.session_file and reply.session_file.endswith("session.jsonl.zstd")
    assert reply.provider == "fake-provider" and reply.model == "fake-model"
    assert reply.elapsed_sec is not None
    # 用量从**同一个会话日志**累加（两条事件）
    assert reply.usage_source == "session_log"
    assert reply.usage["totalTokens"] == 160
    assert reply.usage["inputTokens"] == 130 and reply.usage["outputTokens"] == 30
    assert reply.usage["reasoningTokens"] == 7 and reply.usage["events"] == 2
    assert gen.usage_tokens(reply.usage) == 160
    assert backend.prompt_sent.endswith(gen.HEADLESS_PROMPT_SUFFIX)


def test_cli_headless_records_sent_prompt_and_boundary(tmp_path, contract, monkeypatch):
    """★ 用假 dsh 跑通 CLI：落盘实际发出的提示词、弱边界、观测身份与耗时。"""

    wrapper, _reply_file = _fake_dsh(tmp_path, reply_text(VALID_CANDIDATE))
    monkeypatch.setenv(gen.KEY_ONLY_ENV, "sk-fake-000000")
    monkeypatch.delenv(gen.CONFIG_ENV, raising=False)
    out_dir = tmp_path / "run"
    assert gen._main_with_internal([
        "i1", "--out", str(out_dir), "--backend", "headless",
        "--dsh-bin", str(wrapper), "--dsh-home", str(tmp_path / "dsh-home")]) == 0
    row = json.loads((out_dir / "records.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    record = json.loads((out_dir / row["attempt_dir"] / "record.json").read_text(
        encoding="utf-8"))
    assert record["reply"]["evidence_kind"] == gen.REPLY_HEADLESS
    assert record["reply"]["is_model_output"] is True
    assert record["model"]["model"] == "fake-model"
    assert record["model"]["identity_source"] == "session_log"
    # headless 也必须有凭据来源：密钥确实被注入过子进程（来源可知，不是 None）
    assert record["model"]["credential_source"] == "env {0}".format(gen.KEY_ONLY_ENV)
    assert record["info_boundary"]["strength"] == "weak"
    prompt = record["prompt"]
    assert prompt["sent_path"] == "prompt_sent.txt"
    assert prompt["channel_suffix_chars"] == len(gen.HEADLESS_PROMPT_SUFFIX)
    sent_path = out_dir / row["attempt_dir"] / "prompt_sent.txt"
    assert gen.sha256_file(sent_path) == prompt["sent_sha256"]
    assert sent_path.read_text(encoding="utf-8").endswith(gen.HEADLESS_PROMPT_SUFFIX)
    assert record["load"]["ok"] is True
    assert record["admission"]["eligible"] is False


def test_attempt_identity_prevents_evidence_overwrite(tmp_path, contract):
    """★ 返工 #6：两次**付费**调用若回复相同（例如都被截断、正文为空），不得互相覆盖。"""

    empty = gen.ModelReply(text="", backend=gen.BACKEND_API, origin=gen.ORIGIN_CAPTURED,
                           provider="p", model="m", captured_at_utc="2026-09-15T00:00:00Z",
                           usage={}, finish_reason="length", info_boundary="strong")
    context = gen.prepare_attempt(gen.OPERATOR_I1, contract, None, "")
    out_dir = tmp_path / "run"
    identities = []
    for index in range(2):
        ledger = gen.GenerationBudget(path=out_dir / "budget.json", calls_budget=8)
        ledger.reserve("第 {0} 次".format(index + 1))
        record = gen.ingest_reply(
            context=context, out_dir=out_dir, backend=gen.BACKEND_API,
            env={"reply": empty, "reply_file": None,
                 "sampling": {"values": {"temperature": 0.0}},
                 "request_identity": {}, "endpoint_host": None, "credential_source": None,
                 "tier": None, "model_requested": None},
            parent=None, ledger=ledger, params={}, load_timeout_sec=30, secrets=(),
            started_monotonic=0.0)
        identities.append(record["attempt_identity"])
        assert record["parse"]["status"] == gen.PARSE_TRUNCATED
    assert identities[0] != identities[1], "同一份空回复的两次调用必须各有身份"
    assert "attempt=1" in identities[0] and "attempt=2" in identities[1]
    assert "sampling=-" not in identities[0]
    dirs = sorted(path.name for path in (out_dir / "attempts").iterdir())
    assert len(dirs) == 2, dirs
    assert len((out_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_token_budget_stops_and_is_accounted(tmp_path):
    """★ 返工 S5：累计 token 超限即停止并记账；台账里有累计值。"""

    ledger = gen.GenerationBudget(path=tmp_path / "budget.json", calls_budget=8,
                                  max_total_tokens=1000)
    ledger.check_token_budget()
    ledger.reserve("first")
    assert ledger.charge_tokens({"prompt_tokens": 400, "completion_tokens": 500}) == 900
    assert ledger.spent_tokens == 900
    ledger.check_token_budget()
    ledger.reserve("second")
    ledger.charge_tokens({"total_tokens": 200})
    assert ledger.spent_tokens == 1100
    with pytest.raises(gen.BudgetExhausted):
        ledger.check_token_budget()
    payload = json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))
    assert payload["spent_tokens"] == 1100
    assert payload["max_total_tokens"] == 1000
    assert payload["entries"][0]["tokens"] == 900
    assert payload["entries"][1]["tokens_cumulative"] == 1100


def test_load_report_records_sandbox_facts(tmp_path):
    """★ Lead 裁定 #9：装载报告要带沙箱事实（子进程 cwd、环境白名单、注册表前后快照）。"""

    code_path = tmp_path / "c.py"
    code_path.write_text(VALID_CANDIDATE, encoding="utf-8")
    before = gen.registry_snapshot()
    outcome = gen.supervised_load(code_path, {}, timeout_sec=60, registry_before=before)
    assert outcome.ok is True, outcome.reason
    sandbox = outcome.execution["sandbox"]
    assert sandbox["registry_unchanged"] is True
    assert sandbox["registry_digest_before"] == sandbox["registry_digest_after"]
    assert sandbox["child_cwd"] != str(gen.REPO), "子进程不得在仓库里跑"
    assert "env_allowlist" in sandbox
    assert gen.registry_snapshot() == before, "装载不得改动注册表"


def test_child_env_is_allowlisted(monkeypatch):
    """子进程环境走白名单：父进程的任意环境变量不得整份带下去。"""

    monkeypatch.setenv("SITIN_SHOULD_NOT_LEAK", "1")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
    env = gen.child_env({"DSH_HOME": "/tmp/x"})
    assert "SITIN_SHOULD_NOT_LEAK" not in env
    assert env["DSH_HOME"] == "/tmp/x"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_emit_prompt_writes_handoff_files(tmp_path, contract):
    context = gen.prepare_attempt(gen.OPERATOR_I1, contract, None, "")
    info = gen.emit_prompt(context, tmp_path, backend=gen.BACKEND_DELEGATE)
    pending = Path(info["prompt_dir"])
    assert (pending / "prompt.txt").read_text(encoding="utf-8").startswith(
        "你是离线研发流程")
    payload = json.loads((pending / "prompt.json").read_text(encoding="utf-8"))
    assert payload["prompt_sha256"] == context.packet.sha256
    assert payload["allowed_surface"]
    # ★ 交接文件必须能被下游自证：文件字节哈希 == prompt_sha256
    assert gen.sha256_file(pending / "prompt.txt") == context.packet.sha256
    request = json.loads((pending / "delegation-request.json").read_text(encoding="utf-8"))
    assert request["reply_file_template"]["prompt_sha256"] == context.packet.sha256
    assert any("不" in item and "代理" in item for item in request["how_to_use"])


# ------------------------------------------------------------------ 预算台账

def test_budget_reserves_before_calling_and_persists(tmp_path):
    ledger = gen.GenerationBudget(path=tmp_path / "budget.json", calls_budget=2)
    ledger.reserve("first")
    assert ledger.spent_calls == 1
    assert json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))["spent_calls"] == 1
    ledger.reserve("second")
    with pytest.raises(gen.BudgetExhausted):
        ledger.reserve("third")
    assert json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))["spent_calls"] == 2


def test_budget_refuses_silent_budget_change(tmp_path):
    gen.GenerationBudget(path=tmp_path / "budget.json", calls_budget=3).reserve("x")
    with pytest.raises(ValueError):
        gen.GenerationBudget.load(tmp_path / "budget.json", calls_budget=5)


# ------------------------------------------------------------------ 父代绑定与 CLI

def test_parent_binding_verifies_persisted_artifacts(tmp_path, contract):
    record, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    parent_dir = out_dir / record["attempt_dir"]
    binding = gen.parent_binding(parent_dir)
    assert binding["verified"] is True
    assert binding["identity"] == record["attempt_identity"]
    # ★ R8-3 同一条纪律：改了代码文件，绑定必须拒绝
    code_path = parent_dir / "candidate.py"
    code_path.write_text(code_path.read_text(encoding="utf-8") + "\n# 篡改\n",
                         encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        gen.parent_binding(parent_dir)
    assert "父代代码与记录不一致" in str(excinfo.value)


def test_parent_binding_allows_rejected_parent_for_repair(tmp_path, contract):
    """修复型修订：父代**装载失败**仍可作父代（拒绝诊断 → 修订请求，PLAN §3.2）。

    血缘里如实记 load_ok=false：这是"把坏的修好"，不是"在好父代上继续变强"。
    """

    record, out_dir = _ingest(tmp_path, contract, "{说明}\n\n" + FENCE + "python\nimport os\n"
                              + FENCE + "\n")
    binding = gen.parent_binding(out_dir / record["attempt_dir"])
    assert binding["verified"] is True
    assert binding["load_ok"] is False
    feedback = gen.feedback_from_diagnosis(record)
    assert "静态扫描问题" in feedback and "禁止的 import" in feedback


def test_parent_binding_rejects_unparsable_parent(tmp_path, contract):
    """解析都没过的尝试没有可用代码，不能作父代。"""

    record, out_dir = _ingest(tmp_path, contract, "这条回复里没有任何代码")
    with pytest.raises(ValueError) as excinfo:
        gen.parent_binding(out_dir / record["attempt_dir"])
    assert "candidate.py" in str(excinfo.value)


def test_cli_repair_from_diagnosis_end_to_end(tmp_path, contract):
    """拒绝诊断 → 修复型 M1 → 装载通过；父代装载状态如实落盘。"""

    broken_reply = "{说明}\n\n" + FENCE + "python\nimport os\n" + FENCE + "\n"
    record, out_dir = _ingest(tmp_path, contract, broken_reply, out_name="broken")
    parent_dir = out_dir / record["attempt_dir"]
    parent = gen.parent_binding(parent_dir)
    feedback = gen.feedback_from_diagnosis(record)
    m1_context = gen.prepare_attempt(gen.OPERATOR_M1, contract, parent, feedback)
    reply_file = write_reply_file(tmp_path / "fixed.json",
                                  prompt_sha256=m1_context.packet.sha256,
                                  reply=reply_text(VALID_CANDIDATE))
    assert gen._main_with_internal([
        "m1", "--out", str(out_dir), "--parent", str(parent_dir),
        "--from-diagnosis", str(parent_dir), "--backend", "replay",
        "--replay", str(reply_file), "--calls-budget", "4"]) == 0
    last = json.loads((out_dir / "records.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    repaired = json.loads((out_dir / last["attempt_dir"] / "record.json").read_text(
        encoding="utf-8"))
    assert repaired["operator"] == gen.OPERATOR_M1
    assert repaired["parent"]["load_ok"] is False, "父代装载失败必须如实记录"
    assert repaired["load"]["ok"] is True, "修复后的候选应当装载通过"
    assert repaired["admission"]["eligible"] is False
    assert repaired["lineage"]["repair_depth"] == 1


def test_cli_i1_replay_end_to_end(tmp_path, contract):
    prompt = gen.build_i1_prompt(contract)
    reply_file = write_reply_file(tmp_path / "r.json", prompt_sha256=prompt.sha256,
                                  reply=reply_text(VALID_CANDIDATE),
                                  origin=gen.ORIGIN_DELEGATED, provider="p", model="m",
                                  captured_at_utc="2026-09-15T00:00:00Z", delegator="lead")
    out_dir = tmp_path / "run"
    code = gen._main_with_internal(["i1", "--out", str(out_dir), "--backend", "replay",
                                    "--replay", str(reply_file)])
    assert code == 0
    rows = [json.loads(line) for line in
            (out_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["evidence_kind"] == gen.REPLY_DELEGATED
    assert rows[-1]["load_ok"] is True
    assert rows[-1]["admission_eligible"] is False


def test_cli_rejects_fixture_replayed_as_the_wrong_prompt(tmp_path, contract):
    """★ 拒绝路径：拿另一次（或另一个合同）的回复冒充本次 —— 必须拒绝并计费。"""

    reply_file = write_reply_file(tmp_path / "r.json", prompt_sha256="0" * 64,
                                  reply=reply_text(VALID_CANDIDATE))
    out_dir = tmp_path / "run"
    with pytest.raises(gen.ReplyEnvelopeError):
        gen._main_with_internal(["i1", "--out", str(out_dir), "--backend", "replay",
                                 "--replay", str(reply_file)])
    ledger = json.loads((out_dir / "budget.json").read_text(encoding="utf-8"))
    assert ledger["spent_calls"] == 1, "失败的调用同样计费"
    assert ledger["entries"][-1]["status"] == "failed"
    assert not (out_dir / "records.jsonl").exists()


def test_cli_delegate_without_ingest_tells_the_operator_what_to_do(tmp_path):
    out_dir = tmp_path / "run"
    with pytest.raises(gen.TransportError) as excinfo:
        gen._main_with_internal(["i1", "--out", str(out_dir), "--backend", "delegate"])
    assert "--emit-prompt" in str(excinfo.value)


def test_cli_refuses_to_write_anywhere_outside_out_dir(tmp_path, contract):
    """**没有自动上线通道**：跑完一次生成后，候选注册表目录必须一个字节都没变。"""

    registry = gen.REPO / "src" / "hangma_bot" / "policy" / "heuristics"
    before = {path.name: gen.sha256_file(path) for path in sorted(registry.glob("*.py"))}
    prompt = gen.build_i1_prompt(contract)
    reply_file = write_reply_file(tmp_path / "r.json", prompt_sha256=prompt.sha256,
                                  reply=reply_text(VALID_CANDIDATE))
    out_dir = tmp_path / "run"
    assert gen._main_with_internal(["i1", "--out", str(out_dir), "--backend", "replay",
                                    "--replay", str(reply_file)]) == 0
    after = {path.name: gen.sha256_file(path) for path in sorted(registry.glob("*.py"))}
    assert before == after
    produced = [path for path in out_dir.rglob("*") if path.is_file()]
    assert produced, "必须留下产物"
    assert all(str(path).startswith(str(out_dir)) for path in produced)


def test_cli_m1_requires_parent(tmp_path):
    out_dir = tmp_path / "run"
    with pytest.raises(ValueError) as excinfo:
        gen._main_with_internal(["m1", "--out", str(out_dir), "--backend", "replay",
                                 "--replay", str(tmp_path / "nope.json")])
    assert "M1 必须有父代" in str(excinfo.value)


def test_cli_m1_binds_verified_parent_and_depth_limit(tmp_path, contract):
    record, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    parent_dir = out_dir / record["attempt_dir"]
    parent = gen.parent_binding(parent_dir)
    context = gen.prepare_attempt(gen.OPERATOR_M1, contract, parent, "反馈")
    assert context.packet.parent_identity == parent["identity"]
    # 修复深度上限：第 3 代（父代深度 2）必须被拒绝
    assert parent["repair_depth"] == 0


def test_load_cli_writes_report(tmp_path):
    code_path = tmp_path / "c.py"
    code_path.write_text(VALID_CANDIDATE, encoding="utf-8")
    out_dir = tmp_path / "load"
    assert gen._main_with_internal(["load", "--code", str(code_path),
                                    "--out", str(out_dir)]) == 0
    payload = json.loads((out_dir / "load-report.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["equivalent_to_three_gates"] is False


def test_surface_cli_reports_check(tmp_path, capsys):
    assert gen._main_with_internal(["surface", "--out", str(tmp_path)]) == 0
    payload = json.loads((tmp_path / "allowed-surface.json").read_text(encoding="utf-8"))
    assert payload["check"]["ok"] is True
    assert payload["contract"]["facts"]
    capsys.readouterr()


def test_feedback_from_diagnosis_separates_facts_from_hypotheses(tmp_path, contract):
    record, _ = _ingest(tmp_path, contract, "{说明}\n\n" + FENCE + "python\nimport os\n"
                        + FENCE + "\n")
    feedback = gen.feedback_from_diagnosis(record)
    assert "【事实】" in feedback and "【相关表现】" in feedback and "【机制假设】" in feedback
    assert "确认集" not in feedback
    assert "禁止的 import" in feedback


# ------------------------------------------------------------------ 返工项回归（第三阶段 Challenger #8/#11/#12/#13/#14）

@pytest.mark.parametrize("snippet", [
    "from hangma_bot.policy import heuristics\n",
    "from hangma_bot import policy\n",
    "import hangma_bot.policy\n",
    "from hangma_bot.policy.heuristics import seven_pairs_path_value\n",
    "from hangma_bot.policy.evaluation_v1 import EvaluationContext as _EC\n"
    "from hangma_bot.policy import heuristics\n",
])
def test_scan_rejects_parent_package_import_bypass(snippet):
    """★ 返工 #8：白名单**精确匹配**，不能靠"先导入父包"绕开。

    初版用前缀匹配判断，于是 `from hangma_bot.policy import heuristics` 能过——
    而 `policy.heuristics` 正是候选注册表（README 明确禁止的自动上线通道）。
    """

    body = VALID_CANDIDATE.split("\n", 1)[1]
    report = gen.scan_generated_code(snippet + body)
    assert report.ok is False
    assert any("禁止的 import" in item for item in report.problems), report.problems


def test_scan_still_accepts_legitimate_import_forms():
    """收紧白名单不能把合法写法一起拒掉（多子模块 from、别名）。"""

    prefix = ("from hangma_bot.policy import evaluation_v1, heuristic_adapter\n"
              "from typing import Mapping as _M\n")
    report = gen.scan_generated_code(prefix + VALID_CANDIDATE.split("\n", 1)[1])
    assert report.ok is True, report.problems


@pytest.mark.parametrize("code, keyword", [
    ("from __future__ import annotations\n\n\ndef f():\n"
     "    def build_adjustment_from_params(params, source_fingerprint_value=''):\n"
     "        pass\n", "顶层"),
    ("def build_adjustment_from_params(x, y=''):\n    pass\n", "参数名"),
    ("def build_adjustment_from_params(params, source_fingerprint_value):\n    pass\n", "默认值"),
    ("def build_adjustment_from_params(params=''):\n    pass\n", "参数"),
])
def test_scan_checks_entry_signature(code, keyword):
    """★ 返工 #8 连带项：把"入口签名"真正纳入扫描（初版只查有没有同名函数）。"""

    problems = gen.scan_generated_code(code).problems
    assert problems, "应当拒绝"
    assert any(keyword in item for item in problems), problems


def test_scan_accepts_canonical_entry_signature():
    report = gen.scan_generated_code(VALID_CANDIDATE)
    assert report.ok is True and report.entry_present is True


def test_write_ledger_covers_every_artifact_shape(tmp_path, contract):
    """★ 返工 #13：写盘守卫要覆盖工具**实际写出的所有路径形态**。"""

    prompt = gen.build_i1_prompt(contract)
    reply_file = write_reply_file(tmp_path / "r.json", prompt_sha256=prompt.sha256,
                                  reply=reply_text(VALID_CANDIDATE))
    out_dir = tmp_path / "run"
    assert gen._main_with_internal(["i1", "--out", str(out_dir), "--backend", "replay",
                                    "--replay", str(reply_file)]) == 0
    row = json.loads((out_dir / "records.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    record = json.loads((out_dir / row["attempt_dir"] / "record.json").read_text(
        encoding="utf-8"))
    writes = record["writes"]
    paths = set(writes["paths"])
    for relative in ("records.jsonl", "budget.json", "summary.md"):
        assert relative in paths, relative
    for artifact in ("prompt.txt", "prompt.json", "reply_raw.txt", "parsed.json",
                     "candidate.py", "scan.json", "load.json", "record.json"):
        assert any(item.startswith("attempts/") and item.endswith("/" + artifact)
                   for item in paths), artifact
    assert writes["all_under_out"] is True and writes["outside_out"] == []
    assert writes["src_touched"] is False and writes["registry_dir_touched"] is False
    assert record["registration"]["wrote_to_src"] is False
    # 账本里的每条路径都必须**真的存在**（账本不是愿望清单）
    for item in paths:
        assert (out_dir / item).exists(), item


def test_cli_refuses_out_dir_inside_controlled_trees(tmp_path):
    """★ 返工 #11/#13：守卫要在**写第一个字节之前**拦住越界 --out。"""

    registry = gen.REPO / "src" / "hangma_bot" / "policy" / "heuristics"
    with pytest.raises(ValueError) as excinfo:
        gen._main_with_internal(["load", "--code", str(tmp_path / "x.py"),
                                 "--out", str(registry)])
    assert "不得指向" in str(excinfo.value)
    with pytest.raises(ValueError):
        gen._main_with_internal(["load", "--code", str(tmp_path / "x.py"),
                                 "--out", str(gen.REPO)])
    with pytest.raises(ValueError):
        gen._main_with_internal(["i1", "--out", str(gen.REPO / "src"), "--dry-run"])
    # 仓库外的普通目录照常可用
    assert gen.guard_out_dir(tmp_path / "ok") == (tmp_path / "ok").resolve()


def test_admission_block_is_dated_and_not_a_hardcoded_constant(tmp_path, contract):
    """★ 返工 #12：准入阻塞原因必须带 as-of 与出处，且不得再写死"3.P 未收口"。"""

    record, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE))
    blob = json.dumps(record, ensure_ascii=False)
    assert "3.P" not in blob, "3.P 已交付，不得再作为当前阻塞原因写死"
    admission = record["admission"]
    assert admission["eligible"] is False
    assert admission["status"] == "pending_admission"
    assert admission["as_of_utc"]
    checks = admission["checks"]
    assert checks["registry_source_match"]["checked"] is True
    assert checks["registry_source_match"]["value"] is False
    assert checks["gate_records_for_source"]["checked"] is True
    assert checks["human_review"]["checked"] is False, "无机器可核验项必须标出来"
    assert admission["blocking"] and admission["unfreeze_path"]
    assert record["registration"]["requires_human_review"] is True


def test_sampling_only_recorded_when_a_request_was_sent(tmp_path, contract):
    """★ 返工 #14：delegate/replay 没有发生采样，就不许写 sampling。"""

    replayed, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE), out_name="replay")
    assert replayed["model"]["sampling"] is None
    delegated, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE),
                           origin=gen.ORIGIN_DELEGATED, provider="p", model="m",
                           captured_at_utc="2026-09-15T00:00:00Z", delegator="lead",
                           out_name="delegate")
    assert delegated["model"]["sampling"] is None
    spec = gen.SamplingSpec(temperature=0.0, top_p=None, max_tokens=4096, seed=None)
    assert gen.sampling_record(gen.BACKEND_API, spec, sent=False) is None
    sent = gen.sampling_record(gen.BACKEND_API, spec, sent=True)
    assert sent["source"] == "request_body"
    assert sent["values_origin"] == "cli_args_or_defaults"
    assert sent["values"] == {"temperature": 0.0, "max_tokens": 4096}
    assert sent["omitted"] == ["seed", "top_p"]


def test_resolve_api_credentials_follows_the_required_order(tmp_path, monkeypatch):
    """凭据解析顺序：--config > SITIN_LLM_CONFIG > DEEPSEEK_API_KEY（仅密钥）> 默认路径。"""

    explicit = tmp_path / "explicit.json"
    explicit.write_text(json.dumps({"base_url": "https://explicit.invalid",
                                    "chat_path": "/chat/completions",
                                    "api_key": "sk-explicit-000000",
                                    "models": {"senior": "explicit-pro"}}),
                        encoding="utf-8")
    via_env = tmp_path / "env.json"
    via_env.write_text(json.dumps({"schema": "sitin-llm-credentials/1",
                                   "default_endpoint": "deepseek",
                                   "endpoints": {"deepseek": {
                                       "base_url": "https://env.invalid",
                                       "chat_path": "/v1/chat/completions",
                                       "api_key": "sk-env-000000",
                                       "models": {"senior": "env-pro"}}}}),
                       encoding="utf-8")
    chosen = gen.resolve_api_credentials(explicit, tier="senior")
    assert chosen["base_url"] == "https://explicit.invalid"
    assert chosen["model"] == "explicit-pro"
    assert chosen["source"] == "cli --config"
    monkeypatch.setenv(gen.CONFIG_ENV, str(via_env))
    from_env = gen.resolve_api_credentials(None, tier="senior")
    assert from_env["base_url"] == "https://env.invalid"
    assert from_env["chat_path"] == "/v1/chat/completions"
    assert from_env["model"] == "env-pro"
    assert from_env["source"] == "env {0}".format(gen.CONFIG_ENV)
    monkeypatch.delenv(gen.CONFIG_ENV)
    monkeypatch.setenv(gen.KEY_ONLY_ENV, "sk-keyonly-000000")
    key_only = gen.resolve_api_credentials(None)
    assert key_only["api_key"] == "sk-keyonly-000000"
    assert key_only["base_url"] == gen.DEFAULT_BASE_URL
    assert key_only["source"] == "env {0}".format(gen.KEY_ONLY_ENV)
    monkeypatch.delenv(gen.KEY_ONLY_ENV)
    monkeypatch.setattr(gen, "DEFAULT_CONFIG_PATH", tmp_path / "missing.json")
    with pytest.raises(gen.TransportError):
        gen.resolve_api_credentials(None)


def test_api_backend_never_puts_the_key_into_the_endpoint_host():
    backend = gen.ApiBackend("https://api.example.com/v1", "m", api_key="sk-secret-000000")
    assert backend.endpoint_host == "api.example.com"
    assert "sk-secret" not in backend.endpoint_host


# ------------------------------------------------------------------ api 后端真跑口径（Lead 新增要求）

class _ScriptedHandler(BaseHTTPRequestHandler):
    """可编排的 OpenAI 兼容 stub：content / reasoning_content / finish_reason 都能设。

    注意口径：这是**真实 HTTP 往返**，但 stub **不是模型**；真实模型那一次跑在证据目录里。
    """

    script: dict = {}
    received: list = []

    def do_POST(self):                                   # noqa: N802 —— 标准库命名
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        type(self).received.append({"path": self.path,
                                    "headers": dict(self.headers),
                                    "body": json.loads(raw)})
        message = {"content": self.script.get("content", "")}
        if self.script.get("reasoning") is not None:
            message["reasoning_content"] = self.script["reasoning"]
        payload = json.dumps({
            "model": self.script.get("model", "stub-model"),
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
            "choices": [{"message": message,
                         "finish_reason": self.script.get("finish_reason", "stop")}],
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture()
def scripted_server():
    def _start(script):
        _ScriptedHandler.script = dict(script)
        _ScriptedHandler.received = []
        server = HTTPServer(("127.0.0.1", 0), _ScriptedHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, "http://127.0.0.1:{0}".format(server.server_address[1])
    servers = []

    def _factory(script):
        server, base_url = _start(script)
        servers.append(server)
        return base_url

    try:
        yield _factory
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def _api_config(tmp_path, base_url, api_key="sk-local-stub-00000000"):
    """写一份**指向本地 stub** 的私有配置，避免任何测试意外打到真实端点。"""

    path = tmp_path / "api-config.json"
    path.write_text(json.dumps({"schema": "sitin-llm-credentials/1",
                                "default_endpoint": "stub",
                                "endpoints": {"stub": {
                                    "kind": "openai-compatible",
                                    "base_url": base_url,
                                    "chat_path": "/v1/chat/completions",
                                    "api_key": api_key,
                                    "models": {"senior": "stub-model"}}}}),
                    encoding="utf-8")
    return path


def test_api_backend_keeps_reasoning_out_of_the_reply_text(scripted_server):
    """★ 推理模型：正文在 content，思维链在 reasoning_content——**只取 content**。"""

    base_url = scripted_server({"content": reply_text(VALID_CANDIDATE),
                                "reasoning": "很长很长的思维链" * 10,
                                "finish_reason": "stop"})
    backend = gen.ApiBackend(base_url, "stub-model", chat_path="/v1/chat/completions",
                             api_key="sk-local-stub-00000000")
    reply = backend.complete("提示词")
    assert reply.text == reply_text(VALID_CANDIDATE)
    assert "思维链" not in reply.text
    assert reply.reasoning_present is True
    assert reply.reasoning_chars == len("很长很长的思维链" * 10)
    assert reply.finish_reason == "stop"
    assert reply.endpoint_host == "127.0.0.1"
    assert reply.model_requested == "stub-model"
    # 解析器只看到 content：能正常切出 (thought, code)
    assert gen.parse_model_reply(reply.text).status == gen.PARSE_OK


def test_cli_api_run_freezes_model_identity_and_sampling(tmp_path, scripted_server,
                                                         contract, monkeypatch):
    """★ api 真跑：端点主机 + 模型 id + **实际发出的采样参数**都进血缘。"""

    monkeypatch.setattr(gen, "DEFAULT_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv(gen.CONFIG_ENV, raising=False)
    monkeypatch.delenv(gen.KEY_ONLY_ENV, raising=False)
    base_url = scripted_server({"content": reply_text(VALID_CANDIDATE),
                                "finish_reason": "stop", "model": "stub-model-v2"})
    config = _api_config(tmp_path, base_url)
    out_dir = tmp_path / "run"
    assert gen._main_with_internal([
        "i1", "--out", str(out_dir), "--backend", "api", "--config", str(config),
        "--tier", "senior", "--temperature", "0", "--max-tokens", "4096",
        "--api-key-env", "SITIN_TEST_KEY"]) == 0
    row = json.loads((out_dir / "records.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    record = json.loads((out_dir / row["attempt_dir"] / "record.json").read_text(
        encoding="utf-8"))
    model = record["model"]
    assert model["model"] == "stub-model-v2", "响应回显的模型 id"
    assert model["model_requested"] == "stub-model"
    assert model["endpoint_host"] == "127.0.0.1"
    assert model["tier"] == "senior"
    assert model["credential_source"] == "cli --config"
    sampling = model["sampling"]
    assert sampling["source"] == "request_body"
    assert sampling["values"]["temperature"] == 0.0
    assert sampling["values"]["max_tokens"] == 4096
    # 未显式给的字段取 CLI 默认值并**确实进了请求体**；没有默认值的字段记为 omitted
    assert sampling["values"]["top_p"] == gen.DEFAULT_TOP_P
    assert sampling["omitted"] == ["seed"]
    assert record["reply"]["evidence_kind"] == gen.REPLY_CAPTURED
    assert record["reply"]["is_model_output"] is True
    assert record["reply"]["http_status"] == 200
    assert record["load"]["ok"] is True
    assert record["admission"]["status"] == "pending_admission"
    # 请求体里确实带了这些采样参数
    sent = _ScriptedHandler.received[-1]["body"]
    assert sent["temperature"] == 0.0 and sent["max_tokens"] == 4096


def test_cli_truncated_reply_is_rejected_then_repairable(tmp_path, scripted_server,
                                                         contract, monkeypatch):
    """★ finish_reason != stop ⇒ **被截断**，不得当合法回复解析，并按不合法进修复路径。"""

    monkeypatch.setattr(gen, "DEFAULT_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv(gen.CONFIG_ENV, raising=False)
    monkeypatch.delenv(gen.KEY_ONLY_ENV, raising=False)
    base_url = scripted_server({"content": "", "reasoning": "只有思维链" * 50,
                                "finish_reason": "length"})
    config = _api_config(tmp_path, base_url)
    out_dir = tmp_path / "run"
    assert gen._main_with_internal([
        "i1", "--out", str(out_dir), "--backend", "api", "--config", str(config),
        "--tier", "senior"]) == 0
    row = json.loads((out_dir / "records.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    record = json.loads((out_dir / row["attempt_dir"] / "record.json").read_text(
        encoding="utf-8"))
    assert record["parse"]["status"] == gen.PARSE_TRUNCATED
    assert record["load"]["ok"] is False
    # GL-1：解析未通过时不得给出指向不存在文件的 code 段
    assert record["code"]["stored"] is False
    assert record["code"]["sha256"] is None
    assert record["reply"]["chars"] == 0
    assert record["reply"]["reasoning_chars"] == len("只有思维链" * 50)
    # 拒绝诊断可以直接喂给 M1 修复提示词
    feedback = gen.feedback_from_diagnosis(record)
    assert "截断" in feedback


def test_api_key_never_appears_in_any_artifact(tmp_path, scripted_server, contract,
                                               monkeypatch):
    """★ 自检回归：产物目录里 grep 不到密钥子串。"""

    secret = "sk-super-secret-0123456789abcdef"
    monkeypatch.setattr(gen, "DEFAULT_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv(gen.CONFIG_ENV, raising=False)
    monkeypatch.delenv(gen.KEY_ONLY_ENV, raising=False)
    base_url = scripted_server({"content": reply_text(VALID_CANDIDATE),
                                "finish_reason": "stop"})
    config = _api_config(tmp_path, base_url, api_key=secret)
    out_dir = tmp_path / "run"
    assert gen._main_with_internal([
        "i1", "--out", str(out_dir), "--backend", "api", "--config", str(config),
        "--tier", "senior", "--api-key-env", "SITIN_TEST_KEY"]) == 0
    checked = 0
    for path in out_dir.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert secret not in text, path
            checked += 1
    assert checked >= 8
    # 凭据**来源**可以记（它是"哪来的"），密钥本身不行
    row = json.loads((out_dir / "records.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    record = json.loads((out_dir / row["attempt_dir"] / "record.json").read_text(
        encoding="utf-8"))
    assert record["model"]["credential_source"] == "cli --config"
    assert secret not in json.dumps(record, ensure_ascii=False)


def test_scan_rejects_parent_package_import_bypass_keeps_api_allowlist_intact():
    """收紧 import 白名单后，api 后端自己的模块不受影响（工具源码本身照常导入）。"""

    assert gen.scan_generated_code(VALID_CANDIDATE).ok is True

# ------------------------------------------------------------------ 追加返工项回归（GL-1…GL-10）

def test_write_ledger_refuses_to_write_credential_text(tmp_path):
    """★ GL-2：遮蔽复核必须覆盖**每个文本产物**，而不是只看 record dict。"""

    ledger = gen.WriteLedger(tmp_path / "out", secrets=("sk-super-secret-0123456789abcdef",))
    with pytest.raises(ValueError) as excinfo:
        ledger.write_text(tmp_path / "out" / "prompt.txt",
                          "key=sk-super-secret-0123456789abcdef")
    assert "检出凭据明文" in str(excinfo.value)
    assert not (tmp_path / "out" / "prompt.txt").exists(), "命中即**拒绝写出**"
    ledger.write_text(tmp_path / "out" / "ok.txt", "没有凭据")
    assert (tmp_path / "out" / "ok.txt").is_file()


def test_config_key_is_redacted_even_when_passed_via_config(tmp_path, monkeypatch):
    """★ GL-2：@@BT@@--config@@BT@@ 指定的密钥也要进遮蔽集合（不是只查环境变量）。"""

    secret = "sk-from-config-0123456789abcdef"
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"base_url": "https://example.invalid", "api_key": secret,
                                  "models": {"junior": "m"}}), encoding="utf-8")
    monkeypatch.delenv(gen.CONFIG_ENV, raising=False)
    monkeypatch.delenv(gen.KEY_ONLY_ENV, raising=False)
    creds = gen.resolve_api_credentials(config, tier="junior")
    assert secret in gen.collect_secrets(creds["api_key"])


def test_calls_budget_exhaustion_exits_cleanly(tmp_path, contract):
    """★ GL-3：预算耗尽要"保存状态并停止"（退出码 3），不是未捕获异常。"""

    prompt = gen.build_i1_prompt(contract)
    reply_file = write_reply_file(tmp_path / "r.json", prompt_sha256=prompt.sha256,
                                  reply=reply_text(VALID_CANDIDATE))
    out_dir = tmp_path / "run"
    assert gen._main_with_internal(["i1", "--out", str(out_dir), "--backend", "replay",
                                    "--replay", str(reply_file),
                                    "--calls-budget", "0"]) == 3
    ledger = json.loads((out_dir / "budget.json").read_text(encoding="utf-8"))
    assert ledger["spent_calls"] == 0, "预算耗尽时不得改写台账的已用计数"
    assert not (out_dir / "records.jsonl").exists()


def test_m1_repair_depth_limit_rejects_third_generation(tmp_path, contract):
    """★ GL-3：三级链必须在第 3 代被拒绝（初版注释这么写，断言却只看 depth==0）。"""

    record, out_dir = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE),
                              out_name="gen0")
    first = out_dir / record["attempt_dir"]
    record_path = first / "record.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["lineage"]["repair_depth"] = gen.DEFAULT_REPAIR_DEPTH
    record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    assert gen.parent_binding(first)["repair_depth"] == gen.DEFAULT_REPAIR_DEPTH
    feedback = tmp_path / "fb.md"
    feedback.write_text("反馈", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        gen._main_with_internal(["m1", "--out", str(out_dir), "--parent", str(first),
                                 "--feedback", str(feedback), "--backend", "replay",
                                 "--replay", str(tmp_path / "nope.json")])
    assert "修复深度超限" in str(excinfo.value)


def test_supervised_load_leaves_no_temp_directories(tmp_path):
    """★ GL-4：受监管装载的 mkdtemp 目录用完即删（不得在系统临时目录里堆积）。"""

    import tempfile

    code_path = tmp_path / "c.py"
    code_path.write_text(VALID_CANDIDATE, encoding="utf-8")
    pattern = "sitin-generate-load-*"
    before = set(Path(tempfile.gettempdir()).glob(pattern))
    assert gen.supervised_load(code_path, {}, timeout_sec=60).ok is True
    after = set(Path(tempfile.gettempdir()).glob(pattern))
    assert after <= before, "装载后不得留下新的临时目录：{0}".format(after - before)


def test_synthetic_facts_probe_is_recorded(tmp_path):
    """★ GL-5：冷启动探针判别力有限，必须另有一个**事实完整**探针并写清判别力。"""

    code_path = tmp_path / "c.py"
    code_path.write_text(VALID_CANDIDATE, encoding="utf-8")
    report = gen.supervised_load(code_path, {}, timeout_sec=60).report
    assert report["probe"]["discriminative_power"] == "smoke_only"
    synthetic = report["probe_synthetic_facts"]
    assert synthetic["discriminative_power"] == "mechanism_reachable"
    assert synthetic["ok"] is True
    assert all("delta" in case for case in synthetic["cases"])


def test_prompt_constants_come_from_their_sources():
    """★ GL-8：提示词里的跨模块常量必须与源头绑定（gang_bonus / G-1 单窗口上限）。"""

    from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

    assert gen.gang_bonus_reference() == float(DEFAULT_WEIGHTS_V1.gang_bonus)
    assert gen.gate_window_limit_ms() == 50.0
    text = gen.build_i1_prompt(gen.default_task_contract()).text
    assert "gang_bonus={0}".format(gen.gang_bonus_reference()) in text
    assert "硬上限为 {0:g} ms".format(gen.gate_window_limit_ms()) in text


def test_provenance_attestation_is_explicit(tmp_path, contract):
    """★ GL-9：封套自述 ≠ 工具观测；各来源的取证强度必须写清。"""

    fixtures, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE), out_name="fx")
    assert fixtures["reply"]["provenance_attestation"] == "human-authored-fixture"
    delegated, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE),
                           origin=gen.ORIGIN_DELEGATED, provider="p", model="m",
                           captured_at_utc="2026-09-15T00:00:00Z", delegator="d",
                           out_name="dg")
    assert delegated["reply"]["provenance_attestation"] == "envelope-self-declared"
    captured = gen.ModelReply(text="x", backend=gen.BACKEND_API, origin=gen.ORIGIN_CAPTURED,
                              provider="p", model="m", captured_at_utc="t", usage={})
    assert captured.provenance_attestation == "tool-observed-http"
    headless = gen.ModelReply(text="x", backend=gen.BACKEND_HEADLESS,
                              origin=gen.ORIGIN_HEADLESS, provider="p", model="m",
                              captured_at_utc="t", usage={})
    assert headless.provenance_attestation == "tool-observed-stdout-and-session-log"


def test_write_targets_all_flow_through_the_ledger():
    """★ GL-10：写盘目标只能由 WriteLedger 派生（结构回归，不只是子串检查）。"""

    source = Path(gen.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    ledger_class = next(node for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == "WriteLedger")
    allowed_lines = set()
    for node in ast.walk(ledger_class):
        if hasattr(node, "lineno"):
            allowed_lines.update(range(node.lineno,
                                       getattr(node, "end_lineno", node.lineno) + 1))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # 账本自己的写盘方法当然是允许的：只看"谁在写"。
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in ("writes", "ledger"):
                continue
            if node.func.attr in ("write_text", "write_bytes"):
                if node.lineno not in allowed_lines:
                    offenders.append((node.lineno, node.func.attr))
            if node.func.attr == "open":
                mode = ""
                for arg in node.args[1:2]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        mode = arg.value
                for keyword in node.keywords:
                    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                        mode = str(keyword.value.value)
                if ("w" in mode or "a" in mode) and node.lineno not in allowed_lines:
                    offenders.append((node.lineno, "open"))
    assert not offenders, "这些写盘调用绕过了 WriteLedger：{0}".format(offenders[:5])


def test_info_boundary_is_backend_aware(tmp_path, contract):
    """★ 返工：信息边界只在**工具自己发过请求**时才谈强弱。

    初版把所有非 headless 都写成 strong + "api 直连：无工具、无文件访问能力"，
    于是 delegate 与夹具记录里出现了**与事实不符**的断言（那不是直连），
    还与同一条记录的 provenance_attestation=envelope-self-declared 自相矛盾。
    """

    delegate, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE),
                          origin=gen.ORIGIN_DELEGATED, provider="p", model="m",
                          captured_at_utc="2026-09-15T00:00:00Z", delegator="d",
                          out_name="delegate")
    assert delegate["info_boundary"]["strength"] == "n/a"
    assert "没有向模型发出请求" in delegate["info_boundary"]["note"]
    assert "无工具、无文件访问能力" not in delegate["info_boundary"]["note"]
    fixture, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE), out_name="fixture")
    assert fixture["info_boundary"]["strength"] == "n/a"
    assert gen.info_boundary_block(None, gen.BACKEND_API)["strength"] == "strong"
    assert gen.info_boundary_block("weak", gen.BACKEND_HEADLESS)["strength"] == "weak"
    assert gen.info_boundary_block(None, gen.BACKEND_REPLAY)["strength"] == "n/a"


def test_module_docstring_has_no_stale_status_claims():
    """★ GL-10：docstring 里不得再留"本轮未执行/未收口"这类会被现实打脸的旧状态。"""

    doc = gen.__doc__ or ""
    for stale in ("本轮**未执行**", "3.P（REVIEW-8 修复核验 + 门禁语义收口）未收口",
                  "headless 本轮不实现"):
        assert stale not in doc, stale
    assert "headless" in doc, "docstring 必须说明默认通道"


# ------------------------------------------------------------------ 落盘证据的一致性

def test_committed_fixtures_still_match_the_current_prompt(contract):
    """★ 落盘的格式夹具必须与**当前**提示词哈希一致，否则它们证明不了任何东西。

    合同或模板一改，夹具的 prompt_sha256 就对不上，这里会立刻红——
    这正是要的 fail-closed：宁可测试失败，也不要让"旧夹具跑绿"冒充本轮结论。
    """

    fixtures = _project_file(_PROJECT_ROOT, _HERE.parent / "evidence" / "3.1-generation" / "fixtures")
    if not fixtures.is_dir():
        pytest.skip("证据目录不存在（夹具未生成）")
    prompt_sha = gen.build_i1_prompt(contract).sha256
    for name in ("i1-positive.json", "i1-negative-missing-thought.json",
                 "i1-negative-forbidden-import.json", "i1-negative-infinite-loop.json"):
        path = fixtures / name
        assert path.is_file(), name
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["prompt_sha256"] == prompt_sha, name
    positive = json.loads((fixtures / "i1-positive.json").read_text(encoding="utf-8"))
    parsed = gen.parse_model_reply(positive["reply"])
    assert parsed.status == gen.PARSE_OK
    assert gen.scan_generated_code(parsed.code).ok is True
    # 夹具不得伪装成模型输出
    assert positive["origin"] == gen.ORIGIN_FIXTURE


def _key_shape(value):
    """递归取**键结构**：只比字段有没有、层级对不对，不比取值。

    叶子一律记作 `leaf`：夹具那条记录的 provider/model 是 null，委派那条是字符串，
    这是**取值**差异（本来就是我们要区分的），不是结构差异。
    """

    if isinstance(value, dict):
        return {key: _key_shape(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_key_shape(item) for item in value[:1]]
    return "leaf"


def test_lineage_record_shape_is_backend_agnostic(tmp_path, contract):
    """★ 换后端**不改变血缘形状**：replay 与 delegate 产出的记录键结构必须完全一致。

    这是"将来换通道不会让证据形状变化"的可执行版本：只允许取值不同
    （evidence_kind / is_model_output / provider / model），不允许字段多一个少一个。
    """

    replayed, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE), out_name="replay")
    delegated, _ = _ingest(tmp_path, contract, reply_text(VALID_CANDIDATE),
                           origin=gen.ORIGIN_DELEGATED, provider="p", model="m",
                           captured_at_utc="2026-09-15T00:00:00Z", delegator="lead",
                           out_name="delegate")
    assert _key_shape(replayed) == _key_shape(delegated)
    assert replayed["reply"]["evidence_kind"] == gen.REPLY_FIXTURE
    assert delegated["reply"]["evidence_kind"] == gen.REPLY_DELEGATED
    assert replayed["reply"]["is_model_output"] is False
    assert delegated["reply"]["is_model_output"] is True
    for record in (replayed, delegated):
        assert record["admission"]["status"] == "pending_admission"
        assert record["load"]["equivalent_to_three_gates"] is False
        assert record["gates_run"] == []


def test_module_docstring_declares_no_auto_publish_channel():
    """工具自己必须把"没有自动上线通道"写在文档里（防止后来者加回自动注册）。"""

    text = (Path(gen.__file__)).read_text(encoding="utf-8")
    assert "没有自动上线通道" in text
    assert "equivalent_to_three_gates" in text
    assert "pending_admission" in text


# ============================================================
# D 包追加：action_value_v1 delegate emit 冒烟（新用例，不改上面任何用例）
# ============================================================


def test_action_value_delegate_emit_produces_handoff_with_four_contract_keys(tmp_path):
    """action_value_v1 delegate emit 端到端：三件交接件齐备、四键在场、
    prompt_sha256 与 prompt.txt 文件哈希逐字节一致。

    回归背景：_AvContractShim 曾直接回合同原始载荷，emit_prompt 读
    facts/limits/counterexamples/forbidden 四键时 KeyError，真实 I1
    delegate 生成被堵（D 包返工项）。
    """

    import hashlib
    import subprocess

    out = tmp_path / "av-delegate-emit"
    result = subprocess.run(
        [sys.executable, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py")), "i1",
         "--candidate-kind", "action_value_v1", "--backend", "delegate",
         "--out", str(out), "--objective", "冒烟目标", "--panel-boundary", "冒烟面板"],
        capture_output=True, text=True, timeout=180, cwd=str(gen.REPO))
    assert result.returncode == 0, result.stdout[-400:] + result.stderr[-400:]
    pending = out / "pending" / "i1"
    for name in ("prompt.txt", "prompt.json", "delegation-request.json"):
        assert (pending / name).is_file(), name
    prompt_json = json.loads((pending / "prompt.json").read_text(encoding="utf-8"))
    # 四键（emit_prompt 的旧 delta 消费面）必须在场且非空。
    for key in ("allowed_surface", "limits", "counterexamples", "forbidden"):
        assert prompt_json.get(key), key
    # facts 映射：scoring_view + whitelist + predicates_binding。
    surface = prompt_json["allowed_surface"]
    for section in ("scoring_view", "whitelist", "predicates_binding"):
        assert surface.get(section), section
    # counterexamples=输出合同整批失败条件；forbidden=受限子集禁令（JSON 原文）。
    contract, _ = gen.load_action_value_contract()
    assert prompt_json["counterexamples"] == contract["output_contract"]["batch_failure_conditions"]
    assert prompt_json["forbidden"] == contract["restricted_subset"]["forbidden"]
    # 交接协议不改：schema 与 how_to_use 仍在。
    delegation = json.loads((pending / "delegation-request.json").read_text(encoding="utf-8"))
    assert delegation["schema"] == "sitin-generation-delegation/1"
    assert delegation["how_to_use"]
    # prompt_sha256 必须与 prompt.txt 文件哈希逐字节一致（委派方按文件对账）。
    file_sha = hashlib.sha256((pending / "prompt.txt").read_bytes()).hexdigest()
    assert prompt_json["prompt_sha256"] == file_sha
    # delegate emit 照常计一次调用额度（先预留后结算）。
    budget = json.loads((out / "budget.json").read_text(encoding="utf-8"))
    assert budget["spent_calls"] == 1
    assert any(entry["status"] == "completed"
               for entry in budget["entries"])


# ============================================================
# D 包追加二：action_value_v1 M1 父代绑定（新用例，不改上面任何用例）
# ============================================================

#: batch7 真实 I1 产物（sitin-action-value-generation/1）当夹具（目录）。
AV_PARENT_FIXTURE = (gen.REPO / "review/llm-guided-heuristic-route-2026-09-15"
                     / "evidence/v4-impl/batch7/gen/i1/attempts/i1-641296497a9b")
AV_FEEDBACK_FILE = (gen.REPO / "review/llm-guided-heuristic-route-2026-09-15"
                    / "evidence/v4-impl/batch7/feedback-i1.md")

#: 夹具是**目录**（record.json/candidate.py/parsed.json 在内）；用 is_dir 判在。
_AV_FIXTURE_READY = (AV_PARENT_FIXTURE / "record.json").is_file() and AV_FEEDBACK_FILE.is_file()


def _copy_parent_fixture(tmp_path):
    import shutil

    target = tmp_path / "parent"
    shutil.copytree(AV_PARENT_FIXTURE, target)
    return target


@pytest.mark.skipif(not _AV_FIXTURE_READY, reason="batch7 I1 父代夹具不可用")
def test_action_value_m1_emit_binds_new_schema_parent(tmp_path):
    """action_value_v1 M1 emit 端到端：新 schema 父代绑定跑通，三件交接件
    齐备、prompt 含父代源码（逐字）与三段反馈标记。

    回归背景：_run_generate_action_value 曾直调 legacy parent_binding（期望
    sitin-generation-record/1），对新产物 schema 抛 ValueError，真实 M1
    生成被堵（D 包第二项返工）。
    """

    import hashlib
    import subprocess

    parent = _copy_parent_fixture(tmp_path)
    out = tmp_path / "av-m1-emit"
    result = subprocess.run(
        [sys.executable, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py")), "m1",
         "--candidate-kind", "action_value_v1", "--backend", "delegate",
         "--out", str(out), "--parent", str(parent),
         "--feedback", str(AV_FEEDBACK_FILE),
         "--objective", "冒烟目标", "--panel-boundary", "冒烟面板"],
        capture_output=True, text=True, timeout=180, cwd=str(gen.REPO))
    assert result.returncode == 0, result.stdout[-400:] + result.stderr[-400:]
    pending = out / "pending" / "m1"
    for name in ("prompt.txt", "prompt.json", "delegation-request.json"):
        assert (pending / name).is_file(), name
    prompt_json = json.loads((pending / "prompt.json").read_text(encoding="utf-8"))
    file_sha = hashlib.sha256((pending / "prompt.txt").read_bytes()).hexdigest()
    assert prompt_json["prompt_sha256"] == file_sha
    # 血缘：父代身份 = candidate_id 与 prompt_sha256 组合。
    record = json.loads((parent / "record.json").read_text(encoding="utf-8"))
    expected_identity = "{0}:{1}".format(
        record["identity"]["candidate_id"], record["prompt"]["sha256"])
    assert prompt_json["parent_identity"] == expected_identity
    # 提示词含父代源码（逐字）与三段反馈段（反馈文件内容进 facts 段）。
    prompt = (pending / "prompt.txt").read_text(encoding="utf-8")
    assert "父代代码（逐字）" in prompt
    assert "父代机制说明（逐字）" in prompt
    assert "三段开发反馈" in prompt
    parent_code = (parent / "candidate.py").read_text(encoding="utf-8").rstrip(chr(10))
    assert parent_code in prompt
    feedback_text = AV_FEEDBACK_FILE.read_text(encoding="utf-8").strip()
    assert feedback_text[:60] in prompt


@pytest.mark.skipif(not _AV_FIXTURE_READY, reason="batch7 I1 父代夹具不可用")
def test_action_value_parent_binding_rejects_tampered_code(tmp_path):
    """父代代码与记录不一致（篡改 candidate.py 一字节）→ 按同款 ValueError 拒绝。"""

    parent = _copy_parent_fixture(tmp_path)
    code_path = parent / "candidate.py"
    original = code_path.read_text(encoding="utf-8")
    code_path.write_text(original + "# tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="父代代码与记录不一致"):
        gen.av_parent_binding(parent)


@pytest.mark.skipif(not _AV_FIXTURE_READY, reason="batch7 I1 父代夹具不可用")
def test_action_value_parent_binding_rejects_parse_failed_parent(tmp_path):
    """父代解析未通过（改 parsed.json status 构造）→ 拒绝作修订基础。"""

    parent = _copy_parent_fixture(tmp_path)
    parsed_path = parent / "parsed.json"
    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    parsed["status"] = "missing_mechanism"
    parsed_path.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="父代解析未通过"):
        gen.av_parent_binding(parent)


@pytest.mark.skipif(not _AV_FIXTURE_READY, reason="batch7 I1 父代夹具不可用")
def test_action_value_parent_binding_shape_matches_legacy(tmp_path):
    """返回形状与 legacy parent_binding 同构；装载状态如实带入不遮掩。"""

    parent = _copy_parent_fixture(tmp_path)
    bound = gen.av_parent_binding(parent)
    legacy_keys = {"dir", "identity", "code_sha256", "record_sha256", "operator",
                   "thought", "code", "load_ok", "repair_depth", "verified"}
    assert legacy_keys <= set(bound)
    record = json.loads((parent / "record.json").read_text(encoding="utf-8"))
    assert bound["candidate_id"] == record["identity"]["candidate_id"]
    assert bound["prompt_sha256"] == record["prompt"]["sha256"]
    assert bound["identity"] == "{0}:{1}".format(bound["candidate_id"],
                                                 bound["prompt_sha256"])
    assert bound["code"] == (parent / "candidate.py").read_text(encoding="utf-8")
    assert bound["verified"] is True
    assert bound["load_ok"] == bool(record["load"]["ok"])
    # legacy parent_binding 仍只认旧 schema：新产物交给它必须拒绝（不重解释）。
    with pytest.raises(ValueError, match="schema 不符"):
        gen.parent_binding(parent)
