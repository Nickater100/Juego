import pygame
from core.assets import asset_path
from core.config import TILE_SIZE, SCREEN_WIDTH, SCREEN_HEIGHT


class BattleState:
    def __init__(self, game):
        self.game = game

        # ------------------------
        # Grid (MVP)
        # ------------------------
        self.grid_w = 12
        self.grid_h = 8

        # Cursor en coordenadas de grilla
        self.cursor_x = 0
        self.cursor_y = 0

        self.font = pygame.font.SysFont(None, 32)

        # ------------------------
        # Protagonista (sprite batalla)
        # ------------------------
        self.hero_tile_x = 2
        self.hero_tile_y = 3
        self.hero_facing = (0, 1)  # abajo (placeholder)

        self._battle_sheet = pygame.image.load(
            asset_path("sprites", "protagonist", "battle.png")
        ).convert_alpha()

        # RPG Maker SV Actor:
        # 9 columnas x 6 filas  -> sheet 576x384 (frames de 64x64)
        self._sv_cols = 9
        self._sv_rows = 6

        sheet_w = self._battle_sheet.get_width()
        sheet_h = self._battle_sheet.get_height()

        self._frame_w = sheet_w // self._sv_cols   # 64
        self._frame_h = sheet_h // self._sv_rows   # 64

        # Frame fijo inicial (idle / wait)
        # Podés ajustar estos valores luego para otra pose
        self._hero_frame_col = 1   # 0..8
        self._hero_frame_row = 1   # 0..5


    # ------------------------
    # Input
    # ------------------------
    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        # Volver al mundo
        if event.key == pygame.K_ESCAPE:
            from engines.world_engine.world_state import WorldState
            self.game.change_state(WorldState(self.game))
            return

        # Mover cursor
        dx, dy = 0, 0
        if event.key == pygame.K_w:
            dy = -1
        elif event.key == pygame.K_s:
            dy = 1
        elif event.key == pygame.K_a:
            dx = -1
        elif event.key == pygame.K_d:
            dx = 1

        if dx != 0 or dy != 0:
            self.move_cursor(dx, dy)

    def move_cursor(self, dx, dy):
        nx = self.cursor_x + dx
        ny = self.cursor_y + dy
        self.cursor_x = max(0, min(self.grid_w - 1, nx))
        self.cursor_y = max(0, min(self.grid_h - 1, ny))

    # ------------------------
    # Loop
    # ------------------------
    def update(self, dt):
        pass

    # ------------------------
    # Render helpers
    # ------------------------
    def _get_hero_frame(self):
        src = pygame.Rect(
            self._hero_frame_col * self._frame_w,
            self._hero_frame_row * self._frame_h,
            self._frame_w,
            self._frame_h
        )

        frame = self._battle_sheet.subsurface(src)

        # Ajustar al TILE_SIZE de la grilla táctica
        if frame.get_width() != TILE_SIZE or frame.get_height() != TILE_SIZE:
            frame = pygame.transform.scale(frame, (TILE_SIZE, TILE_SIZE))

        return frame


    # ------------------------
    # Render
    # ------------------------
    def render(self, screen):
        screen.fill((20, 20, 20))

        # Centrar grilla en pantalla
        grid_px_w = self.grid_w * TILE_SIZE
        grid_px_h = self.grid_h * TILE_SIZE
        origin_x = (SCREEN_WIDTH - grid_px_w) // 2
        origin_y = (SCREEN_HEIGHT - grid_px_h) // 2

        # Dibujar celdas
        for y in range(self.grid_h):
            for x in range(self.grid_w):
                r = pygame.Rect(
                    origin_x + x * TILE_SIZE,
                    origin_y + y * TILE_SIZE,
                    TILE_SIZE,
                    TILE_SIZE
                )
                pygame.draw.rect(screen, (45, 45, 45), r, 1)

        # Dibujar protagonista (frame fijo)
        hero_frame = self._get_hero_frame()
        screen.blit(
            hero_frame,
            (
                origin_x + self.hero_tile_x * TILE_SIZE,
                origin_y + self.hero_tile_y * TILE_SIZE
            )
        )

        # Cursor
        cursor_rect = pygame.Rect(
            origin_x + self.cursor_x * TILE_SIZE,
            origin_y + self.cursor_y * TILE_SIZE,
            TILE_SIZE,
            TILE_SIZE
        )
        pygame.draw.rect(screen, (230, 230, 80), cursor_rect, 3)

        # UI simple
        msg = f"BATALLA - Cursor: ({self.cursor_x},{self.cursor_y}) | ESC: volver"
        text = self.font.render(msg, True, (220, 220, 220))
        screen.blit(text, (20, 20))
