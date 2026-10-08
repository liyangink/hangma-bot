"""准备等待候选的隔离运行输入；不编译、不评分、不改线上包。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1')
ROOT = _PROJECT_ROOT
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
WORK = _project_file(_PROJECT_ROOT, '.private/t191-wait-runtime/workspace')
PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/wait-confirmation-1/wait-confirmation-001-PLAN.json')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from t185_prepare_confirmation import background_priority, postprocess_lock


def require(condition, message):
    """输入或身份不符即停止；不覆盖原失败、不自动重新准备。"""
    if not condition:
        raise ValueError(message)


def main():
    """只复制已验字节并生成Cython输入；启动独立解释器只验四个旧包。"""
    background_priority()
    with postprocess_lock("t191-wait-runtime-input-preparation"):
        from hangma_bot import bootstrap as b
        plan = json.loads(PLAN.read_text())
        require(plan["schema"] == "t191-single-confirmation/1" and len(plan["candidates"]) == 1,
            "不是唯一冻结确认候选")
        require(all(pin(Path(p)) == expected for p, expected in plan["files"].items()), "确认冻结输入漂移")
        actual_sources = b._vip_runtime_sources()
        require(set(actual_sources) == set(plan["source_manifest"]) and len(actual_sources) == 182 and
            all(actual_sources[name] == expected["sha256"] and pin(_project_file(_PROJECT_ROOT, ROOT / name)) == expected
                for name, expected in plan["source_manifest"].items()),
            "运行副本未绑定当前182来源")
        candidate = plan["candidates"][0]
        candidate_path = Path(candidate["source_file"])
        source = candidate_path.read_text()
        require(hashlib.sha256(source.encode()).hexdigest() == candidate["identity"]["source_sha256"],
            "候选源码摘要不符")
        strategies = (b.VIP_S02_TESTROOM_SUCCESSOR_STRATEGY, b.VIP_S02_FREE_SUCCESSOR_STRATEGY,
            b.VIP_S02_TEST_TOURNAMENT_STRATEGY, b.VIP_S02_OFFICIAL_TOURNAMENT_STRATEGY)
        packages = {s: b._load_vip_manifest(s) for s in strategies}
        shared, _ = b._verify_vip_s02_runtime()
        require(not WORK.exists() and not (_project_file(_PROJECT_ROOT, HERE / "START.json")).exists(), "原副本/尝试存在，不覆盖")
        names = set(actual_sources)
        for strategy, package in packages.items():
            require(package["source_manifest"] == actual_sources, "四作用域来源不同")
            names.add(b._vip_package_scope(strategy)[2])
            names.update(package["evidence_sha256"])
        names.update(("pyproject.toml", "configs/vip-s02-bounded-d1-v9.test-room.example.json",
            "configs/vip-s02-bounded-d1-v7.free-match.example.json",
            "configs/vip-s02-bounded-d1.test-tournament.example.json",
            "configs/vip-s02-bounded-d1.official-tournament.example.json"))
        native = _project_file(_PROJECT_ROOT, ROOT / b.VIP_S02_COMPILED_DIRECTORY)
        native_manifest = shared["manifest"]
        names.add(b.VIP_S02_COMPILED_DIRECTORY + "/manifest.json")
        names.update(b.VIP_S02_COMPILED_DIRECTORY + "/" + n for n in native_manifest["generated_source_sha256"])
        names.update(b.VIP_S02_COMPILED_DIRECTORY + "/" + value["filename"]
            for value in native_manifest["binaries"].values())
        names.update(p.relative_to(ROOT).as_posix() for p in (_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma")).glob("*.so"))
        for name in names:
            p = Path(name)
            require(not p.is_absolute() and ".." not in p.parts and p.parts[0] != ".private" and
                (_project_file(_PROJECT_ROOT, ROOT / p)).resolve().is_relative_to(ROOT), "拒绝私有凭证和仓库外路径")
        files = {name: pin(_project_file(_PROJECT_ROOT, ROOT / name)) for name in sorted(names)}
        original = _project_file(_PROJECT_ROOT, PRIOR / "prepare_candidate_native.py")
        spec = importlib.util.spec_from_file_location("_t191_original_native_material", original)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        parent = tool.material(b.VIP_S02_SOURCE)
        require(parent["candidate_pyx"].encode() == (native / "_s02_candidate.pyx").read_bytes() and
            parent["meter_pxd"].encode() == (native / "_s02_meter.pxd").read_bytes(),
            "原体转换器未复现当前S02原字节")
        body = tool.material(source)
        require(body["candidate_source_sha256"] == candidate["identity"]["source_sha256"] and
            body["meter_pxd"].encode() == (native / "_s02_meter.pxd").read_bytes(), "新原体/共享ABI不符")
        inputs = {str(p): pin(p) for p in (Path(__file__), PLAN, candidate_path,
            original, tool.ORIGINAL_GENERATOR, tool.ORIGINAL_PLAN)}
        save(_project_file(_PROJECT_ROOT, HERE / "START.json"), {"at_utc": datetime.now(timezone.utc).isoformat(), "workspace": str(WORK),
            "source_files": files, "preparation_input_files": inputs, "candidate": candidate,
            "cpu_nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io_actual_success": True,
            "new_compilations_scores_worlds_tables_HTTP_models_compute_workers": 0})
        WORK.mkdir(parents=True, mode=0o700)
        failure, answer, generated = None, None, {}
        try:
            for name, expected in files.items():
                target = _project_file(_PROJECT_ROOT, WORK / name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_project_file(_PROJECT_ROOT, ROOT / name), target)
                require(pin(target) == expected, "副本字节不同:" + name)
            draft = _project_file(_PROJECT_ROOT, WORK / "draft-candidate")
            draft.mkdir()
            (draft / "source.py").write_text(source)
            module_name = "_t191_candidate_" + candidate["identity"]["candidate_id"][:12]
            (draft / (module_name + ".pyx")).write_text(body.pop("candidate_pyx"))
            (draft / "_s02_meter.pxd").write_text(body.pop("meter_pxd"))
            generated = {p.relative_to(WORK).as_posix(): pin(p) for p in draft.iterdir()}
            code = (
                "import json; from pathlib import Path; from hangma_bot import bootstrap as b; "
                "assert Path(b.__file__).resolve().is_relative_to(Path.cwd()); "
                "ss=(b.VIP_S02_TESTROOM_SUCCESSOR_STRATEGY,b.VIP_S02_FREE_SUCCESSOR_STRATEGY,"
                "b.VIP_S02_TEST_TOURNAMENT_STRATEGY,b.VIP_S02_OFFICIAL_TOURNAMENT_STRATEGY); "
                "print(json.dumps({'bootstrap':b.__file__,'source_count':len(b._vip_runtime_sources()),"
                "'packages':{s:b._load_vip_manifest(s)['release_package_id'] for s in ss},"
                "'native':b._verify_vip_s02_runtime()[0],'math':b.hand_math_runtime_metadata()}))"
            )
            env = {**os.environ, "PYTHONPATH": str(_project_file(_PROJECT_ROOT, WORK / "src")) + os.pathsep + str(WORK),
                "PYTHONDONTWRITEBYTECODE": "1"}
            proc = subprocess.run([sys.executable, "-c", code], cwd=WORK, env=env, capture_output=True)
            save(_project_file(_PROJECT_ROOT, HERE / "PREFLIGHT-RECEIPT.json"), {"actual_exit_code": proc.returncode,
                "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(), "validation_interpreters_started": 1,
                "compute_workers_started": 0, "scores_worlds_tables_HTTP_models": 0})
            require(proc.returncode == 0, "四包隔离预检失败，保留原件:" + proc.stderr.decode()[-1000:])
            answer = json.loads(proc.stdout)
            require(answer["packages"] == {s: v["release_package_id"] for s, v in packages.items()} and
                answer["source_count"] == 182 and answer["native"] == shared and
                answer["math"] == b.hand_math_runtime_metadata(), "副本装配身份不同")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        stable = all(pin(_project_file(_PROJECT_ROOT, ROOT / name)) == expected for name, expected in files.items()) and \
            all(pin(Path(p)) == expected for p, expected in inputs.items())
        complete = failure is None and stable and answer is not None
        save(_project_file(_PROJECT_ROOT, HERE / "CLOSED.json"), {"complete": complete, "failure": failure, "source_stable": stable,
            "workspace": str(WORK), "files": files, "preparation_input_files": inputs,
            "generated_candidate_input_files": generated, "material": body, "candidate": candidate,
            "preflight": answer, "shared_original_helpers_only": True,
            "new_candidate_formula_compiled": False, "baseline_copy_not_candidate_wiring": True,
            "candidate_strength_equivalence_deadline_or_online_admission": False,
            "production_sources_manifests_tokens_or_watchdog_modified": False,
            "new_compilations_scores_worlds_tables_HTTP_models_compute_workers": 0})
        require(complete, "隔离输入准备未通过；保留副本与失败，不自动重做")
        print(json.dumps({"complete": complete, "copied_files": len(files), "source_count": 182,
            "generated_candidate_inputs": len(generated), "candidate_admission": False}), flush=True)


if __name__ == "__main__":
    main()
