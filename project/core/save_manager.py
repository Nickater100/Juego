import json
from pathlib import Path
from typing import Optional
from core.game_state import GameState


def _project_root() -> Path:
    # core/save_manager.py -> core -> project root
    return Path(__file__).resolve().parents[1]


def save_path(slot: int = 1) -> Path:
    root = _project_root()
    saves_dir = root / "saves"
    saves_dir.mkdir(parents=True, exist_ok=True)
    return saves_dir / f"save_{slot:02d}.json"


def save_game(game_state: GameState, slot: int = 1) -> Path:
    path = save_path(slot)
    data = game_state.to_dict()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_game(slot: int = 1) -> Optional[GameState]:
    path = save_path(slot)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return GameState.from_dict(data)
