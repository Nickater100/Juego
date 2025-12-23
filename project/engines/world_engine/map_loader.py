class MapData:
    def __init__(self):
        # 0 = libre, 1 = bloqueado
        self.grid = [
            [1,1,1,1,1,1,1,1,1,1],
            [1,0,0,0,0,0,0,0,0,1],
            [1,0,1,1,0,1,1,1,0,1],
            [1,0,0,0,0,0,0,1,0,1],
            [1,1,1,1,1,1,0,1,0,1],
            [1,0,0,0,0,0,0,0,0,1],
            [1,1,1,1,1,1,1,1,1,1],
        ]

        self.width = len(self.grid[0])
        self.height = len(self.grid)

        # NPCs del mapa (MVP)
        self.npcs = [
            {
                "id": "advisor_01",
                "name": "Consejero",
                "tile_x": 7,
                "tile_y": 5,
                "dialogue": [
                    "Mi príncipe... lamento lo de tu padre.",
                    "La aldea te necesita. Habla con el capitán para reclutar soldados."
                ],
            },
            {
                "id": "captain_01",
                "name": "Capitán",
                "tile_x": 8,
                "tile_y": 5,
                "dialogue": [
                    "A tus órdenes, mi príncipe.",
                    "¿Deseas que me una a tu ejército?"
                ],
                "options": [
                    {"text": "Reclutar", "action": "recruit", "unit_id": "captain_01"},
                    {"text": "Salir", "action": "close"}
                ],
            }
        ]


    def is_blocked(self, x, y):
        if x < 0 or y < 0:
            return True
        if x >= self.width or y >= self.height:
            return True
        return self.grid[y][x] == 1
