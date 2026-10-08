"""通过公开命令入口验证赛前配置生成；网络用标准库边界替身，不启动参赛。"""

from __future__ import annotations

import importlib.util
import io
import json
import ssl
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SECRET = "fixture-not-a-real-tournament-token"


def load_script(name):
    """加载源码脚本以调用其公开入口；不访问运行内部状态。"""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load_script("resolve_tournament")
participant = load_script("run_participant")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """提供模板、文件凭证及可控制的只读服务端响应。"""
    template = tmp_path / "template.json"
    template.write_text(json.dumps({
        "mode": "official_tournament", "token_kind": "official",
        "base_url": "https://10.240.169.190:18080", "insecure_hosts": ["10.240.169.190"],
        "expected_tournament_id": "t_REPLACE_ME", "known_guide_version": 35,
        "token_env": "OLD_TEMPLATE_TOKEN", "audit_root": "artifacts/sessions/template/audit",
        "strategy": "weighted_heuristic", "sse_enabled": True,
        "discard_pacing_enabled": False, "source_namespace": "fixture-platform",
    }), encoding="utf-8")
    token_file = tmp_path / "participant.token"
    token_file.write_text(SECRET + "\n", encoding="utf-8")
    output = tmp_path / "private" / "participant.json"
    responses = {
        "/api/me": {"tournament_id": "t_fixture", "user_id": "fixture-user", "active_games": []},
        "/api/tournaments/me/rules": {"name": "示例赛事", "status": "pending", "config": {"M": 10, "Rounds": 8}},
    }
    requests = []
    handlers = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert request.get_method() == "GET"
            assert request.get_header("Authorization") == "Bearer " + SECRET
            response = responses[request.selector]
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps(response).encode())

    def build_opener(*items):
        handlers.extend(items)
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    args = ["--config", str(template), "--token-file", str(token_file), "--write-config", str(output)]
    return template, token_file, output, responses, requests, handlers, args


@pytest.mark.parametrize("mode,kind", [("official_tournament", "official"), ("test_tournament", "test")])
def test_generated_config_loads_in_frozen_entry(setup, mode, kind, capsys):
    template, token_file, output, _, requests, _, args = setup
    original = json.loads(template.read_text())
    original.update(mode=mode, token_kind=kind)
    template.write_text(json.dumps(original))
    assert resolver.main(args) == 0
    generated = json.loads(output.read_text())
    config = participant.load_config(output, token_file=str(token_file))
    assert config.expected_tournament_id == "t_fixture"
    assert config.mode.value == mode
    assert config.token == SECRET
    assert "token" not in generated and "token_env" not in generated
    assert generated["audit_root"].startswith("artifacts/sessions/" + mode.replace("_", "-"))
    assert generated["audit_root"].endswith("/audit")
    assert generated["audit_root"] != original["audit_root"]
    assert all(generated[key] == original[key] for key in (
        "strategy", "known_guide_version", "sse_enabled", "discard_pacing_enabled", "source_namespace"))
    assert len(requests) == 2
    assert output.stat().st_mode & 0o777 == 0o600
    text = capsys.readouterr()
    assert SECRET not in text.out + text.err + output.read_text()
    result = json.loads(text.out.splitlines()[-1].removeprefix("RESULT "))
    assert "--token-file" in result["start_command"]
    assert result["config_path"] == str(output)


@pytest.mark.parametrize("kind", ["official", "test"])
def test_documented_p0_templates_keep_release_binding(setup, kind):
    template, token_file, output, _, _, _, args = setup
    name = "vip-s03-rulefix-p0-approved-v3.{0}-tournament.example.json".format(kind)
    original = json.loads((ROOT / "configs" / name).read_text())
    template.write_text(json.dumps(original))
    assert resolver.main(args) == 0
    config = participant.load_config(output, token_file=str(token_file))
    assert config.expected_policy_release_id == original["expected_policy_release_id"]
    assert config.strategy == original["strategy"]


def test_environment_source_saved_without_secret(setup, monkeypatch, capsys):
    _, _, output, _, _, _, args = setup
    args[2:4] = ["--token-env", "NEW_TOURNAMENT_TOKEN"]
    monkeypatch.setenv("NEW_TOURNAMENT_TOKEN", SECRET)
    assert resolver.main(args) == 0
    generated = json.loads(output.read_text())
    assert generated["token_env"] == "NEW_TOURNAMENT_TOKEN"
    config = participant.load_config(output, environ={"NEW_TOURNAMENT_TOKEN": SECRET})
    assert config.token == SECRET
    text = capsys.readouterr()
    assert SECRET not in text.out + text.err + output.read_text()
    assert "--token-file" not in json.loads(text.out.splitlines()[-1][7:])["start_command"]


