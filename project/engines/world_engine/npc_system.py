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
    Runtime NPCs (Units) + controllers + tasks (walk_to/despawn).

    Mantiene:
      - units: dict[npc_id] -> Unit
      - controllers: dict[npc_id] -> MovementController
      - tasks: dict[npc_id] -> {"type":"walk_to","target":(tx,ty),"despawn":bool}
    """

    def __init__(self, world_state, collision):
        self.ws = world_state
        self.collision = collision

        self.units: dict[str, Unit] = {}
        self.controllers: dict[str, MovementController] = {}
        self.tasks: dict[str, dict] = {}

    # -------------------------
    # Update / Render
    # -------------------------
    def update(self, dt: float) -> None:
        # controllers
        for ctrl in self.controllers.values():
            ctrl.update(dt)

        # sprites
        for u in self.units.values():
            u.update_sprite(dt)

        # tasks
        self._update_tasks(dt)

    def draw(self, screen, camera) -> None:
        for u in self.units.values():
            u.draw(screen, camera)

    # -------------------------
    # Spawning
    # -------------------------
    def spawn_unit(self, npc_id: str, tx: int, ty: int) -> None:
        """
        Spawnea un Unit para el NPC (runtime) y le setea sprite personalizado si existe.
        """
        if npc_id in self.units:
            return

        # Cargar sprite personalizado si existe
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
        u.pixel_x = tx * TILE_SIZE
        u.pixel_y = ty * TILE_SIZE

        if walk_path:
            try:
                u._walk_sheet = pygame.image.load(asset_path(*walk_path.split("/"))).convert_alpha()
            except Exception:
                pass

        self.units[npc_id] = u
        self.controllers[npc_id] = MovementController(u, self.collision)

    def spawn_intro_line(self, markers: dict, player_tile: tuple[int, int]) -> None:
        """
        Spawnea Marian + 4 NPCs del intro en línea usando markers.
        Mantiene exactamente la lógica que venías usando.
        """
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

            # Llegó
            if unit.tile_x == tx and unit.tile_y == ty:
                if task.get("despawn"):
                    self.remove(npc_id)

                    # Persistencia (igual que antes)
                    self.ws.game.game_state.set_npc(
                        npc_id,
                        active=False,
                        map=None,
                        tile=None
                    )
                continue

            if unit.is_moving:
                continue

            # Step simple hacia el target (igual que antes)
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
