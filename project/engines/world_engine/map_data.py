# project/engines/world_engine/map_data.py

import json


class MapData:
    """
    Cache + queries del JSON del mapa (Tiled JSON).

    Responsabilidades:
      - load_json (cache)
      - get_objectgroup(name)
      - props_to_dict(obj)
      - load_markers() (usa objectgroup "markers" y property "id")
    """

    def __init__(self, json_path: str, tile_size: int):
        self.json_path = json_path
        self.tile_size = tile_size

        self._map_json_cache = None
        self._objectgroups_cache: dict[str, list[dict]] = {}

    def load_json(self) -> dict:
        if self._map_json_cache is None:
            with open(self.json_path, "r", encoding="utf-8") as f:
                self._map_json_cache = json.load(f)
        return self._map_json_cache

    def get_objectgroup(self, layer_name: str) -> list[dict]:
        if layer_name in self._objectgroups_cache:
            return self._objectgroups_cache[layer_name]

        data = self.load_json()
        for layer in data.get("layers", []):
            if layer.get("type") == "objectgroup" and layer.get("name") == layer_name:
                objs = layer.get("objects", [])
                self._objectgroups_cache[layer_name] = objs
                return objs

        self._objectgroups_cache[layer_name] = []
        return []

    def props_to_dict(self, obj: dict) -> dict:
        out = {}
        for p in obj.get("properties", []) or []:
            out[p.get("name")] = p.get("value")
        return out

    def load_markers(self) -> dict:
        markers = {}
        for obj in self.get_objectgroup("markers"):
            name = None
            for prop in obj.get("properties", []) or []:
                if prop.get("name") == "id":
                    name = prop.get("value")
                    break
            if not name:
                continue

            tx = int(obj["x"] // self.tile_size)
            ty = int(obj["y"] // self.tile_size)
            markers[name] = (tx, ty)

        return markers
