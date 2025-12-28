# project/engines/world_engine/assign_roles_system.py

class AssignRolesSystem:
    """
    Maneja UI + estado de asignación de roles (step type: assign_roles).

    WorldState delega:
      - start(step)
      - assign(role)
      - is_active
      - (internamente abre/cierra dialogue)
      - notifica al runner cuando termina: ws.event_runner.on_assign_roles_done(assignments)
    """

    def __init__(self, world_state):
        self.ws = world_state

        self.active = False
        self.step = None

        self.npcs = []
        self.roles = []
        self.remaining = {}
        self.idx = 0
        self.assignments_local = {}

    # -------------------------
    # API
    # -------------------------
    def start(self, step: dict) -> None:
        self.step = step
        self.active = True

        self.npcs = list(step.get("npcs", []))
        self.roles = list(step.get("roles", []))
        constraints = step.get("constraints", {}) or {}

        # remaining inicial
        self.remaining = {r: int(constraints.get(r, 1)) for r in self.roles}

        # descontar ya asignados
        already = dict(getattr(self.ws, "_event_assignments", {}) or {})
        for _npc_id, role in already.items():
            if role in self.remaining:
                self.remaining[role] -= 1

        for r in list(self.remaining.keys()):
            if self.remaining[r] < 0:
                self.remaining[r] = 0

        self.idx = 0
        self.assignments_local = {}

        self._show_prompt()

    def assign(self, role: str) -> None:
        if not self.active:
            return
        if self.idx >= len(self.npcs):
            return

        npc_id = self.npcs[self.idx]

        # Persistir asignación (runtime del evento)
        self.assignments_local[npc_id] = role
        self.ws._event_assignments[npc_id] = role

        # ✅ Persistir asignación (save / estado estable)
        # Esto es lo que habilita que el consejero aparezca en interiores por markers_static.
        try:
            self.ws.game.game_state.set_npc(str(npc_id), role=str(role))

            # --- Activar flag dinámico si está definido en el step del evento ---
            # El step original está en self.step (pasado desde el evento)
            set_flag_map = self.step.get("set_flag", {}) or {}
            # Puede ser: { "advisor": "advisor_chosen", "weapon_shop": "weapon_chosen" }
            flag_name = set_flag_map.get(str(role))
            if flag_name:
                self.ws.game.game_state.set_flag(str(flag_name), True)
        except Exception:
            pass

        # aplicar outcomes (delegado)
        self.ws._apply_role_outcomes_for_npc(npc_id)

        # consumir cupo
        if role in self.remaining and self.remaining[role] > 0:
            self.remaining[role] -= 1

        self.idx += 1
        self._show_prompt()


    # -------------------------
    # Internals
    # -------------------------
    def _show_prompt(self) -> None:
        # fin
        if self.idx >= len(self.npcs):
            self.ws._event_assignments.update(self.assignments_local)
            self.active = False

            if self.ws.dialogue.active:
                self.ws.dialogue.close()

            if self.ws.event_runner.active:
                self.ws.event_runner.on_assign_roles_done(self.ws._event_assignments)
            return

        npc_id = self.npcs[self.idx]

        remaining_bits = [f"{r}: {max(0, int(self.remaining.get(r, 0)))}" for r in self.roles]
        remaining_txt = ", ".join(remaining_bits)

        prompt_lines = [
            f"Asigná un rol para: {npc_id}",
            f"Pendientes -> {remaining_txt}"
        ]

        options = [{"text": r, "action": f"assign_role:{r}"} for r in self.roles if self.remaining.get(r, 0) > 0]
        if not options:
            options = [{"text": r, "action": f"assign_role:{r}"} for r in self.roles]

        self.ws.open_dialogue(
            "Asignación de roles",
            prompt_lines,
            options=options,
            context={"event": "assign_roles"}
        )
