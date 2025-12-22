class Camera:
    def __init__(self, width, height):
        self.x = 0
        self.y = 0
        self.width = width
        self.height = height

    def follow(self, target_x, target_y):
        self.x = target_x - self.width // 2
        self.y = target_y - self.height // 2
