from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple


@dataclass
class GameState:
    # Mundo
    current_map_id: str = "town_01"
    player_tile: Tuple[int, int] = (5, 5)

    # Progreso / historia
    story_flags: Dict[str, bool] = field(default_factory=dict)

    # Party (reclutados)
    # Por ahora guardamos "ids" o dicts simples; más adelante lo hacemos data-driven con JSON.
    party: List[Dict[str, Any]] = field(default_factory=list)

    def set_player_tile(self, x: int, y: int) -> None:
        self.player_tile = (x, y)

    def get_player_tile(self) -> Tuple[int, int]:
        return self.player_tile

    def set_flag(self, key: str, value: bool = True) -> None:
        self.story_flags[key] = value

    def get_flag(self, key: str, default: bool = False) -> bool:
        return self.story_flags.get(key, default)

    def add_party_member(self, unit_id: str, name: str = "", extra: Dict[str, Any] | None = None) -> None:
        payload = {"id": unit_id, "name": name}
        if extra:
            payload.update(extra)
        self.party.append(payload)
