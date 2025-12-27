import sys
import json
import os
import pygame

from core.assets import asset_path


class PauseState:
    def __init__(self, game, world_state):
        self.game = game
        self.world_state = world_state

        self.font = pygame.font.SysFont(None, 32)
        self.small_font = pygame.font.SysFont(None, 24)

        # menu | army | unit | bodyguards
        self.mode = "menu"
        self.selected_unit = None

        self.options = ["Ejército", "Guardaespaldas", "Guardar", "EXIT"]
        self.option_index = 0

        self.army_cols = 4
        self.army_index = 0

        # Guardaespaldas (companions en fila durante exploración)
        self.max_bodyguards = 3
        self.bodyguard_index = 0

        self.toast = ""
        self.toast_timer = 0.0

        # ✅ cache de JSON de unidades para no leer disco todo el tiempo
        self._unit_cache = {}  # unit_id -> dict cargado


    # -------------------------
    # Input
    # -------------------------
    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        # -------------------------
        # Salir / volver
        # -------------------------
        if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            if self.mode == "unit":
                self.mode = "army"
                self.selected_unit = None
                return
            if self.mode in ("army", "bodyguards"):
                self.mode = "menu"
                return

            # volver al mundo + sincronizar guardaespaldas en exploración
            if hasattr(self.world_state, "sync_bodyguards"):
                try:
                    self.world_state.sync_bodyguards()
                except Exception:
                    pass

            self.game.change_state(self.world_state)
            return

        # Atajo: cerrar pausa
        if event.key in (pygame.K_RETURN, pygame.K_p) and self.mode == "menu":
            if hasattr(self.world_state, "sync_bodyguards"):
                try:
                    self.world_state.sync_bodyguards()
                except Exception:
                    pass
            self.game.change_state(self.world_state)
            return

        # -------------------------
        # Modo específico
        # -------------------------
        if self.mode == "menu":
            self._handle_menu_input(event)
        elif self.mode == "army":
            self._handle_army_input(event)
        elif self.mode == "bodyguards":
            self._handle_bodyguards_input(event)
        else:
            self._handle_unit_input(event)


    def _handle_menu_input(self, event):
        if event.key == pygame.K_w:
            self.option_index = (self.option_index - 1) % len(self.options)
        elif event.key == pygame.K_s:
            self.option_index = (self.option_index + 1) % len(self.options)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = self.options[self.option_index]

            if chosen == "Ejército":
                self.mode = "army"
                self.army_index = 0
                return

            if chosen == "Guardaespaldas":
                if not hasattr(self.game.game_state, "bodyguards"):
                    self.game.game_state.bodyguards = []
                self.mode = "bodyguards"
                self.bodyguard_index = 0
                return

            if chosen == "Guardar":
                try:
                    from core.save_manager import save_game
                    path = save_game(self.game.game_state, slot=1)
                    print(f"[SAVE] Guardado en: {path}")
                    self.toast = "Partida guardada ✅"
                    self.toast_timer = 2.0
                except Exception as e:
                    print(f"[SAVE] Error: {e}")
                    self.toast = "Error al guardar ❌"
                    self.toast_timer = 2.0
                return

            if chosen == "EXIT":
                pygame.quit()
                sys.exit(0)


    def _handle_unit_input(self, event):
        # por ahora nada
        pass

    def _handle_army_input(self, event):
        party = self.game.game_state.party
        if not party:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.mode = "menu"
            return

        rows = max(1, (len(party) + self.army_cols - 1) // self.army_cols)
        cols = self.army_cols

        x = self.army_index % cols
        y = self.army_index // cols

        if event.key == pygame.K_a:
            x = max(0, x - 1)
        elif event.key == pygame.K_d:
            x = min(cols - 1, x + 1)
        elif event.key == pygame.K_w:
            y = max(0, y - 1)
        elif event.key == pygame.K_s:
            y = min(rows - 1, y + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.selected_unit = self.game.game_state.party[self.army_index]
            self.mode = "unit"
            return

        new_index = y * cols + x
        if new_index < len(party):
            self.army_index = new_index

    # -------------------------
    # Update / Render
    # -------------------------
    def update(self, dt):
        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast = ""
                self.toast_timer = 0.0

    def render(self, screen):
        self.world_state.render(screen)

        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        if self.mode == "menu":
            self._render_menu(screen)
        elif self.mode == "army":
            self._render_army(screen)
        elif self.mode == "bodyguards":
            self._render_bodyguards(screen)
        else:
            self._render_unit(screen)


    # -------------------------
    # Data helpers (✅ lo importante)
    # -------------------------
    def _load_unit_data(self, unit_id: str) -> dict:
        """
        Carga JSON del personaje por id, con cache.

        Soporta:
        - assets/data/... (units/characters)
        - assets/sprites/npcs/<id>/<id>.json (NPCs reclutables)
        """
        unit_id = str(unit_id)

        if unit_id in self._unit_cache:
            return self._unit_cache[unit_id]

        candidates = [
            # data-driven
            asset_path("data", "units", f"{unit_id}.json"),
            asset_path("data", "characters", f"{unit_id}.json"),
            asset_path("units", f"{unit_id}.json"),
            asset_path("characters", f"{unit_id}.json"),
            # ✅ NPCs reclutables (tu caso)
            asset_path("sprites", "npcs", unit_id, f"{unit_id}.json"),
        ]

        data = {}
        for p in candidates:
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                    break
            except Exception:
                continue

        self._unit_cache[unit_id] = data
        return data


    def _resolve_stats(self, party_unit: dict) -> dict:
        """
        Devuelve un dict unificado:
        - base: JSON del unit_id (incluye NPCs en sprites/npcs)
        - override: party_unit["extra"] si existe (stats guardados al reclutar)
        - fallback: fields directos en party_unit

        Además:
        - Si el JSON trae combat_profile.base_stats, aplana esas claves al nivel raíz
            (level/hp/str/def/dex/spd/res/cha, etc.)
        - Normaliza sinónimos típicos (atk->str, defense->def, speed->spd).
        """
        unit_id = party_unit.get("id") or party_unit.get("unit_id") or "unknown"
        base = self._load_unit_data(unit_id)

        extra = party_unit.get("extra") or {}
        resolved: dict = {}

        # Mezcla: base -> extra -> party_unit (último gana)
        if isinstance(base, dict):
            resolved.update(base)
        if isinstance(extra, dict):
            resolved.update(extra)
        if isinstance(party_unit, dict):
            resolved.update(party_unit)

        # 1) Si existe combat_profile.base_stats, lo aplanamos
        try:
            combat_profile = resolved.get("combat_profile")
            if isinstance(combat_profile, dict):
                base_stats = combat_profile.get("base_stats")
                if isinstance(base_stats, dict):
                    for k, v in base_stats.items():
                        # no pisamos si ya existe (por ejemplo si extra lo guardó)
                        resolved.setdefault(k, v)
        except Exception:
            pass

        # 2) Si existe "stats": {...}, también lo aplanamos
        stats = resolved.get("stats")
        if isinstance(stats, dict):
            for k, v in stats.items():
                resolved.setdefault(k, v)

        # 3) Normalización de sinónimos (sin romper tu esquema principal)
        # ATK suele venir como "atk" pero vos usás "str"
        if "str" not in resolved and "atk" in resolved:
            resolved["str"] = resolved.get("atk")

        # DEF puede venir como "defense"
        if "def" not in resolved and "defense" in resolved:
            resolved["def"] = resolved.get("defense")

        # SPD puede venir como "speed"
        if "spd" not in resolved and "speed" in resolved:
            resolved["spd"] = resolved.get("speed")

        # RES/CHA: a veces en mayúscula
        if "res" not in resolved and "RES" in resolved:
            resolved["res"] = resolved.get("RES")
        if "cha" not in resolved and "CHA" in resolved:
            resolved["cha"] = resolved.get("CHA")

        return resolved

    # -------------------------
    # Render UI
    # -------------------------
    def _render_menu(self, screen):
        w, h = screen.get_width(), screen.get_height()
        box_w, box_h = 320, 200
        box = pygame.Rect(w - box_w - 24, 24, box_w, box_h)

        pygame.draw.rect(screen, (10, 10, 10), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        title = self.font.render("PAUSA", True, (255, 255, 255))
        screen.blit(title, (box.x + 18, box.y + 14))

        y = box.y + 60
        for i, opt in enumerate(self.options):
            prefix = "▶ " if i == self.option_index else "  "
            surf = self.font.render(prefix + opt, True, (255, 255, 255))
            screen.blit(surf, (box.x + 18, y))
            y += 36

        if self.toast:
            toast_surf = self.small_font.render(self.toast, True, (200, 255, 200))
            screen.blit(toast_surf, (box.x + 18, box.bottom - 28))

        hint = self.small_font.render("W/S elegir  ENTER confirmar  ESC volver", True, (200, 200, 200))
        screen.blit(hint, (24, h - 32))

    def _render_army(self, screen):
        w, h = screen.get_width(), screen.get_height()
        box = pygame.Rect(24, 24, w - 48, h - 80)

        pygame.draw.rect(screen, (10, 10, 10), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        title = self.font.render("EJÉRCITO", True, (255, 255, 255))
        screen.blit(title, (box.x + 18, box.y + 14))

        party = self.game.game_state.party
        if not party:
            msg = self.font.render("No tienes soldados reclutados.", True, (255, 255, 255))
            screen.blit(msg, (box.x + 18, box.y + 70))
            hint = self.small_font.render("ESC volver", True, (200, 200, 200))
            screen.blit(hint, (24, h - 32))
            return

        grid_top = box.y + 60
        grid_left = box.x + 18
        grid_w = box.width - 36
        grid_h = box.height - 90

        cols = self.army_cols
        rows = max(1, (len(party) + cols - 1) // cols)

        cell_w = grid_w // cols
        cell_h = max(60, grid_h // max(rows, 1))

        for idx, unit in enumerate(party):
            cx = idx % cols
            cy = idx // cols

            rect = pygame.Rect(
                grid_left + cx * cell_w,
                grid_top + cy * cell_h,
                cell_w - 10,
                cell_h - 10
            )

            pygame.draw.rect(screen, (20, 20, 20), rect)
            pygame.draw.rect(screen, (120, 120, 120), rect, 2)

            name = unit.get("name") or unit.get("id", "???")
            name_surf = self.small_font.render(name, True, (255, 255, 255))
            screen.blit(name_surf, (rect.x + 10, rect.y + 10))

            id_surf = self.small_font.render(unit.get("id", ""), True, (180, 180, 180))
            screen.blit(id_surf, (rect.x + 10, rect.y + 32))

            if idx == self.army_index:
                pygame.draw.rect(screen, (240, 220, 80), rect, 3)

        hint = self.small_font.render("W/A/S/D mover  ENTER ficha  ESC volver", True, (200, 200, 200))
        screen.blit(hint, (24, h - 32))

    def _render_unit(self, screen):
        w, h = screen.get_width(), screen.get_height()
        box = pygame.Rect(24, 24, w - 48, h - 80)

        pygame.draw.rect(screen, (10, 10, 10), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        title = self.font.render("FICHA", True, (255, 255, 255))
        screen.blit(title, (box.x + 18, box.y + 14))

        party_unit = self.selected_unit or {}
        u = self._resolve_stats(party_unit)

        name = u.get("name") or party_unit.get("name") or u.get("id", "???")
        unit_id = u.get("id", party_unit.get("id", "???"))

        level = u.get("level", "-")
        hp = u.get("hp", "-")
        str_ = u.get("str", u.get("atk", "-"))
        deff = u.get("def", u.get("defense", "-"))
        dex = u.get("dex", "-")
        spd = u.get("spd", u.get("speed", "-"))
        res = u.get("res", u.get("RES", "-"))
        cha = u.get("cha", u.get("CHA", "-"))

        lines = [
            f"Nombre: {name}",
            f"ID: {unit_id}",
            "",
            f"LEVEL: {level}",
            f"HP:    {hp}",
            f"STR:   {str_}",
            f"DEF:   {deff}",
            f"DEX:   {dex}",
            f"SPD:   {spd}",
            f"RES:   {res}",
            f"CHA:   {cha}",
        ]

        y = box.y + 70
        for line in lines:
            surf = self.font.render(line, True, (255, 255, 255))
            screen.blit(surf, (box.x + 18, y))
            y += 36 if line == "" else 30

        hint = self.small_font.render("ESC volver", True, (200, 200, 200))
        screen.blit(hint, (24, h - 32))

    def _handle_bodyguards_input(self, event):
        party = self.game.game_state.party or []

        if not hasattr(self.game.game_state, "bodyguards"):
            self.game.game_state.bodyguards = []

        bodyguards = list(self.game.game_state.bodyguards or [])

        if not party:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.mode = "menu"
            return

        rows = max(1, (len(party) + self.army_cols - 1) // self.army_cols)
        cols = self.army_cols

        x = self.bodyguard_index % cols
        y = self.bodyguard_index // cols

        if event.key == pygame.K_a:
            x = max(0, x - 1)
        elif event.key == pygame.K_d:
            x = min(cols - 1, x + 1)
        elif event.key == pygame.K_w:
            y = max(0, y - 1)
        elif event.key == pygame.K_s:
            y = min(rows - 1, y + 1)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            chosen = party[self.bodyguard_index]
            uid = chosen.get("id") or chosen.get("unit_id")
            if not uid:
                return
            uid = str(uid)

            if uid in bodyguards:
                bodyguards = [x for x in bodyguards if x != uid]
                self.toast = f"{chosen.get('name', uid)} ya no es guardaespaldas."
                self.toast_timer = 2.0
            else:
                if len(bodyguards) >= self.max_bodyguards:
                    self.toast = f"Máximo {self.max_bodyguards} guardaespaldas."
                    self.toast_timer = 2.0
                    return
                bodyguards.append(uid)
                self.toast = f"{chosen.get('name', uid)} asignado como guardaespaldas."
                self.toast_timer = 2.0

            self.game.game_state.bodyguards = bodyguards
            return

        new_index = y * cols + x
        if new_index < len(party):
            self.bodyguard_index = new_index

    def _render_bodyguards(self, screen):
        w, h = screen.get_width(), screen.get_height()
        box = pygame.Rect(24, 24, w - 48, h - 80)

        pygame.draw.rect(screen, (10, 10, 10), box)
        pygame.draw.rect(screen, (255, 255, 255), box, 2)

        title = self.font.render("GUARDAESPALDAS", True, (255, 255, 255))
        screen.blit(title, (box.x + 18, box.y + 14))

        if not hasattr(self.game.game_state, "bodyguards"):
            self.game.game_state.bodyguards = []

        bodyguards = list(self.game.game_state.bodyguards or [])
        party = list(self.game.game_state.party or [])

        subtitle = self.small_font.render(
            f"Elegí hasta {self.max_bodyguards}. En traición letal, sólo ellos combaten.",
            True,
            (200, 200, 200),
        )
        screen.blit(subtitle, (box.x + 18, box.y + 46))

        if not party:
            msg = self.font.render("No tenés reclutas todavía.", True, (255, 255, 255))
            screen.blit(msg, (box.x + 18, box.y + 90))
        else:
            cols = self.army_cols
            cell_w = (box.width - 36) // cols
            cell_h = 60

            start_x = box.x + 18
            start_y = box.y + 80

            for i, u in enumerate(party):
                cx = i % cols
                cy = i // cols
                rect = pygame.Rect(
                    start_x + cx * cell_w,
                    start_y + cy * cell_h,
                    cell_w - 10,
                    cell_h - 10,
                )

                is_sel = (i == self.bodyguard_index)
                pygame.draw.rect(screen, (35, 35, 35), rect)
                pygame.draw.rect(screen, (255, 255, 255), rect, 2 if is_sel else 1)

                uid = str(u.get("id") or u.get("unit_id") or "")
                name = u.get("name", uid) if uid else u.get("name", "???")

                marker = "★ " if uid and uid in bodyguards else "  "
                label = self.small_font.render(marker + name, True, (255, 255, 255))
                screen.blit(label, (rect.x + 10, rect.y + 10))

                stats = self._resolve_stats(u)
                hp = stats.get("hp", "-")
                str_ = stats.get("str", stats.get("atk", "-"))
                deff = stats.get("def", stats.get("defense", "-"))
                mini = self.small_font.render(f"HP {hp} | STR {str_} | DEF {deff}", True, (200, 200, 200))
                screen.blit(mini, (rect.x + 10, rect.y + 32))

        if self.toast:
            toast_surf = self.small_font.render(self.toast, True, (200, 255, 200))
            screen.blit(toast_surf, (box.x + 18, box.bottom - 28))

        hint = self.small_font.render("WASD mover  ENTER alternar  ESC volver", True, (200, 200, 200))
        screen.blit(hint, (24, h - 32))
