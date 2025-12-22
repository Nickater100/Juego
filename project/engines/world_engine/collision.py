class CollisionSystem:
    def __init__(self, map_data):
        self.map = map_data

    def can_move_to(self, tile_x, tile_y):
        return not self.map.is_blocked(tile_x, tile_y)
