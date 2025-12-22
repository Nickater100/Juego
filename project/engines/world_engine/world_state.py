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


        px, py = self.game.game_state.get_player_tile()
        self.player = Unit(tile_x=px, tile_y=py)
        self.controller = MovementController(self.player, self.collision)

        self.move_dir = None
        self.move_timer = 0
        self.initial_delay = 0.2
        self.repeat_delay = 0.12


    def handle_event(self, event):
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

            # primer paso inmediato
            if self.move_dir and not self.player.is_moving:
                self.controller.try_move(*self.move_dir)
                self.move_timer = 0

        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_w, pygame.K_s, pygame.K_a, pygame.K_d):
                self.move_dir = None
                self.move_timer = 0

            elif event.key == pygame.K_b:
                from engines.battle_engine.battle_state import BattleState
                self.game.change_state(BattleState(self.game))

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
