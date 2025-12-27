# project/engines/world_engine/npc_system.py

import os
import json
import pygame

from core.entities.unit import Unit
from engines.world_engine.npc_controller import MovementController
from core.assets import asset_path
from core.config import TILE_SIZE


class NPCSystem:
    """
    Runtime NPCs (Units) + controllers + tasks + helpers de interacción.

    Se encarga de:
      - spawns runtime (Unit)
      - update/draw runtime NPCs
      - tasks walk_to + despawn + persistencia
      - detectar NPC interactuable frente al player (map npc o runtime unit)
      - aplicar outcomes de roles sobre runtime NPCs (move_to_marker, despawn, join_party)
    """

    def __init__(self, world_state, collision):
        self.ws = world_state
        self.collision = collision

        self.units: dict[str, Unit] = {}
        self.controllers: dict[str, MovementController] = {}
        self.tasks: dict[str, dict] = {}

    # -------------------------
    # Map NPC data helpers
    # -------------------------
    def filter_map_npcs(self, map_npcs: list[dict]) -> list[dict]:
        """Filtra NPCs del mapa según flags/persistencia."""
        out = []
        for n in map_npcs or []:
            npc_id = n.get("id", "")
            if npc_id and self.ws.game.game_state.get_flag(f"recruited:{npc_id}", False):
                continue
            out.append(n)
        return out

    def get_interactable_at_tile(self, tx: int, ty: int, map_npcs: list[dict]):
        """
        Devuelve:
          (npc_id, npc_data, source)
        donde source es "map" o "runtime".
        """
        # 1) map npc data
        for n in map_npcs or []:
            if n.get("tile_x") == tx and n.get("tile_y") == ty:
                return n.get("id"), n, "map"

        # 2) runtime units
        for uid, u in self.units.items():
            if getattr(u, "tile_x", None) == tx and getattr(u, "tile_y", None) == ty:
                return uid, None, "runtime"

        return None, None, None

    # -------------------------
    # Update / Render
    # -------------------------
    def update(self, dt: float) -> None:
        for ctrl in self.controllers.values():
            ctrl.update(dt)

        for u in self.units.values():
            u.update_sprite(dt)

        self._update_tasks(dt)

    def draw(self, screen, camera) -> None:
        for u in self.units.values():
            u.draw(screen, camera)

    # -------------------------
    # Spawning
    # -------------------------
    def spawn_unit(self, npc_id: str, tx: int, ty: int) -> None:
        if npc_id in self.units:
            return

        npc_json_path = asset_path("sprites", "npcs", npc_id, f"{npc_id}.json")
        walk_path = None
        if os.path.exists(npc_json_path):
            try:
                with open(npc_json_path, "r", encoding="utf-8") as f:
                    npc_data = json.load(f)
                walk_path = npc_data.get("visual", {}).get("walk")
            except Exception:
                walk_path = None

        u = Unit(tile_x=tx, tile_y=ty)

        if walk_path:
            try:
                u._walk_sheet = pygame.image.load(asset_path(*walk_path.split("/"))).convert_alpha()
            except Exception:
                pass

        self.units[npc_id] = u
        self.controllers[npc_id] = MovementController(u, self.collision)

    def spawn_intro_line(self, markers: dict, player_tile: tuple[int, int]) -> None:
        ids = ["selma_ironrose", "loren_valcrest", "iraen_falk", "elinya_brightwell"]
        line_markers = ["line_1", "line_2", "line_3", "line_4"]

        px, py = player_tile
        mx, my = markers.get("spawn_marian_intro", (px + 1, py))
        self.spawn_unit("marian_vell", mx, my)

        for npc_id, m in zip(ids, line_markers):
            tx, ty = markers.get(m, (px + 3, py))
            self.spawn_unit(npc_id, tx, ty)

    # -------------------------
    # Tasks
    # -------------------------
    def walk_to_marker_and_despawn(self, npc_id: str, marker_name: str, markers: dict) -> None:
        if npc_id not in self.units:
            return
        target = markers.get(marker_name)
        if not target:
            return
        self.tasks[npc_id] = {"type": "walk_to", "target": target, "despawn": True}

    def set_walk_to(self, npc_id: str, target_tile: tuple[int, int], despawn_on_arrival: bool) -> None:
        if npc_id not in self.units:
            return
        self.tasks[npc_id] = {"type": "walk_to", "target": target_tile, "despawn": bool(despawn_on_arrival)}

    def remove(self, npc_id: str) -> None:
        self.units.pop(npc_id, None)
        self.controllers.pop(npc_id, None)
        self.tasks.pop(npc_id, None)

    def _update_tasks(self, dt: float) -> None:
        for npc_id, task in list(self.tasks.items()):
            if task.get("type") != "walk_to":
                continue

            unit = self.units.get(npc_id)
            ctrl = self.controllers.get(npc_id)
            if not unit or not ctrl:
                self.tasks.pop(npc_id, None)
                continue

            tx, ty = task["target"]

            if unit.tile_x == tx and unit.tile_y == ty:
                if task.get("despawn"):
                    self.remove(npc_id)
                    self.ws.game.game_state.set_npc(npc_id, active=False, map=None, tile=None)
                continue

            if unit.is_moving:
                continue

            dx = 0
            dy = 0
            if unit.tile_x < tx:
                dx = 1
            elif unit.tile_x > tx:
                dx = -1
            elif unit.tile_y < ty:
                dy = 1
            elif unit.tile_y > ty:
                dy = -1

            if dx != 0 or dy != 0:
                ctrl.try_move(dx, dy)

    # -------------------------
    # Role outcomes (declarativo)
    # -------------------------
    def apply_role_outcomes(self, npc_id: str, cfg: dict, markers: dict) -> None:
        """
        Aplica outcomes de un rol sobre un runtime npc_id.

        cfg soporta:
          - move_to_marker: str
          - despawn_on_arrival: bool
          - effects: list[{type: "..."}]
        """
        if npc_id not in self.units:
            return

        marker_id = cfg.get("move_to_marker")
        if marker_id:
            target = markers.get(marker_id)
            if target:
                despawn = bool(cfg.get("despawn_on_arrival", False))
                self.set_walk_to(npc_id, target, despawn)

        for eff in cfg.get("effects", []) or []:
            if eff.get("type") == "join_party":
                self.ws.game.game_state.add_party_member(
                    npc_id,
                    name=npc_id.replace("_", " ").title()
                )
                self.remove(npc_id)
                self.ws.game.game_state.set_npc(npc_id, active=False, map=None, tile=None)

    def spawn_runtime_unit(self, runtime_id: str, sprite_id: str, tx: int, ty: int) -> None:
        """Spawnea un Unit en runtime usando el sprite/JSON de `sprite_id`, pero registrándolo con `runtime_id`.

        Esto permite tener guardaespaldas siguiendo al jugador sin pisar NPCs del mapa.
        """
        runtime_id = str(runtime_id)
        sprite_id = str(sprite_id)

        if runtime_id in self.units:
            return

        npc_json_path = asset_path("sprites", "npcs", sprite_id, f"{sprite_id}.json")
        walk_path = None
        if os.path.exists(npc_json_path):
            try:
                with open(npc_json_path, "r", encoding="utf-8") as f:
                    npc_data = json.load(f)
                walk_path = npc_data.get("visual", {}).get("walk")
            except Exception:
                walk_path = None

        u = Unit(tile_x=tx, tile_y=ty)

        if walk_path:
            try:
                u._walk_sheet = pygame.image.load(asset_path(*walk_path.split("/"))).convert_alpha()
            except Exception:
                pass

        self.units[runtime_id] = u
        self.controllers[runtime_id] = MovementController(u, self.collision)

    def despawn_unit(self, runtime_id: str) -> None:
        """Elimina un Unit previamente spawneado en runtime."""
        runtime_id = str(runtime_id)
        if runtime_id in self.units:
            del self.units[runtime_id]
        if runtime_id in self.controllers:
            del self.controllers[runtime_id]