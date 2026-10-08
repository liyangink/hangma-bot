"""T194仅一次四席M10/R2工程实测：隔离来源、独占建房、自然完赛，不续房。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
WORK = _project_file(_PROJECT_ROOT, '.private/t192-audit-workspace')
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t194-s03-e2-necessary-testroom-1')
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring/necessary-testroom-1')
SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t194-s03-e2-necessary-testroom-1")


def save(path, value, *, private=False):
    """独占保存原结果；真实凭证仅写权限0600的私有文件。"""
    with path.open("x") as stream:
        if private:
            os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    """先离线核包，再只发一次建房POST；任何未知结果不自动重试。"""
    sys.path[:0] = [str(_project_file(_PROJECT_ROOT, WORK / "src")), str(WORK), str(ROOT)]
    import hangma_bot.bootstrap as b
    from scripts.run_test_room import load_room_config, child_config_mapping
    from scripts import test_room_campaign_watchdog as portal
    # 隔离脚本的默认根是WORK；凭证仍只读用户已保存的主项目私有配置。
    portal.PORTAL_COOKIE = _project_file(_PROJECT_ROOT, ROOT / ".private/portal-session/cookie.txt")
    assert portal.PORTAL_COOKIE.is_file()
    import httpx
    assert Path(b.__file__).resolve().is_relative_to(WORK)
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "ROOT-CHANGESET.json")).read_text())
    assert preparation["complete"] and b._vip_runtime_sources() == preparation["runtime_source_manifest"]
    package = b._load_vip_manifest(b.VIP_S03_TESTROOM_STRATEGY, None)
    deadline = json.loads((_project_file(_PROJECT_ROOT, ROOT / "review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1/original-deadline-probe/CLOSED.json")).read_text())
    assert deadline["complete"] and deadline["actual_service_choose"] == 59
    engineering = json.loads((_project_file(_PROJECT_ROOT, HERE / "ENGINEERING-CLOSED.json")).read_text())
    assert engineering["engineering_checks_complete"]
    assert engineering["game_pin"] == b._vip_runtime_sources()["src/hangma_bot/adapters/official/game.py"]
    assert (_project_file(_PROJECT_ROOT, HERE / "AFFECTED-FINAL-CLOSED.json")).exists()
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "AFFECTED-FINAL-CLOSED.json")).read_text())["actual_exit_code"] == 0
    assert not PRIVATE.exists() and not OUT.exists() and not SESSION.exists()
    PRIVATE.mkdir(mode=0o700)
    OUT.mkdir()
    payload = {"m": 10, "rounds": 2, "base_score": 1, "you_cai_bi_kao": False,
        "peng_timeout_sec": 1, "chi_timeout_sec": 1, "discard_timeout_sec": 3, "timeout_min": 30}
    save(_project_file(_PROJECT_ROOT, OUT / "START.json"), {"pid": os.getpid(), "at_unix": time.time(),
        "requested_rules": payload, "package_id": package["release_package_id"],
        "workspace": str(WORK), "source_manifest": b._vip_runtime_sources(),
        "authorized_one_engineering_room": True, "renew": False, "player_termination_allowed": False})
    try:
        with httpx.Client(verify=False, trust_env=False, timeout=40,
                headers={"Cookie": portal.portal_cookie()}) as client:
            response = client.post("https://10.240.169.190:18080/portal/api/test-rooms", json=payload)
        raw_path = _project_file(_PROJECT_ROOT, PRIVATE / "create-response.bin")
        raw_path.write_bytes(response.content)
        raw_path.chmod(0o600)
        save(_project_file(_PROJECT_ROOT, OUT / "CREATE-RECEIPT.json"), {"http_status": response.status_code,
            "body_sha256": hashlib.sha256(response.content).hexdigest(), "raw_private": True,
            "actual_POST_attempts": 1})
        assert response.status_code == 200, "建房未成功；原响应私存，禁止重做未知POST"
        room = response.json()
        assert room["room_id"].startswith("t_") and len(room["players"]) == 4
        slots = ("qinglong", "baihu", "zhuque", "xuanwu")
        identities = []
        for slot, player in zip(slots, room["players"]):
            token = _project_file(_PROJECT_ROOT, PRIVATE / (slot + ".token"))
            with token.open("x") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(player["token"].strip() + "\n")
            identities.append({"slot": slot, "token_file": str(token), "strategy": package["strategy"],
                "expected_policy_release_id": package["release_package_id"]})
        config = {"mode": "test_room", "base_url": "https://10.240.169.190:18080",
            "expected_tournament_id": room["room_id"], "known_guide_version": 35,
            "audit_root": str(_project_file(_PROJECT_ROOT, SESSION / "audit")), "strategy": package["strategy"],
            "insecure_hosts": ["10.240.169.190"], "sse_enabled": True,
            "discard_pacing_enabled": False, "max_completed_batches": 1,
            "identities": identities, "restart": {"max_restarts": 0}}
        save(_project_file(_PROJECT_ROOT, PRIVATE / "room.json"), config, private=True)
        save(_project_file(_PROJECT_ROOT, PRIVATE / "rules.json"), {"base_score": 1, "you_cai_bi_kao": False}, private=True)
        parsed = load_room_config(_project_file(_PROJECT_ROOT, PRIVATE / "room.json"))
        for seat in parsed.identities:
            data = child_config_mapping(parsed, seat)
            data.pop("token_env", None)
            data["token"] = "offline-fake-only"
            b.runtime_config_from_mapping(data)
        save(_project_file(_PROJECT_ROOT, OUT / "RELEASE-SNAPSHOT.json"), package)
        save(_project_file(_PROJECT_ROOT, OUT / "PLAN.json"), {"room_id": room["room_id"], "rules": payload,
            "strategy": package["strategy"], "package_id": package["release_package_id"],
            "session": str(SESSION.relative_to(ROOT)), "four_equal_configs": True,
            "unique_complete_tables_expected": 10, "unique_hands_expected": 20,
            "strength_evidence": False, "official_tournament_evidence": False})
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(_project_file(_PROJECT_ROOT, WORK / "src")) + os.pathsep + str(WORK)
        for key in ("NO_PROXY", "no_proxy"):
            environment[key] = ",".join(filter(None, (environment.get(key, ""), "10.240.169.190")))
        with (_project_file(_PROJECT_ROOT, OUT / "PLAYERS.log")).open("x") as output:
            child = subprocess.Popen([sys.executable, str(_project_file(_PROJECT_ROOT, WORK / "scripts/run_test_room.py")),
                "--config", str(_project_file(_PROJECT_ROOT, PRIVATE / "room.json")), "--once"], cwd=WORK, env=environment,
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            save(_project_file(_PROJECT_ROOT, OUT / "PLAYERS-START.json"), {"pid": child.pid, "at_unix": time.time(),
                "source_manifest": b._vip_runtime_sources(), "natural_end_only": True})
            code = child.wait()
        save(_project_file(_PROJECT_ROOT, OUT / "PLAYERS-TERMINAL.json"), {"actual_exit_code": code, "at_unix": time.time(),
            "termination_signal_sent": False, "renew": False})
        assert code == 0, "测试房玩家自然退出非零；保留错误，不续房"
        print({"room_id": room["room_id"], "actual_exit_code": code, "verification_pending": True})
    except Exception as error:
        # 不输出HTTP正文/凭证；未知建房结果、玩家失败均保留首次事实。
        save(_project_file(_PROJECT_ROOT, OUT / "FAILURE.json"), {"type": type(error).__name__, "at_unix": time.time(),
            "automatic_retry": False, "player_termination_signal_sent": False})
        raise


if __name__ == "__main__":
    main()
