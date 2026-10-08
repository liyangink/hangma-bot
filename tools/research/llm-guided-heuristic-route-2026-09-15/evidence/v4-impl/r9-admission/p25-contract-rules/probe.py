#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AV-SUB 静态规则清单的零模型探针。

同一份 RULES.json 驱动三件事：
  ① 逐条实测：正例必须被 ActionValueExecutor 成功装载，反例必须以 StaticCheckError 拒绝，
     且消息与规则的消息模板逐字匹配（fullmatch，防止规则间串味）；
  ② 预检诊断：把任意拒绝消息映射回唯一 AV-SUB 编号（当前生产预检只做 str(exc) 透传）；
  ③ 候选提示片段：把同一条定义渲染成候选可读的约束行。

零模型、零网络；只读生产代码与题面/合同，只写本目录的 probe-output.txt。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-contract-rules'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))

from hangma_bot.policy.action_value_executor import (  # noqa: E402
    ALLOWED_BUILTINS,
    ALLOWED_METHODS,
    ActionValueExecutor,
    StaticCheckError,
    _UNARY_OPS,
    _check_expr,
    _Instrumentor,
)

RULES_PATH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-contract-rules/RULES.json')
OUT_PATH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-contract-rules/probe-output.txt')

DOC = '"""probe candidate."""\n'
DEFAULT_SCORE = '    return {"status": "ABSTAIN", "entries": [], "reason": None}\n'

LOG: list[str] = []


def emit(line: str = "") -> None:
    LOG.append(line)


# ---------------------------------------------------------------------------
# 探针源码构造
# ---------------------------------------------------------------------------

def build_source(spec: dict) -> str:
    if "r" in spec:
        return spec["r"]
    out = [DOC, spec.get("m", "")]
    for fn in spec.get("f", []):
        out.append(fn)
    score = spec.get("s", DEFAULT_SCORE)
    if score is not None:
        out.append("def score_actions(view):\n" + score)
    return "".join(out)


def expand_alias(path: str) -> Path:
    if path.startswith("…"):
        prefix = "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package"
        return _project_file(_PROJECT_ROOT, REPO / (prefix + path[1:]))
    return _project_file(_PROJECT_ROOT, REPO / path)


def load(source) -> tuple[str, str]:
    """返回 (结果, 详情)：PASS / REJECT / CRASH。"""
    try:
        ex = ActionValueExecutor(source)
    except StaticCheckError as exc:
        return "REJECT", str(exc)
    except BaseException as exc:  # WorkloadExceeded 是 BaseException，装载期不该出现
        return "CRASH:" + type(exc).__name__, str(exc)
    if not callable(getattr(ex, "_fn", None)):
        return "BADFN", "装载成功但 score_actions 不可调用"
    return "PASS", "已装载；callable(score_actions)=True"


# ---------------------------------------------------------------------------
# 合成 AST / 接口探针（源码不可达的分支）
# ---------------------------------------------------------------------------

def _synthetic() -> dict:
    scope_stack: list = []
    mods: set = set()
    fns: set = set()

    def call_expr(node):
        return _check_expr(node, scope_stack, mods, fns)

    def attribute_store():
        node = ast.Attribute(
            value=ast.Name(id="view", ctx=ast.Load()),
            attr="x",
            ctx=ast.Store(),
        )
        call_expr(node)

    def subscript_store():
        node = ast.Subscript(
            value=ast.Name(id="view", ctx=ast.Load()),
            slice=ast.Constant(value=0),
            ctx=ast.Store(),
        )
        call_expr(node)

    def unary_unknown_op():
        node = ast.UnaryOp(op=ast.Add(), operand=ast.Constant(value=1))
        call_expr(node)

    def unknown_expr():
        call_expr(ast.expr())

    def lambda_annotation():
        node = ast.Lambda(
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="a", annotation=ast.Name(id="int", ctx=ast.Load()))],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=ast.Name(id="a", ctx=ast.Load()),
        )
        call_expr(node)

    def instrumentor_dict_unpack():
        _Instrumentor().visit_Dict(
            ast.Dict(keys=[None], values=[ast.Constant(value=1)])
        )

    def non_string_source():
        ActionValueExecutor(42)

    def mutable_module_binding():
        ActionValueExecutor._snapshot_module_bindings({"X": []})

    return {
        "attribute_store": attribute_store,
        "subscript_store": subscript_store,
        "unary_unknown_op": unary_unknown_op,
        "unknown_expr": unknown_expr,
        "lambda_annotation": lambda_annotation,
        "instrumentor_dict_unpack": instrumentor_dict_unpack,
        "non_string_source": non_string_source,
        "mutable_module_binding": mutable_module_binding,
    }


