"""通过简短入口验证只读检查、正式包绑定、凭证隔离和原运行入口委托。"""
from __future__ import annotations

import fcntl
import io
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

import pytest
from hangma_bot.bootstrap import build_runtime, runtime_config_from_mapping

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import participate

SECRET = "fixture-not-a-real-registration-token"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """真实批准模板配假 HTTP 边界；不连接官方平台或读取真实凭证。"""
    if sys.platform != "darwin" or platform.machine() != "arm64" or sys.version_info[:2] != (3, 11):
        pytest.skip("现有正式预编译包只覆盖 macOS arm64 CPython 3.11")
    (tmp_path / "configs").mkdir()
    for kind in ("official", "test"):
        name = f"vip-s03-rulefix-p0-approved-v4.{kind}-tournament.example.json"
        shutil.copyfile(ROOT / "configs" / name, tmp_path / "configs" / name)
        monkeypatch.delenv(f"HM_{kind.upper()}_TOURNAMENT_TOKEN", raising=False)
    token_file = tmp_path / "input.token"
    token_file.write_text(SECRET)
    responses = {
        "/api/me": {"tournament_id": "t_fixture", "user_id": "fixture-user", "active_games": []},
        "/api/tournaments/me/rules": {"name": "示例赛事", "status": "registering", "config": {"M": 10, "Rounds": 8}},
    }
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert request.get_method() == "GET"
            assert request.get_header("Authorization") == "Bearer " + SECRET
            body = responses[request.selector]
            if isinstance(body, Exception):
                raise body
            return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    return tmp_path, token_file, responses, requests


@pytest.mark.parametrize("kind", ["official", "test"])
def test_check_then_start_with_no_manual_config_or_token_flags(setup, monkeypatch, capsys, kind):
    root, token_file, _, requests = setup
    suffix = ["--test"] if kind == "test" else []
    assert participate.main(["check", "--token-file", str(token_file), *suffix], root=root) == 0
    assert [request.selector for request in requests] == ["/api/me", "/api/tournaments/me/rules"]
    folder = root / ".private/participate" / kind
    config_path = folder / "participant.json"
    data = json.loads(config_path.read_text())
    assert data["expected_tournament_id"] == "t_fixture"
    assert data["strategy"] == f"vip_s03_rulefix_p0_{kind}_tournament_v1"
    assert "token" not in data and "token_env" not in data
    assert SECRET not in config_path.read_text()
    assert config_path.stat().st_mode & 0o777 == 0o600
    assert (folder / "participant.token").stat().st_mode & 0o777 == 0o600
    original = config_path.read_bytes()
    assert participate.main(["check", *suffix], root=root) == 0
    assert config_path.read_bytes() == original
    assert len(requests) == 4

    started = []

    def original_entry(argv):
        args = participate.run_participant.build_arg_parser().parse_args(argv)
        config = participate.run_participant.load_config(Path(args.config), token_file=args.token_file)
        started.append(config)
        assert SECRET not in " ".join(argv)
        # 运行期间同一身份不能另启检查或覆盖配置、凭证。
        assert participate.main(["check", *suffix], root=root) == 2
        return 0

    monkeypatch.setattr(participate.run_participant, "main", original_entry)
    assert participate.main(["start", *suffix], root=root) == 0
    assert len(started) == 1 and started[0].token == SECRET
    assert started[0].mode.value == kind + "_tournament"
    assert len(requests) == 4  # start 全部交给原运行入口，没有额外的赛前 HTTP。
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert "尚未启动比赛" in output.out
    assert not list(folder.glob(".prepare-*"))


def test_rechecking_another_tournament_does_not_overwrite_prepared_identity(setup, capsys):
    root, token_file, responses, _ = setup
    args = ["check", "--token-file", str(token_file)]
    assert participate.main(args, root=root) == 0
    folder = root / ".private/participate/official"
    before = {name: (folder / name).read_bytes() for name in ("participant.json", "participant.token")}
    responses["/api/me"]["tournament_id"] = "t_other"
    assert participate.main(args, root=root) == 10
    assert all((folder / name).read_bytes() == body for name, body in before.items())
    assert "另一个赛事" in capsys.readouterr().err


def test_bad_token_does_not_leave_a_saved_credential_or_config(setup, capsys):
    root, token_file, responses, _ = setup
    responses["/api/me"] = urllib.error.HTTPError("https://platform.invalid", 401, SECRET, None, None)
    assert participate.main(["check", "--token-file", str(token_file)], root=root) == 10
    folder = root / ".private/participate/official"
    assert not (folder / "participant.json").exists()
    assert not (folder / "participant.token").exists()
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err


