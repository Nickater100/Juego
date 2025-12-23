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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "current_map_id": self.current_map_id,
            "player_tile": [self.player_tile[0], self.player_tile[1]],
            "story_flags": dict(self.story_flags),
            "party": list(self.party),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameState":
        gs = cls()
        gs.current_map_id = data.get("current_map_id", "town_01")

        pt = data.get("player_tile", [5, 5])
        if isinstance(pt, (list, tuple)) and len(pt) == 2:
            gs.player_tile = (int(pt[0]), int(pt[1]))
        else:
            gs.player_tile = (5, 5)

        gs.story_flags = dict(data.get("story_flags", {}))
        gs.party = list(data.get("party", []))
        return gs

