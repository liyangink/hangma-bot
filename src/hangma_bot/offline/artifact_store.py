"""本机制品定位与历史整理；保留原文，以相对路径和 SHA-256 支持迁移。

不读取凭证，不连接平台。运行制品与派生/封存副本分开发现，避免四身份
被重复计入；同 run_id 内容冲突必须由调用方处理，不能任选一份覆盖。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from hangma_bot.adapters.recording.bundle import sha256_file

_EXCLUDED = {".git", ".venv", ".team-work", "__pycache__", "bundles", "combined", "derived", "postgame", "archives"}


def catalog_sessions(root: Path) -> dict:
    """生成各会话最新已完成报告的相对索引；重叠历史集不合计为训练样本数。"""
    root = root.resolve()
    sessions = []
    for directory, children, files in os.walk(root, followlinks=False):
        children[:] = sorted(c for c in children if c not in _EXCLUDED and not (Path(directory) / c).is_symlink())
        if "latest-postgame.json" not in files:
            continue
        session = Path(directory)
        latest = json.loads((session / "latest-postgame.json").read_text())
        job = (session / latest["job"]).resolve()
        if root not in job.parents:
            raise ValueError("制品索引指向根目录外部")
        report = json.loads((job / "report.json").read_text())
        sessions.append({"session": session.relative_to(root).as_posix(), "report": (job / "report.json").relative_to(root).as_posix(),
            "report_sha256": sha256_file(job / "report.json"), "run_count": report["run_count"],
            "official_documents": report["official_documents"], "audit_complete": report["audit_complete"],
            "decisions": report["dataset_summary"]["decisions_total"], "hands": report["dataset_summary"]["hands_total"]})
    result = {"schema_version": 1, "sessions": sessions, "note": "历史集可能覆盖同一场次，禁止直接合计训练样本；按场次键和来源筛选"}
    write_json(root / "catalog.json", result)
    return result


def write_json(path: Path, document: object) -> None:
    """JSON 原子落盘；同名控制由用例负责，未完成写入留在 .partial。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def discover_runs(root: str | Path) -> list[Path]:
    """发现单身份、四身份或规范 session 的全部原始 run，跳过派生副本。

    必须具有 manifest 和 participants；活动 run 也返回，由封存命令检查关闭。
    根目录本身可以是 run 或解包后的 bundle。
    """
    root = Path(root).resolve()
    found = []
    for directory, children, files in os.walk(root, followlinks=False):
        path = Path(directory)
        children[:] = sorted(c for c in children if c not in _EXCLUDED and not (path / c).is_symlink())
        if "manifest.json" in files and (path / "participants").is_dir():
            found.append(path)
            children[:] = []
    return sorted(found)


def migrate_runs(legacy: str | Path, artifacts: str | Path) -> dict:
    """把已关闭的旧 runs 根整体移入 artifacts/legacy/runs，旧位置保留相对入口。

    原文件不重写、不删除，已有目标拒绝覆盖；缺 summary 的运行拒绝迁移。
    迁移前还应确认没有正在启动新进程，CLI 不向任何进程发送信号。
    """
    legacy, artifacts = Path(legacy).absolute(), Path(artifacts).absolute()
    target = artifacts / "legacy" / "runs"
    if legacy.is_symlink() and legacy.resolve() == target.resolve():
        return {"status": "already_migrated", "target": str(target)}
    if not legacy.is_dir() or target.exists():
        raise ValueError("旧 runs 不存在或迁移目标已存在，拒绝覆盖")
    if legacy == artifacts or legacy in artifacts.parents:
        raise ValueError("制品目录不能位于待迁移目录内部")
    active = [r.name for r in discover_runs(legacy) if not (r / "summary.json").is_file()]
    if active:
        raise ValueError("存在未关闭运行，拒绝迁移：" + ", ".join(active))
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy.rename(target)
    try:
        legacy.symlink_to(os.path.relpath(target, legacy.parent), target_is_directory=True)
    except OSError:
        target.rename(legacy)
        raise
    return {"status": "migrated", "target": str(target), "compatibility_link": str(legacy)}