def test_explicit_audit_root_and_unique_default_sessions(setup):
    _, _, output, _, _, _, args = setup
    assert resolver.main(args + ["--audit-root", "artifacts/sessions/my-tournament/audit"]) == 0
    assert json.loads(output.read_text())["audit_root"] == "artifacts/sessions/my-tournament/audit"
    args[-1] = str(output.with_name("second.json"))
    assert resolver.main(args) == 0
    second = json.loads(Path(args[-1]).read_text())["audit_root"]
    args[-1] = str(output.with_name("third.json"))
    assert resolver.main(args) == 0
    assert json.loads(Path(args[-1]).read_text())["audit_root"] != second


def test_query_only_keeps_original_result_and_writes_nothing(setup, capsys):
    _, _, output, _, _, _, args = setup
    assert resolver.main(args[:-2]) == 0
    assert not output.exists()
    result = json.loads(capsys.readouterr().out.splitlines()[-1][7:])
    assert result["tournament_id"] == "t_fixture"
    assert "config_path" not in result


@pytest.mark.parametrize("expected", ["t_wrong", None, ""])
def test_real_target_mismatch_is_never_overwritten(setup, expected, capsys):
    template, _, output, _, _, _, args = setup
    data = json.loads(template.read_text())
    data["expected_tournament_id"] = expected
    template.write_text(json.dumps(data))
    assert resolver.main(args) == 2
    assert not output.exists()
    assert "不一致" in capsys.readouterr().err


def test_already_pinned_matching_target_is_accepted(setup):
    template, _, output, _, _, _, args = setup
    data = json.loads(template.read_text())
    data["expected_tournament_id"] = "t_fixture"
    template.write_text(json.dumps(data))
    assert resolver.main(args) == 0
    assert json.loads(output.read_text())["expected_tournament_id"] == "t_fixture"


@pytest.mark.parametrize("changes", [
    {"token_kind": "test"}, {"mode": "test_room"}, {"typo_field": True},
    {"strategy": "action_value:research"},
])
def test_invalid_runtime_configuration_is_not_written(setup, changes):
    template, _, output, _, _, _, args = setup
    data = json.loads(template.read_text())
    data.update(changes)
    template.write_text(json.dumps(data))
    assert resolver.main(args) == 2
    assert not output.exists()


def test_existing_config_is_preserved_without_network(setup):
    _, _, output, _, requests, _, args = setup
    output.parent.mkdir()
    output.write_text("previous private configuration")
    assert resolver.main(args) == 2
    assert output.read_text() == "previous private configuration"
    assert requests == []


@pytest.mark.parametrize("content", ["", SECRET + "\nsecond-secret"])
def test_invalid_token_file_rejected_before_requests(setup, content, capsys):
    _, token_file, output, _, requests, _, args = setup
    token_file.write_text(content)
    assert resolver.main(args) == 2
    assert not output.exists() and requests == []
    assert SECRET not in capsys.readouterr().err


@pytest.mark.parametrize("tournament_id", [None, "", 7])
def test_unbound_or_invalid_identity_does_not_generate_config(setup, tournament_id):
    _, _, output, responses, _, _, args = setup
    responses["/api/me"]["tournament_id"] = tournament_id
    assert resolver.main(args) == 11
    assert not output.exists()


@pytest.mark.parametrize("status,exit_code", [(401, 10), (500, 11)])
def test_server_error_body_cannot_leak_token(setup, status, exit_code, capsys):
    _, _, output, responses, _, _, args = setup
    responses["/api/me"] = urllib.error.HTTPError("https://platform/api/me", status, SECRET, {}, io.BytesIO(SECRET.encode()))
    assert resolver.main(args) == exit_code
    assert not output.exists()
    text = capsys.readouterr()
    assert SECRET not in text.out + text.err


def test_optional_rules_failure_still_allows_pinned_config(setup, capsys):
    _, _, output, responses, _, _, args = setup
    responses["/api/tournaments/me/rules"] = urllib.error.URLError(SECRET)
    assert resolver.main(args) == 0
    assert json.loads(output.read_text())["expected_tournament_id"] == "t_fixture"
    text = capsys.readouterr()
    assert "赛况摘要获取失败" in text.err
    assert SECRET not in text.out + text.err


