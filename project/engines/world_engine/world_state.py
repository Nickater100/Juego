from engines.world_engine.map_loader import MapData
from engines.world_engine.collision import CollisionSystem
from engines.world_engine.npc_controller import MovementController
from core.entities.unit import Unit
import pygame
from core.config import TILE_SIZE
from render.world.camera import Camera
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT

class WorldState:
    def __init__(self, game):
        self.game = game

        self.map = MapData()
        self.collision = CollisionSystem(self.map)
        self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT)


        self.player = Unit()
        self.controller = MovementController(self.player, self.collision)

        self.move_dir = None
        self.move_timer = 0
        self.initial_delay = 0.2
        self.repeat_delay = 0.12


    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_w:
                self.move_dir = (0, -1)
            elif event.key == pygame.K_s:
                self.move_dir = (0, 1)
            elif event.key == pygame.K_a:
                self.move_dir = (-1, 0)
            elif event.key == pygame.K_d:
                self.move_dir = (1, 0)

        elif event.type == pygame.KEYUP:
            if event.key in (
                pygame.K_w, pygame.K_s,
                pygame.K_a, pygame.K_d
            ):
                self.move_dir = None
                self.move_timer = 0

    def update(self, dt):
        self.controller.update(dt)

        if not self.move_dir:
            return

        if self.player.is_moving:
            return

        self.move_timer += dt

        self.camera.follow(
            self.player.pixel_x,
            self.player.pixel_y
        )


        # Primer paso inmediato
        if self.move_timer == 0:
            self.controller.try_move(*self.move_dir)

        # Delay inicial antes del auto-repeat
        elif self.move_timer >= self.initial_delay:
            self.controller.try_move(*self.move_dir)
            self.move_timer = self.initial_delay - self.repeat_delay

    def render(self, screen):
        for y, row in enumerate(self.map.grid):
            for x, tile in enumerate(row):
                color = (80, 80, 80) if tile == 1 else (40, 120, 40)  # 🔹 agregar esta línea
                world_x = x * TILE_SIZE - self.camera.x
                world_y = y * TILE_SIZE - self.camera.y

                pygame.draw.rect(
                    screen,
                    color,
                    (world_x, world_y, TILE_SIZE, TILE_SIZE)
                )

            # Limpiar pantalla antes de dibujar
            screen.fill((0, 0, 0))

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

            pygame.draw.rect(
                screen,
                (200, 50, 50),
                (
                    self.player.pixel_x - self.camera.x,
                    self.player.pixel_y - self.camera.y,
                    TILE_SIZE,
                    TILE_SIZE
                )
            )