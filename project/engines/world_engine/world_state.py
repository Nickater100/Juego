# project/engines/world_engine/world_state.py

from engines.world_engine.map_loader import TiledMap
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.dialogue_system import DialogueSystem
from engines.world_engine.npc_system import NPCSystem
from engines.world_engine.world_interaction_system import WorldInteractionSystem
from engines.world_engine.map_data import MapData
from engines.world_engine.map_transition_system import MapTransitionSystem
from engines.world_engine.assign_roles_system import AssignRolesSystem
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

        # Map data/cache helpers
        self.map_data = MapData(self.map.json_path, tile_size=TILE_SIZE)

        self.markers = self.map_data.load_markers()
        self.doors = self.map_data.get_objectgroup("puertas")
        self.triggers = self.map_data.get_objectgroup("triggers")

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
        self.assign_roles = AssignRolesSystem(self)

        # filtrar NPCs del mapa (data)
        self.map.npcs = self.npc_system.filter_map_npcs(getattr(self.map, "npcs", []) or [])

        # eventos
        self.event_runner = EventRunner(self)

        # assignments / outcomes step (el runner lo setea)
        self._event_assignments = {}
        self._event_apply_role_outcomes_step = None

        if not self.game.game_state.get_flag("intro_done", False):
            self.start_intro_event()

    # --------------------------------
    # Compat: usado por Interaction/Transition systems
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
        self.controller.update(dt)
        self.player.update_sprite(dt)
        self.camera.follow(self.player.pixel_x, self.player.pixel_y)

        if (not self.input_locked) and self.move_dir and not self.player.is_moving:
            self.controller.try_move(*self.move_dir)
        else:
            self.move_timer = 0

        self.npc_system.update(dt)
        self.interactions.update(dt)

        self.game.game_state.set_player_tile(self.player.tile_x, self.player.tile_y)

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
        """Recluta una unidad y persiste sus stats.

        - Si existe un JSON de NPC en assets/sprites/npcs/<id>/<id>.json, toma stats desde:
            combat_profile.base_stats
        y los normaliza para el menú de Ejército (hp/atk/def/level/clase).
        - Guarda esos stats dentro de party_unit["extra"] para que el pause menu los lea.
        """
        # Evitar duplicados
        if any(u.get("id") == unit_id for u in self.game.game_state.party):
            self.open_dialogue(
                speaker,
                ["Ya forma parte de tu ejército."],
                options=[{"text": "Salir", "action": "close"}],
                context={}
            )
            return

        # Intentar obtener stats desde el JSON del NPC (sprites/npcs)
        npc_key = str(npc_id or unit_id)
        npc_stats: dict = {}
        try:
            from core.assets import asset_path  # import local para evitar ciclos en import time
            import os as _os
            import json as _json

            npc_json_path = asset_path("sprites", "npcs", npc_key, f"{npc_key}.json")
            if _os.path.exists(npc_json_path):
                with open(npc_json_path, "r", encoding="utf-8") as f:
                    npc_data = _json.load(f) or {}

                combat_profile = npc_data.get("combat_profile") or {}
                base_stats = combat_profile.get("base_stats") or {}

                # Normalización para UI (Ejército espera hp/atk/def)
                level = base_stats.get("level", 1)
                hp = base_stats.get("hp", base_stats.get("HP", 18))

                # En tus JSON: 'str' representa el ataque base
                atk = base_stats.get("atk", base_stats.get("str", base_stats.get("strength", 5)))

                # 'def' puede venir como 'def' o 'defense'
                deff = base_stats.get("def", base_stats.get("defense", 3))

                # Clase (si no existe en JSON, default razonable)
                unit_class = combat_profile.get("class") or combat_profile.get("unit_class") or "soldier"

                # Guardar también el bloque completo para futuras pantallas
                npc_stats = {
                    "level": level,
                    "class": unit_class,
                    "hp": hp,
                    "atk": atk,
                    "def": deff,
                    # stats secundarios (si existen)
                    "dex": base_stats.get("dex"),
                    "spd": base_stats.get("spd"),
                    "res": base_stats.get("res"),
                    "cha": base_stats.get("cha"),
                    # conservar para depuración / futuros sistemas
                    "stats": dict(base_stats),
                    "source": {"npc_json": npc_json_path},
                }
        except Exception:
            npc_stats = {}

        # Fallback por si no hay JSON o vino incompleto
        if not npc_stats:
            npc_stats = {
                "level": 1,
                "class": "soldier",
                "hp": 18,
                "atk": 5,
                "def": 3,
            }

        # Persistir en party con el esquema que espera pause_state: party_unit["extra"]
        self.game.game_state.add_party_member(
            unit_id=unit_id,
            name=speaker,
            extra={"extra": npc_stats}
        )
        self.game.game_state.set_flag(f"recruited:{unit_id}", True)

        # Remover el NPC del mapa (si corresponde)
        if npc_id:
            self.map.npcs = [n for n in getattr(self.map, "npcs", []) if n.get("id") != npc_id]

        self.open_dialogue(
            speaker,
            [f"{speaker} se ha unido a tu ejército."],
            options=[{"text": "Salir", "action": "close"}],
            context={}
        )

    # -------------------------------
    # Assign Roles hooks (llamados por EventRunner + DialogueSystem)
    # -------------------------------
    def start_assign_roles(self, step: dict) -> None:
        self.assign_roles.start(step)

    def assign_role(self, role: str) -> None:
        self.assign_roles.assign(role)

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
    # Cambiar mapa (delegado)
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

        for n in getattr(self.map, "npcs", []) or []:
            nx = n["tile_x"] * TILE_SIZE - self.camera.x
            ny = n["tile_y"] * TILE_SIZE - self.camera.y
            pygame.draw.rect(screen, (60, 80, 220), (nx, ny, TILE_SIZE, TILE_SIZE))

        self.dialogue.render(screen)
