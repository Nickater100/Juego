# project/engines/world_engine/world_state.py
from __future__ import annotations

import json
import os
import pygame

from core.assets import asset_path
from core.config import TILE_SIZE, SCREEN_WIDTH, SCREEN_HEIGHT
from core.entities.unit import Unit
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.event_runner import EventRunner
from engines.world_engine.map_loader import TiledMap
from engines.world_engine.npc_controller import MovementController
from render.world.camera import Camera


class WorldState:
    def __init__(self, game, map_rel_path=("maps", "world", "town_01.json"), spawn_tile=None):
        self.game = game

        # map_rel_path puede ser tuple/list ("maps","world","town_01.json") o string "maps/world/town_01.json"
        if isinstance(map_rel_path, (tuple, list)):
            json_path = asset_path(*map_rel_path)
        else:
            json_path = asset_path(map_rel_path)

        self.map = TiledMap(
            json_path=json_path,
            assets_root=asset_path("")  # root assets
        )

        # --- Cache JSON del mapa + objectgroups ---
        self._map_json_cache = None
        self._objectgroups_cache = {}

        self.markers = self._load_markers()
        self.doors = self._get_objectgroup("puertas")
        self.triggers = self._get_objectgroup("triggers")

        self._trigger_fired = set()

        # anti-loop puertas
        self._door_was_inside = False
        self._door_cooldown = 0.0  # segundos

        # lock anti-rebote: al spawnear en una puerta, bloquea puertas hasta salir del rect
        self._door_lock_until_exit = False
        self._door_lock_rect = None

        # Input lock (para eventos)
        self.input_locked = False

        # --- NPC Units (para intro y tareas) ---
        self.npc_units = {}        # npc_id -> Unit
        self.npc_controllers = {}  # npc_id -> MovementController
        self.npc_tasks = {}        # npc_id -> {"type": "walk_to", "target": (x,y), "despawn": bool}

        # Filtrado NPCs del mapa (tu lógica previa)
        filtered = []
        for n in getattr(self.map, "npcs", []):
            npc_id = n.get("id", "")
            if npc_id and self.game.game_state.get_flag(f"recruited:{npc_id}", False):
                continue
            filtered.append(n)
        self.map.npcs = filtered

        self.collision = CollisionSystem(self.map, get_npc_units=lambda: self.npc_units)
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)

        # spawn: si viene explícito, usarlo; si no, usar lo guardado en game_state
        if spawn_tile is not None:
            px, py = spawn_tile
            self.game.game_state.set_player_tile(px, py)
        else:
            px, py = self.game.game_state.get_player_tile()

        self.player = Unit(tile_x=px, tile_y=py)
        self.controller = MovementController(self.player, self.collision)

        # Movimiento / UI diálogo
        self.move_dir = None
        self.move_timer = 0
        self.dialogue_options = []
        self.dialogue_option_index = 0
        self.dialogue_context = {}
        self.initial_delay = 0.2
        self.repeat_delay = 0.12
        self.dialogue_active = False
        self.dialogue_lines = []
        self.dialogue_index = 0
        self.dialogue_speaker = ""

        self.ui_font = pygame.font.SysFont(None, 24)

        # Retrato del protagonista (diálogos)
        raw_portrait = pygame.image.load(
            asset_path("sprites", "protagonist", "portrait.png")
        ).convert_alpha()

        self.portrait_original = self._trim_transparent(raw_portrait)
        self.portrait_cover = None
        self.portrait_cover_key = None

        # Event system
        self.event_runner = EventRunner(self)

        # Estado UI assign_roles
        self._assign_active = False
        self._assign_step = None
        self._assign_npcs = []
        self._assign_roles = []
        self._assign_remaining = {}
        self._assign_idx = 0
        self._assignments_local = {}

        # Estado asignaciones de evento (lo usa _apply_role_outcomes_for_npc)
        self._event_assignments = {}

        # Si es partida nueva (intro no hecho) arrancar evento intro automáticamente
        if not self.game.game_state.get_flag("intro_done", False):
            self.start_intro_event()

    # -------------------------------
    # Input
    # -------------------------------
    def handle_event(self, event):
        # Si hay diálogo abierto: capturar teclas
        if self.dialogue_active:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    self.close_dialogue()
                    return

                if self.dialogue_options:
                    if event.key == pygame.K_w:
                        self.dialogue_option_index = (self.dialogue_option_index - 1) % len(self.dialogue_options)
                        return
                    if event.key == pygame.K_s:
                        self.dialogue_option_index = (self.dialogue_option_index + 1) % len(self.dialogue_options)
                        return

                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.confirm_dialogue_option()
                        return
                else:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        # Si hay más líneas, avanzar diálogo
                        if self.dialogue_index + 1 < len(self.dialogue_lines):
                            self.dialogue_index += 1
                        else:
                            ctx = dict(self.dialogue_context) if self.dialogue_context else {}
                            self.close_dialogue()
                            # Si el diálogo viene de un evento, avanzar evento
                            if ctx.get("event") == "json_event" and not ctx.get("after_dialogue"):
                                self.event_runner.advance()
                        return

        if self.input_locked:
            # Permitimos solamente diálogo (ya lo manejás arriba)
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

            elif event.key == pygame.K_e:
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
        # Player
        self.controller.update(dt)
        self.player.update_sprite(dt)

        self.camera.follow(self.player.pixel_x, self.player.pixel_y)

        if (not self.input_locked) and self.move_dir and (not self.player.is_moving):
            self.controller.try_move(*self.move_dir)
        else:
            self.move_timer = 0

        # NPCs (IMPORTANTE: si no, no caminan)
        for ctrl in self.npc_controllers.values():
            ctrl.update(dt)
        for u in self.npc_units.values():
            u.update_sprite(dt)

        # Cooldown puertas
        if self._door_cooldown > 0:
            self._door_cooldown -= dt
            if self._door_cooldown < 0:
                self._door_cooldown = 0

        # Anti-rebote al spawnear en puerta
        skip_doors_this_frame = False
        if self._door_lock_until_exit and self._door_lock_rect:
            player_rect = pygame.Rect(self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)
            if player_rect.colliderect(self._door_lock_rect):
                self._door_was_inside = True
                skip_doors_this_frame = True
            else:
                self._door_lock_until_exit = False
                self._door_lock_rect = None
                self._door_was_inside = False

        # Evaluación de puertas (edge trigger)
        if (not skip_doors_this_frame) and (not self.input_locked) and (not self.player.is_moving) and self._door_cooldown == 0:
            player_rect = pygame.Rect(self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)

            inside_any = False
            door_hit = None

            for obj in self.doors:
                door_rect = pygame.Rect(obj["x"], obj["y"], obj["width"], obj["height"])
                if player_rect.colliderect(door_rect):
                    inside_any = True
                    door_hit = obj
                    break

            if inside_any and (not self._door_was_inside) and door_hit:
                props = self._props_to_dict(door_hit)
                destino = props.get("map") or props.get("target_map")
                if destino:
                    self.cambiar_mapa(destino, puerta_entrada=door_hit)
                    self._door_cooldown = 0.25
                    return

            self._door_was_inside = inside_any

        # Triggers
        if not self.input_locked:
            self._check_triggers()

        # Guardar tile del jugador siempre
        self.game.game_state.set_player_tile(self.player.tile_x, self.player.tile_y)

        # NPC tasks (caminar + despawn)
        self._update_npc_tasks(dt)

        # Event runner
        if getattr(self, "event_runner", None):
            self.event_runner.update(dt)

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
                # Si en el futuro querés eventos por trigger, acá
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

            # Llegó
            if unit.tile_x == tx and unit.tile_y == ty:
                if task.get("despawn"):
                    self.npc_units.pop(npc_id, None)
                    self.npc_controllers.pop(npc_id, None)
                    self.npc_tasks.pop(npc_id, None)

                    # Persistencia
                    self.game.game_state.set_npc(
                        npc_id,
                        active=False,
                        map=None,
                        tile=None
                    )
                continue

            if unit.is_moving:
                continue

            # Step simple hacia el target
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
    # Interacción
    # -------------------------------
    def try_interact(self):
        dx, dy = self.player.facing
        tx = self.player.tile_x + dx
        ty = self.player.tile_y + dy

        npc_id = None
        npc_data = None

        # 1) NPCs del mapa
        for n in getattr(self.map, "npcs", []) or []:
            if n.get("tile_x") == tx and n.get("tile_y") == ty:
                npc_data = n
                npc_id = n.get("id")
                break

        # 2) NPCs spawneados (Unit)
        if npc_id is None:
            for uid, u in getattr(self, "npc_units", {}).items():
                if getattr(u, "tile_x", None) == tx and getattr(u, "tile_y", None) == ty:
                    npc_id = uid
                    break

        if not npc_id:
            return

        # 3) Si hay evento activo, dejar que el runner consuma interacción
        if getattr(self, "event_runner", None) and self.event_runner.active:
            if self.event_runner.on_player_interact(npc_id):
                return

        # 4) Interacción normal
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

    # -------------------------------
    # Diálogo
    # -------------------------------
    def open_dialogue(self, speaker, lines, options=None, context=None):
        self.dialogue_active = True
        self.dialogue_speaker = speaker
        self.dialogue_lines = lines[:] if lines else ["..."]
        self.dialogue_index = 0
        self.dialogue_options = options[:] if options else []
        self.dialogue_option_index = 0
        self.dialogue_context = context or {}

    def close_dialogue(self):
        after = self.dialogue_context.get("after_dialogue") if self.dialogue_context else None

        # si es assign_roles y se cierra con ESC, avanzá para no colgar
        if self.dialogue_context and self.dialogue_context.get("event") == "assign_roles" and getattr(self, "_assign_active", False):
            self._assign_idx += 1
            self._show_assign_prompt()
            return

        self.dialogue_active = False
        self.dialogue_speaker = ""
        self.dialogue_lines = []
        self.dialogue_index = 0
        self.dialogue_options = []
        self.dialogue_option_index = 0
        self.dialogue_context = {}

        if after:
            after()

    def confirm_dialogue_option(self):
        if not self.dialogue_options:
            self.close_dialogue()
            return

        option = self.dialogue_options[self.dialogue_option_index]
        action = option.get("action", "close")

        # Eventos
        if action == "event_continue":
            self.close_dialogue()
            self.event_runner.advance()
            return

        if isinstance(action, str) and action.startswith("assign_role:"):
            role = action.split(":", 1)[1]
            self._assign_current_npc(role)
            return

        # Acciones normales
        if action == "close":
            self.close_dialogue()
            return

        if action == "recruit":
            unit_id = option.get("unit_id", "unknown")

            if any(u.get("id") == unit_id for u in self.game.game_state.party):
                self.dialogue_lines = ["Ya forma parte de tu ejército."]
                self.dialogue_options = [{"text": "Salir", "action": "close"}]
                self.dialogue_option_index = 0
                return

            self.game.game_state.add_party_member(
                unit_id=unit_id,
                name=self.dialogue_speaker,
                extra={"level": 1, "class": "soldier", "hp": 18, "atk": 5, "def": 3}
            )
            self.game.game_state.set_flag(f"recruited:{unit_id}", True)

            npc_id = self.dialogue_context.get("npc_id")
            if npc_id:
                self.map.npcs = [n for n in getattr(self.map, "npcs", []) if n.get("id") != npc_id]

            self.dialogue_lines = [f"{self.dialogue_speaker} se ha unido a tu ejército."]
            self.dialogue_options = [{"text": "Salir", "action": "close"}]
            self.dialogue_option_index = 0
            return

        self.close_dialogue()

    def _trim_transparent(self, surface: pygame.Surface) -> pygame.Surface:
        rect = surface.get_bounding_rect()
        return surface.subsurface(rect).copy()

    def render_dialogue(self, screen):
        w, h = screen.get_width(), screen.get_height()

        box_h = 140
        margin = 16
        padding = 12
        gap = 16

        box_rect = pygame.Rect(margin, h - box_h - margin, w - margin * 2, box_h)
        pygame.draw.rect(screen, (0, 0, 0), box_rect)
        pygame.draw.rect(screen, (255, 255, 255), box_rect, 2)

        content_w = box_rect.width - padding * 2
        content_h = box_rect.height - padding * 2

        portrait_area_w = int(content_w * 0.25)
        text_area_w = content_w - portrait_area_w - gap

        portrait_area = pygame.Rect(
            box_rect.x + padding,
            box_rect.y + padding,
            portrait_area_w,
            content_h
        )

        text_area = pygame.Rect(
            portrait_area.right + gap,
            box_rect.y + padding,
            text_area_w,
            content_h
        )

        # --- Retrato dinámico según speaker ---
        portrait_surface = self.portrait_original
        portrait_key = "protagonist"

        speaker = self.dialogue_speaker.strip().lower().replace(" ", "_")
        if speaker in ["marian_vell", "selma_ironrose", "loren_valcrest", "iraen_falk", "elinya_brightwell"]:
            try:
                npc_json_path = asset_path("sprites", "npcs", speaker, f"{speaker}.json")
                if os.path.exists(npc_json_path):
                    with open(npc_json_path, "r", encoding="utf-8") as f:
                        npc_data = json.load(f)
                    portrait_path = npc_data.get("visual", {}).get("portrait")
                    if portrait_path:
                        surf = pygame.image.load(asset_path(*portrait_path.split("/"))).convert_alpha()
                        portrait_surface = self._trim_transparent(surf)
                        portrait_key = speaker
            except Exception:
                pass

        cache_key = (portrait_area.w, portrait_area.h, portrait_key)
        if getattr(self, "portrait_cover_key", None) != cache_key:
            ow, oh = portrait_surface.get_width(), portrait_surface.get_height()
            scale_needed = min(portrait_area.w / ow, portrait_area.h / oh)
            new_w = int(ow * scale_needed)
            new_h = int(oh * scale_needed)
            scaled = pygame.transform.smoothscale(portrait_surface, (new_w, new_h))
            panel = pygame.Surface((portrait_area.w, portrait_area.h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 255))
            px = (portrait_area.w - new_w) // 2
            py = (portrait_area.h - new_h) // 2
            panel.blit(scaled, (px, py))
            self.portrait_cover = panel
            self.portrait_cover_key = cache_key

        screen.blit(self.portrait_cover, (portrait_area.x, portrait_area.y))

        def wrap_lines(text: str, font: pygame.font.Font, max_w: int):
            words = text.split(" ")
            lines = []
            current = ""
            for word in words:
                test = word if not current else current + " " + word
                if font.size(test)[0] <= max_w:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            return lines

        text_x = text_area.x
        text_y = text_area.y

        if self.dialogue_speaker:
            name_surf = self.ui_font.render(self.dialogue_speaker + ":", True, (255, 255, 255))
            screen.blit(name_surf, (text_x, text_y))
            text_y += 22

        current_text = self.dialogue_lines[self.dialogue_index] if self.dialogue_lines else "..."
        wrapped = wrap_lines(current_text, self.ui_font, text_area.width)

        line_h = 22
        options_lines = len(self.dialogue_options) if getattr(self, "dialogue_options", []) else 0
        options_space = options_lines * line_h + (10 if options_lines else 0)

        max_text_lines = max(1, (text_area.height - options_space - 24) // line_h)
        for i, line in enumerate(wrapped[:max_text_lines]):
            line_surf = self.ui_font.render(line, True, (255, 255, 255))
            screen.blit(line_surf, (text_x, text_y + i * line_h))

        if getattr(self, "dialogue_options", []):
            opt_y = text_y + min(len(wrapped), max_text_lines) * line_h + 10
            for i, opt in enumerate(self.dialogue_options):
                prefix = "▶ " if i == self.dialogue_option_index else "  "
                opt_surf = self.ui_font.render(prefix + opt.get("text", ""), True, (255, 255, 255))
                screen.blit(opt_surf, (text_area.x, opt_y + i * line_h))
            hint_text = "W/S: elegir  ENTER: confirmar  ESC: cerrar"
        else:
            hint_text = "ENTER/SPACE/ESC: cerrar"

        hint = self.ui_font.render(hint_text, True, (180, 180, 180))
        screen.blit(hint, (box_rect.x + box_rect.w - 380, box_rect.y + box_rect.h - 28))

    # -------------------------------
    # Intro / evento inicial
    # -------------------------------
    def start_intro_event(self):
        if self.game.game_state.get_flag("intro_done", False):
            return

        self.input_locked = True

        # mover player al marker si existe
        if "spawn_player_start" in self.markers:
            px, py = self.markers["spawn_player_start"]
            self.player.tile_x = px
            self.player.tile_y = py
            self.player.pixel_x = px * TILE_SIZE
            self.player.pixel_y = py * TILE_SIZE
            self.game.game_state.set_player_tile(px, py)

        # spawnear NPCs
        self.spawn_intro_npcs_in_line()

        # cargar y correr evento JSON
        event_path = asset_path("data", "events", "intro_assign_roles.json")
        with open(event_path, "r", encoding="utf-8") as f:
            event_json = json.load(f)

        self.run_event(event_json)

    # -------------------------------
    # Assign Roles UI
    # -------------------------------
    def _start_assign_roles(self, step: dict) -> None:
        self._assign_step = step
        self._assign_active = True

        self._assign_npcs = list(step.get("npcs", []))
        self._assign_roles = list(step.get("roles", []))
        constraints = step.get("constraints", {}) or {}

        # 1) cupos iniciales desde constraints (por defecto 1 si no viene)
        self._assign_remaining = {r: int(constraints.get(r, 1)) for r in self._assign_roles}

        # 2) ✅ descontar lo ya asignado globalmente en el evento
        #    (esto hace que las opciones "ocupadas" ya no aparezcan)
        already = dict(getattr(self, "_event_assignments", {}) or {})
        for _npc_id, role in already.items():
            if role in self._assign_remaining:
                self._assign_remaining[role] -= 1

        # clamp a >= 0
        for r in list(self._assign_remaining.keys()):
            if self._assign_remaining[r] < 0:
                self._assign_remaining[r] = 0

        # 3) si este assign_roles viene para un solo npc, arrancamos en 0
        self._assign_idx = 0
        self._assignments_local = {}

        self._show_assign_prompt()


    def _assign_current_npc(self, role: str) -> None:
        if not getattr(self, "_assign_active", False):
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
            self.close_dialogue()
            if getattr(self, "event_runner", None) and self.event_runner.active:
                self.event_runner.on_assign_roles_done(self._event_assignments)
            return

        npc_id = self._assign_npcs[self._assign_idx]

        remaining_bits = []
        for r in self._assign_roles:
            remaining_bits.append(f"{r}: {max(0, int(self._assign_remaining.get(r, 0)))}")
        remaining_txt = ", ".join(remaining_bits)

        prompt_lines = [
            f"Asigná un rol para: {npc_id}",
            f"Pendientes -> {remaining_txt}"
        ]

        options = []
        for r in self._assign_roles:
            if self._assign_remaining.get(r, 0) > 0:
                options.append({"text": r, "action": f"assign_role:{r}"})

        if not options:
            for r in self._assign_roles:
                options.append({"text": r, "action": f"assign_role:{r}"})

        self.open_dialogue(
            "Asignación de roles",
            prompt_lines,
            options=options,
            context={"event": "assign_roles"}
        )

    # -------------------------------
    # Event hooks
    # -------------------------------
    def run_event(self, event_json):
        self.event_runner.start(event_json)

    def _run_next_event_step(self):
        self.event_runner.advance()

    # -------------------------------
    # Map change
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
            puerta_destino = None
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
    # NPC intro spawn + tasks
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

        self.npc_units[npc_id] = u
        self.npc_controllers[npc_id] = MovementController(u, self.collision)

    # -------------------------------
    # Map JSON helpers
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

        if self.dialogue_active:
            self.render_dialogue(screen)

    # -------------------------------
    # Event-related helper (si lo usa el runner)
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
            et = eff.get("type")
            if et == "join_party":
                self.game.game_state.add_party_member(
                    npc_id,
                    name=npc_id.replace("_", " ").title()
                )
                self.npc_units.pop(npc_id, None)
                self.npc_controllers.pop(npc_id, None)
                self.npc_tasks.pop(npc_id, None)
                self.game.game_state.set_npc(npc_id, active=False, map=None, tile=None)
            else:
                print(f"[LOG] Unknown role outcome effect: {et}")
