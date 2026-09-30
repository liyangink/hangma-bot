"""VIP生成档只用人工回复与假传输；不读真实凭据、不调用模型或桌赛。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.vip_eoh_generate import (
    VIP_EOH_BATCH_SCHEMA, VipEohBatch, VipEohError, VipEohLedger,
    build_vip_eoh_prompt, legacy_generation_tools, load_vip_parents,
    numeric_constant_manifest, parse_vip_eoh_reply, reconcile_vip_eoh_call,
    run_vip_eoh_generate, write_vip_seed_parent,
)
from hangma_bot.offline import vip_eoh_generate
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE, VipRouteProjectionLimits,
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def batch_file(tmp_path):
    path = tmp_path / "batch.json"
    write_json(path, {
        "schema": VIP_EOH_BATCH_SCHEMA, "batch_id": "synthetic-format-tests",
        "budgets": {"model_calls": 30, "input_tokens": 20_000_000,
                    "output_tokens": 200_000, "table_instances": 0, "wall_clock_seconds": 1000},
        "per_call": {"input_tokens": 400_000, "max_tokens": 4096, "timeout_seconds": 20},
        "max_operations": 100_000, "projection_limits": asdict(VipRouteProjectionLimits()),
        "rule_config": asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False)),
        "route_limits": asdict(ValueAnalysisLimits(max_expansions=8192)),
        "input_bound": {"kind": "verified_model_input_limit", "model": "synthetic-request",
                        "max_input_tokens": 400_000,
                        "evidence": {"sources": ["synthetic-unit-test-evidence"],
                                     "verified_on": "2026-09-30", "interpretation": "仅假传输的人工上限"}},
        "sampling": {"temperature": None, "top_p": None, "seed": None},
    })
    return path


def reply_text(operator, source=VIP_ROUTE_HEURISTIC_SEED_SOURCE, parents=(), changes=()):
    mechanism = {
        "operator": operator, "trigger": "仅人工格式与故障测试", "changed_branches": "全动作统一排名",
        "expected_direction": "预期声明，未测行为效果", "counterexample": "过早偏好保白可能失去普通出口",
        "parent_differences": [{"candidate_id": parent["identity"]["candidate_id"],
                                "expected_change": "预期改变部分选择，尚未实测",
                                "window_classes": ["draw_discard"], "action_keys": ["discard:1w"],
                                "status": "expected"} for parent in parents],
        "parameter_changes": list(changes),
    }
    return "{人工测试联合机制}\n```json\n" + json.dumps(mechanism, ensure_ascii=False) + "\n```\n```python\n" + source + "\n```\n"


def fake_api(batch_file, text, *, usage=None, finish="stop", source="response_body", note=None,
             failure=False, delay=0):
    """注入假传输；隔离子进程证明预留与发起标记都先持久化。"""

    tools = legacy_generation_tools()

    class Transport:
        _api_key = "synthetic-test-secret-key"
        model = "synthetic-request"

        def complete(self, prompt):
            ledger = json.loads(batch_file.with_suffix(".vip-eoh-ledger.json").read_bytes())
            row = ledger["reservations"][-1]
            assert row["status"] == "reserved" and row["call_started"] is True
            if delay:
                time.sleep(delay)
            if failure:
                raise RuntimeError(failure if isinstance(failure, str) else "Authorization: Bearer " + self._api_key)
            return tools.ModelReply(
                text=text, backend="api", origin=tools.ORIGIN_CAPTURED, provider="synthetic-test",
                model="synthetic-response-v1", model_requested="synthetic-request",
                captured_at_utc="2026-09-30T00:00:00Z", usage=usage or {},
                finish_reason=finish, http_status=200, usage_source=source, note=note,
            )

    def factory(kind, **kwargs):
        assert kind == "api"
        ledger = json.loads(batch_file.with_suffix(".vip-eoh-ledger.json").read_bytes())
        assert ledger["reservations"][-1]["status"] == "reserved"
        assert kwargs["sampling"].to_request_fields() == {"max_tokens": 4096}
        return Transport()

    return factory


def fixture_envelope(path, packet, text, *, prompt_hash=None, usage=None, origin="format_fixture", finish=None):
    value = {"schema": "sitin-generation-reply/1", "origin": origin, "author": "unit-test",
             "purpose": "人工格式夹具，不是模型候选", "prompt_sha256": prompt_hash or packet.sha256,
             "reply": text, "usage": usage or {}, "finish_reason": finish}
    if origin == "model_capture":
        value.update(provider="historical-self-declared", model="historical-model",
                     captured_at_utc="2026-09-30T00:00:00Z")
    write_json(path, value)


@pytest.fixture
def seed_parent(batch_file, tmp_path):
    path = tmp_path / "seed"
    write_vip_seed_parent(path, batch_file)
    return path


def generate_model_parent(batch_file, path):
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE.replace("20.0", "21.0", 1)
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=path, operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1", source),
                                 usage={"prompt_tokens": 1200, "completion_tokens": 900}),
    )
    assert record["status"] == "loaded_not_admitted"
    return path


def test_emit_records_full_view_seed_and_never_reads_credentials(batch_file, tmp_path, monkeypatch):
    tools = legacy_generation_tools()
    monkeypatch.setattr(tools, "resolve_api_credentials", lambda *a, **kw: pytest.fail("must not read credentials"))
    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "emit", operator="i1",
                                  config=tmp_path / "nonexistent-private-config.json")
    assert record["status"] == "prompt_emitted" and record["parents"] == []
    assert record["billing"]["charged"]["model_calls"] == 0
    assert record["billing"]["charged"]["input_tokens"] == 0
    assert record["tables_run"] == 0 and record["publication"]["published"] is False
    prompt = (tmp_path / "emit/prompt.txt").read_text()
    assert "qualification_unknown_codes" in prompt and "max_waiting_draw_witnesses" in prompt
    assert "可能偏向k1" in prompt and "不证明1秒在线可用" in prompt
    assert json.dumps(VIP_ROUTE_HEURISTIC_SEED_SOURCE, ensure_ascii=False) in prompt
    appendix = json.loads((tmp_path / "emit/readonly-appendix.json").read_bytes())
    assert appendix["executor"]["rule_config"]["base_score"] == 1
    assert appendix["executor"]["route_limits"]["max_expansions"] == 8192


@pytest.mark.parametrize("operator", ["i1", "m1", "m2", "e1", "e2"])
def test_five_operator_fixture_paths(batch_file, seed_parent, tmp_path, operator):
    batch = VipEohBatch.read(batch_file)
    paths = [] if operator == "i1" else [seed_parent]
    if operator in ("e1", "e2"):
        paths.append(generate_model_parent(batch_file, tmp_path / "second-parent"))
    parents = load_vip_parents(paths, batch)
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE
    changes = []
    if operator == "m2":
        source = source.replace("20.0", "21.0", 1)
        old, new = numeric_constant_manifest(parents[0]["source"]), numeric_constant_manifest(source)
        changes = [{"ast_path": a["ast_path"], "before": a["value"], "after": b["value"],
                    "unit": "启发式点", "expected_change": "预期普通出口取舍改变", "overfit_risk": "过拟合开发窗口"}
                   for a, b in zip(old, new) if a["value"] != b["value"]]
    packet, _ = build_vip_eoh_prompt(batch, operator, parents, "人工开发反馈")
    reply = tmp_path / "fixture.json"
    fixture_envelope(reply, packet, reply_text(operator, source, parents, changes))
    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "fixture-out",
                                  operator=operator, backend="replay", parent_paths=paths,
                                  feedback="人工开发反馈", reply_file=reply)
    assert record["status"] == "loaded_not_admitted" and record["load"]["ok"]
    assert record["artifact_role"] == "format_fixture" and record["is_model_output"] is False
    assert record["admission"]["eligible"] is False and record["behavior_change_credit"] is False
    assert record["billing"]["charged"]["model_calls"] == 0
    assert record["billing"]["charged"]["output_tokens"] == 0
    assert [p["identity"]["candidate_id"] for p in record["parents"]] == [p["identity"]["candidate_id"] for p in parents]
    assert (tmp_path / "fixture-out/source-raw.py").exists()
    if operator == "m2":
        assert record["m2_scope"] == "numeric-literal m2"
        assert record["numeric_literal_changes"][0]["context_before"]


@pytest.mark.parametrize("operator,count", [("i1", 1), ("m1", 0), ("m2", 2), ("e1", 1), ("e2", 0)])
def test_operator_never_silently_changes_on_bad_parent_count(batch_file, seed_parent, operator, count):
    batch = VipEohBatch.read(batch_file)
    parents = load_vip_parents([seed_parent] * count, batch)
    with pytest.raises(VipEohError):
        build_vip_eoh_prompt(batch, operator, parents)


def test_ordered_multi_parent_hash_and_duplicate_guard(batch_file, seed_parent, tmp_path):
    batch = VipEohBatch.read(batch_file)
    second = generate_model_parent(batch_file, tmp_path / "second")
    parents = load_vip_parents([seed_parent, second], batch)
    forward, _ = build_vip_eoh_prompt(batch, "e2", parents)
    backward, _ = build_vip_eoh_prompt(batch, "e2", list(reversed(parents)))
    assert forward.sha256 != backward.sha256 and forward.parent_identity != backward.parent_identity
    with pytest.raises(VipEohError, match="不同候选"):
        build_vip_eoh_prompt(batch, "e1", [parents[0], parents[0]])
    with pytest.raises(VipEohError, match="顺序"):
        parse_vip_eoh_reply(reply_text("e2", parents=parents), "e2", list(reversed(parents)))


@pytest.mark.parametrize("field", ["source", "max_operations", "projection_limits", "rule_config", "route_limits", "profile"])
def test_parent_bytes_and_all_actual_identity_params_are_revalidated(batch_file, seed_parent, field):
    if field == "source":
        (seed_parent / "candidate.py").write_text(VIP_ROUTE_HEURISTIC_SEED_SOURCE + "\n")
    elif field == "profile":
        record = json.loads((seed_parent / "generation.json").read_bytes())
        record["profile"] = "old-profile"
        write_json(seed_parent / "generation.json", record)
    else:
        data = json.loads(batch_file.read_bytes())
        if field == "max_operations":
            data[field] += 1
        elif field == "projection_limits":
            data[field]["max_waiting_draw_witnesses"] += 1
        elif field == "rule_config":
            data[field]["base_score"] = 2
        else:
            data[field]["max_expansions"] += 1
        write_json(batch_file, data)
    with pytest.raises(VipEohError):
        load_vip_parents([seed_parent], VipEohBatch.read(batch_file))


def test_fixture_cannot_become_normal_parent(batch_file, tmp_path):
    batch = VipEohBatch.read(batch_file)
    packet, _ = build_vip_eoh_prompt(batch, "i1", [])
    path = tmp_path / "reply.json"
    fixture_envelope(path, packet, reply_text("i1"))
    run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "fixture", operator="i1",
                         backend="replay", reply_file=path)
    with pytest.raises(VipEohError):
        load_vip_parents([tmp_path / "fixture"], batch)


def test_numeric_literal_m2_permits_index_change_with_explicit_control_context():
    source = "def score_actions(view):\n    return view['actions'][0]\n"
    parents = [{"identity": {"candidate_id": "synthetic-parent"}, "source": source}]
    literal = numeric_constant_manifest(source)[0]
    declaration = {"ast_path": literal["ast_path"], "before": 0, "after": 1,
                   "unit": "索引", "expected_change": "改变所读索引", "overfit_risk": "漏根或越界风险"}
    parsed = parse_vip_eoh_reply(reply_text("m2", source.replace("[0]", "[1]"), parents, [declaration]), "m2", parents)
    assert parsed["numeric_literal_changes"][0]["literal_role"] == "control_or_index"


@pytest.mark.parametrize("change", ["logic", "no_change", "missing_declaration", "false_value"])
def test_m2_rejects_non_numeric_logic_and_incomplete_declarations(change):
    source = "def score_actions(view):\n    return 2.0 + len(view['actions'])\n"
    parents = [{"identity": {"candidate_id": "synthetic-parent"}, "source": source}]
    target = source.replace("2.0", "3.0")
    declaration = {"ast_path": numeric_constant_manifest(source)[0]["ast_path"], "before": 2.0, "after": 3.0,
                   "unit": "点", "expected_change": "预期改变", "overfit_risk": "过拟合"}
    if change == "logic":
        target = target.replace(" + ", " - ")
    elif change == "no_change":
        target = source
    elif change == "false_value":
        declaration["after"] = 4.0
    declarations = [] if change == "missing_declaration" else [declaration]
    with pytest.raises(VipEohError):
        parse_vip_eoh_reply(reply_text("m2", target, parents, declarations), "m2", parents)


def test_m2_real_string_cannot_collide_with_numeric_ast_marker():
    source = "def score_actions(view):\n    return 2.0 + 3.0\n"
    target = "def score_actions(view):\n    return '<numeric_parameter>' + 4.0\n"
    parent = {"identity": {"candidate_id": "synthetic-parent"}, "source": source}
    change = {"ast_path": numeric_constant_manifest(source)[0]["ast_path"], "before": 2.0, "after": 4.0,
              "unit": "点", "expected_change": "碰撞不得通过", "overfit_risk": "并非数值调整"}
    with pytest.raises(VipEohError, match="AST结构不同"):
        parse_vip_eoh_reply(reply_text("m2", target, [parent], [change]), "m2", [parent])


@pytest.mark.parametrize("mutation", ["second_fence", "operator", "duplicate_json", "no_thought"])
def test_exact_reply_shape_and_mechanism_keys(mutation):
    text = reply_text("i1")
    if mutation == "second_fence":
        text += "```python\ndef score_actions(view): return 0\n```\n"
    elif mutation == "operator":
        text = text.replace('"operator": "i1"', '"operator": "m1"')
    elif mutation == "duplicate_json":
        text = text.replace('"operator": "i1"', '"operator": "i1", "operator": "i1"')
    else:
        text = text.replace("{人工测试联合机制}", "")
    with pytest.raises(VipEohError):
        parse_vip_eoh_reply(text, "i1", [])


@pytest.mark.parametrize("account", ["model_calls", "input_tokens", "output_tokens", "wall_clock_seconds"])
def test_zero_budget_never_constructs_api_or_reads_config(batch_file, tmp_path, account):
    data = json.loads(batch_file.read_bytes())
    data["budgets"][account] = 0
    write_json(batch_file, data)
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "blocked", operator="i1", backend="api",
        config=tmp_path / "unread-private.json",
        backend_factory=lambda *a, **kw: pytest.fail("budget must block credential construction"),
    )
    assert record["status"] == "failed" and "billing" not in record


def test_too_small_input_bound_rejected_before_credentials(batch_file, tmp_path):
    data = json.loads(batch_file.read_bytes())
    data["per_call"]["input_tokens"] = 1
    write_json(batch_file, data)
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "blocked", operator="i1", backend="api",
        backend_factory=lambda *a, **kw: pytest.fail("must block before credentials"),
    )
    assert record["status"] == "failed"
    assert record["input_reservation_evidence"]["minimum_reserved_tokens"] > 1
    assert not batch_file.with_suffix(".vip-eoh-ledger.json").exists()


@pytest.mark.parametrize("usage,source,expected", [({}, "response_body", (None, None)),
    ({"prompt_tokens": 0, "completion_tokens": None}, "response_body", (0, None)),
    ({"prompt_tokens": True, "completion_tokens": 1.5}, "response_body", (None, None)),
    ({"prompt_tokens": 12, "completion_tokens": 13}, None, (None, None)),
    ({"prompt_tokens": 12, "completion_tokens": 13}, "response_body", (12, 13))])
def test_api_unknown_usage_preserves_reservation_and_raw_types(batch_file, tmp_path, usage, source, expected):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "api", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1"), usage=usage, source=source),
    )
    assert record["status"] == "loaded_not_admitted"
    assert record["billing"]["charged"]["model_calls"] == 1
    for name, value, reservation in zip(("input_tokens", "output_tokens"), expected, (400_000, 4096)):
        assert record["billing"]["actual"][name] == value
        assert record["billing"]["charged"][name] == (reservation if value is None else value)
    assert record["usage"]["raw"] == usage
    assert record["usage"]["raw_types"] == {k: type(v).__name__ for k, v in usage.items()}
    assert record["model_identity"]["source"] == "response_body"


def test_truncation_retains_full_reply_cost_and_never_loads(batch_file, tmp_path):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "truncated", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1"), finish="length",
                                 usage={"prompt_tokens": 12, "completion_tokens": 4096}),
    )
    assert record["status"] == "truncated" and not record["load"]["ok"]
    assert record["billing"]["charged"]["output_tokens"] == 4096
    assert (tmp_path / "truncated/reply.txt").exists()
    assert not (tmp_path / "truncated/candidate.py").exists()


def test_api_exception_retains_unknown_cost_and_no_secret(batch_file, tmp_path):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "failed", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, "", failure=True),
    )
    assert record["status"] == "failed" and record["billing"]["charged"]["model_calls"] == 1
    assert record["billing"]["actual"]["input_tokens"] is None
    assert record["billing"]["charged"]["input_tokens"] == 400_000
    assert "synthetic-test-secret-key" not in (tmp_path / "failed/generation.json").read_text()


def test_isolated_http_quota_error_is_actionable_without_raw_auth_url_or_config(batch_file, tmp_path):
    error_text = ('模型调用失败：HTTP 429；响应尾部：{"code":"insufficient_quota"}; '
                  'https://example.invalid/private?key=synthetic-test-secret-key '
                  'Authorization: Bearer synthetic-test-secret-key config={"api_key":"private-unknown"}')
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "quota", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, "", failure=error_text),
    )
    assert record["status"] == "failed"
    assert record["error"]["category"] == "quota_exhausted"
    assert record["error"]["http_status"] == 429
    assert record["error"]["provider_error_code"] == "insufficient_quota"
    assert record["error"]["phase"] == "model_call"
    stored = (tmp_path / "quota/generation.json").read_text()
    assert "https://example.invalid" not in stored and "private-unknown" not in stored
    assert "synthetic-test-secret-key" not in stored
    assert record["billing"]["actual"]["input_tokens"] is None


@pytest.mark.parametrize("feedback", ["Authorization: Bearer synthetic-review-feedback-token",
    "Bearer synthetic-review-feedback-token", "Authorization: Basic c3ludGhldGlj", "Authorization: Bearer short",
    '私有配置误贴 {"api_key": "synthetic-review-api-key"}', "api_key = 'synthetic-review-api-key'"])
def test_emit_rejects_obvious_raw_auth_before_any_artifact_or_credential_read(batch_file, tmp_path, monkeypatch, feedback):
    tools = legacy_generation_tools()
    monkeypatch.setattr(tools, "resolve_api_credentials", lambda *a, **kw: pytest.fail("preview cannot read credentials"))
    with pytest.raises(VipEohError, match="认证明文"):
        run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "secret-preview",
                             operator="i1", feedback=feedback)
    assert not (tmp_path / "secret-preview").exists()
    assert not batch_file.with_suffix(".vip-eoh-ledger.json").exists()


def test_api_known_key_found_in_prior_raw_prompt_is_removed_and_never_sent(batch_file, tmp_path):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "secret-input", operator="i1", backend="api",
        feedback="偶然混入已知密钥 synthetic-test-secret-key",
        backend_factory=fake_api(batch_file, reply_text("i1")),
    )
    assert record["status"] == "failed" and record["error"]["phase"] == "backend_configuration"
    assert record["billing"]["charged"]["model_calls"] == 0
    assert "prompt.txt" in record["sensitive_material_removed"]
    assert not (tmp_path / "secret-input/prompt.txt").exists()
    for path in (tmp_path / "secret-input").rglob("*"):
        if path.is_file():
            assert b"synthetic-test-secret-key" not in path.read_bytes()


def test_unknown_input_limit_can_emit_but_api_cannot_read_credentials(batch_file, tmp_path):
    data = json.loads(batch_file.read_bytes())
    data["input_bound"] = None
    write_json(batch_file, data)
    emitted = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "unknown-emit", operator="i1")
    assert emitted["status"] == "prompt_emitted"
    blocked = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "unknown-api", operator="i1", backend="api",
        backend_factory=lambda *a, **kw: pytest.fail("unknown input limit blocks credentials"),
    )
    assert blocked["status"] == "failed" and "billing" not in blocked
    assert blocked["input_reservation_evidence"]["minimum_reserved_tokens"] is None


def test_cli_model_mismatch_blocks_before_credentials(batch_file, tmp_path):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "wrong-model", operator="i1", backend="api", model="another-model",
        backend_factory=lambda *a, **kw: pytest.fail("model mismatch blocks credentials"),
    )
    assert record["status"] == "failed" and "billing" not in record


def test_actual_transport_model_mismatch_never_sends_call(batch_file, tmp_path):
    factory = fake_api(batch_file, reply_text("i1"))

    def wrong_model(kind, **kwargs):
        transport = factory(kind, **kwargs)
        transport.model = "resolved-wrong-model"
        return transport

    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "wrong-resolved-model",
                                  operator="i1", backend="api", backend_factory=wrong_model)
    assert record["status"] == "failed" and record["error"]["phase"] == "backend_configuration"
    assert record["billing"]["charged"]["model_calls"] == 0


def test_nested_json_redaction_preserves_shape(batch_file, tmp_path):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "redacted", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1"),
                                 note="Authorization: Bearer synthetic-test-secret-key\n后续字段保留"),
    )
    assert record["status"] == "loaded_not_admitted"
    assert record["reply"]["note"] == "Authorization: [REDACTED]\n后续字段保留"
    stored = (tmp_path / "redacted/generation.json").read_text()
    assert "synthetic-test-secret-key" not in stored and json.loads(stored)["parents"] == []


def test_unknown_inflight_call_requires_explicit_review_and_is_never_resent(batch_file, tmp_path):
    batch = VipEohBatch.read(batch_file)
    ledger = VipEohLedger(batch_file, batch)
    ledger.reserve("interrupted-call", "api")
    ledger.mark_call_started("interrupted-call")
    with pytest.raises(VipEohError, match="未结算"):
        ledger.reserve("new-call", "api")
    with pytest.raises(VipEohError):
        reconcile_vip_eoh_call(batch_file, "interrupted-call", review_note="")
    with pytest.raises(VipEohError, match="零次"):
        ledger.settle("interrupted-call", actual={"model_calls": 0, "input_tokens": 0,
                      "output_tokens": 0, "table_instances": 0, "wall_clock_seconds": 1}, outcome="wrong")
    recovered = reconcile_vip_eoh_call(batch_file, "interrupted-call", review_note="人工确认结果未知，保留全部预留")
    assert recovered["charged"]["model_calls"] == 1 and recovered["charged"]["input_tokens"] == 400_000
    assert recovered["actual"]["wall_clock_seconds"] is None
    with pytest.raises(VipEohError, match="重复"):
        ledger.reserve("interrupted-call", "api")
    assert ledger.reserve("separate-new-attempt", "emit")["attempt_no"] == 2


def test_api_absolute_timeout_terminates_worker_and_keeps_cost(batch_file, tmp_path):
    # 假传输会长期阻塞；外部隔离截止须无需等待该阻塞返回。
    data = json.loads(batch_file.read_bytes())
    data["per_call"]["timeout_seconds"] = 0.2
    write_json(batch_file, data)
    times = iter((0.0, 0.0, 0.0, 0.0, 0.21))
    started = time.monotonic()
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "timeout", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1"), delay=10),
        now_monotonic=lambda: next(times),
    )
    assert time.monotonic() - started < 3
    assert record["status"] == "deadline_exceeded_invalid"
    assert record["billing"]["charged"]["model_calls"] == 1
    assert record["billing"]["charged"]["output_tokens"] == 4096


def test_same_output_dir_cannot_overwrite_previous_attempt(batch_file, tmp_path):
    path = tmp_path / "one"
    run_vip_eoh_generate(batch_file=batch_file, out_dir=path, operator="i1")
    before = (path / "generation.json").read_bytes()
    with pytest.raises(FileExistsError):
        run_vip_eoh_generate(batch_file=batch_file, out_dir=path, operator="i1", backend="api",
                             backend_factory=lambda *a, **kw: pytest.fail("cannot overwrite"))
    assert (path / "generation.json").read_bytes() == before


def test_replay_prompt_mismatch_is_failure_without_new_model_cost(batch_file, tmp_path):
    packet, _ = build_vip_eoh_prompt(VipEohBatch.read(batch_file), "i1", [])
    reply = tmp_path / "wrong.json"
    fixture_envelope(reply, packet, reply_text("i1"), prompt_hash="0" * 64)
    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "replay",
                                  operator="i1", backend="replay", reply_file=reply)
    assert record["status"] == "failed" and record["billing"]["charged"]["model_calls"] == 0


def test_historical_model_replay_preserves_usage_without_rebilling(batch_file, tmp_path):
    packet, _ = build_vip_eoh_prompt(VipEohBatch.read(batch_file), "i1", [])
    reply = tmp_path / "history.json"
    fixture_envelope(reply, packet, reply_text("i1"), origin="model_capture", finish="stop",
                     usage={"prompt_tokens": 123, "completion_tokens": 456})
    record = run_vip_eoh_generate(batch_file=batch_file, out_dir=tmp_path / "history",
                                  operator="i1", backend="replay", reply_file=reply)
    assert record["status"] == "loaded_not_admitted" and record["is_model_output"] is True
    assert record["reply"]["provenance_attestation"] == "envelope-self-declared"
    assert record["usage"]["raw"]["prompt_tokens"] == 123
    assert record["usage"]["billing_scope"] == "historical_not_rebilled"
    assert record["billing"]["charged"]["model_calls"] == 0
    assert record["billing"]["charged"]["input_tokens"] == 0


@pytest.mark.parametrize("backend", ["emit", "api"])
def test_framework_change_invalidates_new_package(batch_file, tmp_path, monkeypatch, backend):
    original = vip_eoh_generate.freeze_vip_identity
    calls = 0

    def changed_identity(source, **kwargs):
        nonlocal calls
        calls += 1
        identity = original(source, **kwargs)
        if calls >= 3:
            identity["deps_digest"] = "fault-injected-framework-byte-change"
        return identity

    monkeypatch.setattr(vip_eoh_generate, "freeze_vip_identity", changed_identity)
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "changed", operator="i1", backend=backend,
        backend_factory=fake_api(batch_file, reply_text("i1")),
    )
    assert record["status"] == "framework_changed_invalid" and record["identity_stable"] is False
    assert record["admission"]["eligible"] is False
    with pytest.raises(VipEohError):
        load_vip_parents([tmp_path / "changed"], VipEohBatch.read(batch_file))


def test_raw_reply_secret_is_redacted_and_rejected_before_source_load(batch_file, tmp_path):
    text = reply_text("i1").replace("人工测试联合机制", "synthetic-test-secret-key")
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "leaking", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, text),
    )
    assert record["status"] == "failed" and record["reply_redacted"] is True
    assert not record["load"]["ok"] and not (tmp_path / "leaking/candidate.py").exists()
    assert "synthetic-test-secret-key" not in (tmp_path / "leaking/reply.txt").read_text()
    assert record["billing"]["charged"]["model_calls"] == 1


def test_model_without_finish_evidence_fails_and_keeps_fees(batch_file, tmp_path):
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "unknown-finish", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1"), finish=None),
    )
    assert record["status"] == "finish_unknown"
    assert not record["load"]["ok"] and record["billing"]["charged"]["output_tokens"] == 4096


def test_actual_usage_over_budget_remains_charged_and_invalid(batch_file, tmp_path):
    data = json.loads(batch_file.read_bytes())
    data["budgets"]["output_tokens"] = 4096
    write_json(batch_file, data)
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "overrun", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1"),
                                 usage={"prompt_tokens": 123, "completion_tokens": 4097}),
    )
    assert record["status"] == "budget_exceeded_invalid"
    assert record["billing"]["charged"]["output_tokens"] == 4097
    with pytest.raises(VipEohError, match="预算不足"):
        VipEohLedger(batch_file, VipEohBatch.read(batch_file)).reserve("no-budget-borrowing", "api")


def test_static_illegal_source_never_executes_outside_executor(batch_file, tmp_path):
    source = "import pathlib\ndef score_actions(view):\n    return {}\n"
    record = run_vip_eoh_generate(
        batch_file=batch_file, out_dir=tmp_path / "unsafe", operator="i1", backend="api",
        backend_factory=fake_api(batch_file, reply_text("i1", source)),
    )
    assert record["status"] == "failed" and record["load"]["ok"] is False
    assert record["admission"]["eligible"] is False
    assert (tmp_path / "unsafe/candidate.py").read_text() == source.strip()
    assert record["source_sha256"] == hashlib.sha256((tmp_path / "unsafe/candidate.py").read_bytes()).hexdigest()
