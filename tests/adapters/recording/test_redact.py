"""第二道防御性脱敏的行为测试与性质测试。"""

import json

from hangma_bot.adapters.recording.redact import (
    REDACTED,
    is_sensitive_key,
    redact_json_line,
    redact_value,
    unredacted_secret_matches,
)

_SECRET_SAMPLES = [
    "Bearer abcDEF123==",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "token=supersecretvalue",
    "https://official.example/x?access_token=abcdef123456&y=1",
]


class TestStructuralRedaction:
    """结构级扫描：敏感键整值替换，与嵌套深度无关。"""

    def test_sensitive_keys_are_redacted_at_any_depth(self):
        payload = {
            "Authorization": "Bearer abcDEF123==",
            "nested": {"Set-Cookie": "sid=1; HttpOnly", "note": "保留"},
            "list": [{"access_token": "T" * 32}],
        }
        result = redact_value(payload)
        assert result["Authorization"] == REDACTED
        assert result["nested"]["Set-Cookie"] == REDACTED
        assert result["nested"]["note"] == "保留"
        assert result["list"][0]["access_token"] == REDACTED

    def test_non_string_values_pass_through(self):
        payload = {"n": 3, "f": 1.5, "b": True, "z": None, "seq": [1, 2]}
        assert redact_value(payload) == {"n": 3, "f": 1.5, "b": True, "z": None, "seq": [1, 2]}

    def test_redaction_returns_new_structure(self):
        payload = {"a": {"b": 1}}
        result = redact_value(payload)
        payload["a"]["b"] = 99
        assert result["a"]["b"] == 1


class TestValueShapeRedaction:
    """形态级扫描：Bearer/JWT/查询参数三种常见凭证形态。"""

    def test_bearer_and_jwt_and_query_forms(self):
        result = redact_value(
            {
                "m1": "prefix Bearer abcDEF123== suffix",
                "m2": "hdr eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig123456 tail",
                "m3": "https://h/x?token=supersecretvalue&y=1",
            }
        )
        assert result["m1"] == "prefix Bearer [REDACTED] suffix"
        assert "[REDACTED]" in result["m2"]
        assert "eyJhbGciOiJIUzI1NiJ9" not in result["m2"]
        assert result["m3"] == "https://h/x?token=[REDACTED]&y=1"

    def test_redaction_is_idempotent(self):
        payload = {
            "Authorization": "Bearer abcDEF123==",
            "m": "Bearer xyz98765 and token=abcdef123",
        }
        once = redact_value(payload)
        twice = redact_value(once)
        assert once == twice

    def test_no_secret_substring_survives_in_serialized_output(self):
        # 性质测试：任何样本以任何嵌套方式出现，序列化结果都不残留原文。
        for secret in _SECRET_SAMPLES:
            payload = {
                "Authorization": secret,
                "nested": {"cookie": secret},
                "list": [secret, {"deep": [secret]}],
                "plain": secret,
            }
            line = redact_json_line(json.dumps(redact_value(payload), ensure_ascii=False))
            assert secret not in line
            json.loads(line)  # 仍是合法 JSON


class TestLineSweepAndDetection:
    """序列化行兜底与验证器复用的形态判定。"""

    def test_line_sweep_keeps_json_valid(self):
        line = json.dumps({"msg": "call Bearer abcDEF123== now"}, ensure_ascii=False)
        swept = redact_json_line(line)
        assert json.loads(swept)["msg"] == "call Bearer [REDACTED] now"

    def test_unredacted_secret_matches_skips_redacted(self):
        assert unredacted_secret_matches("Bearer [REDACTED]") == ()
        assert len(unredacted_secret_matches("Bearer realsecret99")) == 1
        assert unredacted_secret_matches("普通中文文本") == ()

    def test_sensitive_key_detection(self):
        assert is_sensitive_key("Authorization")
        assert is_sensitive_key("access_token")
        assert is_sensitive_key("Set-Cookie")
        assert not is_sensitive_key("authoritative_seq")
        assert not is_sensitive_key("game_id")
