"""必要胡数学剪枝验收后的独立工程实验：开一个M10/R8测试房，四席同配置自然完赛后下载。

默认只报告准备状态。--execute才有官方HTTP和参赛副作用；不会续房、
重试不确定建房POST、主动停止参赛进程或调整源代码。凭证只写.private。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t155-pruned-s02-engineering-testroom-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t155-vip-s02-testroom-v5")
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t155-vip-s02-testroom-v5')
PACKAGE = "72f055c05f8e6b8200413b9737d53da56b70e869b22444816f82e50d547d9fe6"
HOST = "10.240.169.190"


def write_new(path, body, *, private=False):
    """新文件独占写入；不覆盖历史失败或凭证。私有文件权限为0600。"""
    with path.open("x") as stream:
        if private:
            os.fchmod(stream.fileno(), 0o600)
        json.dump(body, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def require_confirmation():
    """纯工程实验的独立范围；不修改或执行未通过强度门的T149方案。"""
    acceptance = _project_file(_PROJECT_ROOT, HERE.parent / "t154-hu-math-pruning-acceptance-1")
    terminal = json.loads((acceptance / "ACTUAL-TOOL-TERMINAL.json").read_text())
    assert terminal["actual_exit_code"] == 0 and terminal["complete_cases"] == 118
    closure_path = acceptance / "exact-run/CLOSURE.json"
    assert hashlib.sha256(closure_path.read_bytes()).hexdigest() == terminal["closure_sha256"]
    closure = json.loads(closure_path.read_text())
    assert closure["valid"] is True and closure["complete_cases"] == 118
    assembly = json.loads((acceptance / "ASSEMBLY-TOOL-TERMINAL.json").read_text())
    assert assembly["actual_exit_code"] == 0 and assembly["passed"] == 94
    plan = json.loads((acceptance / "PLAN.json").read_text())
    for relative, item in plan["runtime_source_manifest"].items():
        path = _project_file(_PROJECT_ROOT, ROOT / relative)
        assert path.stat().st_size == item["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], relative
    sys.path[:0] = [str(ROOT), str(_project_file(_PROJECT_ROOT, ROOT / "src"))]
    from hangma_bot.bootstrap import _load_vip_testroom_manifest
    package = _load_vip_testroom_manifest(PACKAGE)
    assert package["strength_admission"] is False and package["production_default"] is False
    assert package["allowed_modes"] == ["test_room"]


def main():
    """显式执行时建房一次、等待四身份自然终态，然后采集和规则复核。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print({"prepared": True, "room_created": False, "http_calls": 0,
               "tables_started": 0, "engineering_acceptance_required": True, "strength_admission": False})
        return
    os.chdir(ROOT)
    require_confirmation()
    assert not PRIVATE.exists() and not SESSION.exists(), "本次会话已有原件，不覆盖或重开"
    sys.path.insert(0, str(ROOT))
    from scripts.test_room_campaign_watchdog import portal_cookie
    import httpx
    PRIVATE.mkdir(mode=0o700)
    SESSION.mkdir(parents=True)
    payload = {"m": 10, "rounds": 8, "base_score": 1, "you_cai_bi_kao": False,
               "peng_timeout_sec": 1, "chi_timeout_sec": 1,
               "discard_timeout_sec": 3, "timeout_min": 30}
    # 只对配置的赛事内网关闭证书验证；不修改全局TLS或发送到其他主机。
    with httpx.Client(verify=False, trust_env=False, timeout=40.0,
                      headers={"Cookie": portal_cookie()}) as client:
        response = client.post(f"https://{HOST}:18080/portal/api/test-rooms", json=payload)
        (_project_file(_PROJECT_ROOT, PRIVATE / "create-response.bin")).write_bytes(response.content)
        (_project_file(_PROJECT_ROOT, PRIVATE / "create-response.bin")).chmod(0o600)
        if response.status_code != 200:
            raise RuntimeError(f"建房HTTP {response.status_code}；原件在私有目录，不自动重试")
        room = response.json()
    assert isinstance(room.get("room_id"), str) and room["room_id"].startswith("t_")
    assert len(room.get("players", ())) == 4
    assert len({player["token"].strip() for player in room["players"]}) == 4
    config = json.loads((_project_file(_PROJECT_ROOT, ROOT / "configs/vip-s02-bounded-d1-v5.test-room.example.json")).read_text())
    assert config["expected_policy_release_id"] == PACKAGE
    assert config["sse_enabled"] is True and config["discard_pacing_enabled"] is False
    config["expected_tournament_id"] = room["room_id"]
    config["audit_root"] = str(_project_file(_PROJECT_ROOT, SESSION / "audit"))
    for identity, player in zip(config["identities"], room["players"]):
        token = player["token"].strip()
        assert token
        token_path = _project_file(_PROJECT_ROOT, PRIVATE / (identity["slot"] + ".token"))
        with token_path.open("x") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(token + "\n")
        identity["token_file"] = str(token_path)
    write_new(_project_file(_PROJECT_ROOT, PRIVATE / "run.json"), config, private=True)
    write_new(_project_file(_PROJECT_ROOT, PRIVATE / "rule-config.json"), {"base_score": 1, "you_cai_bi_kao": False}, private=True)
    write_new(_project_file(_PROJECT_ROOT, HERE / "ROOM-CREATED-REDACTED.json"), {
        "room_id": room["room_id"], "requested_config": payload, "http_status": 200,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "package_id": PACKAGE,
        "engineering_closure_sha256": hashlib.sha256((_project_file(_PROJECT_ROOT, HERE.parent / "t154-hu-math-pruning-acceptance-1/exact-run/CLOSURE.json")).read_bytes()).hexdigest(),
        "scope": "engineering_only_not_strength_or_formal_admission",
        "all_four_same_configuration": True, "raw_response_kept_private": True})
    runtime_env = dict(os.environ)
    for key in ("NO_PROXY", "no_proxy"):
        runtime_env[key] = ",".join(filter(None, (runtime_env.get(key, ""), HOST)))
    print({"room_id": room["room_id"], "package_id": PACKAGE,
           "m": 10, "rounds": 8, "four_slots_same": True}, flush=True)
    started = time.monotonic()
    # 无timeout、不发送终止信号；一个身份失败也由现有入口等待其余席结束。
    run = subprocess.run([sys.executable, "scripts/run_test_room.py", "--config",
                          str(_project_file(_PROJECT_ROOT, PRIVATE / "run.json")), "--once"], env=runtime_env)
    write_new(_project_file(_PROJECT_ROOT, HERE / "ROOM-RUNNER-CHILD-TERMINAL.json"), {
        "exit_code": run.returncode, "child_exit_observed": True,
        "controller_sent_termination_signal": False,
        "duration_wall_seconds": time.monotonic() - started})
    postgame = subprocess.run([sys.executable, "scripts/audit_tool.py", "postgame", str(SESSION),
                              "--download", "--runtime-config", str(_project_file(_PROJECT_ROOT, PRIVATE / "run.json")),
                              "--room", room["room_id"], "--batch", "0", "--rule-config",
                              str(_project_file(_PROJECT_ROOT, PRIVATE / "rule-config.json"))], env=runtime_env)
    write_new(_project_file(_PROJECT_ROOT, HERE / "POSTGAME-CHILD-TERMINAL.json"), {"exit_code": postgame.returncode})
    raise SystemExit(0 if run.returncode == postgame.returncode == 0 else 1)


if __name__ == "__main__":
    main()
