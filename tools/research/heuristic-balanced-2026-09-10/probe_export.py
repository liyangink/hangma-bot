"""确认 export_hand 能否提供自然窗口反事实所需的单局起点与动作前缀。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import sys, json
sys.path.insert(0, 'tools/research/big-hand-paths-2026-09-09')
sys.path.insert(0, 'src')
from lab import ROOT, RULESET, HangmaRules, RuleConfig
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.offline.evaluate import MatchSeedSpec
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec

raw = HangmaRules(RuleConfig(RULESET, 1, False))
engine = SimulationEngine(raw, rules_hash=compute_rules_hash(ROOT))
config = TournamentConfig(1, 8, raw.config, TimingConfig(1, 1, 3))
spec = MatchSpec(match_id='probe-export', scenario_id='probe-export', config=config, seed=1193000,
                 initial_dealer=0, initial_scores=(0, 0, 0, 0))
world = engine.start(spec)
frame = engine.frame(world)
print('frame keys:', [k for k in dir(frame) if not k.startswith('_')][:12])
print('decision sample:', [ (d.window_key.seat, str(d.window_key.phase)) for d in frame.decisions ][:6])
row = engine.export_hand(world, 1)
print('export row keys:', sorted(row.keys()))
initial = row.get('initial') or {}
print('initial keys:', sorted(initial.keys()) if isinstance(initial, dict) else type(initial))
payload = (initial or {}).get('world_payload') or {}
print('payload keys:', sorted(payload.keys()) if isinstance(payload, dict) else type(payload))
print('coverage:', row.get('coverage'), '| events:', len(row.get('events') or []))
