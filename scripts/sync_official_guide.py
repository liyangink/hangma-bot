#!/usr/bin/env python3
"""官方接入指南同步工具：免认证抓取 guide/version 变更日志与 guide 全文到本地快照。

用途（文档同步，不进线上动作闭环）：

1. GET /portal/api/guide/version —— 指南版本与变更日志（免认证，5 次/秒/IP）；
2. GET /portal/api/guide?format=text —— 完整接入指南正文（v14 起免认证，与门户
   「接入指南」Tab 同源，纯文本格式，LLM/终端友好）；
3. 与本地已审查基线 KNOWN_GUIDE_VERSION（自动读取
   src/hangma_bot/adapters/official/dto.py，可用 --known-version 覆盖）对比，
   列出基线之后的变更；出现 breaking 时醒目提示人工核对并同步
   doc/official-platform-api-v2.md 与 doc/official-tournament-flow-2026-09-03.md；
4. 快照写入 doc/references/：official-guide-version-v{N}.json（变更日志）、
   official-guide-v{N}.txt（全文端点原始响应）、
   official-guide-v{N}-content.txt（剥离出的指南正文）。与既有内容一致时跳过
   写入，减少 git 噪声。

TLS：默认官方内网主机（10.240.169.190，自签证书）自动关闭证书校验；其他主机
默认校验，确需自签环境才显式 --insecure。指南端点免认证，本脚本不携带 Token。

用法：:

  python scripts/sync_official_guide.py                  # 同步默认官方实例
  python scripts/sync_official_guide.py --fail-on-breaking
  python scripts/sync_official_guide.py --base-url https://<主机>:18080 --insecure

退出码：0 成功；3 发现基线之后 breaking 且 --fail-on-breaking；4 网络/解析失败。
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

DEFAULT_BASE_URL = "https://10.240.169.190:18080"
OFFICIAL_INTRANET_HOST = "10.240.169.190"
GUIDE_VERSION_PATH = "/portal/api/guide/version"
GUIDE_TEXT_PATH = "/portal/api/guide?format=text"
_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DTO_PATH = _SCRIPT_ROOT / "src" / "hangma_bot" / "adapters" / "official" / "dto.py"
DEFAULT_OUT_DIR = _SCRIPT_ROOT / "doc" / "references"


class SyncError(RuntimeError):
    """同步失败（网络/HTTP/报文形状），区别于参数错误。"""


@dataclass(frozen=True)
class GuideSnapshot:
    """两个免认证指南端点抓取结果的合并快照。"""

    version: int
    updated_at: str
    changes: Tuple[Mapping[str, Any], ...]
    content: str
    envelope_raw: str  # /portal/api/guide?format=text 原始响应正文


@dataclass(frozen=True)
class SyncResult:
    """落盘与基线对比结果。"""

    version: int
    updated_at: str
    new_changes: Tuple[Mapping[str, Any], ...]  # version > 已审查基线的变更
    has_new_breaking: bool
    written: Tuple[Path, ...]
    skipped: Tuple[Path, ...]


def _require_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyncError("{} 应为整数，得到 {!r}".format(what, value))
    return value


def _require_str(value: Any, what: str) -> str:
    if not isinstance(value, str):
        raise SyncError("{} 应为字符串，得到 {!r}".format(what, value))
    return value


def known_guide_version_from_source(dto_path: Path = DTO_PATH) -> Optional[int]:
    """从 dto.py 源码读取已审查基线 KNOWN_GUIDE_VERSION；读取失败返回 None。"""

    try:
        text = dto_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^KNOWN_GUIDE_VERSION\s*=\s*(\d+)\s*#", text, re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))


def _host(base_url: str) -> Optional[str]:
    try:
        return urlsplit(base_url).hostname
    except ValueError:
        return None


def _http_get_raw(base_url: str, insecure: bool, timeout: float) -> Callable[[str], str]:
    """构造 GET 函数：传入相对路径，返回原始响应文本；429/网络错误有界重试。"""

    ctx = ssl._create_unverified_context() if insecure else None

    def get(path: str) -> str:
        request = urllib.request.Request(
            base_url.rstrip("/") + path, headers={"Accept": "application/json"}
        )
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=ctx) as resp:
                    return resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    time.sleep(2)
                    last_exc = exc
                    continue
                raise SyncError(
                    "GET {} 返回 HTTP {}: {}".format(
                        path, exc.code, exc.read().decode(errors="replace")[:200]
                    )
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(1)
                    continue
        raise SyncError("GET {} 失败: {}".format(path, last_exc)) from last_exc

    return get


def fetch_guide(get_raw: Callable[[str], str]) -> GuideSnapshot:
    """抓取并校验两个免认证端点；两处版本不一致只警告（官方声明同源，人工核对）。"""

    version_doc = json.loads(get_raw(GUIDE_VERSION_PATH))
    if not isinstance(version_doc, Mapping):
        raise SyncError("guide/version 响应应为 JSON 对象")
    version = _require_int(version_doc.get("version"), "guide.version")
    updated_at = _require_str(version_doc.get("updated_at"), "guide.updated_at")
    raw_changes = version_doc.get("changes") or []
    if not isinstance(raw_changes, Sequence) or isinstance(raw_changes, (str, bytes)):
        raise SyncError("guide.changes 应为数组")
    changes = tuple(item for item in raw_changes if isinstance(item, Mapping))

    envelope_raw = get_raw(GUIDE_TEXT_PATH)
    text_doc = json.loads(envelope_raw)
    if not isinstance(text_doc, Mapping):
        raise SyncError("guide 全文响应应为 JSON 对象")
    content = text_doc.get("content")
    if not isinstance(content, str) or not content:
        raise SyncError("guide 全文响应缺少非空 content")
    text_version = text_doc.get("version")
    if isinstance(text_version, int) and not isinstance(text_version, bool) and text_version != version:
        print(
            "警告：guide/version 版本 {} 与 guide 全文版本 {} 不一致，请人工核对".format(
                version, text_version
            )
        )
    return GuideSnapshot(
        version=version,
        updated_at=updated_at,
        changes=changes,
        content=content,
        envelope_raw=envelope_raw,
    )


def sync_guide(
    snapshot: GuideSnapshot, known_version: Optional[int], out_dir: Path
) -> SyncResult:
    """快照落盘（内容未变则跳过）并与已审查基线对比产出新增变更清单。"""

    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Tuple[Path, str]] = [
        (
            out_dir / "official-guide-version-v{}.json".format(snapshot.version),
            json.dumps(
                {
                    "version": snapshot.version,
                    "updated_at": snapshot.updated_at,
                    "changes": snapshot.changes,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        ),
        (out_dir / "official-guide-v{}.txt".format(snapshot.version), snapshot.envelope_raw),
        (
            out_dir / "official-guide-v{}-content.txt".format(snapshot.version),
            snapshot.content,
        ),
    ]
    written: list[Path] = []
    skipped: list[Path] = []
    for path, text in files:
        try:
            if path.exists() and path.read_text(encoding="utf-8") == text:
                skipped.append(path)
                continue
        except OSError:
            pass
        path.write_text(text, encoding="utf-8")
        written.append(path)
    baseline = known_version if known_version is not None else 0
    new_changes = tuple(
        change
        for change in snapshot.changes
        if isinstance(change.get("version"), int)
        and not isinstance(change.get("version"), bool)
        and change["version"] > baseline
    )
    has_new_breaking = any(change.get("type") == "breaking" for change in new_changes)
    return SyncResult(
        version=snapshot.version,
        updated_at=snapshot.updated_at,
        new_changes=new_changes,
        has_new_breaking=has_new_breaking,
        written=tuple(written),
        skipped=tuple(skipped),
    )


def render_summary(snapshot: GuideSnapshot, known_version: Optional[int], result: SyncResult) -> str:
    """人类可读的同步摘要；breaking 变更醒目提示后续人工步骤。"""

    lines = [
        "服务器指南 v{}（updated_at={}）".format(snapshot.version, snapshot.updated_at),
        "本地已审查基线：v{}".format(
            known_version if known_version is not None else "未知（未读取到 KNOWN_GUIDE_VERSION）"
        ),
    ]
    if result.new_changes:
        breaking_count = sum(1 for change in result.new_changes if change.get("type") == "breaking")
        lines.append(
            "基线之后新增变更 {} 条，其中 breaking {} 条：".format(len(result.new_changes), breaking_count)
        )
        for change in result.new_changes:
            marker = "BREAKING" if change.get("type") == "breaking" else change.get("type", "?")
            lines.append(
                "  [{marker}] v{ver} {date} {summary}".format(
                    marker=marker,
                    ver=change.get("version"),
                    date=change.get("date"),
                    summary=str(change.get("summary") or "")[:160],
                )
            )
        if result.has_new_breaking:
            lines.append(
                "注意：存在 breaking 变更——请人工核对并同步 doc/official-platform-api-v2.md "
                "与 doc/official-tournament-flow-2026-09-03.md，审查后再更新 dto.py 的 "
                "KNOWN_GUIDE_VERSION（--fail-on-breaking 可接入门禁）"
            )
    else:
        lines.append("基线之后无新增变更。")
    for label, paths in (("已写入", result.written), ("未变化跳过", result.skipped)):
        if paths:
            lines.append(label + "：")
            lines.extend("  " + str(path) for path in paths)
    return "\n".join(lines)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="官方接入指南同步工具（免认证，纯标准库）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="官方平台基址（默认 %(default)s）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="快照输出目录（默认 %(default)s）")
    parser.add_argument(
        "--known-version",
        type=int,
        default=None,
        help="本地已审查指南版本；缺省自动读取 dto.py 的 KNOWN_GUIDE_VERSION",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="单请求超时秒数（默认 20）")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="关闭 TLS 证书校验（默认官方内网主机自动关闭；其他主机默认校验）",
    )
    parser.add_argument(
        "--fail-on-breaking",
        action="store_true",
        help="发现基线之后的 breaking 变更时退出码 3（可接入发布门禁）",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None, *, get_raw: Optional[Callable[[str], str]] = None) -> int:
    args = _parse_args(argv)
    insecure = args.insecure or _host(args.base_url) == OFFICIAL_INTRANET_HOST
    if insecure and not args.insecure:
        print("TLS 证书校验已关闭（默认官方内网主机为自签证书）")
    known = args.known_version if args.known_version is not None else known_guide_version_from_source()
    fetch = get_raw or _http_get_raw(args.base_url, insecure, args.timeout)
    try:
        snapshot = fetch_guide(fetch)
    except (SyncError, ValueError) as exc:
        print("同步失败：{}".format(exc), file=sys.stderr)
        return 4
    result = sync_guide(snapshot, known, Path(args.out_dir))
    print(render_summary(snapshot, known, result))
    if args.fail_on_breaking and result.has_new_breaking:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
