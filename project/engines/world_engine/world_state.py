from engines.world_engine.map_loader import MapData
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.npc_controller import MovementController
from core.entities.unit import Unit
import pygame
from core.config import TILE_SIZE
from render.world.camera import Camera
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from core.assets import asset_path

class WorldState:
    def __init__(self, game):
        self.game = game

        self.map = MapData()
        self.collision = CollisionSystem(self.map)
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)


        px, py = self.game.game_state.get_player_tile()
        self.player = Unit(tile_x=px, tile_y=py)
        self.controller = MovementController(self.player, self.collision)

        self.move_dir = None
        self.move_timer = 0
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
        # Si hay diálogo abierto, capturamos teclas para cerrarlo
        if self.dialogue_active:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_SPACE):
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

        if not self.move_dir or self.player.is_moving:
            return

        self.move_timer += dt

        if self.move_timer >= self.initial_delay:
            self.controller.try_move(*self.move_dir)
            self.move_timer = self.initial_delay - self.repeat_delay

        self.game.game_state.set_player_tile(self.player.tile_x, self.player.tile_y)



    def render(self, screen):
        screen.fill((0, 0, 0))

        # Dibujar mapa
        for y, row in enumerate(self.map.grid):
            for x, tile in enumerate(row):
                color = (80, 80, 80) if tile == 1 else (40, 120, 40)
                world_x = x * TILE_SIZE - self.camera.x
                world_y = y * TILE_SIZE - self.camera.y

                pygame.draw.rect(
                    screen,
                    color,
                    (world_x, world_y, TILE_SIZE, TILE_SIZE)
                )
        # Dibujar protagonista (UNA vez)
        self.player.draw(screen, self.camera)

        # Dibujar NPCs (MVP: como cuadrados azules)
        # Dibujar NPCs (MVP: cuadrados azules)
        for n in getattr(self.map, "npcs", []):
            nx = n["tile_x"] * TILE_SIZE - self.camera.x
            ny = n["tile_y"] * TILE_SIZE - self.camera.y
            pygame.draw.rect(screen, (60, 80, 220), (nx, ny, TILE_SIZE, TILE_SIZE))


        # Dibujar caja de diálogo si está activa
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

        self.open_dialogue(npc.get("name", ""), npc.get("dialogue", []))


    def open_dialogue(self, speaker: str, lines: list[str]):
        self.dialogue_active = True
        self.dialogue_speaker = speaker
        self.dialogue_lines = lines[:] if lines else ["..."]
        self.dialogue_index = 0


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
        # Retrato "cover" sin deformar
        # Recorte ANCLADO ARRIBA (para que no corte la cara)
        # -------------------------
        cache_key = (portrait_area.w, portrait_area.h)
        if getattr(self, "portrait_cover_key", None) != cache_key:
            ow, oh = self.portrait_original.get_width(), self.portrait_original.get_height()

            # Escalado tipo 'contain': la imagen siempre entra completa en el área
            scale_needed = min(portrait_area.w / ow, portrait_area.h / oh)
            new_w = int(ow * scale_needed)
            new_h = int(oh * scale_needed)
            scaled = pygame.transform.smoothscale(self.portrait_original, (new_w, new_h))

            # Panel negro de fondo
            panel = pygame.Surface((portrait_area.w, portrait_area.h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 255))

            # Centramos la imagen escalada
            px = (portrait_area.w - new_w) // 2
            py = (portrait_area.h - new_h) // 2
            panel.blit(scaled, (px, py))
            self.portrait_cover = panel

        screen.blit(self.portrait_cover, (portrait_area.x, portrait_area.y))

        # -------------------------
        # Word-wrap para el texto dentro del área (nunca se sale)
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

        all_text = " ".join(self.dialogue_lines) if self.dialogue_lines else "..."
        wrapped = wrap_lines(all_text, self.ui_font, text_area.width)

        line_h = 22
        max_lines = max(1, (text_area.height - 24) // line_h)
        for i, line in enumerate(wrapped[:max_lines]):
            line_surf = self.ui_font.render(line, True, (255, 255, 255))
            screen.blit(line_surf, (text_x, text_y + i * line_h))

        hint = self.ui_font.render("ENTER/SPACE/ESC: cerrar", True, (180, 180, 180))
        screen.blit(hint, (box_rect.x + box_rect.w - 210, box_rect.y + box_rect.h - 28))


        # --------
        # Word-wrap del texto para que NUNCA se salga del cuadro
        # --------
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

        # Unimos todas las líneas en un solo texto y lo wrappeamos al ancho del área de texto
        all_text = " ".join(self.dialogue_lines) if self.dialogue_lines else "..."
        wrapped = wrap_lines(all_text, self.ui_font, text_area.width)

        # Dibujar líneas (máximo según la altura disponible)
        line_h = 22
        max_lines = max(1, (text_area.height - 24) // line_h)
        for i, line in enumerate(wrapped[:max_lines]):
            line_surf = self.ui_font.render(line, True, (255, 255, 255))
            screen.blit(line_surf, (text_x, text_y + i * line_h))

        hint = self.ui_font.render("ENTER/SPACE/ESC: cerrar", True, (180, 180, 180))
        screen.blit(hint, (box_rect.x + box_rect.w - 210, box_rect.y + box_rect.h - 28))
