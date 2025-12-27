# project/engines/world_engine/world_interaction_system.py

import pygame
from core.config import TILE_SIZE


class WorldInteractionSystem:
    """
    Encapsula:
      - Puertas (edge-trigger) + cooldown + lock anti-rebote al spawnear en puerta
      - Triggers (once) / detección de colisión del jugador

    WorldState mantiene los datos de mapa (doors/triggers) y este sistema maneja su lógica.
    """

    def __init__(self, world_state, doors: list[dict], triggers: list[dict]):
        self.ws = world_state
        self.doors = doors or []
        self.triggers = triggers or []

        self._trigger_fired = set()

        # anti-loop puertas
        self._door_was_inside = False
        self._door_cooldown = 0.0  # segundos

        # lock anti-rebote: al spawnear en una puerta, bloquea puertas hasta salir del rect
        self._door_lock_until_exit = False
        self._door_lock_rect = None

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------
    def set_spawn_door_lock(self, door_rect: pygame.Rect, cooldown: float = 0.15) -> None:
        """
        Usar cuando spawneás al player dentro de un rect de puerta, para que no rebote
        instantáneamente.
        """
        self._door_lock_until_exit = True
        self._door_lock_rect = door_rect
        self._door_cooldown = float(cooldown)
        self._door_was_inside = True

    def set_cooldown(self, cooldown: float) -> None:
        self._door_cooldown = max(self._door_cooldown, float(cooldown))

    def update(self, dt: float) -> None:
        """
        Se llama en cada frame desde WorldState.update().
        """
        # Cooldown puertas
        if self._door_cooldown > 0:
            self._door_cooldown -= dt
            if self._door_cooldown < 0:
                self._door_cooldown = 0

        if self.ws.input_locked:
            return

        # Puertas
        if self._handle_doors():
            # si cambió mapa, WorldState va a cortar el update
            return

        # Triggers
        self._check_triggers()

    # -------------------------------------------------
    # Internals
    # -------------------------------------------------
    def _handle_doors(self) -> bool:
        """
        Devuelve True si disparó un cambio de mapa.
        """
        # si el player está moviéndose no evaluamos
        if self.ws.player.is_moving:
            return False

        # lock anti-rebote al spawnear en puerta
        skip_doors_this_frame = False
        if self._door_lock_until_exit and self._door_lock_rect:
            player_rect = pygame.Rect(self.ws.player.pixel_x, self.ws.player.pixel_y, TILE_SIZE, TILE_SIZE)
            if player_rect.colliderect(self._door_lock_rect):
                self._door_was_inside = True
                skip_doors_this_frame = True
            else:
                self._door_lock_until_exit = False
                self._door_lock_rect = None
                self._door_was_inside = False

        if skip_doors_this_frame:
            return False

        if self._door_cooldown != 0:
            return False

        player_rect = pygame.Rect(self.ws.player.pixel_x, self.ws.player.pixel_y, TILE_SIZE, TILE_SIZE)

        inside_any = False
        door_hit = None

        for obj in self.doors:
            door_rect = pygame.Rect(obj["x"], obj["y"], obj["width"], obj["height"])
            if player_rect.colliderect(door_rect):
                inside_any = True
                door_hit = obj
                break

        # edge-trigger: entrar a la puerta en este frame
        if inside_any and not self._door_was_inside and door_hit:
            props = self.ws._props_to_dict(door_hit)
            destino = props.get("map") or props.get("target_map")
            if destino:
                self.ws.cambiar_mapa(destino, puerta_entrada=door_hit)
                self._door_cooldown = 0.25
                return True

        self._door_was_inside = inside_any
        return False

    def _check_triggers(self) -> None:
        player_rect = pygame.Rect(self.ws.player.pixel_x, self.ws.player.pixel_y, TILE_SIZE, TILE_SIZE)

        for obj in self.triggers:
            obj_id = obj.get("id") or obj.get("name") or f'{obj.get("x")}:{obj.get("y")}'
            if obj_id in self._trigger_fired:
                continue

            rect = pygame.Rect(obj["x"], obj["y"], obj["width"], obj["height"])
            if not player_rect.colliderect(rect):
                continue

            props = self.ws._props_to_dict(obj)
            event_id = props.get("event_id")
            once = bool(props.get("once", True))

            if event_id:
                # listo para futuro: acá podrías llamar self.ws.run_event(...) etc
                pass

            if once:
                self._trigger_fired.add(obj_id)
