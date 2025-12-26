# project/engines/world_engine/event_runner.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Waiting:
    kind: str  # "dialogue" | "talk_block" | "assign_roles"


class EventRunner:
    """
    Event runner JSON con triggers:
      - trigger="auto": se ejecuta automáticamente
      - trigger="talk": se ejecuta cuando el jugador interactúa con npc_id

    Importante (genérico y escalable):
      - Los steps talk consecutivos se tratan como un "talk_block":
        el jugador puede completarlos en cualquier orden.
        Al finalizar el bloque, el runner continúa con el siguiente step.
    """

    def __init__(self, ws: Any):
        self.ws = ws
        self.active: bool = False

        self._once_flag: Optional[str] = None
        self._steps: List[Dict[str, Any]] = []
        self._idx: int = 0

        self._waiting: Optional[Waiting] = None

        # talk_block: npc_id -> step
        self._talk_pending: Dict[str, Dict[str, Any]] = {}

        # assignments si los necesitás desde el runner
        self.assignments: Dict[str, str] = {}

    # -------------------------
    # Lifecycle
    # -------------------------
    def reset(self) -> None:
        self.active = False
        self._once_flag = None
        self._steps = []
        self._idx = 0
        self._waiting = None
        self._talk_pending = {}
        self.assignments = {}
        # no fuerzo input_locked acá: start()/finish() lo controlan

    def start(self, event_json: Dict[str, Any]) -> None:
        self.reset()

        event_json = event_json or {}
        self._once_flag = event_json.get("once_flag")

        if self._once_flag and self.ws.game.game_state.get_flag(self._once_flag, False):
            self.ws.input_locked = False
            return

        self._steps = list(event_json.get("steps", []) or [])
        self._idx = 0
        self.active = True
        self.ws.input_locked = True

        # Pre-scan para outcomes (sirve para tu assign_roles)
        for step in self._steps:
            if step.get("type") == "apply_role_outcomes":
                self.ws._event_apply_role_outcomes_step = step

        self.advance()

    def update(self, dt: float) -> None:
        # si luego agregás wait/timers, acá
        return

    # -------------------------
    # Main loop
    # -------------------------
    def advance(self) -> None:
        """Ejecuta steps en orden hasta esperar algo o finalizar."""
        if not self.active:
            return
        if self._waiting is not None:
            return

        while self.active and self._waiting is None:
            if self._idx >= len(self._steps):
                self.finish()
                return

            step = self._steps[self._idx]
            trigger = (step.get("trigger") or "auto").lower()

            if trigger == "talk":
                # Armar bloque: todos los talk consecutivos
                self._enter_talk_block()
                return

            # auto: consumimos el step y lo ejecutamos
            self._idx += 1
            self._exec_step(step)

    def _enter_talk_block(self) -> None:
        """Agrupa todos los talk consecutivos en un bloque pendiente."""
        self._talk_pending = {}

        while self._idx < len(self._steps):
            step = self._steps[self._idx]
            trigger = (step.get("trigger") or "auto").lower()
            if trigger != "talk":
                break

            npc_id = step.get("npc_id")
            if npc_id:
                self._talk_pending[str(npc_id)] = step

            # OJO: consumimos el step igualmente del stream (el bloque lo gestiona)
            self._idx += 1

        # si no había npc_id válidos, seguimos
        if not self._talk_pending:
            return

        # Soltar input para que el jugador pueda ir a hablarles
        self.ws.input_locked = False
        self._waiting = Waiting(kind="talk_block")

    # -------------------------
    # Hooks desde WorldState
    # -------------------------
    def on_player_interact(self, npc_id: str) -> bool:
        """
        Se llama desde WorldState.try_interact().
        Si estamos en talk_block y npc_id está pendiente, abre el diálogo del evento.
        """
        if not self.active:
            return False
        if not self._waiting or self._waiting.kind != "talk_block":
            return False

        step = self._talk_pending.get(str(npc_id))
        if not step:
            return False

        # Consumimos ese talk
        self._talk_pending.pop(str(npc_id), None)

        # Bloqueamos input mientras dura el diálogo
        self.ws.input_locked = True

        # Ejecutamos el step (normalmente abre diálogo y nos deja waiting="dialogue")
        self._exec_step(step)

        return True

    def on_dialogue_closed(self) -> None:
        """Llamar al cerrar un diálogo que abrió el runner."""
        if not self.active:
            return

        if self._waiting and self._waiting.kind == "dialogue":
            self._waiting = None

            # Si todavía quedan talks del bloque, volver a soltar input
            if self._talk_pending:
                self.ws.input_locked = False
                self._waiting = Waiting(kind="talk_block")
                return

            # Si no quedan talks, seguimos con auto steps
            self.ws.input_locked = True
            self.advance()

    def on_assign_roles_done(self, assignments: Dict[str, str]) -> None:
        """Llamar cuando termina el UI de assign_roles."""
        if not self.active:
            return

        if assignments:
            self.assignments.update(assignments)
            # guardar también en WorldState si existe
            try:
                self.ws._event_assignments = dict(self.ws._event_assignments or {})
                self.ws._event_assignments.update(assignments)
            except Exception:
                pass

        if self._waiting and self._waiting.kind == "assign_roles":
            self._waiting = None
            self.ws.input_locked = True
            self.advance()

    # -------------------------
    # Finish
    # -------------------------
    def finish(self) -> None:
        if self._once_flag:
            self.ws.game.game_state.set_flag(self._once_flag, True)
        self.active = False
        self._waiting = None
        self._talk_pending = {}
        self.ws.input_locked = False

    # -------------------------
    # Step execution
    # -------------------------
    def _exec_step(self, step: Dict[str, Any]) -> None:
        t = (step.get("type") or "").lower()

        if t == "dialogue":
            speaker = step.get("speaker", "")
            lines = step.get("lines", []) or []

            # ✅ soporte de opciones desde JSON (para menú de opciones si tu evento lo usa)
            options = step.get("options") or step.get("choices") or None

            self.ws.open_dialogue(
                speaker,
                lines,
                options=options,
                context={
                    "event": "json_event",
                    "after_dialogue": self.on_dialogue_closed,
                },
            )
            self._waiting = Waiting(kind="dialogue")
            return

        if t == "assign_roles":
            self.ws._start_assign_roles(step)
            self._waiting = Waiting(kind="assign_roles")
            return

        if t == "set_flag":
            flag_name = step.get("flag") or step.get("name")
            if flag_name:
                self.ws.game.game_state.set_flag(str(flag_name), step.get("value", True))
            return

        if t == "apply_role_outcomes":
            self.ws._event_apply_role_outcomes_step = step
            return

        if t == "apply_role_spawns":
            role_to_marker = step.get("role_to_marker", {}) or {}
            if not role_to_marker:
                return

            # agrupamos por "base role": soldier_1, soldier_2 -> soldier
            buckets: Dict[str, List[str]] = {}
            for role_key, marker_id in role_to_marker.items():
                base = str(role_key).split("_", 1)[0]
                buckets.setdefault(base, []).append(str(marker_id))

            assignments = {}
            try:
                assignments = dict(getattr(self.ws, "_event_assignments", {}) or {})
            except Exception:
                assignments = dict(self.assignments or {})

            for npc_id, role in assignments.items():
                base = str(role).split("_", 1)[0]
                if base not in buckets or not buckets[base]:
                    continue

                marker_id = buckets[base].pop(0)
                target = getattr(self.ws, "markers", {}).get(marker_id)
                if not target:
                    continue

                if npc_id in getattr(self.ws, "npc_units", {}):
                    u = self.ws.npc_units[npc_id]
                    u.tile_x, u.tile_y = target
                    u.pixel_x = target[0] * self._tile_size()
                    u.pixel_y = target[1] * self._tile_size()
            return

        # step desconocido -> ignorar
        return

    def _tile_size(self) -> int:
        try:
            from core.config import TILE_SIZE
            return int(TILE_SIZE)
        except Exception:
            return 32
