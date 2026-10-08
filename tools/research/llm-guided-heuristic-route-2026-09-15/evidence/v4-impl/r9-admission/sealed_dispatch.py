"""P23 SEALED-DISPATCH：把模型准入的**派发接缝**封死，并让它在下一轮可被机器验证。

要修的缺陷（P22 审计结论）：被测子代理是完整 DSH 子代理（有仓库读权限与工具），部分会话把
仓库内**现成答案**读进上下文——手工标准答案 selftest/standard/T*.txt、旧轮同题回复
r6-model-admission/replies/**、本轮他题回复 replies/r1/**。⇒ 那一轮成绩不得当作免污染的准入依据。

四道控制（缺一不可）：
  1. **最小权限提示词**：派发提示词显式写明「只依据本提示词作答；不得读写、搜索、遍历仓库文件；
     不得使用任何工具；不得创建文件」。没有这句话的会话在审计里直接判 MISSING_SEAL 并拒收。
  2. **答案包移出工作区**：seal 把标准答案/旧轮回复/本轮他题回复/判分报告**搬到工作区之外**的
     保险库（默认 $TMPDIR/sitin-sealed-answers/<stamp>/），unseal 逐条搬回；probe 用工作区扫描
     给出"封存期间不可达"的实测证据。
  3. **卫生 veto 前置**：audit 在**判分之前**扫会话痕迹，任一会话出现工具调用/文件读写迹象 ⇒ 该题标
     CONTAMINATED 并**拒收**（不进入判分、不计入通过数）；一旦有拒收，veto 把整批状态置为
     **INVALID**（既不是 INCOMPLETE 也不是通过）。
  4. **一键入口**：run 把「回收 → 卫生审计 → 拒收 → 只对干净题判分」串成一条命令；selftest 用
     **合成会话**做零模型自检（干净收 / 工具调用拒 / 读文件拒）。

纪律：本工具**零模型调用、零网络**；只读写本目录与保险库。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
DEFAULT_SESSIONS = Path.home() / ".dsh" / "sessions"
DEFAULT_VAULT = Path(tempfile.gettempdir()) / "sitin-sealed-answers"
MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/sealed-dispatch/seal-manifest.json')

#: 派发提示词里**必须**出现的密封条款（缺了即审计判 MISSING_SEAL 并拒收）。
SEAL_CLAUSE = ("【密封作答·必须遵守】只依据本提示词作答；不得读写、搜索、遍历仓库文件；"
               "不得使用任何工具；不得创建文件。")
SEAL_MARKER = "【密封作答·必须遵守】"
DELIVERY_CLAUSE = "【交付方式】直接输出你的答案正文本身，不要任何前言、后记、解释或元说明。"

#: 需要封存的"答案可达面"（相对仓库根；目录或文件）。封存期间这些路径在工作区内不存在。
SEAL_TARGETS = (
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/selftest/standard",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/replies",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/replies",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/reports",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/selftest/standard",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/dispatch",
    # P22 的卫生审计产物里**引用了答案正文片段**（tool-result 窗口），同样是可达面。
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/audit-hygiene.json",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/scratch",
    # --- P24 补齐：P23 的封存清单只覆盖**答案正文**面，漏了**判据面**。-------
    # 判据面 = 「判分器到底要什么」的明文，读了它等价于拿到参考答案的要点：
    #   * package/tasks/T*.json：validation.required_groups（逐题命中词表）、
    #     forbidden 词表与 notes「判分要点」；
    #   * package/manifest.json：题包身份与门槛；
    #   * selftest/**：判分器自测与抗规避探针报告，逐字含命中/禁用词；
    #   * r6/r7/r8 的历史任务包、判分报告与重判记录：同样逐字含命中词表与旧轮答案要点。
    # 这些路径在 P23 那一轮**没有被封存**（当时实测：把一个判据 token 当探针扫工作区，
    # 命中大量未封存文件）。硬控制仍是「任何工具调用 ⇒ 卫生 veto」，但封存面必须补齐，
    # 否则「答案包移出工作区」这句话在判据面上不成立。
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/tasks",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/manifest.json",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/selftest",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/tasks",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/reports",
    'tools/research/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r7-fixes/P4-m5-admission',
    'tools/research/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r8-fixes/E2-admission-behavior',
)

#: probe 用的探针：文件名式 + 正文式（标准答案原文、本轮回复原文）。
PROBE_PATTERNS = (
    "selftest/standard/T",
    "replies/r1/T",
    "replies/r2/T",
    "在父代基础上按三段反馈做有界修订",
    "据决定4，新候选是独立策略评分器",
    "本窗口已知最低分",            # 模型回复正文片段（T10 系）
    "五通道缺失感知",              # 模型回复正文片段（T09 系）
    "known_floor_minus_margin",    # 模型回复代码片段（多题）
)

#: 探针自指噪声：命中这些路径不算"答案可达"（它们只提路径名，或用探针串做自测）。
SELF_NOISE = (
    "r9-admission/sealed-dispatch/", "sealed_dispatch.py", "probe-before-seal.json",
    "probe-while-sealed.json", "collect_reply.py", "audit_hygiene.py", "call_ledger.py",
    "build_package.py", "synthetic_material_check.py", "resign_gate_records.py",
    "r9-admission/README.md", "P23-SEALED-DISPATCH",
)

TOOL_RECORD_TYPES = ("tool/call", "tool/code-dispatch", "tool/code-dispatch-start",
                     "tool/result", "tool/start", "tool/end")
FILE_ACCESS_RE = re.compile(
    r"\b(cat|ls|grep|rg|find|head|tail|sed|awk|wc|read|write|edit|glob)\b"
    r"|tools\.(read|write|edit|glob|grep|bash)"
    r"|/replies/|selftest/standard|admission-selftest",
    re.IGNORECASE)

#: **单请求协议的"工作事件"**（评审 S3）：终止事件（turn/end）之后出现其中任何一种，
#: 即"已结束却仍在工作"，该会话一律具名阻断——不得拿结束后的新答复当答卷。
WORK_EVENT_TYPES = ("assistant/message", "assistant/chunk", "step/start", "step/end",
                    "request/header", "request/context", "user/message",
                    "tool/call", "tool/code-dispatch", "tool/code-dispatch-start",
                    "tool/result", "tool/start", "tool/end")

#: 通道请求身份里**由通道决定**的两项（评审 S3）。provider/model 以题包 manifest 为准，
#: 这两项由无权限单次交付通道的路由/settings 层决定（不是计划自述、也不是会话自查）：
#:   * reasoningEffort：settings 层（p25-headless/settings/headless-settings.yaml；--patch
#:     的 config 里写它会**被静默忽略**）；
#:   * maxTokens：headless profile 上限（实测 P25 通道 97 条会话全部为 256000）。
CHANNEL_REASONING_EFFORT = "max"
CHANNEL_MAX_TOKENS = 256000

#: 宿主固定消息（评审 S1）。无权限单次通道里，DSH 在题面之外另发一条"运行时上下文"
#: user 消息：前缀固定、字节随环境变化（实测 465/453/521 字节，7 种摘要）。因此只按
#: **冻结前缀 + 版本**登记，并把该消息的**确切字节摘要**逐条记进审计行供事后复核；
#: 不把它混进题面，也不把不断变化的环境文案当成题面的一部分。
HOST_MESSAGE_VERSION = "dsh-runtime-context/1"
HOST_MESSAGE_PREFIXES = ("<system-reminder>", "Current runtime context")

#: 题面消息内**登记在册**的额外文本块（逐条 = 确切 sha256 + 字节数 + 版本 + 来源）。
#: 本通道为空：题面必须独占该消息的**唯一**文本块；需要固定宿主块时在此登记其确切
#: 字节摘要与版本，未登记者一律具名阻断（UNREGISTERED_CONTEXT_BLOCK）。
REGISTERED_CONTEXT_BLOCKS: tuple = ()


def registered_context_block(text: str) -> dict:
    """按**确切字节摘要 + 字节数**核对登记表；未登记者返回 None（不看长度、不看前缀）。"""
    raw = text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    for row in REGISTERED_CONTEXT_BLOCKS:
        if str(row.get("sha256")) == digest and int(row.get("bytes") or len(raw)) == len(raw):
            return dict(row)
    return None


def expected_request_config(target_model=None) -> dict:
    """冻结的**请求身份**（评审 S3）：provider/model 取题包 manifest，
    reasoningEffort/maxTokens 取通道常量（见上）。计划自述与会话自查都不构成权威。"""
    model = dict(target_model or {})
    return {"provider": model.get("provider"), "model": model.get("model"),
            "reasoningEffort": CHANNEL_REASONING_EFFORT,
            "maxTokens": CHANNEL_MAX_TOKENS}


def frozen_prompt_sha256(task_id: str, package: Path) -> str:
    """首答题面摘要：**从冻结包装配**（唯一权威）。读不到冻结包即抛错，由调用方失败关闭。"""
    return hashlib.sha256(sealed_prompt(task_id, Path(package)).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 会话痕迹读取（自包含；与 collect_reply.py 同口径，便于 selftest 用合成夹具）
# ---------------------------------------------------------------------------

def session_files(sessions_root: Path):
    return sorted(sessions_root.glob("*/*/session.jsonl.zstd"))


#: 显式准入白名单（评审 S1）：只有这一种状态可以进入判分并计入准入证据。
ADMISSION_STATUSES = ("CLEAN",)
#: 具名阻断状态：既不进 accepted，也不冒充"污染"——"没查到污染"不等于"证据完整且干净"。
BLOCKING_STATUSES = {
    "MISSING_SESSION": "计划里的会话文件不存在",
    "UNREADABLE_SESSION": "会话文件无法解压或读取",
    "UNREADABLE_LOG": "会话日志含无法解析的坏行（不得静默略过后签收）",
    "INCOMPLETE_SESSION": "会话未结束（缺 turn/end）：中断但已产出正文只作恢复素材",
    "NO_REPLY": "会话已结束但没有交付正文",
    "PROMPT_MISMATCH": "会话首条提示词与冻结包/冻结构造器重建值不一致（换题/换提示词）",
    "DUPLICATE_SESSION": "同一会话或同一提示词被重复计入同一批",
    # --- P25 包 C（评审 S1/S3）：单请求协议与未登记上下文，一律具名阻断 ---
    "PROTOCOL_NO_REQUEST": "单请求协议：会话里读不到任何 request/header（身份无法核验）",
    "PROTOCOL_MULTI_REQUEST": "单请求协议：出现多次模型请求（本通道只允许一次）",
    "PROTOCOL_NO_TERMINATION": "单请求协议：缺少 turn/end（没有正常终止）",
    "PROTOCOL_MULTI_TERMINATION": "单请求协议：出现多次 turn/end（终止状态不可唯一确定）",
    "PROTOCOL_WORK_AFTER_TERMINATION": "单请求协议：终止事件之后仍有工作记录（结束后追加的答复不算答卷）",
    "PROTOCOL_REQUEST_CONFIG_UNREADABLE": "单请求协议：request/header 里读不出请求配置",
    "PROTOCOL_REQUEST_CONFIG_INCONSISTENT": "单请求协议：同一会话出现不一致的请求配置",
    "PROTOCOL_REQUEST_CONFIG_MISMATCH": "单请求协议：请求配置与冻结 provider/model/effort/maxTokens 不符",
    "UNREGISTERED_CONTEXT_BLOCK": "题面消息里出现未登记的额外上下文块（无权限单次通道只允许单块）",
    "UNREGISTERED_USER_MESSAGE": "出现未登记的题面之外的 user 消息（只允许宿主固定消息）",
    "PROMPT_UNDERIVABLE": "题面摘要无法从冻结包/冻结构造器重建：缺权威来源，不得用计划自述顶替",
}
#: 污染族：整批必须重做（不是"证据不完整"）。
CONTAMINATION_STATUSES = ("CONTAMINATED_FILE_ACCESS", "CONTAMINATED_TOOL_USE",
                          "MISSING_SEAL")


def read_session_strict(path: Path) -> dict:
    """严格读会话：坏行**不再静默略过**，并绑定原始字节摘要（评审 S1）。"""
    raw = subprocess.run(["zstd", "-dc", str(path)], capture_output=True, check=True)
    text = raw.stdout.decode("utf-8", "replace")
    records, bad = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if not isinstance(record, dict):
            bad += 1
            continue
        records.append(record)
    return {"records": records, "bad_lines": bad,
            "session_sha256": hashlib.sha256(raw.stdout).hexdigest(),
            "session_bytes": len(raw.stdout)}


def _host_message_row(index: int, text: str) -> dict:
    """宿主固定消息的**确切字节**记录（版本 + 摘要 + 字节数，可事后逐条复核）。"""
    raw = text.encode("utf-8")
    return {"index": index, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "head": text.lstrip()[:80], "version": HOST_MESSAGE_VERSION}


def first_message_blocks(records: list) -> dict:
    """任务消息的文本块拆解 + 宿主消息/未登记上下文登记（评审 S1）。

    实测（P25 无权限单次通道 97 条会话）：题面独占一条 user 消息的**单个**文本块；DSH 另发
    一条"运行时上下文"user 消息（前缀固定、字节随环境变化——实测 465/453/521 字节、7 种摘要）。
    因此：
      * 题面消息里的额外文本块 = **未登记上下文**：只有确切字节摘要命中登记表
        （REGISTERED_CONTEXT_BLOCKS，本通道为空）才算登记在册，否则具名阻断；
      * 题面之外的 user 消息只在命中宿主消息前缀（HOST_MESSAGE_PREFIXES）时按宿主固定消息
        收下，并记录其**确切字节摘要**；其余记入未登记消息清单（同样具名阻断）。
    返回的 task 仍是题面块（含密封条款的那一块，否则首块）；injected_* 语义不变，
    以便与历史归档的"额外块计数"逐条对齐。
    """
    result = {"task": "", "block_count": 0, "injected_chars": 0, "injected_blocks": 0,
              "injected_head": None, "registered_blocks": [],
              "unregistered_blocks": 0, "unregistered_block_heads": [],
              "host_messages": [], "unregistered_messages": [],
              "task_message_index": None}
    for index, rec in enumerate(records):
        if rec.get("type") != "user/message":
            continue
        data = rec.get("data") or {}
        content = data.get("content")
        if content is None:
            content = (data.get("message") or {}).get("content")
        blocks = []
        if isinstance(content, list):
            blocks = [b.get("text") or "" for b in content
                      if isinstance(b, dict) and b.get("type") == "text" and b.get("text")]
        elif isinstance(content, str) and content:
            blocks = [content]
        if not blocks:
            continue
        if result["task_message_index"] is None:
            if blocks[0].lstrip().startswith(HOST_MESSAGE_PREFIXES):
                result["host_messages"].append(_host_message_row(index, blocks[0]))
                continue
            task = next((b for b in blocks if SEAL_MARKER in b), blocks[0])
            injected = [b for b in blocks if b is not task]
            registered, unregistered = [], []
            for block in injected:
                entry = registered_context_block(block)
                (registered if entry else unregistered).append(entry or block)
            result.update({
                "task": task, "block_count": len(blocks),
                "injected_chars": sum(len(b) for b in injected),
                "injected_blocks": len(injected),
                "injected_head": (injected[0].strip()[:80] if injected else None),
                "registered_blocks": registered,
                "unregistered_blocks": len(unregistered),
                "unregistered_block_heads": [b.strip()[:80] for b in unregistered[:4]],
                "task_message_index": index})
            continue
        row = _host_message_row(index, blocks[0])
        if blocks[0].lstrip().startswith(HOST_MESSAGE_PREFIXES):
            result["host_messages"].append(row)
        else:
            result["unregistered_messages"].append(row)
    return result


def prompt_of(records: list) -> str:
    """任务提示词 = 首条任务 user 消息里的**题面块**（不含 harness 注入的投递要求）。"""
    return first_message_blocks(records)["task"]


def answer_of(records: list) -> str:
    """回复原文：优先最后一条**符合交付形态**的助手消息（以 { 开头且含 python 围栏）。"""
    texts = []
    for rec in records:
        if rec.get("type") != "assistant/message":
            continue
        message = (rec.get("data") or {}).get("message") or {}
        text = "".join(b.get("text") or "" for b in message.get("content") or []
                       if b.get("type") == "text")
        if text.strip():
            texts.append(text)
    for text in reversed(texts):
        if text.lstrip().startswith("{") and "```python" in text:
            return text
    return texts[-1] if texts else ""


def answer_of_terminated(records: list) -> str:
    """**绑定口径**的答卷（评审 S3）：终止回合（最后一次 turn/end）之内的最后一条交付正文。

    没有终止事件时返回空串：中断会话里的正文只作恢复素材，不得当答卷绑定；
    终止事件之后的答复也不属于本次请求，同样不算答卷。
    """
    ends = [index for index, rec in enumerate(records) if rec.get("type") == "turn/end"]
    if not ends:
        return ""
    return answer_of(records[:ends[-1] + 1])


def request_protocol(records: list, expected_config: dict = None) -> dict:
    """单请求协议核对（评审 S3）：恰好一次请求、一次正常终止、终止后无工作事件、配置可核。

    本通道（无权限单次交付）的协议就是**一次请求**：不需要通用多轮会话支持；任何额外请求、
    结束后的工作事件、配置不符或读不出的请求头一律具名阻断（fail-closed）。
    """
    requests = [rec for rec in records if rec.get("type") == "request/header"]
    configs = []
    for rec in requests:
        header = (rec.get("data") or {}).get("header") or {}
        config = header.get("config")
        configs.append(dict(config) if isinstance(config, dict) else None)
    ends = [index for index, rec in enumerate(records) if rec.get("type") == "turn/end"]
    after = records[ends[-1] + 1:] if ends else []
    post_work = [rec.get("type") for rec in after if rec.get("type") in WORK_EVENT_TYPES]
    violations = []
    if not requests:
        violations.append("PROTOCOL_NO_REQUEST")
    elif len(requests) > 1:
        violations.append("PROTOCOL_MULTI_REQUEST")
    if not ends:
        violations.append("PROTOCOL_NO_TERMINATION")
    elif len(ends) > 1:
        violations.append("PROTOCOL_MULTI_TERMINATION")
    if post_work:
        violations.append("PROTOCOL_WORK_AFTER_TERMINATION")
    unique = [config for config in configs if config is not None]
    unique = [config for index, config in enumerate(unique) if config not in unique[:index]]
    if configs and any(config is None for config in configs):
        violations.append("PROTOCOL_REQUEST_CONFIG_UNREADABLE")
    elif len(unique) > 1:
        violations.append("PROTOCOL_REQUEST_CONFIG_INCONSISTENT")
    elif expected_config is not None and unique and unique[0] != dict(expected_config):
        violations.append("PROTOCOL_REQUEST_CONFIG_MISMATCH")
    return {"request_headers": len(requests), "request_configs": configs,
            "request_config": (unique[0] if len(unique) == 1 else None),
            "expected_request_config": (dict(expected_config)
                                        if expected_config is not None else None),
            "turn_ends": len(ends), "turn_end_index": (ends[-1] if ends else None),
            "post_termination_records": [rec.get("type") for rec in after][:8],
            "post_termination_work": post_work[:8],
            "violations": violations}


def tool_evidence(records: list) -> dict:
    """工具调用与文件访问痕迹（**任何**工具调用即污染，按 Lead 判据从严）。"""
    calls = []
    for rec in records:
        if rec.get("type") not in TOOL_RECORD_TYPES:
            continue
        data = rec.get("data") or {}
        name = data.get("name") or rec.get("type")
        args = str(data.get("arguments") or data.get("payload") or "")
        calls.append({"record": rec.get("type"), "tool": name, "args": args[:400]})
    file_hits = [c for c in calls if FILE_ACCESS_RE.search(c["args"]) or
                 c["tool"] in ("read", "write", "edit", "glob", "grep")]
    return {"tool_calls": len(calls), "calls": calls[:8], "file_access": file_hits[:8]}


def classify(records: list, task_id, *, finished: bool = True,
             bad_lines: int = 0, expected_prompt_sha: str = None,
             duplicate: bool = False, expected_request_config: dict = None,
             prompt_authority: str = "declared") -> dict:
    """单会话分类（评审 S1/S3 的显式白名单口径）。

    判定顺序：污染族 → 密封条款 → 日志/结束状态 → 重复 → **单请求协议** →
    **未登记上下文** → 冻结题面一致性 → 正文 → CLEAN。
    **只有 CLEAN 可进入判分**；其余状态都必须在 veto 里具名阻断。
    """
    blocks = first_message_blocks(records)
    prompt = blocks["task"]
    answer = answer_of(records)
    terminated = answer_of_terminated(records)
    evidence = tool_evidence(records)
    protocol = request_protocol(records, expected_request_config)
    sealed = SEAL_MARKER in prompt
    prompt_sha = (hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None)
    if evidence["file_access"]:
        status = "CONTAMINATED_FILE_ACCESS"
    elif evidence["tool_calls"]:
        status = "CONTAMINATED_TOOL_USE"
    elif not sealed:
        status = "MISSING_SEAL"
    elif bad_lines:
        status = "UNREADABLE_LOG"
    elif not finished:
        status = "INCOMPLETE_SESSION"
    elif duplicate:
        status = "DUPLICATE_SESSION"
    elif protocol["violations"]:
        # 单请求协议优先报告：它比"多了个块"更准确地说明"这不是一次交付"（评审 S3）。
        status = protocol["violations"][0]
    elif blocks["unregistered_blocks"]:
        status = "UNREGISTERED_CONTEXT_BLOCK"
    elif blocks["unregistered_messages"]:
        status = "UNREGISTERED_USER_MESSAGE"
    elif expected_prompt_sha and prompt_sha and prompt_sha != expected_prompt_sha:
        status = "PROMPT_MISMATCH"
    elif not terminated:
        status = "NO_REPLY"
    else:
        status = "CLEAN"
    return {"task_id": task_id, "status": status, "sealed_clause": sealed,
            "prompt_sha256": prompt_sha, "expected_prompt_sha256": expected_prompt_sha,
            "prompt_authority": prompt_authority,
            "answer_chars": len(answer),
            "answer_sha256": (hashlib.sha256(answer.encode("utf-8")).hexdigest()
                              if answer else None),
            "terminated_answer_sha256": (hashlib.sha256(terminated.encode("utf-8")).hexdigest()
                                         if terminated else None),
            "answer_is_terminated": bool(terminated) and terminated == answer,
            "protocol": protocol,
            "harness_injected_blocks": blocks["injected_blocks"],
            "harness_injected_chars": blocks["injected_chars"],
            "harness_injected_head": blocks["injected_head"],
            "registered_context_blocks": blocks["registered_blocks"],
            "unregistered_context_blocks": blocks["unregistered_blocks"],
            "unregistered_context_heads": blocks["unregistered_block_heads"],
            "unregistered_user_messages": blocks["unregistered_messages"],
            "host_messages": blocks["host_messages"],
            "tool_calls": evidence["tool_calls"],
            "file_access_hits": len(evidence["file_access"]),
            "evidence": evidence}


# ---------------------------------------------------------------------------
# seal / unseal / probe
# ---------------------------------------------------------------------------

def do_seal(vault: Path, targets=SEAL_TARGETS) -> dict:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    vault = vault / stamp
    vault.mkdir(parents=True, exist_ok=True)
    moved = []
    for rel in targets:
        src = _project_file(_PROJECT_ROOT, REPO / rel)
        if not src.exists():
            moved.append({"path": rel, "status": "ABSENT"})
            continue
        dst = vault / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append({"path": rel, "status": "SEALED", "vault_path": str(dst)})
    manifest = {"schema": "sitin-sealed-dispatch-seal/1", "stamp": stamp,
                "vault_root": str(vault), "workspace": str(REPO), "moved": moved,
                "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def do_unseal(manifest_path: Path = MANIFEST) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = []
    for row in manifest["moved"]:
        if row.get("status") != "SEALED":
            continue
        src = Path(row["vault_path"])
        dst = _project_file(_PROJECT_ROOT, REPO / row["path"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            restored.append({"path": row["path"], "status": "TARGET_EXISTS_SKIPPED"})
            continue
        shutil.move(str(src), str(dst))
        restored.append({"path": row["path"], "status": "RESTORED"})
    manifest["unsealed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    manifest["restored"] = restored
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    return manifest


def probe(pattern: str) -> dict:
    """工作区内搜索一个探针串：命中文件数与前几个路径（排除重目录）。"""
    # --include 过滤只影响**扫描成本**（跳过 .jsonl 等大文件），不改变"工作区可达性"结论：
    # 答案面本身就是 .txt/.json/.md/.py 这几类文本。
    command = ["grep", "-rIl", "--binary-files=without-match",
               "--include=*.txt", "--include=*.json", "--include=*.md",
               "--include=*.py", "--include=*.jsonl",
               "--exclude-dir=.git", "--exclude-dir=.venv", "--exclude-dir=.uv-cache",
               "--exclude-dir=.uv-python", "--exclude-dir=node_modules",
               "--exclude-dir=artifacts", "--exclude-dir=bundles", "--exclude-dir=datamart",
               "--exclude-dir=prebuilt", "--exclude-dir=__pycache__",
               "-e", pattern, "."]
    result = subprocess.run(command, cwd=str(REPO), capture_output=True, text=True)
    hits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    # 自指噪声：P23 自己的产物（探针输出/审计/工具源码）与被扫到的"路径提及"文件
    # （工具与报告里写着 selftest/standard 这类**路径名**，那不是答案内容）。
    noise = [h for h in hits if any(token in h for token in SELF_NOISE)]
    real = [h for h in hits if h not in noise]
    return {"pattern": pattern, "hits": len(real), "self_noise": len(noise),
            "files": real[:5], "noise_files": noise[:5]}


def do_probe(patterns=PROBE_PATTERNS) -> dict:
    rows = [probe(p) for p in patterns]
    # sealed = **当下**答案面是否真的不在工作区（不是"存在封存清单"）。
    currently_sealed = all(not (_project_file(_PROJECT_ROOT, REPO / rel)).exists() for rel in SEAL_TARGETS)
    return {"schema": "sitin-sealed-dispatch-probe/1", "workspace": str(REPO),
            "sealed": currently_sealed,
            "seal_manifest_present": MANIFEST.is_file(), "rows": rows,
            "total_hits": sum(r["hits"] for r in rows)}


# ---------------------------------------------------------------------------
# sealcheck：判据面（"判分器要什么"的明文）是否也在工作区内不可达
# ---------------------------------------------------------------------------

def _iter_task_rows(tasks_dir: Path):
    for path in sorted(tasks_dir.glob("T*.json")):
        try:
            yield json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def criteria_tokens(tasks_dir: Path, per_task: int = 4) -> list:
    """从题目定义里抽出**判据 token**：命中词表与禁词表里最独特的若干条。

    这些 token 出现在工作区任何文件里，都等价于把"判分器要什么"暴露给被测会话。
    只取长度 >= 3 的条目，并按每题的原始顺序取前若干条（不挑选、不做人工取舍）。
    """
    rows = []
    for task in _iter_task_rows(tasks_dir):
        tokens, seen = [], set()
        validation = task.get("validation") or {}
        flat = [alt for group in validation.get("required_groups") or [] for alt in group]
        flat += list(validation.get("forbidden") or [])
        # 只取**有辨识度**的条目：含 ASCII/下划线/等号/数字的标识符式条目，或 >=6 字的中文短语。
        # 通用领域词（"根数""识别区间"这类）在整仓里到处都是，拿它们做探针只会得到噪声。
        def distinctive(value: str) -> int:
            if any(ch.isascii() and (ch.isalnum() or ch in "_-=./") for ch in value):
                return 2
            return 1 if len(value) >= 6 else 0
        ranked = sorted((str(t) for t in flat), key=lambda t: (-distinctive(t), -len(t)))
        for token in ranked:
            if len(token) < 3 or token in seen or distinctive(token) == 0:
                continue
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= per_task:
                break
        if tokens:
            rows.append({"task_id": task.get("task_id"), "tokens": tokens})
    return rows


#: bulk 扫描时跳过的重目录（与 probe 同口径）。
SCAN_EXCLUDES = ("--exclude-dir=.git", "--exclude-dir=.venv", "--exclude-dir=.uv-cache",
                 "--exclude-dir=.uv-python", "--exclude-dir=node_modules",
                 "--exclude-dir=artifacts", "--exclude-dir=bundles",
                 "--exclude-dir=datamart", "--exclude-dir=prebuilt",
                 "--exclude-dir=__pycache__")


def bulk_scan(tokens) -> dict:
    """一次 grep 扫全部判据 token（-F 定长匹配），返回 {token: [files]}。

    逐 token 起一次 grep 在整仓上要 ~8 分钟；合并成一次扫描后按行内 token 归属。
    """
    ordered = sorted(set(str(t) for t in tokens if str(t).strip()))
    with tempfile.NamedTemporaryFile("w", suffix=".patterns", delete=False,
                                     encoding="utf-8") as handle:
        handle.write("\n".join(ordered) + "\n")
        pattern_file = handle.name
    # 判据面只可能出现在这三棵子树（路线证据树 / tools / src）；扫全仓在整仓上要 30+ 分钟。
    # 只扫**证据树**：判据的明文载体（题包、判分报告、自测）都在这里。tools/src 是生产代码，
    # 它们与判据**共用同一套领域名词**，把它们算作"泄漏"只会得到噪声（实测 1 万+ 文件命中）。
    roots = ["review/llm-guided-heuristic-route-2026-09-15/evidence"]
    command = ["grep", "-rIlF", "-f", pattern_file,
               "--include=*.txt", "--include=*.json", "--include=*.md",
               "--include=*.py", "--include=*.jsonl", *SCAN_EXCLUDES, *roots]
    result = subprocess.run(command, cwd=str(REPO), capture_output=True, text=True)
    hits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    Path(pattern_file).unlink(missing_ok=True)
    return {"files": hits}


def _sealed_prefix(path: str) -> bool:
    clean = path.lstrip("./")
    return any(clean.startswith(target) for target in SEAL_TARGETS)


#: **判据面清单**（P24 人工逐条核实：这些路径逐字含有"判分器要什么"的明文）。
#: 判据面清单里的每一条都必须在 SEAL_TARGETS 内——这是本检查的**判据**（布尔，可机器复核）。
CRITERIA_SURFACES = (
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/tasks",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/manifest.json",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/selftest",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/reports",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/replies",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/selftest/standard",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/dispatch",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/tasks",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/reports",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/replies",
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/selftest/standard",
    'tools/research/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r7-fixes/P4-m5-admission',
    'tools/research/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r8-fixes/E2-admission-behavior',
)


def criteria_coverage() -> dict:
    """"判据面清单 ⊆ SEAL_TARGETS" 的机器复核（本检查真正的判据）。"""
    uncovered = [path for path in CRITERIA_SURFACES if not _sealed_prefix(path)]
    return {"criterion": "判据面清单每一条都必须在 SEAL_TARGETS 内",
            "criteria_surfaces": list(CRITERIA_SURFACES),
            "covered": len(CRITERIA_SURFACES) - len(uncovered),
            "uncovered": uncovered, "ok": not uncovered}


def do_sealcheck(tasks_dir: Path, tasks_dir_label: str) -> dict:
    """判据面（"判分器要什么"的明文）在工作区内的可达性清单。

    分类口径：命中文件落在 SEAL_TARGETS 之内 = 封存清单已覆盖；之外 = **漏**。
    这条检查不依赖"此刻是否已封存"，因此可在任意时刻复跑并作为清单完备性的机器证据。
    """
    rows = criteria_tokens(tasks_dir)
    all_tokens = [token for row in rows for token in row["tokens"]]
    scan = bulk_scan(all_tokens)
    covered, leaked = [], []
    for path in scan["files"]:
        row = {"file": path, "sealed": _sealed_prefix(path)}
        (covered if row["sealed"] else leaked).append(row)
    inventory = criteria_coverage()
    return {"schema": "sitin-sealed-dispatch-sealcheck/1",
            "criterion": inventory["criterion"], "ok": inventory["ok"],
            "criteria_surfaces": inventory["criteria_surfaces"],
            "criteria_covered": inventory["covered"],
            "criteria_uncovered": inventory["uncovered"],
            "inventory_source": ("P24 人工逐条核实（targeted grep 命中 required_groups/notes/禁词），"
                                 "不是自动发现"),
            "diagnostic_token_scan": {
                "tasks_dir": tasks_dir_label, "tokens_scanned": len(set(all_tokens)),
                "files_matched": len(scan["files"]),
                "files_covered_by_seal": len(covered), "files_uncovered": len(leaked),
                "note": ("**仅作诊断，不作为判据**：判据词表与生产代码共用同一套领域名词，"
                         "整树匹配会被「恰好用了同一个词」的文件淹没（实测 1 万+ 命中），"
                         "无法区分「泄漏判据」与「共享词汇」。判据面是否封存以 "
                         "criteria_uncovered 是否为空为准。"),
                "sample_uncovered": [row["file"] for row in leaked[:20]]},
            "note": ("P24 发现 P23 的封存清单只覆盖答案正文面，漏了判据面"
                     "（package/tasks、selftest、历史判分报告等），已补齐并加此检查。")}


def _vault_tasks_dir() -> Path:
    """封存期间从保险库读判据面；未封存时退回工作区。"""
    if MANIFEST.is_file():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for row in manifest.get("moved", []):
            if row.get("status") == "SEALED" and row["path"].endswith("package/tasks"):
                return Path(row["vault_path"])
    return _project_file(_PROJECT_ROOT, HERE / "package" / "tasks")


# ---------------------------------------------------------------------------
# audit / veto
# ---------------------------------------------------------------------------

def do_audit(plan: list, sessions_root: Path, index_path: Path = None, *,
             expected_prompts: dict = None, package_dir: Path = None,
             expected_request_config: dict = None,
             allow_declared_authority: bool = False) -> dict:
    """判分前卫生审计（评审 S1/S3 口径）。

    准入白名单 **只有 CLEAN**；其余一律具名阻断：
    - 污染族（CONTAMINATED_* / MISSING_SEAL）⇒ 整批 INVALID、必须重做；
    - 证据不完整族（缺会话/坏日志/未结束/无正文/题面不符/重复/**单请求协议**/
      未登记上下文）⇒ 阻断但具名区分为 INCOMPLETE。

    **题面权威（S1）**：首答预期题面只能由**冻结包**重建（见 frozen_prompt_sha256），
    修复轮预期题面只能由**冻结构造器 + 首答 + 诊断产物**重建；两者都经
    expected_prompts[(task, kind)] 传入。只给 package_dir 时首答可重建、修复轮一律
    PROMPT_UNDERIVABLE；两者都没有即**失败关闭**（只有合成夹具可显式
    allow_declared_authority=True）。计划自述的 prompt_sha256 降级为**待核数据**：
    与冻结重建不一致即列进计划问题（整批 INVALID）。

    同时**在审核时绑定**：会话原始字节摘要、会话首条提示词摘要、终止回合内的答卷摘要
    与结束序号，供事后 verify 复核"先审后改/先审后继续调用"。
    """
    authority = ("frozen_rebuilt" if expected_prompts is not None
                 else "frozen_package" if package_dir is not None
                 else "declared" if allow_declared_authority else None)
    if authority is None:
        raise ValueError(
            "do_audit 缺少冻结题面权威：必须给 expected_prompts（冻结构造器重建）或 "
            "package_dir（冻结包重建）；只有合成夹具可以显式 allow_declared_authority=True")
    frozen: dict = {}
    if expected_prompts is not None:
        frozen = {(str(key[0]), str(key[1])): value
                  for key, value in dict(expected_prompts).items()}

    def frozen_prompt_for(task_id, kind):
        """冻结重建的预期题面摘要；取不到返回 None（调用方按 PROMPT_UNDERIVABLE 阻断）。"""
        if expected_prompts is not None:
            return frozen.get((str(task_id), str(kind)))
        if str(kind) == "first":
            try:
                return frozen_prompt_sha256(str(task_id), Path(package_dir))
            except OSError:
                return None
        return None

    index = None
    if index_path is not None and Path(index_path).is_file():
        index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    by_run = {path.parent.name: path for path in session_files(sessions_root)}
    rows, plan_problems = [], []
    seen_runs, seen_tasks, seen_prompts = {}, {}, {}
    # 重复判定的粒度是**（题目, 类型）**：协议允许同一题出现一次 first + 一次 repair
    # （max_repairs_per_task=1），那不是重复；同一题同一类型出现两次才是。
    plan_pairs = [(item.get("task"), item.get("kind") or "first") for item in plan]
    dup_pairs = sorted({(t, k) for t, k in plan_pairs if plan_pairs.count((t, k)) > 1})
    if dup_pairs:
        plan_problems.append("计划里出现重复条目（题目,类型）：" + ", ".join(
            "{0}/{1}".format(t, k) for t, k in dup_pairs))
    bad_kinds = sorted({str(k) for _t, k in plan_pairs if str(k) not in ("first", "repair")})
    if bad_kinds:
        plan_problems.append("计划里的条目类型不是 first/repair：" + ", ".join(bad_kinds))
    repair_counts: dict = {}
    for task_id, kind in plan_pairs:
        if kind == "repair":
            repair_counts[task_id] = repair_counts.get(task_id, 0) + 1
    extra_repairs = sorted(task_id for task_id, count in repair_counts.items() if count > 1)
    if extra_repairs:
        plan_problems.append("同一题出现多次修复轮（协议只允许 1 次）：" + ", ".join(
            extra_repairs))
    plan_runs = [item.get("run_id") for item in plan]
    if len(set(plan_runs)) != len(plan_runs):
        plan_problems.append("计划里出现重复会话 id")
    for item in plan:
        run_id = item["run_id"]
        task_id = item.get("task")
        kind = str(item.get("kind") or "first")
        want_prompt = frozen_prompt_for(task_id, kind)
        declared = item.get("prompt_sha256")
        if declared and want_prompt and str(declared) != str(want_prompt):
            plan_problems.append(
                "计划自述题面摘要与冻结重建不一致（题目/类型 {0}/{1}）："
                "计划字段只作待核数据".format(task_id, kind))
        base = {"task_id": task_id, "kind": item.get("kind"), "run_id": run_id,
                "tool_calls": 0, "file_access_hits": 0, "sealed_clause": False,
                "answer_chars": 0, "answer_sha256": None, "session_sha256": None,
                "evidence": {}, "prompt_authority": authority,
                "expected_prompt_sha256": want_prompt,
                "plan_prompt_sha256": declared,
                "prompt_source": ("frozen" if want_prompt else "underivable")}
        if want_prompt is None:
            base["status"] = "PROMPT_UNDERIVABLE"
            rows.append(base)
            continue
        path = by_run.get(run_id)
        if path is None:
            rows.append(dict(base, status="MISSING_SESSION"))
            continue
        try:
            info = read_session_strict(path)
        except Exception as exc:                       # noqa: BLE001
            rows.append(dict(base, status="UNREADABLE_SESSION",
                             evidence={"error": "{0}: {1}".format(type(exc).__name__, exc)}))
            continue
        records = info["records"]
        finished = any(rec.get("type") == "turn/end" for rec in records)
        duplicate_run = run_id in seen_runs
        duplicate_task = (task_id, item.get("kind") or "first") in seen_tasks
        row = classify(records, task_id, finished=finished, bad_lines=info["bad_lines"],
                       expected_prompt_sha=want_prompt,
                       duplicate=duplicate_run or duplicate_task,
                       expected_request_config=expected_request_config,
                       prompt_authority=authority)
        if not duplicate_run and row["prompt_sha256"]:
            first = seen_prompts.get(row["prompt_sha256"])
            if first is not None:
                row["status"] = "DUPLICATE_SESSION"
                row.setdefault("evidence", {})["duplicate_of_task"] = first
            else:
                seen_prompts[row["prompt_sha256"]] = task_id
        seen_runs[run_id] = task_id
        seen_tasks.setdefault((task_id, item.get("kind") or "first"), run_id)
        row.update({"kind": item.get("kind"), "run_id": run_id,
                    "plan_prompt_sha256": declared,
                    "session_sha256": info["session_sha256"],
                    "session_bytes": info["session_bytes"],
                    "session_finished": finished,
                    "bad_lines": info["bad_lines"],
                    "turn_end_seq": next((rec.get("seq") for rec in reversed(records)
                                          if rec.get("type") == "turn/end"), None)})
        rows.append(row)
    planned_tasks = {task_id for task_id, _kind in plan_pairs}
    missing_tasks = sorted(set(index and [r["task_id"] for r in index["tasks"]] or [])
                           - planned_tasks)
    if missing_tasks:
        plan_problems.append("派发清单里的题目未被计划覆盖：" + ", ".join(missing_tasks))
    contamination = [r for r in rows if r["status"] in CONTAMINATION_STATUSES]
    blocking = [r for r in rows if r["status"] not in ADMISSION_STATUSES
                and r["status"] not in CONTAMINATION_STATUSES]
    accepted = sorted({r["task_id"] for r in rows if r["status"] in ADMISSION_STATUSES})

    def _row(r):
        return {"task_id": r["task_id"], "kind": r.get("kind"), "run_id": r["run_id"],
                "status": r["status"], "tool_calls": r["tool_calls"],
                "file_access_hits": r["file_access_hits"],
                "reason": BLOCKING_STATUSES.get(r["status"])}
    return {"schema": "sitin-sealed-dispatch-audit/3",
            "sessions_root": str(sessions_root),
            "index_path": str(index_path) if index_path else None,
            "prompt_authority": authority,
            "prompt_authority_note": (
                "frozen_rebuilt = 每题预期题面由冻结构造器重建（首答=冻结包；修复=冻结构造器+"
                "首答+诊断产物）；frozen_package = 只由冻结包重建首答；declared = 合成夹具的"
                "显式降级（正式出口不得使用）"),
            "expected_request_config": (dict(expected_request_config)
                                        if expected_request_config is not None else None),
            "plan_problems": plan_problems,
            "rows": rows, "accepted": accepted,
            "contaminated": [_row(r) for r in contamination],
            "blocked": [_row(r) for r in blocking],
            "clean": not contamination and not blocking and not plan_problems}


def do_verify(audit: dict, sessions_root: Path) -> dict:
    """事后复核（评审 S1）：审核时绑定的会话字节/提示词/答卷摘要是否仍然一致。

    用来发现"先审后改""先审后继续调用"：只要会话文件字节变了、首条提示词变了、
    最终答卷变了，就具名报告，不得继续用旧审核结论。
    """
    by_run = {path.parent.name: path for path in session_files(sessions_root)}
    rows, changed, missing = [], [], []
    for row in audit.get("rows") or ():
        run_id = row.get("run_id")
        path = by_run.get(run_id)
        entry = {"task_id": row.get("task_id"), "run_id": run_id,
                 "status": row.get("status")}
        if path is None:
            entry["verify"] = "MISSING"
            missing.append(entry)
            rows.append(entry)
            continue
        info = read_session_strict(path)
        checks = {
            "session_sha256": (row.get("session_sha256"), info["session_sha256"]),
            "prompt_sha256": (row.get("prompt_sha256"),
                              hashlib.sha256(prompt_of(info["records"]).encode("utf-8")).hexdigest()),
            "answer_sha256": (row.get("answer_sha256"),
                              hashlib.sha256(answer_of(info["records"]).encode("utf-8")).hexdigest()),
        }
        bad = {k: {"expected": v[0], "observed": v[1]} for k, v in checks.items()
               if v[0] is not None and v[0] != v[1]}
        entry["verify"] = "CHANGED" if bad else "MATCHED"
        if bad:
            entry["differences"] = bad
            changed.append(entry)
        rows.append(entry)
    return {"schema": "sitin-sealed-dispatch-verify/1",
            "audit_schema": audit.get("schema"), "checked": len(rows),
            "changed": changed, "missing": missing, "rows": rows,
            "ok": not changed and not missing,
            "note": "会话字节/提示词/答卷摘要任一与审核时不一致即不得沿用旧审核结论"}


def do_veto(audit: dict, round_labels=("r1", "r2")) -> dict:
    """判分前 veto（评审 S1）：**只有完整且已验证的 CLEAN 才能进入判分**。

    - 污染族或计划自相矛盾 ⇒ `INVALID`（整批重做，不是"证据不全"）；
    - 证据不完整族 ⇒ `INCOMPLETE`（具名阻断；中断但有正文只作恢复素材）；
    - 其余 ⇒ `CLEAN`。
    """
    contaminated = audit.get("contaminated") or []
    blocked = audit.get("blocked") or []
    plan_problems = audit.get("plan_problems") or []
    if contaminated or plan_problems:
        status = "INVALID"
    elif blocked:
        status = "INCOMPLETE"
    else:
        status = "CLEAN"
    kinds: dict = {}
    for row in contaminated + blocked:
        kinds[row["status"]] = kinds.get(row["status"], 0) + 1
    return {"schema": "sitin-sealed-dispatch-veto/2", "status": status,
            "admission_eligible": status == "CLEAN", "rounds": list(round_labels),
            "blocking_kinds": kinds,
            "plan_problems": plan_problems,
            "contaminated_tasks": sorted({r["task_id"] for r in contaminated}),
            "blocked_tasks": sorted({r["task_id"] for r in blocked}),
            "contaminated_runs": contaminated, "blocked_runs": blocked,
            "accepted_tasks": audit.get("accepted") or [],
            "note": ("准入白名单只有 CLEAN；其余具名阻断。INVALID = 污染/计划矛盾（整批重做）；"
                     "INCOMPLETE = 证据不完整（缺会话/坏日志/未结束/无正文/提示词不符/重复）。"
                     "非 CLEAN 时整批不得判 ADMISSION_PASS / NOT_ADMITTED，"
                     "被阻断题不进判分、不计入通过数。"),
            "decided_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


# ---------------------------------------------------------------------------
# emit（派发侧提示词）与 selftest（零模型自检）
# ---------------------------------------------------------------------------

def sealed_prompt(task_id: str, package: Path) -> str:
    body = (package / "prompts" / (task_id + ".txt")).read_text(encoding="utf-8")
    return "\n".join([SEAL_CLAUSE, "", body, "", DELIVERY_CLAUSE])


def do_emit(package: Path, out_dir: Path, tasks=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted((package / "prompts").glob("T*.txt")):
        task_id = path.stem
        if tasks and task_id not in tasks:
            continue
        text = sealed_prompt(task_id, package)
        target = out_dir / task_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(text, encoding="utf-8")
        rows.append({"task_id": task_id,
                     "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                     "prompt_chars": len(text), "seal_clause": SEAL_CLAUSE in text})
    index = {"schema": "sitin-sealed-dispatch-index/1", "seal_clause": SEAL_CLAUSE,
             "dispatch_rule": ("每题的派发提示词 = dispatch/<TID>/prompt.txt 原文；"
                               "派发前先 seal（答案包移出工作区），回收后 unseal"),
             "tasks": rows}
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    return index


def _write_fixture_session(root: Path, run_id: str, prompt: str, answer: str,
                           tool, project="--fixture--", finished: bool = True,
                           bad_line: bool = False, extra_answer: str = None,
                           request_count: int = 1, extra_block: str = None,
                           extra_user_message: str = None,
                           request_config: dict = None,
                           turn_end_count: int = 1,
                           after_end_answer: str = None,
                           host_message: str = None) -> Path:
    """合成会话夹具（P25 包 C 起带**单请求协议**结构：request/header + turn/end）。

    finished=False 模拟"没跑完"；bad_line=True 追加一条坏 JSON；request_count /
    turn_end_count / extra_block / extra_user_message / after_end_answer 用于 S1/S3 反例。
    """
    config = dict(request_config if request_config is not None else
                  expected_request_config({"provider": "fixture-provider",
                                           "model": "fixture-model"}))
    content = [{"type": "text", "text": prompt}]
    if extra_block is not None:
        content.append({"type": "text", "text": extra_block})
    records = [{"type": "session", "seq": 1, "data": None},
               {"type": "user/message", "seq": 2, "data": {"content": content}}]
    if host_message is not None:
        # 宿主固定消息（运行时上下文）：题面之外的独立 user 消息，按前缀+版本登记。
        records.append({"type": "user/message",
                        "data": {"content": [{"type": "text", "text": host_message}]}})
    for index in range(max(int(request_count), 0)):
        records.append({"type": "request/header", "seq": 3 + index,
                        "data": {"header": {"config": dict(config)}}})
    if extra_user_message is not None:
        records.append({"type": "user/message",
                        "data": {"content": [{"type": "text", "text": extra_user_message}]}})
    records.append({"type": "assistant/message",
                    "data": {"message": {"role": "assistant",
                                         "content": [{"type": "text", "text": answer}]}}})
    if extra_answer is not None:
        records.append({"type": "assistant/message",
                        "data": {"message": {"role": "assistant",
                                             "content": [{"type": "text",
                                                          "text": extra_answer}]}}})
    if tool is not None:
        records.append({"type": "tool/call", "data": tool})
        records.append({"type": "tool/code-dispatch",
                        "data": {"name": tool.get("name"),
                                 "arguments": tool.get("arguments")}})
    for index in range(max(int(turn_end_count), 0) if finished else 0):
        records.append({"type": "turn/end", "data": {"turn": 1 + index}})
    if after_end_answer is not None:
        records.append({"type": "assistant/message",
                        "data": {"message": {"role": "assistant",
                                             "content": [{"type": "text",
                                                          "text": after_end_answer}]}}})
    path = root / project / run_id
    path.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    if bad_line:
        lines.append('{"type": "assistant/chunk", "seq": 8, "data": {BROKEN')
    plain = path / "session.jsonl"
    plain.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    packed = path / "session.jsonl.zstd"
    subprocess.run(["zstd", "-q", "-f", str(plain), "-o", str(packed)], check=True)
    plain.unlink()
    return packed


def do_selftest(fixture_root: Path) -> dict:
    """零模型自检（评审 S1/S3 口径）。

    正例：完整且干净的会话 ⇒ CLEAN 且整批 CLEAN（题面由**冻结小包**重建、请求身份冻结）。
    反例①污染族：工具调用 / 读文件 ⇒ 拒收且整批 INVALID。
    反例②证据不完整族：缺会话、无正文、未结束、坏行、题面不符、重复 ⇒ 具名阻断、INCOMPLETE。
    反例③（P25 包 C）单请求协议与未登记上下文：双请求、结束后工作事件、双终止事件、
      请求配置不符、题面内未登记额外块、题面外未登记 user 消息 ⇒ 逐条具名阻断。
    """
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    sessions = fixture_root / "sessions"
    mini_package = fixture_root / "package"
    (mini_package / "prompts").mkdir(parents=True, exist_ok=True)
    body = "（夹具提示词）"
    prompt = SEAL_CLAUSE + chr(10) + chr(10) + body + chr(10) + chr(10) + DELIVERY_CLAUSE
    fence = chr(96) * 3
    clean_answer = ("{夹具机制一句话}" + chr(10) + chr(10) + fence + "json"
                    + chr(10) + '{"trigger": "x"}' + chr(10) + fence
                    + chr(10) + chr(10) + fence + "python" + chr(10)
                    + "def score_actions(view):" + chr(10)
                    + '    return {"status": "ABSTAIN"}' + chr(10) + fence)
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    fixture_identity = expected_request_config({"provider": "fixture-provider",
                                                "model": "fixture-model"})
    fixture_root.mkdir(parents=True, exist_ok=True)
    index_path = fixture_root / "index.json"
    index_path.write_text(json.dumps(
        {"tasks": [{"task_id": "T9%d" % i, "prompt_sha256": prompt_sha}
                   for i in range(0, 10)]}, ensure_ascii=False), encoding="utf-8")

    def write(task_id, run_id, **kwargs):
        (mini_package / "prompts" / (task_id + ".txt")).write_text(body, encoding="utf-8")
        _write_fixture_session(sessions, run_id, kwargs.pop("prompt", prompt),
                               kwargs.pop("answer", clean_answer),
                               kwargs.pop("tool", None), **kwargs)

    def run_audit(items, expected=None):
        # 每例用**只含本例题目的**派发清单：否则"清单里有题未被计划覆盖"会算计划问题，
        # 把本意是"证据不完整"的样例误升成 INVALID。
        plan = [{"task": task_id, "kind": "first", "run_id": run_id}
                for task_id, run_id in items]
        case_index = fixture_root / ("index-%s.json" % "-".join(t for t, _ in items))
        case_index.write_text(json.dumps(
            {"tasks": [{"task_id": task_id, "prompt_sha256": prompt_sha}
                       for task_id, _ in items]}, ensure_ascii=False), encoding="utf-8")
        audit = do_audit(plan, sessions, index_path=case_index,
                         package_dir=mini_package,
                         expected_request_config=(expected if expected is not None
                                                  else fixture_identity))
        return audit, do_veto(audit)

    checks = []

    def check(case, task_id, expect, audit, veto, extra=True):
        observed = {row["task_id"]: row["status"] for row in audit["rows"]}
        ok = observed.get(task_id) == expect
        if extra:
            ok = ok and task_id not in audit["accepted"] and veto["status"] != "CLEAN" \
                and veto["admission_eligible"] is False
        checks.append({"case": case, "task_id": task_id, "expect": expect,
                       "observed": observed.get(task_id), "ok": ok})
        return observed

    # 正例：唯一一个完整干净会话（题面由冻结小包重建）
    write("T90", "run-clean-0001")
    audit, veto = run_audit([("T90", "run-clean-0001")])
    observed = {row["task_id"]: row["status"] for row in audit["rows"]}
    checks.append({"case": "clean_complete", "task_id": "T90", "expect": "CLEAN",
                   "observed": observed.get("T90"),
                   "ok": observed.get("T90") == "CLEAN" and audit["accepted"] == ["T90"]
                         and veto["status"] == "CLEAN" and veto["admission_eligible"] is True
                         and audit["prompt_authority"] == "frozen_package"})

    # 污染族
    write("T91", "run-tooluse-0002", tool={"name": "bash", "arguments": "echo hello"})
    write("T92", "run-fileread-0003",
          tool={"name": "read",
                "arguments": '{"file_path": "review/x/selftest/standard/T13.txt"}'})
    for task_id, run_id, expect in (("T91", "run-tooluse-0002", "CONTAMINATED_TOOL_USE"),
                                    ("T92", "run-fileread-0003",
                                     "CONTAMINATED_FILE_ACCESS")):
        audit, veto = run_audit([(task_id, run_id)])
        observed = {row["task_id"]: row["status"] for row in audit["rows"]}
        checks.append({"case": "contamination", "task_id": task_id, "expect": expect,
                       "observed": observed.get(task_id),
                       "ok": observed.get(task_id) == expect
                             and audit["accepted"] == []
                             and veto["status"] == "INVALID"
                             and veto["admission_eligible"] is False})

    # 证据不完整族：逐例单跑，逐例都必须阻断；整批判 INCOMPLETE
    write("T93", "run-noreply-0004", answer="")
    write("T94", "run-unfinished-0005", finished=False)
    write("T95", "run-badline-0006", bad_line=True)
    write("T96", "run-mismatch-0007", prompt=prompt + "（被换过的题面）")
    write("T97", "run-dup-a-0008")
    write("T98", "run-dup-b-0009")
    incomplete_cases = [
        ("T99", "run-missing-0010", [("T99", "run-missing-0010")], "MISSING_SESSION"),
        ("T93", "run-noreply-0004", None, "NO_REPLY"),
        ("T94", "run-unfinished-0005", None, "INCOMPLETE_SESSION"),
        ("T95", "run-badline-0006", None, "UNREADABLE_LOG"),
        ("T96", "run-mismatch-0007", None, "PROMPT_MISMATCH"),
        ("T98", "run-dup-b-0009", None, "DUPLICATE_SESSION"),
    ]
    for task_id, run_id, items, expect in incomplete_cases:
        # 该例的题面**在冻结小包里存在**（否则会先被 PROMPT_UNDERIVABLE 阻断）：
        # 本组要验的是"会话证据不完整"，不是"题面无法重建"。
        (mini_package / "prompts" / (task_id + ".txt")).write_text(body, encoding="utf-8")
        if expect == "DUPLICATE_SESSION":
            audit, veto = run_audit([("T97", "run-dup-a-0008"), ("T98", "run-dup-b-0009")])
        else:
            audit, veto = run_audit(items or [(task_id, run_id)])
        observed = {row["task_id"]: row["status"] for row in audit["rows"]}
        checks.append({"case": "incomplete_evidence", "task_id": task_id, "expect": expect,
                       "observed": observed.get(task_id),
                       "ok": observed.get(task_id) == expect
                             and task_id not in audit["accepted"]
                             and veto["status"] == "INCOMPLETE"
                             and veto["admission_eligible"] is False})

    # 反例④（S1 失败关闭）：题面摘要无法从冻结包重建 ⇒ 具名阻断（不得退回计划自述）
    audit = do_audit([{"task": "T88", "kind": "first", "run_id": "run-clean-0001"}],
                     sessions, index_path=index_path, package_dir=mini_package,
                     expected_request_config=fixture_identity)
    rows = {row["task_id"]: row["status"] for row in audit["rows"]}
    checks.append({"case": "prompt_underivable_blocks", "task_id": "T88",
                   "expect": "PROMPT_UNDERIVABLE", "observed": rows.get("T88"),
                   "ok": rows.get("T88") == "PROMPT_UNDERIVABLE"
                         and audit["accepted"] == []})

    # 反例⑤（S2 前置）：计划自述的题面摘要与冻结重建不一致 ⇒ 计划问题（整批 INVALID）
    audit = do_audit([{"task": "T90", "kind": "first", "run_id": "run-clean-0001",
                       "prompt_sha256": "0" * 64}],
                     sessions, index_path=index_path, package_dir=mini_package,
                     expected_request_config=fixture_identity)
    veto = do_veto(audit)
    checks.append({"case": "plan_prompt_selfdeclared", "task_id": "T90",
                   "expect": "plan_problems", "observed": veto["status"],
                   "ok": bool(audit["plan_problems"]) and veto["status"] == "INVALID"
                         and veto["admission_eligible"] is False})

    # 反例③（P25 包 C）：单请求协议 + 未登记上下文
    protocol_cases = [
        ("T80", "run-multi-request-0101", {"request_count": 2},
         "PROTOCOL_MULTI_REQUEST"),
        ("T81", "run-work-after-end-0102", {"after_end_answer": clean_answer},
         "PROTOCOL_WORK_AFTER_TERMINATION"),
        ("T82", "run-extra-block-0103", {"extra_block": "这里是未登记的额外上下文：评分要点如下。"},
         "UNREGISTERED_CONTEXT_BLOCK"),
        ("T83", "run-extra-message-0104", {"extra_user_message": "补充要求：按参考答案改正。"},
         "UNREGISTERED_USER_MESSAGE"),
        ("T84", "run-multi-end-0105", {"turn_end_count": 2},
         "PROTOCOL_MULTI_TERMINATION"),
        ("T85", "run-config-mismatch-0106",
         {"request_config": {"provider": "other-provider", "model": "other-model",
                             "reasoningEffort": "low", "maxTokens": 128}},
         "PROTOCOL_REQUEST_CONFIG_MISMATCH"),
    ]
    for task_id, run_id, kwargs, expect in protocol_cases:
        write(task_id, run_id, **kwargs)
        audit, veto = run_audit([(task_id, run_id)])
        check("protocol_" + expect.lower(), task_id, expect, audit, veto)

    # 反例③的控制：宿主固定消息（运行时上下文）不算未登记消息，也不进题面
    write("T87", "run-host-context-0108",
          host_message="Current runtime context. 夹具运行时上下文（宿主固定消息）")
    audit, veto = run_audit([("T87", "run-host-context-0108")])
    observed = {row["task_id"]: row["status"] for row in audit["rows"]}
    checks.append({"case": "host_message_registered", "task_id": "T87", "expect": "CLEAN",
                   "observed": observed.get("T87"),
                   "ok": observed.get("T87") == "CLEAN" and audit["accepted"] == ["T87"]
                         and veto["status"] == "CLEAN"})

    report = {"schema": "sitin-sealed-dispatch-selftest/3",
              "purpose": ("零模型自检：干净完整的会话才收；污染族 ⇒ INVALID；证据不完整族"
                          "（缺会话/无正文/未结束/坏行/题面不符/重复）+ 单请求协议与未登记"
                          "上下文（双请求/结束后工作/双终止/配置不符/额外块/额外消息）"
                          "⇒ 具名阻断"),
              "fixture_sessions_root": str(sessions), "checks": checks,
              "ok": all(c["ok"] for c in checks)}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("emit")
    p.add_argument("--package", default=str(_project_file(_PROJECT_ROOT, HERE / "package")))
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "dispatch")))
    p.add_argument("--tasks", default=None)

    p = sub.add_parser("seal")
    p.add_argument("--vault", default=str(DEFAULT_VAULT))
    p = sub.add_parser("unseal")
    p.add_argument("--manifest", default=str(MANIFEST))
    p = sub.add_parser("probe")
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "probe-evidence.json")))

    p = sub.add_parser("audit")
    p.add_argument("--plan", required=True)
    p.add_argument("--sessions-root", default=str(DEFAULT_SESSIONS))
    p.add_argument("--index", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "dispatch" / "index.json")),
                   help="派发清单（用于核对会话首条提示词与新派发提示词一致）")
    p.add_argument("--package", default=str(_project_file(_PROJECT_ROOT, HERE / "package")),
                   help="冻结题包（首答题面的**唯一权威**来源；修复轮须由冻结构造器另给）")
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "hygiene-audit.json")))

    p = sub.add_parser("verify")
    p.add_argument("--audit", required=True)
    p.add_argument("--sessions-root", default=str(DEFAULT_SESSIONS))
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "hygiene-verify.json")))

    p = sub.add_parser("veto")
    p.add_argument("--audit", required=True)
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "hygiene-veto.json")))

    p = sub.add_parser("sealcheck")
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "sealcheck.json")))

    p = sub.add_parser("selftest")
    p.add_argument("--fixture-root", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "fixtures")))
    p.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "selftest.json")))

    p = sub.add_parser("run")
    p.add_argument("--plan", required=True)
    p.add_argument("--sessions-root", default=str(DEFAULT_SESSIONS))
    p.add_argument("--index", default=str(_project_file(_PROJECT_ROOT, HERE / "sealed-dispatch" / "dispatch" / "index.json")))
    p.add_argument("--package", default=str(_project_file(_PROJECT_ROOT, HERE / "package")),
                   help="冻结题包（首答题面的**唯一权威**来源）")

    args = parser.parse_args()
    if args.cmd == "seal":
        print(json.dumps(do_seal(Path(args.vault)), ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "unseal":
        print(json.dumps(do_unseal(Path(args.manifest)), ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "probe":
        report = do_probe()
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(json.dumps({"total_hits": report["total_hits"], "sealed": report["sealed"],
                          "rows": [{"pattern": r["pattern"], "hits": r["hits"]}
                                   for r in report["rows"]]}, ensure_ascii=False))
        return 0
    if args.cmd == "emit":
        tasks = set(args.tasks.split(",")) if args.tasks else None
        index = do_emit(Path(args.package), Path(args.out), tasks)
        print(json.dumps({"tasks": len(index["tasks"]), "out": args.out}, ensure_ascii=False))
        return 0
    if args.cmd == "audit":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        audit = do_audit(plan, Path(args.sessions_root), index_path=Path(args.index),
                         package_dir=Path(args.package))
        Path(args.out).write_text(json.dumps(audit, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(json.dumps({"clean": audit["clean"], "accepted": len(audit["accepted"]),
                          "contaminated": [r["task_id"] for r in audit["contaminated"]],
                          "blocked": [{"task": r["task_id"], "status": r["status"]}
                                      for r in audit["blocked"]],
                          "plan_problems": audit["plan_problems"],
                          "out": args.out}, ensure_ascii=False))
        return 0 if audit["clean"] else 2
    if args.cmd == "veto":
        audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
        veto = do_veto(audit)
        Path(args.out).write_text(json.dumps(veto, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(json.dumps({"status": veto["status"],
                          "blocking_kinds": veto["blocking_kinds"],
                          "contaminated_tasks": veto["contaminated_tasks"],
                          "blocked_tasks": veto["blocked_tasks"],
                          "admission_eligible": veto["admission_eligible"],
                          "out": args.out}, ensure_ascii=False))
        return 0 if veto["admission_eligible"] else 2
    if args.cmd == "sealcheck":
        tasks_dir = _vault_tasks_dir()
        report = do_sealcheck(tasks_dir, str(tasks_dir))
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(json.dumps({"ok": report["ok"],
                          "criteria_surfaces": len(report["criteria_surfaces"]),
                          "criteria_covered": report["criteria_covered"],
                          "criteria_uncovered": report["criteria_uncovered"],
                          "out": args.out}, ensure_ascii=False, indent=1))
        return 0 if report["ok"] else 2
    if args.cmd == "selftest":
        report = do_selftest(Path(args.fixture_root))
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(json.dumps({"ok": report["ok"],
                          "total": len(report["checks"]),
                          "failed": [c for c in report["checks"] if not c["ok"]]},
                         ensure_ascii=False, indent=1))
        return 0 if report["ok"] else 1
    if args.cmd == "run":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        audit = do_audit(plan, Path(args.sessions_root), index_path=Path(args.index),
                         package_dir=Path(args.package))
        veto = do_veto(audit)
        out_dir = _project_file(_PROJECT_ROOT, HERE / "sealed-dispatch")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "hygiene-audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
        (out_dir / "hygiene-veto.json").write_text(
            json.dumps(veto, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"status": veto["status"], "accepted": len(audit["accepted"]),
                          "blocking_kinds": veto["blocking_kinds"], "note": veto["note"]},
                         ensure_ascii=False))
        return 0 if veto["admission_eligible"] else 2
    if args.cmd == "verify":
        audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
        report = do_verify(audit, Path(args.sessions_root))
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "checked": report["checked"],
                          "changed": report["changed"], "missing": report["missing"],
                          "out": args.out}, ensure_ascii=False))
        return 0 if report["ok"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
