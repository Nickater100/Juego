# project/engines/world_engine/event_runner.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Waiting:
    kind: str  # "dialogue" | "talk_block" | "assign_roles"


class EventRunner:
    """
    Runner de eventos JSON (data-driven) con:
      - trigger="auto": ejecuta inmediatamente
      - trigger="talk": se ejecuta al interactuar con npc_id

    Extensión genérica:
      - Los talk consecutivos se agrupan en un talk_block (orden libre).
      - Cada talk-step puede tener un campo "post": [steps...]
        que se ejecutan inmediatamente después de cerrar el diálogo de ese NPC.
      - assign_roles soporta: npc_from="last_talk"
        para aplicar el menú al NPC con el que recién hablaste.

    Requisitos en WorldState:
      - ws.input_locked: bool
      - ws.open_dialogue(speaker, lines, options=None, context=None)
      - ws._start_assign_roles(step_dict)
      - ws.game.game_state.get_flag / set_flag
      - ws._event_assignments (dict) usado por tu UI de roles
    """

    def __init__(self, ws: Any):
        self.ws = ws
        self.active: bool = False

        self._once_flag: Optional[str] = None
        self._steps: List[Dict[str, Any]] = []
        self._idx: int = 0

        self._waiting: Optional[Waiting] = None

        # talk_block: npc_id -> step(dialogue talk)
        self._talk_pending: Dict[str, Dict[str, Any]] = {}

        # contexto del evento (genérico)
        self._ctx: Dict[str, Any] = {}

        # cola de pasos post-diálogo (para "después de hablar con X")
        self._post_queue: List[Dict[str, Any]] = []

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
        self._ctx = {}
        self._post_queue = []

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

        # Pre-scan útil para tu assign_roles/outcomes
        for step in self._steps:
            if step.get("type") == "apply_role_outcomes":
                self.ws._event_apply_role_outcomes_step = step

        self.advance()

    def update(self, dt: float) -> None:
        return

    # -------------------------
    # Main loop
    # -------------------------
    def advance(self) -> None:
        """Ejecuta steps en orden hasta que haya que esperar algo."""
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
                # armamos el bloque (talks consecutivos)
                self._enter_talk_block()
                return

            # auto: consumir y ejecutar
            self._idx += 1
            self._exec_step(step)

    def _enter_talk_block(self) -> None:
        self._talk_pending = {}

        while self._idx < len(self._steps):
            step = self._steps[self._idx]
            trigger = (step.get("trigger") or "auto").lower()
            if trigger != "talk":
                break

            npc_id = step.get("npc_id")
            if npc_id:
                self._talk_pending[str(npc_id)] = step

            # consumimos el step del stream (queda pendiente en el bloque)
            self._idx += 1

        if not self._talk_pending:
            # no había talks válidos, seguimos
            return

        self.ws.input_locked = False
        self._waiting = Waiting(kind="talk_block")

    # -------------------------
    # Hooks desde WorldState
    # -------------------------
    def on_player_interact(self, npc_id: str) -> bool:
        """
        Si estamos en talk_block y el npc_id está pendiente:
          - ejecuta el diálogo del evento
          - programa los pasos post (si existen) para correr al cerrar el diálogo
        """
        if not self.active:
            return False
        if not self._waiting or self._waiting.kind != "talk_block":
            return False

        step = self._talk_pending.get(str(npc_id))
        if not step:
            return False

        # Consumimos el talk del bloque
        self._talk_pending.pop(str(npc_id), None)

        # Guardamos contexto genérico: último NPC hablado
        self._ctx["last_talk_npc_id"] = str(npc_id)

        # Programar post-steps (si existen)
        self._post_queue = list(step.get("post", []) or [])

        # Bloquear input mientras dura el diálogo / UI
        self.ws.input_locked = True

        # Ejecutar el diálogo (deja waiting="dialogue")
        self._exec_step(step)

        return True

    def on_dialogue_closed(self) -> None:
        """
        Llamar cuando se cierra un diálogo que abrió el runner.
        Ejecuta post-steps si hay, si no vuelve al talk_block o continúa el evento.
        """
        if not self.active:
            return

        if self._waiting and self._waiting.kind == "dialogue":
            self._waiting = None

            # 1) Si hay post-steps, ejecutar el siguiente inmediatamente
            if self._post_queue:
                next_step = self._post_queue.pop(0)
                self._exec_step(next_step)
                return

            # 2) Si todavía quedan talk pendientes del bloque, soltar input y esperar más interacciones
            if self._talk_pending:
                self.ws.input_locked = False
                self._waiting = Waiting(kind="talk_block")
                return

            # 3) Si no quedan talks, seguir con auto-steps
            self.ws.input_locked = True
            self.advance()

    def on_assign_roles_done(self, assignments: Dict[str, str]) -> None:
        """
        Llamar cuando termina el UI de assign_roles.
        Si hay post_queue restante, seguir ejecutándola.
        Si no, volver al talk_block (si quedan) o continuar.
        """
        if not self.active:
            return

        # guardar assignments (tu WorldState ya los usa)
        if assignments:
            try:
                self.ws._event_assignments = dict(getattr(self.ws, "_event_assignments", {}) or {})
                self.ws._event_assignments.update(assignments)
            except Exception:
                pass

        if self._waiting and self._waiting.kind == "assign_roles":
            self._waiting = None

            # 1) Si hay más post-steps, ejecutarlos ya
            if self._post_queue:
                next_step = self._post_queue.pop(0)
                self.ws.input_locked = True
                self._exec_step(next_step)
                return

            # 2) Si estamos todavía en un talk_block (quedan NPCs por hablar), volver a soltar input
            if self._talk_pending:
                self.ws.input_locked = False
                self._waiting = Waiting(kind="talk_block")
                return

            # 3) Continuar el evento
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
        self._post_queue = {}
        self._ctx = {}
        self.ws.input_locked = False

    # -------------------------
    # Step execution
    # -------------------------
    def _exec_step(self, step: Dict[str, Any]) -> None:
        t = (step.get("type") or "").lower()

        if t == "dialogue":
            speaker = step.get("speaker", "")
            lines = step.get("lines", []) or []

            # (por si en el futuro querés opciones en diálogos de evento)
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
            # ✅ soporte npc_from:"last_talk"
            step = dict(step)  # copia segura (no muta el JSON original)
            npc_from = step.get("npc_from")

            if npc_from == "last_talk":
                npc_id = self._ctx.get("last_talk_npc_id")
                if npc_id:
                    step["npcs"] = [npc_id]
                else:
                    # si no hay last_talk, no hacemos nada (evento mal armado)
                    return

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

            # Agrupar por "base role": soldier_1/soldier_2 -> soldier
            buckets: Dict[str, List[str]] = {}
            for role_key, marker_id in role_to_marker.items():
                base = str(role_key).split("_", 1)[0]
                buckets.setdefault(base, []).append(str(marker_id))

            assignments = dict(getattr(self.ws, "_event_assignments", {}) or {})
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

        # Step desconocido -> ignorar
        return

    def _tile_size(self) -> int:
        try:
            from core.config import TILE_SIZE
            return int(TILE_SIZE)
        except Exception:
            return 32