# ---------------------------------------------------------------------------
# 同源渲染：规则 → 预检诊断 / 提示片段
# ---------------------------------------------------------------------------

PLACEHOLDER = re.compile(r"\{[0-9](?:!r)?\}")


def template_to_regex(template: str) -> re.Pattern:
    parts = PLACEHOLDER.split(template)
    pattern = "".join(
        re.escape(part) + ".+?" for part in parts[:-1]
    ) + re.escape(parts[-1])
    return re.compile(pattern, re.DOTALL)


def render_precheck_diagnostic(message: str, rules: list[dict]) -> list[str]:
    """当前生产预检只透传 str(exc)；同源渲染把消息映射回稳定编号。"""
    hits = [r["id"] for r in rules if template_to_regex(r["msg"]).fullmatch(message)]
    return hits


def render_prompt_fragment(rules: list[dict], only_unpublic: bool = True) -> list[str]:
    """把同一条规则定义渲染成候选可读的约束行（题面【工具目录】风格）。"""
    lines = ["【受限子集静态约束（AV-SUB，编号稳定；与执行器同一份定义渲染）】"]
    for rule in rules:
        if only_unpublic and rule["public"] == "VERBATIM":
            continue
        tag = {"PARTIAL": "部分公开", "ABSENT": "未公开"}[rule["public"]]
        lines.append(
            "  - {0}（{1}）：{2} ⇒ 拒绝装载；{3}".format(
                rule["id"], tag, rule["trigger"], rule["msg"]
            )
        )
    return lines


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules = data["rules"]
    qb = data["quote_bank"]
    synth = _synthetic()
    failures: list[str] = []

    emit("=" * 100)
    emit("AV-SUB 静态规则探针（零模型；执行器 %s，sha256=%s）"
         % (data["executor"]["version_constant"], data["executor"]["sha256"][:16]))
    emit("规则总数 %d；合同 sha256=%s" % (len(rules), data["public_authority"]["contract_sha256"][:16]))
    emit("=" * 100)

    # ---- 0. 公开证据逐条回读（题面行号 + 逐字引用） ----
    emit("")
    emit("[0] 公开证据机械校验（题面行号 → 逐字引用）")
    ev_total = ev_checked = 0
    for rule in rules:
        ev = rule["evidence"]
        if ev == "ABSENT":
            continue
        for alias, line_no, quote in ev:
            ev_total += 1
            if alias == "CONTRACT":
                path = _project_file(_PROJECT_ROOT, REPO / data["source_aliases"]["CONTRACT"])
            elif alias in data["source_aliases"]:
                path = expand_alias(data["source_aliases"][alias])
            else:
                failures.append("未知来源别名 %s" % alias)
                continue
            text = qb.get(quote, quote)
            lines = path.read_text(encoding="utf-8").split("\n")
            actual = lines[line_no - 1] if 0 < line_no <= len(lines) else "<越界>"
            if text.strip() and text.strip() in actual:
                ev_checked += 1
            else:
                failures.append("证据不符 %s %s:%d" % (rule["id"], alias, line_no))
            emit("  - %-11s %-9s L%-4d %s" % (rule["id"], alias, line_no, actual.strip()[:88]))
    emit("  证据条目 %d，逐字命中 %d" % (ev_total, ev_checked))

    # ---- 1. 逐条探针 ----
    emit("")
    emit("[1] 逐条正/反例实测（ActionValueExecutor 实际装载）")
    emit("  编号          行  可  公开    正例        反例                        判定")
    emit("  " + "-" * 96)
    neg_messages: dict[str, str] = {}
    pos_pass = pos_fail = neg_hit = neg_miss = syn_hit = 0
    for rule in rules:
        rid = rule["id"]

        # 正例
        if rule.get("pos") is None:
            pos_state = "n/a"
        else:
            state, detail = load(build_source(rule["pos"]))
            if state == "PASS":
                pos_state = "PASS"
                pos_pass += 1
            else:
                pos_state = "FAIL"
                pos_fail += 1
                failures.append("正例未通过 %s：%s %s" % (rid, state, detail))

        # 反例
        if rule.get("neg") is not None:
            state, detail = load(build_source(rule["neg"]))
            ok = state == "REJECT" and rule["expect"] in detail
            if ok:
                neg_state = "REJECT✓"
                neg_hit += 1
                neg_messages[rid] = detail
            else:
                neg_state = "MISS"
                neg_miss += 1
                failures.append("反例未按预期拒绝 %s：%s %s" % (rid, state, detail))
        elif "synth" in rule:
            try:
                synth[rule["synth"]]()
                neg_state = "NO-RAISE"
                neg_miss += 1
                failures.append("合成探针未触发 %s" % rid)
            except StaticCheckError as exc:
                if rule["expect"] in str(exc):
                    neg_state = "SYNTH✓"
                    syn_hit += 1
                    neg_messages[rid] = str(exc)
                else:
                    neg_state = "SYNTH-MISS"
                    neg_miss += 1
                    failures.append("合成探针消息不符 %s：%s" % (rid, exc))
            except BaseException as exc:
                neg_state = "SYNTH-CRASH"
                neg_miss += 1
                failures.append("合成探针异常类型 %s：%s" % (rid, exc))
        else:
            neg_state = "n/a(不可达)"

        emit("  %-11s L%-4d %-3s %-8s %-11s %-28s %s" % (
            rid, rule["line"], "是" if rule["reachable"] else "否",
            rule["public"],
            pos_state, neg_state, "" if pos_state != "FAIL" else "见失败清单"))

    # ---- 2. 缺陷：嵌套函数引用顶层函数名 ----
    emit("")
    emit("[2] 异常项探针（不是 StaticCheckError 的装载期失败）")
    for anomaly in data["anomalies"]:
        state, detail = load(build_source(anomaly["probe"]))
        ok = state == "CRASH:" + anomaly["expect_exception"]
        emit("  - %s %s → %s :: %s" % (anomaly["id"], state, "符合预期" if ok else "不符", detail))
        if not ok:
            failures.append("异常项探针不符 %s：%s %s" % (anomaly["id"], state, detail))

    # ---- 3. 不可达性证据 ----
    emit("")
    emit("[3] 不可达分支的证据（源码路径被上游规则先拦）")
    bypass = {
        "AV-SUB-010": "    view.x = 1\n    return 1\n",
        "AV-SUB-014": "    a = [1]\n    a[0] = 1\n    return a\n",
        "AV-SUB-018": None,
        "AV-SUB-020": None,
        "AV-SUB-025": None,
        "AV-SUB-050": None,
        "AV-SUB-056": '    d = {"a": 1}\n    e = {**d}\n    return e\n',
        "AV-SUB-059": None,
    }
    for rid, body in bypass.items():
        if body is None:
            continue
        state, detail = load(build_source({"s": body}))
        emit("  - %s 源码路径实测：%s :: %s" % (rid, state, detail))
    try:
        ast.parse("lambda a: int: a")
        emit("  - AV-SUB-020 lambda 参数注解语法：可解析（结论需复核）")
        failures.append("lambda 参数注解竟可解析")
    except SyntaxError:
        emit("  - AV-SUB-020 lambda 参数注解语法：SyntaxError（Python 语法不允许 ⇒ 不可达）")
    emit("  - AV-SUB-050 ast.parse 恒返回 Module：%s"
         % isinstance(ast.parse("x = 1"), ast.Module))
    emit("  - AV-SUB-018 _UNARY_OPS 覆盖全部一元运算：%s（%s）"
         % (set(_UNARY_OPS) == {ast.USub, ast.UAdd, ast.Not, ast.Invert},
            "/".join(sorted(_UNARY_OPS.values()))))
    emit("  - AV-SUB-059 每条正例装载后 callable(score_actions)=True：见 [1] 正例列")

    # ---- 4. 同源渲染：预检诊断 ----
    emit("")
    emit("[4] 同源渲染 A：预检诊断（消息 → AV-SUB 编号）")
    diag_ok = diag_bad = 0
    for rid, message in neg_messages.items():
        hits = render_precheck_diagnostic(message, rules)
        if hits == [rid]:
            diag_ok += 1
        else:
            diag_bad += 1
            failures.append("诊断映射不唯一 %s → %s" % (rid, hits))
    emit("  实测拒绝消息 %d 条；唯一命中自身编号 %d 条，歧义/未命中 %d 条"
         % (len(neg_messages), diag_ok, diag_bad))
    for rid in ("AV-SUB-007", "AV-SUB-011", "AV-SUB-033"):
        if rid in neg_messages:
            emit("  样例 %s :: %s" % (rid, render_precheck_diagnostic(neg_messages[rid], rules)[0]))

    # 现生产预检的分类能力（token 表逐字取自 sitin_model_admission.py）
    admission_py = _project_file(_PROJECT_ROOT, REPO / "review/llm-guided-heuristic-route-2026-09-15/tools/sitin_model_admission.py")
    src = admission_py.read_text(encoding="utf-8")
    match = re.search(r'for token in \(([^)]*)\)', src)
    tokens = re.findall(r'"([^"]+)"', match.group(1)) if match else []
    emitted_map = {}
    for rid, message in neg_messages.items():
        rule = next(r for r in rules if r["id"] == rid)
        if rule["public"] == "VERBATIM":
            continue
        emitted_map[rid] = any(tok in message for tok in tokens)
    caught = [rid for rid, hit in emitted_map.items() if hit]
    emit("  现生产分类器 token 表（sitin_model_admission.py:_violating_static_reason）= %s" % tokens)
    emit("  未公开规则中，拒绝消息能被现分类器判为『受限子集硬禁项』的：%d / %d %s"
         % (len(caught), len(emitted_map), caught))

    # ---- 5. 同源渲染：候选提示片段 ----
    emit("")
    emit("[5] 同源渲染 B：候选提示片段（未公开/部分公开规则 → 题面补充约束行）")
    fragment = render_prompt_fragment(rules, only_unpublic=True)
    emit("  渲染行数 %d（%d 条规则中按公开判据筛出）" % (len(fragment) - 1, len(rules)))
    for line in fragment[:8]:
        emit("  " + line)
    emit("  …（完整片段见 RULES.json 与 REPORT.md 的『未公开规则清单』）")

    # ---- 6. 汇总 ----
    unpublic = [r for r in rules if r["public"] != "VERBATIM"]
    absent = [r for r in rules if r["public"] == "ABSENT"]
    partial = [r for r in rules if r["public"] == "PARTIAL"]
    emit("")
    emit("=" * 100)
    emit("[6] 汇总")
    emit("  规则总数 %d：完全公开(VERBATIM) %d；部分公开(PARTIAL) %d；完全未公开(ABSENT) %d"
         % (len(rules), len(rules) - len(unpublic), len(partial), len(absent)))
    emit("  未公开+部分公开合计 %d 条" % len(unpublic))
    emit("  不可达分支 %d 条：%s"
         % (len([r for r in rules if not r["reachable"]]),
            [r["id"] for r in rules if not r["reachable"]]))
    emit("  正例通过 %d 条，正例失败 %d 条" % (pos_pass, pos_fail))
    emit("  反例实测触发 %d 条（装载 REJECT %d + 合成 %d），未触发/不符 %d 条"
         % (neg_hit + syn_hit, neg_hit, syn_hit, neg_miss))
    emit("  证据回读命中 %d/%d" % (ev_checked, ev_total))
    emit("  失败项 %d 条" % len(failures))
    for item in failures:
        emit("    ! " + item)
    emit("  结论：%s" % ("全部通过" if not failures else "存在失败项，须复核"))
    emit("=" * 100)

    text = "\n".join(LOG) + "\n"
    OUT_PATH.write_text(text, encoding="utf-8")
    print(text)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
