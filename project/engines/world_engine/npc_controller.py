from core.config import TILE_SIZE

class MovementController:
    def __init__(self, unit, collision):
        self.unit = unit
        self.collision = collision

    def try_move(self, dx, dy, ignore_unit_ids=None):
        if self.unit.is_moving:
            return

        target_x = self.unit.tile_x + dx
        target_y = self.unit.tile_y + dy

        if not self.collision.can_move_to(target_x, target_y, ignore_unit_ids=ignore_unit_ids):
            return  # ❌ bloqueado

        self.unit.tile_x = target_x
        self.unit.tile_y = target_y

        self.unit.target_x = target_x * TILE_SIZE
        self.unit.target_y = target_y * TILE_SIZE
        self.unit.is_moving = True


    def update(self, dt):
        if not self.unit.is_moving:
            return

        dx = self.unit.target_x - self.unit.pixel_x
        dy = self.unit.target_y - self.unit.pixel_y

        dist = (dx**2 + dy**2) ** 0.5
        step = self.unit.move_speed * dt

        if dist <= step:
            self.unit.pixel_x = self.unit.target_x
            self.unit.pixel_y = self.unit.target_y
            self.unit.is_moving = False
        else:
            self.unit.pixel_x += (dx / dist) * step
            self.unit.pixel_y += (dy / dist) * step

