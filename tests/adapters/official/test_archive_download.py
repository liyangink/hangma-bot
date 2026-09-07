"""官方赛后采集保留字节与版本，HTTP 失败不伪造牌谱。"""
import json
from pathlib import Path

import httpx
import pytest

from hangma_bot.adapters.official.archive_download import collect_test_room
from hangma_bot.bootstrap import build_public_archive_client


def test_download_is_byte_exact_and_paced_without_auth(tmp_path):
    raw = b'{ "status": "finished", "room_id": "t_room", "batch": 0, "game_id": "g", "blocks": [], "rounds": [] }\n'
    seen, sleeps = [], []
    def handler(request):
        seen.append(request)
        assert "authorization" not in request.headers
        if request.url.path.endswith("/events"):
            return httpx.Response(200, content=raw)
        return httpx.Response(200, json={"version": 18, "games": []})
    with httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler)) as client:
        result = collect_test_room(client, "t_room", 0, tmp_path, sleep=sleeps.append)
    folder = Path(result["directory"])
    assert (folder / "events.json").read_bytes() == raw
    assert result["guide_version"] == 18
    assert len(seen) == 4 and all(delay >= .2 for delay in sleeps)
    records = [json.loads(line) for line in (folder / "http-requests.jsonl").read_text().splitlines()]
    assert len(records) == 8
    assert len({record["request_id"] for record in records}) == 4
    assert all(record["http_status"] == 200 for record in records if record["phase"] == "finished")


def test_download_failure_keeps_evidence_but_has_no_events(tmp_path):
    def handler(request):
        return httpx.Response(403) if request.url.path.endswith("/events") else httpx.Response(200, json={"games": []})
    with httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="403"):
            collect_test_room(client, "t_room", 0, tmp_path, sleep=lambda _: None)
    assert not list(tmp_path.glob("official/*/events.json"))
    assert list(tmp_path.glob("official/*/download-error.json"))
    assert list(tmp_path.glob("official/*/events.json.http-error"))


def test_credentials_in_url_are_rejected():
    with pytest.raises(ValueError, match="不含凭证"):
        build_public_archive_client({"base_url": "https://secret:secret@example.invalid"})


@pytest.mark.parametrize("failure", ["wrong_room", "timeout", "invalid_json"])
def test_incomplete_downloads_leave_durable_failure_marker(tmp_path, failure):
    def handler(request):
        if not request.url.path.endswith("/events"):
            return httpx.Response(200, json={"games": []})
        if failure == "timeout":
            raise httpx.ReadTimeout("do not log arbitrary transport detail")
        if failure == "invalid_json":
            return httpx.Response(200, content=b"bad json")
        return httpx.Response(200, json={"room_id": "another", "batch": 0, "status": "finished"})
    with httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            collect_test_room(client, "t_room", 0, tmp_path, sleep=lambda _: None)
    assert list(tmp_path.glob("official/*/download-error.json"))
    assert not list(tmp_path.glob("official/*/source.json"))
