import json
import os
import pygame
import xml.etree.ElementTree as ET

# Bits de flipping de Tiled (GID)
FLIP_H = 0x80000000
FLIP_V = 0x40000000
FLIP_D = 0x20000000
GID_MASK = 0x1FFFFFFF


class TiledMap:
    def __init__(self, json_path: str, assets_root: str = ""):
        self.json_path = os.path.normpath(json_path)
        self.assets_root = os.path.normpath(assets_root) if assets_root else ""

        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.width = data["width"]
        self.height = data["height"]
        self.tilewidth = data["tilewidth"]
        self.tileheight = data["tileheight"]

        # layers por nombre -> grilla 2D de gids
        self.layers = {}
        for layer in data.get("layers", []):
            if layer.get("type") == "tilelayer":
                name = layer.get("name", "")
                raw = layer.get("data", [])
                grid = [raw[y * self.width:(y + 1) * self.width] for y in range(self.height)]
                self.layers[name] = grid

        # collision: objectgroup "colission" (rectángulos bloquean tiles)
        self.collision = set()
        for layer in data.get("layers", []):
            if layer.get("type") == "objectgroup" and layer.get("name") in ("colission", "collision"):
                for obj in layer.get("objects", []):
                    # Convertir el rectángulo a tiles bloqueados
                    x0 = int(obj["x"] // self.tilewidth)
                    y0 = int(obj["y"] // self.tileheight)
                    w = int((obj["width"] + obj["x"] % self.tilewidth) // self.tilewidth)
                    h = int((obj["height"] + obj["y"] % self.tileheight) // self.tileheight)
                    for dx in range(w):
                        for dy in range(h):
                            tx = x0 + dx
                            ty = y0 + dy
                            if 0 <= tx < self.width and 0 <= ty < self.height:
                                self.collision.add((tx, ty))

        # tilesets (soporta TSX / TSJ / embebidos)
        self.tilesets = []
        for ts in data.get("tilesets", []):
            firstgid = ts["firstgid"]

            if "source" in ts:
                src = ts["source"]
                tileset_path = os.path.normpath(os.path.join(os.path.dirname(self.json_path), src))

                ts_data = self._load_external_tileset(tileset_path)
                if not ts_data:
                    continue

                # Resolver imagen SIEMPRE relativa al archivo tileset (tsx/tsj)
                image_abs = self._resolve_image_path(base_dir=os.path.dirname(tileset_path), image_rel=ts_data["image"])
            else:
                # tileset embebido en el mapa
                ts_data = ts
                if "image" not in ts_data:
                    continue

                # Resolver imagen relativa al JSON del mapa
                image_abs = self._resolve_image_path(base_dir=os.path.dirname(self.json_path), image_rel=ts_data["image"])

            tw = int(ts_data["tilewidth"])
            th = int(ts_data["tileheight"])
            columns = int(ts_data.get("columns", 0))
            tilecount = int(ts_data.get("tilecount", 0))
            margin = int(ts_data.get("margin", 0))
            spacing = int(ts_data.get("spacing", 0))

            if columns == 0 and tilecount > 0:
                # fallback: intentar inferir columnas desde el sheet si fuera posible, pero sin imagen cargada es difícil.
                # lo dejamos en 0: el _load_tiles evitará división por 0.
                pass

            self.tilesets.append({
                "firstgid": firstgid,
                "image": image_abs,
                "tilewidth": tw,
                "tileheight": th,
                "columns": columns,
                "tilecount": tilecount,
                "margin": margin,
                "spacing": spacing,
            })

        # cache de tiles por gid real (sin bits)
        self._gid_to_surface = {}
        self._load_tiles()

    # -------------------------------
    # Public API
    # -------------------------------
    def is_blocked(self, x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return True
        return (x, y) in self.collision

    def draw(self, screen, camera, layer_order=("ground", "objects")):
        tw, th = self.tilewidth, self.tileheight

        for layer_name in layer_order:
            grid = self.layers.get(layer_name)
            if not grid:
                continue

            for y in range(self.height):
                for x in range(self.width):
                    raw_gid = grid[y][x]
                    tile_surf = self._get_tile_surface(raw_gid)
                    if tile_surf is None:
                        continue

                    px = x * tw - camera.x
                    py = y * th - camera.y
                    screen.blit(tile_surf, (px, py))

    # -------------------------------
    # Internal helpers
    # -------------------------------
    def _resolve_image_path(self, base_dir: str, image_rel: str) -> str:
        """
        Resuelve path de imagen. Por defecto, relativo a base_dir.
        Si querés forzar todo bajo assets_root, podés ajustar acá.
        """
        image_rel = image_rel.replace("\\", "/")

        # Si viene absoluto, lo respetamos
        if os.path.isabs(image_rel):
            return os.path.normpath(image_rel)

        # Si assets_root se usa y querés que Tiled use rutas como 'tilesets/xxx.png'
        # entonces podés descomentar esta lógica:
        # if self.assets_root:
        #     candidate = os.path.normpath(os.path.join(self.assets_root, image_rel))
        #     if os.path.exists(candidate):
        #         return candidate

        return os.path.normpath(os.path.join(base_dir, image_rel))

    def _load_external_tileset(self, tileset_path: str) -> dict | None:
        """
        Carga tileset externo:
        - .tsj (JSON)
        - .tsx (XML)
        """
        if not os.path.exists(tileset_path):
            # Ruta inválida: típicamente porque Tiled guardó tileset fuera del repo
            raise FileNotFoundError(f"No existe el tileset externo: {tileset_path}")

        lower = tileset_path.lower()

        if lower.endswith(".tsj"):
            with open(tileset_path, "r", encoding="utf-8") as f:
                ts_data = json.load(f)

            if "image" not in ts_data:
                raise ValueError(f"Tileset TSJ sin 'image': {tileset_path}")
            return ts_data

        if lower.endswith(".tsx"):
            tree = ET.parse(tileset_path)
            root = tree.getroot()

            img_node = root.find("image")
            if img_node is None:
                raise ValueError(f"Tileset TSX sin <image>: {tileset_path}")

            ts_data = {
                "tilewidth": int(root.attrib["tilewidth"]),
                "tileheight": int(root.attrib["tileheight"]),
                "tilecount": int(root.attrib.get("tilecount", "0")),
                "columns": int(root.attrib.get("columns", "0")),
                "margin": int(root.attrib.get("margin", "0")),
                "spacing": int(root.attrib.get("spacing", "0")),
                "image": img_node.attrib["source"],
            }
            return ts_data

        raise ValueError(f"Tileset externo no soportado: {tileset_path}")

    def _load_tiles(self):
        for ts in self.tilesets:
            image_path = ts["image"]
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"No se encuentra la imagen del tileset: {image_path}")

            sheet = pygame.image.load(image_path).convert_alpha()

            firstgid = ts["firstgid"]
            tw, th = ts["tilewidth"], ts["tileheight"]
            columns = ts["columns"]
            tilecount = ts["tilecount"]
            margin = ts["margin"]
            spacing = ts["spacing"]

            if tilecount <= 0:
                continue
            if columns <= 0:
                # Evitar crash si el tileset no informa columns.
                # Si esto pasa, lo correcto es que Tiled exporte columns.
                raise ValueError(f"Tileset sin 'columns' válido (0). Imagen: {image_path}")

            for i in range(tilecount):
                col = i % columns
                row = i // columns
                x = margin + col * (tw + spacing)
                y = margin + row * (th + spacing)
                surf = pygame.Surface((tw, th), pygame.SRCALPHA)
                surf.blit(sheet, (0, 0), pygame.Rect(x, y, tw, th))
                gid = firstgid + i
                self._gid_to_surface[gid] = surf

    def _decode_gid(self, raw_gid: int):
        flip_h = bool(raw_gid & FLIP_H)
        flip_v = bool(raw_gid & FLIP_V)
        flip_d = bool(raw_gid & FLIP_D)
        gid = raw_gid & GID_MASK
        return gid, flip_h, flip_v, flip_d

    def _get_tile_surface(self, raw_gid: int):
        gid, fh, fv, fd = self._decode_gid(raw_gid)
        if gid == 0:
            return None

        base = self._gid_to_surface.get(gid)
        if base is None:
            return None

        surf = base
        if fd:
            surf = pygame.transform.rotate(surf, 90)
            fh = not fh
        if fh or fv:
            surf = pygame.transform.flip(surf, fh, fv)
        return surf