def test_first_token_can_be_entered_without_echo_and_is_reused(setup, monkeypatch, capsys):
    root, _, _, requests = setup
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts = []
    monkeypatch.setattr(participate.getpass, "getpass", lambda prompt: prompts.append(prompt) or SECRET)
    assert participate.main(["check"], root=root) == 0
    assert len(prompts) == 1
    assert participate.main(["check"], root=root) == 0
    assert len(prompts) == 1 and len(requests) == 4
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err


def test_start_before_check_and_changed_package_are_rejected_before_network(setup):
    root, token_file, _, requests = setup
    assert participate.main(["start", "--token-file", str(token_file)], root=root) == 2
    assert not requests
    assert participate.main(["check", "--token-file", str(token_file)], root=root) == 0
    config_path = root / ".private/participate/official/participant.json"
    data = json.loads(config_path.read_text())
    data["expected_policy_release_id"] = "0" * 64
    config_path.write_text(json.dumps(data))
    requests.clear()
    assert participate.main(["check"], root=root) == 2
    assert not requests


def test_held_identity_lock_rejects_a_second_process_before_reading_token(setup):
    root, _, _, requests = setup
    folder = root / ".private/participate/official"
    folder.mkdir(parents=True)
    with (folder / "participant.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert participate.main(["check"], root=root) == 2
    assert not requests


@pytest.mark.parametrize("kind", ["official", "test"])
def test_check_does_not_read_offline_evidence_directories(setup, monkeypatch, kind):
    """真实参赛配置必须在离线目录不可读时完成发布校验和赛事查询。"""
    root, token_file, _, requests = setup
    original_open = Path.open

    def runtime_open(path, *args, **kwargs):
        if path.is_relative_to(ROOT):
            relative = path.relative_to(ROOT)
            assert relative.parts[0] not in {"review", "datasets", "datamart", "game-records"}, (
                "参赛入口读取了离线目录: " + str(relative)
            )
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", runtime_open)
    suffix = ["--test"] if kind == "test" else []
    assert participate.main(["check", "--token-file", str(token_file), *suffix], root=root) == 0
    assert [request.selector for request in requests] == ["/api/me", "/api/tournaments/me/rules"]


@pytest.mark.parametrize("failure", ["missing", "modified"])
def test_check_rejects_missing_or_modified_published_evidence_before_network(setup, monkeypatch, failure):
    """离线目录退出运行依赖后，发布原件缺失或篡改仍必须在联网前拒绝。"""
    root, token_file, _, requests = setup
    evidence = ROOT / "prebuilt/vip-s03-rulefix-p0-release-evidence-v1/NATIVE-MECHANICAL-CLOSED.json"
    original_open = Path.open

    def evidence_open(path, *args, **kwargs):
        if path == evidence:
            if failure == "missing":
                raise FileNotFoundError("发布原件缺失")
            with original_open(path, "rb") as handle:
                return io.BytesIO(handle.read() + b" ")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", evidence_open)
    assert participate.main(["check", "--token-file", str(token_file)], root=root) == 2
    assert not requests
    assert not (root / ".private/participate/official/participant.json").exists()


@pytest.mark.asyncio
async def test_published_test_tournament_package_preheats_actual_policy_workers(setup):
    """稀疏源码树装配真实编译策略，预热十个专属计算进程；不运行赛事。"""
    root, _, _, _ = setup
    data = json.loads((root / "configs/vip-s03-rulefix-p0-approved-v4.test-tournament.example.json").read_text())
    data.pop("token_env", None)
    data.update(token=SECRET, base_url="https://platform.invalid", insecure_hosts=[],
                expected_tournament_id="t_fixture", audit_root=str(root / "audit"))
    unit = build_runtime(runtime_config_from_mapping(data))
    try:
        assert unit.compute is not None
        await unit.compute.start()
        resources = unit.compute.snapshot()
        assert resources["ready"] == resources["live_processes"] == 10
        assert resources["faults"] == 0
    finally:
        await unit.compute.close()
        await unit.session.aclose()
        await unit.sink.aclose(timeout_seconds=2.0)
    assert unit.compute.snapshot()["live_processes"] == 0


def test_shell_rejects_unsupported_platform_before_installing_anything(tmp_path):
    script = tmp_path / "participate.sh"
    shutil.copyfile(ROOT / "participate.sh", script)
    command = tmp_path / "uname"
    command.write_text("#!/bin/sh\necho Linux\n")
    command.chmod(0o755)
    result = subprocess.run(["/bin/bash", str(script), "check"],
                            env={"PATH": str(tmp_path)}, capture_output=True, text=True)
    assert result.returncode == 2 and "对应平台发布包" in result.stderr
    assert not (tmp_path / ".private").exists()