@pytest.mark.parametrize("failure", [TimeoutError(SECRET), OSError(SECRET)])
def test_transport_failure_has_clear_exit_without_secret(setup, failure, capsys):
    _, _, output, responses, _, _, args = setup
    responses["/api/me"] = failure
    assert resolver.main(args) == 11
    assert not output.exists()
    text = capsys.readouterr()
    assert SECRET not in text.out + text.err


def test_non_utf8_token_file_rejected_without_traceback(setup):
    _, token_file, _, _, requests, _, args = setup
    token_file.write_bytes(b"\xff\xfe")
    assert resolver.main(args) == 2
    assert requests == []


@pytest.mark.parametrize("hosts", [None, "10.240.169.190", [7]])
def test_invalid_whitelist_rejected_before_network(setup, hosts):
    template, _, _, _, requests, _, args = setup
    data = json.loads(template.read_text())
    data["insecure_hosts"] = hosts
    template.write_text(json.dumps(data))
    assert resolver.main(args) == 2
    assert requests == []


@pytest.mark.parametrize("whitelisted", [True, False])
def test_proxy_and_certificate_exceptions_stay_with_configured_host(setup, whitelisted, monkeypatch):
    template, _, _, _, _, handlers, args = setup
    data = json.loads(template.read_text())
    data["insecure_hosts"] = ["10.240.169.190"] if whitelisted else []
    template.write_text(json.dumps(data))
    contexts = []
    original = ssl.create_default_context

    def make_context():
        context = original()
        contexts.append(context)
        return context

    monkeypatch.setattr(ssl, "create_default_context", make_context)
    assert resolver.main(args[:-2]) == 0
    proxies = [h for h in handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert bool(proxies) is whitelisted
    assert all(h.proxies == {} for h in proxies)
    assert contexts[0].verify_mode == (ssl.CERT_NONE if whitelisted else ssl.CERT_REQUIRED)


def test_insecure_flag_cannot_expand_host_whitelist(setup):
    template, _, _, _, requests, _, args = setup
    data = json.loads(template.read_text())
    data["insecure_hosts"] = []
    template.write_text(json.dumps(data))
    assert resolver.main(args[:-2] + ["--insecure"]) == 2
    assert requests == []


def test_actual_http_preparation_bypasses_proxy_and_refuses_redirect(tmp_path, monkeypatch, capsys):
    """真实本机 HTTP 验证标准库接线，只使用假凭证，不连接官方平台。"""
    requests = []
    redirect = False

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            assert self.headers["Authorization"] == "Bearer " + SECRET
            if redirect:
                self.send_response(302)
                self.send_header("Location", "https://other.invalid/credential-target")
                self.end_headers()
                return
            data = ({"tournament_id": "t_fixture", "user_id": "fixture-user"}
                    if self.path == "/api/me" else {"name": "本机测试"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": "http://127.0.0.1:1"})
    template = tmp_path / "template.json"
    template.write_text(json.dumps({
        "mode": "official_tournament", "token_kind": "official", "known_guide_version": 35,
        "base_url": "http://127.0.0.1:{0}".format(server.server_port),
        "insecure_hosts": ["127.0.0.1"], "expected_tournament_id": "t_REPLACE_ME",
        "audit_root": "unused", "strategy": "weighted_heuristic",
    }))
    token_file = tmp_path / "token"
    token_file.write_text(SECRET)
    output = tmp_path / "generated.json"
    args = ["--config", str(template), "--token-file", str(token_file), "--write-config", str(output)]
    try:
        assert resolver.main(args) == 0
        assert participant.load_config(output, token_file=str(token_file)).expected_tournament_id == "t_fixture"
        assert requests == ["/api/me", "/api/tournaments/me/rules"]
        redirect = True
        assert resolver.main(args[:-2]) == 11
        assert requests == ["/api/me", "/api/tournaments/me/rules", "/api/me"]
        text = capsys.readouterr()
        assert "HTTP 302" in text.err
        assert SECRET not in text.out + text.err
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)


def test_generation_requires_template_and_audit_override_requires_generation(setup):
    _, token_file, output, _, requests, _, args = setup
    assert resolver.main(["--token-file", str(token_file), "--write-config", str(output)]) == 2
    assert resolver.main(args[:-2] + ["--audit-root", "audit"]) == 2
    assert requests == []
