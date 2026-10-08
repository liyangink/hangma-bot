"""用真实公开脚本接口解析四作用域配置并装配；只注入公开假身份会话。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wiring'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile


def main():
    """输入隔离副本和输出证据路径；不读取Token、不调用run、不启动工作进程。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    sys.path[:0] = [str(workspace), str(workspace / "src")]
    import hangma_bot.bootstrap as assembly
    from scripts.run_test_room import load_room_config, child_config_mapping, TOKEN_ENV_VAR
    from scripts.run_participant import load_config
    from scripts.run_auto_match import load_config as load_auto

    async def verify():
        cases = []
        sandbox = workspace / ".verification"
        sandbox.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=sandbox) as temporary:
            async def assemble(config, path, identity=None, settings=None):
                payload = json.loads((workspace / path).read_text())
                assert config.strategy == payload["strategy"]
                assert config.expected_policy_release_id == payload["expected_policy_release_id"]
                assert config.sse_enabled is True and config.known_guide_version == payload["known_guide_version"]
                config = replace(config, audit_root=Path(temporary) / (identity or config.mode.value))
                unit = (assembly.build_runtime(config, session_factory=lambda: object()) if settings is None
                    else assembly.build_auto_match_runtime(config, settings, session_factory=lambda: object()))
                await unit.compute.close()
                await unit.sink.aclose(timeout_seconds=1)
                cases.append(dict(config=path, identity=identity, strategy=config.strategy,
                    scope=config.mode.value, token_kind=config.token_kind.value,
                    release_id=config.expected_policy_release_id, accepted=True))

            path = "configs/vip-s02-bounded-d1-v9.test-room.example.json"
            names = ("qinglong", "baihu", "zhuque", "xuanwu")
            room = load_room_config(workspace / path,
                environ={"HM_ROOM_TOKEN_" + name.upper(): "public-fake-only" for name in names})
            for identity in room.identities:
                child = child_config_mapping(room, identity)
                assert "token" not in child and child["token_env"] == TOKEN_ENV_VAR
                config = assembly.runtime_config_from_mapping(child, environ={TOKEN_ENV_VAR: "public-fake-only"})
                await assemble(config, path, identity=identity.slot)
            path = "configs/vip-s02-bounded-d1-v7.free-match.example.json"
            config, settings = load_auto(workspace / path, environ={"HM_AUTO_MATCH_TOKEN": "public-fake-only"})
            await assemble(config, path, settings=settings)
            for kind in ("test", "official"):
                path = "configs/vip-s02-bounded-d1." + kind + "-tournament.example.json"
                config = load_config(workspace / path,
                    environ={"HM_" + kind.upper() + "_TOURNAMENT_TOKEN": "public-fake-only"})
                await assemble(config, path)
        return cases

    cases = asyncio.run(verify())
    sources = {name: hashlib.sha256((workspace / name).read_bytes()).hexdigest()
        for name in ("src/hangma_bot/bootstrap.py", "scripts/run_test_room.py",
            "scripts/run_participant.py", "scripts/run_auto_match.py")}
    args.output.write_text(json.dumps(dict(cases=cases, source_sha256=sources, network_started=False,
        real_tokens_read=False, worker_processes_started=False, configuration_placeholders_remaining=True,
        tournament_entry="scripts/run_participant.py; repository contains no run_tournament.py"),
        ensure_ascii=False, indent=2) + "\n")
    print(len(cases), "public script/config/factory assemblies passed")


if __name__ == "__main__":
    main()
