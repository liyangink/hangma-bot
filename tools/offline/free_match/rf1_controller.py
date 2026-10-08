"""RF1自由赛单Token控制入口：复用原自然完赛/续赛/后处理，只适配修复准入。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t227-rf1-default-and-live-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
ENTRY_RELATIVE = 'tools/offline/free_match/rf1_controller.py'
BASE_DIRECTORY = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime')
sys.path[:0] = [str(_project_file(_PROJECT_ROOT, ROOT / "src")), str(ROOT), str(BASE_DIRECTORY)]
import controller as original

# 原控制器的worker/后处理spawn和只读status也必须指回本RF1入口。
# 未修改旧文件，已冻结的P0控制器继续保留原路径与资格逻辑。
original.ENTRY_RELATIVE = ENTRY_RELATIVE
gate = original.gate


def free_players_from_ps(output: str) -> list[int]:
    """仅识别全局自由赛入口；四测试Token/赛事注册Token属于独立认证域。"""
    players = []
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        command = parts[1]
        if "python" in command.split()[0].lower() and (
                "/run_auto_match.py " in command or " scripts/run_auto_match.py " in command):
            players.append(int(parts[0]))
    return players


def other_free_players() -> list[int]:
    """只读进程；权限失败保持错误，不能猜全局Token没有玩家。"""
    result = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True)
    if result.returncode:
        raise gate.GateError("无法核实全局自由赛玩家，禁止重复匹配")
    return free_players_from_ps(result.stdout)


class Controller(original.Controller):
    """沿用所有owner/自然终态/资源回收保护，不伪造P0或强度准入。"""

    def __init__(self, *args, **kwargs):
        """自由赛检查不因其他四个独立测试房Token的玩家而停续。"""
        super().__init__(*args, **kwargs)
        if hasattr(self.tools, "h"):
            self.tools.h.other_players = other_free_players

    def check_admission(self) -> dict:
        """逐包核RF1真实修复收据；缺件/漂移在匹配与资源装配前拒绝。"""
        checked = gate.preflight(self.spec)
        if (Path(__file__).resolve() != self.ROOT / ENTRY_RELATIVE
                or ENTRY_RELATIVE not in self.spec["files"]
                or self.spec.get("preparation_only") is not False):
            raise gate.GateError("RF1实际入口、源码冻结或启动授权不符")
        import hangma_bot.bootstrap as bootstrap
        from hangma_bot.policy import vip_g37_rf1_release as release
        if bootstrap._REPO_ROOT.resolve() != self.ROOT:
            raise gate.GateError("RF1组合根已缓存另一根，须新解释器启动")
        qualification = self.spec.get("qualification", {})
        required = {"repair_passed": "repair_passed",
                    "native_equivalence_passed": "native_equivalence_passed",
                    "runtime_passed": "runtime_passed_for_covered_legal_deadline_and_fault_recovery",
                    "corrected_fallback_passed": "corrected_fallback_passed_for_covered_faults",
                    "representative_regression_passed": "representative_regression_passed"}
        if qualification.get("release_kind") != "scoring_defect_repair":
            raise gate.GateError("RF1必须独立修复准入，不能冒认P0或增强资格")
        for flag, field in required.items():
            receipt = qualification.get("receipts", {}).get(flag)
            if qualification.get(flag) is not True or not receipt:
                raise gate.GateError("RF1实际修复收据未闭：" + flag)
            path = Path(receipt["path"])
            if (not path.resolve().is_relative_to(self.ROOT)
                    or gate.pin(path) != receipt["pin"]):
                raise gate.GateError("RF1收据原件缺失/逃逸/漂移：" + flag)
            proof = gate.read_json(path)
            if (proof.get("complete") is not True or proof.get(field) is not True
                    or proof.get("candidate_identity") != release.VIP_G37_RF1_IDENTITY
                    or proof.get("rules_source_hash") != bootstrap.compute_rules_hash(self.ROOT)):
                raise gate.GateError("RF1修复原件身份或结果不符：" + flag)
        for mode, relative in self.spec["mode_manifests"].items():
            payload = gate.read_json(gate.relative_file(self.ROOT, relative))
            if payload["strategy"] not in release.PACKAGE_SCOPES:
                raise gate.GateError("RF1四包装载不能混入其他算法")
            loaded = bootstrap._load_vip_manifest(payload["strategy"], payload["release_package_id"])
            if loaded["allowed_modes"] != [mode] or loaded["strength_admission"] is not False:
                raise gate.GateError("RF1作用域或修复发布范围不符")
        package = bootstrap._load_vip_manifest(self.spec["identity"]["free_strategy"],
                                               self.spec["identity"]["package_ids"]["free"])
        actual = {"free_strategy": package["strategy"], "package_ids": {"free": package["release_package_id"]},
                  "rules_source_hash": bootstrap.compute_rules_hash(self.ROOT),
                  "hand_math": bootstrap.hand_math_runtime_metadata()}
        if actual != self.spec["identity"] or package["allowed_modes"] != ["auto_match"]:
            raise gate.GateError("RF1自由赛实际身份不符")
        credential = self.spec.get("credential_path")
        if not credential or Path(credential).resolve().is_relative_to(self.ROOT):
            raise gate.GateError("自由赛凭据必须在冻结根外")
        return {**checked, "repair_publication_verified": True, "strength_admission": False}


def main():
    """inspect/status只读；watch自然续赛；worker低CPU/IO后台且共用原锁。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "status", "watch", "worker", "postprocess-job"])
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--postprocess-fd", type=int)
    args = parser.parse_args()
    if args.command == "postprocess-job":
        original.postprocess_job(args.spec, args.batch, args.postprocess_fd)
        return
    value = Controller(args.spec)
    if args.command in ("inspect", "status"):
        import json
        result = value.check_admission() if args.command == "inspect" else value.status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "watch":
        value.watch()
    else:
        value.worker()


if __name__ == "__main__":
    main()
