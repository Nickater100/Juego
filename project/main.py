import pygame
from game import Game

def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("My RPG")

    clock = pygame.time.Clock()
    game = Game(screen)

    running = True
    while running:
        dt = clock.tick(60) / 1000

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            game.handle_event(event)

        game.update(dt)
        game.render()

    pygame.quit()

if __name__ == "__main__":
    main()
