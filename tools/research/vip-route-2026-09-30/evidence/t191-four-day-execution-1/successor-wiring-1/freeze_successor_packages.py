"""在已准备隔离副本冻结S03四包及S02四备用包，不联网或启动玩家。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1'

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
import sys
from pathlib import Path

_ALLOW_VERIFIED_EXISTING = False  # 仅明确恢复已知首次解析失败时允许核同已有包，不覆盖。


def pin(path):
    """指定公开文件的实际身份，字节数无单位，SHA为十六进制。"""
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """只写新包和新配置，既有冻结身份不得覆盖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if _ALLOW_VERIFIED_EXISTING and path.exists():
        assert path.read_text() == text, "已知部分产物与重新生成结果不同，禁止覆盖: " + str(path)
        return
    with path.open("x") as stream:
        stream.write(text)


def main():
    """通过真实组合根构建并再装载；全作用域共享公式、来源与运行参数。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-known-partial", action="store_true")
    args = parser.parse_args()
    assert not args.output.exists(), "已闭合或未知输出不能重做"
    global _ALLOW_VERIFIED_EXISTING
    _ALLOW_VERIFIED_EXISTING = args.resume_known_partial
    work = args.workspace.resolve()
    sys.path[:0] = [str(work / "src"), str(work)]
    from hangma_bot import bootstrap as b
    assert Path(b.__file__).resolve().is_relative_to(work), "误导入生产组合根"
    evidence = b.VIP_S03_REQUIRED_EVIDENCE_SHA256
    rows = []
    sources_before = b._vip_runtime_sources()
    for family, scopes in (("T110-S03", b.VIP_S03_PACKAGE_SCOPES), ("T110-S02-backup", b.VIP_S02_BACKUP_PACKAGE_SCOPES)):
        for strategy, (mode, admission, relative) in scopes.items():
            package = (b.build_vip_s03_manifest(strategy, evidence) if family == "T110-S03"
                else b._build_vip_manifest(strategy, evidence))
            save(work / relative, package)
            assert b._load_vip_manifest(strategy, package["release_package_id"]) == package
            if mode == "test_room":
                template = work / "configs/vip-s02-bounded-d1-v9.test-room.example.json"
                version = 1 if family == "T110-S03" else 10
                name = f"vip-{'s03' if family == 'T110-S03' else 's02'}-bounded-d1-v{version}.test-room.example.json"
            elif mode == "auto_match":
                template = work / "configs/vip-s02-bounded-d1-v7.free-match.example.json"
                version = 1 if family == "T110-S03" else 8
                name = f"vip-{'s03' if family == 'T110-S03' else 's02'}-bounded-d1-v{version}.free-match.example.json"
            else:
                kind = "official" if mode == "official_tournament" else "test"
                template = work / f"configs/vip-s02-bounded-d1.{kind}-tournament.example.json"
                name = (f"vip-s03-bounded-d1.{kind}-tournament.example.json" if family == "T110-S03"
                    else f"vip-s02-bounded-d1-v2.{kind}-tournament.example.json")
            config = json.loads(template.read_text())
            config["strategy"] = strategy
            config["expected_policy_release_id"] = package["release_package_id"]
            if mode == "test_room":
                for item in config["identities"]:
                    item["strategy"] = strategy
                    item["expected_policy_release_id"] = package["release_package_id"]
            config["audit_root"] = f"artifacts/sessions/{strategy.replace('_', '-')}"
            config["sse_enabled"] = True
            config["discard_pacing_enabled"] = False
            output = work / "configs" / name
            save(output, config)
            if mode == "test_room":
                from scripts.run_test_room import load_room_config, child_config_mapping, TOKEN_ENV_VAR
                room = load_room_config(output, environ={i["token_env"]: "public-fake-only" for i in config["identities"]})
                parsed = [b.runtime_config_from_mapping(child_config_mapping(room, item),
                    environ={TOKEN_ENV_VAR: "public-fake-only"}) for item in room.identities]
                assert len(parsed) == 4
            elif mode == "auto_match":
                from scripts.run_auto_match import load_config
                runtime, settings = load_config(output, environ={config["token_env"]: "public-fake-only"})
                assert settings.declared_max_games == 10 and settings.declared_rounds == 8
                parsed = [runtime]
            else:
                parsed = [b.runtime_config_from_mapping(config, environ={config["token_env"]: "public-fake-only"})]
            assert all(p.strategy == strategy and p.expected_policy_release_id == package["release_package_id"] for p in parsed)
            rows.append({"family": family, "strategy": strategy, "mode": mode, "admission": admission,
                "package_id": package["release_package_id"], "package_path": relative,
                "package_pin": pin(work / relative), "config_path": output.relative_to(work).as_posix(),
                "config_pin": pin(output), "public_config_assemblies": len(parsed)})
    assert b._vip_runtime_sources() == sources_before and len(rows) == 8
    assert len({r["package_id"] for r in rows}) == 8
    save(args.output, {"complete": True, "workspace": str(work), "source_manifest": sources_before,
        "rows": rows, "new_scores_worlds_tables_HTTP_model_calls_compute_workers": 0,
        "real_online_or_formal_admission": False, "official_test_tournament_not_required": True})
    print(json.dumps({"complete": True, "packages": len(rows), "parsed_configs": sum(r["public_config_assemblies"] for r in rows),
        "new_scores_HTTP_workers": 0}))


if __name__ == "__main__":
    main()
