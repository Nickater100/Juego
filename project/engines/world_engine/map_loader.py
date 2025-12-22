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

    def is_blocked(self, x, y):
        if x < 0 or y < 0:
            return True
        if x >= self.width or y >= self.height:
            return True
        return self.grid[y][x] == 1
