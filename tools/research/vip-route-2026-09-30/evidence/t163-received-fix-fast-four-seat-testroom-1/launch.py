"""完整回信回收修复后的独立工程实验：开一个M10/R8测试房，四席同配置自然完赛后下载。

默认只报告准备状态。--execute才有官方HTTP和参赛副作用；不会续房、
重试不确定建房POST、主动停止参赛进程或调整源代码。凭证只写.private。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t163-received-fix-fast-four-seat-testroom-1'

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
SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t163-vip-s02-testroom-v6")
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t163-vip-s02-testroom-v6')
PACKAGE = "0ed2a86ba5af972a9b5e7017fdbac477d5c3ed6a23eb13ddcc2b01ab5543d0b3"
HOST = "10.240.169.190"


def write_new(path, body, *, private=False):
    """新文件独占写入；不覆盖历史失败或凭证。私有文件权限为0600。"""
    with path.open("x") as stream:
        if private:
            os.fchmod(stream.fileno(), 0o600)
        json.dump(body, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


class PacedPublicClient:
    """只包公开档案GET；单调间隔以请求开始计，最多4次尝试，不吞429证据。"""

    def __init__(self, client):
        self.client = client
        self.previous_start = None
        self.request_number = 0

    def get(self, endpoint):
        """返回首次非429响应或最后一次429；正文原件与实际状态逐尝试记录。"""
        for attempt in range(1, 5):
            if self.previous_start is not None:
                time.sleep(max(0, self.previous_start + 2 - time.monotonic()))
            self.previous_start = time.monotonic()
            self.request_number += 1
            response = self.client.get(endpoint)
            body = response.content
            name = f"attempt-{self.request_number:03d}.bin"
            (_project_file(_PROJECT_ROOT, HERE / name)).write_bytes(body)
            row = {"actual_request_no": self.request_number, "logical_endpoint": endpoint, "attempt": attempt,
                   "http_status": response.status_code, "elapsed_seconds": time.monotonic() - self.previous_start,
                   "response_headers": {k: response.headers[k] for k in ("date", "retry-after", "content-type")
                                        if k in response.headers}, "body_file": name,
                   "body_sha256": hashlib.sha256(body).hexdigest()}
            with (_project_file(_PROJECT_ROOT, HERE / "CAPTURE-RETRY-ACTUAL-HTTP.jsonl")).open("a") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            if response.status_code != 429:
                return response
            if attempt < 4:
                try:
                    pause = max(2, float(response.headers.get("retry-after", "2")))
                except ValueError:
                    pause = 2
                time.sleep(min(pause, 60))
        return response

def require_confirmation():
    """本批只验并发工程，要求本轮自由赛真实闭合及新包完整绑定。"""
    closed = _project_file(_PROJECT_ROOT, HERE.parent / "t161-received-fix-paced-experimental-free-1")
    assert json.loads((closed / "ACTUAL-OUTER-TERMINAL.json").read_text())["actual_exit_code"] == 0
    assert json.loads((closed / "SUMMARY-TOOL-TERMINAL.json").read_text())["actual_exit_code"] == 0
    summary = json.loads((closed / "ROOM-AUDIT-SUMMARY.json").read_text())
    assert summary["strict_full_plan_zero_fault_gate"] is True
    assert summary["unique_tables"] == 10 and summary["unique_hands"] == 80
    assert summary["our_discard_timeouts"] == 0
    assert json.loads((closed / "LIVE-BUDGET-DIAGNOSIS.json").read_text())["zero_plan_count"] == 0
    terminal = summary["participant_terminal_record"]["decision_compute"]
    assert terminal["closed"] and terminal["live_processes"] == terminal["transport_threads_alive"] == 0
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
    require_confirmation()
    if not args.execute:
        print({"prepared": True, "room_created": False, "http_calls": 0,
               "tables_started": 0, "engineering_acceptance_required": True, "strength_admission": False})
        return
    os.chdir(ROOT)
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
    config = json.loads((_project_file(_PROJECT_ROOT, ROOT / "configs/vip-s02-bounded-d1-v6.test-room.example.json")).read_text())
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
        "previous_free_summary_sha256": hashlib.sha256((_project_file(_PROJECT_ROOT, HERE.parent / "t161-received-fix-paced-experimental-free-1/ROOM-AUDIT-SUMMARY.json")).read_bytes()).hexdigest(),
        "pacing_enabled": False, "reason": "四席同配置快速弃牌，检验高事件密度；不声称缺时间依据的缓发生效",
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
    assert run.returncode == 0, "参赛自然结束失败，保留原件不自动开第二房"
    from hangma_bot.bootstrap import build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    captures = []
    with build_public_archive_client(config) as client:
        wrapped = PacedPublicClient(client)
        for batch in range(10):
            time.sleep(2)
            captures.append(collect_test_room(wrapped, room["room_id"], batch, SESSION))
    write_new(_project_file(_PROJECT_ROOT, HERE / "OFFICIAL-CAPTURE.json"), {"room_id": room["room_id"], "ten_tables": captures})
    postgame = subprocess.run([sys.executable, "scripts/audit_tool.py", "postgame", str(SESSION),
                              "--rule-config", str(_project_file(_PROJECT_ROOT, PRIVATE / "rule-config.json"))], env=runtime_env)
    write_new(_project_file(_PROJECT_ROOT, HERE / "POSTGAME-CHILD-TERMINAL.json"), {"exit_code": postgame.returncode})
    raise SystemExit(0 if run.returncode == postgame.returncode == 0 else 1)


if __name__ == "__main__":
    main()
