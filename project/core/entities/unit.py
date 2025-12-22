import pygame
from core.assets import asset_path
from core.config import TILE_SIZE


class Unit:
    def __init__(self, tile_x=5, tile_y=5):
        self.tile_x = tile_x
        self.tile_y = tile_y

        # Posición en píxeles (usar TILE_SIZE, no 32 hardcodeado)
        self.pixel_x = tile_x * TILE_SIZE
        self.pixel_y = tile_y * TILE_SIZE

        # Movimiento
        self.move_speed = 120  # pixels por segundo
        self.is_moving = False
        self.target_x = self.pixel_x
        self.target_y = self.pixel_y

        # --- Sprite overworld ---
        self.facing = (0, 1)  # abajo por defecto

        self._walk_sheet = pygame.image.load(
            asset_path("sprites", "protagonist", "walk.png")
        ).convert_alpha()

        # RPG Maker "sheet grande": 4 bloques a lo ancho, 2 a lo alto (total 8 slots)
        # En tu caso, el personaje está en el bloque superior-izquierdo (0,0)
        self._sheet_chars_x = 4
        self._sheet_chars_y = 2
        self._char_col = 0
        self._char_row = 0

        sheet_w = self._walk_sheet.get_width()
        sheet_h = self._walk_sheet.get_height()

        # Tamaño del bloque de 1 personaje dentro del sheet (ej 144x192)
        self._char_block_w = sheet_w // self._sheet_chars_x
        self._char_block_h = sheet_h // self._sheet_chars_y

        # Dentro del bloque: 3 columnas x 4 filas (frames)
        self._cols = 3
        self._rows = 4
        self._frame_w = self._char_block_w // self._cols
        self._frame_h = self._char_block_h // self._rows

        # Animación
        self._anim_time = 0.0
        self._anim_speed = 0.12
        self._frame_index = 1  # idle típico (columna del medio)

    def set_facing(self, dx: int, dy: int):
        if dx == 0 and dy == 0:
            return
        self.facing = (dx, dy)

    def update_sprite(self, dt: float):
        # Idle cuando no se mueve
        if not self.is_moving:
            self._frame_index = 1
            self._anim_time = 0.0
            return

        # Walk anim
        self._anim_time += dt
        if self._anim_time >= self._anim_speed:
            self._anim_time = 0.0
            self._frame_index = (self._frame_index + 1) % 3

    def draw(self, screen, camera):
        dx, dy = self.facing

        # Filas RPG Maker: abajo, izquierda, derecha, arriba
        if dy == 1:
            row = 0
        elif dx == -1:
            row = 1
        elif dx == 1:
            row = 2
        else:
            row = 3  # dy == -1

        col = self._frame_index

        # Offset al bloque del personaje dentro del sheet 4x2
        base_x = self._char_col * self._char_block_w
        base_y = self._char_row * self._char_block_h

        src = pygame.Rect(
            base_x + col * self._frame_w,
            base_y + row * self._frame_h,
            self._frame_w,
            self._frame_h
        )

        frame = self._walk_sheet.subsurface(src)

        # Ajustar al TILE_SIZE del mundo
        if frame.get_width() != TILE_SIZE or frame.get_height() != TILE_SIZE:
            frame = pygame.transform.scale(frame, (TILE_SIZE, TILE_SIZE))

        screen.blit(
            frame,
            (self.pixel_x - camera.x, self.pixel_y - camera.y)
        )
