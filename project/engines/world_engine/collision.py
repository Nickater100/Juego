
class CollisionSystem:
    def __init__(self, map_data, get_npc_units=None):
        self.map = map_data
        self.get_npc_units = get_npc_units  # callable returning dict npc_id -> Unit

    def can_move_to(self, tile_x, tile_y, ignore_unit_ids=None):
        """
        Devuelve True si se puede mover al tile (tile_x, tile_y).

        ignore_unit_ids: iterable de ids de runtime units (keys de npc_units)
                        que NO deben bloquear el movimiento.
        Se usa para permitir movimiento "en tren" (guardaespaldas),
        donde los followers no deberían bloquearse entre sí.
        """
        ignore = set(ignore_unit_ids or [])

        # Bloqueo por mapa
        if self.map.is_blocked(tile_x, tile_y):
            return False

        # Bloqueo por NPCs del mapa (legacy)
        for n in getattr(self.map, "npcs", []):
            if n.get("tile_x") == tile_x and n.get("tile_y") == tile_y:
                return False

        # Bloqueo por Units activos (evento/runtime)
        npc_units = self.get_npc_units() if self.get_npc_units else None
        if npc_units:
            for uid, u in npc_units.items():
                if uid in ignore:
                    continue
                if u.tile_x == tile_x and u.tile_y == tile_y:
                    return False

        return True

