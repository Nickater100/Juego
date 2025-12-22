TILE_SIZE = 32

class MovementController:
    def __init__(self, unit):
        self.unit = unit

    def try_move(self, dx, dy):
        if self.unit.is_moving:
            return

        self.unit.tile_x += dx
        self.unit.tile_y += dy

        self.unit.target_x = self.unit.tile_x * TILE_SIZE
        self.unit.target_y = self.unit.tile_y * TILE_SIZE
        self.unit.is_moving = True

    def update(self, dt):
        if not self.unit.is_moving:
            return

        dx = self.unit.target_x - self.unit.pixel_x
        dy = self.unit.target_y - self.unit.pixel_y

        dist = (dx ** 2 + dy ** 2) ** 0.5
        step = self.unit.move_speed * dt

        if dist <= step:
            self.unit.pixel_x = self.unit.target_x
            self.unit.pixel_y = self.unit.target_y
            self.unit.is_moving = False
        else:
            self.unit.pixel_x += (dx / dist) * step
            self.unit.pixel_y += (dy / dist) * step
