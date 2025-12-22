class Unit:
    def __init__(self, tile_x=5, tile_y=5):
        self.tile_x = tile_x
        self.tile_y = tile_y

        self.pixel_x = tile_x * 32
        self.pixel_y = tile_y * 32

        self.move_speed = 120  # pixels por segundo
        self.is_moving = False
        self.target_x = self.pixel_x
        self.target_y = self.pixel_y
