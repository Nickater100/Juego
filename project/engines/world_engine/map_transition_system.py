# project/engines/world_engine/map_transition_system.py

import json
import pygame

from core.assets import asset_path
from core.config import TILE_SIZE


class MapTransitionSystem:
    """
    Encapsula la transición de mapas.
    - Lee JSON destino para resolver puertas
    - Decide spawn tile
    - Aplica lock/cooldown anti-rebote usando WorldInteractionSystem del nuevo state
    """

    def __init__(self, world_state):
        self.ws = world_state

    def change_map(self, destino: str, puerta_entrada: dict | None = None) -> None:
        destino_path = asset_path(destino)

        with open(destino_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        puertas_destino = []
        for layer in data.get("layers", []):
            if layer.get("type") == "objectgroup" and layer.get("name") == "puertas":
                puertas_destino = layer.get("objects", [])
                break

        # si el mapa destino no tiene puertas, spawn 0,0
        if not puertas_destino:
            nuevo = type(self.ws)(self.ws.game, map_rel_path=destino, spawn_tile=(0, 0))
            nuevo.interactions.set_cooldown(0.4)
            self.ws.game.change_state(nuevo)
            return

        puerta_destino = None
        tx = ty = None

        # 1) si puerta_entrada tiene spawn_x/spawn_y, usarlo
        if puerta_entrada:
            props_in = self.ws._props_to_dict(puerta_entrada)
            if "spawn_x" in props_in and "spawn_y" in props_in:
                tx = int(props_in["spawn_x"])
                ty = int(props_in["spawn_y"])

                spawn_door_id = props_in.get("spawn_door_id")
                if spawn_door_id:
                    for d in puertas_destino:
                        if self.ws._props_to_dict(d).get("id") == spawn_door_id:
                            puerta_destino = d
                            break

        # 2) si no hay spawn explícito, intentar match por “map” que apunte al origen
        if tx is None or ty is None:
            if puerta_entrada:
                origen_path = self.ws.map.json_path.replace("\\", "/").split("assets/")[-1]
                for pd in puertas_destino:
                    props_pd = self.ws._props_to_dict(pd)
                    map_prop = (props_pd.get("map") or "").replace("\\", "/")
                    if map_prop.endswith(origen_path):
                        puerta_destino = pd
                        break

            # fallback: primera puerta
            if puerta_destino is None:
                puerta_destino = puertas_destino[0]

            tx = int((puerta_destino["x"] + puerta_destino["width"] / 2) // TILE_SIZE)
            ty = int((puerta_destino["y"] + puerta_destino["height"] / 2) // TILE_SIZE)

        # crear nuevo state
        nuevo = type(self.ws)(self.ws.game, map_rel_path=destino, spawn_tile=(tx, ty))

        # aplicar lock/cooldown anti-rebote
        if puerta_destino is not None:
            nuevo.interactions.set_spawn_door_lock(
                pygame.Rect(
                    puerta_destino["x"], puerta_destino["y"],
                    puerta_destino["width"], puerta_destino["height"]
                ),
                cooldown=0.15
            )
        else:
            nuevo.interactions.set_cooldown(0.4)

        self.ws.game.change_state(nuevo)
