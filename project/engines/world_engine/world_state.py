# project/engines/world_engine/world_state.py

from engines.world_engine.map_loader import TiledMap
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.dialogue_system import DialogueSystem
from engines.world_engine.npc_system import NPCSystem
from engines.world_engine.npc_controller import MovementController

from core.entities.unit import Unit
import pygame
from core.config import TILE_SIZE, SCREEN_WIDTH, SCREEN_HEIGHT
from render.world.camera import Camera
from core.assets import asset_path
import json

from engines.world_engine.event_runner import EventRunner


class WorldState:
    def __init__(self, game, map_rel_path=("maps", "world", "town_01.json"), spawn_tile=None):
        self.game = game

        if isinstance(map_rel_path, (tuple, list)):
            json_path = asset_path(*map_rel_path)
        else:
            json_path = asset_path(map_rel_path)

        self.map = TiledMap(json_path=json_path, assets_root=asset_path(""))

        # caches
        self._map_json_cache = None
        self._objectgroups_cache = {}

        self.markers = self._load_markers()
        self.doors = self._get_objectgroup("puertas")
        self.triggers = self._get_objectgroup("triggers")

        self._trigger_fired = set()

        # puertas anti-loop
        self._door_was_inside = False
        self._door_cooldown = 0.0
        self._door_lock_until_exit = False
        self._door_lock_rect = None

        self.input_locked = False

        # collision + camera
        self.collision = CollisionSystem(self.map, get_npc_units=lambda: self.npc_system.units if hasattr(self, "npc_system") else {})
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)

        # spawn player
        if spawn_tile is not None:
            px, py = spawn_tile
            self.game.game_state.set_player_tile(px, py)
        else:
            px, py = self.game.game_state.get_player_tile()

        self.player = Unit(tile_x=px, tile_y=py)
        self.controller = MovementController(self.player, self.collision)

        self.move_dir = None
        self.move_timer = 0

        # systems
        self.dialogue = DialogueSystem(self)
        self.npc_system = NPCSystem(self, self.collision)

        # filtrar NPCs “data” del mapa usando NPCSystem (✅ WorldState ya no sabe flags de recruited)
        self.map.npcs = self.npc_system.filter_map_npcs(getattr(self.map, "npcs", []) or [])

        # events
        self.event_runner = EventRunner(self)

        # roles/assignments
        self._event_assignments = {}
        self._event_apply_role_outcomes_step = None

        self._assign_active = False
        self._assign_step = None
        self._assign_npcs = []
        self._assign_roles = []
        self._assign_remaining = {}
        self._assign_idx = 0
        self._assignments_local = {}

        if not self.game.game_state.get_flag("intro_done", False):
            self.start_intro_event()

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

        if self._door_cooldown > 0:
            self._door_cooldown -= dt
            if self._door_cooldown < 0:
                self._door_cooldown = 0

        # anti-rebote spawn puerta
        skip_doors = False
        if self._door_lock_until_exit and self._door_lock_rect:
            player_rect = pygame.Rect(self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)
            if player_rect.colliderect(self._door_lock_rect):
                self._door_was_inside = True
                skip_doors = True
            else:
                self._door_lock_until_exit = False
                self._door_lock_rect = None
                self._door_was_inside = False

        # puertas
        if (not skip_doors) and (not self.input_locked) and (not self.player.is_moving) and self._door_cooldown == 0:
            player_rect = pygame.Rect(self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)
            inside_any = False
            door_hit = None

            for obj in self.doors:
                door_rect = pygame.Rect(obj["x"], obj["y"], obj["width"], obj["height"])
                if player_rect.colliderect(door_rect):
                    inside_any = True
                    door_hit = obj
                    break

            if inside_any and not self._door_was_inside and door_hit:
                props = self._props_to_dict(door_hit)
                destino = props.get("map") or props.get("target_map")
                if destino:
                    self.cambiar_mapa(destino, puerta_entrada=door_hit)
                    self._door_cooldown = 0.25
                    return

            self._door_was_inside = inside_any

        if not self.input_locked:
            self._check_triggers()

        self.game.game_state.set_player_tile(self.player.tile_x, self.player.tile_y)

        if getattr(self, "event_runner", None):
            self.event_runner.update(dt)

    # -------------------------------
    # Interacción
    # -------------------------------
    def try_interact(self):
        dx, dy = self.player.facing
        tx = self.player.tile_x + dx
        ty = self.player.tile_y + dy

        npc_id, npc_data, source = self.npc_system.get_interactable_at_tile(tx, ty, getattr(self.map, "npcs", []) or [])
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
    # Triggers
    # -------------------------------
    def _check_triggers(self):
        player_rect = pygame.Rect(self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)
        for obj in self.triggers:
            obj_id = obj.get("id") or obj.get("name") or f'{obj.get("x")}:{obj.get("y")}'
            if obj_id in self._trigger_fired:
                continue
            rect = pygame.Rect(obj["x"], obj["y"], obj["width"], obj["height"])
            if not player_rect.colliderect(rect):
                continue
            props = self._props_to_dict(obj)
            event_id = props.get("event_id")
            once = bool(props.get("once", True))
            if event_id:
                pass
            if once:
                self._trigger_fired.add(obj_id)

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
    # Role outcomes (delegado)
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
    # Map switch / JSON helpers / Render (igual que antes)
    # -------------------------------
    def cambiar_mapa(self, destino, puerta_entrada=None):
        destino_path = asset_path(destino)

        with open(destino_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        puertas_destino = []
        for layer in data.get("layers", []):
            if layer.get("type") == "objectgroup" and layer.get("name") == "puertas":
                puertas_destino = layer.get("objects", [])
                break

        if not puertas_destino:
            nuevo = WorldState(self.game, map_rel_path=destino, spawn_tile=(0, 0))
            nuevo._door_cooldown = 0.4
            self.game.change_state(nuevo)
            return

        puerta_destino = None
        tx = ty = None

        if puerta_entrada:
            props_in = self._props_to_dict(puerta_entrada)
            if "spawn_x" in props_in and "spawn_y" in props_in:
                tx = int(props_in["spawn_x"])
                ty = int(props_in["spawn_y"])

                spawn_door_id = props_in.get("spawn_door_id")
                if spawn_door_id:
                    for d in puertas_destino:
                        if self._props_to_dict(d).get("id") == spawn_door_id:
                            puerta_destino = d
                            break

        if tx is None or ty is None:
            if puerta_entrada:
                origen_path = self.map.json_path.replace("\\", "/").split("assets/")[-1]
                for pd in puertas_destino:
                    props_pd = self._props_to_dict(pd)
                    map_prop = (props_pd.get("map") or "").replace("\\", "/")
                    if map_prop.endswith(origen_path):
                        puerta_destino = pd
                        break

            if puerta_destino is None:
                puerta_destino = puertas_destino[0]

            tx = int((puerta_destino["x"] + puerta_destino["width"] / 2) // TILE_SIZE)
            ty = int((puerta_destino["y"] + puerta_destino["height"] / 2) // TILE_SIZE)

        nuevo = WorldState(self.game, map_rel_path=destino, spawn_tile=(tx, ty))

        if puerta_destino is not None:
            nuevo._door_lock_until_exit = True
            nuevo._door_lock_rect = pygame.Rect(
                puerta_destino["x"], puerta_destino["y"],
                puerta_destino["width"], puerta_destino["height"]
            )
            nuevo._door_cooldown = 0.15
            nuevo._door_was_inside = True
        else:
            nuevo._door_cooldown = 0.4
            nuevo._door_was_inside = True

        self.game.change_state(nuevo)

    def _load_map_json(self):
        if self._map_json_cache is None:
            with open(self.map.json_path, "r", encoding="utf-8") as f:
                self._map_json_cache = json.load(f)
        return self._map_json_cache

    def _get_objectgroup(self, layer_name: str):
        if layer_name in self._objectgroups_cache:
            return self._objectgroups_cache[layer_name]

        data = self._load_map_json()
        for layer in data.get("layers", []):
            if layer.get("type") == "objectgroup" and layer.get("name") == layer_name:
                objs = layer.get("objects", [])
                self._objectgroups_cache[layer_name] = objs
                return objs

        self._objectgroups_cache[layer_name] = []
        return []

    def _props_to_dict(self, obj) -> dict:
        out = {}
        for p in obj.get("properties", []) or []:
            out[p.get("name")] = p.get("value")
        return out

    def _load_markers(self) -> dict:
        markers = {}
        for obj in self._get_objectgroup("markers"):
            name = None
            for prop in obj.get("properties", []):
                if prop.get("name") == "id":
                    name = prop.get("value")
                    break
            if not name:
                continue
            tx = int(obj["x"] // TILE_SIZE)
            ty = int(obj["y"] // TILE_SIZE)
            markers[name] = (tx, ty)
        return markers

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
