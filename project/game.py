from engines.world_engine.world_state import WorldState
from engines.battle_engine.battle_state import BattleState
import pygame

class Game:
    def __init__(self, screen):
        self.screen = screen
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
