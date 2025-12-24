# project/engines/world_engine/world_state.py

from engines.world_engine.map_loader import TiledMap
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.npc_controller import MovementController
from core.entities.unit import Unit
import pygame
from core.config import TILE_SIZE
from render.world.camera import Camera
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from core.assets import asset_path
import json


class WorldState:
    def __init__(self, game, map_rel_path=("maps", "world", "town_01.json"), spawn_tile=None):
        self.game = game

        # ✅ ahora el mapa se decide desde afuera
        # map_rel_path puede ser tuple/list ("maps","world","town_01.json") o string "maps/world/town_01.json"
        if isinstance(map_rel_path, (tuple, list)):
            json_path = asset_path(*map_rel_path)
        else:
            json_path = asset_path(map_rel_path)

        self.map = TiledMap(
            json_path=json_path,
            assets_root=asset_path("")  # root assets (si asset_path("") ya apunta a assets)
        )

        # --- Cache JSON del mapa + objectgroups (puertas, triggers, etc) ---
        self._map_json_cache = None
        self._objectgroups_cache = {}

        # cache de puertas del mapa actual (object layer "puertas")
        self.doors = self._get_objectgroup("puertas")

        # anti-loop puertas
        self._door_was_inside = False
        self._door_cooldown = 0.0  # segundos
        # ✅ lock anti-rebote: al spawnear, bloquea puertas hasta salir
        self._door_lock_until_exit = False
        self._door_lock_rect = None


        filtered = []
        for n in getattr(self.map, "npcs", []):
            npc_id = n.get("id", "")
            if npc_id and self.game.game_state.get_flag(f"recruited:{npc_id}", False):
                continue
            filtered.append(n)
        self.map.npcs = filtered

        self.collision = CollisionSystem(self.map)
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)

        # ✅ spawn: si viene explícito, usarlo; si no, usar lo guardado en game_state
        if spawn_tile is not None:
            px, py = spawn_tile
            self.game.game_state.set_player_tile(px, py)
        else:
            px, py = self.game.game_state.get_player_tile()

        self.player = Unit(tile_x=px, tile_y=py)
        self.controller = MovementController(self.player, self.collision)

        self.move_dir = None
        self.move_timer = 0
        self.dialogue_options = []
        self.dialogue_option_index = 0
        self.dialogue_context = {}  # para saber con qué NPC/acción estamos
        self.initial_delay = 0.2
        self.repeat_delay = 0.12
        self.dialogue_active = False
        self.dialogue_lines = []
        self.dialogue_index = 0  # por si luego querés paginar
        self.dialogue_speaker = ""

        self.ui_font = pygame.font.SysFont(None, 24)

        # Retrato del protagonista (se muestra en diálogos)
        raw_portrait = pygame.image.load(
            asset_path("sprites", "protagonist", "portrait.png")
        ).convert_alpha()

        self.portrait_original = self._trim_transparent(raw_portrait)

        self.portrait_cover = None
        self.portrait_cover_key = None

    def handle_event(self, event):
        # Si hay diálogo abierto, capturamos teclas para navegar opciones / cerrar
        if self.dialogue_active:
            if event.type == pygame.KEYDOWN:
                # Cerrar
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    self.close_dialogue()
                    return

                # Navegar opciones (si existen)
                if self.dialogue_options:
                    if event.key == pygame.K_w:
                        self.dialogue_option_index = (self.dialogue_option_index - 1) % len(self.dialogue_options)
                        return
                    if event.key == pygame.K_s:
                        self.dialogue_option_index = (self.dialogue_option_index + 1) % len(self.dialogue_options)
                        return

                    # Confirmar opción
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.confirm_dialogue_option()
                        return
                else:
                    # Si no hay opciones, ENTER/SPACE también cierra (como antes)
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.close_dialogue()
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

            # Abrir menú de pausa estilo Pokémon
            if event.key in (pygame.K_RETURN, pygame.K_p):
                from engines.world_engine.pause_state import PauseState
                self.game.change_state(PauseState(self.game, self))
                return

            # Interactuar
            elif event.key == pygame.K_e:
                self.try_interact()

            # primer paso inmediato
            if self.move_dir and not self.player.is_moving:
                self.controller.try_move(*self.move_dir)
                self.move_timer = 0

        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d):
                self.move_dir = None
                self.move_timer = 0

    def update(self, dt):
        self.controller.update(dt)
        self.player.update_sprite(dt)

        self.camera.follow(self.player.pixel_x, self.player.pixel_y)

        # Movimiento fluido: intenta mover cada frame si no está moviéndose
        if self.move_dir and not self.player.is_moving:
            self.controller.try_move(*self.move_dir)
        else:
            self.move_timer = 0

        # --- Cooldown puertas ---
        if self._door_cooldown > 0:
            self._door_cooldown -= dt
            if self._door_cooldown < 0:
                self._door_cooldown = 0

        # Chequear puertas SOLO cuando el jugador no se está moviendo
        # ✅ Anti-rebote: si recién spawneó en una puerta, no disparar hasta salir del rect
        if self._door_lock_until_exit and self._door_lock_rect:
            player_rect = pygame.Rect(self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)
            if player_rect.colliderect(self._door_lock_rect):
                # sigue dentro, no evaluar puertas
                self._door_was_inside = True
                return
            else:
                # ya salió, liberar lock
                self._door_lock_until_exit = False
                self._door_lock_rect = None
                self._door_was_inside = False

        if not self.player.is_moving and self._door_cooldown == 0:
            player_rect = pygame.Rect(
                self.player.pixel_x,
                self.player.pixel_y,
                TILE_SIZE,
                TILE_SIZE
            )

            inside_any = False
            door_hit = None

            # usar cache (self.doors)
            for obj in self.doors:
                door_rect = pygame.Rect(obj["x"], obj["y"], obj["width"], obj["height"])
                if player_rect.colliderect(door_rect):
                    inside_any = True
                    door_hit = obj
                    break

            # Edge trigger: solo dispara cuando antes NO estaba dentro y ahora SÍ
            if inside_any and not self._door_was_inside and door_hit:
                props = self._props_to_dict(door_hit)

                # soporta tu property "map" y el nuevo "target_map"
                destino = props.get("map") or props.get("map")
                if destino:
                    self.cambiar_mapa(destino, puerta_entrada=door_hit)
                    self._door_cooldown = 0.25  # 250ms anti-loop
                    return

            self._door_was_inside = inside_any

        # ✅ Guardar SIEMPRE la última tile del jugador
        self.game.game_state.set_player_tile(self.player.tile_x, self.player.tile_y)

    # -------------------------------
    # JSON cache + objectgroups
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

    def cambiar_mapa(self, destino, puerta_entrada=None):
        destino_path = asset_path(destino)

        with open(destino_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Puertas del destino
        puertas_destino = []
        for layer in data.get("layers", []):
            if layer.get("type") == "objectgroup" and layer.get("name") == "puertas":
                puertas_destino = layer.get("objects", [])
                break

        # Si no hay puertas en destino: igual cargamos destino y spawn en (0,0)
        if not puertas_destino:
            nuevo = WorldState(self.game, map_rel_path=destino, spawn_tile=(0, 0))
            # lock básico (sin rect específico)
            nuevo._door_cooldown = 0.4
            self.game.change_state(nuevo)
            return

        puerta_destino = None
        tx = ty = None

        # 1) Spawn explícito desde la puerta de entrada (recomendado)
        if puerta_entrada:
            props_in = self._props_to_dict(puerta_entrada)
            if "spawn_x" in props_in and "spawn_y" in props_in:
                tx = int(props_in["spawn_x"])
                ty = int(props_in["spawn_y"])

                # Si además viene un "spawn_door_id", usamos esa puerta para lock (opcional)
                spawn_door_id = props_in.get("spawn_door_id")
                if spawn_door_id:
                    for d in puertas_destino:
                        if self._props_to_dict(d).get("id") == spawn_door_id:
                            puerta_destino = d
                            break

        # 2) Buscar puerta destino que apunte al mapa de origen (match por propiedad 'map')
        if tx is None or ty is None:
            puerta_destino = None
            if puerta_entrada:
                # Path del mapa de origen (normalizado)
                origen_path = self.map.json_path.replace("\\", "/").split("assets/")[-1]
                # Buscar puerta cuyo 'map' apunte al origen
                for pd in puertas_destino:
                    props_pd = self._props_to_dict(pd)
                    map_prop = props_pd.get("map", "").replace("\\", "/")
                    if map_prop.endswith(origen_path):
                        puerta_destino = pd
                        break

            # Si no se encontró match exacto, usar lógica de opuesto como fallback
            if puerta_destino is None:
                puerta_destino = puertas_destino[0]
                if puerta_entrada:
                    eje = "x" if puerta_entrada["width"] >= puerta_entrada["height"] else "y"
                    puerta_in_cx = puerta_entrada["x"] + puerta_entrada["width"] / 2
                    puerta_in_cy = puerta_entrada["y"] + puerta_entrada["height"] / 2
                    map_mid_x = (self.map.width * TILE_SIZE) / 2
                    map_mid_y = (self.map.height * TILE_SIZE) / 2
                    if eje == "x":
                        puerta_destino = max(puertas_destino, key=lambda o: o["x"]) if puerta_in_cx < map_mid_x else min(puertas_destino, key=lambda o: o["x"])
                    else:
                        puerta_destino = max(puertas_destino, key=lambda o: o["y"]) if puerta_in_cy < map_mid_y else min(puertas_destino, key=lambda o: o["y"])

            tx = int((puerta_destino["x"] + puerta_destino["width"] / 2) // TILE_SIZE)
            ty = int((puerta_destino["y"] + puerta_destino["height"] / 2) // TILE_SIZE)

        # Crear estado nuevo en el mapa destino y spawnear
        nuevo = WorldState(self.game, map_rel_path=destino, spawn_tile=(tx, ty))

        # ✅ Anti-rebote:
        # bloquear triggers hasta que el jugador SALGA del rect de la puerta destino
        if puerta_destino is not None:
            nuevo._door_lock_until_exit = True
            nuevo._door_lock_rect = pygame.Rect(
                puerta_destino["x"], puerta_destino["y"],
                puerta_destino["width"], puerta_destino["height"]
            )
            # además, por seguridad, un cooldown corto
            nuevo._door_cooldown = 0.15
            nuevo._door_was_inside = True
        else:
            # si no sabemos qué puerta fue, al menos un cooldown para evitar rebote
            nuevo._door_cooldown = 0.4
            nuevo._door_was_inside = True

        self.game.change_state(nuevo)



    def render(self, screen):
        screen.fill((0, 0, 0))

        # Dibujar mapa (esto ya blitea los tiles)
        self.map.draw(screen, self.camera, layer_order=("mapa",))

        # Dibujar protagonista
        self.player.draw(screen, self.camera)

        # NPCs MVP (cuadrados)
        for n in getattr(self.map, "npcs", []):
            nx = n["tile_x"] * TILE_SIZE - self.camera.x
            ny = n["tile_y"] * TILE_SIZE - self.camera.y
            pygame.draw.rect(screen, (60, 80, 220), (nx, ny, TILE_SIZE, TILE_SIZE))

        # Diálogo
        if self.dialogue_active:
            self.render_dialogue(screen)

    def try_interact(self):
        # NPC enfrente del jugador
        dx, dy = self.player.facing
        tx = self.player.tile_x + dx
        ty = self.player.tile_y + dy

        npc = None
        for n in getattr(self.map, "npcs", []):
            if n.get("tile_x") == tx and n.get("tile_y") == ty:
                npc = n
                break

        if not npc:
            return

        self.open_dialogue(
            npc.get("name", ""),
            npc.get("dialogue", []),
            options=npc.get("options", []),
            context={"npc_id": npc.get("id", ""), "npc": npc}
        )

    def open_dialogue(self, speaker: str, lines: list[str], options=None, context=None):
        self.dialogue_active = True
        self.dialogue_speaker = speaker
        self.dialogue_lines = lines[:] if lines else ["..."]
        self.dialogue_index = 0

        self.dialogue_options = options[:] if options else []
        self.dialogue_option_index = 0
        self.dialogue_context = context or {}

    def close_dialogue(self):
        self.dialogue_active = False
        self.dialogue_speaker = ""
        self.dialogue_lines = []
        self.dialogue_index = 0

    def _trim_transparent(self, surface: pygame.Surface) -> pygame.Surface:
        """Recorta bordes transparentes de una imagen (alpha trim)."""
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

        # -------------------------
        # Layout fijo: 1/4 retrato, 3/4 texto
        # -------------------------
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

        # -------------------------
        # Retrato: 'contain' (entra completo) + panel negro
        # -------------------------
        cache_key = (portrait_area.w, portrait_area.h)
        if getattr(self, "portrait_cover_key", None) != cache_key:
            ow, oh = self.portrait_original.get_width(), self.portrait_original.get_height()

            scale_needed = min(portrait_area.w / ow, portrait_area.h / oh)
            new_w = int(ow * scale_needed)
            new_h = int(oh * scale_needed)

            scaled = pygame.transform.smoothscale(self.portrait_original, (new_w, new_h))

            panel = pygame.Surface((portrait_area.w, portrait_area.h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 255))

            px = (portrait_area.w - new_w) // 2
            py = (portrait_area.h - new_h) // 2
            panel.blit(scaled, (px, py))

            self.portrait_cover = panel
            self.portrait_cover_key = cache_key

        screen.blit(self.portrait_cover, (portrait_area.x, portrait_area.y))

        # -------------------------
        # Word-wrap para el texto dentro del área
        # -------------------------
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

        # Nombre hablante
        if self.dialogue_speaker:
            name_surf = self.ui_font.render(self.dialogue_speaker + ":", True, (255, 255, 255))
            screen.blit(name_surf, (text_x, text_y))
            text_y += 22

        # Texto principal
        all_text = " ".join(self.dialogue_lines) if self.dialogue_lines else "..."
        wrapped = wrap_lines(all_text, self.ui_font, text_area.width)

        line_h = 22

        # Reservar espacio para opciones si existen
        options_lines = len(self.dialogue_options) if getattr(self, "dialogue_options", []) else 0
        options_space = options_lines * line_h + (10 if options_lines else 0)

        max_text_lines = max(1, (text_area.height - options_space - 24) // line_h)
        for i, line in enumerate(wrapped[:max_text_lines]):
            line_surf = self.ui_font.render(line, True, (255, 255, 255))
            screen.blit(line_surf, (text_x, text_y + i * line_h))

        # -------------------------
        # Opciones
        # -------------------------
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

    def confirm_dialogue_option(self):
        # Si no hay opciones, cerrar diálogo
        if not self.dialogue_options:
            self.close_dialogue()
            return

        # Opción seleccionada
        option = self.dialogue_options[self.dialogue_option_index]
        action = option.get("action", "close")

        # Acción: cerrar
        if action == "close":
            self.close_dialogue()
            return

        # Acción: reclutar
        if action == "recruit":
            unit_id = option.get("unit_id", "unknown")

            # Evitar reclutar dos veces
            if any(u.get("id") == unit_id for u in self.game.game_state.party):
                self.dialogue_lines = ["Ya forma parte de tu ejército."]
                self.dialogue_options = [{"text": "Salir", "action": "close"}]
                self.dialogue_option_index = 0
                return

            # Agregar a la party
            self.game.game_state.add_party_member(
                unit_id=unit_id,
                name=self.dialogue_speaker,
                extra={"level": 1, "class": "soldier", "hp": 18, "atk": 5, "def": 3}
            )
            # Registrar reclutamiento como flag de historia
            self.game.game_state.set_flag(f"recruited:{unit_id}", True)

            npc_id = self.dialogue_context.get("npc_id")
            if npc_id:
                self.map.npcs = [n for n in getattr(self.map, "npcs", []) if n.get("id") != npc_id]

            # Feedback
            self.dialogue_lines = [f"{self.dialogue_speaker} se ha unido a tu ejército."]
            self.dialogue_options = [{"text": "Salir", "action": "close"}]
            self.dialogue_option_index = 0
            return

        # Acción desconocida → cerrar por seguridad
        self.close_dialogue()
