import sys
import pygame

from core.game_state import GameState
from core.save_manager import load_game


class StartMenuState:
    def __init__(self, game):
        self.game = game

        self.font_title = pygame.font.SysFont(None, 64)
        self.font = pygame.font.SysFont(None, 36)
        self.small = pygame.font.SysFont(None, 24)

        self.options = ["Nueva partida", "Cargar partida", "Salir"]
        self.option_index = 0

        self.message = ""
        self.message_timer = 0.0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key in (pygame.K_ESCAPE,):
            pygame.quit()
            sys.exit(0)

        if event.key == pygame.K_w:
            self.option_index = (self.option_index - 1) % len(self.options)
            return

        if event.key == pygame.K_s:
            self.option_index = (self.option_index + 1) % len(self.options)
            return

        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = self.options[self.option_index]

            if chosen == "Nueva partida":
                self.game.game_state = GameState()
                from engines.world_engine.world_state import WorldState
                self.game.change_state(WorldState(self.game))
                return

            if chosen == "Cargar partida":
                loaded = load_game(slot=1)
                if loaded is None:
                    self.message = "No hay partida guardada en slot 1 (save_01.json)."
                    self.message_timer = 2.0
                    return

                self.game.game_state = loaded
                from engines.world_engine.world_state import WorldState
                self.game.change_state(WorldState(self.game))
                return

            if chosen == "Salir":
                pygame.quit()
                sys.exit(0)

    def update(self, dt):
        if self.message_timer > 0:
            self.message_timer = max(0.0, self.message_timer - dt)
            if self.message_timer == 0.0:
                self.message = ""

    def render(self, screen):
        screen.fill((0, 0, 0))
        w, h = screen.get_width(), screen.get_height()

        title = self.font_title.render("MI RPG", True, (255, 255, 255))
        screen.blit(title, (w // 2 - title.get_width() // 2, 80))

        # Caja del menú
        box_w, box_h = 420, 220
        box = pygame.Rect(w // 2 - box_w // 2, 200, box_w, box_h)
        pygame.draw.rect(screen, (15, 15, 15), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        y = box.y + 40
        for i, opt in enumerate(self.options):
            prefix = "▶ " if i == self.option_index else "  "
            surf = self.font.render(prefix + opt, True, (255, 255, 255))
            screen.blit(surf, (box.x + 40, y))
            y += 50

        hint = self.small.render("W/S elegir  ENTER confirmar  ESC salir", True, (200, 200, 200))
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 40))

        if self.message:
            msg = self.small.render(self.message, True, (255, 200, 120))
            screen.blit(msg, (w // 2 - msg.get_width() // 2, box.bottom + 20))
