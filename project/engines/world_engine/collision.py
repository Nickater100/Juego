
class CollisionSystem:
    def __init__(self, map_data, get_npc_units=None):
        self.map = map_data
        self.get_npc_units = get_npc_units  # callable returning dict npc_id -> Unit

    def can_move_to(self, tile_x, tile_y):
        # Bloqueo por mapa
        if self.map.is_blocked(tile_x, tile_y):
            return False

        # Bloqueo por NPCs del mapa (legacy)
        for n in getattr(self.map, "npcs", []):
            if n.get("tile_x") == tile_x and n.get("tile_y") == tile_y:
                return False

        # Bloqueo por Units activos (evento)
        npc_units = self.get_npc_units() if self.get_npc_units else None
        if npc_units:
            for u in npc_units.values():
                if u.tile_x == tile_x and u.tile_y == tile_y:
                    return False

        return True
