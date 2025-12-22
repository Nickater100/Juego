import pygame

class BattleState:
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.SysFont(None, 48)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # Volver al mundo
                from engines.world_engine.world_state import WorldState
                self.game.change_state(WorldState(self.game))

    def update(self, dt):
        pass

    def render(self, screen):
        screen.fill((20, 20, 20))

        text = self.font.render("BATALLA (ESC para volver)", True, (220, 220, 220))
        rect = text.get_rect(center=screen.get_rect().center)
        screen.blit(text, rect)
