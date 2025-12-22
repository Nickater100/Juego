import pygame
from core.entities.unit import Unit
from engines.world_engine.npc_controller import MovementController

TILE_SIZE = 32

class WorldState:
    def __init__(self, game):
        self.game = game
        self.player = Unit()
        self.controller = MovementController(self.player)

        self.move_dir = None
        self.move_timer = 0

        self.initial_delay = 0.18
        self.repeat_delay = 0.1

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

        # Primer paso inmediato
        if self.move_timer == 0:
            self.controller.try_move(*self.move_dir)

        # Delay inicial antes del auto-repeat
        elif self.move_timer >= self.initial_delay:
            self.controller.try_move(*self.move_dir)
            self.move_timer = self.initial_delay - self.repeat_delay

    def render(self, screen):
        screen.fill((40, 120, 40))
        pygame.draw.rect(
            screen,
            (200, 50, 50),
            (self.player.pixel_x, self.player.pixel_y, TILE_SIZE, TILE_SIZE)
        )
