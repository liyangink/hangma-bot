"""仅补采自然结束自由赛的b7至b9；每个公开GET间隔至少2秒，429有界重试。

首个外层exit1及b7失败目录保留，b0至b6成功原件不重采。每个实际请求
独立留痕，避免包装器内部重试被误计为一次网络请求。没有新匹配或策略调用。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t157-pruned-s02-experimental-free-1'

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

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t157-vip-s02-free-v3")


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


def main():
    """固定补三桌全部成功后才建完整十桌赛后制品，失败不给通过信用。"""
    os.chdir(ROOT)
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
    from hangma_bot.bootstrap import build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTO-MATCH-CHILD-TERMINAL.json")).read_text())["exit_code"] == 0
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "ACTUAL-OUTER-TERMINAL.json")).read_text())["actual_exit_code"] == 1
    valid = {}
    for p in BASE.glob("official/dl-*"):
        if (p / "download-error.json").exists() or not (p / "source.json").exists():
            continue
        source = json.loads((p / "source.json").read_text())
        assert source["batch"] not in valid
        valid[source["batch"]] = source
    assert set(valid) == set(range(7))
    room = "a_5590d4c47c4a"
    assert all(source["room_id"] == room for source in valid.values())
    with (_project_file(_PROJECT_ROOT, HERE / "CAPTURE-RETRY-START.json")).open("x") as stream:
        json.dump({"existing_valid_batches": list(range(7)), "fixed_remaining_batches": [7, 8, 9],
                   "minimum_actual_GET_interval_seconds": 2, "max_attempts_per_GET": 4,
                   "old_outer_failure_preserved": True, "new_auto_rooms": 0, "candidate_choose": 0}, stream, indent=2)
        stream.write("\n")
    with build_public_archive_client({"base_url": "https://10.240.169.190:18080",
                                      "insecure_hosts": ["10.240.169.190"]}) as client:
        wrapped = PacedPublicClient(client)
        for batch in range(7, 10):
            result = collect_test_room(wrapped, room, batch, BASE)
            valid[batch] = result
            print(json.dumps({"batch": batch, "captured": True}), flush=True)
    with (_project_file(_PROJECT_ROOT, HERE / "OFFICIAL-CAPTURE.json")).open("x") as stream:
        json.dump({"room_id": room, "ten_tables": [valid[i] for i in range(10)]}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    result = subprocess.run([sys.executable, "scripts/audit_tool.py", "postgame", str(BASE), "--rule-config",
                             str(_project_file(_PROJECT_ROOT, ROOT / ".private/t157-vip-s02-free-v3/rule-config.json"))])
    with (_project_file(_PROJECT_ROOT, HERE / "POSTGAME-CHILD-TERMINAL.json")).open("x") as stream:
        json.dump({"exit_code": result.returncode, "scope": "一份本地完整审计与全部十桌官方档案"}, stream,
                  ensure_ascii=False, indent=2)
        stream.write("\n")
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
