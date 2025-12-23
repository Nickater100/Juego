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
        # Atajos globales
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F5:
                from core.save_manager import save_game
                path = save_game(self.game_state, slot=1)
                print(f"[SAVE] Guardado en: {path}")
                return

            if event.key == pygame.K_F9:
                from core.save_manager import load_game
                loaded = load_game(slot=1)
                if loaded is None:
                    print("[LOAD] No existe save_01.json")
                    return

                self.game_state = loaded
                print("[LOAD] Partida cargada")

                # Volver al mundo (por ahora)
                from engines.world_engine.world_state import WorldState
                self.change_state(WorldState(self))
                return

        self.state.handle_event(event)


    def update(self, dt):
        self.state.update(dt)

    def render(self):
        self.state.render(self.screen)
        pygame.display.flip()
