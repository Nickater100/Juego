class CollisionSystem:
    def __init__(self, map_data):
        self.map = map_data

    def can_move_to(self, tile_x, tile_y):
        # Bloqueo por mapa
        if self.map.is_blocked(tile_x, tile_y):
            return False

        # Bloqueo por NPCs (MVP)
        for n in getattr(self.map, "npcs", []):
            if n.get("tile_x") == tile_x and n.get("tile_y") == tile_y:
                return False

        return True
