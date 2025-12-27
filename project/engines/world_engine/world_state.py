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
        from collections import deque

        self.game = game

        if isinstance(map_rel_path, (tuple, list)):
            json_path = asset_path(*map_rel_path)
        else:
            json_path = asset_path(map_rel_path)

        self.map = TiledMap(json_path=json_path, assets_root=asset_path(""))

        self.map_data = MapData(self.map.json_path, tile_size=TILE_SIZE)

        self.markers = self.map_data.load_markers()
        self.markers_static = self.map_data.load_markers_static()
        self.doors = self.map_data.get_objectgroup("puertas")
        self.triggers = self.map_data.get_objectgroup("triggers")

        self.input_locked = False

        # ✅ collision (SIN tile_size)
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

        # input
        self.move_dir = None
        self.move_timer = 0

        # systems
        self.dialogue = DialogueSystem(self)
        self.npc_system = NPCSystem(self, self.collision)
        self.interactions = WorldInteractionSystem(self, doors=self.doors, triggers=self.triggers)
        self.transitions = MapTransitionSystem(self)
        self.assign_roles = AssignRolesSystem(self)

        self.map.npcs = self.npc_system.filter_map_npcs(getattr(self.map, "npcs", []) or [])
        print("[DEBUG] game_state.npcs:", self.game.game_state.npcs)
        print("[DEBUG] game_state.story_flags:", self.game.game_state.story_flags)
        print("[DEBUG] markers_static:", self.markers_static)
        self._apply_static_role_placements()

        self.event_runner = EventRunner(self)
        self._event_assignments = {}
        self._event_apply_role_outcomes_step = None

        if not self.game.game_state.get_flag("intro_done", False):
            self.start_intro_event()

        # -----------------------------
        # ✅ Guardaespaldas (follow natural)
        # -----------------------------
        if not hasattr(self.game.game_state, "bodyguards"):
            self.game.game_state.bodyguards = []

        self._bg_prefix = "bg__"
        self._bodyguard_runtime_ids = []
        self._last_player_tile = (self.player.tile_x, self.player.tile_y)

        # Cola de posiciones previas del player (para "lag" suave)
        # Mientras más larga, más estable cuando el player camina seguido.
        self._follow_history = deque(maxlen=32)
        self._follow_history.appendleft(self._last_player_tile)

        # Ajustes de comportamiento
        self._follow_min_gap = 1          # cada guardaespaldas toma un tile distinto de atraso
        self._follow_snap_distance = 10   # si se desincronizan mucho, recién ahí corrige

        self.sync_bodyguards()


        # --------------------------------
        # Compat: usado por Interaction/Transition systems
        # --------------------------------

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
        # actualizar jugador
        self.controller.update(dt)
        self.player.update_sprite(dt)
        self.camera.follow(self.player.pixel_x, self.player.pixel_y)

        if (not self.input_locked) and self.move_dir and not self.player.is_moving:
            self.controller.try_move(*self.move_dir)
        else:
            self.move_timer = 0

        # ✅ Guardaespaldas: si el jugador cambió de tile, actualizar fila
        try:
            self._update_bodyguards_follow()
        except Exception:
            pass

        # actualizar NPCs / sistemas del mundo
        self.npc_system.update(dt)
        self.interactions.update(dt)

        # persistir tile del jugador
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

    def sync_bodyguards(self) -> None:
        """Sincroniza los guardaespaldas con unidades runtime en el mundo.

        - Spawnea runtime units con id 'bg__<unit_id>'
        - NO hace teleports agresivos: solo los coloca cerca al principio y luego siguen natural.
        """
        desired = []
        try:
            desired = list(getattr(self.game.game_state, "bodyguards", []) or [])
        except Exception:
            desired = []

        party_ids = set()
        try:
            party_ids = {
                str(u.get("id") or u.get("unit_id"))
                for u in (self.game.game_state.party or [])
                if (u.get("id") or u.get("unit_id"))
            }
        except Exception:
            party_ids = set()

        desired = [str(x) for x in desired if str(x) in party_ids]
        self.game.game_state.bodyguards = desired

        # runtime ids deseados
        desired_runtime = [self._bg_prefix + uid for uid in desired]

        # despawn los que sobran
        current_runtime = [
            rid for rid in list(getattr(self.npc_system, "units", {}).keys())
            if str(rid).startswith(self._bg_prefix)
        ]
        for rid in current_runtime:
            if rid not in desired_runtime:
                try:
                    self.npc_system.despawn_unit(rid)
                except Exception:
                    pass

        # spawn faltantes cerca del player
        px, py = self.player.tile_x, self.player.tile_y
        for uid in desired:
            rid = self._bg_prefix + uid
            if rid in getattr(self.npc_system, "units", {}):
                continue
            try:
                self.npc_system.spawn_runtime_unit(rid, uid, px, py)
            except Exception:
                pass

        self._bodyguard_runtime_ids = [self._bg_prefix + uid for uid in desired]

        # reset del history para que arranquen ordenados detrás del player
        self._last_player_tile = (self.player.tile_x, self.player.tile_y)
        try:
            self._follow_history.clear()
        except Exception:
            pass
        self._follow_history.appendleft(self._last_player_tile)

        # colocarlos formando fila inicial (sin parpadeo)
        # si el tile del player es (x,y), ponemos a todos en (x,y) al inicio pero sin teletransportes posteriores
        for rid in self._bodyguard_runtime_ids:
            u = getattr(self.npc_system, "units", {}).get(rid)
            if not u:
                continue
            u.tile_x = px
            u.tile_y = py
            u.pixel_x = px * TILE_SIZE
            u.pixel_y = py * TILE_SIZE
            u.target_x = u.pixel_x
            u.target_y = u.pixel_y
            u.is_moving = False


    def get_lethal_combat_party(self) -> list[dict]:
        """Lista de unidades que participan en un combate letal por traición/emboscada.

        Regla: sólo guardaespaldas asignados desde el menú de pausa.
        """
        try:
            bg = set(str(x) for x in (getattr(self.game.game_state, "bodyguards", []) or []))
        except Exception:
            bg = set()

        try:
            party = list(self.game.game_state.party or [])
        except Exception:
            party = []

        return [u for u in party if str(u.get("id") or u.get("unit_id")) in bg]

    def _teleport_unit_to_tile(self, unit: Unit, tx: int, ty: int) -> None:
        unit.tile_x = int(tx)
        unit.tile_y = int(ty)
        unit.pixel_x = unit.tile_x * TILE_SIZE
        unit.pixel_y = unit.tile_y * TILE_SIZE
        unit.is_moving = False

    def _update_bodyguards_follow(self) -> None:
        """Follow natural: usa historial de tiles del player y mueve en cadena.

        Claves:
        - Cada guardaespaldas i apunta a una posición del historial (lag = i+1).
        - Planifica movimientos para evitar que se bloqueen entre sí.
        - Evita teleports salvo desincronización extrema (map transition/atasco).
        """
        if not self._bodyguard_runtime_ids:
            return

        current_tile = (self.player.tile_x, self.player.tile_y)
        if current_tile != self._last_player_tile:
            # metemos la posición anterior del player al historial
            self._follow_history.appendleft(self._last_player_tile)
            self._last_player_tile = current_tile

        # snapshot unidades
        units = getattr(self.npc_system, "units", {})
        controllers = getattr(self.npc_system, "controllers", {})

        # 1) calcular target tile de cada guardaespaldas según historial
        # lag = (index + 1) * gap
        targets = {}
        for i, rid in enumerate(self._bodyguard_runtime_ids):
            lag = (i + 1) * self._follow_min_gap
            if lag < len(self._follow_history):
                targets[rid] = self._follow_history[lag]
            else:
                targets[rid] = self._follow_history[-1]

        # 2) plan de movimientos: quién se mueve y quién "vacía" su tile
        current_pos = {}
        for rid in self._bodyguard_runtime_ids:
            u = units.get(rid)
            if u:
                current_pos[rid] = (u.tile_x, u.tile_y)

        will_move = set()
        will_vacate_tiles = set()
        for rid, tgt in targets.items():
            cur = current_pos.get(rid)
            if cur and tgt != cur:
                will_move.add(rid)
                will_vacate_tiles.add(cur)

        # 3) ejecutar movimientos en orden (del más cercano al player al más lejano)
        # evitando:
        # - moverse si está en animación
        # - pisar un tile ocupado por otro guardaespaldas que NO se va a mover
        # - teleports salvo que estén demasiado lejos
        bg_set = set(self._bodyguard_runtime_ids)

        for rid in self._bodyguard_runtime_ids:
            u = units.get(rid)
            ctrl = controllers.get(rid)
            if not u or not ctrl:
                continue

            tgt = targets.get(rid, (u.tile_x, u.tile_y))

            # si ya está moviéndose, no tocar
            if u.is_moving:
                continue

            # si está demasiado lejos, snap (solo casos extremos)
            manhattan = abs(u.tile_x - tgt[0]) + abs(u.tile_y - tgt[1])
            if manhattan >= self._follow_snap_distance:
                u.tile_x, u.tile_y = tgt
                u.pixel_x = tgt[0] * TILE_SIZE
                u.pixel_y = tgt[1] * TILE_SIZE
                u.target_x = u.pixel_x
                u.target_y = u.pixel_y
                u.is_moving = False
                continue

            # ya en target
            if (u.tile_x, u.tile_y) == tgt:
                continue

            # dirección 4-dir hacia target
            dx = 0
            dy = 0
            if u.tile_x < tgt[0]:
                dx = 1
            elif u.tile_x > tgt[0]:
                dx = -1
            elif u.tile_y < tgt[1]:
                dy = 1
            elif u.tile_y > tgt[1]:
                dy = -1

            if dx == 0 and dy == 0:
                continue

            next_tile = (u.tile_x + dx, u.tile_y + dy)

            # Regla anti-traba:
            # Si next_tile está ocupado por otro guardaespaldas que NO va a vaciar su tile, no mover.
            blocked_by_bg = False
            for other_id in self._bodyguard_runtime_ids:
                if other_id == rid:
                    continue
                ou = units.get(other_id)
                if not ou:
                    continue
                if (ou.tile_x, ou.tile_y) == next_tile:
                    # si ese otro NO se mueve, bloquea
                    if other_id not in will_move:
                        blocked_by_bg = True
                    else:
                        # si se mueve, solo permitimos si su tile está en vacate (o sea, lo deja)
                        if (ou.tile_x, ou.tile_y) not in will_vacate_tiles:
                            blocked_by_bg = True
                    break

            if blocked_by_bg:
                continue

            # set facing y mover:
            u.set_facing(dx, dy)

            # acá ignoramos a todos los bodyguards en la colisión,
            # pero mantenemos colisión con NPCs/mapa.
            ctrl.try_move(dx, dy, ignore_unit_ids=bg_set)

    def _apply_static_role_placements(self) -> None:
        """
        Coloca NPCs con roles persistidos en markers_static.

        Usa properties en Tiled (capa: markers_static):
        - id (str) obligatorio
        - role (str) obligatorio (ej: "advisor" o "consejero")
        - slot (int) opcional (menor = prioridad)
        - facing (str) opcional: up/down/left/right
        - requires_flag (str) opcional

        Importante:
        - No toca markers de eventos.
        - No depende de eventos: funciona al entrar al mapa.
        """
        gs = self.game.game_state

        # construir role -> npc_id desde el estado persistido
        role_to_npc: dict[str, str] = {}
        try:
            npcs = getattr(gs, "npcs", {}) or {}
            for npc_id, st in npcs.items():
                if not st:
                    continue
                r = st.get("role")
                if r:
                    role_to_npc[str(r)] = str(npc_id)
        except Exception:
            role_to_npc = {}

        if not role_to_npc:
            return  # no hay roles persistidos aún

        # agrupar markers por role y ordenar por slot
        buckets: dict[str, list[dict]] = {}
        for m in (self.markers_static or []):
            props = m.get("props") or {}
            role = props.get("role")
            if not role:
                continue

            req = props.get("requires_flag")
            if req and not gs.get_flag(str(req), False):
                continue

            buckets.setdefault(str(role), []).append(m)

        for role, arr in buckets.items():
            def _slot_key(mm: dict) -> int:
                try:
                    return int((mm.get("props") or {}).get("slot", 0))
                except Exception:
                    return 0
            arr.sort(key=_slot_key)

        # aplicar: para cada role con marker, mover/spawnear al npc correspondiente
        for role, arr in buckets.items():
            npc_id = role_to_npc.get(role)
            if not npc_id:
                continue

            # si fue reclutado, no debería aparecer como NPC del mapa
            if gs.get_flag(f"recruited:{npc_id}", False):
                continue

            marker = arr[0]
            tx, ty = marker.get("tile", (None, None))
            if tx is None or ty is None:
                continue

            # spawn o mover
            if npc_id not in self.npc_system.units:
                try:
                    self.npc_system.spawn_unit(npc_id, int(tx), int(ty))
                except Exception:
                    continue

            u = self.npc_system.units.get(npc_id)
            if not u:
                continue

            u.tile_x = int(tx)
            u.tile_y = int(ty)
            u.pixel_x = int(tx) * TILE_SIZE
            u.pixel_y = int(ty) * TILE_SIZE
            u.target_x = u.pixel_x
            u.target_y = u.pixel_y
            u.is_moving = False

            # facing opcional
            facing = (marker.get("props") or {}).get("facing")
            if facing in ("up", "down", "left", "right"):
                if facing == "up":
                    u.set_facing(0, -1)
                elif facing == "down":
                    u.set_facing(0, 1)
                elif facing == "left":
                    u.set_facing(-1, 0)
                elif facing == "right":
                    u.set_facing(1, 0)
