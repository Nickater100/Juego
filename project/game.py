import pygame
from core.game_state import GameState
from engines.world_engine.world_state import WorldState


class Game:
    def __init__(self, screen):
        self.screen = screen

        # Estado persistente del juego
        self.game_state = GameState()

        # Estado actual (arranca en mundo)
        self.state = WorldState(self)

    def change_state(self, new_state):
        self.state = new_state

    def handle_event(self, event):
        self.state.handle_event(event)

    def update(self, dt):
        self.state.update(dt)

    def render(self):
        self.state.render(self.screen)
        pygame.display.flip()
