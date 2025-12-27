# project/engines/world_engine/world_state.py

from engines.world_engine.map_loader import TiledMap
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.dialogue_system import DialogueSystem
from engines.world_engine.npc_system import NPCSystem
from engines.world_engine.world_interaction_system import WorldInteractionSystem
from engines.world_engine.map_data import MapData
from engines.world_engine.map_transition_system import MapTransitionSystem
from engines.world_engine.npc_controller import MovementController
from engines.world_engine.event_runner import EventRunner

from core.entities.unit import Unit
from core.config import TILE_SIZE, SCREEN_WIDTH, SCREEN_HEIGHT
from render.world.camera import Camera
from core.assets import asset_path

import pygame
import json


class WorldState:
    def __init__(self, game, map_rel_path=("maps", "world", "town_01.json"), spawn_tile=None):
        self.game = game

        if isinstance(map_rel_path, (tuple, list)):
            json_path = asset_path(*map_rel_path)
        else:
            json_path = asset_path(map_rel_path)

        self.map = TiledMap(json_path=json_path, assets_root=asset_path(""))

        # Map data/cache helpers (✅ fuera de WorldState)
        self.map_data = MapData(self.map.json_path, tile_size=TILE_SIZE)

        self.markers = self.map_data.load_markers()
        self.doors = self.map_data.get_objectgroup("puertas")
        self.triggers = self.map_data.get_objectgroup("triggers")

        # input lock global (eventos/diálogo)
        self.input_locked = False

        # collision + camera
        self.collision = CollisionSystem(
            self.map,
            get_npc_units=lambda: self.npc_system.units if hasattr(self, "npc_system") else {}
        )
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)

        # spawn player
        if spawn_tile is not None:
            px, py = spawn_tile
            self.game.game_state.set_player_tile(px, py)
        else:
            px, py = self.game.game_state.get_player_tile()

        self.player = Unit(tile_x=px, tile_y=py)
        self.controller = MovementController(self.player, self.collision)

        # input movimiento
        self.move_dir = None
        self.move_timer = 0

        # systems
        self.dialogue = DialogueSystem(self)
        self.npc_system = NPCSystem(self, self.collision)
        self.interactions = WorldInteractionSystem(self, doors=self.doors, triggers=self.triggers)
        self.transitions = MapTransitionSystem(self)

        # filtrar NPCs del mapa (data)
        self.map.npcs = self.npc_system.filter_map_npcs(getattr(self.map, "npcs", []) or [])

        # eventos
        self.event_runner = EventRunner(self)

        # roles/assignments (UI)
        self._event_assignments = {}
        self._event_apply_role_outcomes_step = None

        self._assign_active = False
        self._assign_step = None
        self._assign_npcs = []
        self._assign_roles = []
        self._assign_remaining = {}
        self._assign_idx = 0
        self._assignments_local = {}

        # autoplay intro
        if not self.game.game_state.get_flag("intro_done", False):
            self.start_intro_event()

    # --------------------------------
    # Compat: usado por WorldInteractionSystem y MapTransitionSystem
    # --------------------------------
    def _props_to_dict(self, obj) -> dict:
        return self.map_data.props_to_dict(obj)

    # -------------------------------
    # Input
    # -------------------------------
    def handle_event(self, event):
        if self.dialogue.handle_event(event):
            return

        if self.input_locked:
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_w:
                self.move_dir = (0, -1)
                self.player.set_facing(0, -1)
            elif event.key == pygame.K_s:
                self.move_dir = (0, 1)
                self.player.set_facing(0, 1)
            elif event.key == pygame.K_a:
                self.move_dir = (-1, 0)
                self.player.set_facing(-1, 0)
            elif event.key == pygame.K_d:
                self.move_dir = (1, 0)
                self.player.set_facing(1, 0)

            if event.key in (pygame.K_RETURN, pygame.K_p):
                from engines.world_engine.pause_state import PauseState
                self.game.change_state(PauseState(self.game, self))
                return

            if event.key == pygame.K_e:
                self.try_interact()

            if self.move_dir and not self.player.is_moving:
                self.controller.try_move(*self.move_dir)
                self.move_timer = 0

        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d):
                self.move_dir = None
                self.move_timer = 0

    # -------------------------------
    # Update
    # -------------------------------
    def update(self, dt):
        # player
        self.controller.update(dt)
        self.player.update_sprite(dt)
        self.camera.follow(self.player.pixel_x, self.player.pixel_y)

        if (not self.input_locked) and self.move_dir and not self.player.is_moving:
            self.controller.try_move(*self.move_dir)
        else:
            self.move_timer = 0

        # NPCs runtime
        self.npc_system.update(dt)

        # puertas/triggers
        self.interactions.update(dt)

        # guardar tile
        self.game.game_state.set_player_tile(self.player.tile_x, self.player.tile_y)

        # eventos
        self.event_runner.update(dt)

    # -------------------------------
    # Interacción (hablar)
    # -------------------------------
    def try_interact(self):
        dx, dy = self.player.facing
        tx = self.player.tile_x + dx
        ty = self.player.tile_y + dy

        npc_id, npc_data, source = self.npc_system.get_interactable_at_tile(
            tx, ty, getattr(self.map, "npcs", []) or []
        )
        if not npc_id:
            return

        if self.event_runner.active and self.event_runner.on_player_interact(npc_id):
            return

        if source == "map" and npc_data:
            self.open_dialogue(
                npc_data.get("name", ""),
                npc_data.get("dialogue", []),
                options=npc_data.get("options", []),
                context={"npc_id": npc_id, "npc": npc_data}
            )
        else:
            self.open_dialogue(
                npc_id.replace("_", " ").title(),
                ["..."],
                options=None,
                context={"npc_id": npc_id}
            )

    def open_dialogue(self, speaker: str, lines, options=None, context=None):
        self.dialogue.open(speaker, lines, options=options, context=context or {})

    # llamada desde DialogueSystem
    def _dialogue_action_recruit(self, unit_id: str, speaker: str, npc_id: str | None):
        if any(u.get("id") == unit_id for u in self.game.game_state.party):
            self.open_dialogue(
                speaker,
                ["Ya forma parte de tu ejército."],
                options=[{"text": "Salir", "action": "close"}],
                context={}
            )
            return

        self.game.game_state.add_party_member(
            unit_id=unit_id,
            name=speaker,
            extra={"level": 1, "class": "soldier", "hp": 18, "atk": 5, "def": 3}
        )
        self.game.game_state.set_flag(f"recruited:{unit_id}", True)

        if npc_id:
            self.map.npcs = [n for n in getattr(self.map, "npcs", []) if n.get("id") != npc_id]

        self.open_dialogue(
            speaker,
            [f"{speaker} se ha unido a tu ejército."],
            options=[{"text": "Salir", "action": "close"}],
            context={}
        )

    # -------------------------------
    # Assign Roles UI
    # -------------------------------
    def _start_assign_roles(self, step: dict) -> None:
        self._assign_step = step
        self._assign_active = True
        self._assign_npcs = list(step.get("npcs", []))
        self._assign_roles = list(step.get("roles", []))
        constraints = step.get("constraints", {}) or {}

        self._assign_remaining = {r: int(constraints.get(r, 1)) for r in self._assign_roles}

        already = dict(getattr(self, "_event_assignments", {}) or {})
        for _npc_id, role in already.items():
            if role in self._assign_remaining:
                self._assign_remaining[role] -= 1

        for r in list(self._assign_remaining.keys()):
            if self._assign_remaining[r] < 0:
                self._assign_remaining[r] = 0

        self._assign_idx = 0
        self._assignments_local = {}
        self._show_assign_prompt()

    def _assign_current_npc(self, role: str) -> None:
        if not self._assign_active:
            return
        if self._assign_idx >= len(self._assign_npcs):
            return

        npc_id = self._assign_npcs[self._assign_idx]
        self._assignments_local[npc_id] = role
        self._event_assignments[npc_id] = role

        self._apply_role_outcomes_for_npc(npc_id)

        if role in self._assign_remaining and self._assign_remaining[role] > 0:
            self._assign_remaining[role] -= 1

        self._assign_idx += 1
        self._show_assign_prompt()

    def _show_assign_prompt(self) -> None:
        if self._assign_idx >= len(self._assign_npcs):
            self._event_assignments.update(self._assignments_local)
            self._assign_active = False
            if self.dialogue.active:
                self.dialogue.close()
            if self.event_runner.active:
                self.event_runner.on_assign_roles_done(self._event_assignments)
            return

        npc_id = self._assign_npcs[self._assign_idx]

        remaining_bits = [f"{r}: {max(0, int(self._assign_remaining.get(r, 0)))}" for r in self._assign_roles]
        remaining_txt = ", ".join(remaining_bits)

        prompt_lines = [
            f"Asigná un rol para: {npc_id}",
            f"Pendientes -> {remaining_txt}"
        ]

        options = [{"text": r, "action": f"assign_role:{r}"} for r in self._assign_roles if self._assign_remaining.get(r, 0) > 0]
        if not options:
            options = [{"text": r, "action": f"assign_role:{r}"} for r in self._assign_roles]

        self.open_dialogue(
            "Asignación de roles",
            prompt_lines,
            options=options,
            context={"event": "assign_roles"}
        )

    # -------------------------------
    # Intro / eventos
    # -------------------------------
    def start_intro_event(self):
        if self.game.game_state.get_flag("intro_done", False):
            return

        self.input_locked = True

        if "spawn_player_start" in self.markers:
            px, py = self.markers["spawn_player_start"]
            self.player.tile_x = px
            self.player.tile_y = py
            self.player.pixel_x = px * TILE_SIZE
            self.player.pixel_y = py * TILE_SIZE
            self.game.game_state.set_player_tile(px, py)

        self.npc_system.spawn_intro_line(self.markers, (self.player.tile_x, self.player.tile_y))

        event_path = asset_path("data", "events", "intro_assign_roles.json")
        with open(event_path, "r", encoding="utf-8") as f:
            event_json = json.load(f)

        self.run_event(event_json)

    def run_event(self, event_json):
        self.event_runner.start(event_json)

    # -------------------------------
    # Role outcomes (delegado a NPCSystem)
    # -------------------------------
    def _apply_role_outcomes_for_npc(self, npc_id: str) -> None:
        step = getattr(self, "_event_apply_role_outcomes_step", None)
        if not step:
            return

        role = self._event_assignments.get(npc_id)
        if not role:
            return

        roles_cfg = step.get("roles", {}) or {}
        cfg = roles_cfg.get(role, {}) or {}
        self.npc_system.apply_role_outcomes(npc_id, cfg, self.markers)

    # -------------------------------
    # Cambiar mapa (delegado a TransitionSystem)
    # -------------------------------
    def cambiar_mapa(self, destino, puerta_entrada=None):
        self.transitions.change_map(destino, puerta_entrada=puerta_entrada)

    # -------------------------------
    # Render
    # -------------------------------
    def render(self, screen):
        screen.fill((0, 0, 0))

        self.map.draw(screen, self.camera, layer_order=("mapa",))
        self.player.draw(screen, self.camera)

        self.npc_system.draw(screen, self.camera)

        # map NPC placeholders (si los seguís usando)
        for n in getattr(self.map, "npcs", []) or []:
            nx = n["tile_x"] * TILE_SIZE - self.camera.x
            ny = n["tile_y"] * TILE_SIZE - self.camera.y
            pygame.draw.rect(screen, (60, 80, 220), (nx, ny, TILE_SIZE, TILE_SIZE))

        self.dialogue.render(screen)