def import_official_history(sources: list[Path], out: Path, *, project_root: Path) -> dict:
    """归并历史官方原文；相同字节只保存一次，多份来源全部保留。

    只接受具有 game_id、blocks、rounds 的官方牌谱对象，不扫描配置/Token。
    摘要是否一致交赛后分析判断；去重不意味着内容已通过规则验证。
    """
    objects, errors = {}, []
    candidates = set()
    for source in sources:
        if source.is_file():
            candidates.add(source.resolve())
        else:
            for directory, children, files in os.walk(source, followlinks=False):
                path = Path(directory)
                children[:] = [c for c in children if c not in _EXCLUDED and not (path / c).is_symlink()]
                if "official" not in path.parts and source.name != "official":
                    continue
                candidates.update((path / f).resolve() for f in files if f.endswith(".json") and f not in {"source.json", "meta.json", "games.json", "_games.json"})
    for path in sorted(candidates):
        try:
            data = json.loads(path.read_bytes())
        except (ValueError, OSError):
            errors.append({"path": os.path.relpath(path, project_root), "reason": "unreadable_json"})
            continue
        if not isinstance(data, dict) or not isinstance(data.get("game_id"), str) or not isinstance(data.get("blocks"), list) or not isinstance(data.get("rounds"), list):
            continue
        digest = sha256_file(path)
        relative = os.path.relpath(path, project_root)
        entry = objects.setdefault(digest, {"sha256": digest, "game_id": data["game_id"], "room_id": data.get("room_id"), "batch": data.get("batch"), "sources": [], "bytes": path.stat().st_size})
        entry["sources"].append(relative)
        def remember_config(config):
            prior = out / "official" / digest / "source.json"
            previous = json.loads(prior.read_text()).get("rule_config") if prior.is_file() else None
            for existing in (entry.get("rule_config"), previous):
                if existing and any(existing.get(k) != config.get(k) for k in ("base_score", "you_cai_bi_kao")):
                    raise ValueError("同一原文的历史规则配置冲突：" + relative)
            entry["rule_config"] = config
        # 原下载 sidecar 和历史会话 META 是配置依据，不从目录名猜布尔规则。
        sidecar = path.parent / "source.json"
        if sidecar.is_file():
            metadata = json.loads(sidecar.read_text())
            if metadata.get("rule_config"):
                remember_config(metadata["rule_config"])
            for key in ("guide_version", "captured_at", "captured_at_unix_ms"):
                if metadata.get(key) is not None:
                    entry[key] = metadata[key]
        for parent in path.parents:
            if parent == project_root or project_root not in parent.parents:
                break
            meta = parent / "meta.json"
            if meta.is_file():
                room_config = json.loads(meta.read_text()).get("room_config", {})
                if isinstance(room_config.get("YouCaiBiKao"), bool) and type(room_config.get("BaseScore")) is int:
                    remember_config({"base_score": room_config["BaseScore"], "you_cai_bi_kao": room_config["YouCaiBiKao"]})
                    entry["rule_config_source"] = os.path.relpath(meta, project_root)
                break
        target = out / "official" / digest
        target.mkdir(parents=True, exist_ok=True)
        events = target / "events.json"
        if events.exists() and sha256_file(events) != digest:
            raise ValueError("历史归并对象已损坏：" + str(events))
        if not events.exists():
            shutil.copy2(path, events)
    for digest, entry in objects.items():
        target = out / "official" / digest
        previous = json.loads((target / "source.json").read_text()) if (target / "source.json").exists() else {}
        entry["sources"] = sorted(set(entry["sources"] + previous.get("original_paths", [])))
        write_json(target / "source.json", {"download_id": digest, "game_id": entry["game_id"], "room_id": entry["room_id"], "batch": entry["batch"], "original_sha256": digest,
            "original_paths": entry["sources"], "captured_at": previous.get("captured_at"), "imported_at": datetime.now(timezone.utc).isoformat(),
            **{k: entry.get(k, previous.get(k)) for k in ("guide_version", "captured_at", "captured_at_unix_ms", "rule_config", "rule_config_source")},
            "provenance_note": "历史原文逐字节归并；未知采集日期/指南版本不推定"})
    partial_runs = import_partial_audits(sources, out, project_root=project_root)
    report = {"schema_version": 1, "objects": list(objects.values()), "partial_audit_runs": partial_runs, "unique_documents": len(objects),
        "source_copies": sum(len(x["sources"]) for x in objects.values()), "errors": errors}
    write_json(out / "history-import.json", report)
    return report


def import_partial_audits(sources: list[Path], out: Path, *, project_root: Path) -> list[dict]:
    """把历史 bot-audit 扁平副本恢复为标准目录布局，原记录逐字节复制。

    这是布局恢复而非数据恢复；缺失 raw 永远明确标记，不生成假观察/假运行。
    同名已导入文件仅在字节一致时复用。
    """
    imported = []
    for source in sources:
        if not source.is_dir():
            continue
        for manifest in sorted(source.glob("**/bot-audit/*/*/manifest.json")):
            document = json.loads(manifest.read_text())
            context = document.get("context", {})
            run_id, pid = context.get("run_id"), context.get("participant_id")
            if not all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", v) and v not in {".", ".."} for v in (run_id, pid)):
                raise ValueError("历史审计身份缺失或不合法")
            target = out / "audit" / "runs" / run_id
            sources_map = []
            for path in sorted(manifest.parent.rglob("*")):
                if not path.is_file():
                    continue
                if path.is_symlink():
                    raise ValueError("历史审计含链接，拒绝导入")
                relative = path.relative_to(manifest.parent)
                destination = target / relative if relative.as_posix() in {"manifest.json", "summary.json", "lifecycle.jsonl"} else target / "participants" / pid / relative
                digest = sha256_file(path)
                if destination.exists() and sha256_file(destination) != digest:
                    raise ValueError("同 run_id 的历史审计内容冲突")
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    shutil.copy2(path, destination)
                sources_map.append({"original": os.path.relpath(path, project_root), "file": destination.relative_to(target).as_posix(), "sha256": digest})
            note = {"source_kind": "partial_audit_copy", "missing_raw": not (manifest.parent / "raw").is_dir(), "files": sources_map}
            write_json(target / "imported-layout.json", note)
            imported.append({"run_id": run_id, "missing_raw": note["missing_raw"], "path": target.relative_to(out).as_posix()})
    return imported
