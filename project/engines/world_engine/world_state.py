# project/engines/world_engine/world_state.py

from engines.world_engine.map_loader import TiledMap
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.npc_controller import MovementController
from engines.world_engine.dialogue_system import DialogueSystem
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

        # input lock global (runner/diálogo)
        self.input_locked = False

        # NPC runtime
        self.npc_units = {}
        self.npc_controllers = {}
        self.npc_tasks = {}

        # filtrar NPC reclutados
        filtered = []
        for n in getattr(self.map, "npcs", []) or []:
            npc_id = n.get("id", "")
            if npc_id and self.game.game_state.get_flag(f"recruited:{npc_id}", False):
                continue
            filtered.append(n)
        self.map.npcs = filtered

        self.collision = CollisionSystem(self.map, get_npc_units=lambda: self.npc_units)
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

        # Dialogue system (✅ todo el UI/input/render del diálogo vive acá)
        self.dialogue = DialogueSystem(self)

        # Event runner
        self.event_runner = EventRunner(self)

        # estado assignments / roles
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

    # -------------------------------
    # Input
    # -------------------------------
    def handle_event(self, event):
        # diálogo consume input
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

        for ctrl in self.npc_controllers.values():
            ctrl.update(dt)
        for u in self.npc_units.values():
            u.update_sprite(dt)

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

        self._update_npc_tasks(dt)

        if getattr(self, "event_runner", None):
            self.event_runner.update(dt)

    # -------------------------------
    # Interacción
    # -------------------------------
    def try_interact(self):
        dx, dy = self.player.facing
        tx = self.player.tile_x + dx
        ty = self.player.tile_y + dy

        npc_id = None
        npc_data = None

        for n in getattr(self.map, "npcs", []) or []:
            if n.get("tile_x") == tx and n.get("tile_y") == ty:
                npc_data = n
                npc_id = n.get("id")
                break

        if npc_id is None:
            for uid, u in getattr(self, "npc_units", {}).items():
                if getattr(u, "tile_x", None) == tx and getattr(u, "tile_y", None) == ty:
                    npc_id = uid
                    break

        if not npc_id:
            return

        if getattr(self, "event_runner", None) and self.event_runner.active:
            if self.event_runner.on_player_interact(npc_id):
                return

        # diálogo normal
        if npc_data:
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

    # --- acción recruit centralizada (llamada desde DialogueSystem) ---
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
    # Triggers / tasks
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

    def _update_npc_tasks(self, dt):
        for npc_id, task in list(self.npc_tasks.items()):
            if task.get("type") != "walk_to":
                continue

            unit = self.npc_units.get(npc_id)
            ctrl = self.npc_controllers.get(npc_id)
            if not unit or not ctrl:
                self.npc_tasks.pop(npc_id, None)
                continue

            tx, ty = task["target"]

            if unit.tile_x == tx and unit.tile_y == ty:
                if task.get("despawn"):
                    self.npc_units.pop(npc_id, None)
                    self.npc_controllers.pop(npc_id, None)
                    self.npc_tasks.pop(npc_id, None)
                    self.game.game_state.set_npc(npc_id, active=False, map=None, tile=None)
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
            # cerrar diálogo si estaba abierto
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

        self.spawn_intro_npcs_in_line()

        event_path = asset_path("data", "events", "intro_assign_roles.json")
        with open(event_path, "r", encoding="utf-8") as f:
            event_json = json.load(f)

        self.run_event(event_json)

    def run_event(self, event_json):
        self.event_runner.start(event_json)

    # -------------------------------
    # Map switch
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

    # -------------------------------
    # NPC spawn intro
    # -------------------------------
    def spawn_intro_npcs_in_line(self):
        ids = ["selma_ironrose", "loren_valcrest", "iraen_falk", "elinya_brightwell"]
        line_markers = ["line_1", "line_2", "line_3", "line_4"]

        mx, my = self.markers.get("spawn_marian_intro", (self.player.tile_x + 1, self.player.tile_y))
        if "marian_vell" not in self.npc_units:
            self._spawn_npc_unit("marian_vell", mx, my)

        for npc_id, m in zip(ids, line_markers):
            tx, ty = self.markers.get(m, (self.player.tile_x + 3, self.player.tile_y))
            if npc_id not in self.npc_units:
                self._spawn_npc_unit(npc_id, tx, ty)

    def _spawn_npc_unit(self, npc_id: str, tx: int, ty: int):
        import os
        npc_json_path = asset_path("sprites", "npcs", npc_id, f"{npc_id}.json")
        walk_path = None
        if os.path.exists(npc_json_path):
            with open(npc_json_path, "r", encoding="utf-8") as f:
                npc_data = json.load(f)
            walk_path = npc_data.get("visual", {}).get("walk")

        u = Unit(tile_x=tx, tile_y=ty)
        u.pixel_x = tx * TILE_SIZE
        u.pixel_y = ty * TILE_SIZE

        if walk_path:
            try:
                u._walk_sheet = pygame.image.load(asset_path(*walk_path.split("/"))).convert_alpha()
            except Exception:
                pass

        self.npc_units[npc_id] = u
        self.npc_controllers[npc_id] = MovementController(u, self.collision)

    # -------------------------------
    # JSON helpers
    # -------------------------------
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

    # -------------------------------
    # Role outcomes
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

        marker_id = cfg.get("move_to_marker")
        if marker_id:
            target = getattr(self, "markers", {}).get(marker_id)
            if target:
                despawn = bool(cfg.get("despawn_on_arrival", False))
                self.npc_tasks[npc_id] = {"type": "walk_to", "target": target, "despawn": despawn}

        effects = cfg.get("effects", []) or []
        for eff in effects:
            if eff.get("type") == "join_party":
                self.game.game_state.add_party_member(
                    npc_id,
                    name=npc_id.replace("_", " ").title()
                )
                self.npc_units.pop(npc_id, None)
                self.npc_controllers.pop(npc_id, None)
                self.npc_tasks.pop(npc_id, None)
                self.game.game_state.set_npc(npc_id, active=False, map=None, tile=None)

    # -------------------------------
    # Render
    # -------------------------------
    def render(self, screen):
        screen.fill((0, 0, 0))

        self.map.draw(screen, self.camera, layer_order=("mapa",))
        self.player.draw(screen, self.camera)

        for u in self.npc_units.values():
            u.draw(screen, self.camera)

        for n in getattr(self.map, "npcs", []):
            nx = n["tile_x"] * TILE_SIZE - self.camera.x
            ny = n["tile_y"] * TILE_SIZE - self.camera.y
            pygame.draw.rect(screen, (60, 80, 220), (nx, ny, TILE_SIZE, TILE_SIZE))

        self.dialogue.render(screen)
