import sys
import pygame

from core.game_state import GameState
from core.save_manager import load_game, save_path


class StartMenuState:
    def __init__(self, game):
        self.game = game

        self.font_title = pygame.font.SysFont(None, 64)
        self.font = pygame.font.SysFont(None, 36)
        self.small = pygame.font.SysFont(None, 24)

        self.has_save = save_path(slot=1).exists()

        self.options = [
            {"id": "new", "text": "Nueva partida", "enabled": True},
            {
                "id": "load",
                "text": "Cargar partida",
                "enabled": self.has_save,
            },
            {"id": "exit", "text": "Salir", "enabled": True},
        ]

        self.option_index = 0
        if not self.options[self.option_index]["enabled"]:
            self.move_selection(1)

        self.message = ""
        self.message_timer = 0.0

    def move_selection(self, direction: int):
        start = self.option_index
        while True:
            self.option_index = (self.option_index + direction) % len(self.options)
            if self.options[self.option_index]["enabled"]:
                break
            if self.option_index == start:
                break

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit(0)

        if event.key == pygame.K_w:
            self.move_selection(-1)
            return

        if event.key == pygame.K_s:
            self.move_selection(1)
            return

        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if not self.options[self.option_index]["enabled"]:
                return

            chosen_id = self.options[self.option_index]["id"]

            # -----------------------------
            # NUEVA PARTIDA (RESET TOTAL)
            # -----------------------------
            if chosen_id == "new":
                # Reset duro del GameState
                self.game.game_state = GameState()

                # Seguridad: flags iniciales explícitos
                self.game.game_state.set_flag("intro_done", False)

                from engines.world_engine.world_state import WorldState
                self.game.change_state(WorldState(self.game))
                return

            # -----------------------------
            # CARGAR PARTIDA
            # -----------------------------
            if chosen_id == "load":
                loaded = load_game(slot=1)
                if loaded is None:
                    self.message = "No hay partida guardada en slot 1."
                    self.message_timer = 2.0
                    return

                self.game.game_state = loaded

                from engines.world_engine.world_state import WorldState
                self.game.change_state(WorldState(self.game))
                return

            # -----------------------------
            # SALIR
            # -----------------------------
            if chosen_id == "exit":
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

        box_w, box_h = 420, 220
        box = pygame.Rect(w // 2 - box_w // 2, 200, box_w, box_h)
        pygame.draw.rect(screen, (15, 15, 15), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        y = box.y + 40
        for i, opt in enumerate(self.options):
            prefix = "▶ " if i == self.option_index else "  "
            color = (255, 255, 255) if opt["enabled"] else (120, 120, 120)
            surf = self.font.render(prefix + opt["text"], True, color)
            screen.blit(surf, (box.x + 40, y))
            y += 50

        hint = self.small.render("W/S elegir  ENTER confirmar  ESC salir", True, (200, 200, 200))
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 40))

        if self.message:
            msg = self.small.render(self.message, True, (255, 200, 120))
            screen.blit(msg, (w // 2 - msg.get_width() // 2, box.bottom + 20))
