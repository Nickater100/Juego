import sys
import pygame


class PauseState:
    def __init__(self, game, world_state):
        self.game = game
        self.world_state = world_state  # referencia al mundo para dibujarlo detrás

        self.font = pygame.font.SysFont(None, 32)
        self.small_font = pygame.font.SysFont(None, 24)

        self.mode = "menu"  # "menu" o "army"

        self.options = ["Ejército", "EXIT"]
        self.option_index = 0

        # Ejército (grilla)
        self.army_cols = 4
        self.army_index = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        # --- salir / volver ---
        if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            if self.mode == "army":
                self.mode = "menu"
                return
            # cerrar pausa -> volver al mundo
            self.game.change_state(self.world_state)
            return

        # --- toggle tipo Pokémon (ENTER/P) ---
        if event.key in (pygame.K_RETURN, pygame.K_p) and self.mode == "menu":
            self.game.change_state(self.world_state)
            return

        if self.mode == "menu":
            self._handle_menu_input(event)
        elif self.mode == "army":
            self._handle_army_input(event)

    def _handle_menu_input(self, event):
        if event.key == pygame.K_w:
            self.option_index = (self.option_index - 1) % len(self.options)
        elif event.key == pygame.K_s:
            self.option_index = (self.option_index + 1) % len(self.options)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = self.options[self.option_index]
            if chosen == "Ejército":
                self.mode = "army"
                self.army_index = 0
            elif chosen == "EXIT":
                pygame.quit()
                sys.exit(0)

    def _handle_army_input(self, event):
        party = self.game.game_state.party
        if not party:
            # sin soldados: cualquier ENTER/ESC vuelve
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.mode = "menu"
            return

        rows = max(1, (len(party) + self.army_cols - 1) // self.army_cols)
        cols = self.army_cols

        x = self.army_index % cols
        y = self.army_index // cols

        if event.key == pygame.K_a:
            x = max(0, x - 1)
        elif event.key == pygame.K_d:
            x = min(cols - 1, x + 1)
        elif event.key == pygame.K_w:
            y = max(0, y - 1)
        elif event.key == pygame.K_s:
            y = min(rows - 1, y + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            # por ahora no hace nada (luego: ver stats / equipar)
            return

        new_index = y * cols + x
        if new_index < len(party):
            self.army_index = new_index

    def update(self, dt):
        # No actualizamos el mundo mientras está pausado
        pass

    def render(self, screen):
        # 1) Dibujar el mundo detrás
        self.world_state.render(screen)

        # 2) Oscurecer overlay
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        if self.mode == "menu":
            self._render_menu(screen)
        else:
            self._render_army(screen)

    def _render_menu(self, screen):
        w, h = screen.get_width(), screen.get_height()
        box_w, box_h = 320, 180
        box = pygame.Rect(w - box_w - 24, 24, box_w, box_h)

        pygame.draw.rect(screen, (10, 10, 10), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        title = self.font.render("PAUSA", True, (255, 255, 255))
        screen.blit(title, (box.x + 18, box.y + 14))

        y = box.y + 60
        for i, opt in enumerate(self.options):
            prefix = "▶ " if i == self.option_index else "  "
            surf = self.font.render(prefix + opt, True, (255, 255, 255))
            screen.blit(surf, (box.x + 18, y))
            y += 36

        hint = self.small_font.render("W/S elegir  ENTER confirmar  ESC volver", True, (200, 200, 200))
        screen.blit(hint, (24, h - 32))

    def _render_army(self, screen):
        w, h = screen.get_width(), screen.get_height()
        box = pygame.Rect(24, 24, w - 48, h - 80)

        pygame.draw.rect(screen, (10, 10, 10), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        title = self.font.render("EJÉRCITO", True, (255, 255, 255))
        screen.blit(title, (box.x + 18, box.y + 14))

        party = self.game.game_state.party
        if not party:
            msg = self.font.render("No tienes soldados reclutados.", True, (255, 255, 255))
            screen.blit(msg, (box.x + 18, box.y + 70))
            hint = self.small_font.render("ESC volver", True, (200, 200, 200))
            screen.blit(hint, (24, h - 32))
            return

        grid_top = box.y + 60
        grid_left = box.x + 18
        grid_w = box.width - 36
        grid_h = box.height - 90

        cols = self.army_cols
        rows = max(1, (len(party) + cols - 1) // cols)

        cell_w = grid_w // cols
        cell_h = max(60, grid_h // max(rows, 1))

        for idx, unit in enumerate(party):
            cx = idx % cols
            cy = idx // cols

            rect = pygame.Rect(
                grid_left + cx * cell_w,
                grid_top + cy * cell_h,
                cell_w - 10,
                cell_h - 10
            )

            pygame.draw.rect(screen, (20, 20, 20), rect)
            pygame.draw.rect(screen, (120, 120, 120), rect, 2)

            name = unit.get("name") or unit.get("id", "???")
            name_surf = self.small_font.render(name, True, (255, 255, 255))
            screen.blit(name_surf, (rect.x + 10, rect.y + 10))

            id_surf = self.small_font.render(unit.get("id", ""), True, (180, 180, 180))
            screen.blit(id_surf, (rect.x + 10, rect.y + 32))

            if idx == self.army_index:
                pygame.draw.rect(screen, (240, 220, 80), rect, 3)

        hint = self.small_font.render("W/A/S/D mover  ESC volver", True, (200, 200, 200))
        screen.blit(hint, (24, h - 32))
